"""Build and verify the evidence-receipt update without rewriting archived releases."""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import io
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
def module(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+".py"))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
b=module("business_env_v2")
rd=module("research_dataset")
VERSION="agent-runtime-v5"
POLICY={"split":"development","rights":{"allowed_uses":["diagnostic"],"distribution":"private_internal_only","training_eligible":False}}
LIVE={"tool_retry":31903,"concurrent_edit":19293}
AUDITS=("claim_evidence_after_429","backfill_note_after_later_read")
def check(ok,reason):
    if not ok:raise ValueError(reason)
def read(path):return rd.load_json(path)
def lines(path):return rd.load_lines(path)
def hash_files(root):
    return {p.relative_to(root).as_posix():rd.sha(p.read_bytes()) for p in root.rglob("*")
            if p.is_file() and p!=root/"manifest.json"}
def tokenize(text):
    for source,replacement in (
        (r"D:\Codex\agent-trajectory-data","<PROJECT>"),
        (r"D:\Codex\_home","<CODEX_HOME>"),(r"C:\Users\luosong03","<USER_PROFILE>")):
        for variant in (source.replace("\\","\\\\"),source,source.replace("\\","/")):text=text.replace(variant,replacement)
    return text
def textparts(value):
    return value if isinstance(value,str) else "\n".join(p.get("text","") for p in value if p.get("type") in {"text","input_text","output_text"})
def processing(session):
    raw=Path(session).read_bytes();source_lines=raw.split(b"\n");records=[]
    for number,line in enumerate(source_lines,1):
        if not line.strip():continue
        row=json.loads(line)
        if row.get("type")=="response_item":records.append((number,line,row))
    calls={row["payload"]["call_id"]:(n,line,row) for n,line,row in records
           if row["payload"].get("type") in {"custom_tool_call","function_call"}}
    results={row["payload"]["call_id"]:(n,line,row) for n,line,row in records
             if row["payload"].get("type") in {"custom_tool_call_output","function_call_output"}}
    start=min(n for n,line,row in calls.values() if "data/runtime-audit-20260928" in row["payload"].get("input",""))
    last=next(cid for cid,(n,line,row) in calls.items() if n>start
              and "session_id:19293" in row["payload"].get("input","")
              and "concurrent_edit-episode.json" in row["payload"].get("input",""))
    end=results[last][0];events=[];wire={}
    for number,line,row in records:
        if not start<=number<=end:continue
        q=row["payload"];typ=q.get("type");event={"event_id":"processing-"+str(number),
            "source_line":number,"source_line_sha256":rd.sha(line),"timestamp":row.get("timestamp")}
        if typ in {"custom_tool_call","function_call"}:
            arguments=q.get("input",q.get("arguments",""))
            event.update(kind="tool_call",call_id=q["call_id"],tool=q["name"],arguments=tokenize(arguments))
            for name,sid in LIVE.items():
                match=re.search(r"session_id\s*:\s*"+str(sid)+r"\s*,\s*chars\s*:\s*'((?:\\.|[^'])*)'",arguments)
                if match:
                    raw_chars=re.sub(r"\\([\\'nrt])",lambda m:{"\\":"\\","'":"'","n":"\n","r":"\r","t":"\t"}[m[1]],match[1])
                    wire.setdefault(name,[]).extend({"source_event":event["event_id"],"action":json.loads(chunk)}
                                                   for chunk in raw_chars.split("\n") if chunk.strip())
        elif typ in {"custom_tool_call_output","function_call_output"}:
            event.update(kind="tool_result",call_id=q["call_id"],output=tokenize(textparts(q["output"])))
        elif (typ=="message" and q.get("role")=="assistant"
              and (q.get("phase") or q.get("channel"))=="commentary"):
            event.update(kind="assistant_message",text=tokenize(textparts(q.get("content",[]))))
        else:continue
        events.append(event)
    prefix=b"\n".join(source_lines[:end])+b"\n"
    check({e["call_id"] for e in events if e["kind"]=="tool_call"}==
          {e["call_id"] for e in events if e["kind"]=="tool_result"},"processing_unpaired_calls")
    return events,wire,{"source_session_id":json.loads(source_lines[0])["payload"]["id"],
        "selection_start_line":start,"frozen_prefix_end_line":end,"prefix_sha256":rd.sha(prefix),
        "prefix_bytes":len(prefix),"hidden_reasoning_included":False,"raw_source_included":False,
        "body_transform":"Known local roots tokenized; visible tool arguments and returns retained."}

