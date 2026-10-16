"""Prepare the two pinned AI knowledge snapshots; offline, no model calls.

Reuse the dataset's immutable writers. Originals and differing records are kept;
the reading copy selects one existing record, never a field-wise merged article.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import html
import json
from pathlib import Path
import re
import subprocess
import zipfile

from research_dataset import encoded, put, put_json, put_lines, sha


PINS = {
    "aiknowledge-cli": "63f5c8b1803aa9aa6551a97a50afff9bfa4daf63",
    "ai-knowledge-graph": "67584ce8abe5155c049354a7be9baf150573ce3f",
}
TOOLKIT_PIN = "5ee675d29200c64edcd615aa2ab9bf5b8ee99e97"
RECOVER_IDS = ("D-2279323149", "D-2073114610", "D-2271174789", "D-2499046308", "D-2748557520")


def git_bytes(root, revision, path):
    return subprocess.check_output(["git", "show", f"{revision}:{path}"], cwd=root)


def clean_markup(text):
    # Only known presentation tokens. Unknown content remains visible.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?m)^目标 ClientId: [^\n]*\n?", "", text)
    text = re.sub(r":\[font\]\{[^}\n]*\}|\[/font\]", "", text)
    text = re.sub(r":::paragraph(?:\{[^}\n]*\})?", "", text)
    text = re.sub(r"(?m)^:::title\s*$|^:::catalog\{[^}\n]*\}:::\s*$", "", text)
    text = re.sub(r":::(?:__)?(?=\s|$)", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def readable_capture(raw):
    """Decode stored KM JSON tables without inventing absent cells or text."""
    pieces, cursor, tables, issues = [], 0, 0, []
    for match in re.finditer(r":::table\{[^}\n]*\}\s*", raw):
        if match.start() < cursor:
            continue
        pieces.append(clean_markup(raw[cursor:match.start()]))
        try:
            rows, length = json.JSONDecoder().raw_decode(raw[match.end():])
            if not isinstance(rows, list) or not all(isinstance(row, list) for row in rows):
                raise ValueError("not a cell matrix")
            lines = ["<table>"]
            for row in rows:
                lines.append("<tr>")
                for cell in row:
                    if not isinstance(cell, dict) or not isinstance(cell.get("content"), str):
                        raise ValueError("unknown cell representation")
                    attrs = cell.get("attrs", {})
                    spans = "".join(f' {key}="{attrs[key]}"' for key in ("rowspan", "colspan")
                                    if isinstance(attrs.get(key), int) and attrs[key] > 1)
                    tag = "th" if cell.get("type") == "table_header" else "td"
                    body = html.escape(clean_markup(cell["content"])).replace("\n", "<br>")
                    lines.append(f"<{tag}{spans}>{body}</{tag}>")
                lines.append("</tr>")
            lines.append("</table>")
            pieces.append("\n".join(lines))
            cursor = match.end()+length
            tables += 1
        except (ValueError, TypeError, KeyError) as exc:
            issues.append({"offset": match.start(), "reason": str(exc), "handling": "original retained verbatim"})
            # Do not strip formatting from an undecodable table or imply completeness.
            pieces.append("未能展开此表；以下保留该处原始捕获内容。\n\n<pre>" + html.escape(raw[match.start():]) + "</pre>")
            cursor = len(raw)
            break
    pieces.append(clean_markup(raw[cursor:]))
    return "\n\n".join(part for part in pieces if part)+"\n", tables, issues


def entity_names(value):
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(name.strip() for item in value
                             if isinstance(name := item if isinstance(item, str) else item.get("name", item.get("label", "")) if isinstance(item, dict) else "", str)
                             and name.strip()))


def recover_selected(out):
    """Read complete cells before the known truncation; never complete their JSON."""
    cards = {row["document_id"]: row for row in (json.loads(line) for line in (out/"catalog.jsonl").read_text(encoding="utf-8").splitlines())}
    outcomes = []
    for doc_id in RECOVER_IDS:
        card = cards[doc_id]
        record = json.loads((out/f"versions/{card['selected_version']}.json").read_text(encoding="utf-8"))
        raw = record["raw_text"]
        pieces, cursor, recovered = [], 0, []
        for issue in card["table_issues"]:
            start = issue["offset"]
            pieces.append(clean_markup(raw[cursor:start]))
            marker = re.match(r":::table\{[^}\n]*\}\s*", raw[start:])
            pos = start+marker.end()
            row_number, cell_number, depth = 0, 0, 0
            while pos < len(raw):
                char = raw[pos]
                if char in " \r\n\t,":
                    pos += 1
                elif char == "[":
                    depth += 1
                    if depth == 2:
                        row_number += 1
                        cell_number = 0
                    pos += 1
                elif char == "]":
                    depth -= 1
                    pos += 1
                    if depth == 0:
                        break
                elif char == "{" and depth == 2:
                    try:
                        cell, size = json.JSONDecoder().raw_decode(raw[pos:])
                    except ValueError:
                        break
                    if not isinstance(cell.get("content"), str):
                        break
                    cell_number += 1
                    recovered.append({"row": row_number, "cell": cell_number, "raw_start": pos, "raw_end": pos+size,
                                      "attrs": cell.get("attrs", {}), "content": cell["content"]})
                    pos += size
                else:
                    break
            pieces.append("## 截断表中仍完整保存的单元格\n\n按原始行和单元格次序列出；不是补齐后的表格。后续未完成的单元格保留在原记录中。\n\n| 原始行 | 单元格序号 | 行跨度／列跨度 | 内容 |\n| --- | --- | --- | --- |")
            for cell in recovered:
                attrs = cell["attrs"]
                value = clean_markup(cell["content"]).replace("|", "\\|").replace("\n", "<br>")
                pieces.append(f"| {cell['row']} | {cell['cell']} | {attrs.get('rowspan', 1)}／{attrs.get('colspan', 1)} | {value} |")
            cursor = len(raw)
        if cursor < len(raw):
            pieces.append(readable_capture(raw[cursor:])[0])
        header = f"# {card['title']}：恢复阅读稿\n\n[原记录](../versions/{card['selected_version']}.json) · [基本阅读稿及旧摘要](../documents/{doc_id}.md) · [本次发现与使用限制](../recovery-notes.zh-CN.md)\n\n仅从同一保存版本恢复正文和完整单元格，不补写缺失内容。事实与发布日期仍按恢复说明判断。\n\n"
        put(out/f"recovered/{doc_id}.md", (header+"\n\n".join(pieces)+"\n").encode())
        put_json(out/f"recovered/{doc_id}.cells.json", recovered)
        outcomes.append({"document_id": doc_id, "title": card["title"], "selected_version": card["selected_version"],
                         "complete_cells_recovered": len(recovered), "truncated_json_table_found": bool(card["table_issues"]),
                         "external_fact_verification": "see recovery notes; not blanket verified"})
    put_json(out/"recovery.json", outcomes)
    index = ["# 重点恢复材料", "[全量材料目录](../README.zh-CN.md) · [恢复发现与使用限制](../recovery-notes.zh-CN.md)"]
    index += [f"- [{row['title']}]({row['document_id']}.md)" for row in outcomes]
    put(out/"recovered/README.zh-CN.md", ("\n\n".join(index)+"\n").encode())
    print("Selected recovery:", json.dumps(outcomes, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True, help="Parent of the two source checkouts and research-toolkit")
    parser.add_argument("--output", type=Path, required=True, help="New immutable corpus directory")
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        raise SystemExit("Choose a new output directory; existing corpus versions are immutable.")
    out.mkdir(parents=True)
    inventories, originals, records, lineage = [], {}, {}, []
    families, snippets, categories, graph = defaultdict(set), [], [], defaultdict(dict)
    generated_hashes = set()
    for repo, commit in PINS.items():
        root = args.inputs/repo
        files = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", commit], cwd=root, text=True).splitlines()
        for path in files:
            data = git_bytes(root, commit, path)
            original = f"{repo}/{path}"
            originals[original] = data
            entry = {"repository": repo, "commit": commit, "path": path, "sha256": sha(data), "bytes": len(data), "role": "code_or_documentation"}
            inventories.append(entry)
            if not path.endswith(".json"):
                continue
            obj = json.loads(data)
            entry.update(role="metadata", top_level_type=type(obj).__name__, top_level_count=len(obj))
            rows = obj.get("docs", []) if path == "public/kb_bm25.json" else obj
            if isinstance(rows, list) and rows and isinstance(rows[0], dict) and "id" in rows[0] and ("title" in rows[0] or path == "data/doc_list.json"):
                entry["role"] = "document_records"
                for i, row in enumerate(rows):
                    doc_id = "D-"+str(row["id"])
                    version = sha(encoded(row))
                    records.setdefault(version, row)
                    families[doc_id].add(version)
                    pointer = f"/docs/{i}" if path == "public/kb_bm25.json" else f"/{i}"
                    lineage.append({"document_id": doc_id, "version_id": version, "repository": repo, "commit": commit, "path": path, "pointer": pointer})
                    if row.get("raw_text_method") == "llm_generated_from_metadata":
                        generated_hashes.add(sha(row.get("raw_text", "").encode()))
            elif path == "data/collected_texts.json":
                entry["role"] = "title_keyed_excerpts"
                for title, fragments in obj.items():
                    snippets.append({"title": title, "fragments": fragments, "repository": repo, "commit": commit, "path": path,
                                     "pointer": "/"+title.replace("~", "~0").replace("/", "~1"), "evidence_status": "stored_excerpt_unverified"})
            elif path == "data/doc_categories.json":
                entry["role"] = "title_categories"
                categories = [{"category": category, "titles": titles} for category, titles in obj.items()]
            elif isinstance(obj, list) and ("nodes" in path or "edges" in path):
                kind = "nodes" if "nodes" in path else "edges"
                entry["role"] = "derived_"+kind
                for i, row in enumerate(obj):
                    key = sha(encoded(row))
                    graph[kind].setdefault(key, {"record_id": key, "original": row, "origins": []})["origins"].append({"repository": repo, "path": path, "pointer": f"/{i}"})

    put_json(out/"inventory.json", inventories)
    with zipfile.ZipFile(out/"history-inputs.zip", "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(originals.items()):
            archive.writestr(name, data)
    origins = defaultdict(list)
    for row in lineage:
        origins[row["version_id"]].append(row)
    title_ids = defaultdict(set)
    for doc_id, versions in families.items():
        for version in versions:
            record = records[version]
            title_ids[record.get("title", record.get("name", ""))].add(doc_id)
    normalized, catalog, table_count, damaged_tables = [], [], 0, []
    priority = {"data/knowledge_base.json": 0, "data/knowledge_base_rebuilt.json": 1, "data/docs.json": 2,
                "data/knowledge_base_public.json": 3, "data/kb_with_dates.json": 4}

    def capture_kind(row):
        raw = row.get("raw_text") or ""
        if raw and sha(raw.encode()) in generated_hashes:
            return "generated_from_metadata"
        return "stored_capture_unverified" if raw else "summary_or_metadata_only"

    def rank(version):
        row = records[version]
        return (0 if capture_kind(row) == "stored_capture_unverified" else 1,
                min(priority.get(origin["path"], 9) for origin in origins[version]), version)

    for version, row in sorted(records.items()):
        put_json(out/f"versions/{version}.json", row)
        normalized.append({"version_id": version, "document_id": "D-"+str(row["id"]), "record": f"versions/{version}.json",
                           "title": row.get("title", row.get("name", "")), "entities": entity_names(row.get("entities")),
                           "date_fields": {key: row[key] for key in ("date", "created_date") if row.get(key)},
                           "date_meaning": "original field; publication date not established",
                           "capture_kind": capture_kind(row), "summary_kind": "inherited_derivative_unverified"})
    for doc_id, versions in sorted(families.items()):
        selected = min(versions, key=rank)
        row = records[selected]
        title = row.get("title", row.get("name", doc_id))
        kind = capture_kind(row)
        source_origins = origins[selected]
        source = min(source_origins, key=lambda origin: (priority.get(origin["path"], 9), origin["repository"]))
        raw = row.get("raw_text") or ""
        body, tables, issues = readable_capture(raw) if raw else ("此记录没有原始正文；以下仅保留已有摘要。\n", 0, [])
        table_count += tables
        damaged_tables.extend({"document_id": doc_id, **issue} for issue in issues)
        card = {"document_id": doc_id, "title": title, "selected_version": selected,
                "selection": "existing capture preferred, then explicit file priority; not a chronology claim",
                "document": f"documents/{doc_id}.md", "version_count": len(versions), "capture_kind": kind,
                "entities": entity_names(row.get("entities")), "tags": row.get("tags", []),
                "date_fields": {key: row[key] for key in ("date", "created_date") if row.get(key)},
                "publication_date_verified": False, "factual_verification": "not_performed",
                "reuse_rights": "inherited; no additional redistribution or training rights established",
                "table_count": tables, "table_issues": issues}
        catalog.append(card)
        provenance = f"{source['repository']} @ {source['commit']} / {source['path']} #{source['pointer']}"
        lines = [f"# {title}", f"材料编号：{doc_id}。版本：{selected}。", f"来源：{provenance}",
                 f"[所选原记录](../versions/{selected}.json)；其他版本及出处见 `lineage.jsonl`。",
                 f"材料性质：`{kind}`。保存文本的完整性、事实与发布日期未据原站核实。",
                 "## 保存的正文" if kind == "stored_capture_unverified" else "## 原记录内容（不作原文证据）", body]
        if row.get("summary"):
            lines.extend(["## 旧生成摘要（未重写，未核实）", row["summary"]])
        if row.get("key_points"):
            lines.extend(["## 旧提取要点（未核实）", "\n".join("- "+str(item) for item in row["key_points"])])
        put(out/card["document"], ("\n\n".join(lines)+"\n").encode())
    for snippet in snippets:
        snippet["candidate_document_ids"] = sorted(title_ids.get(snippet["title"], []))
        snippet["link_basis"] = "exact title only; fragments are not merged into a document"
    for kind, rows in graph.items():
        for value in rows.values():
            original = value["original"]
            doc_ids = ([original["doc_id"]] if "doc_id" in original else original.get("doc_ids", original.get("sources", [])))
            value["unmatched_document_references"] = [str(item) for item in doc_ids if "D-"+str(item) not in families]
            value["evidence_status"] = "derived_navigation_only; no claim verification"
        put_lines(out/f"graph/{kind}.jsonl", sorted(rows.values(), key=lambda item: item["record_id"]))
    put_lines(out/"catalog.jsonl", catalog)
    put_lines(out/"versions.jsonl", normalized)
    put_lines(out/"lineage.jsonl", lineage)
    put_lines(out/"snippets.jsonl", snippets)
    put_json(out/"categories.json", categories)

    mappings = []
    for filename in ("sources.jsonl", "quarantined_sources.jsonl"):
        path = "evals/source_packs/ai_knowledge_sanitized/"+filename
        raw = git_bytes(args.inputs/"research-toolkit", TOOLKIT_PIN, path)
        put(out/"existing-source-pack"/filename, raw)
        for line in raw.splitlines():
            row = json.loads(line)
            mappings.append({"source_id": row["source_id"], "title": row["title"], "toolkit_commit": TOOLKIT_PIN,
                             "frozen_input_sha256": sha(raw), "frozen_file": path,
                             "document_ids": sorted(title_ids.get(row["title"], [])),
                             "basis": "exact title association; original sanitized pack unchanged",
                             "existing_disposition": "quarantined" if filename.startswith("quarantined") else "active",
                             "new_tasks_or_runs": 0})
    put_lines(out/"existing-source-map.jsonl", mappings)
    stats = {"source_commits": PINS, "input_files": len(inventories), "json_files": sum(item['path'].endswith('.json') for item in inventories),
             "document_occurrences": len(lineage), "document_families": len(families), "distinct_record_versions": len(records),
             "exact_duplicate_record_occurrences": len(lineage)-len(records),
             "selected_capture_kinds": dict(Counter(item["capture_kind"] for item in catalog)),
             "generated_text_hashes": len(generated_hashes), "title_keyed_excerpt_groups": len(snippets),
             "expanded_tables": table_count, "unexpanded_tables": damaged_tables,
             "distinct_graph_nodes": len(graph["nodes"]), "distinct_graph_edges": len(graph["edges"]),
             "mapped_existing_sources": len(mappings), "new_evaluation_tasks": 0, "new_model_runs": 0}
    put_json(out/"summary.json", stats)
    index = ["# AI 行业研究材料目录", "按题目选择材料，把所选正文作为当前研究的可选输入。原始捕获、旧摘要和元数据生成内容分别标注；没有自动事实认证。", "| 材料 | 正文性质 | 保留版本数 |", "| --- | --- | --- |"]
    index += [f"| [{item['title'].replace('|', '／')}]({item['document']}) | {item['capture_kind']} | {item['version_count']} |" for item in catalog]
    put(out/"README.zh-CN.md", ("\n\n".join(index[:2])+"\n\n"+"\n".join(index[2:])+"\n").encode())
    recover_selected(out)
    notes = Path(__file__).resolve().parents[1]/"corpora/ai-industry/recovery-notes.zh-CN.md"
    if notes.exists():
        put(out/"recovery-notes.zh-CN.md", notes.read_bytes())
    print(json.dumps({key: value for key, value in stats.items() if key != "unexpanded_tables"}, ensure_ascii=False, indent=2))
    print("Unexpanded tables:", len(damaged_tables))


if __name__ == "__main__":
    main()
