"""Import retained research runs and review histories, without executing archived actions."""
from __future__ import annotations
import argparse
import importlib.util
import io
import json
import re
import subprocess
import zipfile
from collections import Counter
from pathlib import Path

_HELPER = Path(__file__).with_name("research_dataset.py")
_spec = importlib.util.spec_from_file_location("research_dataset_helper", _HELPER)
rd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rd)

VERSION = "research-history-v2"
RUNS = {"run-01": ("customer-service", "framework", 1),
        "run-02": ("customer-service", "baseline", 1),
        "run-03": ("video-production", "framework", 3),
        "run-04": ("video-production", "baseline", 3)}
SEMANTIC = Path("evals/semantic_diagnostics/reviews/2026-09-08")
REPORT_NAMES = ("original-baseline.md", "original-framework.md",
                "before-model-diagnostics.md", "repaired.md")
SECRET = re.compile(r"(?<![A-Za-z0-9_-])(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|"
                    r"sk-(?:proj-|ant-)?[A-Za-z0-9_-]{24,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")
BASE = {"split": "development", "rights": rd.RIGHTS}
ALLOWED_ITEMS = {"agent_message", "command_execution", "file_change", "web_search"}
ALLOWED_EVENTS = {"thread.started", "turn.started", "turn.completed", "turn.failed",
                  "item.started", "item.updated", "item.completed", "error"}

def check(condition, reason):
    if not condition:
        raise ValueError(reason)

def scrub(value, cwd):
    """Tokenize known local roots; retain commands as inert text."""
    if isinstance(value, dict):
        return {key: scrub(item, cwd) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub(item, cwd) for item in value]
    if not isinstance(value, str):
        return value
    roots = [(cwd, "<RUN_WORKSPACE>"),
             (r"D:\Codex\industry-research-framework-field-eval", "<FIELD_EVAL>"),
             (r"D:\Codex\_home", "<CODEX_HOME>"),
             (r"C:\Users\luosong03", "<USER_PROFILE>")]
    for original, replacement in roots:
        if not original:
            continue
        for variant in (original.replace("\\", "\\\\"), original,
                        original.replace("\\", "/")):
            value = value.replace(variant, replacement)
    check(not SECRET.search(value), "credential_like_content")
    return value

def project_capture(raw, cwd):
    """Expose only the recorded visible stream, with source line hashes."""
    rows, excluded = [], []
    for line_number, line in enumerate(raw.split(b"\n"), 1):
        if not line.strip():
            continue
        obj = json.loads(line)
        item = obj.get("item", {})
        if item.get("type") in {"reasoning", "analysis"}:
            excluded.append({"source_line": line_number, "reason": "hidden_reasoning",
                             "source_line_sha256": rd.sha(line)})
            continue
        check(obj.get("type") in ALLOWED_EVENTS, "unknown_capture_event")
        if item:
            check(item.get("type") in ALLOWED_ITEMS, "unknown_capture_item")
        check(set(obj) <= {"type", "item", "thread_id", "usage", "error", "message"}, "unknown_capture_fields")
        fields = {
            "agent_message": {"id", "type", "text"},
            "command_execution": {"id", "type", "command", "aggregated_output", "exit_code", "status"},
            "file_change": {"id", "type", "changes", "status"},
            "web_search": {"id", "type", "query", "action"}}
        if item:
            check(set(item) <= fields[item["type"]], "unknown_capture_item_fields")
        redactions = []
        if item.get("type") == "command_execution":
            command = item.get("command", "").lower().replace("\\", "/")
            if "_home" in command or "/memories/" in command:
                output = item.get("aggregated_output", "")
                if output:
                    redactions.append({"field": "item.aggregated_output",
                                       "reason": "unrelated_global_context",
                                       "original_sha256": rd.sha(output.encode("utf-8"))})
                    item["aggregated_output"] = "[OMITTED: unrelated global context; digest retained]"
        rows.append({"source_line": line_number, "source_line_sha256": rd.sha(line),
                     "redactions": redactions, "payload": scrub(obj, cwd)})
    return rows, excluded

