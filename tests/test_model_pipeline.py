import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from agentdata.core import generate, read, run_task, reference_policy, quality_decision, split_for
from agentdata.providers import CodexProvider, INSTRUCTION, ProviderError, parse_stream
from agentdata.pipeline import run_pipeline, batch_lock

class ModelPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        seed = next(i for i in range(100) if split_for(f"synthetic-{i}-00000") == "train")
        self.task = read(generate(self.root, 1, seed)[0])
        self.calls = 0
        self.requests = []
        self.which = patch("agentdata.providers.shutil.which", return_value="codex")
        self.which.start()
        self.addCleanup(self.which.stop)

    def fake_cli(self, argv, **kwargs):
        if "--version" in argv:
            return subprocess.CompletedProcess(argv, 0, "codex-cli test-fixture", "")
        self.calls += 1
        payload = json.loads(kwargs["input"][len(INSTRUCTION)+1:])
        self.requests.append(payload)
        action = reference_policy(payload["task"], payload["observations"])
        events = [
            {"type":"thread.started", "thread_id":f"fixture-thread-{self.calls}"},
            {"type":"turn.started"},
            {"type":"item.completed","item":{"type":"agent_message","text":json.dumps(action)}},
            {"type":"turn.completed","usage":{"input_tokens":100,"cached_input_tokens":10,"output_tokens":20}}
        ]
        return subprocess.CompletedProcess(argv, 0, "\n".join(json.dumps(x) for x in events), "")

    def provider(self, sft=False):
        rights = {"basis":"test_fixture_policy","allowed_uses":["diagnostic","sft"] if sft else ["diagnostic"]}
        return CodexProvider({"model":"test-fixture-model","output_rights":rights}, admit=lambda:None)

    def test_observed_capture_does_not_invent_reported_model(self):
        with patch("agentdata.providers.subprocess.run",side_effect=self.fake_cli):
            result = run_task(self.root,self.task,"codex",provider=self.provider())
        self.assertEqual("model_cli",result["actor_kind"])
        self.assertEqual(2,result["model_calls_observed"])
        self.assertEqual(200,result["token_usage"]["input_tokens"])
        self.assertEqual("accept",quality_decision(self.root,result)["decision"])
        capture = read(next((self.root/"runs"/result["run_id"]/"model_calls").glob("*/capture.json")))
        self.assertIsNone(capture["model_reported"])
        self.assertTrue(capture["thread_id"].startswith("fixture-thread-"))
        for request in self.requests:
            self.assertNotIn("oracle",request["task"])
            self.assertNotIn("environment",request["task"])

    def test_default_output_rights_block_training(self):
        with patch("agentdata.providers.subprocess.run",side_effect=self.fake_cli):
            result=run_task(self.root,self.task,"codex",provider=self.provider())
        self.assertIn("model_output_rights_not_established",
                      quality_decision(self.root,result,"sft")["reasons"])

    def test_training_requires_configured_rights_and_consistent_capture(self):
        with patch("agentdata.providers.subprocess.run",side_effect=self.fake_cli):
            result=run_task(self.root,self.task,"codex",provider=self.provider(sft=True))
        self.assertEqual("accept",quality_decision(self.root,result,"sft")["decision"])
        path=next((self.root/"runs"/result["run_id"]/"model_calls").glob("*/request.json"))
        request=read(path)
        request["observations"]=[{"invented":True}]
        path.write_text(json.dumps(request))
        self.assertIn("invalid_model_capture",quality_decision(self.root,result,"sft")["reasons"])

    def test_usage_and_model_action_are_bound(self):
        with patch("agentdata.providers.subprocess.run",side_effect=self.fake_cli):
            result=run_task(self.root,self.task,"codex",provider=self.provider())
        result["token_usage"]["input_tokens"]=0
        self.assertIn("model_usage_mismatch",quality_decision(self.root,result)["reasons"])

    def test_hidden_reasoning_is_not_retained(self):
        events,omitted=parse_stream(json.dumps({"type":"item.completed",
            "item":{"type":"reasoning","text":"do not retain"}})+"\n"+json.dumps({"type":"turn.started"}))
        self.assertEqual(1,omitted)
        self.assertNotIn("do not retain",json.dumps(events))

    def test_cli_failure_retains_known_usage_and_original_events(self):
        def faulty(argv,**kwargs):
            result=self.fake_cli(argv,**kwargs)
            if "--version" not in argv:
                result.stdout += "\n"+json.dumps({"type":"error","message":"fixture_error"})
            return result
        with patch("agentdata.providers.subprocess.run",side_effect=faulty):
            result=run_task(self.root,self.task,"codex",provider=self.provider())
        self.assertEqual("model_protocol_error",result["terminal_reason"])
        self.assertEqual(100,result["token_usage"]["input_tokens"])
        self.assertEqual("accept",quality_decision(self.root,result)["decision"])

    def test_no_budget_callback_means_no_model_request(self):
        provider=CodexProvider({"model":"test-fixture-model"})
        with patch("agentdata.providers.subprocess.run") as call:
            with self.assertRaises(ValueError):
                provider.invoke(self.task["public"],[],self.root/"call",1)
        call.assert_not_called()

    def test_pipeline_resume_never_reexecutes_completed_jobs(self):
        config={"policy":"codex","provider":{"model":"test-fixture-model"}}
        with patch("agentdata.providers.subprocess.run",side_effect=self.fake_cli):
            first=run_pipeline(self.root,config,"resume-test")
            count=self.calls
            second=run_pipeline(self.root,config,"resume-test")
        self.assertEqual(7,count)
        self.assertEqual(count,self.calls)
        self.assertEqual(first,second)
        self.assertEqual(3,first["exports"]["diagnostic"]["accepted"])
        exported=read(self.root/"batches/resume-test/diagnostic.json")
        self.assertTrue(exported["records"][0]["model_calls"][0]["request"])
        self.assertEqual(0,first["exports"]["sft"]["accepted"])

    def test_persistent_budget_stops_without_repeated_requests(self):
        config={"policy":"codex","max_model_calls":1,"provider":{"model":"test-fixture-model"}}
        with patch("agentdata.providers.subprocess.run",side_effect=self.fake_cli):
            result=run_pipeline(self.root,config,"budget-test")
            resumed=run_pipeline(self.root,config,"budget-test")
        self.assertEqual(1,self.calls)
        self.assertEqual(1,result["calls_reserved"])
        self.assertEqual("call_budget_exhausted",result["status"])
        self.assertEqual(2,result["job_statuses"]["pending"])
        self.assertEqual(result,resumed)

    def test_crashed_worker_does_not_reissue_unknown_call(self):
        config={"policy":"codex","provider":{"model":"test-fixture-model"}}
        with patch("agentdata.providers.subprocess.run",side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                run_pipeline(self.root,config,"crash-test")
        state=read(self.root/"batches/crash-test/state.json")
        self.assertEqual(1,state["calls_reserved"])
        with patch("agentdata.providers.subprocess.run",side_effect=self.fake_cli):
            result=run_pipeline(self.root,config,"crash-test")
        self.assertEqual(1,result["job_statuses"]["interrupted"])
        self.assertEqual(5,self.calls)
        self.assertEqual(6,result["calls_reserved"])

    def test_batch_configuration_cannot_change_on_resume(self):
        run_pipeline(self.root,{"policy":"reference"},"immutable-config")
        with self.assertRaises(ValueError):
            run_pipeline(self.root,{"policy":"reference","max_model_calls":9},"immutable-config")

    def test_exclusive_lock_releases_after_error(self):
        path=self.root/"worker.lock"
        with batch_lock(path):
            with self.assertRaises(RuntimeError):
                with batch_lock(path):
                    pass
        with batch_lock(path):
            pass

    def test_budget_typo_is_rejected_before_calling_model(self):
        with patch("agentdata.providers.subprocess.run") as call:
            with self.assertRaises(ValueError):
                run_pipeline(self.root,{"max_model_call":1},"typo")
        call.assert_not_called()

    def test_credentials_are_not_accepted_in_provider_config(self):
        with self.assertRaises(ValueError):
            CodexProvider({"model":"test-fixture-model","api_key":"fixture-not-a-real-key"})

    def test_invalid_batch_ids_cannot_escape_root(self):
        with self.assertRaises(ValueError):
            run_pipeline(self.root,{}, "../outside")

if __name__=="__main__":
    unittest.main()
