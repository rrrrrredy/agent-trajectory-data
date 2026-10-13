"""Configuration-driven incremental runtime batches; frozen inputs, controls and exports."""
from __future__ import annotations
import argparse, copy, hashlib, json, re, sys, zipfile
from pathlib import Path
import research_env_v3 as e

HELP = {
 "search": {"args":{"query":"literal substring; empty string lists documents"}},
 "read": {"args":{"document_id":"one of the listed document IDs"},"rule":"Read actual documents; retry sources 429 at most twice (3 attempts total); 403 is permanent."},
 "read_ticket": {"args":{},"rule":"Read again after a 409 conflict; use its new version."},
 "revise_claim": {"args":{"if_version":"integer claims version","claim_id":"C1","value":"integer","unit":"string"},"rule":"Only review_revision may edit claims; reread claims after a successful revision."},
 "write_note": {"args":{"report":"structured object defined in policy"},"rule":"Host renders the final text. Optional text must exactly equal that rendering; no freeform assertions."},
 "update_ticket": {"args":{"if_version":"integer ticket version","status":"report status","note_id":"returned note ID"}},
 "submit": {"args":{"note_id":"returned note ID","ticket_version":"integer latest ticket version"},"rule":"Required terminal action after successful update_ticket."}}

POLICY = {
 "purpose":"Resolve only supplied synthetic records. Do not assert external factual verification.",
 "report_contract":{"status":"ready | needs_revision | blocked","scope":"mechanism scope given below",
                    "result":"mechanism result or null if blocked","limitations":["synthetic_material","no_external_verification","as_of_snapshot"],
                    "citations":[{"document_id":"every listed document exactly once","version":"version read, null for denied sources","status":"200 or 403","row_ids":"selected row IDs"}]},
 "evidence_update":{"scope":"snapshot_evidence_only","rule":"Select the latest effective_at on or before as_of; break ties by revision. Compare C1 value and unit with that record. Exclude future records.",
                    "result_fields":["metric","as_of","value","unit","claim_supported"]},
 "numeric_consistency":{"scope":"period_metric_only","rule":"Sum records for C1 metric and period; thousand_units = 1000 units. Exclude other periods and metrics; compare the normalized total with C1.",
                        "result_fields":["metric","period","value","unit","claim_supported"]},
 "review_revision":{"scope":"review_findings_only","rule":"Resolve source-supported review findings by revising C1; reject findings that contradict the source. Reread and verify the edited claim.",
                    "result_fields":["resolved_findings","rejected_findings","remaining_findings"]},
 "status_rule":"For evidence/numeric: ready iff claim_supported, otherwise needs_revision. For corrected review: ready. If sources return 403: blocked with result null and add source_access_denied to limitations; do not edit claims.",
 "evidence_rule":"Read every listed document before creating the note. Cite only selected source rows and all claim/review rows; policy/handoff have empty row_ids. Cite the actual 403 for denied sources with empty row_ids. Citations must use current versions and receipts available when note was created.",
 "completion":"Create the structured note; update the ticket to the same status and note; submit the note with the latest ticket version.",
 "tool_failures":"At most 3 source reads including 429 responses. On ticket 409 read current ticket and retry. Other failures remain in the trajectory."}

def read(path):return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def encoded(value):return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n").encode()
def sha(data):return hashlib.sha256(data).hexdigest()
def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():e.check(path.read_bytes()==data,"immutable_file_conflict:"+path.name)
    else:path.write_bytes(data)
def put(path,value):write(path,encoded(value))
def lines(path):return [json.loads(x) for x in Path(path).read_bytes().split(b"\n") if x.strip()]
def put_lines(path,rows):write(path,("".join(e.canonical(r)+"\n" for r in rows)).encode())
def hashes(root):return {p.relative_to(root).as_posix():sha(p.read_bytes()) for p in sorted(Path(root).rglob("*")) if p.is_file() and p.name!="manifest.json" and "__pycache__" not in p.parts}
def local(root,name):
    e.check(isinstance(name,str) and bool(name) and "\\" not in name,"invalid_path")
    root=Path(root).resolve();path=root/name
    e.check(not Path(name).is_absolute() and ".." not in Path(name).parts and path.resolve().is_relative_to(root) and not path.is_symlink(),"unsafe_path")
    return path

