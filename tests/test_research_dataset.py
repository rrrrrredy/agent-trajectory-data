"""Regression tests for provenance, real failure retention and replay integrity."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/research_dataset.py"
spec = importlib.util.spec_from_file_location("research_dataset", SCRIPT)
dataset = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dataset)


class ResearchDatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.output = self.root / "source", self.root / "dataset"
        bundle = self.source / dataset.BUNDLE
        dataset.put(self.source / "LICENSE", b"MIT fixture license\n")
        for name in dataset.REPORTS:
            report = "Report " + name + "\nLegal Unicode separator: \u2028 within a JSON string.\n"
            brief = "Review only the supplied " + name + " report.\n"
            original = {"system": "Review this text.", "user": brief + "\n" + report}
            dataset.put_json(bundle / "inputs" / (name + ".json"), original)
            for filename, content in (("original-request.md", "Original request\n"),
                                      ("repair-brief.md", brief),
                                      ("before-model-diagnostics.md", report),
                                      ("data/source_registry.csv", "source_id,title\nS1,Source " + name + "\n"),
                                      ("data/claims_registry.csv", "claim_id,claim,source_ids\nC1,Claim " + name + ",S1\n")):
                dataset.put(bundle / "reports" / name / filename, content.encode("utf-8"))
            for provider in dataset.PROVIDERS:
                request = {"model": provider + "-fixture",
                           "messages": [{"role": "system", "content": original["system"]},
                                        {"role": "user", "content": original["user"]}]}
                failed = name == "video-production" and provider == "kimi"
                parsed = None if failed else {"verdict": "usable_with_limits",
                                               "findings": [], "external_facts_verified": False}
                response = {"model_returned": request["model"], "parsed": parsed,
                            "content": "" if failed else json.dumps(parsed),
                            "finish_reason": "length" if failed else "stop",
                            "usage": {"prompt_tokens": 2, "completion_tokens": 1},
                            "input_sha256": dataset.normalized_hash(bundle / "inputs" / (name + ".json")),
                            "external_fact_check": False}
                dataset.put_json(bundle / "requests" / provider / (name + ".json"), request)
                dataset.put_json(bundle / "results" / provider / (name + ".json"), response)
        files = {p.relative_to(bundle).as_posix(): dataset.normalized_hash(p)
                 for p in bundle.rglob("*") if p.is_file()}
        dataset.put_json(bundle / "bundle-manifest.json", {"files": files})
        with patch.object(dataset.subprocess, "check_output", return_value="fixture-revision\n"):
            dataset.build_dataset(self.source, self.output)

    def reseal(self, relative):
        manifest = dataset.load_json(self.output / "manifest.json")
        manifest["files"][relative] = dataset.sha((self.output / relative).read_bytes())
        (self.output / "manifest.json").write_bytes(dataset.encoded(manifest))

    def replace_lines(self, relative, rows):
        (self.output / relative).write_bytes(b"".join(
            json.dumps(row, ensure_ascii=False).encode("utf-8") + b"\n" for row in rows))
        self.reseal(relative)

    def test_complete_pilot_and_idempotent_rebuild(self):
        result = dataset.verify_dataset(self.output)
        self.assertEqual(result["observed_runtime_status"], {"completed": 3, "output_limit": 1})
        self.assertEqual(result["scripted_outcomes"], {"pass": 12, "fail": 4})
        self.assertEqual(result["training_records"], 0)
        before = (self.output / "manifest.json").read_bytes()
        dataset.build_dataset(self.source, self.output)
        self.assertEqual(before, (self.output / "manifest.json").read_bytes())

    def test_truncated_real_response_cannot_be_relabelled_complete(self):
        episodes = dataset.load_lines(self.output / "episodes.jsonl")
        failed = next(row for row in episodes if row["evaluation"].get("runtime_status") == "output_limit")
        failed["evaluation"]["runtime_status"] = "completed"
        self.replace_lines("episodes.jsonl", episodes)
        with self.assertRaisesRegex(ValueError, "observed_metadata_or_label_mismatch"):
            dataset.verify_dataset(self.output)

    def test_first_failure_cannot_be_silently_dropped(self):
        episodes = dataset.load_lines(self.output / "episodes.jsonl")
        episodes = [row for row in episodes if row["evaluation"].get("runtime_status") != "output_limit"]
        self.replace_lines("episodes.jsonl", episodes)
        with self.assertRaisesRegex(ValueError, "missing_or_repeated_episode"):
            dataset.verify_dataset(self.output)

    def test_rehashed_forged_tool_result_is_rejected(self):
        episodes = dataset.load_lines(self.output / "episodes.jsonl")
        episode = next(row for row in episodes if row["actor_kind"] == "scripted_policy")
        events = dataset.load_lines(self.output / episode["events_path"])
        events[1]["payload"]["rows"][0]["source_id"] = "FORGED"
        self.replace_lines(episode["events_path"], events)
        with self.assertRaisesRegex(ValueError, "forged_or_mismatched_observation"):
            dataset.verify_dataset(self.output)

    def test_seen_synthetic_child_cannot_move_to_holdout(self):
        tasks = dataset.load_lines(self.output / "tasks.jsonl")
        next(row for row in tasks if row["task_origin"] == "synthetic")["split"] = "holdout"
        self.replace_lines("tasks.jsonl", tasks)
        with self.assertRaisesRegex(ValueError, "seen_source_must_stay_development"):
            dataset.verify_dataset(self.output)

    def test_input_binding_is_checked_beyond_file_hashes(self):
        tasks = dataset.load_lines(self.output / "tasks.jsonl")
        task = next(row for row in tasks if row["profile"] == "archived-review-v1")
        episodes = dataset.load_lines(self.output / "episodes.jsonl")
        episode = next(row for row in episodes if row["task_id"] == task["task_id"])
        path = self.output / episode["request_path"]
        request = dataset.load_json(path)
        request["messages"][1]["content"] = "A different report"
        path.write_bytes(dataset.encoded(request))
        with self.assertRaisesRegex(ValueError, "request_input_binding_mismatch"):
            dataset.verify_review(self.output, task, episode,
                                  dataset.load_lines(self.output / episode["events_path"]))

    def test_jsonl_unicode_separator_does_not_split_records(self):
        path = self.root / "unicode.jsonl"
        dataset.put_lines(path, [{"text": "a\u2028b\u2029c"}, {"text": "next"}])
        self.assertEqual(dataset.load_lines(path), [{"text": "a\u2028b\u2029c"}, {"text": "next"}])

    def test_registry_labels_against_independent_literal_examples(self):
        observations = [
            {"table": "sources", "status": 200, "rows": [{"source_id": "S1"}, {"source_id": "S1"}]},
            {"table": "claims", "status": 200, "rows": [
                {"claim_id": "C1", "source_ids": "S1|SX|SX"},
                {"claim_id": "C2", "source_ids": ""}]}]
        self.assertEqual(dataset.registry_result(observations), {
            "verdict": "inconsistent", "missing_tables": [], "duplicate_source_ids": ["S1"],
            "claims_without_sources": ["C2"],
            "dangling_references": [{"claim_id": "C1", "source_id": "SX"}]})
        observations[0] = {"table": "sources", "status": 404}
        self.assertEqual(dataset.registry_result(observations), {
            "verdict": "insufficient_evidence", "missing_tables": ["sources"],
            "duplicate_source_ids": [], "claims_without_sources": [], "dangling_references": []})

    def test_observation_required_even_when_answer_is_correct(self):
        tasks = dataset.load_lines(self.output / "tasks.jsonl")
        task = next(row for row in tasks if row.get("variant") == "original")
        env = dataset.environment_for(self.output, task)
        evaluation = dataset.grade_registry(
            env, [{"tool": "submit_check", "result": copy.deepcopy(task["oracle"])}], [])
        self.assertEqual(evaluation["failure_type"], "required_table_not_observed")


if __name__ == "__main__":
    unittest.main()