def derive_turn(run_id, turn, capture, prompt, message, result_turn, command):
    turn_id = f"{run_id}-turn-{turn}"
    events, grouped = [], {}
    for seq, row in enumerate(capture, 1):
        p = row["payload"]
        event = {"event_id": f"{turn_id}-event-{seq:04d}", "run_id": run_id,
                 "turn_id": turn_id, "sequence": seq, **row}
        events.append(event)
        item = p.get("item", {})
        if item.get("type") in {"command_execution", "file_change", "web_search"}:
            grouped.setdefault(item["id"], []).append(event)
    actions, failures = [], []
    for native_id, group in grouped.items():
        item = group[-1]["payload"]["item"]
        kind = item["type"]
        check(all(x["payload"]["item"]["type"] == kind for x in group), "action_type_changed")
        started = [x for x in group if x["payload"]["type"] == "item.started"]
        completed = [x for x in group if x["payload"]["type"] == "item.completed"]
        check(len(started) <= 1 and len(completed) <= 1, "duplicate_action_boundary")
        if started and completed:
            check(started[0]["sequence"] < completed[0]["sequence"], "reversed_action_boundary")
            if kind == "command_execution":
                check(started[0]["payload"]["item"]["command"] == item["command"], "command_changed_between_boundaries")
        action_id = f"{turn_id}-{native_id}"
        action = {"action_id": action_id, "run_id": run_id, "turn_id": turn_id,
                  "kind": kind, "event_ids": [e["event_id"] for e in group],
                  "started": bool(started), "completed": bool(completed),
                  "decision_basis": "visible_action_only", "private_reasoning": None}
        if kind == "command_execution":
            redacted = any(e["redactions"] for e in group)
            action.update(command=item["command"], exit_code=item["exit_code"],
                          status=item["status"],
                          observation_kind=("redacted_output" if redacted else "recorded_stdout"),
                          output_available=bool(completed) and not redacted)
            if completed and (item["exit_code"] not in (0, None) or item["status"] == "failed"):
                failures.append({"record_id": action_id + "-nonzero", "action_id": action_id,
                                 "kind": "command_nonzero_exit", "exit_code": item["exit_code"],
                                 "task_failure": "not_assessed", "semantic_cause": "not_assessed",
                                 "evidence_event_id": completed[0]["event_id"]})
        else:
            action.update(observation_kind="action_metadata_only", output_available=False)
            if kind == "web_search":
                action["action"] = item["action"]
            else:
                action["changes"] = item["changes"]
        actions.append(action)
    terminal = [x["payload"] for x in events if x["payload"]["type"] in {"turn.completed", "turn.failed"}]
    messages = [x["payload"]["item"]["text"] for x in events
                if x["payload"].get("item", {}).get("type") == "agent_message"]
    usage = [x["usage"] for x in terminal if "usage" in x]
    check(usage == result_turn.get("usage", []), "turn_usage_binding_mismatch")
    requested_model = next((v.split("=", 1)[1].strip('"') for v in command["args"] if v.startswith("model=")), None)
    check(bool(requested_model), "missing_requested_model")
    check(len(terminal) <= 1, "duplicate_turn_terminal")
    info = {"turn_id": turn_id, "run_id": run_id, "turn": turn,
            "previous_turn_id": f"{run_id}-turn-{turn-1}" if turn > 1 else None,
            "session_id": result_turn["session_id"],
            "event_thread_ids": sorted({x["payload"]["thread_id"] for x in events
                                       if x["payload"]["type"] == "thread.started"}),
            "model_requested": requested_model, "model_returned": None,
            "model_identity_basis": "launch_configuration_only",
            "runtime_status": terminal[0]["type"] if terminal else "terminal_missing",
            "exit_code": result_turn["exit_code"], "timeout": result_turn["timeout"],
            "elapsed_seconds": result_turn["elapsed_seconds"], "usage": usage,
            "instruction_boundary": "explicit_pause" if "先停在这里" in prompt else "continue_or_deliver",
            "final_message_matches_event": bool(messages) and messages[-1].strip() == message.strip(),
            "event_count": len(events), "action_count": len(actions),
            "unmatched_actions": sum(not (x["started"] and x["completed"]) for x in actions),
            "quality_outcome": "not_assessed", "replayable_external_environment": False, **BASE}
    check(info["event_thread_ids"] == [info["session_id"]], "session_binding_mismatch")
    return info, events, actions, failures

def copy_source(source, destination, output, inventory, source_group, transform=None):
    check(source.is_file() and not source.is_symlink(), "missing_or_linked_source")
    raw = source.read_bytes()
    body = transform(raw) if transform else raw
    check(not SECRET.search(body.decode("utf-8-sig")), "credential_like_content")
    rd.put(output / destination, body)
    inventory.append({"path": destination, "source_group": source_group,
                      "source_relative_path": source.name,
                      "original_sha256": rd.sha(raw), "packaged_sha256": rd.sha(body),
                      "transformed": raw != body})
    return inventory[-1]

