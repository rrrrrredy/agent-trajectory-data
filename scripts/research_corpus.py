"""Build a portable private corpus from selected native observations and frozen report inputs."""
from __future__ import annotations
import argparse
import importlib.util
import io
import json
import re
import zipfile
from collections import Counter
from pathlib import Path

_spec = importlib.util.spec_from_file_location("history_helper", Path(__file__).with_name("research_history.py"))
history = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(history)
rd, check = history.rd, history.check
VERSION = "research-corpus-v3"
DATASET = Path("evaluation-dataset-20260914")
SELECTION = Path("mainline-replan-20260921/original-review-completions/current-original-review-index.json")
POLICY = {"split": "development", "rights": rd.RIGHTS, "quality_outcome": "not_assessed"}
FORBIDDEN = {"reasoning", "reasoning_content", "encrypted_content", "thinking", "authorization", "api_key"}

def digest_json(obj):
    return rd.sha(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())

def safe_material(obj):
    if isinstance(obj, dict):
        check(not (set(k.lower() for k in obj) & FORBIDDEN), "private_field_in_material")
        for value in obj.values():
            safe_material(value)
    elif isinstance(obj, list):
        for value in obj:
            safe_material(value)
    elif isinstance(obj, str):
        check(not history.SECRET.search(obj), "credential_like_content")

def source_blob(root, source, output, expected=None, lf=None):
    source = Path(source).resolve()
    check(source.is_relative_to(root.resolve()) and source.is_file() and not source.is_symlink(),
          "source_outside_selected_tree")
    raw = source.read_bytes()
    digest = rd.sha(raw)
    check(expected is None or digest == expected, "original_source_hash_mismatch")
    if lf:
        check(rd.normalized_hash(source) == lf, "original_source_lf_hash_mismatch")
    text = raw.decode("utf-8-sig")
    if source.suffix == ".json":
        safe_material(json.loads(text))
    elif source.suffix == ".jsonl":
        for line in raw.split(b"\n"):
            if line.strip():
                safe_material(json.loads(line))
    else:
        safe_material(text)
    path = "sources/objects/" + digest + source.suffix
    rd.put(output / path, raw)
    return {"path": path, "sha256": digest, "source_relative_path": source.relative_to(root).as_posix()}

def read_blob(root, ref, as_json=True):
    path = rd.local_file(root, ref["path"])
    check(rd.sha(path.read_bytes()) == ref["sha256"], "source_blob_changed")
    return rd.load_json(path) if as_json else path.read_text(encoding="utf-8-sig")

def content_text(payload):
    parts = payload.get("content", [])
    return [p["text"] for p in parts if p.get("type") in {"input_text", "output_text", "text"}]

