"""Self-contained, proprietary evaluation releases. Holdouts never leave this path."""
from __future__ import annotations
import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path
from .core import read, digest, grade, reference_policy, write_new
from .taskpacks import validate_task

RUNNER = r'''"""Licensed local evaluation client. All rights reserved."""
import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

def verify(folder):
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["files"].items():
        path = (folder / name).resolve()
        path.relative_to(folder.resolve())
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Release file changed: " + name)
    return manifest

def run(task, command, steps, seconds):
    seen, counts, events, answer = [], {}, [], None
    deadline = time.monotonic() + seconds
    terminal = "step_budget_exhausted"
    for step in range(steps):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            terminal = "time_budget_exhausted"
            break
        try:
            response = subprocess.run(command, input=json.dumps({
                "task": task["public"], "observations": seen}), shell=False,
                capture_output=True, text=True, encoding="utf-8", timeout=remaining)
            if response.returncode or len(response.stdout) > 65536:
                raise ValueError("bad_command_response")
            action = json.loads(response.stdout)
            if not isinstance(action, dict):
                raise ValueError("action_not_object")
        except (ValueError, OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
            terminal = type(exc).__name__
            break
        events.append({"action": action})
        if action.get("tool") == "submit_answer":
            answer = action
            terminal = "submitted"
            break
        source = action.get("source_id")
        if action.get("tool") != "fetch_source" or not isinstance(source, str) or source not in task["environment"]:
            terminal = "disallowed_action"
            break
        config = task["environment"][source]
        count = counts.get(source, 0)
        status = config["responses"][min(count, len(config["responses"]) - 1)]
        counts[source] = count + 1
        result = {"source_id": source, "status": status, "attempt": count + 1}
        if status == 200:
            result["document"] = config["document"]
        seen.append(result)
        events.append({"observation": result})
    if task.get("profile") == "research-evidence-v1":
        from research_runtime import grade
        return {"task_id": task["task_id"], "family_id": task["family_id"],
                **grade(task, answer, seen), "terminal_reason": terminal, "events": events}
    failures = []
    passed = None
    if answer is not None:
        actual, expected = answer.get("answer"), task["oracle"]["answer"]
        mismatch = (json.dumps(actual, sort_keys=True) != json.dumps(expected, sort_keys=True)
                    if task.get("grading_contract") == "closed-facts-v2" else actual != expected)
        if mismatch:
            failures.append("incorrect_answer")
        if answer.get("verdict") != task["oracle"]["verdict"]:
            failures.append("wrong_evidence_decision")
        evidence = answer.get("evidence_ids", [])
        if not isinstance(evidence, list) or not all(isinstance(x, str) for x in evidence):
            failures.append("invalid_evidence_ids")
            evidence = []
        observed = {x["source_id"] for x in seen if x["status"] == 200}
        if set(evidence) - observed:
            failures.append("unobserved_evidence")
        if answer.get("verdict") == "answered" and not evidence:
            failures.append("unsupported_answer")
        if answer.get("verdict") == "insufficient_evidence":
            for source in task["public"]["source_ids"]:
                states = [x["status"] for x in seen if x["source_id"] == source]
                if not states or states[-1] != 404 or 200 in states:
                    failures.append("unverified_source_unavailability")
        passed = not failures
    return {"task_id": task["task_id"], "family_id": task["family_id"],
            "passed": passed, "outcome": "not_assessed" if passed is None else "pass" if passed else "fail",
            "terminal_reason": terminal, "failure_codes": failures, "events": events}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-steps", type=int, default=5)
    parser.add_argument("--max-seconds", type=float, default=30)
    args = parser.parse_args()
    if not 1 <= args.max_steps <= 100 or not 0 < args.max_seconds <= 3600:
        parser.error("Invalid run limits")
    folder = Path(__file__).resolve().parent
    manifest = verify(folder)
    command = json.loads(args.agent_config.read_text(encoding="utf-8-sig"))["argv"]
    if not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command):
        parser.error("argv must be a nonempty string array")
    tasks = json.loads((folder / "tasks.json").read_text(encoding="utf-8"))
    rows = [run(t, command, args.max_steps, args.max_seconds) for t in tasks]
    report = {"release_id": manifest["release_id"], "records": rows,
              "summary": {key: sum(row["outcome"] == key for row in rows)
                          for key in ("pass", "fail", "not_assessed")}}
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps(report["summary"]))
if __name__ == "__main__":
    main()
'''

CONTROL = r'''"""Scripted positive control; never label this as model execution."""
import json
import sys
payload = json.load(sys.stdin)
task, obs = payload["task"], payload["observations"]
if task.get("profile") == "research-evidence-v1":
    from research_runtime import reference_action
    action = reference_action(task, obs)
elif not obs or obs[-1]["status"] == 429:
    action = {"tool": "fetch_source", "source_id": task["source_ids"][0]}
elif obs[-1]["status"] == 404:
    action = {"tool": "submit_answer", "verdict": "insufficient_evidence",
              "answer": {}, "evidence_ids": []}
else:
    action = {"tool": "submit_answer", "verdict": "answered",
              "answer": obs[-1]["document"]["facts"], "evidence_ids": [obs[-1]["source_id"]]}
print(json.dumps(action))
'''


