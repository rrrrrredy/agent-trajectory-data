"""Tests for faithful event projection, action boundaries and fallible review labels."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/research_history.py"
spec = importlib.util.spec_from_file_location("research_history", SCRIPT)
history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history)
rd = history.rd

def raw_rows(rows):
    return b"".join(json.dumps(r, ensure_ascii=False).encode("utf-8") + b"\n" for r in rows)

class RuntimeHistoryTests(unittest.TestCase):
    def rows(self):
        command = {"id": "item_1", "type": "command_execution", "command": "rg absent report.md",
                   "aggregated_output": "", "exit_code": None, "status": "in_progress"}
        web = {"id": "search_1", "type": "web_search", "query": "evidence",
               "action": {"type": "search", "queries": ["evidence"]}}
        return [
            {"type": "thread.started", "thread_id": "fixture-session"},
            {"type": "turn.started"},
            {"type": "item.started", "item": command},
            {"type": "item.completed", "item": {**command, "exit_code": 1, "status": "completed"}},
            {"type": "item.started", "item": web},
            {"type": "item.completed", "item": web},
            {"type": "item.completed", "item": {"id": "message", "type": "agent_message", "text": "done"}},
            {"type": "turn.completed", "usage": {"input_tokens": 4, "output_tokens": 1}}]

    def derive(self, rows):
        projected, excluded = history.project_capture(raw_rows(rows), r"D:\fixture")
        result = {"session_id": "fixture-session", "exit_code": 0, "timeout": False,
                  "elapsed_seconds": 1, "usage": [{"input_tokens": 4, "output_tokens": 1}]}
        return history.derive_turn("fixture", 2, projected, "先停在这里", "done\n", result,
                                   {"args": ["model=\"fixture-model\""]})

    def test_real_action_boundaries_do_not_imply_quality_or_web_body(self):
        info, events, actions, failures = self.derive(self.rows())
        self.assertEqual(info["quality_outcome"], "not_assessed")
        self.assertEqual(info["instruction_boundary"], "explicit_pause")
        self.assertTrue(info["final_message_matches_event"])
        self.assertEqual(info["unmatched_actions"], 0)
        self.assertFalse(actions[1]["output_available"])
        self.assertEqual(actions[1]["observation_kind"], "action_metadata_only")
        self.assertEqual(failures[0]["exit_code"], 1)
        self.assertEqual(failures[0]["task_failure"], "not_assessed")

    def test_unmatched_action_is_retained(self):
        rows = self.rows()
        del rows[3]
        info, _, actions, failures = self.derive(rows)
        self.assertEqual(info["unmatched_actions"], 1)
        self.assertFalse(actions[0]["output_available"])
        self.assertEqual(failures, [])

    def test_changed_command_and_reversed_boundary_rejected(self):
        rows = self.rows()
        rows[3]["item"]["command"] = "different command"
        with self.assertRaisesRegex(ValueError, "command_changed"):
            self.derive(rows)
        rows = self.rows()
        rows[2], rows[3] = rows[3], rows[2]
        with self.assertRaisesRegex(ValueError, "reversed_action_boundary"):
            self.derive(rows)

    def test_source_session_and_usage_cannot_be_reassigned(self):
        rows = self.rows()
        rows[0]["thread_id"] = "different-session"
        with self.assertRaisesRegex(ValueError, "session_binding"):
            self.derive(rows)
        rows = self.rows()
        rows[-1]["usage"]["input_tokens"] += 1
        with self.assertRaisesRegex(ValueError, "usage_binding"):
            self.derive(rows)

    def test_unicode_line_break_and_hidden_reasoning_projection(self):
        rows = [
            {"type": "item.completed", "item": {"id": "hidden", "type": "reasoning", "text": "not exported"}},
            {"type": "item.completed", "item": {"id": "message", "type": "agent_message", "text": "a\u2028b"}},
            {"type": "item.completed", "item": {"id": "cmd", "type": "command_execution",
                "command": "Get-Content D:/Codex/_home/memories/MEMORY.md",
                "aggregated_output": "Unrelated context", "exit_code": 0, "status": "completed"}}]
        projected, excluded = history.project_capture(raw_rows(rows), r"D:\fixture")
        self.assertEqual(len(projected), 2)
        self.assertEqual(projected[0]["source_line"], 2)
        self.assertEqual(len(excluded), 1)
        self.assertNotIn("not exported", json.dumps(projected))
        self.assertNotIn("Unrelated context", json.dumps(projected))
        self.assertEqual(projected[1]["redactions"][0]["original_sha256"], rd.sha(b"Unrelated context"))

    def test_unknown_fields_and_credentials_rejected_without_domain_false_positive(self):
        rows = self.rows()
        rows[2]["item"]["reasoning"] = "must not be exported"
        with self.assertRaisesRegex(ValueError, "unknown_capture_item_fields"):
            self.derive(rows)
        with self.assertRaisesRegex(ValueError, "credential_like_content"):
            history.scrub("sk-" + "x" * 35, "")
        url = "https://example.test/zendesk-customer-support-release-notes"
        self.assertEqual(history.scrub(url, ""), url)
        self.assertEqual(history.scrub(r"D:\fixture\report.md", r"D:\fixture"), r"<RUN_WORKSPACE>\report.md")

class SemanticHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / "sources/semantic"
        self.case = {"id": "case-1", "evidence": "Four passed one check.",
                     "bad": "All twenty fully passed.", "control": "Four complete successes.",
                     "expected_failure": "Unsupported success denominator.",
                     "control_boundary": "The proposed control can be wrong.", "critical_fact_failure": True}
        self.revision = {"revision_id": "case-1-r2", "case_id": "case-1",
                         "base_case_sha256": rd.sha(json.dumps(self.case, ensure_ascii=False,
                            sort_keys=True, separators=(",", ":")).encode()),
                         "reason": "The original control also overclaimed.",
                         "changes": {"control": "Four passed one check; full success is unknown."}}
        self.write("source-catalogs/cases.json", {"cases": [self.case]})
        self.write("source-catalogs/additional-cases.json", {"cases": []})
        self.write("source-catalogs/revisions.json", {"revisions": [self.revision]})
        self.write("mapping.json", {"jobs": {"batch-01": [
            {"id": "item-1", "original_id": "case-1", "A": "bad", "B": "control"}]}})
        self.write("revisions-mapping.json", {"items": []})
        self.input = {"system": "Review supplied text.", "user": json.dumps([
            {"id": "item-1", "evidence": self.case["evidence"], "A": self.case["bad"], "B": self.case["control"]}
        ]) + "\nReturn JSON."}
        self.write("inputs/batch-01.json", self.input)
        self.write("requests/model/batch-01.json", {"model": "fixture",
            "messages": [{"role": k, "content": self.input[k]} for k in ("system", "user")]})
        result = {"cases": [{"id": "item-1",
            "A": {"judgment": "flawed", "critical_fact_error": True, "reason": "excessive", "evidence_boundary": "partial"},
            "B": {"judgment": "acceptable", "critical_fact_error": False, "reason": "missed flaw", "evidence_boundary": "partial"}}]}
        self.response = {"content": json.dumps(result), "parsed": result, "model_returned": "fixture",
                         "finish_reason": "stop", "usage": {"output_tokens": 1},
                         "input_sha256": rd.normalized_hash(self.directory / "inputs/batch-01.json")}
        self.write("finals/model/batch-01.json", self.response)
        self.write("attempts/model/batch-01.json", {"input_sha256": self.response["input_sha256"],
                   "model_returned": "fixture", "model_requested": "fixture"})
        self.write("run-index.json", {"held_out": False, "author_labels_are_truth": False,
            "unique_original_pairs": 1, "attempts": 1, "records": [
                {"provider": "model", "job": "batch-01", "input": "inputs/batch-01.json",
                 "request": "requests/model/batch-01.json", "final": "finals/model/batch-01.json",
                 "attempt": "attempts/model/batch-01.json"}]})

    def write(self, rel, value):
        path = self.directory / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(rd.encoded(value))

    def test_fallible_model_judgment_and_retained_revision_are_not_gold(self):
        views = history.semantic_views(self.root)
        self.assertEqual(len(views["semantic_cases.jsonl"]), 2)
        self.assertEqual(views["semantic_cases.jsonl"][1]["revision_of"], "case-1")
        judged = views["judgments.jsonl"][1]
        self.assertEqual(judged["model_judgment"]["judgment"], "acceptable")
        self.assertIsNone(judged["gold_label"])
        self.assertFalse(judged["rights"]["training_eligible"])
        self.assertEqual(judged["split"], "development")

    def test_orientation_swap_is_rejected(self):
        self.write("mapping.json", {"jobs": {"batch-01": [
            {"id": "item-1", "original_id": "case-1", "A": "control", "B": "bad"}]}})
        with self.assertRaisesRegex(ValueError, "semantic_orientation"):
            history.semantic_views(self.root)

    def test_parsed_review_cannot_change_visible_model_response(self):
        changed = copy.deepcopy(self.response)
        changed["parsed"]["cases"][0]["B"]["judgment"] = "flawed"
        self.write("finals/model/batch-01.json", changed)
        with self.assertRaisesRegex(ValueError, "semantic_response_content"):
            history.semantic_views(self.root)

    def test_revision_cannot_be_applied_to_different_original(self):
        self.revision["base_case_sha256"] = "0" * 64
        self.write("source-catalogs/revisions.json", {"revisions": [self.revision]})
        with self.assertRaisesRegex(ValueError, "revision_base_hash"):
            history.semantic_views(self.root)

if __name__ == "__main__":
    unittest.main()
