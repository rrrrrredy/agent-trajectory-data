"""Read-only consumer projections of pinned repair and workspace release archives."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

VERSION = "runtime-consumer-1"
ENVIRONMENTS = {"research-repair-1", "research-workspace-1"}


def check(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def read(path):
    return json.loads(Path(path).read_bytes())


def rows(data):
    return [json.loads(line) for line in data.split(b"\n") if line.strip()]


def jsonl(values):
    return "".join(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n" for value in values).encode("utf-8")


def safe_member(name):
    check(isinstance(name, str) and bool(name) and "\\" not in name and ":" not in name, "unsafe_archive_path")
    path = PurePosixPath(name)
    check(not path.is_absolute() and all(part not in {"", ".", ".."} for part in name.split("/")), "unsafe_archive_path")
    check(path.as_posix() == name, "unsafe_archive_path")
    return path


class Archive:
    """A pinned release; reading members never imports its executable code."""

    def __init__(self, path, expected_sha256):
        self.path = Path(path)
        check(sha(self.path.read_bytes()) == expected_sha256, "source_archive_changed:" + self.path.name)
        self.members = {}
        with zipfile.ZipFile(self.path) as archive:
            for item in archive.infolist():
                safe_member(item.filename)
                check(not item.is_dir() and not stat.S_ISLNK(item.external_attr >> 16), "unsupported_archive_member")
                check(item.filename not in self.members, "duplicate_archive_member")
                self.members[item.filename] = archive.read(item)
        manifest = self.json("manifest.json")
        actual = {name: sha(data) for name, data in self.members.items() if name != "manifest.json"}
        check(manifest["files"] == actual, "source_manifest_changed:" + self.path.name)

    def data(self, member):
        safe_member(member)
        check(member in self.members, "source_member_missing:" + member)
        return self.members[member]

    def json(self, member):
        return json.loads(self.data(member))

    def rows(self, member):
        return rows(self.data(member))

    def ref(self, member):
        return {"archive": "sources/" + self.path.name, "member": member, "sha256": sha(self.data(member))}


def validate_config(config):
    check(set(config) == {"version", "dataset_version", "sources"} and config["version"] == VERSION, "unsupported_consumer_config")
    check(isinstance(config["dataset_version"], str) and bool(config["dataset_version"]), "invalid_dataset_version")
    check(isinstance(config["sources"], list) and bool(config["sources"]), "sources_required")
    ids, names = set(), set()
    for source in config["sources"]:
        check(set(source) == {"source_id", "archive", "sha256"}, "invalid_source_config")
        check(isinstance(source["source_id"], str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", source["source_id"]), "invalid_source_id")
        name = source["archive"]
        safe_member(name)
        check("/" not in name and name.endswith(".zip"), "invalid_source_archive")
        check(isinstance(source["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", source["sha256"]), "invalid_source_digest")
        check(source["source_id"] not in ids and name not in names, "duplicate_source")
        ids.add(source["source_id"])
        names.add(name)


def exclusion_reason(split, rights, reward=None):
    if split == "test":
        return "test_family"
    if split == "development":
        return "development_family" if rights.get("training_eligible") is True else "source_restricted_development"
    if rights.get("training_eligible") is not True:
        return "source_not_training_eligible"
    return "unsuccessful_or_incomplete" if reward is not None and reward != 1 else None


def project_episode(source_id, archive, row, task, scenario, run):
    """Project one complete recorded index row, including failures and external stops."""
    task_id = row["task_id"]
    check(task_id == task["task_id"] == scenario["task_id"] == run["task_id"], "task_binding_changed")
    check(run["environment_version"] == scenario["version"] and scenario["version"] in ENVIRONMENTS, "unsupported_environment")
    check(row["split"] == scenario["split"] == task["split"] and row["split"] in {"train", "test", "development"}, "split_changed")
    check(row["family_id"] == task["family_id"] == scenario["family_id"], "family_changed")
    check(row["complete"] == run["complete"] and row["reward"] == run["grade"]["reward"] and row["stop_reason"] == run["stop_reason"], "episode_index_changed")
    check(row["actor_kind"] == run["actor_kind"] == "isolated_model_cli", "model_actor_changed")
    check(task["rights"] == scenario["rights"] and task["origin"] == scenario["origin"], "source_rights_changed")
    episode_ref = archive.ref("model/" + row["path"])
    episode_id = source_id + "/" + task_id
    rights, split = scenario["rights"], row["split"]
    eligible = split == "train" and rights.get("training_eligible") is True
    positive = eligible and row["reward"] == 1
    completed = []
    check(row["model_calls"] == len(run["capture_refs"]), "model_call_count_changed")
    for ref in run["capture_refs"]:
        member = "model/" + ref["path"] + "/capture.json"
        check(sha(archive.data(member)) == ref["capture_sha256"], "capture_changed")
        capture = archive.json(member)
        if capture["status"] == "completed":
            completed.append((ref, capture))
    check(len(completed) == len(run["events"]), "transition_capture_count_changed")
    transitions = []
    observed = run["initial_observation"]
    for position, (event, (ref, capture)) in enumerate(zip(run["events"], completed), 1):
        check(event["step"] == position and event["action"] == capture["action"], "transition_action_changed")
        last = position == len(run["events"])
        transitions.append({
            "transition_id": episode_id + "/" + str(position).zfill(4),
            "source_id": source_id, "episode_id": episode_id, "task_id": task_id,
            "step": position, "environment_version": scenario["version"],
            "split": split, "origin": scenario["origin"], "actor_kind": run["actor_kind"],
            "rights": copy.deepcopy(rights), "training_eligible": eligible,
            "observation": copy.deepcopy(observed), "action": copy.deepcopy(event["action"]),
            "next_observation": copy.deepcopy(event["observation"]), "reward": event["reward"],
            "terminated": event["terminated"], "truncated": event["truncated"],
            "recording_last_transition": last,
            "collection_stop_reason": run["stop_reason"] if last else None,
            "decision_summary": capture["decision_summary"],
            "public_request_ref": archive.ref("model/" + ref["path"] + "/request.json"),
            "original_episode_sha256": episode_ref["sha256"],
        })
        observed = event["observation"]
    if scenario["version"] == "research-repair-1":
        deliverables = [{"kind": "json_pointer", "ref": episode_ref, "json_pointer": "/final_state/code", "sha256": sha(run["final_state"]["code"].encode("utf-8"))}]
    else:
        deliverables = [{"kind": "file", "ref": archive.ref("model/episodes/" + task_id + "/deliverables/" + name)} for name in scenario["documents"]["brief"]["body"]["artifact_ids"]]
    episode = {
        "source_id": source_id, "episode_id": episode_id, "task_id": task_id,
        "family_id": row["family_id"], "source_group_id": task["source_group_id"],
        "environment_version": scenario["version"], "split": split, "origin": scenario["origin"],
        "actor_kind": run["actor_kind"], "model_identity": run["model_identity"], "rights": copy.deepcopy(rights),
        "complete": row["complete"], "reward": row["reward"], "terminal_status": run["final_state"]["ticket"]["status"],
        "stop_reason": run["stop_reason"], "transition_count": len(transitions), "model_calls": row["model_calls"],
        "training_transition_eligible": eligible, "positive_demonstration_eligible": positive,
        "rl_exclusion_reason": exclusion_reason(split, rights),
        "positive_demonstration_exclusion_reason": exclusion_reason(split, rights, row["reward"]),
        "episode_ref": episode_ref, "scenario_ref": archive.ref("batch/" + task["scenario"]),
        "deliverables": deliverables,
    }
    evaluation = None
    if split == "test":
        evaluation = {"source_id": source_id, "task_id": task_id, "episode_id": episode_id,
                      "family_id": row["family_id"], "source_group_id": task["source_group_id"],
                      "environment_version": scenario["version"], "max_steps": scenario["max_steps"],
                      "seed": run["seed"], "scenario_ref": episode["scenario_ref"],
                      "grader_ref": archive.ref("task-entrypoints/" + task_id + "/tests/verify.py"),
                      "policy_surface": "reset/step public observations only; scenario, solutions and grader stay evaluator-side"}
    return episode, transitions, evaluation


def counts(episodes, transitions, evaluation):
    return {"episodes": len(episodes), "transitions": len(transitions),
            "training_transitions": sum(row["training_eligible"] for row in transitions),
            "positive_demonstrations": sum(row["positive_demonstration_eligible"] for row in episodes),
            "verified_ready_episodes": sum(row["reward"] == 1 and row["terminal_status"] == "ready" for row in episodes),
            "verified_blocked_episodes": sum(row["reward"] == 1 and row["terminal_status"] == "blocked" for row in episodes),
            "eval_tasks": len(evaluation)}


def derive(config, archives):
    episodes, transitions, evaluation, by_source = [], [], [], {}
    for source in config["sources"]:
        source_id = source["source_id"]
        archive = archives[source_id]
        check(source_id == "v" + archive.json("batch/config.json")["dataset_version"], "source_version_changed")
        task_rows = archive.rows("batch/tasks.jsonl")
        tasks = {row["task_id"]: row for row in task_rows}
        check(len(tasks) == len(task_rows), "duplicate_task")
        selected = archive.rows("model/episodes.jsonl")
        check(len({row["task_id"] for row in selected}) == len(selected), "duplicate_episode")
        local_episodes, local_transitions, local_evaluation = [], [], []
        for row in selected:
            check(row["task_id"] in tasks, "unknown_episode_task")
            task = tasks[row["task_id"]]
            scenario = archive.json("batch/" + task["scenario"])
            run = archive.json("model/" + row["path"])
            episode, steps, selected_eval = project_episode(source_id, archive, row, task, scenario, run)
            local_episodes.append(episode)
            local_transitions.extend(steps)
            if selected_eval is not None:
                local_evaluation.append(selected_eval)
        episodes.extend(local_episodes)
        transitions.extend(local_transitions)
        evaluation.extend(local_evaluation)
        by_source[source_id] = counts(local_episodes, local_transitions, local_evaluation)
    summary = {"version": VERSION, "dataset_version": config["dataset_version"], **counts(episodes, transitions, evaluation),
               "by_source": by_source, "new_model_calls": 0, "new_model_episodes": 0, "new_tasks": 0, "new_source_groups": 0,
               "contract": "Projection of existing published actual model episodes. Public observations are partial; the original request preserves the complete public history at each decision. Source rights and family splits are unchanged. Failed eligible train episodes may supply RL transitions; positive demonstrations also require reward 1. External collection stops do not alter environment terminal flags. Evaluator snapshots are excluded from transitions. Replay uses each pinned archive's own environment and grader."}
    evaluation_doc = {"tasks": evaluation, "selection": "existing_test_split_only",
                      "new_blind_evaluation": False,
                      "boundary": "Existing development evaluation selection; repackaging creates no new held-out tasks or blind benchmark."}
    return {"episodes.jsonl": jsonl(episodes), "transitions.jsonl": jsonl(transitions),
            "training/rl-transitions.jsonl": jsonl([row for row in transitions if row["training_eligible"]]),
            "evaluation.json": encoded(evaluation_doc), "summary.json": encoded(summary)}


def load_archives(config, root):
    validate_config(config)
    return {source["source_id"]: Archive(Path(root) / source["archive"], source["sha256"]) for source in config["sources"]}


def file_hashes(root):
    root = Path(root)
    return {path.relative_to(root).as_posix(): sha(path.read_bytes()) for path in sorted(root.rglob("*"))
            if path.is_file() and path != root / "manifest.json"}


def build(config_path, output, source_root=None):
    config_path, root = Path(config_path).resolve(), Path(output).resolve()
    check(not root.exists(), "output_exists")
    config = read(config_path)
    archives = load_archives(config, Path(source_root).resolve() if source_root is not None else config_path.parent)
    projections = derive(config, archives)
    root.mkdir(parents=True)
    (root / "sources").mkdir()
    for source in config["sources"]:
        shutil.copyfile(archives[source["source_id"]].path, root / "sources" / source["archive"])
    for name, content in {"config.json": encoded(config), **projections}.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    shutil.copyfile(Path(__file__), root / "runtime_exports.py")
    (root / "manifest.json").write_bytes(encoded({"files": file_hashes(root)}))
    return {"passed": True, **json.loads(projections["summary.json"])}


def verify(output):
    root = Path(output).resolve()
    check(read(root / "manifest.json")["files"] == file_hashes(root), "consumer_files_changed")
    config = read(root / "config.json")
    projections = derive(config, load_archives(config, root / "sources"))
    for name, content in projections.items():
        check((root / name).read_bytes() == content, "consumer_projection_changed:" + name)
    return {"passed": True, **json.loads(projections["summary.json"])}


def history(output, transition_id):
    root = Path(output).resolve()
    verify(root)
    selected = [row for row in rows((root / "transitions.jsonl").read_bytes()) if row["transition_id"] == transition_id]
    check(len(selected) == 1, "transition_not_found")
    ref = selected[0]["public_request_ref"]
    source = next(source for source in read(root / "config.json")["sources"] if "sources/" + source["archive"] == ref["archive"])
    archive = Archive(root / ref["archive"], source["sha256"])
    check(sha(archive.data(ref["member"])) == ref["sha256"], "public_request_changed")
    return archive.json(ref["member"])


def replay(output, work):
    root, work = Path(output).resolve(), Path(work).resolve()
    result = verify(root)
    check(not work.exists() and not work.is_relative_to(root) and not root.is_relative_to(work), "fresh_external_replay_directory_required")
    config = read(root / "config.json")
    archives = load_archives(config, root / "sources")
    checks = []
    work.mkdir(parents=True)
    for source in config["sources"]:
        target = work / source["source_id"]
        target.mkdir()
        for name, data in archives[source["source_id"]].members.items():
            path = target.joinpath(*safe_member(name).parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        process = subprocess.run([sys.executable, "-X", "utf8", "-B", str(target / "runtime_release.py"), "verify", str(target)],
                                 cwd=target, text=True, encoding="utf-8", capture_output=True, timeout=180)
        receipt = {"source_id": source["source_id"], "exit_code": process.returncode, "stdout": process.stdout, "stderr": process.stderr}
        checks.append(receipt)
        (work / "replay.json").write_bytes(encoded({"passed": all(item["exit_code"] == 0 for item in checks), "complete": len(checks) == len(config["sources"]), "checks": checks}))
        check(process.returncode == 0, "source_replay_failed:" + source["source_id"])
    return {"passed": True, "source_replays": len(checks), "episodes": result["episodes"], "transitions": result["transitions"], "new_model_calls": 0, "checks": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("build")
    create.add_argument("config")
    create.add_argument("output")
    create.add_argument("--source-root")
    for name in ("verify", "history", "replay"):
        command = commands.add_parser(name)
        command.add_argument("output")
        if name == "history":
            command.add_argument("transition_id")
        if name == "replay":
            command.add_argument("--work", required=True)
    args = parser.parse_args()
    if args.command == "build":
        result = build(args.config, args.output, args.source_root)
    elif args.command == "verify":
        result = verify(args.output)
    elif args.command == "history":
        result = history(args.output, args.transition_id)
    else:
        result = replay(args.output, args.work)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
