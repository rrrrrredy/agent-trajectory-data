"""Regression tests for native observation recovery and label-free input export."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("research_corpus", Path(__file__).resolve().parents[1] / "scripts/research_corpus.py")
corpus = importlib.util.module_from_spec(spec)
spec.loader.exec_module(corpus)
rd = corpus.rd

class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prior = self.root / "prior"
        rd.put(self.prior / "prompt.txt", "Original task\n".encode())
        rd.put(self.prior / "message.md", "Delivered report\n".encode())
        self.turn = {"session_id": "session-fixture", "turn": 1, "prompt_path": "prompt.txt",
                     "final_message_path": "message.md"}
        def row(kind, payload):
            return {"type": kind, "timestamp": "2026-09-07T01:00:00Z", "payload": payload}
        self.records = [
            row("session_meta", {"id": "session-fixture", "cwd": r"D:\fixture"}),
            row("event_msg", {"type": "task_started", "turn_id": "native-turn-1"}),
            row("response_item", {"type": "message", "role": "developer", "content": [
                {"type": "input_text", "text": "Private system context"}]}),
            row("response_item", {"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": "Original task"}]}),
            row("response_item", {"type": "reasoning", "summary": "Hidden reasoning"}),
            row("response_item", {"type": "custom_tool_call", "name": "exec", "call_id": "web",
                                  "input": 'text(await tools.web__run({search_query:[{q:"example"}]}));'}),
            row("response_item", {"type": "custom_tool_call_output", "call_id": "web", "output": [
                {"type": "input_text", "text": "Source page\u2028contains a legal Unicode separator.\nWarning: truncated output"}]}),
            row("response_item", {"type": "custom_tool_call", "name": "exec", "call_id": "global",
                                  "input": 'text(await tools.exec_command({cmd:"read D:/Codex/_home/memories/MEMORY.md"}));'}),
            row("response_item", {"type": "custom_tool_call_output", "call_id": "global", "output": [
                {"type": "input_text", "text": "Unrelated personal context"}]}),
            row("response_item", {"type": "message", "role": "assistant", "phase": "final_answer",
                                  "content": [{"type": "output_text", "text": "Delivered report\n\n<oai-mem-citation>Client footer</oai-mem-citation>"}]}),
            row("event_msg", {"type": "task_complete", "turn_id": "native-turn-1"})]

    def project(self):
        raw = b"".join(json.dumps(x, ensure_ascii=False).encode() + b"\n" for x in self.records)
        return corpus.project_native(raw, "fixture", [self.turn], self.prior)

    def test_projection_preserves_observations_without_private_context(self):
        events, meta = self.project()
        serialized = json.dumps(events, ensure_ascii=False)
        self.assertNotIn("Hidden reasoning", serialized)
        self.assertNotIn("Private system context", serialized)
        self.assertNotIn("Unrelated personal context", serialized)
        self.assertNotIn("Client footer", serialized)
        self.assertIn("Source page\u2028contains", serialized)
        final = next(e for e in events if e["kind"] == "assistant_message")
        self.assertEqual(final["channel"], "final")
        self.assertTrue(final["client_footer_removed"])
        self.assertEqual(meta["prompt_source_lines"], {1: 4})
        pairs = corpus.native_calls(events)
        self.assertEqual(len(pairs), 2)
        self.assertTrue(pairs[0]["output_available"])
        self.assertTrue(pairs[0]["truncation_marker_present"])
        self.assertTrue(pairs[0]["web_related_executor_batch"])
        self.assertFalse(pairs[1]["output_available"])
        self.assertFalse(pairs[0]["fully_replayable_environment"])

    def test_actual_final_body_change_is_rejected(self):
        self.records[-2]["payload"]["content"][0]["text"] = "A different report"
        with self.assertRaisesRegex(ValueError, "native_final_message"):
            self.project()

    def test_prompt_and_session_binding_cannot_be_reassigned(self):
        self.records[3]["payload"]["content"][0]["text"] = "A different task"
        with self.assertRaisesRegex(ValueError, "native_turn_or_prompt_binding"):
            self.project()
        self.records[3]["payload"]["content"][0]["text"] = "Original task"
        self.records[0]["payload"]["id"] = "someone-else"
        with self.assertRaisesRegex(ValueError, "native_session_identity"):
            self.project()

    def test_missing_and_duplicate_outputs_are_rejected(self):
        events, _ = self.project()
        missing = [e for e in events if not(e["kind"] == "tool_result" and e["call_id"] == "web")]
        with self.assertRaisesRegex(ValueError, "unmatched_native"):
            corpus.native_calls(missing)
        duplicate = events + [next(e for e in events if e["kind"] == "tool_result")]
        with self.assertRaisesRegex(ValueError, "duplicate_native_result"):
            corpus.native_calls(duplicate)

    def test_hidden_material_fields_and_credentials_are_not_exportable(self):
        with self.assertRaisesRegex(ValueError, "private_field_in_material"):
            corpus.safe_material({"metadata": {"reasoning_content": "must not ship"}})
        with self.assertRaisesRegex(ValueError, "credential_like_content"):
            corpus.safe_material({"visible": "sk-" + "x" * 36})
        corpus.safe_material({"usage": {"reasoning_output_tokens": 5},
                              "source": "https://example.test/zendesk-support-long-product-page"})

    def test_transitive_relationships_share_existing_family(self):
        catalog = {"cases": [
            {"task": "A", "correlated_with": ["B"]},
            {"task": "B", "correlated_with": ["CAL-02"]},
            {"task": "C", "correlated_with": []}]}
        with patch.object(corpus.history, "family_map", return_value={
                "video-production": "existing-video", "customer-service": "existing-service"}):
            groups = corpus.related_groups(catalog, self.prior)
        self.assertEqual(groups["A"]["family_id"], "existing-video")
        self.assertEqual(groups["B"]["family_id"], "existing-video")
        self.assertNotEqual(groups["C"]["family_id"], "existing-video")
        self.assertFalse(groups["A"]["independence_certified"])

    def setup_export(self):
        ds = self.root / "corpus"
        rd.put_lines(ds / "tasks.jsonl", [{"task_id": "dev-U01", "gold_label": "must remain outside input"}])
        rd.put_json(ds / "inputs/dev-U01.json", {"system": "Review", "user": "Frozen report and sources"})
        return ds

    def test_export_separates_labels_and_refuses_overwrite(self):
        ds, destination = self.setup_export(), self.root / "export.json"
        with patch.object(corpus, "verify_dataset", return_value={"verified": True}):
            result = corpus.export_input(ds, "dev-U01", destination)
            self.assertFalse(result["labels_included"])
            self.assertEqual(set(rd.load_json(destination)), {"system", "user"})
            with self.assertRaisesRegex(ValueError, "export_destination_exists"):
                corpus.export_input(ds, "dev-U01", destination)

    def test_withdrawn_case_and_extra_label_field_cannot_export(self):
        ds = self.setup_export()
        with patch.object(corpus, "verify_dataset", return_value={"verified": True}):
            with self.assertRaisesRegex(ValueError, "unknown_or_withdrawn"):
                corpus.export_input(ds, "formal-F11", self.root / "withdrawn.json")
            payload = rd.load_json(ds / "inputs/dev-U01.json")
            payload["grading_labels"] = {"expected": "answer"}
            (ds / "inputs/dev-U01.json").write_bytes(rd.encoded(payload))
            with self.assertRaisesRegex(ValueError, "labels_or_extra_fields"):
                corpus.export_input(ds, "dev-U01", self.root / "leak.json")

if __name__ == "__main__":
    unittest.main()