def project_native(raw, run_id, prior_turns, prior):
    records = [(n, line, json.loads(line)) for n, line in enumerate(raw.split(b"\n"), 1) if line.strip()]
    meta = [r["payload"] for _, _, r in records if r["type"] == "session_meta"]
    check(len(meta) == 1, "native_session_metadata_missing")
    sid, cwd = meta[0]["id"], meta[0]["cwd"]
    check({t["session_id"] for t in prior_turns} == {sid}, "native_session_identity_mismatch")
    prompts = {t["turn"]: rd.local_file(prior, t["prompt_path"]).read_text(encoding="utf-8").strip()
               for t in prior_turns}
    events, omitted, prompt_lines, finished = [], Counter(), {}, []
    turn, native_turn = 0, None
    global_calls = set()
    for number, line, row in records:
        payload = row.get("payload", {})
        kind, subtype = row["type"], payload.get("type")
        event = {"source_line": number, "source_line_sha256": rd.sha(line),
                 "timestamp": row.get("timestamp"), "event_id": f"native-{run_id}-{number}"}
        if kind == "event_msg" and subtype in {"task_started", "task_complete"}:
            if subtype == "task_started":
                turn += 1
                check(turn in prompts, "extra_native_turn")
                native_turn = payload["turn_id"]
            else:
                check(payload["turn_id"] == native_turn, "native_terminal_identity_mismatch")
                finished.append(turn)
            event.update(kind=subtype, native_turn_id=native_turn)
        elif kind == "compacted":
            event.update(kind="context_compacted", content_retained=False)
        elif kind == "response_item" and subtype == "message":
            if payload.get("role") == "user":
                if any(prompts.get(turn) == history.scrub(text, cwd).strip() for text in content_text(payload)):
                    prompt_lines[turn] = number
                omitted["user_context_already_bound_or_not_selected"] += 1
                continue
            phase = payload.get("channel") or payload.get("phase")
            if payload.get("role") != "assistant" or phase not in {"commentary", "final", "final_answer"}:
                omitted["nonvisible_or_instruction_message"] += 1
                continue
            text = "\n".join(content_text(payload))
            body = re.sub(r"\s*<oai-mem-citation>[\s\S]*?</oai-mem-citation>\s*$", "", text)
            event.update(kind="assistant_message", channel="final" if phase == "final_answer" else phase,
                         text=history.scrub(body, cwd), client_footer_removed=body != text,
                         original_message_sha256=rd.sha(text.encode()))
        elif kind == "response_item" and subtype in {"custom_tool_call", "function_call"}:
            call_id = payload["call_id"]
            code = payload.get("input", payload.get("arguments"))
            check(isinstance(code, str), "nontext_native_call")
            if re.search(r"_home|memories", code, flags=re.I):
                global_calls.add(call_id)
            event.update(kind="tool_call", call_id=call_id, name=payload["name"],
                         arguments=history.scrub(code, cwd),
                         web_invocation_text_present=bool(re.search(r"tools\.web__run\s*\(", code)))
        elif kind == "response_item" and subtype in {"custom_tool_call_output", "function_call_output"}:
            output = payload["output"]
            if isinstance(output, str):
                output = [{"type": "text", "text": output}]
            check(isinstance(output, list) and all(p.get("type") in {"input_text", "output_text", "text"}
                  and isinstance(p.get("text"), str) for p in output), "unsupported_native_output")
            redacted = payload["call_id"] in global_calls
            event.update(kind="tool_result", call_id=payload["call_id"], redacted=redacted,
                         original_output_sha256=digest_json(output),
                         output=None if redacted else history.scrub(
                             [{"type": p["type"], "text": p["text"]} for p in output], cwd),
                         redaction_reason="unrelated_global_context" if redacted else None)
        else:
            omitted[subtype if kind == "response_item" else kind] += 1
            continue
        check(turn in prompts, "native_event_outside_turn")
        event.update(run_id=run_id, turn_id=f"{run_id}-turn-{turn}", turn=turn)
        events.append(event)
    check(turn == len(prior_turns) and finished == list(range(1, turn+1))
          and set(prompt_lines) == set(prompts), "native_turn_or_prompt_binding_mismatch")
    for original in prior_turns:
        messages = [e["text"] for e in events if e["turn"] == original["turn"]
                    and e["kind"] == "assistant_message" and e["channel"] == "final"]
        expected = rd.local_file(prior, original["final_message_path"]).read_text(encoding="utf-8").strip()
        check(len(messages) == 1 and messages[0].strip() == expected, "native_final_message_mismatch")
    return events, {"run_id": run_id, "session_id": sid, "source_sha256": rd.sha(raw),
                    "source_bytes": len(raw), "prompt_source_lines": prompt_lines,
                    "omitted_counts": dict(omitted), "turn_count": turn}

def native_calls(events):
    calls, outputs = {}, {}
    for e in events:
        if e["kind"] == "tool_call":
            check(e["call_id"] not in calls, "duplicate_native_call")
            calls[e["call_id"]] = e
        elif e["kind"] == "tool_result":
            check(e["call_id"] not in outputs, "duplicate_native_result")
            outputs[e["call_id"]] = e
    check(set(calls) == set(outputs), "unmatched_native_tool_record")
    rows = []
    for call_id, request in calls.items():
        response = outputs[call_id]
        check(request["source_line"] < response["source_line"] and request["turn_id"] == response["turn_id"],
              "native_pair_boundary_mismatch")
        text = "\n".join(p["text"] for p in response["output"] or [])
        rows.append({"call_id": call_id, "run_id": request["run_id"], "turn_id": request["turn_id"],
                     "request_event": request["event_id"], "response_event": response["event_id"],
                     "tool": request["name"], "output_available": not response["redacted"],
                     "web_related_executor_batch": request["web_invocation_text_present"],
                     "truncation_marker_present": bool(re.search(r"truncated output|tokens truncated|content truncated", text, re.I)),
                     "granularity": "executor_batch", "fully_replayable_environment": False, **POLICY})
    return rows

