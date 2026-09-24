"""Client-side agent adapter. The service never receives or executes client code."""
from __future__ import annotations
import json
import urllib.request
import uuid
from pathlib import Path
from .core import read, invoke_policy, write_new


def evaluate_api(url, key_file, output, limit=10, command_config=None):
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("invalid_client_task_limit")
    # Remote deployments require an explicitly configured HTTPS endpoint.
    if not (url.startswith("http://127.0.0.1:") or url.startswith("https://")):
        raise ValueError("https_or_loopback_required")
    token = read(key_file)["token"]
    command = read(command_config)["argv"] if command_config else None
    def request(path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(url.rstrip("/") + path, data=data, headers={
            "Authorization": "Bearer " + token, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.load(response)
    catalogue = request("/v1/tasks")
    selected = catalogue["tasks"][:limit]
    if not selected:
        raise ValueError("no_available_tasks")
    records = []
    for item in selected:
        state = request("/v1/trials", {"request_id": uuid.uuid4().hex, "task_id": item["task_id"]})
        identifier = state["trial_id"]
        while state["status"] == "running":
            action = invoke_policy("command" if command else "reference", state["task"],
                                   state["observations"], command=command, timeout=10)
            state = request("/v1/trials/" + identifier + "/actions", {
                "request_id": uuid.uuid4().hex, "expected_step": state["step"], "action": action})
        records.append({"task_id": item["task_id"], "trial_id": identifier,
                        "steps": state["step"], "evaluation": state["evaluation"],
                        "terminal_reason": state["terminal_reason"]})
    report = {"actor_kind": "external_command" if command else "scripted_control_client",
              "model_identity": "unverified", "trials": records, "summary": {
                  outcome: sum(x["evaluation"]["outcome"] == outcome for x in records)
                  for outcome in ("pass", "fail", "not_assessed")}}
    write_new(Path(output), report)
    return {"output": str(Path(output).resolve()), "actor_kind": report["actor_kind"], **report["summary"]}
