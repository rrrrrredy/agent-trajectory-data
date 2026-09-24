import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from agentdata.core import (
    generate, read, run_task, split_for, quality_decision,
    export_runs, import_workflow, redact, write_new, grade, stats
)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tasks = [read(p) for p in generate(self.root, 1, 91)]

    def task(self, variant="normal"):
        return next(t for t in self.tasks if t["variant"] == variant)

    def test_reference_success_and_missing_evidence(self):
        for task in self.tasks:
            result = run_task(self.root, task)
            self.assertTrue(result["evaluation"]["passed"])
        records = list((self.root / "runs").glob("*/run.json"))
        self.assertEqual(3, len(records))

    def test_transient_failure_is_retained(self):
        result = run_task(self.root, self.task("transient_error"))
        events = [json.loads(x) for x in (self.root / result["events_path"]).read_text().splitlines()]
        observations = [e["payload"] for e in events if e["event_type"] == "observation"]
        self.assertEqual([429, 200], [o["status"] for o in observations])
        self.assertEqual([1, 2], [o["attempt"] for o in observations])

    def test_negative_run_retained_and_not_sft(self):
        result = run_task(self.root, self.task(), "broken")
        self.assertFalse(result["evaluation"]["passed"])
        self.assertEqual("accept", quality_decision(self.root, result)["decision"])
        decision = quality_decision(self.root, result, "sft", True)
        self.assertIn("failed_run_not_sft_demonstration", decision["reasons"])

    def test_budget_stops_loop(self):
        result = run_task(self.root, self.task(), "loop", max_steps=2)
        self.assertEqual("step_budget_exhausted", result["terminal_reason"])
        self.assertIsNone(result["evaluation"]["passed"])
        self.assertEqual("accept", quality_decision(self.root, result)["decision"])

    def test_retries_are_bounded(self):
        task = self.task("transient_error")
        task["environment"][task["public"]["source_ids"][0]]["responses"] = [429]
        result = run_task(self.root, task, max_tool_retries=1)
        self.assertEqual("tool_retry_exhausted", result["terminal_reason"])

    def test_same_family_cannot_cross_splits(self):
        self.assertEqual(1, len({t["split"] for t in self.tasks}))
        result = run_task(self.root, self.task())
        result["split"] = "holdout" if result["split"] != "holdout" else "train"
        self.assertIn("invalid_family_split", quality_decision(self.root, result)["reasons"])

    def test_unobserved_evidence_cannot_pass(self):
        task = self.task()
        result = grade(task, {"verdict": "answered", "answer": task["oracle"]["answer"],
                              "evidence_ids": ["invented"]}, [])
        self.assertFalse(result["passed"])
        self.assertIn("unobserved_evidence", result["failure_codes"])

    def test_import_does_not_invent_full_trace_or_rights(self):
        source = self.root / "source"
        (source / "logs").mkdir(parents=True)
        (source / "logs" / "review.jsonl").write_text(json.dumps({
            "record_type": "model_review", "execution_id": "observed-session",
            "status": "completed", "report_verdict": "pass"}) + "\n")
        result = import_workflow(self.root, source)
        decision = quality_decision(self.root, result)
        self.assertIn("incomplete_trace", decision["reasons"])
        self.assertIn("rights_not_established", decision["reasons"])
        self.assertEqual("observed-session", result["observed_reviews"][0]["execution_id"])

    def test_command_never_receives_oracle(self):
        script = self.root / "actor.py"
        script.write_text(
            "import json,sys\np=json.load(sys.stdin)\n"
            "assert set(p)=={'protocol','task','observations'}\n"
            "assert 'oracle' not in p['task'] and 'environment' not in p['task']\n"
            "print(json.dumps({'tool':'submit_answer','verdict':'insufficient_evidence',"
            "'answer':{},'evidence_ids':[]}))\n")
        result = run_task(self.root, self.task("missing_source"), "command",
                          command=[sys.executable, str(script)])
        self.assertIn("unverified_source_unavailability", result["evaluation"]["failure_codes"])

    def test_bad_command_protocol_preserves_failure(self):
        result = run_task(self.root, self.task(), "command",
                          command=[sys.executable, "-c", "print('not json')"])
        self.assertEqual("runner_error", result["terminal_reason"])
        self.assertTrue((self.root / result["events_path"]).exists())

    def test_command_timeout_does_not_retry_unknown_cancellation(self):
        result = run_task(self.root, self.task(), "command", max_seconds=0.05,
                          command=[sys.executable, "-c", "import time;time.sleep(1)"])
        self.assertEqual("runner_timeout", result["terminal_reason"])
        events = (self.root / result["events_path"]).read_text()
        self.assertEqual(1, events.count('"event_type": "runner_error"'))
        self.assertIn('"remote_request_cancelled": "unknown"', events)

    def test_corrupt_chain_is_quarantined(self):
        result = run_task(self.root, self.task())
        path = self.root / result["events_path"]
        events = [json.loads(x) for x in path.read_text().splitlines()]
        events[1]["parent_event_ids"] = ["not-a-parent"]
        path.write_text("\n".join(json.dumps(x) for x in events) + "\n")
        self.assertIn("invalid_event_chain", quality_decision(self.root, result)["reasons"])

    def test_immutable_task_generation(self):
        first = generate(self.root, 1, 91)
        self.assertEqual(first, generate(self.root, 1, 91))
        with self.assertRaises(ValueError):
            write_new(first[0], {"replacement": True})

    def test_export_and_training_default_excludes_scripted_controls(self):
        result = run_task(self.root, self.task())
        self.assertIn("scripted_control_not_model_training_data",
                      quality_decision(self.root, result, "sft")["reasons"])
        counts = export_runs(self.root, self.root / "release.json")
        self.assertEqual({"accepted": 1, "quarantined": 0}, counts)

    def test_unknown_rights_never_export(self):
        result = run_task(self.root, self.task())
        result["rights"] = {"basis": "unknown", "allowed_uses": []}
        self.assertIn("rights_not_established", quality_decision(self.root, result)["reasons"])

    def test_secret_fields_are_filtered(self):
        result = redact({"api_key": "secret-value", "message": "Bearer abcdefg",
                         "nested": [{"password": "another-secret"}]})
        self.assertNotIn("secret-value", json.dumps(result))
        self.assertNotIn("another-secret", json.dumps(result))
        self.assertEqual("Bearer [REDACTED]", result["message"])

    def test_tampered_label_is_recomputed(self):
        result = run_task(self.root, self.task(), "broken")
        result["evaluation"]["passed"] = True
        result["evaluation"]["outcome"] = "pass"
        self.assertIn("evaluation_mismatch", quality_decision(self.root, result)["reasons"])

    def test_task_snapshot_change_blocks_export(self):
        result = run_task(self.root, self.task())
        path = self.root / result["task_snapshot_path"]
        task = json.loads(path.read_text())
        task["public"]["question"] = "changed after run"
        path.write_text(json.dumps(task))
        self.assertIn("task_hash_mismatch", quality_decision(self.root, result)["reasons"])

    def test_trace_contains_visible_initial_task(self):
        result = run_task(self.root, self.task())
        event = json.loads((self.root / result["events_path"]).read_text().splitlines()[0])
        self.assertIn("visible_task", event["payload"])
        self.assertNotIn("oracle", event["payload"]["visible_task"])

    def test_events_outside_root_are_denied(self):
        result = run_task(self.root, self.task())
        result["events_path"] = "../outside.jsonl"
        self.assertIn("event_path_outside_root", quality_decision(self.root, result)["reasons"])

    def test_terminal_metadata_mismatch_is_quarantined(self):
        result = run_task(self.root, self.task())
        result["terminal_reason"] = "runner_timeout"
        self.assertIn("terminal_event_mismatch", quality_decision(self.root, result)["reasons"])

    def test_abstention_requires_observed_unavailability(self):
        task = self.task("missing_source")
        result = grade(task, {"verdict": "insufficient_evidence", "answer": {},
                              "evidence_ids": []}, [])
        self.assertIn("unverified_source_unavailability", result["failure_codes"])

    def test_missing_or_changed_actor_cannot_bypass_training_gate(self):
        record = run_task(self.root, self.task())
        for actor in ("model", None, "recorded_model_review"):
            result = copy.deepcopy(record)
            result["actor_kind"] = actor
            self.assertEqual("quarantine", quality_decision(self.root, result, "sft")["decision"])
        del record["actor_kind"]
        self.assertEqual("quarantine", quality_decision(self.root, record, "sft")["decision"])

    def test_abstention_requires_terminal_missing_status(self):
        task = self.task("missing_source")
        submission = {"verdict": "insufficient_evidence", "answer": {}, "evidence_ids": []}
        for status in (200, 429):
            result = grade(task, submission, [{"source_id": task["public"]["source_ids"][0],
                                               "status": status}])
            self.assertIn("unverified_source_unavailability", result["failure_codes"])

    def test_one_corrupt_record_does_not_stop_batch(self):
        run_task(self.root, self.task())
        path = self.root / "runs" / "broken-record" / "run.json"
        path.parent.mkdir()
        path.write_text("{broken json")
        counts = export_runs(self.root, self.root / "partial-export.json")
        self.assertEqual({"accepted": 1, "quarantined": 1}, counts)
        self.assertEqual(2, stats(self.root)["runs"])
        quarantine = read(self.root / "partial-export.json")["quarantine"][0]
        self.assertEqual("invalid_run_record", quarantine["reasons"][0])
        self.assertTrue(quarantine["source_record_sha256"])

    def test_invalid_metadata_types_are_quarantined(self):
        record = run_task(self.root, self.task())
        for field in ("rights", "evaluation", "events_path", "task_snapshot_path"):
            result = copy.deepcopy(record)
            result[field] = []
            self.assertEqual("quarantine", quality_decision(self.root, result)["decision"])

    def test_wrong_event_path_type_does_not_stop_export(self):
        record = run_task(self.root, self.task())
        record["events_path"] = 1
        path = self.root / "runs" / record["run_id"] / "run.json"
        path.write_text(json.dumps(record))
        counts = export_runs(self.root, self.root / "invalid-path-export.json")
        self.assertEqual({"accepted": 0, "quarantined": 1}, counts)

    def test_wrong_task_identity_is_quarantined(self):
        result = run_task(self.root, self.task())
        result["task_id"] = "a-different-task"
        reasons = quality_decision(self.root, result)["reasons"]
        self.assertIn("task_provenance_mismatch", reasons)
        self.assertIn("invalid_event_chain", reasons)

    def test_invalid_budget_rejected(self):
        for value in (0, -1, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                run_task(self.root, self.task(), max_seconds=value)


if __name__ == "__main__":
    unittest.main()