def collect_sources(source, sessions, prior, output):
    for p in sorted(prior.rglob("*")):
        if p.is_file():
            rd.put(output / "prior" / p.relative_to(prior), p.read_bytes())
    old_turns = rd.load_lines(prior / "turns.jsonl")
    native_index = []
    for run_id in history.RUNS:
        turns = [t for t in old_turns if t["run_id"] == run_id]
        sid = turns[0]["session_id"]
        matches = list(sessions.glob("*" + sid + ".jsonl"))
        check(len(matches) == 1, "selected_native_session_missing_or_ambiguous")
        events, meta = project_native(matches[0].read_bytes(), run_id, turns, prior)
        path = "sources/native/" + run_id + ".jsonl"
        rd.put_lines(output / path, events)
        meta.update(path=path, projection_sha256=rd.sha((output / path).read_bytes()),
                    source_filename=matches[0].name)
        native_index.append(meta)
    original_manifest = rd.load_json(source / DATASET / "first-endpoint-current-manifest.json")
    catalog_ref = original_manifest["catalog"]
    catalog_blob = source_blob(source, Path(catalog_ref["path"]), output,
                               catalog_ref["sha256_bytes"], catalog_ref["sha256_lf"])
    catalog = read_blob(output, catalog_blob)
    selection_blob = source_blob(source, source / SELECTION, output)
    selection = read_blob(output, selection_blob)
    selected = {r["task"]: r for r in selection["cases"]}
    cases, reviews = [], []
    for item in catalog["cases"]:
        task = item["task"]
        entry = {"task": task, "bundles": {}, "report": None, "freeze": None}
        for key in ("freeze", "inputs", "packet"):
            ref = item["frozen_input_bundle"][key]
            entry["bundles"][key] = source_blob(source, Path(ref["path"]), output,
                                               ref["sha256_bytes"], ref["sha256_lf"])
        for key, original_key in (("report", "first_report"), ("freeze", "first_freeze")):
            ref = item[original_key]
            entry[key] = source_blob(source, Path(ref["path"]), output, ref.get("sha256_bytes"), ref["sha256_lf"])
        cases.append(entry)
        for provider in item["original_review_records"]:
            refs = item["original_review_records"][provider] + [selected[task]["selected_records"][provider]]
            seen = set()
            for ref in refs:
                source_path = Path(ref["path"])
                if str(source_path) in seen:
                    continue
                seen.add(str(source_path))
                blob = source_blob(source, source_path, output, ref["record_sha256_bytes"])
                reviews.append({"task": task, "provider": provider, "source": blob,
                                "selected": str(source_path) == selected[task]["selected_records"][provider]["path"],
                                "upstream_check": ref.get("check")})
    formal = source / DATASET / "formal-first-endpoints-20260920"
    formal_manifest_blob = source_blob(source, formal / "manifest.json", output)
    manifest = read_blob(output, formal_manifest_blob)
    formal_cases = []
    for row in manifest["cases"]:
        check(row["family_id"] != "H16" and row["case_id"] not in {"F11", "F12"}, "withdrawn_case")
        plan_path = Path(row["frozen_plan"]["path"]).resolve()
        check(plan_path.is_relative_to(source.resolve()) and
              rd.sha(plan_path.read_bytes()) == row["frozen_plan"]["sha256"], "formal_plan_hash_changed")
        frozen_packet = rd.load_json(plan_path)["packet"]
        safe_material(frozen_packet)
        packet_path = "sources/formal_packets/" + row["case_id"] + ".json"
        rd.put_json(output / packet_path, frozen_packet)
        formal_cases.append({"case_id": row["case_id"],
                             "review_packet": {"path": packet_path,
                                 "sha256": rd.sha((output / packet_path).read_bytes()),
                                 "source_relative_path": plan_path.relative_to(source).as_posix() + "#packet"},
                             "input": source_blob(source, formal / row["input_file"], output, row["input_sha256"]),
                             "packet": source_blob(source, Path(row["input_packet"]["path"]), output,
                                                   row["input_packet"]["sha256"]),
                             "plan_sha256_verified_locally": row["frozen_plan"]["sha256"]})
    sidecars = {name: source_blob(source, formal / name, output, digest)
                for name, digest in manifest["sidecars"].items()}
    author_rows = rd.load_lines(rd.local_file(output, sidecars["author-attempts.jsonl"]["path"]))
    author_sources = []
    for row in author_rows:
        ref = row["primary_outcome_record"]
        item = {"run_id": row["run_id"], "original": source_blob(source, Path(ref["path"]), output, ref["sha256"])}
        if row["completion_attempt"]:
            ref = row["completion_attempt"]["record"]
            item["completion"] = source_blob(source, Path(ref["path"]), output, ref["sha256"])
        author_sources.append(item)
    return {"native": native_index, "development_catalog": catalog_blob, "current_selection": selection_blob,
            "development_inputs": cases, "development_reviews": reviews,
            "formal_manifest": formal_manifest_blob, "formal_inputs": formal_cases,
            "formal_sidecars": sidecars, "author_sources": author_sources,
            "prior_manifest_sha256": rd.sha((prior / "manifest.json").read_bytes())}

