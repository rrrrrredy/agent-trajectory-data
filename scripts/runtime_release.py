"""Assemble and independently verify the versioned incremental data release."""
from __future__ import annotations
import argparse,json,shutil,zipfile
from collections import Counter
from pathlib import Path
import runtime_batch as b
import runtime_collect as c
import research_env_v3 as e

def all_hashes(root):
    root=Path(root)
    return {p.relative_to(root).as_posix():b.sha(p.read_bytes()) for p in sorted(root.rglob("*")) if p.is_file() and p!=root/"manifest.json" and "__pycache__" not in p.parts}

def task_entrypoints(root):
    for task in b.lines(Path(root)/"batch/tasks.jsonl"):
        tid=task["task_id"];scenario=b.read(Path(root)/"batch"/task["scenario"]);module=b.environment_module(scenario).__name__
        base="from pathlib import Path\nimport json,sys\nROOT=Path(__file__).resolve().parents[3]\nsys.path.insert(0,str(ROOT))\nimport research_env_v3 as e\nimport runtime_batch as b\nSCENARIO=b.read(ROOT/"+repr("batch/"+task["scenario"])+")\n"
        verify=base+"run=b.read(sys.argv[1])\ngrade=e.verify_record(SCENARIO,run)\nprint(json.dumps(grade,indent=2))\nsys.exit(0 if grade['reward'] else 1)\n"
        solution=base+"run=b.run_reference(SCENARIO)\nb.put(sys.argv[1],run)\nprint(json.dumps(e.verify_record(SCENARIO,run),indent=2))\n"
        verify=verify.replace("import research_env_v3 as e","import "+module+" as e");solution=solution.replace("import research_env_v3 as e","import "+module+" as e")
        yield "task-entrypoints/"+tid+"/tests/verify.py",verify.encode()
        yield "task-entrypoints/"+tid+"/solution/reference.py",solution.encode()
        yield "task-entrypoints/"+tid+"/environment.json",b.encoded({"runtime":"CPython >= 3.10","dependencies":[],"environment_version":scenario["version"],
              "api":module+".ResearchEnv.reset / step","stdio":module+".py","scenario":"batch/"+task["scenario"],
              "network_required":False,"max_steps":b.read(Path(root)/"batch"/task["scenario"])["max_steps"]})

def metrics(root):
    root=Path(root);batch=b.verify(root/"batch");models=c.verify(root/"batch",root/"model")
    tasks=b.lines(root/"batch/tasks.jsonl");episodes=b.lines(root/"model/episodes.jsonl")
    families={}
    for task in tasks:families.setdefault(task["family_id"],{})[task["variant"]]=task
    contrasts=0
    for family,variants in families.items():
        if "counterfactual" not in variants:continue
        e.check("clean" in variants,"counterfactual_without_baseline")
        original=b.read(root/"batch"/variants["clean"]["scenario"]);changed=b.read(root/"batch"/variants["counterfactual"]["scenario"])
        e.check(not e.equal(b.expected_outcome(original),b.expected_outcome(changed)),"ineffective_counterfactual:"+family)
        contrasts+=1
    status=Counter();usage=Counter();stops=Counter()
    for row in episodes:
        run=b.read(root/"model"/row["path"])
        status.update(str(event["observation"]["status"]) for event in run["events"])
        stops.update([run["stop_reason"] or "submitted"])
        for ref in run["capture_refs"]:
            cap=b.read(root/"model"/ref["path"]/"capture.json")
            usage.update({key:value for key,value in (cap["usage"] or {}).items() if type(value) is int})
    repair=b.read(root/"batch/config.json")["version"]=="runtime-repair-batch-1"
    workspace=b.read(root/"batch/config.json")["version"]=="runtime-workspace-batch-1"
    prior=b.read(root/"model/started.json")["prior_ledger_entries"];final=b.read(root/"model/ledger-final.json")["entries"]
    return {"curriculum":batch,"model_collection":models,"mechanisms":sorted({t["mechanism"] for t in tasks}),
            "effective_counterfactual_pairs":contrasts,"source_families_by_split":{split:sorted({t["family_id"] for t in tasks if t["split"]==split}) for split in (("train","test","development") if repair or workspace else ("train","test"))},
            "observed_tool_status_counts":dict(status),"stop_reason_counts":dict(stops),"usage_tokens":dict(usage),
            "previous_ledger_reservations":len(prior),"final_ledger_reservations":len(final),"provider_cost":None,
            "evaluation_boundary":("Fresh model attempts on two archived report sources and four new synthetic sources. Historical source assertions are not independently reverified. Shared runtime template; source-based splits; no broad blind-generalization claim." if workspace else "Fresh model attempts on minimal reproductions of observed incidents, with synthetic layout/concurrency variants. One inherited development source group; no blind-generalization or toolkit-effect claim." if repair else "Fresh model contexts on authored synthetic development tasks. Source families are disjoint; mechanisms are shared. No broad generalization or toolkit-effect estimate."),
            "grading_boundary":("Recomputed bounded results, current citations at write time, two consistent deliverables, protected content, final reads and validation, and duplicate effects. The bounded structured report is graded; freeform research quality and external truth are not." if workspace else "Baseline failure, current code, public and private behavioral tests, evidence timing and terminal state. Restricted pure-function Python; not general shell or repository execution." if repair else "Exact structured facts, arithmetic, citations and observed state transitions; no freeform research truth judgment.")}

