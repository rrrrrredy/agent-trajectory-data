"""Build task + trajectory + environment + verifier dataset. Standard library only."""
from __future__ import annotations
import argparse
import difflib
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
import time
import zipfile
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent
def module(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+".py"))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
corpus=module("research_corpus");rd=corpus.rd;check=corpus.check
repair=module("runtime_tasks");business=module("business_env")
VERSION="agent-runtime-v4"
SOURCE_SESSION="01a0cdac-218f-7070-82a2-f0506bdbeaf6"
POLICY={"split":"development","rights":rd.RIGHTS,"training_eligible":False}
# Exact selected source windows. They do not include deleted commerce work or system context.
PREFIX_END=3059
WINDOWS=((2099,2113),(2422,2449),(2664,2821),(2915,PREFIX_END))
INCIDENTS=[
 {"incident_id":"jsonl-observation","failure_line":2103,"diagnosis_lines":[2109,2113],
  "patch_lines":[2109],"retry_lines":[2113],"verification_lines":[2775],
  "finding":"A line-oriented inspection used Unicode splitlines and broke a JSON string at a legal separator.",
  "verification_boundary":"Later LF-only parser and its regression tests; this source window does not contain the whole first implementation."},
 {"incident_id":"credential-product-false-positive","failure_line":2435,"diagnosis_lines":[2439,2442],
  "patch_lines":[2446],"retry_lines":[2449],"verification_lines":[2449],
  "finding":"The credential pattern matched sk- inside a longer product URL; add a left token boundary.",
  "verification_boundary":"Candidate build and its internal checks completed; no claim that pattern matching proves absence of every secret."},
 {"incident_id":"native-final-mismatch","failure_line":2681,"diagnosis_lines":[2685,2688],
  "patch_lines":[2692],"retry_lines":[2695],"verification_lines":[2748,2775],
  "finding":"Native final messages include a trailing client citation footer absent from the CLI export.",
  "verification_boundary":"The immediate retry passed that check but then failed on a different manifest schema."},
 {"incident_id":"legacy-hash-key","failure_line":2695,"diagnosis_lines":[2699,2702],
  "patch_lines":[2706],"retry_lines":[2709],"verification_lines":[2748,2775],
  "finding":"Some historical report references retain only the LF-normalized digest; byte digest is optional, LF binding is not.",
  "verification_boundary":"The immediate retry progressed to a separate material-selection error."},
 {"incident_id":"unnecessary-plan-material","failure_line":2709,"diagnosis_lines":[2713,2716],
  "patch_lines":[2720],"retry_lines":[2723],"verification_lines":[2748,2775],
  "finding":"A whole runtime plan included an unnecessary thinking configuration field. Keep only the needed frozen packet.",
  "verification_boundary":"No hidden reasoning content was recovered; the next attempt failed on packet layout."},
 {"incident_id":"formal-packet-binding","failure_line":2723,"diagnosis_lines":[2729,2733],
  "patch_lines":[2739],"retry_lines":[2745,2748],"verification_lines":[2748,2775,2821],
  "finding":"Formal payload lives in plan.packet, unlike the component input file, and uses a different JSON hash serialization.",
  "verification_boundary":"Source code and component binding checked, then full build, tests and independent exports verified."},
]
INCIDENTS.extend([{'incident_id': 'source-event-pointer', 'failure_line': 2969, 'diagnosis_lines': [2973, 2976], 'patch_lines': [2980], 'retry_lines': [2982, 2996], 'verification_lines': [2996], 'finding': 'The chosen source line was usage metadata; actual failure was in the wait tool result two lines later.', 'verification_boundary': 'Correcting the pointer allowed projection and task execution; this candidate later failed on environment replay.'}, {'incident_id': 'serialized-observation-order', 'failure_line': 2996, 'diagnosis_lines': [3000, 3003], 'patch_lines': [3010], 'retry_lines': [3017, 3021], 'verification_lines': [3021], 'finding': 'Sorting JSON object keys changed document insertion order after reload, so search observations diverged; sort search results by document ID.', 'verification_boundary': 'The new save-load-action regression passes; final bundle acceptance independently repeats all recorded transitions.'}])

