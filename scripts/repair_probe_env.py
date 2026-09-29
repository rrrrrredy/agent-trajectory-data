"""Counterexample-driven pure-function repair; the oracle is evaluator-only."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

import repair_env as base
import repair_executor as runner

VERSION = "research-repair-2"
ORACLE_ID = "scoped-event-dedup-v1"
TOOLS = (*base.TOOLS, "probe")
canonical, digest, check, equal = base.canonical, base.digest, base.check, base.equal
code_hash = base.code_hash

POLICY = copy.deepcopy(base.POLICY)
POLICY["workflow"] = (
    "Read the contract and current worker, and run the supplied public test examples. "
    "Those examples initially pass. Before patching, construct a valid input and its "
    "expected execution envelope, then use probe to demonstrate a contract violation. "
    "Patch solve(data), reread the worker, and rerun exactly the same input and expected "
    "envelope on the final worker with probe. Run test again, write_note with that "
    "successful regression_probe_id, update_ticket and submit. Test and probe receipts "
    "apply only to their exact code and version. On 409 reread before retrying."
)
POLICY["probe_boundary"] = (
    "probe runs only the supplied input on the current worker. matches_claim compares "
    "actual with your supplied expected; it does not establish that your expected "
    "answer is correct. Only final grading checks that expectation against the public "
    "contract, initial failure, same-case final retest and separate private behavior. "
    "The tool never supplies a reference answer or runs private examples."
)
POLICY["note_contract"]["regression_probe_id"] = "successful final-code probe id for the same pre-repair counterexample"
POLICY["grade_boundary"] = (
    "Final grading requires a genuine pre-repair counterexample with a contract-correct "
    "expected envelope, the same case passing on the final code before the note, current "
    "public tests and independent private behavior. Scenario, oracle and reference code "
    "are evaluator-only. This is a bounded synthetic task, not unrestricted execution."
)
HELP = copy.deepcopy(base.HELP)
HELP["probe"] = {
    "args": {"input": "valid contract input", "expected": "execution envelope: {ok:true,value:...} or {ok:false,error:string}"},
    "rule": "Executes only your input on the current worker. matches_claim is comparison with your assertion, not a correctness certificate.",
}
HELP["write_note"]["args"]["report"] = "policy note_contract object, including regression_probe_id"


def valid_input(data):
    if not isinstance(data, dict) or set(data) != {"events"} or not isinstance(data["events"], list) or len(data["events"]) > 32:
        return False
    for event in data["events"]:
        if not isinstance(event, dict) or set(event) != {"tenant_id", "event_id", "payload"}:
            return False
        if any(not isinstance(event[key], str) or len(event[key]) > 80 for key in event):
            return False
        if not event["tenant_id"] or not event["event_id"]:
            return False
    return True


def oracle(data):
    """Independent contract implementation: scan accepted rows, rather than key hashing."""
    check(valid_input(data), "probe_input_contract")
    accepted = []
    for current in data["events"]:
        previous = next((row for row in accepted if row["tenant_id"] == current["tenant_id"] and row["event_id"] == current["event_id"]), None)
        if previous is None:
            accepted.append(copy.deepcopy(current))
        elif previous["payload"] != current["payload"]:
            return {"ok": False, "error": "ValueError"}
    return {"ok": True, "value": accepted}


def expected_shape(value):
    if not isinstance(value, dict) or type(value.get("ok")) is not bool:
        return False
    if value["ok"]:
        valid = set(value) == {"ok", "value"}
    else:
        valid = set(value) == {"ok", "error"} and isinstance(value["error"], str) and 0 < len(value["error"]) <= 80
    if not valid:
        return False
    try:
        return len(canonical(value)) <= 20000
    except (TypeError, ValueError):
        return False


class ResearchEnv(base.ResearchEnv):
    def __init__(self, scenario):
        self.scenario = copy.deepcopy(scenario)
        check(scenario["version"] == VERSION and scenario["oracle_id"] == ORACLE_ID, "unsupported_scenario")
        check(type(scenario["max_steps"]) is int and 12 <= scenario["max_steps"] <= 100, "invalid_budget")
        self.reset()

    def reset(self, seed=0):
        super().reset(seed)
        self.probes = []
        self.initial.update(
            mechanism="counterexample_driven_program_repair",
            task="Construct a regression case from the public contract, reproduce a failure, repair the worker and verify the same case on final code.",
            tools=copy.deepcopy(HELP),
        )
        return copy.deepcopy(self.initial), {"environment_version": VERSION, "seed": seed}

    def snapshot(self):
        state = super().snapshot()
        state["probes"] = copy.deepcopy(self.probes)
        return state

    def _action(self, action, step):
        if not isinstance(action, dict) or set(action) != {"tool", "args"} or not isinstance(action["args"], dict):
            return {"status": 400, "error": "invalid_action"}
        tool, args = action["tool"], action["args"]
        if tool == "probe":
            if set(args) != {"input", "expected"} or not valid_input(args.get("input")):
                return {"status": 422, "error": "probe_input_contract"}
            if not expected_shape(args["expected"]):
                return {"status": 422, "error": "probe_expected_envelope"}
            actual = runner.execute(self.code, args["input"])
            row = {
                "probe_id": "probe-" + str(len(self.probes) + 1),
                "input": copy.deepcopy(args["input"]), "expected": copy.deepcopy(args["expected"]),
                "actual": actual, "matches_claim": equal(actual, args["expected"]),
                "version": self.version, "code_sha256": code_hash(self.code), "step": step,
            }
            self.probes.append(row)
            return {"status": 200, "probe": copy.deepcopy(row)}
        if tool == "write_note":
            report = args.get("report")
            fields = {"status", "scope", "code_sha256", "test_run_id", "diagnosis", "regression_probe_id"}
            if set(args) != {"report"} or not isinstance(report, dict) or set(report) != fields or not all(isinstance(value, str) for value in report.values()):
                return {"status": 422, "error": "report_contract"}
            key = "note-" + str(len(self.notes) + 1)
            self.notes[key] = {
                "report": copy.deepcopy(report), "step": step, "worker_version": self.version,
                "read_version": self.read_version, "test_ids": [row["test_run_id"] for row in self.tests],
                "probe_ids": [row["probe_id"] for row in self.probes],
            }
            return {"status": 200, "note_id": key}
        result = super()._action(action, step)
        if tool == "read" and result.get("status") == 200 and args.get("document_id") == self.scenario["document_ids"]["policy"]:
            result["body"] = copy.deepcopy(POLICY)
        return result

    def grade(self):
        result = super().grade()
        checks = result["checks"]
        initial_hash, final_hash = code_hash(self.scenario["initial_code"]), code_hash(self.code)
        note = self.notes.get((self.submission or {}).get("note_id"))
        pairs, baselines = [], []
        # Called for evaluator checkpoints too; no oracle output enters public actions.
        if self.terminated:
            patches = [event["step"] for event in self.events if event["action"]["tool"] == "patch" and event["observation"].get("status") == 200]
            first_patch = min(patches) if patches else None
            for probe in self.probes:
                if probe["version"] != 1 or probe["code_sha256"] != initial_hash or first_patch is None or probe["step"] >= first_patch:
                    continue
                expected = oracle(probe["input"])
                if equal(probe["expected"], expected) and not equal(probe["actual"], expected):
                    baselines.append(probe)
            for baseline in baselines:
                for fixed in self.probes:
                    if (fixed["step"] > baseline["step"] and fixed["version"] == self.version
                            and fixed["code_sha256"] == final_hash and fixed["matches_claim"]
                            and equal([baseline["input"], baseline["expected"]], [fixed["input"], fixed["expected"]])):
                        pairs.append({"baseline_probe_id": baseline["probe_id"], "fixed_probe_id": fixed["probe_id"]})
        checks["baseline_failure_observed"] = bool(baselines)
        checks["current_regression_pass"] = bool(pairs)
        fixed_ids = {pair["fixed_probe_id"] for pair in pairs}
        note_probe = (note or {}).get("report", {}).get("regression_probe_id")
        checks["regression_note_binding"] = bool(
            note and note_probe in fixed_ids and note_probe in note["probe_ids"]
            and any(probe["probe_id"] == note_probe and probe["step"] < note["step"] for probe in self.probes)
        )
        result.update(
            reward=int(all(checks.values())), grader_version=VERSION,
            assessed_capability="counterexample_driven_program_repair",
            validated_regression_pairs=pairs,
        )
        return result


def record(env, actor_kind):
    value = base.record(env, actor_kind)
    value["environment_version"] = VERSION
    return value


def verify_record(scenario, run):
    env = ResearchEnv(scenario)
    initial, _ = env.reset(run["seed"])
    check(run["environment_version"] == VERSION and run["task_id"] == scenario["task_id"] and run["scenario_sha256"] == digest(scenario), "scenario_binding_changed")
    check(equal(initial, run["initial_observation"]), "initial_observation_changed")
    for event in run["events"]:
        env.step(event["action"])
        check(equal(env.events[-1], event), "event_replay_changed")
    check(equal(env.snapshot(), run["final_state"]) and run["complete"] == env.finished, "final_state_changed")
    check(equal(env.grade(), run["grade"]), "grade_changed")
    return env.grade()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    env = ResearchEnv(json.loads(Path(args.scenario).read_bytes()))
    print(canonical({"observation": env.initial}), flush=True)
    for line in sys.stdin:
        if not line.strip():
            continue
        observation, reward, terminated, truncated, info = env.step(json.loads(line))
        Path(args.output).write_text(canonical(record(env, "external_policy")) + "\n", encoding="utf-8", newline="\n")
        print(canonical({"observation": observation, "reward": reward, "terminated": terminated, "truncated": truncated, "info": info}), flush=True)
        if env.finished:
            break


if __name__ == "__main__":
    main()
