"""Import an explicitly selected runtime log without copying reasoning or system prompts."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from .core import digest, read, redact, split_for, write_new

VISIBLE_CHANNELS = {"commentary", "final"}
CALLS = {"function_call", "custom_tool_call"}
RESULTS = {"function_call_output", "custom_tool_call_output"}


def import_session(root, source, max_bytes=100_000_000):
    source = Path(source)
    if not source.is_file() or source.stat().st_size > max_bytes:
        raise ValueError("session_missing_or_too_large")
    with source.open("rb") as stream:
        raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("session_too_large")
    source_hash = hashlib.sha256(raw).hexdigest()
    rows, omitted, malformed, model_requests, usage = [], {}, [], set(), []
    session_id = None
    calls, results = set(), set()
    for number, line in enumerate(raw.splitlines(), 1):
        try:
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError("record_not_object")
            kind, payload = item.get("type"), item.get("payload", {})
            if not isinstance(payload, dict):
                raise ValueError("payload_not_object")
        except (ValueError, TypeError):
            malformed.append({"source_line": number, "sha256": hashlib.sha256(line).hexdigest()})
            continue
        if kind == "session_meta":
            session_id = payload.get("id", session_id)
            continue
        if kind == "turn_context":
            if isinstance(payload.get("model"), str):
                model_requests.add(payload["model"])
            continue
        if kind == "event_msg" and payload.get("type") == "token_count":
            info = payload.get("info", {})
            # Retain only numeric usage counters, not arbitrary event text.
            if isinstance(info, dict):
                totals = info.get("total_token_usage", {})
                if isinstance(totals, dict):
                    numeric = {k: v for k, v in totals.items() if type(v) is int and v >= 0}
                    if numeric:
                        usage.append({"source_line": number, "cumulative_counters": numeric})
            continue
        if kind != "response_item":
            omitted[kind or "unknown"] = omitted.get(kind or "unknown", 0) + 1
            continue
        subtype = payload.get("type")
        event = {"source_line": number, "timestamp": item.get("timestamp")}
        if subtype == "message":
            role, channel = payload.get("role"), payload.get("channel")
            if role == "assistant" and channel not in VISIBLE_CHANNELS:
                omitted["nonvisible_assistant"] = omitted.get("nonvisible_assistant", 0) + 1
                continue
            if role not in {"user", "assistant"}:
                omitted["system_or_developer"] = omitted.get("system_or_developer", 0) + 1
                continue
            content = []
            parts = payload.get("content", [])
            if not isinstance(parts, list):
                malformed.append({"source_line": number, "reason": "invalid_message_content"})
                continue
            for part in parts:
                if isinstance(part, dict) and part.get("type") in {"input_text", "output_text", "text"}:
                    content.append(str(part.get("text", "")))
            event.update(type="visible_message", role=role, channel=channel,
                         text="\n".join(content))
        elif subtype in CALLS:
            call_id = payload.get("call_id")
            if not isinstance(call_id, str) or call_id in calls:
                malformed.append({"source_line": number, "reason": "invalid_or_duplicate_call_id"})
                continue
            calls.add(call_id)
            event.update(type="tool_call", call_id=call_id, name=payload.get("name"),
                         arguments=payload.get("arguments", payload.get("input")))
        elif subtype in RESULTS:
            call_id = payload.get("call_id")
            if not isinstance(call_id, str) or call_id in results:
                malformed.append({"source_line": number, "reason": "invalid_or_duplicate_result_id"})
                continue
            results.add(call_id)
            event.update(type="tool_result", call_id=call_id, output=payload.get("output"))
        else:
            omitted[subtype or "unknown_response_item"] = omitted.get(subtype or "unknown_response_item", 0) + 1
            continue
        rows.append(redact(event))
    if not rows:
        raise ValueError("no_visible_session_events")
    family = "session-" + digest(session_id or source.name)[:24]
    identifier = digest([source_hash, "visible-session-v1"])[:32]
    folder = Path(root) / "runtime_sessions" / identifier
    events_path = folder / "events.jsonl"
    folder.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    if events_path.exists():
        if events_path.read_text(encoding="utf-8") != body:
            raise ValueError("immutable_session_import_conflict")
    else:
        with events_path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(body)
    record = {
        "schema_version": "visible-session-v1", "import_id": identifier, "family_id": family,
        "split": split_for(family), "task_origin": "observed_session",
        "actor_kind": "observed_assistant_session", "execution_mode": "imported_visible_runtime",
        "capture_scope": "top_level_visible_messages_and_tool_calls",
        "source_sha256": source_hash, "source_bytes": len(raw),
        "events_sha256": hashlib.sha256(events_path.read_bytes()).hexdigest(),
        "events": len(rows), "tool_calls": len(calls), "tool_results": len(results),
        "unmatched_calls": len(calls - results), "orphan_results": len(results - calls),
        "requested_models": sorted(model_requests), "served_model": None,
        "model_identity_basis": "session_context_configuration",
        "usage_snapshots": usage, "usage_boundary": "Cumulative session counters; not per-call billing.",
        "omitted_counts": omitted, "malformed_records": malformed,
        "rights": {"basis": "selected_local_session_internal_diagnostics",
                   "allowed_uses": ["diagnostic"]},
        "evaluation": {"outcome": "not_assessed", "passed": None},
        "replay_status": "no_frozen_external_environment",
        "training_eligible": False,
    }
    write_new(folder / "manifest.json", record)
    # Do not echo message bodies or local session contents to the caller.
    return {k: record[k] for k in ("import_id", "family_id", "task_origin", "actor_kind",
                "source_sha256", "events", "tool_calls", "tool_results", "unmatched_calls", "orphan_results",
                "replay_status", "training_eligible")}
