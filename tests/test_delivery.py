import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from agentdata.core import generate, read, split_for, write_new
from agentdata.taskpacks import capture_facts, validate_task
from agentdata.release import build_release
from agentdata.pipeline import run_pipeline, run_cycle, reserve_monthly, normalize_config
from agentdata.providers import BudgetExceeded, action_schema


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.json"
        self.source.write_text(json.dumps({"result": {"count": 7, "status": "completed"}}))
        self.rights = {"basis": "test_owned_source", "allowed_uses": ["diagnostic"]}
        self.selectors = {"observed_calls": "/result/count", "batch_status": "/result/status"}
        self.group = next("group-" + str(i) for i in range(100)
                          if split_for("facts-" + __import__("agentdata.core",
                              fromlist=["digest"]).digest("group-" + str(i))[:24]) != "holdout")

    def tearDown(self):
        self.temp.cleanup()

    def intake(self):
        return capture_facts(self.root / "data", self.source, self.selectors,
                             self.group, self.rights)

    def test_capture_lineage_idempotence_and_family_split(self):
        a, b = self.intake(), self.intake()
        self.assertEqual(a, b)
        self.source.write_text(json.dumps({"result": {"count": 8, "status": "completed"}}))
        c = self.intake()
        self.assertEqual(a["family_id"], c["family_id"])
        self.assertNotEqual(a["task_ids"], c["task_ids"])
        self.assertEqual(len(list((self.root / "data/tasks").glob("*.json"))), 6)
        self.assertEqual(a["task_origin"], "artifact_derived")

    def test_real_task_claim_requires_receipt(self):
        with self.assertRaisesRegex(ValueError, "receipt"):
            capture_facts(self.root / "data", self.source, self.selectors,
                          self.group, self.rights, "observed_task")

    def test_selected_credentials_rejected_before_write(self):
        self.source.write_text(json.dumps({"result": {"status": "Bearer super-secret-token"}}))
        with self.assertRaisesRegex(ValueError, "credential"):
            capture_facts(self.root / "data", self.source, {"field": "/result/status"},
                          self.group, self.rights)
        self.assertFalse((self.root / "data/tasks").exists())

    def test_general_answer_schema_contains_types_not_answers(self):
        intake = self.intake()
        task = read(self.root / "data/tasks" / (intake["task_ids"][0] + ".json"))
        schema = action_schema(task["public"])
        self.assertEqual(schema["properties"]["answer"]["anyOf"][1]["properties"],
                         {"observed_calls": {"type": "integer"}, "batch_status": {"type": "string"}})
        self.assertNotIn('"completed"', json.dumps(schema))

    def test_selected_tasks_execute_without_synthetic_generation(self):
        intake = self.intake()
        config = {"task_ids": intake["task_ids"], "policy": "reference"}
        summary = run_pipeline(self.root / "data", config, "selected")
        self.assertEqual(summary["jobs"], 3)
        self.assertEqual(summary["exports"]["diagnostic"]["accepted"], 3)
        self.assertEqual(summary["data_origin"], "selected_tasks")
        self.assertEqual(run_pipeline(self.root / "data", config, "selected"), summary)

    def test_unresolvable_oracle_is_rejected(self):
        intake = self.intake()
        task = read(self.root / "data/tasks" / (intake["task_ids"][0] + ".json"))
        task["oracle"]["answer"]["observed_calls"] = 8
        with self.assertRaisesRegex(ValueError, "oracle"):
            validate_task(task)

    def test_release_replay_is_independent_and_immutable(self):
        self.intake()
        archive = self.root / "pack.zip"
        first = build_release(self.root / "data", archive, "trial-1")
        self.assertEqual(first, build_release(self.root / "data", archive, "trial-1"))
        unpacked = self.root / "unpacked"
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(unpacked)
        config = self.root / "agent.json"
        config.write_text(json.dumps({"argv": [sys.executable, str(unpacked / "control_agent.py")]}))
        result = self.root / "result.json"
        call = subprocess.run([sys.executable, "-B", str(unpacked / "evaluate.py"),
                               "--agent-config", str(config), "--output", str(result)],
                              capture_output=True, text=True, cwd=unpacked)
        self.assertEqual(call.returncode, 0, call.stderr)
        self.assertEqual(read(result)["summary"], {"pass": 3, "fail": 0, "not_assessed": 0})
        with self.assertRaisesRegex(ValueError, "immutable"):
            build_release(self.root / "data", archive, "trial-2")

    def test_release_excludes_holdouts_and_requires_distribution_rights(self):
        generate(self.root / "data", families=25, seed=333)
        archive = self.root / "internal.zip"
        report = build_release(self.root / "data", archive, "internal")
        self.assertNotIn("holdout", report["splits"])
        self.assertGreater(report["exclusions_by_reason"].get("holdout_reserved", 0), 0)
        with zipfile.ZipFile(archive) as bundle:
            card = json.loads(bundle.read("DATA_CARD.json"))
            self.assertNotIn("quarantined", card)
            self.assertNotIn('"file":', json.dumps(card))
            for path in (self.root / "data/tasks").glob("*.json"):
                task = read(path)
                if task["split"] == "holdout":
                    self.assertNotIn(task["task_id"], json.dumps(card))
        private_receipt = read(next((self.root / "data/releases").glob("*.json")))
        self.assertTrue(private_receipt["excluded"])
        with self.assertRaisesRegex(ValueError, "no_eligible"):
            build_release(self.root / "data", self.root / "sale.zip", "sale", "licensed")

    def test_package_tampering_fails_before_agent_execution(self):
        self.intake()
        archive = self.root / "pack.zip"
        build_release(self.root / "data", archive, "trial")
        unpacked = self.root / "unpacked"
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(unpacked)
        (unpacked / "tasks.json").write_text("[]")
        config = self.root / "agent.json"
        config.write_text(json.dumps({"argv": ["never-run-this"]}))
        call = subprocess.run([sys.executable, "-B", str(unpacked / "evaluate.py"),
                               "--agent-config", str(config), "--output", str(self.root / "out.json")],
                              capture_output=True, text=True)
        self.assertNotEqual(call.returncode, 0)
        self.assertIn("Release file changed", call.stderr)
        self.assertFalse((self.root / "out.json").exists())

    def test_monthly_reservations_persist_across_batches(self):
        data = self.root / "data"
        reserve_monthly(data, 2, "batch-a")
        reserve_monthly(data, 2, "batch-b")
        with self.assertRaisesRegex(BudgetExceeded, "monthly"):
            reserve_monthly(data, 2, "batch-c")
        ledger = read(next((data / "budgets").glob("*.json")))
        self.assertEqual(ledger["calls_reserved"], 2)

    def test_scheduled_duplicate_is_idempotent_and_requires_model_cap(self):
        with patch("agentdata.pipeline.time.time", return_value=1900000000):
            a = run_cycle(self.root / "data", {"policy": "reference"})
            b = run_cycle(self.root / "data", {"policy": "reference"})
        self.assertEqual(a, b)
        with self.assertRaisesRegex(ValueError, "monthly"):
            run_cycle(self.root / "data", {"policy": "codex"})

    def test_frozen_task_cannot_bypass_schema_or_origin_checks(self):
        intake = self.intake()
        task = read(self.root / "data/tasks" / (intake["task_ids"][0] + ".json"))
        task["public"]["answer_fields"]["observed_calls"] = "string"
        with self.assertRaisesRegex(ValueError, "schema"):
            validate_task(task)
        task["public"]["answer_fields"]["observed_calls"] = "integer"
        task["task_origin"] = "observed_task"
        with self.assertRaisesRegex(ValueError, "receipt"):
            validate_task(task)

    def test_typed_grading_rejects_boolean_numeric_confusion_in_both_runners(self):
        from agentdata.core import grade
        from agentdata.release import RUNNER
        from agentdata.providers import INSTRUCTION
        import types
        namespace = {"__name__": "test_release"}
        exec(RUNNER, namespace)
        for expected, wrong in [(True, 1), (False, 0)]:
            self.source.write_text(json.dumps({"enabled": expected}))
            receipt = capture_facts(self.root / "data", self.source, {"enabled": "/enabled"},
                                    self.group, self.rights)
            task = read(self.root / "data/tasks" / (receipt["task_ids"][0] + ".json"))
            source = task["public"]["source_ids"][0]
            observation = {"source_id": source, "status": 200,
                           "document": task["environment"][source]["document"]}
            submit = {"tool": "submit_answer", "verdict": "answered",
                      "answer": {"enabled": wrong}, "evidence_ids": [source]}
            self.assertFalse(grade(task, submit, [observation])["passed"])
            self.assertEqual(grade(task, submit, [observation])["version"], "closed-facts-v2")
            responses = [
                subprocess.CompletedProcess([], 0, json.dumps({"tool": "fetch_source", "source_id": source}), ""),
                subprocess.CompletedProcess([], 0, json.dumps(submit), ""),
            ]
            with patch("subprocess.run", side_effect=responses):
                record = namespace["run"](task, ["fixture"], 5, 30)
            self.assertFalse(record["passed"])

    def test_task_path_escape_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_config({"task_ids": ["../private"]})


if __name__ == "__main__":
    unittest.main()
