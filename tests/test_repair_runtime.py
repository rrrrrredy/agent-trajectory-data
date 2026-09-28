import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"scripts"))
import runtime_batch as b,runtime_collect as c,repair_batch as batch,repair_env as env,repair_executor as runner
class RepairRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name);cls.batch=cls.root/"batch";b.build(ROOT/"configs/runtime-v0.10/batch.json",cls.batch)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def scenario(self,task="jsonl-unicode",variant="clean"):return b.read(self.batch/"tasks"/("repair-"+task+"-"+variant+"-v1")/"scenario.json")
    def test_all_controls_and_references(self):
        result=b.verify(self.batch);self.assertEqual((result["tasks"],result["controls"],result["source_groups"]),(9,54,1))
    def test_save_reload_preserves_layout_and_actions(self):
        scenario=self.scenario(variant="layout");saved=json.loads(json.dumps(scenario,sort_keys=True));self.assertEqual(batch.run_reference(scenario),batch.run_reference(saved))
    def test_partial_hash_fix_passes_public_but_fails_private(self):
        scenario=self.scenario("manifest-hashes");run=batch.run_reference(scenario,"partial_fix")
        self.assertTrue(run["final_state"]["tests"][-1]["passed"]);self.assertFalse(run["grade"]["checks"]["private_behavior"]);self.assertEqual(run["grade"]["reward"],0)
    def test_missing_diagnosis_or_verification_rejected(self):
        for mutation in ("no_baseline","no_retest","edit_after_test","wrong_binding"):
            with self.subTest(mutation=mutation):self.assertEqual(batch.run_reference(self.scenario(),mutation)["grade"]["reward"],0)
    def test_concurrent_edit_requires_read_and_preserves_note(self):
        scenario=self.scenario(variant="stale_patch");run=batch.run_reference(scenario);events=run["events"];i=next(i for i,x in enumerate(events) if x["observation"]["status"]==409)
        self.assertEqual(events[i+1]["action"]["tool"],"read");self.assertIn("Concurrent edit",run["final_state"]["code"]);self.assertEqual(env.verify_record(scenario,run)["reward"],1)
    def test_stale_read_cannot_patch(self):
        runtime=env.ResearchEnv(self.scenario());obs,*_=runtime.step({"tool":"patch","args":{"if_version":1,"old":"splitlines()","new":"split('\\n')"}});self.assertEqual(obs["status"],412)
    def test_unknown_action_is_not_submit(self):
        runtime=env.ResearchEnv(self.scenario());obs,*_=runtime.step({"tool":"execute_shell","args":{}});self.assertEqual(obs["status"],400);self.assertFalse(runtime.finished)
    def test_reward_tampering_rejected(self):
        scenario=self.scenario();run=batch.run_reference(scenario);run["events"][0]["reward"]=1
        with self.assertRaisesRegex(ValueError,"event_replay_changed"):env.verify_record(scenario,run)
    def test_source_rights_and_missingness_are_preserved(self):
        scenario=self.scenario();self.assertFalse(scenario["rights"]["training_eligible"]);self.assertEqual(scenario["split"],"development");self.assertIn("minimal_reproduction_not_original_program",scenario["missingness"])
    def test_executor_rejects_non_subset_programs(self):
        for code in ["import os\ndef solve(data): return []", "def solve(data): return open('secret')", "def solve(data): return data.__class__", "def solve(data): return solve(data)", "def solve(data):\n while True: pass", "def solve(data): return 'x'*99999"]:
            with self.subTest(code=code),self.assertRaises((ValueError,SyntaxError)):runner.validate(code)
    def test_mutating_loop_hits_instruction_limit(self):
        result=runner.execute("def solve(data):\n rows=[0]\n for x in rows: rows.append(x)\n return rows",{})
        self.assertEqual(result,{"ok":False,"error":"ExecutionLimit"})
    def test_executor_does_not_mutate_input(self):
        data={"items":[1]};runner.execute("def solve(data):\n data['items'].append(2)\n return data",data);self.assertEqual(data,{"items":[1]})
    def test_private_cases_and_reference_never_enter_requests(self):
        scenario=self.scenario();runtime=env.ResearchEnv(scenario);config={"max_call_seconds":90,"environment_profile":"bounded_program_repair"}
        runtime.step({"tool":"read","args":{"document_id":scenario["document_ids"]["sample"]}})
        request=c.request_for(runtime,config,10,100);encoded=json.dumps(request)
        self.assertNotIn("private_cases",encoded);self.assertNotIn("reference_code",encoded);self.assertNotIn("additional-unicode",encoded)
    def test_collector_real_protocol_with_mocked_provider(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);cfg=b.read(ROOT/"configs/runtime-v0.10/collection.json");cfg.update(task_ids=["repair-manifest-hashes-stale_patch-v1"],max_new_calls=30);b.put(root/"config.json",cfg);requests=[]
            def fake(argv,**kw):
                request=json.loads(kw["input"]);requests.append(request);action=batch.reference_action(request["initial_observation"],request["history"])
                answer={"tool":action["tool"],"arguments_json":json.dumps(action["args"]),"decision_summary":"Public-observation fixture."}
                events=[{"type":"thread.started","thread_id":"repair-"+str(len(requests))},{"type":"item.completed","item":{"type":"agent_message","text":json.dumps(answer)}},{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}]
                return SimpleNamespace(stdout="\n".join(json.dumps(x) for x in events),stderr="",returncode=0)
            with patch.object(c.subprocess,"run",side_effect=fake),patch.object(c.shutil,"which",return_value="fixture"):
                result=c.execute(self.batch,root/"config.json",root/"out",root/"ledger")
            self.assertEqual(result["first_attempt_successes"],1);self.assertEqual(result["model_train_trajectories"],0)
            self.assertEqual(b.read(root/"out/training/selection.json")["excluded"][0]["reason"],"source_restricted_development")
            self.assertIn("repair_executor.py",b.read(root/"out/input-freeze.json")["source_sha256"])
if __name__=="__main__":unittest.main()
