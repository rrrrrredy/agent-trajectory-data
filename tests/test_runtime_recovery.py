import copy,importlib.util,json,tempfile,time,unittest
from unittest.mock import patch
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
    def test_crash_resume_preserves_calls_and_writes_all_episode_indices(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);parent=root/"parent";out=root/"out";ledger=root/"ledger.json"
            r.rd.put_json(ledger,{"fixture":True})
            config={"max_new_calls":54,"max_call_seconds":90,"max_batch_seconds":1200,
                    "monthly_model_calls":98,"model":"gpt-6-astra","evaluation_mode":"repair_validation_previously_observed_tasks"}
            tasks={};indices=[]
            for n in range(3):
                env,_=self.env()
                for _ in range(12):env.step({"tool":"read_ticket","args":{}})
                tid="fixture-"+str(n);path=tid+".json"
                r.rd.put_json(parent/"curriculum"/path,env.scenario)
                r.rd.put_json(parent/"rollouts"/path,r.b.record(env,"isolated_model_cli"))
                tasks[tid]={"environment":path,"family_id":tid,"split":"train"}
                indices.append({"task_id":tid,"path":path})
            prepared=(parent,out,root,config,tasks,indices,ledger)
            reservations=[];invocations=[]
            def reserve(*args):reservations.append(args[-1])
            def invoke(request,folder,config,timeout):
                invocations.append(folder.as_posix());action={"tool":"read_ticket","args":{}}
                response={"tool":"read_ticket","arguments_json":"{}","decision_summary":"Test fixture"}
                thread="fixture-thread-"+str(len(invocations));usage={"input_tokens":1,"output_tokens":1}
                events=[{"type":"thread.started","thread_id":thread},
                        {"type":"item.completed","item":{"type":"agent_message","text":json.dumps(response)}},
                        {"type":"turn.completed","usage":usage}]
                r.rd.put_json(folder/"request.json",request);r.rd.put_lines(folder/"visible-events.jsonl",events)
                cap={"action":action,"status":"completed","error":None,"decision_summary":"Test fixture","thread_id":thread,"usage":usage,
                     "request_sha256":r.rd.sha((folder/"request.json").read_bytes()),
                     "visible_events_sha256":r.rd.sha((folder/"visible-events.jsonl").read_bytes())}
                r.rd.put_json(folder/"capture.json",cap);return cap
            original_put=r.rd.put_json
            def crash(path,value):
                if Path(path).name=="002.json" and Path(path).parent.name=="checkpoints":raise OSError("simulated save failure")
                original_put(path,value)
            with patch.object(r,"prepare",return_value=prepared),patch.object(r.v,"invoke",side_effect=invoke),patch("agentdata.pipeline.reserve_monthly",side_effect=reserve),patch.object(r.rd,"put_json",side_effect=crash):
                with self.assertRaisesRegex(OSError,"simulated save failure"):r.execute(parent,"config","evidence",out,root)
            self.assertEqual(len(invocations),2)
            first=out/"episodes/fixture-0/checkpoints/001.json";before=first.read_bytes()
            with patch.object(r,"prepare_resume",return_value=(prepared,time.time()+1200)),patch.object(r.v,"invoke",side_effect=invoke),patch("agentdata.pipeline.reserve_monthly",side_effect=reserve),patch.object(r,"verify_recoveries",return_value={"fixture":True}):
                r.execute(parent,"config","evidence",out,root,resume=True)
            self.assertEqual(len(invocations),54)
            self.assertEqual(len(reservations),54)
            self.assertEqual(len(set(invocations)),54)
            self.assertEqual(first.read_bytes(),before)
            rows=r.c.lines(out/"episodes.jsonl")
            self.assertEqual(len(rows),3)
            self.assertTrue(all(row["total_steps"]==30 and row["new_model_calls"]==18 for row in rows))
            for row in rows:
                record=r.c.read(out/row["path"])
                self.assertEqual(len(record["capture_refs"]),18)
                self.assertEqual(record["events"][:12],r.c.read(parent/"rollouts"/(row["task_id"]+".json"))["events"])

if __name__=="__main__":unittest.main()
