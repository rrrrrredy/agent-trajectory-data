"""Machine-readable withdrawal records; retained evidence is never silently erased."""
from __future__ import annotations
import hashlib
import re
from pathlib import Path
from .core import read, digest, write_new


def withdraw(root, kind, value, reason):
    if kind not in {"source_group", "source_sha256"} or not isinstance(value, str) or not value:
        raise ValueError("invalid_withdrawal_selector")
    if kind == "source_sha256" and not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("invalid_source_hash")
    if not isinstance(reason, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", reason):
        raise ValueError("reason_must_be_machine_code")
    record = {"kind": kind, "value": value, "reason": reason, "status": "withdrawn"}
    identifier = digest(record)
    write_new(Path(root) / "governance/withdrawals" / (identifier + ".json"), record)
    return {"withdrawal_id": identifier, **record, "effect": "blocks_future_export_and_delivery"}


def withdrawal_reason(root, task):
    lineage = task.get("lineage", {})
    values = {"source_group": task.get("source_group", lineage.get("source_group")),
              "source_sha256": lineage.get("source_sha256")}
    for path in (Path(root) / "governance/withdrawals").glob("*.json"):
        try:
            record = read(path)
            if record["status"] != "withdrawn" or record["kind"] not in values:
                return "invalid_withdrawal_policy"
            if record["value"] == values[record["kind"]]:
                return "source_withdrawn"
        except (OSError, ValueError, TypeError, KeyError):
            return "invalid_withdrawal_policy"
    return None


def resolve_release(root, release_id, audience="internal"):
    root = Path(root).resolve()
    receipt_path = root / "releases" / (digest([release_id, audience]) + ".json")
    receipt = read(receipt_path)
    if not receipt.get("task_ids") or not receipt.get("artifact_path"):
        raise ValueError("legacy_release_requires_new_governed_build")
    for task_id in receipt["task_ids"]:
        if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}", task_id):
            raise ValueError("invalid_release_task_id")
        task_path = (root / "tasks" / (task_id + ".json")).resolve()
        task_path.relative_to(root)
        task = read(task_path)
        if digest(task) != receipt["task_hashes"][task_id]:
            raise ValueError("release_source_changed")
        reason = withdrawal_reason(root, task)
        if reason:
            raise ValueError(reason)
    path = Path(receipt["artifact_path"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != receipt["sha256"]:
        raise ValueError("release_file_changed")
    return path
