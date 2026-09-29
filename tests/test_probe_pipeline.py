import copy,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"scripts"))
import runtime_batch as b,runtime_collect as c,repair_probe_env as env,repair_probe_tasks as tasks,failure_exports as failures

class ProbePipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(dir=ROOT.parent/"_tmp");cls.batch=Path(cls.temp.name)/"batch"
        cls.summary=b.build(ROOT/"configs/runtime-v0.14/batch.json",cls.batch)
        row=b.lines(cls.batch/"tasks.jsonl")[0];cls.scenario=b.read(cls.batch/row["scenario"]);cls.reference_run=b.read(cls.batch/row["reference"])
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_one_frozen_authored_family_and_all_controls(self):
        self.assertEqual((self.summary["tasks"],self.summary["controls"],self.summary["scripted_train_trajectories"]),(1,14,1))
        self.assertEqual(b.verify_episode(self.scenario,self.reference_run)["reward"],1)
        self.assertEqual(len(b.lines(self.batch/"controls.jsonl")),14)
    def test_model_schema_and_public_request_do_not_leak_evaluator_material(self):
        config=b.read(ROOT/"configs/runtime-v0.14/collection.json");c.config_validate(config,{self.scenario["task_id"]:self.scenario})
        self.assertIn("probe",c.schema_for(config)["properties"]["tool"]["enum"])
        self.assertNotIn("probe",c.schema_for(b.read(ROOT/"configs/runtime-v0.12/collection.json"))["properties"]["tool"]["enum"])
        runtime=env.ResearchEnv(self.scenario)
        for name in runtime.initial["documents"]:runtime.step({"tool":"read","args":{"document_id":name}})
        request=c.request_for(runtime,config,40,100)
        def keys(value):
            if isinstance(value,dict):return set(value).union(*(keys(v) for v in value.values()))
            if isinstance(value,list):return set().union(*(keys(v) for v in value))
            return set()
        self.assertFalse(keys(request)&{"oracle_id","reference_probe","reference_code","private_cases","control_codes"})
    def test_only_oracle_validated_recovery_is_training_eligible(self):
        index={"task_id":self.scenario["task_id"],"family_id":self.scenario["family_id"],"split":"train","reward":1,"complete":True}
        fs,pairs=failures.project("fixture",index,self.reference_run,self.reference_run["initial_observation"],self.scenario["rights"])
        self.assertEqual(len(pairs),1);self.assertEqual(fs[0]["category"],"probe_claim_mismatch")
        self.assertTrue(pairs[0]["training_eligible"]);self.assertEqual(pairs[0]["verification"]["kind"],"contract_regression_verified")
        changed=copy.deepcopy(self.reference_run);changed["grade"]["validated_regression_pairs"]=[]
        _,pairs=failures.project("fixture",index,changed,changed["initial_observation"],self.scenario["rights"])
        self.assertFalse(pairs[0]["training_eligible"]);self.assertFalse(pairs[0]["verification"]["oracle_validated"])
    def test_different_case_cannot_be_mistaken_for_recovery(self):
        run=tasks.run_reference(self.scenario,"different_retest")
        index={"task_id":self.scenario["task_id"],"family_id":self.scenario["family_id"],"split":"train","reward":0,"complete":True}
        fs,pairs=failures.project("fixture",index,run,run["initial_observation"],self.scenario["rights"])
        self.assertTrue(any(x["category"]=="probe_claim_mismatch" for x in fs));self.assertFalse(pairs)
if __name__=="__main__":unittest.main()
