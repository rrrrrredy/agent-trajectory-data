"""Automated closed-world control pipeline. No human review queue."""
from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "0.1"
VERSIONS = {"generator": "research-facts-v1", "grader": "closed-facts-v1",
            "pipeline": "0.2.0"}
VARIANTS = ("normal", "missing_source", "transient_error")


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    try:
        with path.open("x", encoding="utf-8", newline="\n") as f:
            f.write(body)
    except FileExistsError:
        if read(path) != value:
            raise ValueError(f"Immutable artifact already exists: {path.name}")


def split_for(family_id, seed="atd-split-v1"):
    bucket = int(digest([seed, family_id])[:8], 16) % 100
    return "train" if bucket < 70 else "development" if bucket < 85 else "holdout"


def generate(root, families=8, seed=1):
    if not 1 <= families <= 10000:
        raise ValueError("families must be between 1 and 10000")
    created = []
    for index in range(families):
        family = f"synthetic-{seed}-{index:05d}"
        price = 100 + int(digest([seed, index])[:6], 16) % 1900
        facts = {"deployment": "planned" if index % 2 else "available",
                 "billing_unit": "workspace" if index % 3 else "seat",
                 "monthly_price": price}
        for variant in VARIANTS:
            task_id = f"{family}-{variant}"
            source_id = f"{family}-official"
            task = {
                "schema_version": SCHEMA, "task_id": task_id, "family_id": family,
                "split": split_for(family), "task_origin": "synthetic",
                "source_group": family, "variant": variant, "generator": VERSIONS,
                "rights": {"basis": "repository_generated_synthetic",
                           "allowed_uses": ["diagnostic", "sft"]},
                "public": {
                    "question": "Read the supplied official source and return deployment, "
                                "billing_unit and monthly_price. If the required source is "
                                "unavailable, return insufficient_evidence and no answer. "
                                "Cite only successfully observed source ids.",
                    "source_ids": [source_id],
                    "tools": ["fetch_source", "submit_answer"],
                },
                "environment": {
                    source_id: {
                        "document": {"source_id": source_id,
                                     "title": f"Fictional product {index} official facts",
                                     "facts": facts},
                        "responses": [404] if variant == "missing_source"
                                     else [429, 200] if variant == "transient_error"
                                     else [200],
                    }
                },
                "oracle": {
                    "verdict": "insufficient_evidence" if variant == "missing_source"
                               else "answered",
                    "answer": {} if variant == "missing_source" else facts,
                },
            }
            path = Path(root) / "tasks" / f"{task_id}.json"
            write_new(path, task)
            created.append(path)
    return created


def redact(value):
    if isinstance(value, dict):
        return {k: "[REDACTED]" if re.search(
            r"(?i)^(authorization|api[_-]?key|password|secret|access[_-]?token)$", k)
            else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer [REDACTED]", value)
        value = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "[REDACTED]", value)
        return value
    return value


def reference_policy(public, observations):
    if not observations:
        return {"tool": "fetch_source", "source_id": public["source_ids"][0]}
    last = observations[-1]
    if last["status"] == 429:
        return {"tool": "fetch_source", "source_id": last["source_id"]}
    if last["status"] != 200:
        return {"tool": "submit_answer", "verdict": "insufficient_evidence",
                "answer": {}, "evidence_ids": []}
    return {"tool": "submit_answer", "verdict": "answered",
            "answer": last["document"]["facts"],
            "evidence_ids": [last["source_id"]]}


def invoke_policy(policy, public, observations, command=None, timeout=5):
    if policy == "reference":
        return reference_policy(public, observations)
    if policy == "broken":
        return {"tool": "submit_answer", "verdict": "answered",
                "answer": {"deployment": "available", "billing_unit": "seat",
                           "monthly_price": 0}, "evidence_ids": []}
    if policy == "loop":
        return {"tool": "fetch_source", "source_id": public["source_ids"][0]}
    if policy != "command" or not isinstance(command, list) or not command or not all(
            isinstance(part, str) and part for part in command):
        raise ValueError("command policy requires a trusted nonempty argv list")
    # Only visible task and past observations cross this boundary, never the oracle.
    payload = {"protocol": SCHEMA, "task": public, "observations": observations}
    completed = subprocess.run(command, input=json.dumps(payload, ensure_ascii=False),
                               capture_output=True, text=True, encoding="utf-8",
                               timeout=timeout, shell=False)
    if completed.returncode:
        raise ValueError("command_exit_nonzero")
    if len(completed.stdout) > 65536:
        raise ValueError("command_output_too_large")
    action = json.loads(completed.stdout)
    if not isinstance(action, dict):
        raise ValueError("command_output_not_object")
    return action