def related_groups(catalog, prior):
    parent = {}
    def find(key):
        parent.setdefault(key, key)
        if parent[key] != key:
            parent[key] = find(parent[key])
        return parent[key]
    for c in catalog["cases"]:
        find(c["task"])
        for other in c.get("correlated_with", []):
            parent[find(c["task"])] = find(other)
    groups = {}
    for key in parent:
        groups.setdefault(find(key), []).append(key)
    old = history.family_map(prior)
    anchors = {"CAL-01": old["customer-service"], "CAL-02": old["video-production"]}
    result = {}
    for members in groups.values():
        ids = {anchors[m] for m in members if m in anchors}
        check(len(ids) <= 1, "conflicting_existing_family_anchors")
        family = next(iter(ids)) if ids else "research-family-" + digest_json(sorted(members))[:20]
        for member in members:
            result[member] = {"family_id": family, "related_task_ids": sorted(members),
                              "basis": "recorded_relationships_only", "independence_certified": False}
    return result

def derive(root, index):
    catalog, selection = read_blob(root, index["development_catalog"]), read_blob(root, index["current_selection"])
    original = {x["task"]: x for x in catalog["cases"]}
    selected = {x["task"]: x for x in selection["cases"]}
    check(len(original) == 23 and set(original) == set(selected) ==
          {x["task"] for x in index["development_inputs"]}, "development_input_coverage")
    groups = related_groups(catalog, root / "prior")
    tables = {"tasks.jsonl": [], "reviews.jsonl": [], "author_attempts.jsonl": [], "native_calls.jsonl": []}
    inputs, packets = {}, {}
    for entry in index["development_inputs"]:
        task, item = entry["task"], original[entry["task"]]
        check(item["held_out"] is False, "seen_development_task_promoted")
        bundle = {k: read_blob(root, ref) for k, ref in entry["bundles"].items()}
        data, packet, freeze = bundle["inputs"], bundle["packet"], bundle["freeze"]
        check(set(data) == {"brief", "report", "evidence"}, "incomplete_frozen_report_input")
        check(entry["bundles"]["inputs"]["sha256"] == freeze["inputs_file_sha256"] and
              entry["bundles"]["packet"]["sha256"] == freeze["packet_file_sha256"], "frozen_bundle_binding")
        check(rd.sha(data["report"].encode()) == packet["report_text_sha256"] ==
              item["first_report"]["sha256_lf"] == selected[task]["first_report_sha256_lf"], "first_report_binding")
        check(read_blob(root, entry["report"], False) == data["report"], "frozen_report_text_changed")
        payload = packet["payload"]
        check(set(payload) == {"system", "user"} and digest_json(payload) == packet["payload_sha256"],
              "packet_payload_binding")
        check(all(data[k] in payload["user"] for k in data), "full_input_not_in_payload")
        task_id = "dev-" + task
        inputs[task_id] = payload
        packets[task_id] = packet
        tables["tasks.jsonl"].append(
            {"task_id": task_id, "source_task_id": task, "cohort": "development_first_submission",
             "task_kind": "report_review", "task_origin": "observed_review_request",
             "input_path": "inputs/" + task_id + ".json", "report_sha256": packet["report_text_sha256"],
             "payload_sha256": packet["payload_sha256"], "gold_label": None,
             **groups[task], **POLICY})
    seen_reviews, slots = set(), Counter()
    for item in index["development_reviews"]:
        record = read_blob(root, item["source"])
        task_id = "dev-" + item["task"]
        packet, meta = packets[task_id], record.get("metadata", {})
        is_report = meta.get("report_text_sha256") == packet["report_text_sha256"]
        is_payload = meta.get("payload_sha256") == packet["payload_sha256"]
        if item["selected"]:
            check(is_report and is_payload and selected[item["task"]]["selected_records"][item["provider"]]
                  ["record_sha256_bytes"] == item["source"]["sha256"], "selected_review_binding")
            slots[(task_id, item["provider"])] += 1
        review_id = task_id + "-" + item["provider"] + "-" + item["source"]["sha256"][:20]
        check(review_id not in seen_reviews, "duplicate_development_review")
        seen_reviews.add(review_id)
        tables["reviews.jsonl"].append(
            {"review_id": review_id, "task_id": task_id, "provider": item["provider"],
             "selected_by_current_source_index": item["selected"], "record": item["source"]["path"],
             "report_binding_matches": is_report, "payload_binding_matches": is_payload,
             "response_complete": meta.get("response_complete"),
             "model_judgment": record.get("review"), "gold_label": None,
             "unit": "retained_review_record_not_request_count", **POLICY})
    check(len(slots) == 92 and all(v == 1 for v in slots.values()), "selected_review_slot_coverage")
    m = read_blob(root, index["formal_manifest"])
    declared = {c["case_id"]: c for c in m["cases"]}
    check(len(declared) == 22 and not({"F11", "F12"} & set(declared)) and
          {x["family_id"] for x in m["cases"]} - {"H16"} == {x["family_id"] for x in m["cases"]},
          "withdrawn_or_wrong_formal_case_inventory")
    check({x["case_id"] for x in index["formal_inputs"]} == set(declared), "formal_input_coverage")
    by_run = {}
    for entry in index["formal_inputs"]:
        row = declared[entry["case_id"]]
        payload = read_blob(root, entry["input"])
        components, packet = read_blob(root, entry["packet"]), read_blob(root, entry["review_packet"])
        check(entry["input"]["sha256"] == row["input_sha256"]
              and set(payload) == {"system", "user"} and payload == packet["payload"], "formal_input_binding")
        check(payload["user"] == "BRIEF\n" + components["brief"] + "\nREPORT\n" + components["report"]
              + "\nEVIDENCE\n" + components["evidence"]
              and rd.sha(components["report"].encode()) == packet["report_text_sha256"],
              "formal_frozen_components_changed")
        check(payload["user"].startswith("BRIEF\n") and "\nREPORT\n" in payload["user"]
              and "\nEVIDENCE\n" in payload["user"], "formal_input_sections_missing")
        check(rd.sha(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()) ==
              packet["payload_sha256"], "formal_packet_payload_changed")
        task_id = "formal-" + row["case_id"]
        inputs[task_id], packets[task_id], by_run[row["run_id"]] = payload, packet, task_id
        tables["tasks.jsonl"].append(
            {"task_id": task_id, "source_task_id": row["case_id"], "cohort": "historical_paired_study",
             "family_id": "formal-" + row["family_id"], "source_family_id": row["family_id"],
             "condition": row["condition"], "analysis_scope": row["analysis_scope"],
             "task_kind": "report_review", "task_origin": "observed_review_request",
             "input_path": "inputs/" + task_id + ".json", "report_sha256": packet["report_text_sha256"],
             "payload_sha256": packet["payload_sha256"], "gold_label": None, **POLICY})
    sidecars = {name: rd.load_lines(rd.local_file(root, ref["path"])) for name, ref in index["formal_sidecars"].items()}
    for name, ref in index["formal_sidecars"].items():
        check(ref["sha256"] == m["sidecars"][name] == rd.sha(rd.local_file(root, ref["path"]).read_bytes()),
              "formal_sidecar_changed")
    for seq, row in enumerate(sidecars["review-records.jsonl"], 1):
        provenance, record = row["provenance"], row["original_record"]
        task_id = by_run[provenance["run_id"]]
        packet, meta = packets[task_id], record.get("metadata", {})
        bound = meta.get("payload_sha256") == packet["payload_sha256"]
        report_bound = meta.get("report_text_sha256") == packet["report_text_sha256"]
        if provenance["effective_valid_review"]:
            check(bound and report_bound, "formal_valid_review_binding")
        tables["reviews.jsonl"].append(
            {"review_id": f"formal-record-{seq:03d}", "task_id": task_id,
             "provider": provenance["provider"], "source_row": seq,
             "record": index["formal_sidecars"]["review-records.jsonl"]["path"],
             "selected_by_current_source_index": provenance["effective_valid_review"],
             "response_complete": provenance["response_complete"],
             "report_binding_matches": report_bound, "payload_binding_matches": bound,
             "model_judgment": record.get("review"), "gold_label": None,
             "unit": "retained_review_record_not_request_count", **POLICY})
    author_refs = {a["run_id"]: a for a in index["author_sources"]}
    for row in sidecars["author-attempts.jsonl"]:
        check(row["family_id"] != "H16" and row["primary_failure_not_replaced"] is True, "author_failure_removed")
        original_outcome = read_blob(root, author_refs[row["run_id"]]["original"])
        check(original_outcome == row["original"], "author_original_outcome_binding")
        for kind, outcome in [("original", row["original"]),
                              ("completion", row["completion_attempt"]["outcome"] if row["completion_attempt"] else None)]:
            if outcome is None:
                continue
            if kind == "completion":
                check(read_blob(root, author_refs[row["run_id"]]["completion"]) == outcome, "completion_outcome_binding")
            tables["author_attempts.jsonl"].append(
                {"attempt_id": row["run_id"] + "-" + kind, "run_id": row["run_id"],
                 "family_id": "formal-" + row["family_id"], "condition": row["condition"],
                 "attempt_kind": kind, "replaces_original": False,
                 "original_complete": row["primary_complete"] if kind == "original" else None,
                 "original_attempt_id": row["run_id"] + "-original" if kind == "completion" else None,
                 "outcome_record": outcome, **POLICY})
    tables["source_adjudications.jsonl"] = [
        {"task_id": "formal-" + row["case_id"], "label_status": "inherited_source_adjudication_not_newly_verified",
         "source_row": n, "source_record": row, "gold_label": None, **POLICY}
        for n, row in enumerate(sidecars["grading-labels.jsonl"], 1)]
    for item in index["native"]:
        path = rd.local_file(root, item["path"])
        check(rd.sha(path.read_bytes()) == item["projection_sha256"], "native_projection_changed")
        events = rd.load_lines(path)
        rows = native_calls(events)
        check(all(x["run_id"] == item["run_id"] for x in rows), "native_run_binding")
        prior_turns = [t for t in rd.load_lines(root / "prior/turns.jsonl") if t["run_id"] == item["run_id"]]
        check({t["session_id"] for t in prior_turns} == {item["session_id"]}
              and item["turn_count"] == len(prior_turns), "native_prior_identity_changed")
        valid_kinds = {"tool_call", "tool_result", "assistant_message", "task_started",
                       "task_complete", "context_compacted"}
        check(all(e["kind"] in valid_kinds and e["run_id"] == item["run_id"] for e in events),
              "unexpected_native_event")
        lines = [e["source_line"] for e in events]
        check(lines == sorted(set(lines)), "native_source_order_changed")
        for t in prior_turns:
            part = [e for e in events if e["turn_id"] == t["turn_id"]]
            check(sum(e["kind"] == "task_started" for e in part) == 1
                  and sum(e["kind"] == "task_complete" for e in part) == 1, "native_turn_boundary_changed")
            final = [e["text"].strip() for e in part
                     if e["kind"] == "assistant_message" and e["channel"] == "final"]
            expected = rd.local_file(root / "prior", t["final_message_path"]).read_text(encoding="utf-8").strip()
            check(final == [expected], "native_final_binding_changed")
        for e in events:
            if e["kind"] == "tool_result":
                check((e["output"] is None) == e["redacted"], "native_redaction_flag_changed")
                if e["output"] is not None:
                    safe_material(e["output"])
        tables["native_calls.jsonl"].extend(rows)
    check(len(index["native"]) == 4 and {x["run_id"] for x in index["native"]} == set(history.RUNS),
          "native_session_coverage_changed")
    return tables, inputs

