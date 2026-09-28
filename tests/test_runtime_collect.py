import copy,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"scripts"))
import runtime_batch as b
import runtime_collect as c

class RuntimeCollectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.base=Path(cls.temp.name)
        cls.batch=cls.base/"batch";b.build(ROOT/"configs/runtime-v0.8/batch.json",cls.batch)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setup_case(self,root):
        cfg=b.read(ROOT/"configs/runtime-v0.8/collection.json")
        cfg["task_ids"]=["canal-staffing-tool_retry-v3"];cfg["max_new_calls"]=24;cfg["monthly_model_calls"]=80
        b.put(root/"config.json",cfg);(root/"ledger").mkdir()
        return cfg
    def fake_model(self,requests):
        def run(argv,**kwargs):
            request=json.loads(kwargs["input"]);requests.append(request)
            action=b.reference_action(request["initial_observation"],request["history"])
            value={"tool":action["tool"],"arguments_json":json.dumps(action["args"]),"decision_summary":"Fixture policy from public observations."}
            events=[{"type":"thread.started","thread_id":"fixture-"+str(len(requests))},
                    {"type":"item.completed","item":{"type":"agent_message","text":json.dumps(value)}},
                    {"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}]
            return SimpleNamespace(stdout="\n".join(json.dumps(x) for x in events)+"\n",stderr="",returncode=0)
        return run
    def test_capture_is_replayed_after_crash_without_another_provider_call(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.setup_case(root);requests=[];crashed=[False]
            def crash(folder):
                if len(requests)==2 and not crashed[0]:crashed[0]=True;raise RuntimeError("fixture_crash_after_capture")
            with patch.object(c.subprocess,"run",side_effect=self.fake_model(requests)),patch.object(c.shutil,"which",return_value="fixture"):
                with self.assertRaisesRegex(RuntimeError,"fixture_crash"):
                    c.execute(self.batch,root/"config.json",root/"out",root/"ledger",after_capture=crash)
                before={p:b.sha(p.read_bytes()) for p in (root/"out").glob("episodes/*/calls/*/capture.json")}
                result=c.execute(self.batch,root/"config.json",root/"out",root/"ledger")
                self.assertEqual(result["first_attempt_successes"],1)
                self.assertEqual(result["calls"],9);self.assertEqual(len(requests),9)
                self.assertEqual(len(c.ledger_entries(root/"ledger")),9)
                for p,sha in before.items():self.assertEqual(b.sha(p.read_bytes()),sha)
                c.execute(self.batch,root/"config.json",root/"out",root/"ledger")
                self.assertEqual(len(requests),9)
    def test_unknown_inflight_call_is_quarantined_without_reissue(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.setup_case(root);calls=[]
            def crash(*args):calls.append(True);raise RuntimeError("fixture_before_capture")
            with self.assertRaisesRegex(RuntimeError,"fixture_before_capture"):
                c.execute(self.batch,root/"config.json",root/"out",root/"ledger",provider=crash)
            result=c.execute(self.batch,root/"config.json",root/"out",root/"ledger",provider=crash)
            self.assertEqual(len(calls),1);self.assertEqual(result["first_attempt_successes"],0)
            row=b.lines(root/"out/episodes.jsonl")[0];self.assertEqual(row["stop_reason"],"unknown_inflight_call_quarantined")
            self.assertEqual(len(c.ledger_entries(root/"ledger")),1)
    def test_budget_is_public_and_hidden_grading_never_enters_request(self):
        task=b.lines(self.batch/"tasks.jsonl")[0];env=c.e.ResearchEnv(b.read(self.batch/task["scenario"]))
        env.step({"tool":"read","args":{"document_id":"claims"}})
        request=c.request_for(env,{"max_call_seconds":90},5,80)
        self.assertEqual(request["runtime_budget"]["environment_steps_remaining"],23)
        self.assertEqual(request["history"][0]["observation"]["body"]["rows"][0]["value"],37)
        self.assertFalse({"final_state","scenario","expected","checks","grade"}&set(request))
        with self.assertRaisesRegex(ValueError,"no_collection_budget"):c.request_for(env,{"max_call_seconds":90},0,80)
    def test_unicode_transport_and_incomplete_return(self):
        value={"tool":"read_ticket","arguments_json":"{}","decision_summary":"before\u2028after"}
        events=[{"type":"thread.started","thread_id":"fixture"},{"type":"item.completed","item":{"type":"agent_message","text":json.dumps(value,ensure_ascii=False)}},{"type":"turn.completed"}]
        parsed,_=c.parse_visible("\n".join(json.dumps(x,ensure_ascii=False) for x in events))
        self.assertEqual(c.parse_action(parsed)[1],"before\u2028after")
        with self.assertRaisesRegex(ValueError,"incomplete_model_turn"):c.parse_action(parsed[:-1])

if __name__=="__main__":unittest.main()