def environment_module(scenario):
    if scenario["version"]==e.VERSION:return e
    if scenario["version"]=="research-runtime-4":
        import research_env_v4
        return research_env_v4
    if scenario["version"]=="research-repair-2":
        import repair_probe_env
        return repair_probe_env
    if scenario["version"]=="research-repair-1":
        import repair_env
        return repair_env
    if scenario["version"]=="research-workspace-1":
        import workspace_env
        return workspace_env
    raise ValueError("unsupported_environment_version")

def new_env(scenario):return environment_module(scenario).ResearchEnv(scenario)
def record_env(env,actor_kind):return environment_module(env.scenario).record(env,actor_kind)
def verify_episode(scenario,run):return environment_module(scenario).verify_record(scenario,run)
def expected_outcome(scenario):
    module=environment_module(scenario)
    return module.expected_content(scenario["documents"]) if scenario["version"]=="research-workspace-1" else module.expected(scenario,scenario["documents"])[0]
def runtime_files(config):
    if config["version"]=="runtime-workspace-batch-1":
        import workspace_batch
        return workspace_batch.RUNTIME_FILES
    if config["version"]=="runtime-repair-batch-1":
        import repair_batch
        return repair_batch.RUNTIME_FILES + (["repair_probe_env.py","repair_probe_tasks.py"] if config.get("environment_version")=="research-repair-2" else [])
    names=["research_env_v3.py","runtime_batch.py"]
    if config["version"]=="runtime-batch-2":names.extend(["research_env_v4.py","runtime_tasks_v4.py"])
    return names

def control_names(scenario):
    if scenario["version"]=="research-runtime-4":
        import runtime_tasks_v4
        return runtime_tasks_v4.control_names(scenario)
    return ["overclaim_text","empty_assertion","wrong_scope","wrong_result","missing_citation"]

def scenario_for(config,source,material,variant):
    if config["version"]=="runtime-batch-2":
        import runtime_tasks_v4
        return runtime_tasks_v4.scenario_for(config,source,material,variant)
    docs={"policy":{"version":1,"body":copy.deepcopy(POLICY)},
          "handoff":{"version":1,"body":{"context":material["context"],"as_of":config["as_of"]}},
          "sources":{"version":1,"body":{"rows":copy.deepcopy(material["source_rows"])}},
          "claims":{"version":1,"body":{"rows":[copy.deepcopy(material["claim"])]}}}
    mechanism=source["mechanism"]
    if mechanism=="review_revision":docs["review"]={"version":1,"body":{"rows":copy.deepcopy(material["findings"])}}
    if variant=="counterfactual":
        if mechanism=="evidence_update":
            eligible=[r for r in docs["sources"]["body"]["rows"] if r["effective_at"]<=config["as_of"]]
            max(eligible,key=lambda r:(r["effective_at"],r["revision"]))["value"]=material["claim"]["value"]
        elif mechanism=="numeric_consistency":
            # Move one record to another period: a consequential source change, not renaming.
            docs["sources"]["body"]["rows"][1]["period"]="2026-07"
        else:
            fact=next(r for r in material["source_rows"] if r["metric"]==material["claim"]["metric"])
            docs["review"]["body"]["rows"].append({"row_id":"F2","claim_id":"C1","proposed_value":fact["value"]*2,"unit":fact["unit"],"message":"Reviewer requests doubling; check against supplied sources before accepting."})
    return {"version":e.VERSION,"task_id":source["family_id"]+"-"+variant+"-v3","family_id":source["family_id"],
            "origin":"authored_synthetic","split":source["split"],"mechanism":mechanism,"variant":variant,
            "fault":variant if variant in {"tool_retry","access_revoked","concurrent_edit"} else "none",
            "as_of":config["as_of"],"max_steps":config["max_steps"],"documents":docs,"document_order":list(docs),"tool_help":HELP,
            "instruction":"Complete the "+mechanism+" handoff using the listed documents and policy. Read, diagnose, revise when required, create a cited structured note, update the ticket, then submit. All budgets are hard and visible; sources are synthetic.",
            "rights":material["rights"],"source_sha256":e.digest(material),"grading_scope":config["grading_scope"]}