def summarize(tables):
    tasks, reviews, native = tables["tasks.jsonl"], tables["reviews.jsonl"], tables["native_calls.jsonl"]
    dev = [r for r in tasks if r["cohort"] == "development_first_submission"]
    formal = [r for r in tasks if r["cohort"] == "historical_paired_study"]
    authors = tables["author_attempts.jsonl"]
    return {"frozen_review_inputs": len(tasks), "development_report_inputs": len(dev),
            "development_related_groups": len({x["family_id"] for x in dev}),
            "historical_paired_report_inputs": len(formal), "historical_paired_groups": len({x["family_id"] for x in formal}),
            "retained_review_records": len(reviews),
            "current_development_review_slots": sum(r["selected_by_current_source_index"] for r in reviews if r["task_id"].startswith("dev-")),
            "current_paired_review_slots": sum(r["selected_by_current_source_index"] for r in reviews if r["task_id"].startswith("formal-")),
            "author_original_attempts": sum(r["attempt_kind"] == "original" for r in authors),
            "author_original_incomplete": sum(r["original_complete"] is False for r in authors),
            "author_completion_attempts": sum(r["attempt_kind"] == "completion" for r in authors),
            "native_executor_batches": len(native), "native_available_outputs": sum(r["output_available"] for r in native),
            "native_redacted_outputs": sum(not r["output_available"] for r in native),
            "native_web_related_batches": sum(r["web_related_executor_batch"] for r in native),
            "native_outputs_with_truncation_markers": sum(r["truncation_marker_present"] for r in native),
            "withdrawn_cases_reintroduced": 0, "new_model_calls": 0, "training_records": 0, "held_out_tasks": 0}