def verify(root):
    root=Path(root).resolve();manifest=b.read(root/"manifest.json")
    e.check(manifest["files"]==all_hashes(root),"release_files_changed")
    for name,expected in task_entrypoints(root):e.check(b.local(root,name).read_bytes()==expected,"task_entrypoint_changed")
    result=metrics(root);e.check(e.equal(result,b.read(root/"metrics.json")),"release_metrics_changed")
    prior=b.read(root/"lineage.json")["prior_release"]
    e.check(prior==b.read(root/"batch/config.json")["prior_release"],"prior_lineage_changed")
    events=b.lines(root/"processing/events.jsonl");calls={r["call_id"] for r in events if r["kind"]=="tool_call"};results={r["call_id"] for r in events if r["kind"]=="tool_result"}
    e.check(calls==results,"processing_calls_unpaired")
    e.check(all(r["kind"] in {"tool_call","tool_result","assistant_message","user_message"} for r in events),"unexpected_processing_kind")
    by_id={r["event_id"]:r for r in events};source=b.read(root/"processing/source.json")
    e.check(source["projection_sha256"]==b.sha((root/"processing/events.jsonl").read_bytes()) and source["events"]==len(events),"processing_projection_changed")
    for incident in b.read(root/"processing/incidents.json"):
        for relation in ("failure_events","diagnosis_events","patch_events","verification_events"):
            e.check(incident[relation] and all(ref in by_id for ref in incident[relation]),"incident_evidence_missing")
    extra={}
    if b.read(root/"batch/config.json")["version"] in {"runtime-repair-batch-1","runtime-workspace-batch-1"}:
        import source_catalog,failure_exports
        extra={"source_catalog":source_catalog.verify(root/"catalog"),"failure_exports":failure_exports.verify(root/"failures")}
    if b.read(root/"batch/config.json")["version"]=="runtime-workspace-batch-1":
        import workspace_exports
        extra["workspace_exports"]=workspace_exports.verify(root/"exports",root/"batch",root/"model")
    return {"passed":True,"files":len(manifest["files"]),"processing_events":len(events),**result,**extra}

