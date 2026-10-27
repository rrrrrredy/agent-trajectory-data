"""Summarize archived study runs or render one complete observed case; no API calls."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import re


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def summary(root, task=None, provider=None, condition=None):
    rows = read(root / "results.json")["results"]
    rows = [r for r in rows if (not task or r["task"] == task) and (not provider or r["provider"] == provider) and (not condition or r["condition"] == condition)]
    if not rows:
        raise ValueError("No archived runs match the selected task, provider and condition")
    groups = defaultdict(list)
    for row in rows:
        groups[row["condition"]].append(row)
    totals = {}
    for condition, selected in sorted(groups.items()):
        totals[condition] = {
            "runs": len(selected), "successful": sum(r["reward"] == 1 for r in selected),
            "model_turns": sum(r.get("model_turns", r.get("steps", 0)) for r in selected),
            "format_rejections": sum(r["protocol_errors"] for r in selected),
            "environment_actions_excluding_format_rejections": sum(r["environment_steps"] if "environment_steps" in r else r["steps"] - r["protocol_errors"] for r in selected),
            "reported_input_tokens": sum(r["prompt_tokens"] for r in selected),
            "reported_output_tokens": sum(r["output_tokens"] for r in selected),
        }
    return {"tasks": sorted({r["task"] for r in rows}), "conditions": totals,
            "by_provider": {p: {c: {"runs": len(rs), "successes": sum(r["reward"] == 1 for r in rs), "reported_input_tokens": sum(r["prompt_tokens"] for r in rs)} for c in sorted(groups) if (rs := [r for r in rows if r["provider"] == p and r["condition"] == c])} for p in sorted({r["provider"] for r in rows})},
            "scope": "Reaggregation of archived results, not new model execution or semantic validation. These runs are diagnostic, training_eligible=false; source rights remain unchanged."}


def case(root, run_name, output, archive_url=None):
    root = Path(os.path.abspath(root))
    run = (root / "runs" / run_name).resolve()
    if not run.is_relative_to((root / "runs").resolve()):
        raise ValueError("--run must identify a directory inside runs/")
    episode = read(run / "episode.json")
    stats = read(run / "summary.json")
    relative_to = output.resolve().parent if output else Path.cwd()

    def reference(label, path):
        if archive_url:
            return label + ": `" + path.resolve().relative_to(root.resolve().parents[1]).as_posix() + "`"
        return "[" + label + "](" + Path(os.path.relpath(path, relative_to)).as_posix() + ")"

    def block(value):
        return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```"

    lines = [f"# {run_name}", "", "Archived model execution on constructed task material. This reading view is not an additional run, a training export or a new evaluation.", "", "## Task and recorded result", "", block({"task": episode["initial_observation"]["task"], "summary": stats, "grade": episode["grade"]}), "", "## Observed actions and results", "", "All recorded events follow in order. Old study format refusals are collector-generated events; new study refusals have no environment event. Use the separate model-round list below to inspect both.", ""]
    if archive_url:
        lines[4:4] = [f"[Download original archive]({archive_url}). Paths below are relative to the extracted archive; request/response files are available there. This page includes every observed event and final deliverable, not the full prompts or hidden final state.", ""]
    for event in episode["events"]:
        title = f"Event {event['step']}: {event['action']['tool']}"
        lines += ([f"<details><summary>{title}</summary>", "", block(event), "", "</details>", ""] if archive_url else [f"### {title}", "", block(event), ""])
    lines += ["## Model rounds, including refusals and retries", ""]
    for path in sorted((run / "calls").glob("*/transition.json")):
        transition = read(path)
        marker = transition.get("environment_event_index", "old collector: see event")
        responses = sorted(path.parent.glob("response-*.json"))
        lines += [f"- Round {path.parent.name}; accepted={transition.get('accepted', 'old collector')}; environment event={marker}. " + reference("Input", path.parent / "request.json") + " · " + reference("Parsed record", path) + " · " + " · ".join(reference(f"Response {i}", p) for i, p in enumerate(responses, 1))]
    lines += ["", "## Final delivered files", ""]
    for path in sorted((run / "deliverables").iterdir()):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            fence = "`" * max(3, max((len(s) for s in re.findall(r"`+", text)), default=0) + 1)
            lines += [f"### {path.name}", "", reference("Original file", path), "", fence, text, fence, ""]
    lines += ["The rendered case includes observed inputs and final outputs, not the entire hidden final environment state. Original source and usage restrictions apply; publication does not itself grant training rights.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="data/usefulness-study-20260929 or data/format-study-20260929 from the existing release")
    parser.add_argument("--run", help="For example kimi/wren-delivery-A or longcat/cedar-pilot-N")
    parser.add_argument("--output", type=Path, help="Write a new case Markdown file; existing files are never replaced")
    parser.add_argument("--archive-url", help="Publish a portable reading view with an archive download link, archive-relative paths and collapsible events")
    parser.add_argument("--task", help="Filter summary by the original task name")
    parser.add_argument("--provider", help="Filter summary by the original provider name")
    parser.add_argument("--condition", help="Filter summary by the original study condition")
    args = parser.parse_args()
    if args.output and not args.run:
        parser.error("--output requires --run")
    if args.archive_url and not args.run:
        parser.error("--archive-url requires --run")
    if args.run and any((args.task, args.provider, args.condition)):
        parser.error("Summary filters cannot be combined with --run")
    result = case(args.root, args.run, args.output, args.archive_url) if args.run else json.dumps(summary(args.root, args.task, args.provider, args.condition), ensure_ascii=False, indent=2)
    if args.output:
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(result)
        print(args.output)
    else:
        print(result)


if __name__ == "__main__":
    main()
