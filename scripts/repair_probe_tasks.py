"""Scripted controls for the separately versioned self-authored regression task."""
from __future__ import annotations
import copy
import repair_probe_env as env

CONTROLS = ["no_probe", "forged_probe", "different_retest", "probe_after_patch", "probe_without_failure", "stale_probe"]

def run_reference(scenario, mutation=None):
    runtime = env.ResearchEnv(scenario)
    def act(tool, **args):
        return runtime.step({"tool": tool, "args": args})[0]
    ids = runtime.initial["document_roles"]
    for name in runtime.initial["documents"]:
        act("read", document_id=name)
    act("test")
    witness = copy.deepcopy(scenario["reference_probe"])
    if mutation == "forged_probe":
        witness["expected"] = {"ok": True, "value": []}
    if mutation == "probe_without_failure":
        case = scenario["public_cases"][0]
        witness = {"input": copy.deepcopy(case["input"]), "expected": copy.deepcopy(case["expected"])}
    if mutation not in {"no_baseline", "no_probe", "probe_after_patch"}:
        act("probe", **witness)
    if mutation != "initial_unfixed":
        target = scenario["partial_code"] if mutation == "partial_fix" else scenario.get("control_codes", {}).get(mutation, scenario["reference_code"])
        act("patch", if_version=runtime.version, old=runtime.code, new=target)
        act("read", document_id=ids["worker"])
    fixed_id = "missing-probe"
    if mutation not in {"no_probe", "no_retest"}:
        if mutation == "different_retest":
            case = scenario["public_cases"][0]
            witness = {"input": copy.deepcopy(case["input"]), "expected": copy.deepcopy(case["expected"])}
        fixed_id = act("probe", **witness)["probe"]["probe_id"]
    if mutation == "stale_probe":
        act("patch", if_version=runtime.version, old=runtime.code, new=runtime.code + "\n")
        act("read", document_id=ids["worker"])
    test = act("test")["test"]
    if mutation == "edit_after_test":
        act("patch", if_version=runtime.version, old=runtime.code, new=runtime.code + "\n")
        act("read", document_id=ids["worker"])
    report = {"status": "ready", "scope": "bounded_program_repair", "code_sha256": env.code_hash(runtime.code),
              "test_run_id": test["test_run_id"], "regression_probe_id": fixed_id,
              "diagnosis": "The supplied regression assertion reproduces the initial mismatch and is checked again against the edited worker."}
    if mutation == "wrong_binding":
        report["code_sha256"] = "0" * 64
    note = act("write_note", report=report)
    # Missing/invalid proof IDs remain recordable and are rejected by terminal grading.
    env.check(note["status"] == 200, "reference_note_rejected")
    ticket = act("update_ticket", if_version=runtime.ticket["version"], status="ready", note_id=note["note_id"])["ticket"]
    act("submit", note_id=note["note_id"], ticket_version=ticket["version"])
    return env.record(runtime, "scripted_negative_control" if mutation else "scripted_reference")