INCIDENTS.append({'incident_id': 'negative-control-erased-by-serialization', 'failure_line': 3043, 'diagnosis_lines': [3048, 3051], 'patch_lines': [3048], 'retry_lines': [3056, 3059], 'verification_lines': [3059], 'finding': 'Serializing test inputs with sorted object keys removed the deliberately unordered baseline, so the broken program incorrectly passed. Preserve raw input order inside a JSON string.', 'verification_boundary': 'The corrected control now produces 0,0,1,1 for initial, partial, reference and reset-reference; full-suite results are separately recorded.'})

def textparts(value):
    if isinstance(value,str):return value
    return "\n".join(p.get("text","") for p in value if isinstance(p,dict) and p.get("type") in {"text","input_text","output_text"})
def scrub(text):
    return corpus.history.scrub(text,r"D:\Codex\agent-trajectory-data")
def processing_projection(session):
    raw=Path(session).read_bytes();lines=raw.split(b"\n")
    check(len(lines)>PREFIX_END,"source_prefix_incomplete")
    check(json.loads(lines[0])["payload"]["id"]==SOURCE_SESSION,"wrong_processing_source_session")
    prefix=b"\n".join(lines[:PREFIX_END])+b"\n"
    events=[];kinds=Counter()
    for number,line in enumerate(lines[:PREFIX_END],1):
        if not any(a<=number<=b for a,b in WINDOWS):continue
        row=json.loads(line);q=row.get("payload",{});kind=q.get("type")
        if row["type"]!="response_item":continue
        base={"event_id":"processing-"+str(number),"source_line":number,
              "source_line_sha256":rd.sha(line),"timestamp":row.get("timestamp")}
        if kind in {"custom_tool_call","function_call"}:
            value=q.get("input",q.get("arguments",""))
            base.update(kind="tool_call",call_id=q["call_id"],name=q["name"],arguments=scrub(value))
        elif kind in {"custom_tool_call_output","function_call_output"}:
            value=textparts(q["output"])
            base.update(kind="tool_result",call_id=q["call_id"],output=scrub(value),
                        truncation_marker_present=bool(__import__("re").search("truncated",value,__import__("re").I)))
        elif kind=="message" and q.get("role")=="assistant" and (q.get("phase") or q.get("channel"))=="commentary":
            base.update(kind="assistant_message",text=scrub(textparts(q.get("content",[]))))
        else:
            kinds["excluded_"+str(kind)]+=1;continue
        events.append(base)
    by_line={e["source_line"]:e for e in events}
    # A yielded exec resumes through a wait result; source event 2435 may differ by tool shape.
    for item in INCIDENTS:
        check(item["failure_line"] in by_line,"missing_failure_source:"+item["incident_id"])
        for key in ("diagnosis_lines","patch_lines","retry_lines","verification_lines"):
            check(all(n in by_line for n in item[key]),"missing_incident_edge:"+item["incident_id"]+":"+key)
    calls={e["call_id"] for e in events if e["kind"]=="tool_call"}
    outputs={e["call_id"] for e in events if e["kind"]=="tool_result"}
    check(calls==outputs,"processing_call_pair_missing")
    return events,{"source_session_id":SOURCE_SESSION,"frozen_prefix_line_count":PREFIX_END,
                   "frozen_prefix_bytes":len(prefix),"frozen_prefix_sha256":rd.sha(prefix),
                   "selected_windows":[list(w) for w in WINDOWS],"projection_version":1,
                   "excluded_counts":dict(kinds),"raw_source_included":False,
                   "boundary":"Selected visible records only; commands are inert text and not replayed."}

def runtime_manifest():
    return {"kind":"local_cpython_stdlib","python_version":platform.python_version(),
            "implementation":platform.python_implementation(),"platform":platform.platform(),
            "interpreter_sha256":rd.sha(Path(sys.executable).read_bytes()),
            "entrypoints":{"repair":"python -I -B tests/verify.py WORKSPACE",
                           "business":"python business_env.py SCENARIO.json"},
            "dependencies":[],"external_network_required":False,"docker_available":shutil.which("docker") is not None,
            "container_execution_verified":False,
            "isolation":{"repair":"fresh working directory and isolated Python import mode; no OS security sandbox",
                         "business":"in-memory state, allowlisted JSON actions; no arbitrary code tool"},
            "supported_runtime":"CPython 3.11; recorded version is the version actually exercised",
            "repair_timeout_per_test_seconds":3,
            "business_step_limit":30}

