import copy,importlib.util,json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("recovery",ROOT/"scripts/runtime_recovery.py")
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
class RuntimeRecoveryTests(unittest.TestCase):
    def env(self,fault="clean"):
        material=r.c.synthetic_material("capacity")
        source={"source_id":"synthetic-capacity","family_id":"family-synthetic-capacity","split":"train",
                "rights":r.c.TRAIN_RIGHTS,"origin":material["origin"],"sources":material["sources"],"claims":material["claims"]}
        env=r.b.BusinessEnv(r.c.scenario_for(source,fault));initial,_=env.reset()
        return env,initial
    def test_visible_budget_counts_previous_steps(self):
        env,initial=self.env()
        for i in range(12):env.step({"tool":"read_ticket","args":{}})
        request=r.request_for(initial,env.events,12,54,1200,{"max_call_seconds":90})
        budget=request["runtime_budget"]
        self.assertEqual((budget["environment_total_steps"],budget["environment_steps_used"],budget["environment_steps_remaining"]),(30,12,18))
        self.assertEqual(budget["continuation_decisions_used"],0)
        env.step({"tool":"search","args":{"query":""}})
        next_request=r.request_for(initial,env.events,12,53,1190,{"max_call_seconds":90})
        self.assertEqual(next_request["runtime_budget"]["environment_steps_remaining"],17)
        self.assertEqual(next_request["runtime_budget"]["continuation_decisions_used"],1)
    def test_restore_replays_failures_without_resetting_counts(self):
        env,_=self.env("tool_retry")
        env.step({"tool":"read","args":{"document_id":"sources"}})
        env.step({"tool":"read","args":{"document_id":"sources"}})
        prefix=r.b.record(env,"isolated_model_cli")
        resumed,_=r.restore(env.scenario,prefix)
        self.assertEqual(resumed.read_counts["sources"],2)
        self.assertEqual(resumed.events,prefix["events"])
        observation,*_=resumed.step({"tool":"read","args":{"document_id":"sources"}})
        self.assertEqual(observation["status"],200)
        self.assertEqual(resumed.events[:2],prefix["events"])
    def test_changed_checkpoint_is_rejected(self):
        env,_=self.env();env.step({"tool":"read_ticket","args":{}})
        prefix=r.b.record(env,"isolated_model_cli");prefix["final_state"]["ticket"]["version"]=99
        with self.assertRaisesRegex(ValueError,"run_result_mismatch"):r.restore(env.scenario,prefix)
    def test_search_help_matches_real_matching(self):
        env,_=self.env()
        observation,*_=env.step({"tool":"search","args":{"query":"主张 来源"}})
        self.assertEqual(observation["results"],[])
        observation,*_=env.step({"tool":"search","args":{"query":""}})
        self.assertTrue(any(x["document_id"]=="claims" for x in observation["results"]))
        self.assertFalse(any(x["document_id"]=="future" for x in observation["results"]))
    def test_document_ids_work_and_receipt_ids_still_fail(self):
        env,_=self.env()
        obs,*_=env.step({"tool":"read","args":{"document_id":"policy"}})
        failed,*_=env.step({"tool":"write_note","args":{"text":"Observed policy","evidence_ids":[obs["receipt_id"]]}})
        self.assertEqual(failed["status"],422)
        passed,*_=env.step({"tool":"write_note","args":{"text":"Observed policy","evidence_ids":["policy"]}})
        self.assertEqual(passed["status"],200)
    def test_request_keeps_projection_and_actual_failure(self):
        env,initial=self.env("tool_retry")
        env.step({"tool":"read","args":{"document_id":"sources"}})
        request=r.request_for(initial,env.events,1,54,1200,{"max_call_seconds":90})
        self.assertEqual(request["history"][0]["observation"]["status"],429)
        self.assertNotIn("body",request["history"][0]["observation"])
        self.assertNotIn("final_state",request)
        self.assertNotIn("checks",request)
    def test_budget_cannot_claim_more_steps_than_environment(self):
        env,initial=self.env()
        for i in range(30):env.step({"tool":"read_ticket","args":{}})
        with self.assertRaisesRegex(ValueError,"invalid_remaining"):r.request_for(initial,env.events,12,54,1200,{"max_call_seconds":90})
    def test_exhausted_collection_budget_cannot_call_model(self):
        env,initial=self.env()
        for calls,seconds in ((0,1200),(54,0)):
            with self.assertRaisesRegex(ValueError,"no_collection_budget"):
                r.request_for(initial,env.events,0,calls,seconds,{"max_call_seconds":90})
    def test_reference_continuation_preserves_censored_prefix(self):
        env,_=self.env("tool_retry")
        for i in range(2):env.step({"tool":"read","args":{"document_id":"sources"}})
        for i in range(10):env.step({"tool":"read_ticket","args":{}})
        prefix=copy.deepcopy(env.events)
        r.reference_continuation(env)
        self.assertEqual(env.events[:12],prefix)
        self.assertEqual(r.b.verify_record(env.scenario,r.b.record(env,"scripted_preflight"))["reward"],1)
    def test_repair_request_alone_cannot_bypass_new_batch_approval(self):
        config={"execution_authorization":"pending_new_batch_approval","authorization_record":{"sha256":"request-only"}}
        with self.assertRaisesRegex(ValueError,"new_recovery_batch_approval_required"):
            r.require_recovery_approval(config,Path("unused"))
if __name__=="__main__":unittest.main()