def reference(task,mode):
    env=b.BusinessEnv(task);b.reference_policy(env,"reference" if mode=="repeat_reference" else mode)
    run=b.record(env,"scripted_control");run["policy"]=mode;return run

def recovery(task):
    env=b.BusinessEnv(task)
    def act(tool,**args):return env.step({"tool":tool,"args":args})[0]
    for key in ("policy","handoff","claims","sources"):act("read",document_id=key)
    early=act("write_note",text="Premature note control",evidence_ids=sorted(b.REQUIRED))
    check(early["status"]==422,"premature_note_not_rejected")
    act("read",document_id="sources");act("read",document_id="sources")
    note=act("write_note",text="Corrected after successful reads",evidence_ids=sorted(b.REQUIRED))
    answer=env.expected() # Explicit oracle-assisted regression control, not model performance.
    updated=act("update_ticket",if_version=1,status=answer["status"],note_id=note["note_id"])
    answer.update(evidence_ids=sorted(b.REQUIRED),ticket_version=updated["ticket"]["version"],scope="registry_integrity_only")
    act("submit",**answer)
    return b.record(env,"scripted_recovery_control")

def build(prior,audit,live,session,output):
    prior=Path(prior).resolve();audit=Path(audit).resolve();live=Path(live).resolve();output=Path(output).resolve()
    check(not output.exists(),"output_exists")
    pm=read(prior/"manifest.json")
    check(hash_files(prior)==pm["files"],"prior_content_changed")
    old_runtime=(prior/"business_env.py").read_bytes()
    check(old_runtime==(HERE/"business_env.py").read_bytes(),"v1_runtime_modified")
    events,wire,source=processing(session)
    output.mkdir(parents=True)
    for name in ("business_env.py","business_env_v2.py","research_dataset.py"):
        rd.put(output/name,(HERE/name).read_bytes())
    rd.put(output/"verify_dataset.py",Path(__file__).read_bytes())
    rd.put(output/"LICENSE",(prior/"LICENSE").read_bytes())
    rd.put(output/"sources/parent-manifest.json",(prior/"manifest.json").read_bytes())
    rd.put_json(output/"sources/parent.json",{"release":"dataset-v0.4",
        "release_url":"https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.4",
        "manifest_sha256":rd.sha((prior/"manifest.json").read_bytes()),
        "archive_sha256":"f665f77514d3ca7502b15868d943dd6eb10f3fc55a43311af26629e071f3b2e2",
        "delivery":"Standalone environment update; full historical corpus remains in the unchanged v0.4 asset."})
    rd.put_lines(output/"processing/events.jsonl",events);rd.put_json(output/"processing/source.json",source)
    parent_tasks=[t for t in lines(prior/"tasks.jsonl") if t.get("origin")=="synthetic_business_scenario_over_real_artifacts"]
    tasks=[];runs=[];scenarios={}
    def keep(run,label,expected,origin,**extra):
        tid=run["task_id"];path="episodes/"+tid+"/"+label+".json"
        grade=b.verify_record(scenarios[tid],run)
        check(grade["reward"]==expected,"control_outcome_mismatch:"+label)
        rd.put_json(output/path,run)
        runs.append({"episode_id":tid+"-"+label,"task_id":tid,"path":path,"reward":grade["reward"],
                     "complete":run["complete"],"actor_kind":run["actor_kind"],"execution_origin":origin,
                     "label":label,"model_identity_verified":False,**POLICY,**extra})
    for parent in parent_tasks:
        tid=parent["task_id"];relative="tasks/"+tid+"/environment/scenario.json"
        original=read(prior/relative)
        rd.put(output/"sources/tasks"/(tid+".json"),(prior/relative).read_bytes())
        scenario=b.revise_scenario(original);sid=scenario["task_id"];scenarios[sid]=scenario
        root=output/"tasks"/sid
        rd.put_json(root/"environment/scenario.json",scenario)
        rd.put(root/"instruction.md",(scenario["instruction"]+"\n").encode())
        rd.put_json(root/"rubric.json",{"terminal_reward":"all checks must pass","intermediate_reward":0,
            "evidence":"Successful current reads, or an actual denial/missing receipt for a blocked table.",
            "note":"Receipts are frozen at note creation; later reads cannot backfill old notes.",
            "scope":"registry_integrity_only; no prose-quality or external-fact certification"})
        rd.put(root/"solution/reference.py",SOLUTION.encode())
        rd.put(root/"tests/verify.py",VERIFIER.encode())
        meta={"task_id":sid,"parent_task_id":tid,"family_id":scenario["family_id"],"fault":scenario["fault"],
              "parent_environment_path":"sources/tasks/"+tid+".json","parent_file_path":relative,
              "parent_file_sha256":pm["files"][relative],"environment":"tasks/"+sid+"/environment/scenario.json",
              "instruction":"tasks/"+sid+"/instruction.md","grader":"tasks/"+sid+"/tests/verify.py",
              "solution":"tasks/"+sid+"/solution/reference.py","origin":"revision_of_existing_development_scenario",
              "new_independent_task_claim":False,**POLICY}
        rd.put_json(root/"task.json",meta);tasks.append(meta)
        for mode in ["reference","empty","wrong_answer","repeat_reference"]+(["ignore_conflict"] if parent["fault"]=="concurrent_edit" else []):
            keep(reference(scenario,mode),mode,int(mode in {"reference","repeat_reference"}),"scripted_control")
        if parent["fault"]=="tool_retry":
            keep(recovery(scenario),"repair_after_failed_note",1,"scripted_recovery_control")
    tid="business-customer-service-tool_retry-v2";scenario=scenarios[tid]
    for case in AUDITS:
        original=read(audit/(case+".json"))
        rd.put(output/"sources/audit"/(case+".json"),(audit/(case+".json")).read_bytes())
        env=b.BusinessEnv(scenario)
        for event in original["events"]:env.step(event["action"])
        run=b.record(env,"oracle_assisted_adversarial_control")
        keep(run,case,0,"counterexample_replay")
    rd.put(output/"sources/audit/reference-cli.json",(audit/"reference-cli.json").read_bytes())
    rd.put(output/"sources/audit/reference-cli-verification.json",(audit/"reference-cli-verification.json").read_bytes())
    for name,raw in (("malformed_budget",("{bad\n[]\nnull\n"*12)),("early_eof",'{"tool":"read_ticket"}\n')):
        env=b.BusinessEnv(scenario)
        run=b.serve(env,io.StringIO(raw),io.StringIO());run["actor_kind"]="scripted_protocol_control"
        keep(run,name,0,"scripted_protocol_control")
    for name in LIVE:
        task_id="business-customer-service-"+name+"-v2"
        check(read(live/(name+"-scenario.json"))==scenarios[task_id],"live_scenario_not_frozen")
        run=read(live/(name+"-episode.json"))
        check([row["action"] for row in wire[name]]==[e["action"] for e in run["events"]],"live_actions_not_source_bound")
        rd.put_json(output/"processing"/(name+"-action-bindings.json"),wire[name])
        keep(run,"current_assistant",1,"current_authoring_assistant",
             evaluation_mode="seen_development_integration_run",independent_model_evaluation=False,
             source_action_binding="processing/"+name+"-action-bindings.json")
    rd.put_lines(output/"tasks.jsonl",tasks);rd.put_lines(output/"episodes.jsonl",runs)
    rd.put_json(output/"audit-findings.json",[
        {"id":"429-as-evidence","before":"reward 1 despite no successful source read","after":"reward 0; note rejected with 422"},
        {"id":"retroactive-note","before":"later read made an earlier note appear supported","after":"failed note remains absent; new note required"},
        {"id":"reference-cli-contract","before":"run lacked task_id and verifier raised KeyError","after":"common run envelope verifies directly"},
        {"id":"protocol-failures","before":"malformed messages were not environment steps or persisted","after":"parse failures retained and count toward the step limit"}
    ])
    rd.put(output/"DATA_CARD.md",CARD.encode())
    rd.put_json(output/"manifest.json",{"version":VERSION,"files":hash_files(output),"summary":summary(output),**POLICY})
    return verify(output)