def write_repair(root,spec):
    path=root/"tasks"/spec["task_id"]
    rd.put(path/"instruction.md",spec["instruction"].encode("utf-8")+b"\n")
    rd.put(path/"environment/worker.py",spec["initial"].encode("utf-8"))
    rd.put_json(path/"environment/runtime.json",{"python":"3.11","dependencies":[],"external_network_required":False})
    rd.put(path/"tests/verify.py",repair.VERIFIER.encode("utf-8"))
    rd.put_json(path/"tests/cases.json",spec["cases"])
    rd.put(path/"solution/worker.py",spec["reference"].encode("utf-8"))
    rd.put(path/"solution/solve.py",repair.SOLVER.encode("utf-8"))
    rd.put(path/"controls/partial.py",spec["partial"].encode("utf-8"))
    meta={"task_id":spec["task_id"],"family_id":"dataset-processing",
          "origin":spec["origin"],"parent_incident":spec["source_incident"],**POLICY,
          "grading":{"reward":"1 iff every behavioral test passes, else 0","case_count":len(spec["cases"]),
                     "partial_fraction":"diagnostic only","quality_scope":"specified deterministic contract"},
          "environment":"environment/runtime.json","reference_solution":"solution/solve.py",
          "verifier":"tests/verify.py","minimal_reproduction":True,"original_source_code_claim":False}
    rd.put_json(path/"task.json",meta)
    return meta

def grader(task,workspace):
    spec=importlib.util.spec_from_file_location("task_verifier",task/"tests/verify.py")
    v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
    return v.grade(workspace)

def repair_controls(root,spec):
    path=root/"tasks"/spec["task_id"]
    runroot=root/"executions"/spec["task_id"]
    events=[];attempts=[]
    previous=None
    for n,phase in enumerate(("initial","partial","reference","reset_reference"),1):
        workspace=runroot/phase/"workspace";workspace.mkdir(parents=True)
        source=(path/"environment/worker.py" if phase=="initial" else path/"controls/partial.py" if phase=="partial" else path/"solution/worker.py")
        before=previous or (path/"environment/worker.py").read_text(encoding="utf-8")
        after=source.read_text(encoding="utf-8")
        rd.put(workspace/"worker.py",source.read_bytes())
        events.append({"event_id":spec["task_id"]+"-patch-"+str(n),"kind":"reset" if phase in {"initial","reset_reference"} else "file_change",
                       "actor_kind":"scripted_control","phase":phase,"step":len(events)+1,
                       "before_sha256":rd.sha(before.encode()),"after_sha256":rd.sha(after.encode()),
                       "diff":"".join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile="before/worker.py",tofile="after/worker.py")),
                       "decision_basis":"predeclared control sequence, not inferred historical model reasoning"})
        events.append({"kind":"tool_call","step":len(events)+1,"phase":phase,
                       "tool":"python_verifier","arguments":{"workspace":"executions/"+spec["task_id"]+"/"+phase+"/workspace"}})
        result=grader(path,workspace)
        rd.put_json(runroot/phase/"result.json",result)
        events.append({"kind":"tool_result","step":len(events)+1,"phase":phase,"result":result})
        attempts.append({"attempt_id":spec["task_id"]+"-"+phase,"task_id":spec["task_id"],"phase":phase,
                         "actor_kind":"scripted_control","reward":result["reward"],
                         "result_path":(runroot/phase/"result.json").relative_to(root).as_posix(),
                         "retry_of":attempts[-1]["attempt_id"] if attempts and phase!="reset_reference" else None,
                         "worker_sha256":result["worker_sha256"],**POLICY})
        previous=after
    check([a["reward"] for a in attempts]==[0,0,1,1],"repair_controls_failed:"+spec["task_id"])
    rd.put_lines(runroot/"events.jsonl",events)
    return attempts