def grade(task, submission, observations):
    grader_version = task.get("grading_contract", VERSIONS["grader"])
    if submission is None:
        return {"source": "deterministic", "version": grader_version,
                "outcome": "not_assessed", "passed": None,
                "failure_codes": ["no_submission"]}
    flags = []
    evidence = submission.get("evidence_ids", [])
    if not isinstance(evidence, list) or not all(isinstance(x, str) for x in evidence):
        flags.append("invalid_evidence_ids")
        evidence = []
    seen = {x["source_id"] for x in observations if x["status"] == 200}
    if set(evidence) - seen:
        flags.append("unobserved_evidence")
    if submission.get("verdict") != task["oracle"]["verdict"]:
        flags.append("wrong_evidence_decision")
    actual, expected = submission.get("answer"), task["oracle"]["answer"]
    mismatch = (digest(actual) != digest(expected) if grader_version == "closed-facts-v2"
                else actual != expected)
    if mismatch:
        flags.append("incorrect_answer")
    if submission.get("verdict") == "insufficient_evidence":
        unavailable = set()
        for source_id in task["public"]["source_ids"]:
            statuses = [x["status"] for x in observations if x["source_id"] == source_id]
            if statuses and statuses[-1] == 404 and 200 not in statuses:
                unavailable.add(source_id)
        if not set(task["public"]["source_ids"]).issubset(unavailable):
            flags.append("unverified_source_unavailability")
    if submission.get("verdict") == "answered" and not evidence:
        flags.append("unsupported_answer")
    return {"source": "deterministic", "version": grader_version,
            "outcome": "pass" if not flags else "fail", "passed": not flags,
            "failure_codes": flags}