CARD = """# 研究输入与实际工具观察 v0.3

本包在 prior/ 中保留未经修改的 v0.2，以及四个已选会话恢复的原生执行器返回。
它还提供23份开发题首稿和22份历史对照研究送评输入。它们是报告评审任务，
不是45个独立研究家族，也不补写这些报告缺失的作者执行过程。
关联题、条件对照和补跑保留家族与原始关系，全部按 development 复用。

sources/native 保存可见消息、执行器调用和实际返回文本，排除隐藏推理、系统提示、
用户环境配置、压缩摘要及无关全局上下文输出；保留源文件、源行和被删输出摘要。
最终消息中仅移除已核对的客户端记忆引用脚注，正文不改写。
一个执行器批次可包含多个工具动作，不与上版动作数相加。
已恢复的是当时模型看到的文本，截断、摘要和工具限制保持原样，
并非完整网页镜像或可重新执行的网络环境。

inputs 仅含冻结 system/user；reviews 是原模型判断，source_adjudications 是既有裁定，
二者与输入分开，gold_label 不升级。迟到评审、失败和补跑不覆盖第一次记录。
author_attempts 保留原失败与后续完成。额度错误不归因于模型研究能力。
H16/F11/F12遵守原任务明确撤回，未读取其审计备份或恢复正文。
原有12题设计及事后排除仍在来源清单中记录，当前11个题族不代表质量提高。

标准库命令：
    python -B verify_dataset.py verify .
    python -B verify_dataset.py export-input . --case dev-U01 --output ../U01-input.json
    python -B verify_dataset.py export-input . --case formal-F01 --output ../F01-input.json
    python -B verify_dataset.py observe . --run run-03 --output ../run-03-observations.jsonl

导出拒绝覆盖既有文件，observe只导出记录，不执行其中命令、不联网、不调用模型。
原始来源在本地核对，经过删减的原始会话不随包分发；哈希证明冻结一致性，不证明事实正确。
本包仅限私有开发诊断。来源许可证保留于 prior/base/UPSTREAM_LICENSE.txt。
"""