def business_controls(root,scenario):
    task_id=scenario["task_id"];attempts=[]
    modes=["reference","empty","wrong_answer","repeat_reference"]
    if scenario["fault"]=="concurrent_edit":modes.append("ignore_conflict")
    for mode in modes:
        env=business.BusinessEnv(scenario);business.reference_policy(env,"reference" if mode=="repeat_reference" else mode)
        run={"attempt_id":task_id+"-"+mode,"task_id":task_id,"actor_kind":"scripted_control","mode":mode,
             "events":env.events,"outcome":env.outcome,"final_state":env.snapshot(),**POLICY}
        path="executions/"+task_id+"/"+mode+".json";rd.put_json(root/path,run)
        expected=int(mode in {"reference","repeat_reference"})
        check(env.outcome["reward"]==expected,"business_control_failed:"+run["attempt_id"])
        attempts.append({"attempt_id":run["attempt_id"],"task_id":task_id,"actor_kind":"scripted_control",
                         "phase":mode,"reward":env.outcome["reward"],"result_path":path,
                         "retry_of":None,**POLICY})
    a=rd.load_json(root/attempts[0]["result_path"]);b=rd.load_json(root/attempts[3]["result_path"])
    check(a["events"]==b["events"] and a["outcome"]==b["outcome"],"business_reset_nondeterministic")
    return attempts

def coverage(prior,tasks):
    rows=[]
    def add(identity,kind,task,trajectory,environment,grading,refs,missing):
        rows.append({"record_id":identity,"kind":kind,"task":task,"trajectory":trajectory,
                     "environment":environment,"grading":grading,"references":refs,"missing":missing,
                     "fully_executable":environment in {"local_cpython","offline_stateful"},
                     **POLICY})
    for t in rd.load_lines(prior/"tasks.jsonl"):
        add(t["task_id"],"report_review","exact_frozen_payload","retained_review_request_response",
            "frozen_input_only","protocol_checks_and_fallible_model_judgments",
            ["prior/"+t["input_path"],"prior/reviews.jsonl","rubrics/archived-review.json"],
            ["original_author_actions_not_in_this_input","external_services_not_reconstructed","quality_gold_label_unavailable"])
    for r in rd.load_lines(prior/"prior/runs.jsonl"):
        add(r["run_id"],"research_run","archived_prompt","visible_messages_tools_artifacts",
            "recorded_observations_only","artifact_binding_and_recorded_reviews",
            ["prior/prior/runs.jsonl","prior/sources/native/"+r["run_id"]+".jsonl","environments/historical.json"],
            ["complete_web_state_unavailable","truncated_returns_not_recovered","quality_gold_label_unavailable"])
    for t in rd.load_lines(prior/"prior/base/tasks.jsonl"):
        runnable=t["profile"]=="registry-links-v1"
        add(t["task_id"],t["profile"],"archived_prompt",
            "scripted_controls" if runnable else "archived_model_response",
            "frozen_registry_tool_simulation" if runnable else "frozen_input_only",
            "deterministic_registry_links" if runnable else "protocol_and_model_judgment",
            ["prior/prior/base/tasks.jsonl","prior/prior/base/verify_dataset.py"],
            [] if runnable else ["original_drafting_runtime_not_retained","quality_gold_label_unavailable"])
        rows[-1]["fully_executable"]=runnable
    for c in rd.load_lines(prior/"prior/semantic_cases.jsonl"):
        add(c["case_version_id"],"semantic_fixture","frozen_case","archived_model_reviews",
            "frozen_input_only","fallible_authored_expectation_and_model_judgments",
            ["prior/prior/semantic_cases.jsonl","prior/prior/judgments.jsonl","rubrics/archived-review.json"],
            ["no_deterministic_quality_oracle"])
    for t in tasks:
        new_repair=t.get("minimal_reproduction",False)
        add(t["task_id"],"repair" if new_repair else "business_handoff",
            "instruction_and_initial_state","executed_scripted_controls",
            "local_cpython" if new_repair else "offline_stateful","deterministic_behavior_or_state_verifier",
            ["tasks/"+t["task_id"],"executions/"+t["task_id"]],
            ["new_model_rollout_not_run","training_rights_not_granted"]+([] if new_repair else ["organization_context_is_synthetic"]))
    return rows

