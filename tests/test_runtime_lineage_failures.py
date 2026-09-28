import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"scripts"))
import runtime_batch as b,source_catalog as catalog,failure_exports as failures
class CatalogTests(unittest.TestCase):
    def row(self,component="old",task="T",family="F",split="development",eligible=False,**extra):
        return catalog.project(component,{"task_id":task,"family_id":family,"split":split,"rights":{"training_eligible":eligible},**extra},1)
    def test_original_case_versions_are_distinct_records(self):
        a=catalog.project("old",{"case_id":"C","case_version_id":"C","split":"development"},1);z=catalog.project("old",{"case_id":"C","case_version_id":"C-r2","split":"development","revision_of":"C"},2)
        rows=catalog.resolve([a,z]);self.assertNotEqual(rows[0]["record_id"],rows[1]["record_id"]);self.assertEqual(rows[0]["lineage_group_id"],rows[1]["lineage_group_id"])
    def test_renamed_identical_content_is_not_new_source(self):
        rows=catalog.resolve([self.row(source_sha256="same"),self.row("v0.10","renamed","new-family",source_sha256="same")]);self.assertEqual(catalog.stats(rows)["new_independent_source_groups"],0)
    def test_parent_alias_cannot_cross_train_test(self):
        with self.assertRaisesRegex(ValueError,"train_test_leakage"):catalog.resolve([self.row(split="train",eligible=True),self.row("new","N","G","test",True,parent_task_id="T")])
    def test_restricted_source_cannot_be_promoted(self):
        with self.assertRaisesRegex(ValueError,"inherited_use_promotion"):catalog.resolve([self.row(),self.row("new","N","G","train",True,parent_task_id="T")])
    def test_all_retained_catalog_records_and_new_variants(self):
        result=catalog.verify(ROOT/"data/runtime-catalog-v0.10");self.assertEqual((result["records"],result["new_task_variants"],result["new_independent_source_groups"]),(205,9,0))
    def test_next_version_inherits_the_previous_catalog(self):
        import shutil
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);batch=root/"batch";batch.mkdir();original=ROOT/"data/runtime-batch-v0.10"
            for name in ("config.json","tasks.jsonl","manifest.json"):shutil.copyfile(original/name,batch/name)
            config=b.read(batch/"config.json");config["dataset_version"]="0.11";config["prior_release"]["tag"]="dataset-v0.10";(batch/"config.json").write_bytes(b.encoded(config))
            result=catalog.build(ROOT,batch,root/"catalog")
            self.assertEqual((result["records"],result["components"],result["new_independent_source_groups"]),(214,12,0))
            self.assertEqual(b.read(root/"catalog/sources.json")[-1]["component"],"v0.11")
    def test_rehashed_catalog_projection_tamper(self):
        import shutil
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/"catalog";shutil.copytree(ROOT/"data/runtime-catalog-v0.10",out);rows=b.lines(out/"records.jsonl");rows[0]["training_eligible"]=True
            (out/"records.jsonl").write_text("".join(json.dumps(x)+"\n" for x in rows));(out/"manifest.json").write_bytes(b.encoded({"files":b.hashes(out)}))
            with self.assertRaisesRegex(ValueError,"catalog_projection_changed"):catalog.verify(out)
class FailureExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)/"export"
        failures.build(ROOT,ROOT/"data/runtime-batch-v0.9",ROOT/"data/runtime-model-v0.9",cls.root)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_historical_budget_censoring_is_retained(self):
        rows=b.lines(self.root/"failures.jsonl");censored=[r for r in rows if r["category"]=="external_budget_truncation"]
        self.assertEqual(len(censored),3);self.assertTrue(all(r["censored"] and r["action"] is None for r in censored))
    def test_censored_original_has_no_invented_terminal_grade(self):
        source=next(x for x in b.read(self.root/"sources.json") if x["component"]=="v0.6")
        original=b.read(self.root/source["original_episode"]);self.assertIsNone(original["outcome"]);self.assertFalse(original["complete"])
    def test_preserved_prefixes_are_not_new_failures(self):
        result=failures.verify(self.root);self.assertLess(result["unique_observed_failures"],result["failure_records"])
    def test_training_pairs_have_positive_terminal_and_allowed_source(self):
        pairs=b.lines(self.root/"training/recovery-pairs.jsonl");self.assertTrue(pairs)
        for row in pairs:
            self.assertEqual(row["split"],"train");self.assertTrue(row["rights"]["training_eligible"]);self.assertTrue(row["verification"]["goal_verified_separately"]);self.assertEqual(set(row["context"]),{"initial_observation","history"})
        self.assertEqual(len(pairs),len({r["event_fingerprint"] for r in pairs}))
    def test_expected_baseline_is_not_labeled_policy_error(self):
        event={"action":{"tool":"test","args":{}},"observation":{"status":200,"test":{"passed":False,"version":1}}};self.assertEqual(failures.classify(event),"expected_reproduction_failure")
        event["observation"]["test"]["version"]=2;self.assertEqual(failures.classify(event),"candidate_test_failure")
    def test_denied_patch_is_not_missing_evidence(self):
        event={"action":{"tool":"patch","args":{}},"observation":{"status":403}};self.assertEqual(failures.classify(event),"policy_action_contract_error")
    def test_rehashed_rights_promotion_rejected(self):
        import shutil
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/"export";shutil.copytree(self.root,out);sources=b.read(out/"sources.json");source=next(x for x in sources if b.read(out/x["snapshot"])["rights"]["training_eligible"] is False)
            value=b.read(out/source["snapshot"]);value["rights"]["training_eligible"]=True;(out/source["snapshot"]).write_bytes(b.encoded(value));source["sha256"]=b.sha((out/source["snapshot"]).read_bytes());(out/"sources.json").write_bytes(b.encoded(sources));(out/"manifest.json").write_bytes(b.encoded({"files":b.hashes(out)}))
            with self.assertRaisesRegex(ValueError,"failure_rights_or_index_changed"):failures.verify(out)
    def test_wrong_failure_category_rejected_after_rehash(self):
        import shutil
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/"export";shutil.copytree(self.root,out);rows=b.lines(out/"failures.jsonl");rows[0]["category"]="model_error";(out/"failures.jsonl").write_text("".join(json.dumps(x)+"\n" for x in rows));(out/"manifest.json").write_bytes(b.encoded({"files":b.hashes(out)}))
            with self.assertRaisesRegex(ValueError,"failure_export_projection_changed"):failures.verify(out)
    def test_public_recovery_does_not_imply_terminal_success(self):
        index={"task_id":"T","family_id":"F","split":"train","reward":0,"complete":True};event=lambda step,version,passed:{"step":step,"action":{"tool":"test","args":{}},"observation":{"status":200,"test":{"version":version,"passed":passed,"code_sha256":str(version)}}}
        run={"events":[event(1,1,False),event(2,2,True)],"actor_kind":"isolated_model_cli","stop_reason":None,"grade":{"reward":0,"checks":{"private_behavior":False}},"final_state":{}}
        rows,pairs=failures.project("test",index,run,{}, {"training_eligible":True});self.assertEqual(len(pairs),1);self.assertFalse(pairs[0]["training_eligible"]);self.assertFalse(pairs[0]["verification"]["goal_verified_separately"]);self.assertEqual(rows[-1]["category"],"terminal_verification_failure")
if __name__=="__main__":unittest.main()