def run_task(root, task, policy="reference", max_steps=8, max_seconds=30,
             max_tool_retries=2, command=None, provider=None, run_id=None):
    if not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps < 1:
        raise ValueError("max_steps must be a positive integer")
    if not isinstance(max_seconds, (int, float)) or not math.isfinite(max_seconds) or max_seconds <= 0:
        raise ValueError("max_seconds must be finite and positive")
    if not isinstance(max_tool_retries, int) or max_tool_retries < 0:
        raise ValueError("max_tool_retries must be a nonnegative integer")
    if task.get("schema_version") != SCHEMA:
        raise ValueError("unsupported task schema")
    if policy == "codex" and provider is None:
        raise ValueError("codex policy requires a provider and admission budget")
    if run_id is not None and not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ValueError("run_id must be a UUID hex string")
    run_id = run_id or uuid.uuid4().hex
    folder = Path(root) / "runs" / run_id
    folder.mkdir(parents=True, exist_ok=False)
    events_path = folder / "events.jsonl"
    write_new(folder / "task_snapshot.json", task)
    sequence = 0
    previous = None

    def emit(event_type, payload):
        nonlocal sequence, previous
        sequence += 1
        eid = f"{run_id}:{sequence}"
        event = {"schema_version": SCHEMA, "run_id": run_id,
                 "task_id": task["task_id"], "family_id": task["family_id"],
                 "event_id": eid, "parent_event_ids": [previous] if previous else [],
                 "timestamp": now(), "event_type": event_type, "payload": redact(payload)}
        with events_path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
            f.flush()
        previous = eid

    start = time.monotonic()
    observations, calls = [], Counter()
    submission = None
    model_captures = []
    terminal = "step_budget_exhausted"
    emit("run_started", {"policy": policy, "task_hash": digest(task),
                         "max_steps": max_steps, "max_seconds": max_seconds,
                         "visible_task": task["public"],
                         **({"model_config": provider.visible_config} if policy == "codex" else {})})
    for step in range(max_steps):
        remaining = max_seconds - (time.monotonic() - start)
        if remaining <= 0:
            terminal = "time_budget_exhausted"
            break
        try:
            if policy == "codex":
                from .providers import ProviderError, BudgetExceeded
                call_folder = folder / "model_calls" / f"{step + 1:04d}"
                try:
                    action, capture = provider.invoke(
                        task["public"], observations, call_folder, timeout=remaining)
                except BudgetExceeded as exc:
                    terminal = exc.code
                    emit("runner_error", {"reason": terminal})
                    break
                except ProviderError as exc:
                    if exc.capture:
                        reference = {"path": str((call_folder / "capture.json").relative_to(root)),
                                     "sha256": digest(exc.capture)}
                        model_captures.append(exc.capture)
                        emit("model_call", {"capture": reference, "status": exc.capture["status"]})
                    terminal = exc.code
                    emit("runner_error", {"reason": terminal, "remote_request_cancelled": "unknown"})
                    break
                reference = {"path": str((call_folder / "capture.json").relative_to(root)),
                             "sha256": digest(capture)}
                model_captures.append(capture)
                emit("model_call", {"capture": reference, "status": capture["status"]})
            else:
                action = invoke_policy(policy, task["public"], observations, command,
                                       timeout=min(remaining, 5))
            if not isinstance(action, dict):
                raise ValueError("invalid_action")
        except subprocess.TimeoutExpired:
            terminal = "runner_timeout"
            emit("runner_error", {"reason": terminal, "remote_request_cancelled": "unknown"})
            break  # Do not repeat a request with unknown cancellation.
        except (ValueError, OSError, UnicodeError) as exc:
            terminal = "runner_error"
            emit("runner_error", {"reason": str(exc)[:200]})
            break
        emit("action", action)
        tool = action.get("tool")
        if tool == "submit_answer":
            submission = action
            terminal = "submitted"
            break
        if tool != "fetch_source":
            terminal = "disallowed_tool"
            break
        source = action.get("source_id")
        if not isinstance(source, str) or source not in task["environment"]:
            terminal = "disallowed_source"
            break
        config = task["environment"][source]
        if calls[source] > max_tool_retries:
            terminal = "tool_retry_exhausted"
            break
        statuses = config["responses"]
        status = statuses[min(calls[source], len(statuses) - 1)]
        calls[source] += 1
        observation = {"source_id": source, "status": status,
                       "attempt": calls[source]}
        if status == 200:
            observation["document"] = config["document"]
        observations.append(observation)
        emit("observation", observation)
    label = grade(task, submission, observations)
    emit("run_finished", {"terminal_reason": terminal, "evaluation": label})
    result = {
        "schema_version": SCHEMA, "run_id": run_id,
        "task_id": task["task_id"], "family_id": task["family_id"],
        "task_hash": digest(task), "split": split_for(task["family_id"]),
        "task_origin": task["task_origin"], "execution_mode": "closed_world_observed",
        "actor_kind": "model_cli" if policy == "codex" else "external_command" if policy == "command" else "scripted_policy",
        "policy": policy, "coverage": "complete_visible_loop",
        "terminal_reason": terminal, "evaluation": label,
        "rights": task["rights"], "events_path": str(events_path.relative_to(root)),
        "task_snapshot_path": str((folder / "task_snapshot.json").relative_to(root)),
        "events_sha256": hashlib.sha256(events_path.read_bytes()).hexdigest(),
        "submission": submission, "event_count": sequence,
        "elapsed_seconds": round(time.monotonic() - start, 6),
        "usage_status": "unknown" if policy == "command" else "not_applicable",
        "provider_cost": None, "created_at": now(),
    }
    if policy == "codex":
        from .providers import valid_usage
        known = [c["usage"] for c in model_captures if valid_usage(c.get("usage"))]
        result.update(
            model_config=provider.visible_config, output_rights=provider.rights,
            model_identity_basis="requested_configuration",
            model_calls_observed=len(model_captures),
            usage_status=("observed_complete" if known and len(known) == len(model_captures)
                          else "observed_partial" if known else "unknown"),
            token_usage={k: sum(u[k] for u in known) for k in
                         ("input_tokens", "cached_input_tokens", "output_tokens")},
        )
    write_new(folder / "run.json", result)
    return result