def bytes_json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def build_release(root, destination, release_id, audience="internal", task_ids=None):
    if audience not in {"internal", "licensed"}:
        raise ValueError("unknown_release_audience")
    if not isinstance(release_id, str) or not release_id or len(release_id) > 100:
        raise ValueError("invalid_release_id")
    tasks, rejected = [], []
    selected = None if task_ids is None else set(task_ids)
    if selected is not None and (not selected or not all(isinstance(x, str) for x in selected)):
        raise ValueError("invalid_task_selection")
    found = set()
    for path in sorted((Path(root) / "tasks").glob("*.json")):
        if selected is not None and path.stem not in selected:
            continue
        found.add(path.stem)
        try:
            task = validate_task(read(path))
            from .governance import withdrawal_reason
            withdrawn = withdrawal_reason(root, task)
            if withdrawn:
                raise ValueError(withdrawn)
            if task["split"] == "holdout":
                raise ValueError("holdout_reserved")
            purpose = "evaluation_distribution" if audience == "licensed" else "diagnostic"
            if purpose not in task["rights"]["allowed_uses"]:
                raise ValueError("distribution_rights_not_established")
            # Positive/negative grader controls before releasing a task.
            seen = []
            submission = None
            calls = {}
            for step in range(3 * len(task["environment"]) + 1):
                action = reference_policy(task["public"], seen)
                if action["tool"] == "submit_answer":
                    submission = action
                    break
                source = action["source_id"]
                env = task["environment"][source]
                count = calls.get(source, 0)
                calls[source] = count + 1
                status = env["responses"][min(count, len(env["responses"]) - 1)]
                obs = {"source_id": source, "status": status}
                if status == 200:
                    obs["document"] = env["document"]
                seen.append(obs)
            if grade(task, submission, seen)["passed"] is not True:
                raise ValueError("positive_control_failed")
            if grade(task, {"verdict": "answered", "answer": {}, "evidence_ids": []}, [])["passed"] is not False:
                raise ValueError("negative_control_failed")
            tasks.append(task)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            rejected.append({"file": path.name, "reason": str(exc) if isinstance(exc, ValueError)
                             and str(exc).replace("_", "").isalnum() else "invalid_task_structure"})
    if selected is not None and found != selected:
        raise ValueError("missing_selected_tasks")
    if not tasks:
        raise ValueError("no_eligible_tasks")
    files = {"tasks.json": bytes_json(tasks), "evaluate.py": RUNNER.encode(),
             "control_agent.py": CONTROL.encode()}
    if any(task.get("profile") == "research-evidence-v1" for task in tasks):
        files["research_runtime.py"] = Path(__file__).with_name("research_protocol.py").read_bytes()
    notice = ("Internal evaluation only. Redistribution and training are not granted."
              if audience == "internal" else
              "Proprietary evaluation package. Authorized licensees may use this release "
              "for internal evaluation. Redistribution, resale, sublicensing and model training "
              "are not granted. Additional uses require a separate license.")
    files["LICENSE.txt"] = ("Copyright 2026 rrrrrredy. All rights reserved.\n" + notice + "\n").encode()
    card = {
        "release_id": release_id, "audience": audience,
        "task_count": len(tasks), "family_count": len({t["family_id"] for t in tasks}),
        "origins": dict(Counter(t["task_origin"] for t in tasks)),
        "variants": dict(Counter(t["variant"] for t in tasks)),
        "splits": dict(Counter(t["split"] for t in tasks)),
         "model_trajectories_included": False,
        "exclusions_by_reason": dict(Counter(x["reason"] for x in rejected)),
         "oracle": "Versioned deterministic facts and evidence-selection rules.",
        "profiles": dict(Counter(t.get("profile", "closed-facts") for t in tasks)),
        "template_count": len({t["variant"] for t in tasks}),
        "family_boundary": "Source/seed groups can share templates; this count does not establish statistical independence.",
        "limits": [
            "A downloaded suite exposes its answers; it is not a secret benchmark.",
            "The command adapter is for trusted local agents, not an operating-system sandbox.",
            "Selected-source correctness does not establish truth outside the source.",
            "Licensing metadata is an assertion, not proof of third-party rights.",
            "Task snapshots may carry personal data beyond basic credential detection.",
        ],
    }
    files["DATA_CARD.json"] = bytes_json(card)
    files["README.md"] = (
        "# Proprietary evaluation package\n\n"
        "Python 3.10+, standard library only. No factory repository is needed.\n\n"
        "Create a JSON config containing an argv array for your trusted local agent. "
        "The agent reads one JSON object from stdin (task and past observations), "
        "then writes one JSON action to stdout (fetch_source or submit_answer).\n\n"
        "Run: python evaluate.py --agent-config agent.json --output result.json\n\n"
        "For the scripted positive control, use your Python executable and the absolute "
        "path of control_agent.py as argv. Each task starts with empty observations. "
        "Results never overwrite existing files. The runner verifies manifest hashes first.\n\n"
        + notice + "\n"
    ).encode()
    manifest = {"format": "atd-evaluation-v1", "release_id": release_id,
                "files": {k: hashlib.sha256(v).hexdigest() for k, v in files.items()},
                "task_content_sha256": digest(tasks)}
    files["manifest.json"] = bytes_json(manifest)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    import io
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(info, files[name])
    body = buffer.getvalue()
    build_record = {"release_id": release_id, "audience": audience,
                    "sha256": hashlib.sha256(body).hexdigest(), "excluded": rejected,
                    "artifact_path": str(destination.resolve()),
                    "task_ids": [t["task_id"] for t in tasks],
                    "task_hashes": {t["task_id"]: digest(t) for t in tasks}}
    receipt_path = Path(root) / "releases" / (digest([release_id, audience]) + ".json")
    if receipt_path.exists() and read(receipt_path) != build_record:
        raise ValueError("immutable_release_record_conflict")
    if destination.exists():
        if destination.read_bytes() != body:
            raise ValueError("immutable_release_conflict")
    else:
        with destination.open("xb") as stream:
            stream.write(body)
    write_new(receipt_path, build_record)
    return {**card, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}
