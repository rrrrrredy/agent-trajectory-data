"""Build and verify a small local research-trajectory dataset; standard library only."""
from __future__ import annotations
import argparse
import copy
import csv
import hashlib
import io
import json
import subprocess
import zipfile
from collections import Counter
from pathlib import Path

VERSION = "research-slices-v1"
REPORTS = ("customer-service", "video-production")
PROVIDERS = ("deepseek", "kimi")
VARIANTS = ("original", "dangling_reference", "missing_registry", "transient_registry")
BUNDLE = Path("evals/diagnostics/2026-09-07")
RIGHTS = {"allowed_uses": ["diagnostic"], "distribution": "private_internal_only",
          "training_eligible": False}
QUESTION = (
    "Read both supplied tables. Retry a transient 429 at most twice. "
    "If a required table returns 404, return insufficient_evidence and its name. "
    "Otherwise identify duplicate source IDs, claims without source IDs, and every "
    "claim/source pair whose source ID is absent from the source table. "
    "Return consistent only when all these lists are empty. "
    "This checks registry links only; it does not verify the truth of any claim."
)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def encoded(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")

def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def load_lines(path):
    # U+2028/U+2029 are legal within JSON strings, not JSONL record delimiters.
    return [json.loads(line) for line in Path(path).read_bytes().split(b"\n") if line.strip()]

def put(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("immutable_file_conflict:" + path.name)
    else:
        with path.open("xb") as stream:
            stream.write(data)

def put_json(path, obj):
    put(path, encoded(obj))

def put_lines(path, rows):
    body = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True,
                              allow_nan=False) + "\n" for row in rows)
    put(path, body.encode("utf-8"))