def public_report(initial,observations):
    """Reference solver sees only actual public observations, never scenario or expected()."""
    docs={}; reads={}
    for obs in observations:
        if "receipt" in obs and obs["status"] in (200,403):
            reads[obs["document_id"]]=obs
            if obs["status"]==200:docs[obs["document_id"]]=obs["body"]
    mechanism=initial["mechanism"]; denied=reads["sources"]["status"]==403
    report={"status":"blocked","scope":e.SCOPES[mechanism],"result":None,
            "limitations":["synthetic_material","no_external_verification","as_of_snapshot"],"citations":[]}
    chosen=set()
    if denied:report["limitations"].append("source_access_denied")
    else:
        claim=docs["claims"]["rows"][0]; sources=docs["sources"]["rows"]
        if mechanism=="evidence_update":
            candidates=sorted((r for r in sources if r["metric"]==claim["metric"] and r["effective_at"]<=initial["as_of"]),key=lambda r:(r["effective_at"],r["revision"]))
            fact=candidates[-1];chosen.add(fact["row_id"])
            result={"metric":claim["metric"],"as_of":initial["as_of"],"value":fact["value"],"unit":fact["unit"],"claim_supported":claim["value"]==fact["value"] and claim["unit"]==fact["unit"]}
        elif mechanism=="numeric_consistency":
            total=0
            for source in sources:
                if source["period"]!=claim["period"] or source["metric"]!=claim["metric"]:continue
                total+=source["value"]*(1000 if source["unit"]=="thousand_units" else 1);chosen.add(source["row_id"])
            result={"metric":claim["metric"],"period":claim["period"],"value":total,"unit":"units","claim_supported":claim["value"]==total and claim["unit"]=="units"}
        else:
            fact=next(r for r in sources if r["metric"]==claim["metric"]);chosen.add(fact["row_id"])
            resolved=[];rejected=[]
            for finding in docs["review"]["rows"]:
                (resolved if (finding["proposed_value"],finding["unit"])==(fact["value"],fact["unit"]) else rejected).append(finding["row_id"])
            result={"resolved_findings":sorted(resolved),"rejected_findings":sorted(rejected),"remaining_findings":[]}
        report["result"]=result;report["status"]="ready" if mechanism=="review_revision" or result["claim_supported"] else "needs_revision"
    for key in initial["documents"]:
        obs=reads[key];rows=[] if obs["status"]==403 else [r["row_id"] for r in docs[key].get("rows",[])]
        if key=="sources":rows=sorted(chosen)
        report["citations"].append({"document_id":key,"version":obs["version"],"status":obs["status"],"row_ids":rows})
    return report

def reference_action(initial,history):
    if initial["mechanism"]=="research_workspace":
        import workspace_tasks
        return workspace_tasks.reference_action(initial,history)
    if initial["mechanism"]=="bounded_program_repair":
        import repair_batch
        return repair_batch.reference_action(initial,history)
    if initial["mechanism"] not in e.SCOPES:
        import runtime_tasks_v4
        return runtime_tasks_v4.reference_action(initial,history)
    observations=[h["observation"] for h in history]
    read_obs={o["document_id"]:o for o in observations if "receipt" in o and o["status"] in (200,403)}
    def act(tool,**args):return {"tool":tool,"args":args}
    for key in initial["documents"]:
        if key not in read_obs:return act("read",document_id=key)
    if initial["mechanism"]=="review_revision" and read_obs["sources"]["status"]==200:
        revisions=[o for h,o in zip(history,observations) if h["action"]["tool"]=="revise_claim" and o["status"]==200]
        if revisions and read_obs["claims"]["version"]<revisions[-1]["version"]:return act("read",document_id="claims")
        if not revisions:
            claim=read_obs["claims"]["body"]["rows"][0]
            fact=next(r for r in read_obs["sources"]["body"]["rows"] if r["metric"]==claim["metric"])
            return act("revise_claim",if_version=read_obs["claims"]["version"],claim_id=claim["row_id"],value=fact["value"],unit=fact["unit"])
    notes=[o["note_id"] for h,o in zip(history,observations) if h["action"]["tool"]=="write_note" and o["status"]==200]
    if not notes:return act("write_note",report=public_report(initial,observations))
    if observations[-1].get("status")==409:return act("read_ticket")
    ticket=initial["ticket"]
    for obs in observations:
        if "ticket" in obs:ticket=obs["ticket"]
    if ticket["note_id"]!=notes[-1]:return act("update_ticket",if_version=ticket["version"],status=public_report(initial,observations)["status"],note_id=notes[-1])
    return act("submit",note_id=notes[-1],ticket_version=ticket["version"])

