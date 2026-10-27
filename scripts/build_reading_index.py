"""Build a task index and portable cases from the two existing public study archives."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from read_study import case, read

ARCHIVES = {
    "usefulness": "https://github.com/rrrrrredy/agent-trajectory-data/releases/download/study-2026-09-29/workspace-usefulness-20260929.zip",
    "format": "https://github.com/rrrrrredy/agent-trajectory-data/releases/download/format-study-2026-09-29/workspace-format-20260929.zip",
}
TASKS = {
    "wren-delivery": ("写入结果未知时如何恢复", "观察同一 operation_id 的查询与重试，以及两份交付件的最终一致性。"),
    "cedar-pilot": ("证据变化后，内容与结构是否都修正", "区分新数据读取、保护文字恢复、公开校验和最终内容评分。"),
    "linden-retention": ("关键材料缺失时是否正确阻塞", "观察是否保留未解决交付件，并检查对同一缺失材料的重复读取。"),
    "harbor-backlog": ("结论不变时，是否仍修正基础数据", "核对已关闭数量和剩余积压，不能因队列结论未变就保留错误数值。"),
}
CASES = {
    ("usefulness", "kimi/wren-delivery-A"): ("wren-write-recovery", "写入未知后的查询与重试", "16 回合、0 次格式拒绝，最终评分 1。504 是构造环境的预设故障。基础条件已经成功，不能归功于完整示范。"),
    ("format", "longcat/cedar-pilot-N"): ("cedar-content-failure", "校验通过但内容交付失败", "28 回合包含 8 次格式拒绝、20 次环境动作。数值 74 正确，但最终结构缺少 success_percent 层，最终评分 0；错误输出原样保留。"),
    ("usefulness", "glm/linden-retention-C"): ("linden-correct-block", "正确阻塞与重复读取", "18 回合包含 2 次格式拒绝，读取同一缺失材料 5 次。最终评分 1 表示正确阻塞，不表示原业务目标已完成；单次对照不能建立因果。"),
}


def build(roots, output):
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output must be empty; preserve existing reading notes")
    output.mkdir(parents=True, exist_ok=True)
    records, sources = [], {}
    for study, root in roots.items():
        path = root / "results.json"
        sources[study] = {"archive_url": ARCHIVES[study], "results_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for row in read(path)["results"]:
            run = row["provider"] + "/" + row["task"] + "-" + row["condition"]
            records.append({"study": study, "task": row["task"], "provider": row["provider"], "condition": row["condition"],
                "run": run, "archive_path": "data/" + root.name + "/runs/" + run,
                "reward": row["reward"], "ticket_status": row["ticket_status"], "failed_checks": row["failed_checks"],
                "model_turns": row.get("model_turns", row.get("steps", 0)), "format_rejections": row["protocol_errors"],
                "environment_actions": row["environment_steps"] if "environment_steps" in row else row["steps"] - row["protocol_errors"],
                "reported_input_tokens": row["prompt_tokens"], "training_eligible": row["training_eligible"]})
    lines = ["# 按任务读轨迹", "", "本目录覆盖两份已发布研究归档的 4 个开发任务、80 次执行；不是整个仓库所有版本的任务清单。它把同一个任务的不同模型与条件放在一起，保留失败和正确阻塞。", "",
        "[首次使用与研究发现](../START-HERE.zh-CN.md) · [v0.16 消费包说明](../DATASET-v0.16.zh-CN.md) · [全部历史资产](../PUBLIC-EVALUATIONS.zh-CN.md) · [机器可读目录](catalog.json)", "",
        "任务材料为原创构造记录，轨迹来自实际模型执行。这 80 次执行均为诊断用途，不进入训练导出；[现有许可](../../LICENSE)未改变。", "", "## 先选一个完整案例", "",
        "以下页面包含全部可观察事件和最终交付文件；模型回合逐一给出归档路径，完整请求与响应需下载原包。折叠事件便于阅读，没有删除中间失败。", ""]
    for (study, run), (slug, title, note) in CASES.items():
        path = output / (slug + ".md")
        content = case(roots[study], run, path, ARCHIVES[study])
        content = content.replace("# " + run, "# " + title + "\n\n[返回任务目录](README.md)\n\n" + note + "\n\n执行：`" + run + "`", 1)
        path.write_text(content, encoding="utf-8", newline="\n")
        lines += [f"- [{title}]({slug}.md)：{note}"]
    lines += ["", "## 四个任务", "", "| 问题 | 任务 | 执行数 |", "| --- | --- | ---: |"]
    for task, (title, note) in TASKS.items():
        lines.append(f"| [{title}](#{task}) | `{task}` | {sum(r['task'] == task for r in records)} |")
    lines += ["", "A/B/C 分别为基础说明、短经验摘要、完整示范；N/E 为另一轮修复接口后的无格式示例／单个 JSON 示例。只在同一轮内比较；跨轮差异不能直接归因于示范长度。输入 token 是供应商上报口径，不是统一货币成本。", ""]
    for task, (title, note) in TASKS.items():
        lines += [f"## {task}", "", f"**{title}。** {note}", "",
            "| 研究 | 模型 | 条件 | 最终评分 | 交付状态 | 回合 | 格式拒绝 | 环境动作 | 输入 token | 完整案例 |",
            "| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | --- |"]
        for r in sorted((r for r in records if r["task"] == task), key=lambda r: (r["study"], r["provider"], r["condition"])):
            selected = CASES.get((r["study"], r["run"]))
            case_link = f"[打开]({selected[0]}.md)" if selected else "见原归档"
            lines.append(f"| {r['study']} | {r['provider']} | {r['condition']} | {r['reward']} | {r['ticket_status']} | {r['model_turns']} | {r['format_rejections']} | {r['environment_actions']} | {r['reported_input_tokens']:,} | {case_link} |")
        lines += ["", f"原记录位置：各归档的 `data/<研究目录>/runs/<provider>/{task}-<condition>/`；每条精确路径也保留在 catalog.json。", ""]
    lines += ["## 下载与筛选", "", f"[用途实验原包]({ARCHIVES['usefulness']}) · [格式实验原包]({ARCHIVES['format']})", "",
        "在仓库根目录运行，路径替换为实际解压位置：", "", "```sh",
        "python -X utf8 examples/read_study.py ../format/data/format-study-20260929 --task cedar-pilot --provider longcat --condition N",
        "python -X utf8 scripts/build_reading_index.py --usefulness-root ../usefulness/data/usefulness-study-20260929 --format-root ../format/data/format-study-20260929 --output ../rebuilt-reading-index",
        "```", "", "目录由原 results.json 汇总，案例由原 episode.json、summary.json、calls 和 deliverables 生成，不重新调用模型或评审。生成输入的哈希见 catalog.json；输出目录须为空，避免覆盖阅读笔记。", ""]
    (output / "README.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    catalog = {"sources": sources, "task_count": len({r["task"] for r in records}), "run_count": len(records), "records": records}
    (output / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    return {"tasks": catalog["task_count"], "runs": len(records), "portable_cases": len(CASES)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usefulness-root", type=Path, required=True)
    parser.add_argument("--format-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build({"usefulness": args.usefulness_root, "format": args.format_root}, args.output)))