def build(prior,session,output):
    prior=Path(prior).resolve();output=Path(output).resolve()
    check(not output.exists(),"output_already_exists")
    corpus.verify_dataset(prior)
    events,source=processing_projection(session)
    output.mkdir(parents=True);shutil.copytree(prior,output/"prior")
    for name in ("research_dataset.py","research_history.py","research_corpus.py","runtime_tasks.py","business_env.py"):
        rd.put(output/name,(HERE/name).read_bytes())
    rd.put(output/"verify_dataset.py",Path(__file__).read_bytes())
    rd.put(output/"LICENSE",(prior/"LICENSE").read_bytes())
    rd.put_lines(output/"processing/events.jsonl",events)
    rd.put_json(output/"processing/source.json",source)
    incidents=[]
    for item in INCIDENTS:
        row=dict(item,origin="observed_model_tool_execution",interpretation="posthoc_evidence_linked_summary",
                 source_events=["processing-"+str(n) for key in ("diagnosis_lines","patch_lines","retry_lines","verification_lines") for n in item[key]],
                 hidden_reasoning_reconstructed=False,**POLICY)
        incidents.append(row)
    rd.put_lines(output/"processing/incidents.jsonl",incidents)
    tasks=[];attempts=[]
    for spec in repair.task_specs():
        tasks.append(write_repair(output,spec));attempts.extend(repair_controls(output,spec))
    base=prior/"prior/base"
    for report,family in corpus.history.family_map(prior/"prior").items():
        folder=base/"assets/reports"/report/"data"
        sources=rd.table_rows(folder/"source_registry.csv");claims=rd.table_rows(folder/"claims_registry.csv")
        for fault in ("clean","missing_reference","tool_retry","access_revoked","concurrent_edit"):
            scenario=business.make_scenario(report,family,sources,claims,fault)
            scenario["source_artifacts"]=[{"path":"prior/prior/base/assets/reports/"+report+"/data/"+name,
                                          "sha256":rd.sha((folder/name).read_bytes())}
                                         for name in ("source_registry.csv","claims_registry.csv")]
            path=output/"tasks"/scenario["task_id"]
            rd.put_json(path/"environment/scenario.json",scenario)
            rd.put(path/"instruction.md",business.INSTRUCTION.encode("utf-8"))
            rd.put_json(path/"rubric.json",{"terminal_reward":"1 iff decision, scope, observed evidence, ticket, note and retry budget pass",
                        "step_reward":0,"limits":"Does not grade prose quality, truth of cited web pages or broad business value."})
            rd.put(path/"solution/reference.py",b"import sys\nfrom pathlib import Path\nsys.path.insert(0,str(Path(__file__).resolve().parents[3]))\nfrom business_env import BusinessEnv,reference_policy,stable\ne=BusinessEnv.from_file(Path(__file__).resolve().parents[1]/'environment/scenario.json')\nreference_policy(e)\nprint(stable({'events':e.events,'outcome':e.outcome}))\n")
            rd.put(path/"tests/verify.py",b"import sys\nfrom pathlib import Path\nsys.path.insert(0,str(Path(__file__).resolve().parents[3]))\nfrom verify_dataset import verify_business_run\nr=verify_business_run(Path(__file__).resolve().parents[3],Path(sys.argv[1]))\nimport json\nprint(json.dumps(r,ensure_ascii=False))\nraise SystemExit(0 if r[\"reward\"] else 1)\n")
            meta={"task_id":scenario["task_id"],"family_id":family,"origin":scenario["origin"],
                  "environment":"environment/scenario.json","verifier":"tests/verify.py",
                  "reference_solution":"solution/reference.py","fault":fault,"report":report,**POLICY}
            rd.put_json(path/"task.json",meta);tasks.append(meta);attempts.extend(business_controls(output,scenario))
    rd.put_json(output/"environments/current.json",runtime_manifest())
    rd.put_json(output/"environments/historical.json",{
        "mode":"observation_replay_only","full_execution_environment_reconstructed":False,
        "available":["frozen_prompts","retained_tool_arguments","available_tool_returns","artifact_snapshots","hashes"],
        "missing":["original_external_web_state","service_runtime","unreturned_output","complete_author_trajectories_for_review_only_records"],
        "recovery":"Use explicit derived tasks for live execution; never fill historical gaps with invented actions."})
    rd.put_json(output/"rubrics/archived-review.json",{
        "protocol":"Check exact frozen input binding, response state, failure retention and source-artifact hashes.",
        "quality_score":None,"quality_status":"not_assessed",
        "model_judgments":"Retained as fallible opinions with provider, version and input binding.",
        "source_adjudications":"Inherited records, not promoted to independent gold.",
        "training_eligible":False})
    rd.put_lines(output/"tasks.jsonl",tasks);rd.put_lines(output/"attempts.jsonl",attempts)
    rd.put_lines(output/"coverage.jsonl",coverage(output/"prior",tasks))
    rd.put(output/"DATA_CARD.md",DATA_CARD.encode("utf-8"))
    files={p.relative_to(output).as_posix():rd.sha(p.read_bytes()) for p in output.rglob("*") if p.is_file()}
    rd.put_json(output/"manifest.json",{"version":VERSION,"files":files,"summary":summary(output),
                                     "parent_manifest_sha256":rd.sha((prior/"manifest.json").read_bytes()),**POLICY})
    return verify(output)