def import_workflow(root, source_dir):
    """Import only observed review metadata. Never invent missing author tool events."""
    source_dir = Path(source_dir)
    log = source_dir / "logs" / "review.jsonl"
    reviews = []
    for line in log.read_text(encoding="utf-8-sig").splitlines():
        row = json.loads(line)
        if row.get("record_type") == "model_review":
            reviews.append({k: row.get(k) for k in (
                "attempt_id", "status", "reviewer_id", "model", "scope",
                "artifact_sha256", "execution_id", "report_verdict")})
    family = "workflow-" + hashlib.sha256(log.read_bytes()).hexdigest()[:20]
    rid = "import-" + digest([family, reviews])[:20]
    record = {
        "schema_version": SCHEMA, "run_id": rid, "task_id": family, "family_id": family,
        "split": split_for(family), "task_origin": "observed_workflow",
        "execution_mode": "imported_metadata", "actor_kind": "recorded_model_review",
        "coverage": "partial_review_metadata", "observed_reviews": reviews,
        "source_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
        "rights": {"basis": "unverified", "allowed_uses": []},
        "evaluation": {"source": "not_evaluated", "outcome": "not_assessed",
                       "passed": None, "failure_codes": []},
        "terminal_reason": "metadata_imported",
        "usage_status": "unknown", "provider_cost": None,
    }
    write_new(Path(root) / "runs" / rid / "run.json", record)
    return record


def valid_record_shape(record):
    if not isinstance(record, dict):
        return False
    if not all(isinstance(record.get(k), str) and record[k] for k in (
            "run_id", "task_id", "family_id", "split", "actor_kind", "terminal_reason")):
        return False
    for key in ("events_path", "task_snapshot_path"):
        if key in record and (not isinstance(record[key], str) or not record[key]
                              or "\x00" in record[key]):
            return False
    rights, label = record.get("rights"), record.get("evaluation")
    return (isinstance(rights, dict) and isinstance(rights.get("allowed_uses"), list)
            and all(isinstance(x, str) for x in rights["allowed_uses"])
            and isinstance(label, dict) and isinstance(label.get("outcome"), str))


