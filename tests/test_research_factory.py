import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from agentdata.core import read, run_task, quality_decision, split_for, write_new, all_runs, reference_policy
from agentdata.pipeline import run_pipeline
from agentdata.research_protocol import resolve, equal_json, grade
from agentdata.research_tasks import generate_research, validate_research_task
from agentdata.factory import run_factory
from agentdata.training import export_training
from agentdata.release import build_release
from agentdata.providers import INSTRUCTION


class ResearchFactoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "data"

    def task(self, variant="latest_version"):
        seed = next(i for i in range(100) if split_for(f"research-{i}-00000") == "train")
        paths = generate_research(self.root, 1, seed)
        return next(read(p) for p in paths if read(p)["variant"] == variant)

    def source_config(self):
        (self.base / "inbox").mkdir()
        (self.base / "sources").mkdir()
        (self.base / "sources/result.json").write_text(json.dumps({"jobs": 7}))
        (self.base / "inbox/valid.json").write_text(json.dumps({
            "source": "own", "path": "result.json", "source_group": "job-series"}))
        return {"pipeline": {"policy": "reference"}, "inbox": "inbox",
                "sources": {"own": {"root": "sources", "selectors": {"jobs": "/jobs"},
                "rights": {"basis": "test_owned_source", "allowed_uses": ["diagnostic"]}}}}

    def test_all_research_scenarios_pass_reference_and_fail_broken(self):
        tasks = [read(p) for p in generate_research(self.root, 2, 42)]
        self.assertEqual(len(tasks), 20)
        self.assertEqual(len({t["variant"] for t in tasks}), 10)
        for task in tasks:
            good = run_task(self.root, task, "reference", max_steps=8)
            bad = run_task(self.root, task, "broken", max_steps=8)
            self.assertTrue(good["evaluation"]["passed"], task["variant"])
            self.assertFalse(bad["evaluation"]["passed"], task["variant"])
            self.assertEqual(quality_decision(self.root, good)["decision"], "accept")

    def test_known_date_region_authority_and_unit_examples(self):
        public = {"selection": {"region": "CN", "as_of": "2026-09-01", "minimum_authority": 1}}
        fact = {"deployment": "available", "billing_unit": "seat", "price": 101, "period": "year"}
        valid = {"source_id": "official", "authority": "official", "published_at": "2026-09-01",
                 "region": "CN", "facts": fact}
        future = {**valid, "source_id": "future", "published_at": "2026-09-02",
                  "facts": {**fact, "price": 999}}
        wrong_region = {**future, "source_id": "us", "region": "US", "published_at": "2026-08-31"}
        community = {**future, "source_id": "forum", "authority": "community", "published_at": "2026-09-01"}
        result = resolve(public, [valid, future, wrong_region, community])
        self.assertEqual(result, {"verdict": "answered",
            "answer": {"deployment": "available", "billing_unit": "seat", "monthly_price": 8.42},
            "evidence_ids": ["official"]})
        self.assertFalse(equal_json({"price": True}, {"price": 1}))
        self.assertTrue(equal_json({"price": 1}, {"price": 1.0}))

    def test_wrong_citation_and_unread_sources_fail_even_with_right_answer(self):
        task = self.task()
        record = run_task(self.root, task, "reference")
        events = [json.loads(x) for x in (self.root / record["events_path"]).read_text().splitlines()]
        observations = [e["payload"] for e in events if e["event_type"] == "observation"]
        answer = copy.deepcopy(record["submission"])
        answer["evidence_ids"] = [task["public"]["source_ids"][0]]
        self.assertIn("wrong_source_selection", grade(task, answer, observations)["failure_codes"])
        self.assertIn("sources_not_checked", grade(task, record["submission"], observations[1:])["failure_codes"])

    def test_conflicts_missing_fields_and_unavailability_require_abstention(self):
        for variant in ("missing_field", "equal_rank_conflict", "source_unavailable"):
            task = self.task(variant)
            record = run_task(self.root, task, "reference")
            self.assertEqual(record["submission"]["verdict"], "insufficient_evidence")
            self.assertTrue(record["evaluation"]["passed"])

    def test_forged_environment_observation_is_quarantined_even_after_rehash(self):
        task = self.task()
        record = run_task(self.root, task, "reference")
        path = self.root / record["events_path"]
        events = [json.loads(x) for x in path.read_text().splitlines()]
        event = next(e for e in events if e["event_type"] == "observation")
        event["payload"]["document"]["facts"]["price"] += 1000
        path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
        record["events_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertIn("observation_environment_mismatch", quality_decision(self.root, record)["reasons"])

    def test_standalone_multi_source_release_runs_all_scenarios(self):
        self.task()
        archive = self.base / "suite.zip"
        metadata = build_release(self.root, archive, "suite", "licensed")
        self.assertEqual(metadata["task_count"], 10)
        dest = self.base / "unpacked"
        with zipfile.ZipFile(archive) as bundle:
            self.assertIn("research_runtime.py", bundle.namelist())
            self.assertNotIn("research_tasks.py", bundle.namelist())
            bundle.extractall(dest)
        write_new(dest / "agent.json", {"argv": [sys.executable, str(dest / "control_agent.py")]})
        run = subprocess.run([sys.executable, "-B", str(dest / "evaluate.py"),
            "--agent-config", str(dest / "agent.json"), "--output", str(dest / "results.json"),
            "--max-steps", "8"], capture_output=True, text=True, cwd=dest)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(read(dest / "results.json")["summary"]["pass"], 10)

    def test_factory_generates_executes_releases_and_does_not_repeat(self):
        config = {"pipeline": {"policy": "reference", "max_steps": 8},
                  "generators": [{"id": "starter", "profile": "research-evidence-v1", "families": 2, "seed": 42}],
                  "release_audience": "licensed"}
        first = run_factory(self.root, config, self.base)
        self.assertEqual(first["statuses"]["completed"], 1)
        self.assertEqual(len(all_runs(self.root)), 20)
        second = run_factory(self.root, config, self.base)
        self.assertEqual(second["processed_this_tick"], 0)
        self.assertEqual(len(all_runs(self.root)), 20)
        manifest = read(next((self.root / "batches").glob("*/training/manifest.json")))
        self.assertEqual(manifest["sft_records"], 0)

    def test_invalid_input_is_quarantined_without_blocking_valid_input(self):
        config = self.source_config()
        (self.base / "inbox/bad.json").write_text("{broken")
        summary = run_factory(self.root, config, self.base)
        self.assertEqual(summary["statuses"]["completed"], 1)
        self.assertEqual(summary["statuses"]["quarantined"], 1)
        self.assertEqual(run_factory(self.root, config, self.base)["processed_this_tick"], 0)

    def test_source_path_escape_cannot_be_read_or_sent(self):
        config = self.source_config()
        (self.base / "outside.json").write_text('{"secret": "keep private"}')
        (self.base / "inbox/escape.json").write_text(json.dumps({
            "source": "own", "path": "../outside.json", "source_group": "escape"}))
        summary = run_factory(self.root, config, self.base)
        self.assertEqual(summary["statuses"]["quarantined"], 1)
        self.assertNotIn("keep private", (self.root / "factory/state.json").read_text())

    def test_private_intake_defaults_to_no_external_model_send(self):
        config = self.source_config()
        config["pipeline"] = {"policy": "codex", "monthly_model_calls": 8,
                              "provider": {"model": "fixture"}}
        with patch("agentdata.factory.run_pipeline") as execute:
            summary = run_factory(self.root, config, self.base)
        execute.assert_not_called()
        self.assertEqual(summary["statuses"]["quarantined"], 1)
        state = read(self.root / "factory/state.json")
        self.assertEqual(next(iter(state["jobs"].values()))["reason"],
                         "external_model_send_disallowed_for_source")

    def test_failed_submissions_have_bounded_linked_new_attempts(self):
        result = run_pipeline(self.root, {"policy": "broken", "max_attempts_per_task": 3}, "retry")
        self.assertEqual(result["jobs"], 9)
        rows = all_runs(self.root)
        self.assertEqual(len([r for r in rows if r.get("parent_run_id")]), 6)
        self.assertTrue(all(r["evaluation"]["outcome"] == "fail" for r in rows))
        self.assertTrue(all(quality_decision(self.root, r)["decision"] == "accept" for r in rows))

    def test_unassessed_loops_are_not_reissued_as_answer_repairs(self):
        result = run_pipeline(self.root, {"policy": "loop", "max_steps": 2,
                                         "max_attempts_per_task": 3}, "no-retry")
        self.assertEqual(result["jobs"], 3)
        self.assertTrue(all(r["evaluation"]["outcome"] == "not_assessed" for r in all_runs(self.root)))

    def test_recovery_enqueues_completed_failure_once_after_worker_crash(self):
        config = {"policy": "broken", "max_attempts_per_task": 2}
        def crash_after_result(*args, **kwargs):
            run_task(*args, **kwargs)
            raise KeyboardInterrupt("simulated_worker_loss")
        with patch("agentdata.pipeline.run_task", side_effect=crash_after_result):
            with self.assertRaises(KeyboardInterrupt):
                run_pipeline(self.root, config, "crash-retry")
        result = run_pipeline(self.root, config, "crash-retry")
        self.assertEqual(result["jobs"], 6)
        self.assertEqual(result["job_statuses"]["done"], 6)
        self.assertEqual(len([r for r in all_runs(self.root) if r.get("parent_run_id")]), 3)
        self.assertEqual(run_pipeline(self.root, config, "crash-retry"), result)

    def test_model_training_pair_needs_explicit_rights_and_same_task(self):
        task = self.task()
        calls = 0
        def fake_cli(argv, **kwargs):
            nonlocal calls
            if "--version" in argv:
                return subprocess.CompletedProcess(argv, 0, "codex test-fixture", "")
            calls += 1
            payload = json.loads(kwargs["input"][len(INSTRUCTION) + 1:])
            action = ({"tool": "submit_answer", "verdict": "answered", "answer": {}, "evidence_ids": []}
                      if calls == 1 else reference_policy(payload["task"], payload["observations"]))
            events = [
                {"type": "thread.started", "thread_id": "fixture-" + str(calls)},
                {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(action)}},
                {"type": "turn.completed", "usage": {"input_tokens": 100, "cached_input_tokens": 0, "output_tokens": 20}}]
            return subprocess.CompletedProcess(argv, 0, "\n".join(json.dumps(e) for e in events), "")
        config = {"policy": "codex", "task_ids": [task["task_id"]], "max_attempts_per_task": 2,
                  "max_steps": 8, "provider": {"model": "fixture",
                    "output_rights": {"basis": "test_fixture_only", "allowed_uses": ["diagnostic", "sft", "preference"]}}}
        with patch("agentdata.providers.shutil.which", return_value="codex"), patch(
                "agentdata.providers.subprocess.run", side_effect=fake_cli):
            result = run_pipeline(self.root, config, "model-fixture")
        self.assertEqual(result["jobs"], 2)
        export = export_training(self.root, self.base / "training")
        self.assertEqual(export["sft_records"], 1)
        self.assertEqual(export["preference_pairs"], 1)
        pair = json.loads((self.base / "training/preferences.jsonl").read_text())
        self.assertFalse(pair["causal_claim"])
        self.assertNotIn('"oracle"', (self.base / "training/sft.jsonl").read_text())


if __name__ == "__main__":
    unittest.main()