def summary(root):
    tasks=rd.load_lines(root/"tasks.jsonl");attempts=rd.load_lines(root/"attempts.jsonl")
    events=rd.load_lines(root/"processing/events.jsonl")
    cov=rd.load_lines(root/"coverage.jsonl")
    return {"new_tasks":len(tasks),"repair_tasks":sum(t.get("minimal_reproduction",False) for t in tasks),
            "business_scenarios":sum(t.get("origin")=="synthetic_business_scenario_over_real_artifacts" for t in tasks),
            "business_source_families":2,"processing_incidents":len(rd.load_lines(root/"processing/incidents.jsonl")),
            "processing_visible_events":len(events),"processing_tool_calls":sum(e["kind"]=="tool_call" for e in events),
            "executed_control_attempts":len(attempts),"passed_controls":sum(a["reward"] for a in attempts),
            "failed_controls":sum(1-a["reward"] for a in attempts),"coverage_records":len(cov),
            "new_model_calls":0,"trained_models":0,"held_out_tasks":0,"training_records":0}

def verify_business_run(root,path):
    run=rd.load_json(path)
    scenario=rd.load_json(root/"tasks"/run["task_id"]/"environment/scenario.json")
    env=business.BusinessEnv(scenario)
    env.reset(seed=run.get("seed",0))
    for event in run["events"]:
        env.step(event["action"])
        check(env.events[-1]==event,"business_transition_or_reward_mismatch")
    check(env.outcome==run["outcome"] and env.snapshot()==run["final_state"],"business_outcome_mismatch")
    return env.outcome or {"reward":0,"passed":False,"reason":"incomplete_episode"}

