import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"scripts"))
import runtime_batch as b,repair_batch as batch,repair_env as env,repair_executor as runner,runtime_collect as collect

class AuthoredRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)/"batch"
        b.build(ROOT/"configs/runtime-v0.12/batch.json",cls.root)
        cls.scenario=b.read(cls.root/"tasks/repair-denominator-integrity-clean-v1/scenario.json")
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_authored_cases_and_workflow_controls(self):
        result=b.verify(self.root);self.assertEqual((result["tasks"],result["real_incident_chains"]),(1,0))
        run=batch.run_reference(self.scenario);self.assertEqual(run["grade"]["reward"],1)
        self.assertTrue(any(x["action"]["tool"]=="test" and not x["observation"]["test"]["passed"] for x in run["events"]))
        self.assertTrue(runner.run_cases(self.scenario["reference_code"],self.scenario["public_cases"]+self.scenario["private_cases"])["passed"])
        self.assertFalse(b.lines(self.root/"training/scripted-trajectories.jsonl"))
    def test_partial_fix_and_reject_all_cannot_pass(self):
        partial=batch.run_reference(self.scenario,"partial_fix")
        self.assertTrue(partial["final_state"]["tests"][-1]["passed"])
        self.assertFalse(partial["grade"]["checks"]["private_behavior"]);self.assertEqual(partial["grade"]["reward"],0)
        for name in self.scenario["control_codes"]:
            with self.subTest(control=name):self.assertEqual(batch.run_reference(self.scenario,name)["grade"]["reward"],0)
    def test_private_data_and_reference_stay_outside_policy_context(self):
        runtime=env.ResearchEnv(self.scenario)
        for doc in runtime.initial["documents"]:runtime.step({"tool":"read","args":{"document_id":doc}})
        config=b.read(ROOT/"configs/runtime-v0.12/collection.json")
        request=collect.request_for(runtime,config,30,100)
        text=json.dumps(request);self.assertNotIn("private_cases",text);self.assertNotIn("control_codes",text)
        for case in self.scenario["private_cases"]:self.assertNotIn(case["name"],text)
        self.assertEqual(runtime.step({"tool":"read","args":{"document_id":"private_cases"}})[0]["status"],404)
        self.assertFalse(collect.training_eligible({"split":"development","reward":1},self.scenario))
    def test_record_order_and_local_labels_do_not_change_final_decision(self):
        case=self.scenario["public_cases"][1];data=copy.deepcopy(case["input"])
        for side in ("baseline","candidate"):
            data[side].reverse()
            for row in data[side]:row["label_pass"]=not row["label_pass"]
        self.assertEqual(runner.execute(self.scenario["reference_code"],data),case["expected"])
    def test_rehashed_task_cannot_rewrite_private_answers(self):
        import shutil
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"batch";shutil.copytree(self.root,root)
            path=root/"tasks/repair-denominator-integrity-clean-v1/scenario.json";value=b.read(path)
            value["private_cases"][0]["expected"]={"ok":True,"value":"forged"};path.write_bytes(b.encoded(value))
            manifest=b.read(root/"manifest.json");manifest["files"]=b.hashes(root);(root/"manifest.json").write_bytes(b.encoded(manifest))
            with self.assertRaisesRegex(ValueError,"task_lineage_changed"):b.verify(root)
if __name__=="__main__":unittest.main()
