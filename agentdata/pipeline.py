"""Finite unattended production batches with durable admission and resumable state."""
from __future__ import annotations
import json
import math
import os
import re
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from .core import generate, read, digest, now, run_task, export_runs, write_new
from .providers import CodexProvider, BudgetExceeded

def atomic_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temp.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    for attempt in range(20):
        try:
            os.replace(temp, path)
            break
        except PermissionError:
            # Windows readers/indexers can briefly hold the old file without
            # FILE_SHARE_DELETE. Retrying this local rename cannot repeat model calls.
            if attempt == 19:
                raise
            time.sleep(0.025 * (attempt + 1))


@contextmanager
def batch_lock(path):
    # OS releases the lock if a worker exits. No stale-lock manual queue.
    stream = Path(path).open("a+b")
    stream.seek(0, os.SEEK_END)
    if stream.tell() == 0:
        stream.write(b"0")
        stream.flush()
    stream.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        stream.close()
        raise RuntimeError("batch_already_running") from exc
    try:
        yield
    finally:
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def normalize_config(config):
    if not isinstance(config, dict):
        raise ValueError("pipeline config must be an object")
    allowed = {"schema_version", "policy", "families", "seed", "max_steps",
               "max_task_seconds", "max_batch_seconds", "max_model_calls", "provider",
               "task_ids", "monthly_model_calls", "profile", "command_argv", "max_attempts_per_task"}
    if set(config) - allowed or config.get("schema_version", "0.2") != "0.2":
        raise ValueError("unknown pipeline option or unsupported schema version")
    result = {
        "schema_version": "0.2", "policy": config.get("policy", "reference"),
        "families": config.get("families", 1), "seed": config.get("seed", 20260924),
        "max_steps": config.get("max_steps", 5), "max_task_seconds": config.get("max_task_seconds", 120),
        "max_batch_seconds": config.get("max_batch_seconds", 600),
        "max_model_calls": config.get("max_model_calls", 8),
        "provider": config.get("provider", {}),
    }
    if result["policy"] not in {"reference", "broken", "loop", "codex", "command"}:
        raise ValueError("unsupported pipeline policy")
    for field in ("families", "max_steps", "max_model_calls"):
        if not isinstance(result[field], int) or isinstance(result[field], bool) or result[field] < 1:
            raise ValueError(field + " must be a positive integer")
    if result["families"] > 1000:
        raise ValueError("pipeline family limit is 1000")
    if not isinstance(result["seed"], int) or isinstance(result["seed"], bool):
        raise ValueError("seed must be an integer")
    for field in ("max_task_seconds", "max_batch_seconds"):
        value = result[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(field + " must be finite and positive")
    if not isinstance(result["provider"], dict):
        raise ValueError("provider must be an object")
    if "max_attempts_per_task" in config:
        attempts = config["max_attempts_per_task"]
        if type(attempts) is not int or not 1 <= attempts <= 3:
            raise ValueError("max_attempts_per_task must be between 1 and 3")
        result["max_attempts_per_task"] = attempts

    if "profile" in config:
        if config["profile"] not in {"closed-facts-v1", "research-evidence-v1"}:
            raise ValueError("unsupported_profile")
        result["profile"] = config["profile"]
    if result["policy"] == "command":
        argv = config.get("command_argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
            raise ValueError("command_policy_requires_argv")
        result["command_argv"] = argv
    elif "command_argv" in config:
        raise ValueError("command_argv_without_command_policy")

    if "task_ids" in config:
        ids = config["task_ids"]
        if (not isinstance(ids, list) or not 1 <= len(ids) <= 3000
                or not all(isinstance(x, str) and re.fullmatch(
                    r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}", x) for x in ids)
                or len(set(ids)) != len(ids)):
            raise ValueError("invalid_task_ids")
        result["task_ids"] = ids
    if "monthly_model_calls" in config:
        cap = config["monthly_model_calls"]
        if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
            raise ValueError("monthly_model_calls must be positive")
        result["monthly_model_calls"] = cap
    return result


def reserve_monthly(root, limit, run_id):
    from datetime import datetime, timezone
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    folder = Path(root) / "budgets"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (month + ".json")
    with batch_lock(folder / (month + ".lock")):
        ledger = read(path) if path.exists() else {"month_utc": month, "calls_reserved": 0,
                                                  "reservations": []}
        if ledger["calls_reserved"] >= limit:
            raise BudgetExceeded("monthly_call_budget_exhausted")
        ledger["calls_reserved"] += 1
        ledger["reservations"].append({"run_id": run_id, "reserved_at": now()})
        atomic_json(path, ledger)


def run_cycle(root, config, period_hours=24):
    # Intended for an external scheduler; duplicate triggers in one UTC bucket are safe.
    if isinstance(period_hours, bool) or not isinstance(period_hours, int) or not 1 <= period_hours <= 168:
        raise ValueError("period_hours must be between 1 and 168")
    config = normalize_config(config)
    if config["policy"] == "codex" and "monthly_model_calls" not in config:
        raise ValueError("scheduled_model_batches_require_monthly_call_budget")
    bucket = int(time.time()) // (period_hours * 3600)
    batch_id = "cycle-" + digest(config)[:12] + "-" + str(period_hours) + "-" + str(bucket)
    return run_pipeline(root, config, batch_id)


def run_pipeline(root, config, batch_id, provider_factory=CodexProvider):
    config = normalize_config(config)
    if not isinstance(batch_id, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", batch_id):
        raise ValueError("batch_id must contain only letters, digits, hyphens and underscores")
    root = Path(root).resolve()
    folder = root / "batches" / batch_id
    folder.mkdir(parents=True, exist_ok=True)
    with batch_lock(folder / "worker.lock"):
        state_path = folder / "state.json"
        if state_path.exists():
            state = read(state_path)
            if state["config_sha256"] != digest(config):
                raise ValueError("batch configuration is immutable; use a new batch id")
        else:
            if "task_ids" in config:
                from .taskpacks import validate_task
                tasks = [root / "tasks" / (task_id + ".json") for task_id in config["task_ids"]]
                for path in tasks:
                    path.resolve().relative_to(root)
                    task = validate_task(read(path))
                    if task["task_id"] != path.stem:
                        raise ValueError("task_file_identity_mismatch")
            elif config.get("profile") == "research-evidence-v1":
                from .research_tasks import generate_research
                tasks = generate_research(root, config["families"], config["seed"])
            else:
                tasks = generate(root, config["families"], config["seed"])
            state = {
                "batch_id": batch_id, "config": config, "config_sha256": digest(config),
                "created_at": now(), "deadline_epoch": time.time() + config["max_batch_seconds"],
                "status": "pending", "calls_reserved": 0, "reservations": [],
                "jobs": [{"task_path": str(p.relative_to(root)), "task_hash": digest(read(p)),
                          "task_id": read(p)["task_id"], "run_id": uuid.uuid4().hex, "status": "pending"}
                         for p in tasks],
            }
            write_new(folder / "config.json", config)
            atomic_json(state_path, state)
        def save():
            atomic_json(state_path, state)
        def enqueue_retry(job, result):
            if (result["terminal_reason"] == "submitted"
                    and result["evaluation"]["outcome"] == "fail"
                    and job.get("attempt", 1) < config.get("max_attempts_per_task", 1)
                    and not any(j.get("parent_run_id") == job["run_id"] for j in state["jobs"])):
                state["jobs"].append({
                    "task_path": job["task_path"], "task_hash": job["task_hash"],
                    "task_id": job["task_id"], "run_id": uuid.uuid4().hex, "status": "pending",
                    "attempt": job.get("attempt", 1) + 1, "parent_run_id": job["run_id"]})
        # A lost worker must not reissue a model request with unknown cancellation.
        for job in state["jobs"]:
            if job["status"] == "running":
                result_path = root / "runs" / job["run_id"] / "run.json"
                if result_path.exists():
                    try:
                        result = read(result_path)
                        if result["task_hash"] != job["task_hash"] or result["run_id"] != job["run_id"]:
                            raise ValueError("mismatched recovered run")
                        job.update(status="done", terminal_reason=result["terminal_reason"],
                                   evaluation=result["evaluation"])
                        enqueue_retry(job, result)
                    except (OSError, ValueError, TypeError, KeyError):
                        job.update(status="interrupted", reason="inconsistent_recovered_record")
                else:
                    job.update(status="interrupted", reason="worker_lost_remote_cancellation_unknown")
                job["recovered_at"] = now()
                save()
        active = {"run_id": None}
        def admit():
            if time.time() >= state["deadline_epoch"]:
                raise BudgetExceeded("batch_deadline_exhausted")
            if state["calls_reserved"] >= config["max_model_calls"]:
                raise BudgetExceeded("model_call_budget_exhausted")
            if "monthly_model_calls" in config:
                reserve_monthly(root, config["monthly_model_calls"], active["run_id"])
            state["calls_reserved"] += 1
            state["reservations"].append({
                "index": state["calls_reserved"], "run_id": active["run_id"], "reserved_at": now()})
            save()  # Before sending the request. Unknown calls are never refunded.
        provider = None
        if config["policy"] == "codex" and any(j["status"] == "pending" for j in state["jobs"]):
            provider = provider_factory(config["provider"], admit=admit)
        for job in state["jobs"]:
            if job["status"] != "pending":
                continue
            if time.time() >= state["deadline_epoch"]:
                state["status"] = "deadline_exhausted"
                break
            if config["policy"] == "codex" and state["calls_reserved"] >= config["max_model_calls"]:
                state["status"] = "call_budget_exhausted"
                break
            state["status"] = "running"
            active["run_id"] = job["run_id"]
            job.update(status="running", started_at=now())
            save()
            try:
                task = read(root / job["task_path"])
                if digest(task) != job["task_hash"]:
                    raise ValueError("task_changed_after_batch_creation")
                result = run_task(
                    root, task, policy=config["policy"], max_steps=config["max_steps"],
                    max_seconds=min(config["max_task_seconds"], max(
                        0.001, state["deadline_epoch"]-time.time())),
                    provider=provider, run_id=job["run_id"], command=config.get("command_argv"),
                    parent_run_id=job.get("parent_run_id"))
                job.update(status="done", terminal_reason=result["terminal_reason"],
                           evaluation=result["evaluation"], ended_at=now())
                enqueue_retry(job, result)
            except Exception as exc:
                # Preserve any partial run directory. Class names avoid secret-bearing error text.
                job.update(status="failed", reason=type(exc).__name__, ended_at=now())
                write_new(folder / (job["run_id"] + "-failure.json"), {
                    "run_id": job["run_id"], "task_id": job["task_id"],
                    "error_type": type(exc).__name__, "partial_run_preserved": True})
            save()
            if job.get("terminal_reason") == "monthly_call_budget_exhausted":
                state["status"] = "monthly_call_budget_exhausted"
                break
        if all(j["status"] in {"done", "failed", "interrupted"} for j in state["jobs"]):
            state["status"] = "completed_with_errors" if any(
                j["status"] != "done" for j in state["jobs"]) else "completed"
        save()
        run_ids = {j["run_id"] for j in state["jobs"]}
        exports = {}
        for purpose in ("diagnostic", "sft"):
            exports[purpose] = export_runs(root, folder / (purpose + ".json"), purpose,
                                          run_ids=run_ids)
        summary = {
            "batch_id": batch_id, "status": state["status"], "jobs": len(state["jobs"]),
            "job_statuses": {key: sum(j["status"] == key for j in state["jobs"])
                             for key in ("pending", "running", "done", "failed", "interrupted")},
            "calls_reserved": state["calls_reserved"], "max_model_calls": config["max_model_calls"],
             "exports": exports, "data_origin": "selected_tasks" if "task_ids" in config else "synthetic_tasks",
            "monthly_call_limit": config.get("monthly_model_calls"),
            "model_identity_basis": "requested_configuration" if config["policy"] == "codex" else "not_applicable",
            "billing_amount": None, "billing_boundary": "Unknown; call count is the admission limit.",
        }
        # Derived summary has no timestamp, so a no-change resume is idempotent.
        atomic_json(folder / "summary.json", summary)
        return summary