def build_dataset(source, sessions, prior, output):
    source, sessions, prior, output = map(lambda p: Path(p).resolve(), (source, sessions, prior, output))
    check(not output.is_relative_to(source) and not output.is_relative_to(sessions)
          and not output.is_relative_to(prior) and not prior.is_relative_to(output), "overlapping_dataset_roots")
    if (output / "manifest.json").exists():
        return verify_dataset(output)
    check(not output.exists() or not any(output.iterdir()), "output_must_be_empty")
    history.verify_dataset(prior)
    index = collect_sources(source, sessions, prior, output)
    rd.put_json(output / "source_index.json", index)
    tables, inputs = derive(output, index)
    for name, rows in tables.items():
        rd.put_lines(output / name, rows)
    for task_id, payload in inputs.items():
        rd.put_json(output / "inputs" / (task_id + ".json"), payload)
    for filename, original in [("verify_dataset.py", Path(__file__)),
                               ("research_history.py", Path(history.__file__)),
                               ("research_dataset.py", Path(rd.__file__))]:
        rd.put(output / filename, original.read_bytes())
    rd.put(output / "LICENSE", (prior / "LICENSE").read_bytes())
    rd.put(output / "DATA_CARD.md", CARD.encode())
    files = {p.relative_to(output).as_posix(): rd.sha(p.read_bytes())
             for p in sorted(output.rglob("*")) if p.is_file()}
    rd.put_json(output / "manifest.json", {"schema_version": VERSION, "summary": summarize(tables),
        "source_index_sha256": rd.sha(rd.encoded(index)), "prior_manifest_sha256": index["prior_manifest_sha256"],
        "rights": rd.RIGHTS, "split": "development", "files": files})
    return verify_dataset(output)