def local_file(root, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("invalid_bundle_path")
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("unsafe_bundle_path")
    root = Path(root).resolve()
    candidate = root / rel
    if candidate.is_symlink() or not candidate.resolve().is_relative_to(root):
        raise ValueError("linked_bundle_path")
    return candidate

def normalized(raw):
    return raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")

def normalized_hash(path):
    return sha(normalized(Path(path).read_bytes()).encode("utf-8"))

def table_rows(path):
    return list(csv.DictReader(io.StringIO(Path(path).read_text(encoding="utf-8-sig"))))

def input_family(report_text):
    return "research-" + sha(report_text.encode("utf-8"))[:24]

def review_status(result):
    content = result.get("content")
    if not isinstance(content, str):
        raise ValueError("invalid_response_content")
    try:
        parsed = json.loads(content)
    except ValueError:
        parsed = None
    if encoded(parsed) != encoded(result.get("parsed")):
        raise ValueError("parsed_response_disagrees_with_visible_content")
    if result.get("finish_reason") == "length":
        state, failure = "output_limit", "response_truncated"
    elif result.get("finish_reason") != "stop":
        state, failure = "unknown_terminal", "unrecognized_finish_reason"
    elif (not isinstance(parsed, dict)
          or parsed.get("verdict") not in {"usable_with_limits", "needs_revision", "insufficient_context"}
          or not isinstance(parsed.get("findings"), list)
          or parsed.get("external_facts_verified") is not False):
        state, failure = "protocol_failure", "invalid_review_response"
    else:
        state, failure = "completed", None
    return {"runtime_status": state, "failure_type": failure,
            "outcome": "not_assessed", "label_basis": "archived_response_metadata",
            "model_judgment": parsed.get("verdict") if isinstance(parsed, dict) else None,
            "research_quality_verified": False}

def registry_result(observations):
    latest = {row["table"]: row for row in observations}
    missing = sorted(name for name in ("sources", "claims")
                     if latest.get(name, {}).get("status") != 200)
    empty = {"duplicate_source_ids": [], "claims_without_sources": [], "dangling_references": []}
    if missing:
        return {"verdict": "insufficient_evidence", "missing_tables": missing, **empty}
    counts = Counter(row["source_id"] for row in latest["sources"]["rows"])
    duplicates = sorted(key for key, count in counts.items() if count > 1)
    unlinked, dangling = [], []
    for claim in latest["claims"]["rows"]:
        ids = sorted(set(value.strip() for value in claim["source_ids"].split("|") if value.strip()))
        if not ids:
            unlinked.append(claim["claim_id"])
        for source_id in ids:
            if source_id not in counts:
                dangling.append({"claim_id": claim["claim_id"], "source_id": source_id})
    dangling.sort(key=lambda row: (row["claim_id"], row["source_id"]))
    return {"verdict": "inconsistent" if duplicates or unlinked or dangling else "consistent",
            "missing_tables": [], "duplicate_source_ids": duplicates,
            "claims_without_sources": sorted(unlinked), "dangling_references": dangling}

def environment_for(root, task):
    refs = task["artifacts"]
    sources = table_rows(local_file(root, refs["sources"]))
    claims = table_rows(local_file(root, refs["claims"]))
    if not sources or not claims:
        raise ValueError("empty_registry")
    env = {"sources": {"rows": sources, "responses": [200]},
           "claims": {"rows": claims, "responses": [200]}}
    variant = task["variant"]
    if variant == "dangling_reference":
        if any(row["source_id"] == "S_UNREGISTERED" for row in sources):
            raise ValueError("mutation_id_collision")
        env["claims"]["rows"][0]["source_ids"] += "|S_UNREGISTERED"
    elif variant == "missing_registry":
        env["sources"]["responses"] = [404]
    elif variant == "transient_registry":
        env["sources"]["responses"] = [429, 200]
    elif variant != "original":
        raise ValueError("unknown_variant")
    return env

def observe(env, name, calls):
    if name not in env or calls[name] >= 3:
        raise ValueError("invalid_or_excessive_table_read")
    config = env[name]
    status = config["responses"][min(calls[name], len(config["responses"]) - 1)]
    calls[name] += 1
    return {"table": name, "status": status,
            **({"rows": copy.deepcopy(config["rows"])} if status == 200 else {})}

def oracle_for(env):
    return registry_result([
        {"table": name, "status": cfg["responses"][-1],
         **({"rows": cfg["rows"]} if cfg["responses"][-1] == 200 else {})}
        for name, cfg in env.items()])

def grade_registry(env, actions, observations):
    terminal = {row["table"]: row["status"] for row in observations}
    if not actions or actions[-1].get("tool") != "submit_check":
        return {"outcome": "not_assessed", "failure_type": "no_submission"}
    if any(terminal.get(name) not in {200, 404} for name in env):
        return {"outcome": "fail", "failure_type": "required_table_not_observed"}
    passed = encoded(actions[-1].get("result")) == encoded(oracle_for(env))
    return {"outcome": "pass" if passed else "fail",
            "failure_type": None if passed else "registry_check_mismatch"}

def control_run(root, task, policy):
    env, calls, observations, actions, events = environment_for(root, task), Counter(), [], [], []
    def event(kind, payload):
        events.append({"seq": len(events), "event_type": kind, "payload": copy.deepcopy(payload)})
    for name in ("sources", "claims"):
        for _ in range(3):
            action = {"tool": "read_table", "table": name}
            actions.append(action)
            event("action", action)
            response = observe(env, name, calls)
            observations.append(response)
            event("observation", response)
            if response["status"] != 429:
                break
    result = registry_result(observations) if policy == "reference" else {
        "verdict": "consistent", "missing_tables": [], "duplicate_source_ids": [],
        "claims_without_sources": [], "dangling_references": []}
    action = {"tool": "submit_check", "result": result}
    actions.append(action)
    event("action", action)
    episode_id = task["task_id"] + "-" + policy
    relative = "events/" + episode_id + ".jsonl"
    put_lines(Path(root) / relative, events)
    return {"episode_id": episode_id, "task_id": task["task_id"], "family_id": task["family_id"],
            "split": task["split"], "task_origin": task["task_origin"], "actor_kind": "scripted_policy",
            "execution_mode": "frozen_table_execution", "policy": policy, "events_path": relative,
            "terminal_reason": "submitted", "evaluation": grade_registry(env, actions, observations),
            "tool_error_count": sum(row["status"] == 429 for row in observations), "rights": RIGHTS}

def collect_inventory(roots):
    inventory = []
    for index, value in enumerate(roots):
        root = Path(value).resolve()
        if not root.is_dir():
            raise ValueError("inventory_root_missing")
        records = [load_json(path) for path in sorted(root.glob("runs/*/run.json"))]
        tasks = [load_json(path) for path in sorted(root.glob("tasks/*.json"))]
        sessions = []
        for manifest_path in sorted(root.glob("runtime_sessions/*/manifest.json")):
            manifest = load_json(manifest_path)
            raw_path = manifest_path.parent / "events.jsonl"
            rows = load_lines(raw_path)
            if sha(raw_path.read_bytes()) != manifest["events_sha256"] or len(rows) != manifest["events"]:
                raise ValueError("existing_session_hash_or_count_mismatch")
            calls = {row["call_id"] for row in rows if row["type"] == "tool_call"}
            results = {row["call_id"] for row in rows if row["type"] == "tool_result"}
            sessions.append({"import_id": manifest["import_id"], "events": len(rows),
                             "tool_calls": len(calls), "tool_results": len(results),
                             "unmatched_calls": len(calls - results),
                             "events_sha256": manifest["events_sha256"],
                             "outcome": "not_assessed", "included_in_this_release": False})
        inventory.append({"source_label": root.name, "source_index": index,
                          "tasks": len(tasks), "runs": len(records),
                          "actors": dict(Counter(row["actor_kind"] for row in records)),
                          "task_origins": dict(Counter(row["task_origin"] for row in tasks)),
                          "sessions": sessions, "included_in_this_release": False})
    return inventory

def summarize(tasks, episodes):
    observed = [row for row in episodes if row["actor_kind"] == "archived_model_response"]
    controls = [row for row in episodes if row["actor_kind"] == "scripted_policy"]
    return {"tasks": len(tasks), "source_families": len({row["family_id"] for row in tasks}),
            "task_origins": dict(Counter(row["task_origin"] for row in tasks)),
            "task_splits": dict(Counter(row["split"] for row in tasks)),
            "observed_review_episodes": len(observed),
            "observed_runtime_status": dict(Counter(row["evaluation"]["runtime_status"] for row in observed)),
            "scripted_episodes": len(controls),
            "scripted_outcomes": dict(Counter(row["evaluation"]["outcome"] for row in controls)),
            "new_model_calls": 0, "training_records": 0, "holdout_tasks": 0}

CARD = """# 研究任务片段数据集 v0.1

本包对齐 research-toolkit 的两份真实研究报告及历史模型评审记录，保留请求、可见响应、失败状态和文件来源。另包含由报告的主张表、来源表派生的结构一致性任务及脚本执行。

## 实际内容

- 历史评审调用 4 条：3 条正常完成、1 条因输出长度限制结束，可见正文为空。
- 原始评审任务 2 条、产物衍生引用检查任务 2 条、合成变体 6 条。
- 脚本执行 16 条：12 条通过、4 条失败，执行主体明确标识。
- 包内包含原始研究需求、修订说明、冻结报告、来源表、主张表、输入、请求与响应。
- inventory.json 另登记旧管线和部分会话的数量，其轨迹正文不计入本包。
- 本次新增模型调用 0 次，训练记录 0 条。

## 标签与范围

真实记录仅覆盖研究报告评审子任务。报告撰写过程、检索轨迹和外部网页快照未在这些历史记录中提供。请求响应对不是完整研究轨迹；仓库文件校验也不是模型提供方认证。

报告正文和修订说明逐字出现在对应模型输入中。原始需求、来源与主张表是关联产物，不声称模型直接看到了未放入输入的文件。没有进行新的联网事实核查。

历史评审结论保留为 model_judgment；三条正常完成不等于报告正确。截断是响应元数据支持的运行失败，研究质量仍为 not_assessed。没有补写失败调用的空正文或隐藏推理。

合成任务只检查来源编号与主张表的连接。未知编号、404 和 429 为显式注入条件。这不能判断证据是否支持主张，也不能评分研究洞察和文风。盲目返回 consistent 的控制策略会在正常和恢复场景通过，在未知编号和缺失场景失败。

两组已被查看的历史来源及全部派生固定为 development。本版不宣称隐藏测试，也不估计泛化准确率。共享模板不是独立能力；脚本轨迹不是模型轨迹。仅供私有内部诊断，不输出训练样本；未知账单金额为 null。

## 本地验证

Python 3.10+，无第三方依赖。运行命令：

    py -3 -B verify_dataset.py verify .

检查文件、原始清单哈希、输入与报告绑定、响应状态、血缘、事件重放、重新评分和切分。验证不调用模型、不访问网络。

manifest.json 为实际统计与文件清单。source_provenance.json 记录原项目版本和来源。UPSTREAM_LICENSE.txt 保留原项目许可证；新增编排及记录见 LICENSE。
"""

def build_dataset(source, output, existing_roots=()):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output == source or source.is_relative_to(output) or output.is_relative_to(source):
        raise ValueError("output_must_be_separate_from_source")
    upstream_manifest = load_json(source / BUNDLE / "bundle-manifest.json")
    selected, reports = {}, {}
    for name in REPORTS:
        names = ["inputs/" + name + ".json"]
        names += ["reports/" + name + "/" + part for part in
                  ("original-request.md", "repair-brief.md", "before-model-diagnostics.md",
                   "data/source_registry.csv", "data/claims_registry.csv")]
        names += [kind + "/" + provider + "/" + name + ".json"
                  for kind in ("requests", "results") for provider in PROVIDERS]
        for rel in names:
            path = local_file(source / BUNDLE, rel)
            expected = upstream_manifest["files"].get(rel)
            if expected is None or normalized_hash(path) != expected:
                raise ValueError("upstream_snapshot_mismatch:" + rel)
            selected[rel] = path.read_bytes()
        reports[name] = {
            "input": "assets/inputs/" + name + ".json",
            "original_request": "assets/reports/" + name + "/original-request.md",
            "brief": "assets/reports/" + name + "/repair-brief.md",
            "report": "assets/reports/" + name + "/before-model-diagnostics.md",
            "sources": "assets/reports/" + name + "/data/source_registry.csv",
            "claims": "assets/reports/" + name + "/data/claims_registry.csv"}
    fingerprint = sha(encoded({key: sha(value) for key, value in sorted(selected.items())}))
    if (output / "manifest.json").exists():
        prior = verify_dataset(output)
        if load_json(output / "manifest.json")["source_fingerprint"] != fingerprint:
            raise ValueError("dataset_version_source_changed")
        return prior
    output.mkdir(parents=True, exist_ok=True)
    for rel, raw in selected.items():
        put(output / "assets" / rel, raw)
    put(output / "assets/upstream-manifest.json", (source / BUNDLE / "bundle-manifest.json").read_bytes())
    put(output / "UPSTREAM_LICENSE.txt", (source / "LICENSE").read_bytes())
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"],
                                       text=True, encoding="utf-8").strip()
    provenance = {"repository": "https://github.com/rrrrrredy/research-toolkit",
                  "revision": revision, "upstream_bundle": BUNDLE.as_posix(),
                  "hashing": "UTF-8 with CRLF/CR normalized to LF; other whitespace preserved",
                  "files": {("assets/" + rel): {"upstream_path": (BUNDLE / rel).as_posix(),
                            "normalized_sha256": upstream_manifest["files"][rel]}
                            for rel in selected},
                  "capture_boundary": "archived_request_response_files_not_provider_attestation"}
    put_json(output / "source_provenance.json", provenance)
    tasks, episodes = [], []
    for name, refs in reports.items():
        family = input_family(local_file(output, refs["report"]).read_text(encoding="utf-8-sig"))
        review_id = family + "-review"
        tasks.append({"schema_version": VERSION, "task_id": review_id, "family_id": family,
                      "source_group": family, "split": "development",
                      "task_origin": "observed_review_request", "profile": "archived-review-v1",
                      "artifacts": refs, "report_name": name, "oracle": None, "rights": RIGHTS,
                      "lineage": {"parent_task_id": None, "historically_seen": True}})
        for provider in PROVIDERS:
            request_path = "assets/requests/" + provider + "/" + name + ".json"
            response_path = "assets/results/" + provider + "/" + name + ".json"
            request, result = load_json(output / request_path), load_json(output / response_path)
            allowed = {"content", "parsed", "model_returned", "finish_reason", "usage",
                       "input_sha256", "external_fact_check"}
            if set(result) - allowed or any(key in request for key in ("api_key", "authorization")):
                raise ValueError("unsupported_capture_fields")
            episode_id = review_id + "-" + provider
            events_path = "events/" + episode_id + ".jsonl"
            put_lines(output / events_path, [
                {"seq": 0, "event_type": "model_request",
                 "payload": {"request_path": request_path, "messages": request["messages"]}},
                {"seq": 1, "event_type": "model_response",
                 "payload": {"response_path": response_path, "content": result["content"],
                             "finish_reason": result["finish_reason"]}}])
            episodes.append({"episode_id": episode_id, "task_id": review_id, "family_id": family,
                             "split": "development", "task_origin": "observed_review_request",
                             "actor_kind": "archived_model_response",
                             "execution_mode": "imported_request_response", "provider": provider,
                             "request_path": request_path, "response_path": response_path,
                             "events_path": events_path, "capture_scope": "review_call_io_only",
                             "observed_at": None, "model_requested": request["model"],
                             "model_returned": result.get("model_returned"),
                             "model_identity_basis": "archived_response_field",
                             "usage": result.get("usage"), "billed_amount": None,
                             "terminal_reason": result["finish_reason"],
                             "evaluation": review_status(result), "rights": RIGHTS})
        base_id = family + "-registry-original"
        for variant in VARIANTS:
            task = {"schema_version": VERSION, "task_id": family + "-registry-" + variant,
                    "family_id": family, "source_group": family, "split": "development",
                    "task_origin": "artifact_derived" if variant == "original" else "synthetic",
                    "profile": "registry-links-v1", "variant": variant, "artifacts": refs,
                    "public": {"question": QUESTION, "tools": ["read_table", "submit_check"],
                               "table_names": ["sources", "claims"]}, "rights": RIGHTS,
                    "lineage": {"parent_task_id": review_id if variant == "original" else base_id,
                                "recipe": "registry-faults-v1", "mutation": variant,
                                "observed_agent_failure_claim": False, "historically_seen": True}}
            task["oracle"] = oracle_for(environment_for(output, task))
            tasks.append(task)
            for policy in ("reference", "unchecked"):
                episodes.append(control_run(output, task, policy))
    put_lines(output / "tasks.jsonl", tasks)
    put_lines(output / "episodes.jsonl", episodes)
    put_json(output / "inventory.json", collect_inventory(existing_roots))
    put(output / "verify_dataset.py", Path(__file__).read_bytes())
    put(output / "DATA_CARD.md", CARD.encode("utf-8"))
    put(output / "LICENSE", b"Private internal diagnostic dataset. No training or redistribution grant.\n"
        b"Upstream material retains its applicable license; see UPSTREAM_LICENSE.txt.\n"
        b"All rights reserved for new dataset compilation and tooling.\n")
    files = {path.relative_to(output).as_posix(): sha(path.read_bytes())
             for path in sorted(output.rglob("*")) if path.is_file()}
    manifest = {"schema_version": VERSION, "source_fingerprint": fingerprint,
                "split_policy": "historically_seen_sources_and_all_descendants_development_only",
                "summary": summarize(tasks, episodes), "files": files}
    put_json(output / "manifest.json", manifest)
    return verify_dataset(output)