def summary(root):
    runs=lines(root/"episodes.jsonl");controls=[r for r in runs if r["execution_origin"]!="current_authoring_assistant"]
    return {"revised_scenarios":len(lines(root/"tasks.jsonl")),"new_independent_task_families":0,
        "scripted_control_episodes":len(controls),"controls_passed":sum(r["reward"] for r in controls),
        "controls_not_passed":sum(1-r["reward"] for r in controls),
        "controls_incomplete":sum(not r["complete"] for r in controls),
        "current_assistant_episodes":len(runs)-len(controls),"independent_model_evaluations":0,
        "held_out_tasks":0,"additional_model_processes":0,"training_records":0,
        "processing_visible_events":len(lines(root/"processing/events.jsonl"))}

def verify(root):
    root=Path(root).resolve();m=read(root/"manifest.json")
    check(m["version"]==VERSION,"version_changed")
    for key,value in POLICY.items():check(m.get(key)==value,"manifest_policy_changed")
    check(hash_files(root)==m["files"],"file_hash_or_membership_changed")
    parent=read(root/"sources/parent.json");pm=read(root/"sources/parent-manifest.json")
    check(rd.sha((root/"sources/parent-manifest.json").read_bytes())==parent["manifest_sha256"],"parent_manifest_changed")
    check(rd.sha((root/"business_env.py").read_bytes())==pm["files"]["business_env.py"],"frozen_v1_changed")
    tasks=lines(root/"tasks.jsonl");runs=lines(root/"episodes.jsonl");scenarios={}
    check(len(tasks)==10 and len({t["task_id"] for t in tasks})==10,"task_membership_changed")
    for t in tasks:
        for key,value in POLICY.items():check(t.get(key)==value,"task_policy_changed")
        check(t==read(root/"tasks"/t["task_id"]/"task.json"),"task_metadata_changed")
        old=rd.local_file(root,t["parent_environment_path"])
        check(rd.sha(old.read_bytes())==t["parent_file_sha256"]==pm["files"][t["parent_file_path"]],"parent_task_changed")
        scenario=read(rd.local_file(root,t["environment"]))
        check(scenario==b.revise_scenario(read(old)),"revised_scenario_changed")
        scenarios[t["task_id"]]=scenario
        check((root/t["grader"]).read_text(encoding="utf-8")==VERIFIER,"grader_changed")
        check((root/t["solution"]).read_text(encoding="utf-8")==SOLUTION,"solution_changed")
    for row in runs:
        for key,value in POLICY.items():check(row.get(key)==value,"episode_policy_changed")
        run=read(rd.local_file(root,row["path"]));result=b.verify_record(scenarios[row["task_id"]],run)
        check(row["reward"]==result["reward"] and row["actor_kind"]==run["actor_kind"]
              and row["complete"]==run["complete"],"episode_label_changed")
        check(row["model_identity_verified"] is False and run.get("model_identity")=="not_supplied"
              and run.get("tokens") is None and run.get("cost") is None,"unsupported_model_identity")
        label=row["label"]
        origin,actor=("scripted_control","scripted_control")
        if label=="repair_after_failed_note":origin=actor="scripted_recovery_control"
        elif label in AUDITS:origin,actor="counterexample_replay","oracle_assisted_adversarial_control"
        elif label in {"malformed_budget","early_eof"}:origin=actor="scripted_protocol_control"
        elif label=="current_assistant":origin,actor="current_authoring_assistant","external_client"
        check(row["execution_origin"]==origin and row["actor_kind"]==actor,"episode_origin_changed")
        expected_reward=int(label in {"reference","repeat_reference","repair_after_failed_note","current_assistant"})
        check(row["reward"]==expected_reward,"expected_control_reward_changed")
        check(row["complete"] is (label!="early_eof"),"completion_label_changed")
        if actor in {"external_client","scripted_protocol_control"}:
            check(bool(run.get("transport")),"wire_observations_missing")
        if origin=="current_authoring_assistant":
            check(row["evaluation_mode"]=="seen_development_integration_run"
                  and row["independent_model_evaluation"] is False,"seen_run_promoted_to_evaluation")
            binding=read(rd.local_file(root,row["source_action_binding"]))
            check([x["action"] for x in binding]==[e["action"] for e in run["events"]],"live_binding_changed")
    expected=set()
    for t in tasks:
        modes=["reference","empty","wrong_answer","repeat_reference"]
        if t["fault"]=="concurrent_edit":modes.append("ignore_conflict")
        if t["fault"]=="tool_retry":modes.append("repair_after_failed_note")
        expected|={(t["task_id"],mode) for mode in modes}
    tid="business-customer-service-tool_retry-v2"
    expected|={(tid,x) for x in (*AUDITS,"malformed_budget","early_eof","current_assistant")}
    expected.add(("business-customer-service-concurrent_edit-v2","current_assistant"))
    check({(r["task_id"],r["label"]) for r in runs}==expected and len(runs)==len(expected),"episode_membership_changed")
    for case in AUDITS:
        original=read(root/"sources/audit"/(case+".json"))
        check(original["runtime_sha256"]==rd.sha((root/"business_env.py").read_bytes()),"audit_runtime_binding_changed")
        oldfile=root/"sources/tasks/business-customer-service-tool_retry.json"
        check(original["scenario_sha256"]==rd.sha(oldfile.read_bytes()),"audit_scenario_binding_changed")
        old=b.v1.BusinessEnv(read(oldfile));new=b.BusinessEnv(scenarios[tid])
        for event in original["events"]:
            old.step(event["action"]);check(old.events[-1]==event,"original_counterexample_changed")
            new.step(event["action"])
        check(old.outcome==original["outcome"] and old.outcome["reward"]==1 and original["expected_reward"]==0,
              "original_false_positive_erased")
        check(new.outcome["reward"]==0,"loophole_not_fixed")
    cli=read(root/"sources/audit/reference-cli.json")
    failed_cli=read(root/"sources/audit/reference-cli-verification.json")
    check("task_id" not in cli and failed_cli["producer_exit"]==0
          and failed_cli["verifier_exit"]==1 and "task_id" in failed_cli["stderr"],
          "original_cli_failure_erased")
    events=lines(root/"processing/events.jsonl");by_id={e["event_id"]:e for e in events}
    for name,sid in LIVE.items():
        binding=read(root/"processing"/(name+"-action-bindings.json"))
        for item in binding:
            check(item["source_event"] in by_id and by_id[item["source_event"]]["kind"]=="tool_call","live_source_missing")
        reconstructed=[]
        for e in events:
            if e["kind"]!="tool_call":continue
            match=re.search(r"session_id\s*:\s*"+str(sid)+r"\s*,\s*chars\s*:\s*'((?:\\.|[^'])*)'",e["arguments"])
            if match:
                raw=re.sub(r"\\([\\'nrt])",lambda m:{"\\":"\\","'":"'","n":"\n","r":"\r","t":"\t"}[m[1]],match[1])
                reconstructed.extend({"source_event":e["event_id"],"action":json.loads(x)} for x in raw.split("\n") if x.strip())
        check(reconstructed==binding,"native_action_binding_changed")
    check({e["call_id"] for e in events if e["kind"]=="tool_call"}==
          {e["call_id"] for e in events if e["kind"]=="tool_result"},"processing_pair_changed")
    check(summary(root)==m["summary"],"summary_changed")
    return {"verified":True,**summary(root),"verified_files":len(m["files"])}

