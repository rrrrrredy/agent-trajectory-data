import copy,importlib.util,json,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("rollout",ROOT/"scripts/model_rollout.py")
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
c,b=r.c,r.b
class RuntimeCurriculumTests(unittest.TestCase):
    def scenario(self,fault="clean"):
        material=c.synthetic_material("capacity")
        source={"source_id":"synthetic-capacity","family_id":"family-synthetic-capacity","split":"train",
                "rights":c.TRAIN_RIGHTS,"origin":material["origin"],"sources":material["sources"],"claims":material["claims"]}
        return c.scenario_for(source,fault)
    def stream(self,tool="read",args=None,reason="Read policy"):
        payload={"tool":tool,"arguments_json":json.dumps(args or {"document_id":"policy"}),"decision_summary":reason}
        return [{"type":"thread.started","thread_id":"test-thread"},
                {"type":"item.completed","item":{"type":"agent_message","text":json.dumps(payload)}},
                {"type":"turn.completed","usage":{"input_tokens":1,"cached_input_tokens":0,"output_tokens":1}}]
    def test_public_request_has_only_observations(self):
        env=b.BusinessEnv(self.scenario());initial,_=env.reset()
        env.step({"tool":"read","args":{"document_id":"sources"}})
        request=r.request_for(initial,env.events)
        self.assertEqual(set(request),{"instruction","initial_observation","history"})
        self.assertEqual(set(request["history"][0]),{"action","observation"})
        self.assertNotIn("documents",request["initial_observation"])
        self.assertNotIn("final_state",json.dumps(request))
        self.assertNotIn("checks",request["history"][0])
    def test_report_projection_retains_unknown_links(self):
        source=b"source_id,title,url\nS1,One,local\n"
        claims=b"claim_id,claim,supporting_sources\nC1,text,S1;MISSING\n"
        s,cs=c.normalize_tables(source,claims)
        self.assertEqual(cs[0]["source_ids"],"S1|MISSING")
        self.assertEqual([x["source_id"] for x in s],["S1"])
    def test_ambiguous_projection_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"ambiguous"):
            c.normalize_tables(b"source_id,title\nS1,one\n",
                               b"claim_id,claim,supporting_sources\nC1,text,S1 (maybe)\n")
    def test_synthetic_controls_cover_all_faults(self):
        for fault in c.FAULTS:
            scenario=self.scenario(fault)
            self.assertEqual(b.verify_record(scenario,c.control(scenario,"reference"))["reward"],1)
            self.assertEqual(b.verify_record(scenario,c.control(scenario,"wrong_answer"))["reward"],0)
    def test_preference_has_identical_observed_prefix(self):
        scenario=self.scenario("concurrent_edit")
        good=c.messages(scenario,c.control(scenario,"reference"))
        bad=c.messages(scenario,c.control(scenario,"wrong_answer"))
        self.assertEqual(good[:-1],bad[:-1])
        self.assertNotEqual(good[-1],bad[-1])
        self.assertEqual(good[-1]["role"],"assistant")
    def test_nested_manifest_is_hashed(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);(p/"nested").mkdir();(p/"nested/manifest.json").write_text("{}")
            (p/"manifest.json").write_text("{}")
            self.assertEqual(set(c.hashes(p)),{"nested/manifest.json"})
    def test_hidden_reasoning_removed_without_unicode_split(self):
        events=self.stream(reason="read\u2028policy")
        raw="\n".join(json.dumps(x,ensure_ascii=False) for x in [
            {"type":"item.completed","item":{"type":"reasoning","text":"private"}},*events])
        visible,count=r.parse_visible(raw)
        self.assertEqual(count,1)
        self.assertEqual(r.parsed_action(visible)[1],"read\u2028policy")
    def test_provider_failure_and_tool_use_rejected(self):
        for event in ({"type":"turn.failed"},
                      {"type":"item.completed","item":{"type":"command_execution","command":"ls"}}):
            with self.assertRaises(ValueError):r.parsed_action([*self.stream(),event])
    def test_model_action_not_inferred_from_usage(self):
        with self.assertRaisesRegex(ValueError,"incomplete"):
            r.parsed_action([{"type":"turn.completed","usage":{"input_tokens":42}}])
    def test_invalid_inner_action_rejected(self):
        events=self.stream();events[1]["item"]["text"]=json.dumps(
            {"tool":"read","arguments_json":"[]","decision_summary":"read"})
        with self.assertRaisesRegex(ValueError,"invalid_model_action"):r.parsed_action(events)
    def test_model_observes_429_before_retry(self):
        env=b.BusinessEnv(self.scenario("tool_retry"));initial,_=env.reset()
        env.step({"tool":"read","args":{"document_id":"sources"}})
        history=r.request_for(initial,env.events)["history"]
        self.assertEqual(history[0]["observation"]["status"],429)
        self.assertNotIn("body",history[0]["observation"])
    def test_excess_budget_config_rejected(self):
        config=json.loads((ROOT/"configs/runtime-v0.6-rollout.json").read_bytes())
        tasks={tid:{"split":"train" if i==0 else "test"} for i,tid in enumerate(config["task_ids"])}
        self.assertEqual(r.config_validate(config,tasks),config)
        config["max_new_calls"]=37
        with self.assertRaises(ValueError):r.config_validate(config,tasks)
    def test_archived_text_not_in_model_request(self):
        env=b.BusinessEnv(self.scenario());initial,_=env.reset()
        env.step({"tool":"read","args":{"document_id":"sources"}})
        req=r.request_for(initial,env.events)
        self.assertTrue(all(set(row)=={"source_id"} for row in req["history"][0]["observation"]["body"]["rows"]))
        self.assertNotIn("设备盘点",json.dumps(req,ensure_ascii=False))
        self.assertNotEqual(req["initial_observation"]["ticket"]["id"],initial["ticket"]["id"])
    def test_claim_projection_keeps_only_ids(self):
        obs={"status":200,"document_id":"claims","body":{"rows":[{"claim_id":"C1","source_ids":"S1|S2","claim":"PRIVATE"}]}}
        self.assertEqual(r.public_observation(obs)["body"]["rows"],[{"claim_id":"C1","source_ids":"S1|S2"}])
        self.assertNotIn("PRIVATE",json.dumps(r.public_observation(obs)))
    def test_dates_follow_current_snapshot(self):
        scenario=self.scenario()
        self.assertEqual(scenario["as_of"],"2026-09-28")
        self.assertLess(scenario["documents"]["old-note"]["effective_at"],scenario["as_of"])
        self.assertGreater(scenario["documents"]["future"]["effective_at"],scenario["as_of"])
    def test_model_export_uses_same_projected_observations(self):
        scenario=self.scenario();run=c.control(scenario,"reference")
        exported=r.model_messages(scenario,run)
        self.assertNotIn("设备盘点",json.dumps(exported,ensure_ascii=False))
        self.assertEqual(exported[-1]["role"],"assistant")
    def test_pending_execution_cannot_spend_calls(self):
        config=json.loads((ROOT/"configs/runtime-v0.6-rollout.json").read_bytes())
        config["execution_authorization"]="pending"
        with self.assertRaisesRegex(ValueError,"not_approved"):r.require_execution_approval(config)
        config.update(execution_authorization="approved_by_user",approval_record="explicit-user-message")
        r.require_execution_approval(config)
if __name__=="__main__":unittest.main()
