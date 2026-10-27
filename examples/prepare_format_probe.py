"""Prepare a paired request from one archived failure, or inspect a saved response.

Standard library only. No network calls and no environment actions are executed.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from workspace_action_contract import parse_output

CASE = "runs/deepseek/cedar-pilot-E/calls/002"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(root, output):
    freeze = read(root / "freeze.json")
    if freeze["study"] != "format-study-20260929":
        raise ValueError("Use the existing format-study-20260929 archive")
    folder = root / CASE
    request = read(folder / "request.json")
    response = read(folder / "response-1.json")
    transition = read(folder / "transition.json")
    parser = ROOT / "scripts/workspace_action_contract.py"
    frozen_parser = root.parent.parent / "scripts/workspace_action_contract.py"
    if sha(frozen_parser) != freeze["code"]["scripts/workspace_action_contract.py"]:
        raise ValueError("The archived action parser does not match its freeze")
    # The original archive has one CRLF line; Git checkouts normalize it.
    parser_hash = hashlib.sha256(parser.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    if parser.read_text(encoding="utf-8") != frozen_parser.read_text(encoding="utf-8"):
        raise ValueError("The local action parser differs from this archive's frozen parser")
    parsed = parse_output(response["visible_text"])
    if parsed["accepted"] or parsed["collector_feedback"]["error"] != "non_json_tool_markup":
        raise ValueError("The selected archived response is not the documented format failure")
    if transition["accepted"] or request.get("action_format_example") != freeze["example"]:
        raise ValueError("Expected a rejected E-condition turn with the existing format example")
    body = {
        "model": response["requested_model"],
        "messages": [
            {"role": "system", "content": freeze["system"]},
            {"role": "user", "content": json.dumps(request, ensure_ascii=False, separators=(",", ":"))},
        ],
        "max_tokens": response["max_output_tokens"],
        **response["parameters"],
    }
    if "response_format" in body:
        raise ValueError("The baseline already requests an output format")
    json_mode = copy.deepcopy(body)
    json_mode["response_format"] = {"type": "json_object"}
    sources = ["freeze.json", *(CASE + "/" + name for name in ("request.json", "response-1.json", "transition.json"))]
    manifest = {
        "archive": freeze["study"], "case": CASE, "endpoint": response["endpoint"],
        "source_sha256": {name: sha(root / name) for name in sources},
        "parser_sha256_lf": parser_hash,
        "payloads": ["text-request.json", "json-request.json"],
        "only_changed_parameter": "response_format",
        "archived_rejection": parsed["collector_feedback"]["error"],
        "historical_response_is_new_baseline": False,
        "model_calls": 0, "environment_actions": 0,
        "scope": "One selected historical failure state, not an unseen task or a complete rollout. JSON mode is not native function calling. No provider effectiveness has been measured.",
    }
    output.mkdir(parents=True, exist_ok=False)
    for name, value in [("text-request.json", body), ("json-request.json", json_mode), ("manifest.json", manifest)]:
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


def inspect(path):
    response = read(path)
    if "visible_text" in response:
        visible = response["visible_text"]
        finish = response.get("finish_reason")
    else:
        choice = response["choices"][0]
        visible = choice["message"].get("content")
        finish = choice.get("finish_reason")
    parsed = parse_output(visible)
    return {
        "response_sha256": sha(path), "finish_reason": finish,
        "response_complete": bool(visible) and finish == "stop",
        "envelope_accepted": parsed["accepted"], "action": parsed["action"],
        "collector_feedback": parsed["collector_feedback"],
        "reported_usage": response.get("usage"),
        "environment_actions": 0, "business_outcome_evaluated": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("prepare", help="Export two requests from the fixed archived failure")
    export.add_argument("root", type=Path, help="Extracted data/format-study-20260929 directory")
    export.add_argument("--output", type=Path, required=True, help="A new output directory")
    check = commands.add_parser("inspect", help="Inspect an archived capture or saved Chat Completions response")
    check.add_argument("response", type=Path)
    args = parser.parse_args()
    result = prepare(args.root, args.output) if args.command == "prepare" else inspect(args.response)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