def verify(root):
    root=Path(root).resolve();manifest=rd.load_json(root/"manifest.json")
    actual={p.relative_to(root).as_posix():rd.sha(p.read_bytes()) for p in root.rglob("*") if p.is_file() and p!=root/"manifest.json"}
    check(actual==manifest["files"],"bundle_file_hash_or_membership_changed")
    check(manifest["version"]==VERSION and manifest["split"]=="development","bundle_policy_changed")
    check(manifest["parent_manifest_sha256"]==rd.sha((root/"prior/manifest.json").read_bytes()),"parent_changed")
    corpus.verify_dataset(root/"prior")
    tasks=rd.load_lines(root/"tasks.jsonl");attempts=rd.load_lines(root/"attempts.jsonl")
    for t in tasks:
        check(t["split"]=="development" and not t["rights"]["training_eligible"],"unsupported_training_or_split")
        check(t==rd.load_json(root/"tasks"/t["task_id"]/"task.json"),"task_metadata_mismatch")
    specs={s["task_id"]:s for s in repair.task_specs()}
    for spec in specs.values():
        p=root/"tasks"/spec["task_id"]
        check((p/"environment/worker.py").read_text(encoding="utf-8")==spec["initial"],"initial_state_changed")
        check((p/"solution/worker.py").read_text(encoding="utf-8")==spec["reference"],"reference_changed")
        check(rd.load_json(p/"tests/cases.json")==spec["cases"],"verifier_cases_changed")
        check((p/"tests/verify.py").read_text(encoding="utf-8")==repair.VERIFIER,"verifier_code_changed")
    for a in attempts:
        check(a["actor_kind"]=="scripted_control" and a["split"]=="development","actor_or_split_promoted")
        result=rd.load_json(rd.local_file(root,a["result_path"]))
        if a["task_id"] in specs:
            expected_reward=int(a["phase"] in {"reference","reset_reference"})
            spec=specs[a["task_id"]];ph=a["phase"]
            target=root/"executions"/a["task_id"]/ph/"workspace/worker.py"
            expected_source=spec["initial"] if ph=="initial" else spec["partial"] if ph=="partial" else spec["reference"]
            check(target.read_text(encoding="utf-8")==expected_source,"control_worker_changed")
            checks=result["cases"]
            check(len(checks)==len(spec["cases"]),"missing_test_result")
            for c,known in zip(checks,spec["cases"]):
                try: observed=json.loads(c["stdout"])
                except ValueError: observed=None
                passed=not c["timeout"] and c["exit_code"]==0 and observed==known["expected"]
                check(c["case"]==known["name"] and c["passed"]==passed and c["expected"]==known["expected"],"test_result_inconsistent")
            check(result["reward"]==int(all(c["passed"] for c in checks)),"repair_reward_forged")
            check(rd.sha(target.read_bytes())==result["worker_sha256"]==a["worker_sha256"],"worker_binding_changed")
        else:
            outcome=verify_business_run(root,rd.local_file(root,a["result_path"]))
            expected_reward=int(a["phase"] in {"reference","repeat_reference"})
            check(outcome["reward"]==a["reward"],"business_attempt_reward_mismatch")
        check(a["reward"]==expected_reward and (result.get("reward",result.get("outcome",{}).get("reward"))==a["reward"]),"control_expectation_changed")
    expected_ids={s["task_id"] for s in specs.values()}
    for report,family in corpus.history.family_map(root/"prior/prior").items():
        folder=root/"prior/prior/base/assets/reports"/report/"data"
        for fault in ("clean","missing_reference","tool_retry","access_revoked","concurrent_edit"):
            expected=business.make_scenario(report,family,rd.table_rows(folder/"source_registry.csv"),rd.table_rows(folder/"claims_registry.csv"),fault)
            tid=expected["task_id"];expected_ids.add(tid)
            actual_s=rd.load_json(root/"tasks"/tid/"environment/scenario.json")
            refs=actual_s.pop("source_artifacts")
            check(expected==actual_s,"scenario_changed")
            check(all(rd.sha(rd.local_file(root,r["path"]).read_bytes())==r["sha256"] for r in refs),"scenario_source_changed")
    check({t["task_id"] for t in tasks}==expected_ids and len(tasks)==len(expected_ids),"task_membership_changed")
    expected_attempts={(s,"initial") for s in specs}|{(s,"partial") for s in specs}|{(s,"reference") for s in specs}|{(s,"reset_reference") for s in specs}
    for t in tasks:
        if t["task_id"] in specs:continue
        for mode in (["reference","empty","wrong_answer","repeat_reference"]+(["ignore_conflict"] if t["fault"]=="concurrent_edit" else [])):
            expected_attempts.add((t["task_id"],mode))
    check({(a["task_id"],a["phase"]) for a in attempts}==expected_attempts and len(attempts)==len(expected_attempts),"attempt_membership_changed")
    check(rd.load_lines(root/"coverage.jsonl")==coverage(root/"prior",tasks),"coverage_changed")
    incidents=rd.load_lines(root/"processing/incidents.jsonl")
    check(len(incidents)==len(INCIDENTS),"processing_failure_deleted")
    event_lines={e["source_line"] for e in rd.load_lines(root/"processing/events.jsonl")}
    for row,known in zip(incidents,INCIDENTS):
        check(all(row[k]==v for k,v in known.items()),"incident_changed")
        check(known["failure_line"] in event_lines,"processing_failure_event_missing")
        check(not row["hidden_reasoning_reconstructed"],"invented_reasoning")
    for tid,spec in specs.items():
        recorded=rd.load_lines(root/"executions"/tid/"events.jsonl")
        check(len(recorded)==12,"repair_trace_incomplete")
        before=spec["initial"]
        for n,phase in enumerate(("initial","partial","reference","reset_reference")):
            after=spec["initial"] if phase=="initial" else spec["partial"] if phase=="partial" else spec["reference"]
            change,call,result=recorded[n*3:n*3+3]
            check(change["before_sha256"]==rd.sha(before.encode()) and change["after_sha256"]==rd.sha(after.encode()),"patch_state_changed")
            check(result["result"]==rd.load_json(root/"executions"/tid/phase/"result.json"),"trace_result_changed")
            check(call["kind"]=="tool_call" and result["kind"]=="tool_result" and call["phase"]==phase,"trace_action_changed")
            before=after
    check(summary(root)==manifest["summary"],"summary_changed")
    return {"verified":True,**summary(root),"verified_files":len(actual)}

