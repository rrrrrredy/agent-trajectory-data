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
    os.replace(temp, path)


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
               "max_task_seconds", "max_batch_seconds", "max_model_calls", "provider"}
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
    if result["policy"] not in {"reference", "broken", "loop", "codex"}:
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
    return result


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
        # A lost worker must not reissue a model request with unknown cancellation.
        for job in state["jobs"]:
            if job["status"] == "running":
                result_path = root / "runs" / job["run_id"] / "run.json"
                if result_path.exists():
                    try:
                        result = read(result_path)
                        if result["task_hash"] != job["task_hash"] or result["run_id"] != job["run_id"]:
                            raise ValueError("mismatched recovered run")
                        job.update(status="done", terminal_reason=result["terminal_reason"])
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
                    provider=provider, run_id=job["run_id"])
                job.update(status="done", terminal_reason=result["terminal_reason"],
                           evaluation=result["evaluation"], ended_at=now())
            except Exception as exc:
                # Preserve any partial run directory. Class names avoid secret-bearing error text.
                job.update(status="failed", reason=type(exc).__name__, ended_at=now())
                write_new(folder / (job["run_id"] + "-failure.json"), {
                    "run_id": job["run_id"], "task_id": job["task_id"],
                    "error_type": type(exc).__name__, "partial_run_preserved": True})
            save()
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
            "exports": exports, "data_origin": "synthetic_tasks",
            "model_identity_basis": "requested_configuration" if config["policy"] == "codex" else "not_applicable",
            "billing_amount": None, "billing_boundary": "Unknown; call count is the admission limit.",
        }
        # Derived summary has no timestamp, so a no-change resume is idempotent.
        atomic_json(folder / "summary.json", summary)
        return summary
