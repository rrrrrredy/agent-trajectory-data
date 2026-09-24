"""Vendor-neutral training exports with provenance gates and paired-attempt checks."""
from __future__ import annotations
import json
from pathlib import Path
from .core import all_runs, read, quality_decision, write_new, redact, digest


def messages_for(root, record):
    events = [json.loads(line) for line in (Path(root) / record["events_path"]).read_text(
        encoding="utf-8").splitlines()]
    public = events[0]["payload"]["visible_task"]
    messages = [{"role": "user", "content": json.dumps(public, ensure_ascii=False)}]
    for event in events:
        if event["event_type"] == "action":
            messages.append({"role": "assistant", "content": json.dumps(event["payload"], ensure_ascii=False)})
        elif event["event_type"] == "observation":
            messages.append({"role": "user", "content": json.dumps(
                {"tool_result": event["payload"]}, ensure_ascii=False)})
    return redact(messages)


def write_lines(path, rows):
    path = Path(path)
    body = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != body:
            raise ValueError("immutable_training_export_conflict")
    else:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(body)


def export_training(root, destination, run_ids=None):
    root, destination = Path(root), Path(destination)
    records = [r for r in all_runs(root) if run_ids is None or r["run_id"] in run_ids]
    by_id = {r["run_id"]: r for r in all_runs(root)}
    sft, pairs, rejected = [], [], []
    for record in records:
        decision = quality_decision(root, record, "sft")
        if decision["decision"] != "accept":
            rejected.append({"run_id": record["run_id"], "reasons": decision["reasons"]})
            continue
        sft.append({"run_id": record["run_id"], "task_id": record["task_id"],
                    "family_id": record["family_id"], "task_hash": record["task_hash"],
                    "format": "atd-visible-messages-v1", "messages": messages_for(root, record)})
        parent = by_id.get(record.get("parent_run_id"))
        if not parent or parent["evaluation"].get("outcome") != "fail":
            continue
        if (parent.get("task_hash") != record["task_hash"]
                or parent.get("model_config") != record.get("model_config")
                or parent.get("actor_kind") != "model_cli"
                or parent.get("terminal_reason") != "submitted"
                or record.get("terminal_reason") != "submitted"
                or parent.get("split") == "holdout"
                or set(quality_decision(root, parent, "sft")["reasons"]) != {"failed_run_not_sft_demonstration"}
                or "preference" not in record["rights"].get("allowed_uses", [])
                or "preference" not in record.get("output_rights", {}).get("allowed_uses", [])
                or "preference" not in parent.get("output_rights", {}).get("allowed_uses", [])):
            continue
        parent_events = [json.loads(x) for x in (root / parent["events_path"]).read_text(encoding="utf-8").splitlines()]
        child_events = [json.loads(x) for x in (root / record["events_path"]).read_text(encoding="utf-8").splitlines()]
        # Enforce comparable runtime limits as well as identical task/model configuration.
        keys = ("max_steps", "max_seconds")
        if any(parent_events[0]["payload"].get(k) != child_events[0]["payload"].get(k) for k in keys):
            continue
        chosen, rejected_messages = messages_for(root, record), messages_for(root, parent)
        if chosen[0] != rejected_messages[0]:
            continue
        pairs.append({"format": "atd-trajectory-preference-v1", "task_hash": record["task_hash"],
                      "family_id": record["family_id"], "chosen_run": record["run_id"],
                      "rejected_run": parent["run_id"], "prompt": chosen[0],
                      "chosen": chosen[1:], "rejected": rejected_messages[1:],
                      "label_basis": "deterministic_outcome_same_task_config_and_limits",
                      "causal_claim": False})
    write_lines(destination / "sft.jsonl", sft)
    write_lines(destination / "preferences.jsonl", pairs)
    summary = {"format": "atd-training-v1", "sft_records": len(sft),
               "preference_pairs": len(pairs), "quarantine": rejected,
               "messages_contract": "Visible JSON actions and tool-result messages; no private reasoning or oracle.",
               "trainer_boundary": "Vendor-neutral messages. Adapt tool roles/chat templates to the selected trainer.",
               "input_fingerprint": digest(sorted((r["run_id"], r.get("task_hash")) for r in records))}
    write_new(destination / "manifest.json", summary)
    return summary