def quality_decision(root, record, purpose="diagnostic", allow_scripted=False):
    reasons = []
    if purpose not in ("diagnostic", "sft"):
        raise ValueError("unsupported export purpose")
    if not valid_record_shape(record) or record.get("_load_error"):
        return {"decision": "quarantine", "reasons": ["invalid_run_record"],
                "purpose": purpose}
    if record["actor_kind"] not in {
            "scripted_policy", "external_command", "recorded_model_review", "model_cli"}:
        reasons.append("unknown_actor_kind")
    if purpose not in record.get("rights", {}).get("allowed_uses", []):
        reasons.append("rights_not_established")
    if record.get("coverage") != "complete_visible_loop":
        reasons.append("incomplete_trace")
    label = record.get("evaluation", {})
    label_valid = (
        (label.get("outcome") == "pass" and label.get("passed") is True)
        or (label.get("outcome") == "fail" and label.get("passed") is False)
        or (label.get("outcome") == "not_assessed" and label.get("passed") is None)
    )
    if label.get("source") != "deterministic" or not label_valid:
        reasons.append("unverified_label")
    if record.get("split") != split_for(record.get("family_id", "")):
        reasons.append("invalid_family_split")
    events_ref = record.get("events_path")
    if events_ref:
        try:
            path = (Path(root) / events_ref).resolve()
            path.relative_to(Path(root).resolve())
        except (OSError, ValueError, TypeError):
            reasons.append("event_path_outside_root")
        else:
            try:
                if hashlib.sha256(path.read_bytes()).hexdigest() != record.get("events_sha256"):
                    reasons.append("events_hash_mismatch")
                events = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
                task_path = (Path(root) / record.get("task_snapshot_path", "")).resolve()
                task_path.relative_to(Path(root).resolve())
                task = read(task_path)
                if digest(task) != record.get("task_hash"):
                    reasons.append("task_hash_mismatch")
                if (task.get("family_id") != record.get("family_id")
                        or task.get("task_id") != record.get("task_id")
                        or task.get("rights") != record.get("rights")):
                    reasons.append("task_provenance_mismatch")
                observed = [e["payload"] for e in events if e["event_type"] == "observation"]
                regraded = grade(task, record.get("submission"), observed)
                if regraded != record.get("evaluation"):
                    reasons.append("evaluation_mismatch")
                submissions = [e["payload"] for e in events if e["event_type"] == "action"
                               and e["payload"].get("tool") == "submit_answer"]
                if (submissions[-1] if submissions else None) != record.get("submission"):
                    reasons.append("submission_mismatch")
                ids = [e["event_id"] for e in events]
                if len(ids) != len(set(ids)) or len(ids) != record.get("event_count"):
                    reasons.append("invalid_event_count")
                previous = None
                for event in events:
                    if (event.get("run_id") != record["run_id"]
                            or event.get("task_id") != record["task_id"]
                            or event.get("family_id") != record["family_id"]
                            or event.get("parent_event_ids") != ([previous] if previous else [])):
                        reasons.append("invalid_event_chain")
                        break
                    previous = event["event_id"]
                if not events or events[-1].get("event_type") != "run_finished":
                    reasons.append("missing_terminal_event")
                elif events[-1].get("payload") != {
                        "terminal_reason": record.get("terminal_reason"),
                        "evaluation": record.get("evaluation")}:
                    reasons.append("terminal_event_mismatch")
                if (not events or events[0].get("event_type") != "run_started"
                        or events[0]["payload"].get("task_hash") != record.get("task_hash")
                        or events[0]["payload"].get("visible_task") != redact(task["public"])):
                    reasons.append("initial_task_mismatch")
                if events:
                    policy = events[0].get("payload", {}).get("policy")
                    actor = ("model_cli" if policy == "codex" else "external_command" if policy == "command" else
                             "scripted_policy" if policy in {"reference", "broken", "loop"} else None)
                    if actor is None or actor != record.get("actor_kind") or policy != record.get("policy"):
                        reasons.append("actor_provenance_mismatch")
                    if policy == "codex":
                        reasons.extend(check_model_trace(root, record, task, events, purpose))
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                reasons.append("unreadable_events")
    else:
        reasons.append("missing_events")
    if purpose == "sft":
        if label.get("passed") is not True:
            reasons.append("failed_run_not_sft_demonstration")
        if record.get("actor_kind") == "scripted_policy" and not allow_scripted:
            reasons.append("scripted_control_not_model_training_data")
        if record.get("actor_kind") not in {"scripted_policy", "model_cli"}:
            reasons.append("model_execution_provenance_not_established")
        if record.get("split") == "holdout":
            reasons.append("holdout_not_for_training")
    return {"decision": "quarantine" if reasons else "accept",
            "reasons": sorted(set(reasons)), "purpose": purpose}