def export_learner(root,task_id,output):
    root=Path(root).resolve();output=Path(output).resolve();verify(root)
    tasks={t["task_id"]:t for t in lines(root/"tasks.jsonl")}
    check(task_id in tasks,"unknown_task");check(not output.exists() and not output.is_relative_to(root),"export_destination_exists_or_inside_bundle")
    t=tasks[task_id];env=b.BusinessEnv(read(root/t["environment"]))
    obs,info=env.reset()
    rd.put(output/"instruction.md",(root/t["instruction"]).read_bytes())
    rd.put_json(output/"initial-observation.json",obs)
    rd.put_json(output/"tool-schema.json",b.v1.TOOLS)
    return {"exported":task_id,"files":sorted(p.name for p in output.iterdir()),"reference_or_grader_included":False}

def pack(root,output):
    root=Path(root).resolve();output=Path(output).resolve();verify(root);check(not output.exists(),"archive_exists")
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,"x",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                info=zipfile.ZipInfo(p.relative_to(root).as_posix(),date_time=(2026,9,28,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(info,p.read_bytes())
    return {"path":str(output),"bytes":output.stat().st_size,"sha256":rd.sha(output.read_bytes())}

SOLUTION='''import argparse,json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root))
from business_env_v2 import BusinessEnv,reference_policy,record,stable
p=argparse.ArgumentParser();p.add_argument("--output");a=p.parse_args()
if a.output and Path(a.output).exists():raise ValueError("output_exists")
e=BusinessEnv.from_file(Path(__file__).resolve().parents[1]/"environment/scenario.json")
reference_policy(e);run=record(e,"scripted_control");body=stable(run)+"\\n"
if a.output:
    with open(a.output,"x",encoding="utf-8") as stream:stream.write(body)
else:print(body)
'''
VERIFIER='''import json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root))
from business_env_v2 import verify_record,stable
scenario=json.loads((Path(__file__).resolve().parents[1]/"environment/scenario.json").read_bytes())
result=verify_record(scenario,json.loads(Path(sys.argv[1]).read_bytes()))
print(stable(result))
raise SystemExit(0 if result["reward"] else 1)
'''
CARD="""# Agent runtime evidence-receipt update v0.5

This standalone update revises the ten existing development business scenarios. It includes task
instructions, frozen environments, private graders, reference solutions, executed controls and
two actual interactive runs by the current authoring assistant.
The unchanged full historical corpus and seven coding repair tasks remain in the private v0.4 asset.
This is not a new independent benchmark or a model training result.

A successful read requires a 200 receipt matching the current document. A 429 is an observation of
failure, not evidence content. Denial/missing receipts can support blocked decisions. Notes retain
the receipts available when written; later reads do not retroactively validate a premature note.
Old notes and ticket revisions persist. Invalid JSON and forbidden resets count toward the budget.

The old false-positive episodes are retained and replayed with the original runtime. The same actions
fail in v2. Counterexamples use an oracle-assisted scripted adversary and are not model trajectories.
The two current-assistant runs are already-seen development tasks: the author had seen the environment,
grader and reference implementation. Their raw JSONL input, results and native tool-call bindings
are retained. External provider/model identity and token/cost figures remain unverified; no independent
model evaluation or generalization result is claimed. No additional model process was launched.

Run python -B verify_dataset.py verify .
Run python -X utf8 -B business_env_v2.py tasks/TASK/environment/scenario.json --output ../episode.json
Reference: add --policy reference. Grade: add --verify ../episode.json.
Give an agent only export-learner output and tool observations, not the entire evaluator archive.
All material remains private diagnostic development data; training eligibility is false.
"""
def main():
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest="cmd",required=True)
    p=sub.add_parser("build")
    for arg in ("prior","audit","live","session","output"):p.add_argument("--"+arg,required=True)
    p=sub.add_parser("verify");p.add_argument("dataset")
    p=sub.add_parser("pack");p.add_argument("dataset");p.add_argument("output")
    p=sub.add_parser("export-learner");p.add_argument("dataset");p.add_argument("--task",required=True);p.add_argument("--output",required=True)
    a=parser.parse_args()
    if a.cmd=="build":result=build(a.prior,a.audit,a.live,a.session,a.output)
    elif a.cmd=="verify":result=verify(a.dataset)
    elif a.cmd=="pack":result=pack(a.dataset,a.output)
    else:result=export_learner(a.dataset,a.task,a.output)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
