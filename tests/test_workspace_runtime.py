import copy,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"scripts"))
import runtime_batch as b, runtime_collect as c, workspace_batch as wb, workspace_env as e, workspace_tasks as t

class WorkspaceRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.batch=Path(cls.temp.name)/"batch"
        b.build(ROOT/"configs/runtime-v0.11/batch.json",cls.batch)
        cls.scenarios={r["task_id"]:b.read(cls.batch/r["scenario"]) for r in b.lines(cls.batch/"tasks.jsonl")}
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def scenario(self,task="delta-quality-clean-w1"):return copy.deepcopy(self.scenarios[task])
    def test_all_tasks_alternative_orders_and_errors(self):
        for scenario in self.scenarios.values():
            with self.subTest(task=scenario["task_id"]):
                self.assertEqual(e.verify_record(scenario,t.run_reference(scenario,reverse=True))["reward"],1)
                for control in t.control_names(scenario):self.assertEqual(e.verify_record(scenario,t.run_reference(scenario,control))["reward"],0,control)
    def test_public_consistency_does_not_establish_correct_result(self):
        run=t.run_reference(self.scenario(),"wrong_result")
        self.assertTrue(run["final_state"]["validations"][-1]["passed"])
        self.assertFalse(run["grade"]["checks"]["correct_content"])
    def test_source_refresh_changes_result_and_requires_new_evidence(self):
        old=t.run_reference(self.scenario());new=t.run_reference(self.scenario("delta-quality-source_refresh-w1"))
        self.assertNotEqual(old["final_state"]["documents"]["report.md"]["body"]["content"]["decision"],new["final_state"]["documents"]["report.md"]["body"]["content"]["decision"])
        self.assertIn(409,[x["observation"]["status"] for x in new["events"]])
        stale=t.run_reference(self.scenario("delta-quality-source_refresh-w1"),"stale_source")
        self.assertFalse(stale["grade"]["checks"]["write_time_evidence"])
    def test_uncertain_results_are_resolved_without_duplicate_effects(self):
        for task,applied in [("mosaic-coverage-uncertain_applied-w1",True),("rivet-routing-uncertain_not_applied-w1",False)]:
            run=t.run_reference(self.scenario(task));state=run["final_state"]
            self.assertEqual(state["uncertain"][0]["applied"],applied);self.assertEqual(len(state["operations"]),2)
            checks=[x["observation"]["state"] for x in run["events"] if x["action"]["tool"]=="operation_status"]
            self.assertEqual(checks,["committed" if applied else "absent"])
    def test_idempotent_key_and_conflicting_payload(self):
        env=e.ResearchEnv(self.scenario())
        while True:
            action=t.reference_action(env.initial,env.events);obs=env.step(action)[0]
            if action["tool"]=="revise_artifact":break
        before=env.artifact_state();repeat=env.step(action)[0]
        self.assertTrue(repeat["replayed"]);self.assertEqual(env.artifact_state(),before)
        changed=copy.deepcopy(action);changed["args"]["content"]["scope"]="changed"
        self.assertEqual(env.step(changed)[0]["error"],"operation_key_payload_conflict")
    def test_prefix_preserves_unknown_inflight_admission(self):
        import workspace_prefix as wp
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);cfg=b.read(ROOT/"configs/runtime-v0.11/collection.json");cfg.update(task_ids=["delta-quality-clean-w1"],max_new_calls=48,monthly_model_calls=48);b.put(root/"config.json",cfg)
            def crash(*args):raise RuntimeError("unknown_fixture_call")
            with self.assertRaisesRegex(RuntimeError,"unknown_fixture_call"):c.execute(self.batch,root/"config.json",root/"out",root/"ledger",provider=crash)
            c.execute(self.batch,root/"config.json",root/"out",root/"ledger",provider=crash)
            result=wp.build(self.batch,root/"out",root/"prefix",1)
            self.assertEqual((result["model_calls"],result["admissions"]),(0,1));self.assertEqual(result["positive_demonstrations"],0)
            self.assertEqual(result["failures"]["categories"],{"unknown_inflight_call":1})
    def test_verified_blocked_is_counted_separately_from_ready_delivery(self):
        import workspace_exports as wx
        result=wx.summary([{"reward":1,"terminal_status":"ready","positive_demonstration_eligible":False},{"reward":1,"terminal_status":"blocked","positive_demonstration_eligible":False},{"reward":0,"terminal_status":"open","positive_demonstration_eligible":False}],[],[])
        self.assertEqual((result["verified_ready_episodes"],result["verified_blocked_episodes"]),(1,1))
    def test_absent_operation_alone_does_not_confirm_recovery(self):
        import failure_exports as fx
        scenario=self.scenario("rivet-routing-uncertain_not_applied-w1");run=t.run_reference(scenario)
        cut=next(i for i,x in enumerate(run["events"]) if x["action"]["tool"]=="operation_status")
        partial=copy.deepcopy(run);partial["events"]=partial["events"][:cut+1];partial["stop_reason"]="batch_time_budget_exhausted"
        index={"task_id":scenario["task_id"],"family_id":scenario["family_id"],"split":"test","reward":0,"complete":False}
        failures,pairs=fx.project("fixture",index,partial,run["initial_observation"],scenario["rights"])
        self.assertIsNone(failures[0]["resolution"]);self.assertFalse(pairs)
        index.update(reward=1,complete=True);failures,pairs=fx.project("fixture",index,run,run["initial_observation"],scenario["rights"])
        self.assertEqual(failures[0]["resolution"]["kind"],"write_effect_verified")
    def test_unknown_future_values_and_private_context_are_absent(self):
        env=e.ResearchEnv(self.scenario("delta-quality-source_refresh-w1"));cfg=b.read(ROOT/"configs/runtime-v0.11/collection.json")
        request=c.request_for(env,cfg,20,100)
        self.assertFalse({"scenario","source_updates","final_state","grade"}&set(request))
        self.assertNotIn("source_updates",json.dumps(request));self.assertEqual(env.documents["exclusions"]["body"]["rows"][0]["value"],17)
        unavailable=e.ResearchEnv(self.scenario("archive-support-withheld_evidence-w1"));obs=unavailable.step({"tool":"read","args":{"document_id":"archived-report"}})[0]
        self.assertEqual(obs["status"],404);self.assertNotIn("body",obs)
    def test_inherited_rights_and_cross_split_duplicates(self):
        archived=self.scenario("archive-support-clean-w1");self.assertFalse(archived["rights"]["training_eligible"])
        row={"split":"development","reward":1};self.assertFalse(c.training_eligible(row,archived))
        a={"family_id":"a","source_group_id":"a","split":"train","text":"unchanged material 12","normalized_sha256":"same"};z={**a,"family_id":"z","source_group_id":"z","split":"test"}
        with self.assertRaisesRegex(ValueError,"near_duplicate_cross_split"):wb.audit_materials([a,z],[])
    def test_archived_source_binding_is_not_replaced_by_a_hash_label(self):
        source=b.read(self.batch/"config.json")["sources"][0];files={p.relative_to(self.batch/"source").as_posix():p.read_bytes() for p in (self.batch/"source").rglob("*") if p.is_file()}
        material=wb.archived_material(source,files);path=material["source_binding"]["claim_file"]
        files[path]=files[path].replace(b"Not 96 percent labor or cost reduction",b"labor reduction")
        with self.assertRaisesRegex(ValueError,"source_qualification_missing"):wb.archived_material(source,files)
    def test_pause_resume_and_train_selection_and_deliverables(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);cfg=b.read(ROOT/"configs/runtime-v0.11/collection.json")
            cfg.update(task_ids=["summit-capacity-source_refresh-w1","mosaic-coverage-uncertain_applied-w1"],max_new_calls=96,monthly_model_calls=96);b.put(root/"config.json",cfg);requests=[]
            def fake(argv,**kwargs):
                request=json.loads(kwargs["input"]);requests.append(request);action=t.reference_action(request["initial_observation"],request["history"])
                payload={"tool":action["tool"],"arguments_json":json.dumps(action["args"]),"decision_summary":"Observed state determines the next action."}
                events=[{"type":"thread.started","thread_id":"fixture-"+str(len(requests))},{"type":"item.completed","item":{"type":"agent_message","text":json.dumps(payload)}},{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}]
                return SimpleNamespace(stdout="\n".join(json.dumps(x) for x in events)+"\n",stderr="",returncode=0)
            with patch.object(c.subprocess,"run",side_effect=fake),patch.object(c.shutil,"which",return_value="fixture"):
                pilot=c.execute(self.batch,root/"config.json",root/"out",root/"ledger",pause_after=1);self.assertEqual(pilot["paused_after_episodes"],1)
                import workspace_prefix as wp
                staged=wp.build(self.batch,root/"out",root/"prefix",1);self.assertFalse(staged["collection_complete"]);self.assertEqual(staged["pending_task_ids"],["mosaic-coverage-uncertain_applied-w1"]);self.assertEqual(staged["positive_demonstrations"],0)
                first=len(requests);captured={p:b.sha(p.read_bytes()) for p in (root/"out").glob("episodes/*/calls/*/capture.json")}
                result=c.execute(self.batch,root/"config.json",root/"out",root/"ledger");self.assertEqual(result["first_attempt_successes"],2);self.assertEqual(result["model_train_trajectories"],1)
                for p,h in captured.items():self.assertEqual(b.sha(p.read_bytes()),h)
                self.assertEqual(wp.verify(self.batch,root/"out",root/"prefix"),staged)
                self.assertGreater(len(requests),first);self.assertEqual(len(requests),result["calls"])
                c.execute(self.batch,root/"config.json",root/"out",root/"ledger");self.assertEqual(len(requests),result["calls"])
                import workspace_exports as wx,failure_exports as fx
                exported=wx.build(self.batch,root/"out",root/"exports")
                self.assertEqual(exported["positive_train_families"],["mosaic-coverage"])
                transitions=b.lines(root/"exports/training/rl-transitions.jsonl")
                self.assertTrue(all(x["split"]=="train" for x in transitions));self.assertFalse(any("final_state" in x for x in transitions))
                run=b.read(root/"out/episodes/mosaic-coverage-uncertain_applied-w1/episode.json");index=b.read(root/"out/episodes/mosaic-coverage-uncertain_applied-w1/index.json")
                failures,pairs=fx.project("fixture",index,run,run["initial_observation"],self.scenario(index["task_id"])["rights"])
                self.assertEqual(failures[0]["resolution"]["kind"],"write_effect_verified");self.assertTrue(pairs[0]["training_eligible"])
                file=root/"out/episodes/mosaic-coverage-uncertain_applied-w1/deliverables/report.md";self.assertIn("coverage_percent",file.read_text())
                file.write_text("forged");manifest=b.read(root/"out/manifest.json");manifest["files"]=b.hashes(root/"out");(root/"out/manifest.json").write_bytes(b.encoded(manifest))
                with self.assertRaisesRegex(ValueError,"delivered_artifact_changed"):c.verify(self.batch,root/"out")

if __name__=="__main__":unittest.main()