def import_sources(source, runtime, base, output):
    rd.verify_dataset(base)
    for p in sorted(base.rglob("*")):
        if p.is_file():
            rd.put(output / "base" / p.relative_to(base), p.read_bytes())
    inventory, run_index, artifact_index = [], [], []
    for run_id, (report, condition, count) in RUNS.items():
        directory = runtime / run_id
        result = rd.load_json(directory / "result.json")
        cwd = result["run"]["cwd"]
        check(result["run"]["condition"] == condition, "runtime_condition_mismatch")
        check([t["turn"] for t in result["turns"]] == list(range(1, count+1)), "runtime_turn_inventory")
        group, prefix = "calibration-20260907/" + run_id, "sources/runtime/" + run_id + "/"
        transform_json = lambda raw: rd.encoded(scrub(json.loads(raw), cwd))
        transform_text = lambda raw: scrub(raw.decode("utf-8-sig"), cwd).encode("utf-8")
        entry = copy_source(directory / "result.json", prefix + "result.json",
                            output, inventory, group, transform_json)
        entry["source_relative_path"] = run_id + "/result.json"
        turns = []
        for n in range(1, count+1):
            stem = f"turn-{n}"
            for suffix, transform in [("prompt.txt", transform_text), ("message.md", transform_text),
                                      ("command.json", transform_json)]:
                rel = stem + "." + suffix
                e = copy_source(directory / rel, prefix + rel, output, inventory, group, transform)
                e["source_relative_path"] = run_id + "/" + rel
            raw_path = directory / (stem + ".events.jsonl")
            raw = raw_path.read_bytes()
            rows, excluded = project_capture(raw, cwd)
            path = prefix + stem + ".visible.jsonl"
            rd.put_lines(output / path, rows)
            inventory.append({"path": path, "source_group": group,
                              "source_relative_path": run_id + "/" + raw_path.name,
                              "original_sha256": rd.sha(raw),
                              "packaged_sha256": rd.sha((output / path).read_bytes()), "transformed": True})
            turns.append({"turn": n, "capture": path, "excluded": excluded,
                          "original_line_count": sum(bool(x.strip()) for x in raw.split(b"\n"))})
        roots = []
        for metadata in sorted((directory / "checkpoints").glob("*.capture.json")):
            meta = rd.load_json(metadata)
            name = metadata.name.removesuffix(".capture.json")
            captured = directory / "checkpoints" / name
            check(meta["stable_during_copy"] and meta.get("boundary_confirmed"), "unstable_checkpoint")
            for rel, digest in meta["files"].items():
                p = rd.local_file(captured, rel.replace("\\", "/"))
                check(rd.sha(p.read_bytes()) == digest, "checkpoint_source_hash_mismatch")
            dest = prefix + "checkpoints/" + metadata.name
            e = copy_source(metadata, dest, output, inventory, group)
            e["source_relative_path"] = run_id + "/checkpoints/" + metadata.name
            roots.append((captured, "verified_turn_checkpoint", meta["completed_turn"], dest))
        if not roots and (directory / "workspace").exists():
            roots.append((directory / "workspace", "post_run_workspace_without_capture_boundary", count, None))
        for capture_root, boundary, n, metadata_path in roots:
            for p in sorted(capture_root.rglob("*")):
                if not p.is_file() or ".agents" in p.parts or p.suffix not in {".md", ".csv", ".json", ".jsonl"}:
                    continue
                check(p.resolve().is_relative_to(directory.resolve()), "source_path_escape")
                local, relative = p.relative_to(directory).as_posix(), p.relative_to(capture_root).as_posix()
                dest = prefix + local
                e = copy_source(p, dest, output, inventory, group, transform_text)
                e["source_relative_path"] = run_id + "/" + local
                artifact_index.append({"artifact_id": run_id + ":" + local, "run_id": run_id,
                                       "turn": n, "path": dest, "relative_artifact": relative,
                                       "boundary": boundary, "capture_metadata": metadata_path,
                                       "original_sha256": e["original_sha256"]})
        run_index.append({"run_id": run_id, "report": report, "condition": condition, "prefix": prefix, "turns": turns})
    for name, relative in (("reports", rd.BUNDLE), ("semantic", SEMANTIC)):
        bundle = source / relative
        manifest = rd.load_json(bundle / "bundle-manifest.json")
        if name == "semantic":
            selected = sorted(manifest["files"])
        else:
            selected = ["ADJUDICATION.md", "calibration-provenance.json"]
            for report in rd.REPORTS:
                selected.extend("reports/" + report + "/" + f for f in REPORT_NAMES)
                selected.extend(p.relative_to(bundle).as_posix()
                                for p in sorted((bundle / "reports" / report / "reviews").glob("*.json")))
        for rel in selected:
            p = rd.local_file(bundle, rel)
            check(rd.normalized_hash(p) == manifest["files"][rel], "upstream_file_hash_mismatch")
            e = copy_source(p, "sources/" + name + "/" + rel, output, inventory, "research-toolkit")
            e.update(source_relative_path=(relative / rel).as_posix(), upstream_sha256_lf=manifest["files"][rel])
        e = copy_source(bundle / "bundle-manifest.json", "sources/" + name + "/bundle-manifest.json",
                        output, inventory, "research-toolkit")
        e["source_relative_path"] = (relative / "bundle-manifest.json").as_posix()
    return {"runs": run_index, "artifacts": artifact_index, "files": inventory,
            "source_revision": subprocess.check_output(
                ["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip(),
            "base_manifest_sha256": rd.sha((base / "manifest.json").read_bytes()),
            "original_source_checks": "verified_locally_at_build; transformed originals are not distributed"}

def family_map(root):
    rows = rd.load_lines(root / "base/tasks.jsonl")
    return {name: next(r["family_id"] for r in rows
                      if r["profile"] == "archived-review-v1" and name in r["artifacts"]["report"])
            for name in rd.REPORTS}

def semantic_views(root):
    directory = root / "sources/semantic"
    get = lambda p: rd.load_json(rd.local_file(directory, p))
    catalogs = get("source-catalogs/cases.json")["cases"] + get("source-catalogs/additional-cases.json")["cases"]
    by_case = {x["id"]: x for x in catalogs}
    check(len(by_case) == len(catalogs), "duplicate_semantic_case")
    versions = {}
    for case in catalogs:
        versions[case["id"]] = {"case_version_id": case["id"], "case_id": case["id"],
                                "revision_of": None, "revision_reason": None, "case": case,
                                "task_origin": "synthetic", "label_status": "author_proposed_uncalibrated",
                                "gold_label": None, **BASE}
    for rev in get("source-catalogs/revisions.json")["revisions"]:
        base = by_case[rev["case_id"]]
        digest = rd.sha(json.dumps(base, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
        check(digest == rev["base_case_sha256"], "revision_base_hash_mismatch")
        versions[rev["revision_id"]] = {"case_version_id": rev["revision_id"],
                                       "case_id": rev["case_id"], "revision_of": rev["case_id"],
                                       "revision_reason": rev["reason"], "case": {**base, **rev["changes"]},
                                       "task_origin": "synthetic", "label_status": "author_proposed_uncalibrated",
                                       "gold_label": None, **BASE}
    mapping = get("mapping.json")["jobs"]
    mapping["revised-controls-02"] = get("revisions-mapping.json")["items"]
    run_index = get("run-index.json")
    check(run_index["held_out"] is False and run_index["author_labels_are_truth"] is False,
          "semantic_source_label_boundary_changed")
    check(len(catalogs) == run_index["unique_original_pairs"], "semantic_case_count_mismatch")
    episodes, judgments, review_events = [], [], []
    for record in run_index["records"]:
        source_input, request, response, attempt = [get(record[k]) for k in ("input", "request", "final", "attempt")]
        check(request["messages"] == [{"role": k, "content": source_input[k]} for k in ("system", "user")],
              "semantic_request_input_mismatch")
        digest = rd.normalized_hash(directory / record["input"])
        check(response["input_sha256"] == digest and attempt["input_sha256"] == digest,
              "semantic_input_hash_mismatch")
        check(json.loads(response["content"]) == response["parsed"], "semantic_response_content_mismatch")
        check(response["finish_reason"] == "stop", "semantic_incomplete_response")
        check(response["model_returned"] == attempt["model_returned"]
              and request["model"] == attempt["model_requested"], "semantic_model_binding_mismatch")
        provided, _ = json.JSONDecoder().raw_decode(source_input["user"].lstrip())
        inputs, outputs = {x["id"]: x for x in provided}, {x["id"]: x for x in response["parsed"]["cases"]}
        maps = mapping[record["job"]]
        check(len(inputs) == len(provided) and len(outputs) == len(response["parsed"]["cases"])
              and set(inputs) == set(outputs) == {x["id"] for x in maps}, "semantic_case_coverage_mismatch")
        episode_id = "semantic-" + record["provider"] + "-" + record["job"]
        episodes.append({"episode_id": episode_id, "provider": record["provider"], "job": record["job"],
                         "actor_kind": "archived_model_response", "task_origin": "synthetic",
                         "runtime_status": "completed", "quality_outcome": "not_assessed",
                         "model_requested": request["model"], "model_returned": response["model_returned"],
                         "usage": response["usage"],
                         "sources": {k: "sources/semantic/" + record[k] for k in ("input", "request", "final", "attempt")},
                         "judgment_count": len(maps) * 2, **BASE})
        for sequence, kind in enumerate(("request", "final"), 1):
            review_events.append({"event_id": episode_id + "-" + kind, "episode_id": episode_id,
                                  "sequence": sequence, "kind": "model_" + kind,
                                  "source_path": "sources/semantic/" + record[kind]})
        for m in maps:
            version = versions[m.get("revision_id", m.get("original_id"))]
            input_row, result = inputs[m["id"]], outputs[m["id"]]
            check(input_row["evidence"] == version["case"]["evidence"], "semantic_evidence_mismatch")
            for side in ("A", "B"):
                role = m[side]
                check(input_row[side] == version["case"][role], "semantic_orientation_mismatch")
                j = result[side]
                check(j["judgment"] in {"acceptable", "flawed", "insufficient_context"}
                      and isinstance(j["critical_fact_error"], bool), "invalid_semantic_judgment")
                judgments.append({"judgment_id": episode_id + "-" + m["id"] + "-" + side,
                                  "episode_id": episode_id, "case_version_id": version["case_version_id"],
                                  "case_id": version["case_id"], "provider": record["provider"],
                                  "job": record["job"], "side": side, "author_designated_role": role,
                                  "text_sha256": rd.sha(input_row[side].encode()),
                                  "model_judgment": j, "gold_label": None, **BASE})
    check(len(episodes) == run_index["attempts"], "semantic_episode_count_mismatch")
    comparisons = []
    for after in judgments:
        if after["job"] != "order-control":
            continue
        before = next(j for j in judgments if j["job"] in {"batch-01", "batch-02"}
                      and all(j[k] == after[k] for k in ("provider", "case_version_id", "author_designated_role")))
        check(before["text_sha256"] == after["text_sha256"], "order_control_text_changed")
        comparisons.append({"comparison_id": after["judgment_id"] + "-vs-original",
                            "before": before["judgment_id"], "after": after["judgment_id"],
                            "changed_fields": [k for k in ("judgment", "critical_fact_error")
                                               if before["model_judgment"][k] != after["model_judgment"][k]],
                            "causal_claim": False, "confounds": ["order", "batch_composition", "separate_call"]})
    return {"semantic_cases.jsonl": list(versions.values()), "semantic_episodes.jsonl": episodes,
            "semantic_events.jsonl": review_events, "judgments.jsonl": judgments,
            "comparisons.jsonl": comparisons}

def derive_views(root, index):
    families = family_map(root)
    tables = {name: [] for name in ("runs.jsonl", "turns.jsonl", "events.jsonl", "actions.jsonl",
                                    "failures.jsonl", "artifacts.jsonl", "report_versions.jsonl", "lineage.jsonl")}
    inventory = {x["path"]: x for x in index["files"]}
    check(len(inventory) == len(index["files"]), "duplicate_source_path")
    check({x["run_id"] for x in index["runs"]} == set(RUNS) and len(index["runs"]) == len(RUNS),
          "run_coverage_mismatch")
    for entry in index["runs"]:
        run_id, prefix = entry["run_id"], entry["prefix"]
        report, condition, count = RUNS[run_id]
        check(entry["report"] == report and entry["condition"] == condition, "run_identity_mismatch")
        check([t["turn"] for t in entry["turns"]] == list(range(1, count+1)), "turn_coverage_mismatch")
        result = rd.load_json(rd.local_file(root, prefix + "result.json"))
        check(result["run"]["id"] == run_id and result["run"]["condition"] == condition,
              "run_result_identity_mismatch")
        check(len(result["turns"]) == count, "result_turn_coverage_mismatch")
        turn_rows = []
        for t in entry["turns"]:
            n = t["turn"]
            stem = prefix + f"turn-{n}"
            prompt = rd.local_file(root, stem + ".prompt.txt").read_text(encoding="utf-8")
            message = rd.local_file(root, stem + ".message.md").read_text(encoding="utf-8")
            command = rd.load_json(rd.local_file(root, stem + ".command.json"))
            rows = rd.load_lines(rd.local_file(root, t["capture"]))
            positions = [x["source_line"] for x in rows] + [x["source_line"] for x in t["excluded"]]
            check(sorted(positions) == list(range(1, t["original_line_count"]+1)), "source_event_coverage_mismatch")
            info, events, actions, failures = derive_turn(run_id, n, rows, prompt, message, result["turns"][n-1], command)
            info.update(family_id=families[report], prompt_path=stem + ".prompt.txt",
                        final_message_path=stem + ".message.md", omitted_reasoning_events=len(t["excluded"]))
            tables["turns.jsonl"].append(info)
            tables["events.jsonl"].extend(events)
            tables["actions.jsonl"].extend(actions)
            tables["failures.jsonl"].extend(failures)
            turn_rows.append(info)
        check(len({t["session_id"] for t in turn_rows}) == 1, "resume_session_changed")
        tables["runs.jsonl"].append({"run_id": run_id, "family_id": families[report],
                                    "report": report, "condition": condition,
                                    "task_origin": "authored_development_calibration",
                                    "actor_kind": "observed_model_execution",
                                    "turn_ids": [t["turn_id"] for t in turn_rows],
                                    "quality_outcome": "not_assessed",
                                    "replayable_external_environment": False, **BASE})
    for a in index["artifacts"]:
        check(a["run_id"] in RUNS and inventory[a["path"]]["original_sha256"] == a["original_sha256"],
              "artifact_source_binding_mismatch")
        if a["capture_metadata"]:
            meta = rd.load_json(rd.local_file(root, a["capture_metadata"]))
            check(meta["stable_during_copy"] and meta["boundary_confirmed"]
                  and meta["completed_turn"] == a["turn"]
                  and meta["files"][a["relative_artifact"].replace("/", "\\")] == a["original_sha256"],
                  "artifact_checkpoint_binding_mismatch")
        tables["artifacts.jsonl"].append({**a, "sha256": rd.sha(rd.local_file(root, a["path"]).read_bytes()),
                                          "family_id": families[RUNS[a["run_id"]][0]], **BASE})
    calibration = rd.load_json(root / "sources/reports/calibration-provenance.json")
    for report in rd.REPORTS:
        for name in REPORT_NAMES:
            rel = "sources/reports/reports/" + report + "/" + name
            tables["report_versions.jsonl"].append(
                {"version_id": report + ":" + name.removesuffix(".md"), "family_id": families[report],
                 "report": report, "path": rel, "sha256": rd.sha(rd.local_file(root, rel).read_bytes()),
                 "quality_outcome": "not_assessed", **BASE})
        reviews = [e for e in rd.load_lines(root / "base/episodes.jsonl")
                   if e["family_id"] == families[report] and e["actor_kind"] == "archived_model_response"]
        for review in reviews:
            tables["lineage.jsonl"].append(
                {"relation": "review_of_version", "from": report + ":before-model-diagnostics",
                 "to": "base/" + review["episode_id"], "family_id": families[report],
                 "episode_table": "base/episodes.jsonl",
                 "runtime_status": review["evaluation"]["runtime_status"],
                 "research_quality_verified": False})
        tables["lineage.jsonl"].append(
            {"relation": "documented_revision_sequence",
             "from": report + ":before-model-diagnostics", "to": report + ":repaired",
             "family_id": families[report], "evidence": "sources/reports/ADJUDICATION.md",
             "review_attempt_ids": ["base/" + e["episode_id"] for e in reviews],
             "available_feedback_ids": ["base/" + e["episode_id"] for e in reviews
                                        if e["evaluation"]["runtime_status"] == "completed"],
             "writer_actions_recorded": False, "review_verdict_transfers_to_revision": False})
    for row in calibration["runs"]:
        run_id = row["run_id"]
        last = RUNS[run_id][2]
        original = inventory[f"sources/runtime/{run_id}/turn-{last}.message.md"]
        check(original["original_sha256"] == row["original_capture_sha256"], "report_capture_binding_mismatch")
        rel = "sources/reports/" + row["reader_export"]
        check(rd.normalized_hash(rd.local_file(root, rel)) == row["reader_export_sha256_lf"],
              "report_export_binding_mismatch")
        tables["lineage.jsonl"].append(
            {"relation": "documented_reader_export", "from": f"{run_id}-turn-{last}",
             "to": RUNS[run_id][0] + ":original-" + RUNS[run_id][1],
             "family_id": families[RUNS[run_id][0]], "evidence": "sources/reports/calibration-provenance.json",
             "original_capture_sha256": row["original_capture_sha256"],
             "transformation": row["transformation"], "causal_quality_claim": False})
    tables.update(semantic_views(root))
    return tables

def summary(tables):
    actions = tables["actions.jsonl"]
    return {"research_families": len({x["family_id"] for x in tables["runs.jsonl"]}),
            "observed_research_runs": len(tables["runs.jsonl"]), "research_turns": len(tables["turns.jsonl"]),
            "visible_runtime_events": len(tables["events.jsonl"]),
            "runtime_actions": dict(sorted(Counter(x["kind"] for x in actions).items())),
            "unmatched_actions": sum(not(x["started"] and x["completed"]) for x in actions),
            "redacted_command_outputs": sum(x["observation_kind"] == "redacted_output" for x in actions),
            "command_nonzero_exits": len(tables["failures.jsonl"]),
            "explicit_pause_turns": sum(x["instruction_boundary"] == "explicit_pause" for x in tables["turns.jsonl"]),
            "research_artifact_snapshots": len(tables["artifacts.jsonl"]),
            "report_versions": len(tables["report_versions.jsonl"]),
            "semantic_case_families": len({x["case_id"] for x in tables["semantic_cases.jsonl"]}),
            "semantic_case_versions": len(tables["semantic_cases.jsonl"]),
            "archived_semantic_calls": len(tables["semantic_episodes.jsonl"]),
            "semantic_judgments": len(tables["judgments.jsonl"]),
            "order_comparisons": len(tables["comparisons.jsonl"]),
            "changed_order_comparisons": sum(bool(x["changed_fields"]) for x in tables["comparisons.jsonl"]),
            "new_model_calls": 0, "training_records": 0, "held_out_tasks": 0}

CARD = """# 研究执行与评审历史数据集 v0.2

本包包括未经改写的 base/v0.1 数据集，以及新导入的历史研究执行和评审记录。
manifest.json 的 summary 为本次新增内容的实际数量，base_summary 单列上版，
两者的研究家族有重叠，不能相加当作独立样本数。

运行 verify_dataset.py verify <数据包目录> 可离线核对文件、原项目冻结哈希、
逐轮动作配对、返回值、用量、报告血缘、评审输入和 A/B 映射。不会执行归档命令。
运行 verify_dataset.py show <数据包目录> --run run-03 可读取一条多轮轨迹的概览。

sources 是冻结的输入；JSONL 表是可由输入重新生成的查询视图。
runs/turns/events/actions 提供研究任务、轮次、可见动作和已记录工具观察。
failures 只记录明确的命令非零退出，不把它自动当作研究失败。
artifacts 提供按轮快照；report_versions/lineage 连接报告导出与后续修订。
semantic_cases/semantic_episodes/judgments 保留合成案例、作者修订与历史模型判断；
comparisons 保留重排批次前后的变化，不作位置因素的因果解释。

研究题与语义案例均为真实独立任务，已执行记录都是真实测试，研究题用于开发校准。
4 次完整报告研究运行属于 2 个研究家族；20 组语义诊断任务使用构造短文材料。
所有关联样本和派生均为 development，训练用途未批准，quality_outcome 为 not_assessed。
作者标签及模型多数意见均不是标准答案；修订不增加独立任务数。
运行配置只能证明请求的模型，归档未给出可信的返回模型身份。
历史人工提示是原记录的一部分；本构建流程没有新增访谈、标注或人工审核环节。

工具日志完整度与外部环境完整度分别记录。网页条目只保存动作元数据，没有返回页正文；
文件变更条目不含完整补丁。命令标准输出有记录，但无关的全局记忆输出已移除并保留摘要。
已知本地目录替换为路径占位符；隐藏推理不导入。
result/事件用量按原记录保留，不当作账单。进程退出和轮次结束不等于报告质量通过。
多轮运行的 checkpoint 有原采集边界与文件哈希；没有该证据的末态目录明确标作未冻结末态。
原始文件哈希在构建时与本地源核对；经过删减的原文不分发，离线校验不能独立还原该原文。
哈希校验保证对冻结包的一致性，不证明内容真实。初稿、评审、修后稿分别保存，不转移通过标签。

本包用于诊断，训练用途按各来源许可记录；公开访问入口见管理仓库发布页。
原项目许可证保留于 base/UPSTREAM_LICENSE.txt。
JSONL 中字符串可含合法 Unicode 分隔符，按 LF 字节分行，不能使用 str.splitlines()。
"""

def build_dataset(source, runtime, base, output):
    source, runtime, base, output = map(lambda x: Path(x).resolve(), (source, runtime, base, output))
    check(not output.is_relative_to(base) and not base.is_relative_to(output), "overlapping_base_output")
    if (output / "manifest.json").exists():
        return verify_dataset(output)
    check(not output.exists() or not any(output.iterdir()), "output_must_be_empty")
    index = import_sources(source, runtime, base, output)
    rd.put_json(output / "source_index.json", index)
    tables = derive_views(output, index)
    for name, rows in tables.items():
        rd.put_lines(output / name, rows)
    rd.put(output / "verify_dataset.py", Path(__file__).read_bytes())
    rd.put(output / "research_dataset.py", _HELPER.read_bytes())
    rd.put(output / "LICENSE", (base / "LICENSE").read_bytes())
    rd.put(output / "DATA_CARD.md", CARD.encode("utf-8"))
    files = {p.relative_to(output).as_posix(): rd.sha(p.read_bytes())
             for p in sorted(output.rglob("*")) if p.is_file()}
    manifest = {"schema_version": VERSION, "summary": summary(tables),
                "base_summary": rd.load_json(base / "manifest.json")["summary"],
                "base_manifest_sha256": index["base_manifest_sha256"],
                "source_index_sha256": rd.sha(rd.encoded(index)),
                "split_policy": "historically_seen_sources_and_all_descendants_development_only",
                "rights": rd.RIGHTS, "files": files}
    rd.put_json(output / "manifest.json", manifest)
    return verify_dataset(output)

def verify_dataset(root):
    root = Path(root).resolve()
    manifest = rd.load_json(root / "manifest.json")
    check(manifest["schema_version"] == VERSION, "unsupported_history_version")
    check(manifest["rights"] == rd.RIGHTS and manifest["split_policy"] ==
          "historically_seen_sources_and_all_descendants_development_only", "history_rights_or_split_changed")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    check(actual == set(manifest["files"]) | {"manifest.json"}, "history_file_inventory_mismatch")
    for rel, digest in manifest["files"].items():
        check(rd.sha(rd.local_file(root, rel).read_bytes()) == digest, "history_file_hash_mismatch:" + rel)
    rd.verify_dataset(root / "base")
    index = rd.load_json(root / "source_index.json")
    check(rd.sha(rd.encoded(index)) == manifest["source_index_sha256"], "source_index_hash_mismatch")
    check(rd.sha((root / "base/manifest.json").read_bytes()) == index["base_manifest_sha256"]
          == manifest["base_manifest_sha256"], "base_dataset_changed")
    check(rd.load_json(root / "base/manifest.json")["summary"] == manifest["base_summary"], "base_summary_changed")
    for entry in index["files"]:
        path = rd.local_file(root, entry["path"])
        check(rd.sha(path.read_bytes()) == entry["packaged_sha256"], "source_snapshot_changed")
        check(not SECRET.search(path.read_text(encoding="utf-8-sig")), "credential_like_content")
        if "upstream_sha256_lf" in entry:
            category = "semantic" if "/semantic/" in entry["path"] else "reports"
            upstream = rd.load_json(root / "sources" / category / "bundle-manifest.json")
            rel = entry["path"].removeprefix("sources/" + category + "/")
            check(rd.normalized_hash(path) == upstream["files"][rel] == entry["upstream_sha256_lf"],
                  "upstream_snapshot_changed")
        elif not entry["transformed"]:
            check(entry["original_sha256"] == entry["packaged_sha256"], "untransformed_source_hash_mismatch")
    tables = derive_views(root, index)
    for name, expected in tables.items():
        check(rd.load_lines(root / name) == expected, "derived_view_mismatch:" + name)
    check(summary(tables) == manifest["summary"], "history_summary_changed")
    return {"verified": True, **manifest["summary"], "verified_files": len(manifest["files"])}

def make_archive(root, destination):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    verify_dataset(root)
    check(not destination.is_relative_to(root), "archive_must_be_outside_dataset")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                info = zipfile.ZipInfo(p.relative_to(root).as_posix(), (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o600 << 16
                archive.writestr(info, p.read_bytes())
    raw = buffer.getvalue()
    rd.put(destination, raw)
    return {"archive": str(destination), "bytes": len(raw), "sha256": rd.sha(raw)}

def show_run(root, run_id):
    root = Path(root)
    verify_dataset(root)
    run = next((x for x in rd.load_lines(root / "runs.jsonl") if x["run_id"] == run_id), None)
    check(run is not None, "unknown_run_id")
    return {"run": run, "turns": [x for x in rd.load_lines(root / "turns.jsonl") if x["run_id"] == run_id],
            "actions_by_kind": dict(Counter(x["kind"] for x in rd.load_lines(root / "actions.jsonl")
                                            if x["run_id"] == run_id)),
            "failure_records": [x for x in rd.load_lines(root / "failures.jsonl")
                                if x["action_id"].startswith(run_id + "-")]}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    build = commands.add_parser("build")
    for key in ("source", "runtime", "base", "output"):
        build.add_argument("--" + key, type=Path, required=True)
    for operation in ("verify", "pack", "show"):
        command = commands.add_parser(operation)
        command.add_argument("dataset", type=Path)
        if operation == "pack":
            command.add_argument("destination", type=Path)
        if operation == "show":
            command.add_argument("--run", required=True)
    args = parser.parse_args()
    if args.operation == "build":
        result = build_dataset(args.source, args.runtime, args.base, args.output)
    elif args.operation == "verify":
        result = verify_dataset(args.dataset)
    elif args.operation == "show":
        result = show_run(args.dataset, args.run)
    else:
        result = make_archive(args.dataset, args.destination)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