def verify_dataset(root):
    root = Path(root).resolve()
    m = rd.load_json(root / "manifest.json")
    check(m["schema_version"] == VERSION and m["rights"] == rd.RIGHTS and m["split"] == "development",
          "corpus_policy_changed")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    check(actual == set(m["files"]) | {"manifest.json"}, "corpus_file_inventory")
    for rel, digest in m["files"].items():
        check(rd.sha(rd.local_file(root, rel).read_bytes()) == digest, "corpus_file_hash:" + rel)
    history.verify_dataset(root / "prior")
    index = rd.load_json(root / "source_index.json")
    check(rd.sha(rd.encoded(index)) == m["source_index_sha256"], "corpus_source_index_changed")
    check(rd.sha((root / "prior/manifest.json").read_bytes()) ==
          index["prior_manifest_sha256"] == m["prior_manifest_sha256"], "prior_version_changed")
    tables, inputs = derive(root, index)
    for name, expected in tables.items():
        check(rd.load_lines(root / name) == expected, "corpus_derived_view_changed:" + name)
    for task_id, payload in inputs.items():
        check(rd.load_json(root / "inputs" / (task_id + ".json")) == payload, "corpus_export_input_changed")
    check(summarize(tables) == m["summary"], "corpus_counts_changed")
    return {"verified": True, **m["summary"], "verified_files": len(m["files"])}

def export_input(root, case, destination):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    verify_dataset(root)
    ids = {r["task_id"] for r in rd.load_lines(root / "tasks.jsonl")}
    check(case in ids, "unknown_or_withdrawn_case")
    check(not destination.is_relative_to(root), "export_must_be_outside_dataset")
    check(not destination.exists(), "export_destination_exists")
    payload = rd.load_json(root / "inputs" / (case + ".json"))
    check(set(payload) == {"system", "user"}, "labels_or_extra_fields_in_export")
    rd.put_json(destination, payload)
    return {"task_id": case, "output_sha256": rd.sha(destination.read_bytes()), "labels_included": False}

def observations(root, run_id, destination):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    verify_dataset(root)
    check(run_id in history.RUNS, "unknown_run")
    check(not destination.is_relative_to(root) and not destination.exists(), "invalid_observation_destination")
    index = rd.load_json(root / "source_index.json")
    entry = next(x for x in index["native"] if x["run_id"] == run_id)
    rows = rd.load_lines(rd.local_file(root, entry["path"]))
    rd.put_lines(destination, rows)
    return {"run_id": run_id, "events": len(rows), "executed_commands": 0,
            "output_sha256": rd.sha(destination.read_bytes())}

def make_archive(root, destination):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    verify_dataset(root)
    check(not destination.is_relative_to(root), "archive_must_be_outside_dataset")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                info = zipfile.ZipInfo(p.relative_to(root).as_posix(), (1980, 1, 1, 0, 0, 0))
                info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o600 << 16
                archive.writestr(info, p.read_bytes())
    raw = buffer.getvalue()
    rd.put(destination, raw)
    return {"archive": str(destination), "bytes": len(raw), "sha256": rd.sha(raw)}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    build = commands.add_parser("build")
    for name in ("source", "sessions", "prior", "output"):
        build.add_argument("--" + name, type=Path, required=True)
    for name in ("verify", "pack", "export-input", "observe"):
        p = commands.add_parser(name)
        p.add_argument("dataset", type=Path)
        if name == "pack":
            p.add_argument("destination", type=Path)
        elif name in {"export-input", "observe"}:
            p.add_argument("--case" if name == "export-input" else "--run", required=True)
            p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.operation == "build":
        result = build_dataset(args.source, args.sessions, args.prior, args.output)
    elif args.operation == "verify":
        result = verify_dataset(args.dataset)
    elif args.operation == "pack":
        result = make_archive(args.dataset, args.destination)
    elif args.operation == "export-input":
        result = export_input(args.dataset, args.case, args.output)
    else:
        result = observations(args.dataset, args.run, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