def verify_review(root, task, episode, events):
    refs = task["artifacts"]
    original_input = load_json(local_file(root, refs["input"]))
    request = load_json(local_file(root, episode["request_path"]))
    result = load_json(local_file(root, episode["response_path"]))
    expected_messages = [{"role": "system", "content": original_input["system"]},
                         {"role": "user", "content": original_input["user"]}]
    if request["messages"] != expected_messages:
        raise ValueError("request_input_binding_mismatch")
    for name in ("brief", "report"):
        text = local_file(root, refs[name]).read_text(encoding="utf-8-sig")
        if not text or text not in original_input["user"]:
            raise ValueError("report_input_binding_mismatch")
    if result["input_sha256"] != normalized_hash(local_file(root, refs["input"])):
        raise ValueError("response_input_hash_mismatch")
    expected_events = [
        {"seq": 0, "event_type": "model_request",
         "payload": {"request_path": episode["request_path"], "messages": expected_messages}},
        {"seq": 1, "event_type": "model_response",
         "payload": {"response_path": episode["response_path"], "content": result["content"],
                     "finish_reason": result["finish_reason"]}}]
    if events != expected_events:
        raise ValueError("observed_events_disagree_with_capture")
    if (episode["model_requested"] != request["model"]
            or episode["model_returned"] != result.get("model_returned")
            or episode["usage"] != result.get("usage")
            or episode["terminal_reason"] != result["finish_reason"]
            or episode["billed_amount"] is not None
            or episode["capture_scope"] != "review_call_io_only"
            or episode["execution_mode"] != "imported_request_response"
            or encoded(episode["evaluation"]) != encoded(review_status(result))):
        raise ValueError("observed_metadata_or_label_mismatch")