def build(batch,model,processing,checks,output,catalog=None,failures=None,exports=None):
    root=Path(output).resolve();e.check(not root.exists(),"output_exists")
    b.verify(batch);c.verify(batch,model)
    root.mkdir();shutil.copytree(batch,root/"batch");shutil.copytree(model,root/"model");shutil.copytree(processing,root/"processing");shutil.copytree(checks,root/"checks")
    repair=b.read(root/"batch/config.json")["version"]=="runtime-repair-batch-1"
    workspace=b.read(root/"batch/config.json")["version"]=="runtime-workspace-batch-1"
    extra=[]
    if repair or workspace:
        e.check(catalog is not None and failures is not None,"runtime_release_addons_required")
        shutil.copytree(catalog,root/"catalog");shutil.copytree(failures,root/"failures");extra=["source_catalog.py","failure_exports.py"]
    if workspace:
        e.check(exports is not None,"workspace_exports_required");shutil.copytree(exports,root/"exports");extra.append("workspace_exports.py")
    for name in b.runtime_files(b.read(root/"batch/config.json"))+["runtime_collect.py","runtime_release.py"]+extra:
        b.write(root/name,(Path(__file__).parent/name).read_bytes())
    for name,data in task_entrypoints(root):b.write(root/name,data)
    config=b.read(root/"batch/config.json")
    b.put(root/"lineage.json",{"dataset_version":config["dataset_version"],"incremental":True,"prior_release":config["prior_release"],"toolkit_commit":config["toolkit_commit"],
        "prior_artifacts_modified":False,"source_and_grader_identity":"batch/tasks.jsonl and per-task scenario; model/input-freeze.json",
        "rights":("Archived reports retain diagnostic-only development restrictions. New authored synthetic train families can supply eligible demonstrations and RL transitions. Synthetic development and test trajectories remain excluded from training." if workspace else "Inherited real-incident data stays development-only. Earlier eligible train-source recovery pairs are exported separately; source restrictions never change." if repair else "Synthetic train families may enter training; test families and processing diagnostics remain excluded.")})
    b.put(root/"metrics.json",metrics(root))
    version=config["dataset_version"];environment_name=b.environment_module(b.read(root/"batch"/b.lines(root/"batch/tasks.jsonl")[0]["scenario"])).__name__
    material_note=("This increment derives four diagnostic tasks from two retained reports and adds eight tasks from four authored synthetic families. Both report.md and analysis.json are saved for every actual episode. exports/ provides public-observation RL transitions and fixed evaluation selection; catalog/ preserves cross-version lineage, and failures/ retains recovery evidence. Original reports are immutable and missing historical steps are never reconstructed as observed." if workspace else "This increment reconstructs three retained real failure chains into bounded pure-function repair tasks. Original evidence stays evaluator-side; layout and conflict variants are synthetic. New trajectories inherit development-only rights. catalog/ links prior versions; failures/ separates failure causes and observed recovery, with eligible earlier train-source pairs under failures/training/." if repair else "Earlier real report material remains in its original private releases. This increment adds authored synthetic material, not new company records.")
    b.write(root/"README.md",(f"# Agent Runtime Dataset v{version}\n\nIncremental private release. Verify with Python 3.10+:\n\n    python -B runtime_release.py verify .\n\n"
       "Each batch/tasks/<id>/ contains the scenario, reference trajectory and negative controls. Evaluator-only files must stay outside policy context.\n\n"
       f"Start a fresh policy session with `python -B {environment_name}.py batch/tasks/<id>/scenario.json --output ../episode.json`. Send one {{tool,args}} JSON action per line. The host exposes reset/step observations, reward, terminated and truncated.\n\n"
       f"The episode output is a complete observable trajectory. To grade it independently: import {environment_name}, load the task scenario and episode JSON, and call verify_record(scenario, episode).\n\n"
       "Actual model requests, visible replies, actions, tool failures and checkpoints are under model/. Successful eligible model trajectories are under model/training/. Derived recovery exports, when present, are under failures/training/. Scripted references are separately identified in batch/training/.\n\n"
       f"The prior release is retained by tag and SHA-256 in lineage.json. {material_note}\n\n"
       "See metrics.json and processing/ for quality boundaries and the actual diagnosis-to-verification evidence. Archived commands are inert evidence and must not be executed.\n").encode())
    b.put(root/"manifest.json",{"version":"agent-runtime-v"+config["dataset_version"],"files":all_hashes(root)})
    return verify(root)

def pack(root,archive):
    root=Path(root).resolve();verify(root);archive=Path(archive);e.check(not archive.exists(),"archive_exists")
    archive.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED) as z:
        for path in sorted(root.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                info=zipfile.ZipInfo(path.relative_to(root).as_posix(),date_time=(2026,9,28,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,path.read_bytes())
    return {"sha256":b.sha(archive.read_bytes()),"bytes":archive.stat().st_size}

def main():
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("build")
    for name in ("batch","model","processing","checks","output"):p.add_argument(name)
    p.add_argument("--catalog");p.add_argument("--failures");p.add_argument("--exports")
    p=sub.add_parser("verify");p.add_argument("root")
    p=sub.add_parser("pack");p.add_argument("root");p.add_argument("archive")
    args=parser.parse_args()
    result=build(args.batch,args.model,args.processing,args.checks,args.output,args.catalog,args.failures,args.exports) if args.command=="build" else pack(args.root,args.archive) if args.command=="pack" else verify(args.root)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
