"""Consumption checks against the immutable v0.10-v0.12 release archives."""
import copy
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import runtime_exports as exports


def read_json(path):
    return json.loads(Path(path).read_bytes())


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_bytes().split(b"\n") if line.strip()]


def write_rows(path, rows):
    Path(path).write_bytes(exports.jsonl(rows))


class RuntimeExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="runtime-export-tests-", dir=ROOT.parent / "_tmp")
        cls.work = Path(cls.temp.name)
        cls.root = cls.work / "consumer"
        cls.config = read_json(ROOT / "configs/runtime-v0.13/exports.json")
        cls.result = exports.build(ROOT / "configs/runtime-v0.13/exports.json", cls.root, source_root=ROOT / "artifacts")
        cls.episodes = read_rows(cls.root / "episodes.jsonl")
        cls.transitions = read_rows(cls.root / "transitions.jsonl")
        cls.archives = {source["source_id"]: zipfile.ZipFile(ROOT / "artifacts" / source["archive"]) for source in cls.config["sources"]}

    @classmethod
    def tearDownClass(cls):
        for archive in cls.archives.values():
            archive.close()
        cls.temp.cleanup()

    def original(self, source, member):
        return json.loads(self.archives[source].read(member))

    def original_rows(self, source, member):
        return [json.loads(line) for line in self.archives[source].read(member).split(b"\n") if line.strip()]

    def test_counts_and_source_use_boundaries(self):
        summary = read_json(self.root / "summary.json")
        self.assertEqual(tuple(summary[key] for key in ("episodes", "transitions", "training_transitions", "positive_demonstrations", "eval_tasks")), (19, 242, 57, 4, 2))
        training = read_rows(self.root / "training/rl-transitions.jsonl")
        self.assertEqual(len(training), 57)
        self.assertTrue(all(row["source_id"] == "v0.11" and row["split"] == "train" and row["rights"]["training_eligible"] for row in training))
        self.assertEqual(len({row["transition_id"] for row in self.transitions}), 242)
        repair = [row for row in self.episodes if row["source_id"] in {"v0.10", "v0.12"}]
        self.assertEqual((len(repair), sum(row["transition_count"] for row in repair)), (7, 75))
        self.assertTrue(all(row["split"] == "development" and not row["training_transition_eligible"] for row in repair))

    def test_workspace_public_transition_semantics_are_unchanged(self):
        old = self.original_rows("v0.11", "exports/transitions.jsonl")
        current = [row for row in self.transitions if row["source_id"] == "v0.11"]
        self.assertEqual(len(old), len(current))
        fields = ("step", "split", "origin", "actor_kind", "rights", "training_eligible", "observation", "action", "next_observation", "reward", "terminated", "truncated", "collection_stop_reason", "recording_last_transition", "decision_summary", "original_episode_sha256")
        for prior, row in zip(old, current):
            with self.subTest(task=row["task_id"], step=row["step"]):
                self.assertEqual(prior["episode_id"], row["task_id"])
                self.assertEqual({key: prior[key] for key in fields}, {key: row[key] for key in fields})

    def test_real_recovery_and_only_preceding_public_history_are_preserved(self):
        rows = [row for row in self.transitions if row["source_id"] == "v0.12"]
        self.assertEqual(len(rows), 13)
        self.assertEqual(rows[5]["next_observation"]["status"], 412)
        self.assertEqual(rows[5]["next_observation"]["error"], "read_current_worker")
        self.assertEqual(rows[6]["action"]["tool"], "read")
        self.assertEqual(rows[7]["action"]["tool"], "patch")
        self.assertEqual(rows[9]["action"]["tool"], "test")
        self.assertTrue(rows[9]["next_observation"]["test"]["passed"])
        self.assertEqual((rows[-1]["reward"], rows[-1]["terminated"], rows[-1]["truncated"]), (1, True, False))
        for row in rows:
            request = exports.history(self.root, row["transition_id"])
            preceding = rows[:row["step"] - 1]
            self.assertEqual(request["history"], [{"action": prior["action"], "observation": prior["next_observation"]} for prior in preceding])
            self.assertEqual(request["initial_observation"], rows[0]["observation"])
            self.assertEqual(request, self.original("v0.12", row["public_request_ref"]["member"]))

    def test_public_observations_and_requests_exclude_evaluator_state(self):
        forbidden = {"private_cases", "reference_code", "control_codes", "final_state", "grade"}
        def check_keys(value):
            if isinstance(value, dict):
                self.assertFalse(forbidden.intersection(value))
                for child in value.values():
                    check_keys(child)
            elif isinstance(value, list):
                for child in value:
                    check_keys(child)
        for row in self.transitions:
            with self.subTest(transition=row["transition_id"]):
                check_keys(row["observation"])
                check_keys(row["next_observation"])
                request = self.original(row["source_id"], row["public_request_ref"]["member"])
                check_keys(request)
        episode = next(row for row in self.episodes if row["source_id"] == "v0.12")
        deliverable = episode["deliverables"][0]
        self.assertEqual(deliverable["kind"], "json_pointer")
        self.assertEqual(deliverable["json_pointer"], "/final_state/code")
        original = self.original("v0.12", deliverable["ref"]["member"])
        self.assertEqual(deliverable["sha256"], hashlib.sha256(original["final_state"]["code"].encode()).hexdigest())

    def copied_export(self, name):
        target = self.work / name
        shutil.copytree(self.root, target, ignore=shutil.ignore_patterns("sources"))
        (target / "sources").mkdir()
        # Frozen source ZIPs are read-only inputs; share them without changing their bytes.
        for source in (self.root / "sources").iterdir():
            os.link(source, target / "sources" / source.name)
        return target

    def rehash(self, root):
        path = root / "manifest.json"
        manifest = read_json(path)
        manifest["files"] = {item.relative_to(root).as_posix(): hashlib.sha256(item.read_bytes()).hexdigest() for item in sorted(root.rglob("*")) if item.is_file() and item.name != "manifest.json"}
        path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    def test_rehashed_semantic_changes_are_rejected(self):
        roundtrip = self.copied_export("canonical-roundtrip")
        write_rows(roundtrip / "transitions.jsonl", read_rows(roundtrip / "transitions.jsonl"))
        self.rehash(roundtrip)
        self.assertTrue(exports.verify(roundtrip)["passed"])
        mutations = {
            "action": lambda rows: rows[0]["action"].update(tool="submit"),
            "next_observation": lambda rows: rows[0]["next_observation"].update(status=299),
            "reward": lambda rows: rows[0].update(reward=1),
            "terminated": lambda rows: rows[0].update(terminated=True),
            "truncated": lambda rows: rows[0].update(truncated=True),
            "split_rights": lambda rows: (rows[0].update(split="train", training_eligible=True), rows[0]["rights"].update(training_eligible=True)),
            "request_reference": lambda rows: rows[0].update(public_request_ref=copy.deepcopy(rows[1]["public_request_ref"])),
        }
        for name, mutate in mutations.items():
            with self.subTest(change=name):
                root = self.copied_export("tamper-" + name)
                rows = read_rows(root / "transitions.jsonl")
                mutate(rows)
                write_rows(root / "transitions.jsonl", rows)
                self.rehash(root)
                with self.assertRaises(ValueError):
                    exports.verify(root)
        with self.subTest(change="final_code_reference"):
            root = self.copied_export("tamper-final-code")
            rows = read_rows(root / "episodes.jsonl")
            current = next(row for row in rows if row["source_id"] == "v0.12")
            prior = next(row for row in rows if row["source_id"] == "v0.10")
            current["deliverables"][0]["ref"] = copy.deepcopy(prior["episode_ref"])
            write_rows(root / "episodes.jsonl", rows)
            self.rehash(root)
            with self.assertRaises(ValueError):
                exports.verify(root)

    def test_external_collection_stop_does_not_invent_environment_terminal(self):
        # An explicitly hypothetical stop on an observed checkpoint tests projection only.
        # It is never saved as another actual model execution or training sample.
        source = next(item for item in self.config["sources"] if item["source_id"] == "v0.12")
        row = copy.deepcopy(self.original_rows("v0.12", "model/episodes.jsonl")[0])
        task = self.original_rows("v0.12", "batch/tasks.jsonl")[0]
        scenario = self.original("v0.12", "batch/" + task["scenario"])
        original = self.original("v0.12", "model/" + row["path"])
        run = copy.deepcopy(self.original("v0.12", "model/episodes/" + row["task_id"] + "/checkpoints/003.json"))
        run.update(capture_refs=copy.deepcopy(original["capture_refs"][:3]), stop_reason="batch_call_budget_exhausted", model_identity=original["model_identity"], evaluation_mode=original["evaluation_mode"])
        row.update(model_calls=3, complete=False, reward=0, stop_reason=run["stop_reason"])
        archive = exports.Archive(ROOT / "artifacts" / source["archive"], source["sha256"])
        episode, transitions, evaluation = exports.project_episode(source["source_id"], archive, row, task, scenario, run)
        self.assertEqual(len(transitions), 3)
        self.assertFalse(episode["complete"])
        self.assertFalse(episode["positive_demonstration_eligible"])
        self.assertIsNone(evaluation)
        self.assertTrue(transitions[-1]["recording_last_transition"])
        self.assertEqual(transitions[-1]["collection_stop_reason"], "batch_call_budget_exhausted")
        self.assertFalse(any(item["terminated"] or item["truncated"] for item in transitions))


if __name__ == "__main__":
    unittest.main()