def verify_control(root, task, episode, events):
    env, calls, actions, observations = environment_for(root, task), Counter(), [], []
    if encoded(task["oracle"]) != encoded(oracle_for(env)):
        raise ValueError("oracle_environment_mismatch")
    if not events or len(events) > 13 or [row["seq"] for row in events] != list(range(len(events))):
        raise ValueError("invalid_event_sequence")
    index = 0
    while index < len(events):
        row = events[index]
        if row["event_type"] != "action":
            raise ValueError("missing_action")
        action = row["payload"]
        actions.append(action)
        if action.get("tool") == "submit_check":
            if index != len(events) - 1:
                raise ValueError("events_after_submission")
            break
        if action.get("tool") != "read_table" or index + 1 >= len(events):
            raise ValueError("invalid_action_or_unpaired_observation")
        expected = observe(env, action.get("table"), calls)
        observation = events[index + 1]
        if (observation["event_type"] != "observation"
                or encoded(observation["payload"]) != encoded(expected)):
            raise ValueError("forged_or_mismatched_observation")
        observations.append(expected)
        index += 2
    if encoded(episode["evaluation"]) != encoded(grade_registry(env, actions, observations)):
        raise ValueError("control_label_mismatch")
    if (episode["tool_error_count"] != sum(row["status"] == 429 for row in observations)
            or episode["terminal_reason"] != "submitted"
            or episode["execution_mode"] != "frozen_table_execution"):
        raise ValueError("control_runtime_metadata_mismatch")
    expected = registry_result(observations) if episode["policy"] == "reference" else {
        "verdict": "consistent", "missing_tables": [], "duplicate_source_ids": [],
        "claims_without_sources": [], "dangling_references": []}
    if encoded(actions[-1].get("result")) != encoded(expected):
        raise ValueError("scripted_policy_binding_mismatch")