def check_model_trace(root, record, task, events, purpose):
    from .providers import validate_capture, valid_usage
    reasons = []
    config = record.get("model_config")
    if not isinstance(config, dict) or config != events[0]["payload"].get("model_config"):
        return ["model_configuration_mismatch"]
    rights = config.get("output_rights", {})
    if rights != record.get("output_rights") or purpose not in rights.get("allowed_uses", []):
        reasons.append("model_output_rights_not_established")
    observations, pending, captures = [], None, []
    for event in events:
        if event["event_type"] == "model_call":
            if pending is not None:
                reasons.append("model_action_binding_mismatch")
            reference = event["payload"]["capture"]
            if not validate_capture(root, reference, task["public"], observations, config,
                                    strict=purpose == "sft"):
                reasons.append("invalid_model_capture")
                continue
            capture = read(Path(root) / reference["path"])
            if event["payload"].get("status") != capture["status"]:
                reasons.append("model_capture_status_mismatch")
            captures.append(capture)
            pending = capture["action"] if capture["status"] == "completed" else None
        elif event["event_type"] == "action":
            if pending is None or event["payload"] != pending:
                reasons.append("model_action_binding_mismatch")
            pending = None
        elif event["event_type"] == "observation":
            observations.append(event["payload"])
    if pending is not None:
        reasons.append("model_action_binding_mismatch")
    if not captures:
        reasons.append("no_model_execution_observed")
    if len(captures) != record.get("model_calls_observed"):
        reasons.append("model_call_count_mismatch")
    known = [c["usage"] for c in captures if valid_usage(c.get("usage"))]
    expected = {k: sum(u[k] for u in known) for k in
                ("input_tokens", "cached_input_tokens", "output_tokens")}
    status = ("observed_complete" if known and len(known) == len(captures)
              else "observed_partial" if known else "unknown")
    if record.get("model_identity_basis") != "requested_configuration":
        reasons.append("model_identity_basis_mismatch")
    if expected != record.get("token_usage") or status != record.get("usage_status"):
        reasons.append("model_usage_mismatch")
    return reasons


def all_runs(root):
    records = []
    for path in sorted((Path(root) / "runs").glob("*/run.json")):
        try:
            record = read(path)
            if not valid_record_shape(record):
                raise ValueError("invalid_record_structure")
        except (OSError, ValueError, TypeError) as exc:
            try:
                raw_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                raw_hash = None
            record = {
                "run_id": path.parent.name, "task_id": "unknown", "family_id": "unknown",
                "split": "unknown", "actor_kind": "unknown", "terminal_reason": "record_unreadable",
                "rights": {"basis": "unknown", "allowed_uses": []},
                "evaluation": {"outcome": "unknown", "passed": None},
                "_load_error": type(exc).__name__,
                "source_record_path": str(path.relative_to(root)),
                "source_record_sha256": raw_hash,
            }
        records.append(record)
    return records


def export_runs(root, destination, purpose="diagnostic", allow_scripted=False, run_ids=None):
    accepted, quarantined = [], []
    for record in all_runs(root):
        if run_ids is not None and record["run_id"] not in run_ids:
            continue
        decision = quality_decision(root, record, purpose, allow_scripted)
        if decision["decision"] == "accept":
            events = [json.loads(x) for x in (Path(root) / record["events_path"]).read_text(
                encoding="utf-8").splitlines()]
            item = {"record": redact(record), "events": redact(events)}
            if record.get("actor_kind") == "model_cli":
                item["model_calls"] = []
                for event in events:
                    if event["event_type"] == "model_call":
                        folder = (Path(root) / event["payload"]["capture"]["path"]).parent
                        item["model_calls"].append({
                            "capture": redact(read(folder / "capture.json")),
                            "request": redact(read(folder / "request.json")),
                            "events": [json.loads(x) for x in (folder / "events.jsonl").read_text(
                                encoding="utf-8").splitlines()]})
            accepted.append(item)
        else:
            item = {"run_id": record["run_id"], **decision}
            if record.get("_load_error"):
                item.update({key: record[key] for key in (
                    "source_record_path", "source_record_sha256", "_load_error")})
            quarantined.append(item)
    package = {"schema_version": SCHEMA, "purpose": purpose,
               "records": accepted, "quarantine": quarantined,
               "counts": {"accepted": len(accepted), "quarantined": len(quarantined)}}
    write_new(destination, package)
    return package["counts"]


def stats(root):
    runs = all_runs(root)
    return {"runs": len(runs),
            "task_families": len({r["family_id"] for r in runs if not r.get("_load_error")}),
            "actor_kinds": dict(Counter(r["actor_kind"] for r in runs)),
            "outcomes": dict(Counter(r["evaluation"]["outcome"] for r in runs)),
            "terminals": dict(Counter(r["terminal_reason"] for r in runs)),
            "export_decisions": dict(Counter(
                quality_decision(root, r)["decision"] for r in runs)),
            "cost_boundary": "Provider charges are not inferred from missing usage."}
