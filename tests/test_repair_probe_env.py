"""Behavioral checks for self-authored regression evidence, not just tool receipt shape."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import repair_probe_env as env
import repair_executor as runner


class ProbeRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.material = json.loads((ROOT / "configs/runtime-v0.14/scoped-event-regression.json").read_bytes())
        m = cls.material
        cls.scenario = {
            "version": env.VERSION, "oracle_id": env.ORACLE_ID, "task_id": "probe-env-test",
            "max_steps": 48, "fault": "clean", "document_ids": {"policy": "policy", "contract": "contract", "worker": "worker.py", "sample": "sample"},
            "document_order": ["policy", "contract", "worker.py", "sample"], "contract": m["contract"],
            "initial_code": m["initial"], "public_cases": m["public_cases"], "private_cases": m["private_cases"],
            "reference_code": m["reference"], "reference_probe": m["reference_probe"],
        }
        cls.case = copy.deepcopy(m["reference_probe"])

    def action(self, runtime, tool, **args):
        return runtime.step({"tool": tool, "args": args})[0]

    def begin(self):
        runtime = env.ResearchEnv(self.scenario)
        for document in runtime.initial["documents"]:
            self.action(runtime, "read", document_id=document)
        self.assertTrue(self.action(runtime, "test")["test"]["passed"])
        return runtime

    def patch(self, runtime, code):
        worker = self.action(runtime, "read", document_id="worker.py")
        result = self.action(runtime, "patch", if_version=worker["version"], old=worker["body"]["code"], new=code)
        self.assertEqual(result["status"], 200)
        self.action(runtime, "read", document_id="worker.py")

    def note(self, runtime, probe_id):
        return self.action(runtime, "write_note", report={
            "status": "ready", "scope": "bounded_program_repair", "code_sha256": env.code_hash(runtime.code),
            "test_run_id": runtime.tests[-1]["test_run_id"], "diagnosis": "A contract-derived scoped event collision failed before repair and was checked on the final worker.",
            "regression_probe_id": probe_id,
        })["note_id"]

    def finish(self, runtime, probe_id, note_id=None):
        if note_id is None:
            note_id = self.note(runtime, probe_id)
        updated = self.action(runtime, "update_ticket", if_version=runtime.ticket["version"], status="ready", note_id=note_id)
        self.action(runtime, "submit", note_id=note_id, ticket_version=updated["ticket"]["version"])
        return env.record(runtime, "scripted_test_policy")

    def run_case(self, baseline=None, final_case=None, retest=True, edit_after_retest=False):
        runtime = self.begin()
        self.action(runtime, "probe", **(baseline if baseline is not None else self.case))
        self.patch(runtime, self.material["reference"])
        fixed_id = "missing-probe"
        if retest:
            fixed_id = self.action(runtime, "probe", **(final_case if final_case is not None else self.case))["probe"]["probe_id"]
        if edit_after_retest:
            self.patch(runtime, runtime.code + "\n# Changed after the probe.\n")
        self.action(runtime, "test")
        return self.finish(runtime, fixed_id)

    def test_existing_examples_pass_but_authored_case_exposes_failure(self):
        runtime = self.begin()
        before = self.action(runtime, "probe", **self.case)["probe"]
        self.assertFalse(before["matches_claim"])
        self.assertEqual(before["version"], 1)
        self.assertEqual(env.oracle(before["input"]), before["expected"])
        self.assertNotEqual(before["actual"], before["expected"])
        self.assertTrue(all(item["passed"] for item in runner.run_cases(self.material["initial"], self.material["public_cases"])["cases"]))

    def test_real_same_case_repair_passes_and_replays(self):
        run = self.run_case()
        self.assertEqual(run["grade"]["reward"], 1)
        self.assertEqual(run["grade"]["validated_regression_pairs"], [{"baseline_probe_id": "probe-1", "fixed_probe_id": "probe-2"}])
        self.assertEqual(env.verify_record(self.scenario, run), run["grade"])
        self.assertEqual(run["environment_version"], env.VERSION)

    def test_fixed_expected_cases_independently_match_oracle_and_reference(self):
        for case in self.material["public_cases"] + self.material["private_cases"]:
            with self.subTest(case=case["name"]):
                self.assertEqual(env.oracle(case["input"]), case["expected"])
                self.assertEqual(runner.execute(self.material["reference"], case["input"]), case["expected"])

    def test_false_expectation_and_uninformative_probe_do_not_certify_failure(self):
        false_case = copy.deepcopy(self.case)
        false_case["expected"] = {"ok": True, "value": ["invented-answer"]}
        cases = [false_case, {"input": {"events": []}, "expected": {"ok": True, "value": []}}]
        for case in cases:
            with self.subTest(case=case):
                run = self.run_case(baseline=case, final_case=case)
                self.assertEqual(run["grade"]["reward"], 0)
                self.assertFalse(run["grade"]["checks"]["baseline_failure_observed"])
                self.assertEqual(run["grade"]["validated_regression_pairs"], [])

    def test_different_case_cannot_stand_in_for_a_regression_retest(self):
        other = copy.deepcopy(self.case)
        for item in other["input"]["events"]:
            item["event_id"] += "-different"
        other["expected"] = env.oracle(other["input"])
        run = self.run_case(final_case=other)
        self.assertTrue(run["grade"]["checks"]["baseline_failure_observed"])
        self.assertFalse(run["grade"]["checks"]["current_regression_pass"])
        self.assertEqual(run["grade"]["reward"], 0)

    def test_missing_retest_and_edit_after_retest_rejected(self):
        for options in ({"retest": False}, {"edit_after_retest": True}):
            with self.subTest(options=options):
                run = self.run_case(**options)
                self.assertEqual(run["grade"]["reward"], 0)
                self.assertFalse(run["grade"]["checks"]["current_regression_pass"])
                self.assertTrue(run["grade"]["checks"]["current_test_pass"])

    def test_note_cannot_reference_future_probe(self):
        runtime = self.begin()
        self.action(runtime, "probe", **self.case)
        self.patch(runtime, self.material["reference"])
        self.action(runtime, "test")
        note = self.note(runtime, "probe-2")
        fixed = self.action(runtime, "probe", **self.case)["probe"]["probe_id"]
        run = self.finish(runtime, fixed, note_id=note)
        self.assertTrue(run["grade"]["checks"]["current_regression_pass"])
        self.assertFalse(run["grade"]["checks"]["regression_note_binding"])
        self.assertEqual(run["grade"]["reward"], 0)

    def test_partial_fix_with_passing_regression_still_fails_private_behavior(self):
        runtime = self.begin()
        self.action(runtime, "probe", **self.case)
        self.patch(runtime, self.material["partial"])
        fixed = self.action(runtime, "probe", **self.case)["probe"]
        self.assertTrue(fixed["matches_claim"])
        self.action(runtime, "test")
        run = self.finish(runtime, fixed["probe_id"])
        self.assertTrue(run["grade"]["checks"]["current_regression_pass"])
        self.assertFalse(run["grade"]["checks"]["private_behavior"])
        self.assertEqual(run["grade"]["reward"], 0)

    def test_input_bounds_and_exception_envelope(self):
        invalid = [
            {"events": [{"tenant_id": "", "event_id": "e", "payload": "p"}]},
            {"events": [{"tenant_id": "t", "event_id": "e", "payload": "p", "extra": True}]},
            {"events": [{"tenant_id": "t", "event_id": "e", "payload": "x" * 81}]},
            {"events": [{"tenant_id": "t", "event_id": "e", "payload": "p"}] * 33},
            {"events": [], "extra": True},
        ]
        runtime = self.begin()
        for data in invalid:
            self.assertFalse(env.valid_input(data))
            self.assertEqual(self.action(runtime, "probe", input=data, expected={"ok": True, "value": []})["status"], 422)
        valid = {"events": [{"tenant_id": "t" * 80, "event_id": "e" * 80, "payload": ""}] * 32}
        self.assertTrue(env.valid_input(valid))
        conflict = {"events": [{"tenant_id": "a", "event_id": "e", "payload": "one"}, {"tenant_id": "a", "event_id": "e", "payload": "two"}]}
        self.assertEqual(env.oracle(conflict), {"ok": False, "error": "ValueError"})
        self.assertEqual(self.action(runtime, "probe", input=conflict, expected={"ok": False, "error": "ValueError"})["status"], 200)

    def test_public_surface_does_not_execute_or_expose_oracle(self):
        from unittest.mock import patch
        runtime = self.begin()
        with patch.object(env, "oracle", side_effect=AssertionError("oracle must stay evaluator-side")):
            self.action(runtime, "probe", **self.case)
            self.action(runtime, "test")
        public = {"initial": runtime.initial, "history": [{"action": e["action"], "observation": e["observation"]} for e in runtime.events]}
        def keys(value):
            if isinstance(value, dict):
                return set(value).union(*(keys(item) for item in value.values()))
            if isinstance(value, list):
                return set().union(*(keys(item) for item in value))
            return set()
        self.assertFalse(keys(public) & {"private_cases", "reference_code", "reference_probe", "oracle_id"})
        public_text = json.dumps(public)
        for case in self.material["private_cases"]:
            self.assertNotIn(case["name"], public_text)
        for name in ("private_cases", "reference_probe", "oracle_id"):
            self.assertEqual(self.action(runtime, "read", document_id=name)["status"], 404)

    def test_replay_rejects_probe_and_grade_tampering(self):
        original = self.run_case()
        for change in ("event", "state", "grade"):
            run = copy.deepcopy(original)
            if change == "event":
                probe = next(event for event in run["events"] if event["action"]["tool"] == "probe")
                probe["observation"]["probe"]["matches_claim"] = True
            elif change == "state":
                run["final_state"]["probes"][0]["expected"] = {"ok": True, "value": []}
            else:
                run["grade"]["validated_regression_pairs"][0]["baseline_probe_id"] = "invented"
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "event_replay_changed|final_state_changed|grade_changed"):
                env.verify_record(self.scenario, run)


if __name__ == "__main__":
    unittest.main()