def verify_dataset(root):
    root = Path(root).resolve()
    manifest = load_json(root / "manifest.json")
    if manifest.get("schema_version") != VERSION:
        raise ValueError("unsupported_dataset_version")
    listed = manifest["files"]
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual != set(listed) | {"manifest.json"}:
        raise ValueError("dataset_file_inventory_mismatch")
    for relative, expected in listed.items():
        if sha(local_file(root, relative).read_bytes()) != expected:
            raise ValueError("file_hash_mismatch:" + relative)
    provenance = load_json(root / "source_provenance.json")
    upstream = load_json(root / "assets/upstream-manifest.json")
    selected = {}
    for relative, source in provenance["files"].items():
        rel = relative.removeprefix("assets/")
        path = local_file(root, relative)
        if (source["upstream_path"] != (BUNDLE / rel).as_posix()
                or normalized_hash(path) != source["normalized_sha256"]
                or source["normalized_sha256"] != upstream["files"].get(rel)):
            raise ValueError("upstream_source_binding_mismatch")
        selected[rel] = sha(path.read_bytes())
    if sha(encoded(dict(sorted(selected.items())))) != manifest["source_fingerprint"]:
        raise ValueError("source_fingerprint_mismatch")
    tasks, episodes = load_lines(root / "tasks.jsonl"), load_lines(root / "episodes.jsonl")
    by_id = {row["task_id"]: row for row in tasks}
    if len(by_id) != len(tasks) or not tasks:
        raise ValueError("duplicate_or_empty_tasks")
    fingerprints = set()
    for task in tasks:
        if task["schema_version"] != VERSION or task["rights"] != RIGHTS:
            raise ValueError("task_schema_or_rights_changed")
        if task["split"] != "development" or not task["lineage"]["historically_seen"]:
            raise ValueError("seen_source_must_stay_development")
        for relative in task["artifacts"].values():
            if relative not in provenance["files"]:
                raise ValueError("task_artifact_outside_provenance")
        expected_family = input_family(local_file(root, task["artifacts"]["report"]).read_text(
            encoding="utf-8-sig"))
        if task["family_id"] != expected_family or task["source_group"] != expected_family:
            raise ValueError("source_family_mismatch")
        parent_id = task["lineage"]["parent_task_id"]
        if parent_id:
            parent = by_id.get(parent_id)
            if (not parent or parent["family_id"] != task["family_id"]
                    or parent["split"] != task["split"] or parent["artifacts"] != task["artifacts"]):
                raise ValueError("parent_lineage_mismatch")
        if task["profile"] == "archived-review-v1":
            if task["task_origin"] != "observed_review_request" or parent_id or task["oracle"] is not None:
                raise ValueError("invalid_observed_task")
            fingerprint = ("review", sha(local_file(root, task["artifacts"]["input"]).read_bytes()))
        elif task["profile"] == "registry-links-v1":
            variant = task["variant"]
            origin = "artifact_derived" if variant == "original" else "synthetic"
            expected_parent = expected_family + ("-review" if variant == "original" else "-registry-original")
            if (task["task_origin"] != origin or parent_id != expected_parent
                    or task["lineage"]["observed_agent_failure_claim"] is not False
                    or task["lineage"]["mutation"] != variant
                    or task["lineage"]["recipe"] != "registry-faults-v1"
                    or task["public"] != {"question": QUESTION, "tools": ["read_table", "submit_check"],
                                          "table_names": ["sources", "claims"]}):
                raise ValueError("invalid_synthetic_lineage")
            fingerprint = ("registry", sha(encoded(environment_for(root, task))))
        else:
            raise ValueError("unknown_task_profile")
        if fingerprint in fingerprints:
            raise ValueError("duplicate_task_content")
        fingerprints.add(fingerprint)
    seen_ids, coverage = set(), Counter()
    for episode in episodes:
        identifier = episode["episode_id"]
        task = by_id.get(episode["task_id"])
        if identifier in seen_ids or not task:
            raise ValueError("duplicate_episode_or_missing_task")
        seen_ids.add(identifier)
        if (any(episode[key] != task[key] for key in ("family_id", "split", "task_origin"))
                or episode["rights"] != RIGHTS):
            raise ValueError("episode_lineage_or_rights_mismatch")
        events = load_lines(local_file(root, episode["events_path"]))
        if task["profile"] == "archived-review-v1" and episode["actor_kind"] == "archived_model_response":
            if episode["provider"] not in PROVIDERS:
                raise ValueError("unsupported_archived_provider")
            key = episode["provider"]
            verify_review(root, task, episode, events)
        elif task["profile"] == "registry-links-v1" and episode["actor_kind"] == "scripted_policy":
            if episode["policy"] not in {"reference", "unchecked"}:
                raise ValueError("unsupported_control_policy")
            key = episode["policy"]
            verify_control(root, task, episode, events)
        else:
            raise ValueError("actor_task_profile_mismatch")
        coverage[(task["task_id"], key)] += 1
    for task in tasks:
        keys = PROVIDERS if task["profile"] == "archived-review-v1" else ("reference", "unchecked")
        if any(coverage[(task["task_id"], key)] != 1 for key in keys):
            raise ValueError("missing_or_repeated_episode")
    summary = summarize(tasks, episodes)
    if (summary != manifest["summary"]
            or manifest["split_policy"] != "historically_seen_sources_and_all_descendants_development_only"):
        raise ValueError("dataset_summary_or_split_policy_mismatch")
    return {"verified": True, **summary, "verified_files": len(listed)}

def make_archive(root, destination):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    verify_dataset(root)
    if destination.is_relative_to(root):
        raise ValueError("archive_must_be_outside_dataset")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            info = zipfile.ZipInfo(path.relative_to(root).as_posix(), (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, path.read_bytes())
    raw = buffer.getvalue()
    put(destination, raw)
    return {"archive": str(destination), "bytes": len(raw), "sha256": sha(raw)}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    build = commands.add_parser("build")
    build.add_argument("--source", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--existing-root", type=Path, action="append", default=[])
    verify = commands.add_parser("verify")
    verify.add_argument("dataset", type=Path)
    pack = commands.add_parser("pack")
    pack.add_argument("dataset", type=Path)
    pack.add_argument("destination", type=Path)
    args = parser.parse_args()
    if args.operation == "build":
        result = build_dataset(args.source, args.output, args.existing_root)
    elif args.operation == "verify":
        result = verify_dataset(args.dataset)
    else:
        result = make_archive(args.dataset, args.destination)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
