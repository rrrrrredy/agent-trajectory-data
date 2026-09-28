import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"scripts"))
import research_env_v4 as e
import runtime_tasks_v4 as t
import runtime_batch as b
import runtime_collect as c

class ResearchEnvV4Tests(unittest.TestCase):
    def scenario(self,family="willow-dispatch",variant="clean"):
        config=b.read(ROOT/"configs/runtime-v0.9/batch.json")
        source=next(x for x in config["sources"] if x["family_id"]==family)
        return b.scenario_for(config,source,b.read(ROOT/"configs/runtime-v0.9"/source["material"]),variant)
    def before_note(self,scenario):
        env=e.ResearchEnv(scenario)
        while True:
            action=t.reference_action(env.initial,env.events)
            if action["tool"]=="write_note":return env,action
            env.step(action)
    def test_independent_hand_calculated_dependency_totals(self):
        for family,variant,total in [("willow-dispatch","clean",6300),("willow-dispatch","counterfactual",6000),("marina-capacity","clean",9000),("marina-capacity","counterfactual",10000)]:
            with self.subTest(family=family,variant=variant):
                run=t.run_reference(self.scenario(family,variant))
                report=run["final_state"]["notes"]["note-1"]["report"]
                self.assertEqual(report["result"]["value"],total);self.assertEqual(run["grade"]["reward"],1)
                cited={x["document_id"] for x in report["citations"]};self.assertIn("capacity-total",cited)
                self.assertEqual("reservation-revised" in cited,variant=="counterfactual")
    def test_future_material_is_unobservable_through_search_and_read(self):
        scenario=self.scenario();env=e.ResearchEnv(scenario)
        self.assertNotIn("future-resolution",e.canonical(env.initial))
        obs,*_=env.step({"tool":"search","args":{"query":""}});self.assertNotIn("future-resolution",obs["documents"])
        future,*_=env.step({"tool":"read","args":{"document_id":"future-resolution"}})
        missing,*_=env.step({"tool":"read","args":{"document_id":"unknown-document"}})
        for item in (future,missing):self.assertEqual(item["status"],404);self.assertNotIn("body",item);self.assertIsNone(item["version"])
        request=c.request_for(env,{"max_call_seconds":90},20,100)
        self.assertNotIn("99999",e.canonical(request));self.assertNotIn("documents",request)
        later=copy.deepcopy(scenario);later["as_of"]="2026-10-02";later_env=e.ResearchEnv(later)
        obs,*_=later_env.step({"tool":"read","args":{"document_id":"future-resolution"}});self.assertEqual(obs["status"],200)
    def test_hidden_document_changes_do_not_change_public_trace(self):
        original=self.scenario();changed=copy.deepcopy(original)
        changed["documents"]["future-resolution"]["body"]["rows"][0]["value"]=-987654
        left=t.run_reference(original);right=t.run_reference(changed)
        self.assertEqual(left["initial_observation"],right["initial_observation"])
        self.assertEqual([(x["action"],x["observation"],x["reward"]) for x in left["events"]],[(x["action"],x["observation"],x["reward"]) for x in right["events"]])
    def test_withheld_dependency_produces_valid_blocked_without_guessing(self):
        for family in ("willow-dispatch","cedar-access","aster-routing"):
            run=t.run_reference(self.scenario(family,"withheld_evidence"));report=run["final_state"]["notes"]["note-1"]["report"]
            self.assertEqual(report["status"],"blocked");self.assertEqual(run["grade"]["reward"],1)
            self.assertEqual(run["final_state"]["revisions"],[])
            self.assertTrue(any(citation["status"]==404 for citation in report["citations"]))
    def test_peer_conflict_remains_unresolved_despite_newer_record(self):
        scenario=self.scenario("cedar-access");run=t.run_reference(scenario)
        report=run["final_state"]["notes"]["note-1"]["report"]
        self.assertEqual(report["result"],{"resolution":"unresolved_conflict","value":None,"unit":"seats"})
        self.assertEqual(report["status"],"blocked")
        self.assertEqual(t.run_reference(scenario,"prefer_latest_over_authority")["grade"]["reward"],0)
    def test_authority_can_outweigh_recency_without_changing_evidence_values(self):
        run=t.run_reference(self.scenario("flint-retention","counterfactual"))
        report=run["final_state"]["notes"]["note-1"]["report"]
        self.assertEqual(report["result"],{"resolution":"resolved","value":30,"unit":"days"})
        self.assertEqual(report["status"],"ready")
    def test_multi_claim_repair_and_unsupported_review_are_verified(self):
        run=t.run_reference(self.scenario("aster-routing","counterfactual"));state=run["final_state"]
        self.assertEqual({r["claim_id"] for r in state["revisions"]},{"C1","C2"})
        self.assertEqual(state["notes"]["note-1"]["report"]["result"]["rejected_findings"],["F3"])
        rows={r["row_id"]:r for r in state["documents"]["claims"]["body"]["rows"]}
        self.assertEqual((rows["C1"]["value"],rows["C2"]["unit"]),(187,"days"))
        self.assertEqual(rows["C0"],{"row_id":"C0","value":7,"unit":"batches"})
    def test_partial_repair_cannot_receive_terminal_success(self):
        run=t.run_reference(self.scenario("aster-routing"),"partial_repair")
        self.assertTrue(run["complete"]);self.assertEqual(run["grade"]["reward"],0)
        self.assertFalse(run["grade"]["checks"]["task_resolution"])
    def test_concurrent_claim_update_is_retried_with_fresh_evidence(self):
        scenario=self.scenario("aster-routing","stale_revision");run=t.run_reference(scenario)
        events=run["events"];conflict=next(i for i,x in enumerate(events) if x["observation"]["status"]==409)
        self.assertEqual(events[conflict+1]["action"],{"tool":"read","args":{"document_id":"claims"}})
        self.assertEqual(e.verify_record(scenario,run)["reward"],1)
        note=run["final_state"]["notes"]["note-1"]
        claim_cite=next(x for x in note["report"]["citations"] if x["document_id"]=="claims")
        self.assertEqual(claim_cite["version"],4)
    def test_each_revision_requires_current_read_and_protected_claim_is_denied(self):
        env=e.ResearchEnv(self.scenario("aster-routing"))
        obs,*_=env.step({"tool":"revise_claim","args":{"if_version":1,"claim_id":"C1","value":187,"unit":"requests_per_day"}});self.assertEqual(obs["status"],412)
        env.step({"tool":"read","args":{"document_id":"claims"}})
        env.step({"tool":"revise_claim","args":{"if_version":1,"claim_id":"C1","value":187,"unit":"requests_per_day"}})
        obs,*_=env.step({"tool":"revise_claim","args":{"if_version":2,"claim_id":"C2","value":14,"unit":"days"}});self.assertEqual(obs["status"],412)
        obs,*_=env.step({"tool":"revise_claim","args":{"if_version":2,"claim_id":"C0","value":99,"unit":"batches"}});self.assertEqual(obs["status"],403)
    def test_terminal_reward_is_recorded_and_replayed(self):
        scenario=self.scenario();run=t.run_reference(scenario)
        self.assertEqual([x["reward"] for x in run["events"]],[0]*(len(run["events"])-1)+[1])
        run["events"][0]["reward"]=1
        with self.assertRaisesRegex(ValueError,"event_replay_changed"):e.verify_record(scenario,run)
    def test_policy_identifier_does_not_disclose_fault_or_split(self):
        env=e.ResearchEnv(self.scenario(variant="tool_retry"))
        self.assertRegex(env.initial["task_id"],r"^task-[a-f0-9]{16}$")
        self.assertNotIn("tool_retry",e.canonical(env.initial));self.assertNotIn("train",env.initial["ticket"]["id"])
    def test_pipeline_builds_and_replays_158_controls(self):
        with tempfile.TemporaryDirectory() as d:
            result=b.build(ROOT/"configs/runtime-v0.9/batch.json",Path(d)/"batch")
            self.assertEqual((result["tasks"],result["families"],result["controls"]),(24,6,158))
    def test_cyclic_graph_is_rejected(self):
        config=b.read(ROOT/"configs/runtime-v0.9/batch.json");source=config["sources"][0]
        material=b.read(ROOT/"configs/runtime-v0.9"/source["material"])
        changed=copy.deepcopy(material);body=changed["documents"]["capacity-total"]["body"]
        body["references"]=["capacity-net"];body["rows"][0]["inputs"]=["capacity-net"]
        with self.assertRaisesRegex(ValueError,"cyclic_dependency"):t.validate_material(source,changed,config["as_of"])
    def test_renaming_context_does_not_create_a_new_source_family(self):
        config=b.read(ROOT/"configs/runtime-v0.9/batch.json");source=config["sources"][0]
        material=b.read(ROOT/"configs/runtime-v0.9"/source["material"])
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);original=copy.deepcopy(source);original["material"]="first.json"
            renamed=copy.deepcopy(source);renamed.update(family_id="renamed-company",material="second.json")
            duplicate=copy.deepcopy(material);duplicate["family_id"]="renamed-company"
            duplicate["documents"]["handoff"]["body"]["context"]="Only a different company name."
            b.put(folder/"first.json",material);b.put(folder/"second.json",duplicate);config["sources"]=[original,renamed]
            with self.assertRaisesRegex(ValueError,"duplicate_source_content"):b.validate_config(config,folder)

    def test_request_rejects_inflated_batch_budgets(self):
        env=e.ResearchEnv(self.scenario());config={"max_call_seconds":90,"max_new_calls":10,"max_batch_seconds":100}
        with self.assertRaisesRegex(ValueError,"invalid_remaining_call_budget"):c.request_for(env,config,11,90)
        with self.assertRaisesRegex(ValueError,"invalid_remaining_time_budget"):c.request_for(env,config,10,101)

if __name__=="__main__":unittest.main()