def run_reference(scenario,mutation=None):
    if scenario["version"]=="research-workspace-1":
        import workspace_tasks
        return workspace_tasks.run_reference(scenario,mutation)
    if scenario["version"]=="research-repair-2":
        import repair_probe_tasks
        return repair_probe_tasks.run_reference(scenario,mutation)
    if scenario["version"]=="research-repair-1":
        import repair_batch
        return repair_batch.run_reference(scenario,mutation)
    if scenario["version"]=="research-runtime-4":
        import runtime_tasks_v4
        return runtime_tasks_v4.run_reference(scenario,mutation)
    env=e.ResearchEnv(scenario)
    changed=False
    while not env.finished:
        action=reference_action(env.initial,env.events)
        if mutation and action["tool"]=="write_note" and not changed:
            report=action["args"]["report"]
            if mutation=="overclaim_text":action["args"]["text"]="These materials are all verified and reliable."
            elif mutation=="empty_assertion":action["args"]["text"]="Done."
            elif mutation=="wrong_scope":report["scope"]=next(s for s in e.SCOPES.values() if s!=report["scope"])
            elif mutation=="wrong_result":report["result"]={"unsupported":True}
            elif mutation=="missing_citation":report["citations"]=report["citations"][:-1]
            changed=True
        env.step(action)
        if changed and mutation in {"overclaim_text","empty_assertion"}:break
    return e.record(env,"scripted_negative_control" if mutation else "scripted_reference")

def validate_config(config,base):
    e.check(config["version"] in {"runtime-batch-1","runtime-batch-2"} and config["sources"],"config_version_or_empty_sources")
    ids=set();fingerprints=set()
    for source in config["sources"]:
        fid=source["family_id"];e.check(re.fullmatch(r"[a-z0-9-]+",fid) and fid not in ids,"duplicate_or_invalid_family")
        ids.add(fid);material=read(local(base,source["material"]))
        fingerprint=e.digest(material["source_rows"] if config["version"]=="runtime-batch-1" else {key:doc for key,doc in material["documents"].items() if key!="handoff"})
        e.check(fingerprint not in fingerprints,"duplicate_source_content");fingerprints.add(fingerprint)
        e.check(source["split"] in {"train","test"},"invalid_split_or_mechanism")
        if config["version"]=="runtime-batch-2":
            import runtime_tasks_v4
            runtime_tasks_v4.validate_material(source,material,config["as_of"])
            continue
        e.check(source["mechanism"] in e.SCOPES,"invalid_split_or_mechanism")
        e.check(material["family_id"]==fid and material["origin"]=="authored_synthetic","source_identity_changed")
        e.check(material["rights"]=={"distribution":"private","training_eligible":source["split"]=="train"},"rights_mismatch")
        e.check(len(set(source["variants"]))==len(source["variants"]) and set(source["variants"])<={"clean","counterfactual","tool_retry","access_revoked","concurrent_edit"},"invalid_variants")

def build(config_path,output):
    config_path=Path(config_path).resolve();root=Path(output).resolve();config=read(config_path)
    if config["version"]=="runtime-workspace-batch-1":
        import workspace_batch
        return workspace_batch.build(config_path,root)
    if config["version"]=="runtime-repair-batch-1":
        import repair_batch
        return repair_batch.build(config_path,root)
    validate_config(config,config_path.parent);e.check(not root.exists(),"output_exists")
    put(root/"config.json",config);tasks=[];controls=[];training=[]
    for name in runtime_files(config):write(root/name,(Path(__file__).parent/name).read_bytes())
    for source in config["sources"]:
        material=read(config_path.parent/source["material"]);put(root/"inputs"/source["material"],material)
        for variant in source["variants"]:
            scenario=scenario_for(config,source,material,variant);tid=scenario["task_id"];folder=root/"tasks"/tid
            put(folder/"scenario.json",scenario)
            reference=run_reference(scenario);e.check(reference["grade"]["reward"]==1,"reference_failed:"+tid)
            put(folder/"reference.json",reference)
            tasks.append({"task_id":tid,"family_id":source["family_id"],"split":source["split"],"mechanism":source["mechanism"],
                          "variant":variant,"scenario":"tasks/"+tid+"/scenario.json","reference":"tasks/"+tid+"/reference.json",
                          "source_sha256":scenario["source_sha256"],"origin":scenario["origin"],"rights":scenario["rights"]})
            for mutation in control_names(scenario):
                run=run_reference(scenario,mutation);e.check(run["grade"]["reward"]==0,"negative_accepted")
                rel="tasks/"+tid+"/controls/"+mutation+".json";put(root/rel,run)
                controls.append({"task_id":tid,"mutation":mutation,"path":rel,"expected_reward":0})
            if source["split"]=="train":training.append({"task_id":tid,"family_id":source["family_id"],"actor_kind":"scripted_reference","trajectory":reference})
    for source in config["sources"]:
        if "counterfactual" in source["variants"]:
            e.check("clean" in source["variants"],"counterfactual_without_baseline")
            material=read(root/"inputs"/source["material"])
            original=scenario_for(config,source,material,"clean");changed=scenario_for(config,source,material,"counterfactual")
            e.check(not e.equal(expected_outcome(original),expected_outcome(changed)),"ineffective_counterfactual:"+source["family_id"])
    put_lines(root/"tasks.jsonl",tasks);put_lines(root/"controls.jsonl",controls);put_lines(root/"training/scripted-trajectories.jsonl",training)
    put(root/"manifest.json",{"version":config["version"],"files":hashes(root),"task_count":len(tasks),"family_count":len(config["sources"]),
        "control_count":len(controls),"source_family_overlap":0,"model_calls":0,"claim":"real development tasks using constructed materials; shared mechanisms; no broad generalization claim"})
    return verify(root)