def export_learner(root,task_id,destination):
    root=Path(root).resolve();destination=Path(destination).resolve()
    verify(root);check(not destination.exists() and not destination.is_relative_to(root),"unsafe_export_destination")
    tasks={t["task_id"]:t for t in rd.load_lines(root/"tasks.jsonl")}
    check(task_id in tasks,"unknown_task")
    t=tasks[task_id];source=root/"tasks"/task_id
    destination.mkdir(parents=True)
    rd.put(destination/"instruction.md",(source/"instruction.md").read_bytes())
    if t.get("minimal_reproduction"):
        for name in ("worker.py","runtime.json"):
            rd.put(destination/name,(source/"environment"/name).read_bytes())
    else:
        env=business.BusinessEnv.from_file(source/"environment/scenario.json")
        obs,info=env.reset()
        rd.put_json(destination/"initial-observation.json",obs)
        rd.put_json(destination/"tool-schema.json",business.TOOLS)
    return {"exported":task_id,"files":sorted(p.name for p in destination.iterdir()),
            "grader_and_reference_included":False,"business_environment":"evaluator process only"}

def make_archive(root,destination):
    root=Path(root).resolve();destination=Path(destination).resolve();verify(root)
    check(not destination.exists(),"archive_already_exists");destination.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(destination,"x",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                info=zipfile.ZipInfo(p.relative_to(root).as_posix(),date_time=(2026,9,24,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(info,p.read_bytes())
    return {"path":str(destination),"bytes":destination.stat().st_size,"sha256":rd.sha(destination.read_bytes())}

DATA_CARD="""# Agent runtime dataset v0.4

This private development bundle contains the unchanged v0.3 archive under prior/, evidence-linked
processing incidents, executable minimal repair tasks, and offline research-handoff RL environments.
Observed logs, synthetic business context, derived reproductions, and scripted controls are distinct.
No new paid API model rollout, model training, generalization test or original corporate field execution
is claimed. Existing web/report material remains diagnostic-only and does not receive new training rights.

Run: python -B verify_dataset.py verify .
Repair task: export-learner . --task jsonl-unicode --output EXTERNAL_DIR
then edit EXTERNAL_DIR/worker.py and run tasks/jsonl-unicode/tests/verify.py EXTERNAL_DIR.
Business environment: python -B business_env.py tasks/business-customer-service-tool_retry/environment/scenario.json
The process emits an initial observation and accepts JSONL actions. reset/step is also available in Python.
A solution and behavioral verifier accompany every new task. Detailed expected answers stay evaluator-side.
Only CPython/stdlib is required. The exact exercised runtime is in environments/current.json.
The local repair runner is for trusted candidates: Python -I is NOT an OS sandbox. There was no Docker run.
The business action interface performs no host commands or external writes. Use a separate evaluator process
and expose only learner exports/tool observations to an agent.

Terminal reward is 1 only for a fully satisfied task contract; otherwise 0. Intermediate reward is 0.
Repair test fractions and business checks are evaluator diagnostics, not dense policy rewards.
State transitions, tool failures, hashes, patches, attempts, resets and verification outputs are retained.
Hashes bind files; they do not prove semantic correctness. Open-ended report quality remains unassessed.

processing/source.json freezes an exact prefix of the selected real session. It excludes hidden reasoning,
system instructions and the deleted commerce work. Diagnosis summaries are explicitly posthoc interpretations.
Original visible commands are inert text. Reproductions are small derived tasks, not exact former environments.
coverage.jsonl lists the four components and known missingness per old/new task or case/run.
Historical gaps that cannot be recovered are not replaced with synthetic history.
All related reports, variants, repairs and repeats remain development. Held-out tasks and training records: 0.
"""

def main():
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest="cmd",required=True)
    p=sub.add_parser("build");p.add_argument("--prior",required=True);p.add_argument("--session",required=True);p.add_argument("--output",required=True)
    p=sub.add_parser("verify");p.add_argument("dataset")
    p=sub.add_parser("pack");p.add_argument("dataset");p.add_argument("destination")
    p=sub.add_parser("export-learner");p.add_argument("dataset");p.add_argument("--task",required=True);p.add_argument("--output",required=True)
    a=parser.parse_args()
    if a.cmd=="build":result=build(a.prior,a.session,a.output)
    elif a.cmd=="verify":result=verify(a.dataset)
    elif a.cmd=="pack":result=make_archive(a.dataset,a.destination)
    else:result=export_learner(a.dataset,a.task,a.output)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
