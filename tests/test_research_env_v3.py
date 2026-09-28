import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import research_env_v3 as e
import runtime_batch as b

class ResearchEnvV3Tests(unittest.TestCase):
    def scenario(self,family="canal-staffing",variant="clean"):
        config=b.read(ROOT/"configs/runtime-v0.8/batch.json")
        source=next(s for s in config["sources"] if s["family_id"]==family)
        return b.scenario_for(config,source,b.read(ROOT/"configs/runtime-v0.8"/source["material"]),variant)
    def before_note(self,scenario):
        env=e.ResearchEnv(scenario)
        while True:
            action=b.reference_action(env.initial,env.events)
            if action["tool"]=="write_note":return env,action
            env.step(action)
    def finish(self,env,action):
        obs,*_=env.step(action)
        self.assertEqual(obs["status"],200)
        note=obs["note_id"]
        _,_,_,_,_=env.step({"tool":"update_ticket","args":{"if_version":env.ticket["version"],"status":action["args"]["report"]["status"],"note_id":note}})
        env.step({"tool":"submit","args":{"note_id":note,"ticket_version":env.ticket["version"]}})
        return env.grade()
    def test_independent_known_answers_and_counterfactuals(self):
        cases=[("canal-staffing","clean",41),("canal-staffing","counterfactual",37),
               ("birch-fulfilment","clean",8200),("birch-fulfilment","counterfactual",6000),
               ("harbor-inventory","clean",27300),("harbor-inventory","counterfactual",25000)]
        for family,variant,value in cases:
            with self.subTest(family=family,variant=variant):
                run=b.run_reference(self.scenario(family,variant))
                note=run["final_state"]["notes"]["note-1"]["report"]
                self.assertEqual(note["result"]["value"],value)
                self.assertNotIn("S-future",e.canonical(note["citations"]))
                self.assertEqual(run["grade"]["reward"],1)
    def test_false_review_is_rejected_and_real_revision_is_applied(self):
        run=b.run_reference(self.scenario("orchid-quota","counterfactual"))
        self.assertEqual(run["final_state"]["documents"]["claims"]["body"]["rows"][0]["value"],187)
        result=run["final_state"]["notes"]["note-1"]["report"]["result"]
        self.assertEqual(result,{"resolved_findings":["F1"],"rejected_findings":["F2"],"remaining_findings":[]})
    def test_freeform_overclaims_and_empty_assertions_are_rejected(self):
        for text in ("已处理。","这些材料全部真实可靠，已完成事实核验。",""):
            env,action=self.before_note(self.scenario());action["args"]["text"]=text
            obs,*_=env.step(action)
            self.assertEqual(obs["status"],422);self.assertEqual(env.notes,{})
    def test_wrong_result_scope_and_missing_citation_fail_at_submission(self):
        for mutation in ("wrong_result","wrong_scope","missing_citation"):
            run=b.run_reference(self.scenario(),mutation)
            self.assertTrue(run["complete"]);self.assertEqual(run["grade"]["reward"],0)
    def test_correct_blocked_result_is_a_positive_example(self):
        run=b.run_reference(self.scenario("orchid-quota","access_revoked"))
        self.assertEqual(run["grade"]["reward"],1)
        self.assertEqual(run["final_state"]["ticket"]["status"],"blocked")
        self.assertEqual(run["final_state"]["documents"]["claims"]["version"],1)
    def test_boolean_cannot_replace_numeric_answer(self):
        env,action=self.before_note(self.scenario());action["args"]["report"]["result"]["value"]=True
        self.assertEqual(self.finish(env,action)["reward"],0)
    def test_skipped_read_cannot_be_backfilled_after_note(self):
        scenario=self.scenario();correct,action=self.before_note(scenario);env=e.ResearchEnv(scenario)
        for event in correct.events:
            if event["action"]["args"].get("document_id")!="sources":env.step(event["action"])
        obs,*_=env.step(action);note=obs["note_id"]
        env.step({"tool":"read","args":{"document_id":"sources"}})
        env.step({"tool":"update_ticket","args":{"if_version":1,"status":"needs_revision","note_id":note}})
        env.step({"tool":"submit","args":{"note_id":note,"ticket_version":2}})
        self.assertFalse(env.grade()["checks"]["evidence_links"])
    def test_claim_revision_without_reread_is_not_verified(self):
        scenario=self.scenario("orchid-quota");correct,action=self.before_note(scenario);env=e.ResearchEnv(scenario)
        for event in correct.events:
            if event["action"]["tool"]=="read" and event["action"]["args"]["document_id"]=="claims" and env.documents["claims"]["version"]>1:continue
            env.step(event["action"])
        self.assertFalse(self.finish(env,action)["checks"]["evidence_links"])
    def test_claiming_review_resolved_without_patch_fails(self):
        scenario=self.scenario("orchid-quota");_,action=self.before_note(scenario);env=e.ResearchEnv(scenario)
        for doc in env.initial["documents"]:env.step({"tool":"read","args":{"document_id":doc}})
        for cite in action["args"]["report"]["citations"]:
            if cite["document_id"]=="claims":cite["version"]=1
        grade=self.finish(env,action);self.assertTrue(grade["checks"]["evidence_links"]);self.assertFalse(grade["checks"]["task_resolution"])
    def test_429_and_409_are_recorded_and_resolved(self):
        for variant,status in (("tool_retry",429),("concurrent_edit",409)):
            run=b.run_reference(self.scenario(variant=variant))
            self.assertIn(status,[event["observation"]["status"] for event in run["events"]])
            self.assertEqual(e.verify_record(self.scenario(variant=variant),run)["reward"],1)
    def test_replay_detects_rehashed_observation_or_final_text(self):
        scenario=self.scenario();run=b.run_reference(scenario)
        for where in ("event","note"):
            changed=copy.deepcopy(run)
            if where=="event":changed["events"][0]["observation"]["body"]["purpose"]="changed"
            else:changed["final_state"]["notes"]["note-1"]["text"]="Fully verified."
            with self.assertRaisesRegex(ValueError,"changed"):e.verify_record(scenario,changed)
    def test_invalid_tool_arguments_are_observations_and_consume_budget(self):
        env=e.ResearchEnv(self.scenario())
        actions=[{"tool":"read","args":{"document_id":[]}}, {"tool":"submit","args":{"note_id":[],"ticket_version":2}},
                 {"tool":"write_note","args":{"report":{}}}, {"tool":"read_ticket","args":{"extra":1}}]
        for action in actions:
            if env.finished:break
            obs,*_=env.step(action);self.assertIn(obs["status"],(200,400,422))
        env=e.ResearchEnv(self.scenario())
        for _ in range(24):env.step({"tool":"read","args":{"document_id":[]}})
        self.assertTrue(env.truncated);self.assertEqual(env.grade()["reward"],0)
    def test_extra_retry_fails_even_with_correct_final_report(self):
        scenario=self.scenario(variant="tool_retry");env,action=self.before_note(scenario)
        env.step({"tool":"read","args":{"document_id":"sources"}})
        self.assertFalse(self.finish(env,action)["checks"]["retry_budget"])
    def test_config_batch_and_source_split_are_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"batch";result=b.build(ROOT/"configs/runtime-v0.8/batch.json",root)
            self.assertEqual((result["tasks"],result["families"],result["controls"]),(24,6,120))
            rows=b.lines(root/"training/scripted-trajectories.jsonl")
            rows.append({"task_id":"test-family"});(root/"training/scripted-trajectories.jsonl").write_bytes(("".join(e.canonical(r)+"\n" for r in rows)).encode())
            manifest=b.read(root/"manifest.json");manifest["files"]=b.hashes(root);(root/"manifest.json").write_bytes(b.encoded(manifest))
            with self.assertRaisesRegex(ValueError,"training_selection_changed"):b.verify(root)

if __name__=="__main__":unittest.main()