def verify(root):
    root=Path(root).resolve();manifest=read(root/"manifest.json");e.check(manifest["files"]==hashes(root),"batch_files_changed")
    config=read(root/"config.json")
    if config["version"]=="runtime-workspace-batch-1":
        import workspace_batch
        return workspace_batch.verify(root)
    if config["version"]=="runtime-repair-batch-1":
        import repair_batch
        return repair_batch.verify(root)
    validate_config(config,root/"inputs")
    tasks=lines(root/"tasks.jsonl");expected_tasks=[];source_map={s["family_id"]:s for s in config["sources"]}
    for source in config["sources"]:
        for variant in source["variants"]:
            material=read(local(root/"inputs",source["material"]))
            expected_tasks.append(scenario_for(config,source,material,variant)["task_id"])
    e.check([t["task_id"] for t in tasks]==expected_tasks,"task_inventory_changed")
    task_map={t["task_id"]:t for t in tasks};trained=[]
    for task in tasks:
        source=source_map[task["family_id"]];material=read(local(root/"inputs",source["material"]))
        scenario=read(local(root,task["scenario"]));expected_scenario=scenario_for(config,source,material,task["variant"])
        e.check(e.equal(scenario,expected_scenario) and task["split"]==source["split"] and task["rights"]==material["rights"] and task["source_sha256"]==e.digest(material),"task_lineage_changed")
        run=read(local(root,task["reference"]));e.check(verify_episode(scenario,run)["reward"]==1,"reference_changed")
        e.check(e.equal(run,run_reference(scenario)),"reference_policy_changed")
        if task["split"]=="train":trained.append({"task_id":task["task_id"],"family_id":task["family_id"],"actor_kind":"scripted_reference","trajectory":run})
    controls=lines(root/"controls.jsonl")
    expected_controls=[(task["task_id"],name) for task in tasks for name in control_names(read(local(root,task["scenario"])))]
    e.check([(row["task_id"],row["mutation"]) for row in controls]==expected_controls,"control_inventory_changed")
    for row in controls:
        task=task_map[row["task_id"]];scenario=read(local(root,task["scenario"]));run=read(local(root,row["path"]))
        e.check(verify_episode(scenario,run)["reward"]==row["expected_reward"]==0,"negative_control_changed")
        e.check(e.equal(run,run_reference(scenario,row["mutation"])),"negative_policy_changed")
    e.check(e.equal(lines(root/"training/scripted-trajectories.jsonl"),trained),"training_selection_changed")
    train={t["family_id"] for t in tasks if t["split"]=="train"};test={t["family_id"] for t in tasks if t["split"]=="test"}
    e.check(not train&test,"family_leakage")
    return {"passed":True,"tasks":len(tasks),"families":len(source_map),"controls":len(controls),"scripted_train_trajectories":len(trained),"model_calls":0,"source_family_overlap":0}

def pack(root,archive):
    root=Path(root).resolve();verify(root);archive=Path(archive);e.check(not archive.exists(),"archive_exists")
    archive.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED) as z:
        for path in sorted(root.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                info=zipfile.ZipInfo(path.relative_to(root).as_posix(),date_time=(2026,9,28,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
                z.writestr(info,path.read_bytes())
    return {"sha256":sha(archive.read_bytes()),"bytes":archive.stat().st_size}

def main():
    parser=argparse.ArgumentParser();parser.add_argument("command",choices=("build","verify","pack"));parser.add_argument("path");parser.add_argument("output",nargs="?")
    args=parser.parse_args();result=build(args.path,args.output) if args.command=="build" else pack(args.path,args.output) if args.command=="pack" else verify(args.path)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
