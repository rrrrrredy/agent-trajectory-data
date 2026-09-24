"""Behavior and leakage checks for executable environments and process provenance."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
SCRIPTS=Path(__file__).resolve().parents[1]/"scripts"
spec=importlib.util.spec_from_file_location("runtime_module",SCRIPTS/"runtime_dataset.py")
rt=importlib.util.module_from_spec(spec);spec.loader.exec_module(rt)
business=rt.business

def scenario(fault="clean"):
    return business.make_scenario("fixture","fixture-family",[{"source_id":"S01"}],
        [{"claim_id":"C1","source_ids":"S01"}],fault)

class BusinessEnvironmentTests(unittest.TestCase):
    def test_reference_handles_five_business_states(self):
        for fault in ("clean","missing_reference","tool_retry","access_revoked","concurrent_edit"):
            with self.subTest(fault=fault):
                env=business.BusinessEnv(scenario(fault));business.reference_policy(env)
                self.assertEqual(env.outcome["reward"],1)
                self.assertTrue(env.finished)
                if fault=="tool_retry":
                    self.assertEqual([e["observation"]["status"] for e in env.events].count(429),2)
                if fault=="concurrent_edit":
                    self.assertIn(409,[e["observation"]["status"] for e in env.events])
                if fault=="access_revoked":self.assertEqual(env.ticket["status"],"blocked")

    def test_cannot_win_with_answer_without_business_artifacts(self):
        env=business.BusinessEnv(scenario());answer=env.expected()
        answer.update(scope="registry_integrity_only",evidence_ids=["policy","handoff","claims","sources"],ticket_version=1)
        o,r,t,tr,i=env.step({"tool":"submit","args":answer})
        self.assertEqual(r,0);self.assertTrue(t);self.assertFalse(tr)
        self.assertFalse(env.outcome["checks"]["note"])
        self.assertFalse(env.outcome["checks"]["observed_evidence"])

    def test_old_ticket_version_cannot_silently_overwrite(self):
        env=business.BusinessEnv(scenario("concurrent_edit"));business.reference_policy(env,"ignore_conflict")
        self.assertEqual(env.outcome["reward"],0)
        self.assertEqual(env.ticket["status"],"open")

    def test_published_observations_exclude_private_and_future_state(self):
        env=business.BusinessEnv(scenario())
        initial,info=env.reset()
        self.assertNotIn("documents",initial);self.assertNotIn("fault",initial);self.assertNotIn("expected",initial)
        found=env.step({"tool":"search","args":{"query":""}})[0]
        ids={r["document_id"] for r in found["results"]}
        self.assertNotIn("restricted",ids);self.assertNotIn("future",ids)
        for doc,code in (("restricted",403),("future",404),("../../secret",404)):
            result=env.step({"tool":"read","args":{"document_id":doc}})[0]
            self.assertEqual(result["status"],code);self.assertNotIn("body",result)

    def test_invalid_tools_cannot_mutate_documents_or_execute_commands(self):
        env=business.BusinessEnv(scenario())
        before=copy.deepcopy(env.scenario)
        for action in ({"tool":"exec","args":{"command":"anything"}},{"tool":"write_document","args":{"document_id":"sources"}},
                       {"tool":"read","args":{"document_id":[]}},{"tool":[]},None,{"tool":"search","args":{"query":1}}):
            out,reward,_,_,_=env.step(action)
            self.assertEqual(out["status"],400);self.assertEqual(reward,0)
        self.assertEqual(env.scenario,before)

    def test_failed_attempt_budget_ends_episode_without_success(self):
        env=business.BusinessEnv(scenario())
        for _ in range(30):last=env.step({"tool":"missing"})
        self.assertTrue(last[3]);self.assertFalse(last[2]);self.assertEqual(last[1],0)
        with self.assertRaisesRegex(ValueError,"episode_finished"):env.step({"tool":"submit"})

    def test_reset_erases_state_and_repeats_transitions(self):
        env=business.BusinessEnv(scenario("tool_retry"));business.reference_policy(env)
        old=copy.deepcopy(env.events);state=env.snapshot()
        env.reset(seed=7);self.assertEqual(env.notes,[]);self.assertEqual(env.read_counts,{})
        business.reference_policy(env)
        self.assertEqual(old,env.events);self.assertEqual(state,env.snapshot())

    def test_no_intermediate_reward_or_answer_leak_in_feedback(self):
        env=business.BusinessEnv(scenario("missing_reference"));business.reference_policy(env)
        self.assertTrue(all(e["reward"]==0 for e in env.events[:-1]))
        self.assertNotIn("checks",env.events[-1]["observation"])
        self.assertNotIn("dangling_references",env.events[-1]["observation"])

    def test_malformed_submit_is_failure_not_harness_crash(self):
        for evidence in (None,[],[[]],{},1,"sources"):
            env=business.BusinessEnv(scenario())
            result=env.step({"tool":"submit","args":{"evidence_ids":evidence}})
            self.assertEqual(result[1],0);self.assertTrue(result[2])

    def test_serialized_environment_preserves_exact_observations(self):
        original=scenario("concurrent_edit")
        reloaded=json.loads(json.dumps(original,ensure_ascii=False,sort_keys=True))
        first=business.BusinessEnv(original);business.reference_policy(first)
        second=business.BusinessEnv(reloaded)
        for event in first.events:
            second.step(event["action"])
            self.assertEqual(second.events[-1],event)
        self.assertEqual(second.outcome,first.outcome)

class RepairTaskTests(unittest.TestCase):
    def test_controls_are_functionally_distinguishable(self):
        # One complete external execution cycle is also retained in the built dataset.
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for spec in rt.repair.task_specs():
                rt.write_repair(root,spec)
                attempts=rt.repair_controls(root,spec)
                self.assertEqual([a["reward"] for a in attempts],[0,0,1,1])

if __name__=="__main__":unittest.main()
