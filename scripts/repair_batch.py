"""Import real incident bindings and reconstruct bounded executable repair tasks."""
from __future__ import annotations
import ast,copy,json,zipfile
from pathlib import Path
import runtime_batch as b
import research_env_v3 as common
import repair_env as env
VERSION="runtime-repair-batch-1"
RUNTIME_FILES=["research_env_v3.py","runtime_batch.py","repair_executor.py","repair_env.py","repair_batch.py"]
CONTROLS=["initial_unfixed","partial_fix","no_baseline","no_retest","edit_after_test","wrong_binding"]
def function(source):
    tree=ast.parse(source);return ast.get_source_segment(source,next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="solve"))+"\n"
def material_from(files,task_id):
    prefix="tasks/"+task_id+"/";meta=json.loads(files[prefix+"task.json"])
    incidents=[json.loads(x) for x in files["processing/incidents.jsonl"].split(b"\n") if x.strip()]
    incident=next(x for x in incidents if x["incident_id"]==meta["parent_incident"])
    wanted={incident["failure_line"]}|{n for key in ("diagnosis_lines","patch_lines","retry_lines","verification_lines") for n in incident[key]}
    events=[json.loads(x) for x in files["processing/events.jsonl"].split(b"\n") if x.strip()];selected=[x for x in events if x["source_line"] in wanted]
    common.check({x["source_line"] for x in selected}==wanted,"incomplete_source_incident")
    return {"task_id":task_id,"origin":"observed_failure_minimal_reproduction","source_group_id":"dataset-processing","split":meta["split"],"rights":meta["rights"],"contract":files[prefix+"instruction.md"].decode().strip(),"initial":function(files[prefix+"environment/worker.py"].decode()),"partial":function(files[prefix+"controls/partial.py"].decode()),"reference":function(files[prefix+"solution/worker.py"].decode()),"cases":json.loads(files[prefix+"tests/cases.json"]),"incident":incident,"source_events":selected,"missingness":["original_machine_not_reconstructed","minimal_reproduction_not_original_program","historical_truncation_not_recovered"]}
def scenario_for(config,material,variant):
    if config.get("source_mode")=="authored_synthetic":return authored_scenario(config,material,variant)
    m=copy.deepcopy(material);layout=variant=="layout"
    if layout:
        for key in ("initial","partial","reference"):m[key]=m[key].replace("solve(data)","solve(payload)").replace("data[","payload[")
    ids={"policy":"policy","contract":"contract","worker":"worker.py","sample":"sample"}
    if layout:ids={"sample":"inputs/reproduction.json","worker":"src/transform.py","contract":"tickets/change.md","policy":"handbook"}
    cases=copy.deepcopy(m["cases"])
    # Known-answer additional cases vary records independently of candidate/reference code.
    if m["task_id"]=="jsonl-unicode":extra={"name":"additional-unicode","input":{"text":'{"other":"a\u0085b\u2029c"}\r\n'},"expected":{"ok":True,"value":[{"other":"a\u0085b\u2029c"}]}}
    elif m["task_id"]=="manifest-hashes":extra={"name":"missing-lf-empty","input":{"text":"", "ref":{"sha256_bytes":env.code_hash("")}},"expected":{"ok":True,"value":False}}
    else:extra={"name":"different-order-and-future","input":{"documents_json":json.dumps({"z":{"title":"A","roles":["reviewer"],"effective_at":"2026-09-01"},"m":{"title":"Z","roles":["reviewer"],"effective_at":"2026-09-01"},"a":{"title":"M","roles":["reviewer"],"effective_at":"2027-01-01"}}),"role":"reviewer","as_of":"2026-09-28"},"expected":{"ok":True,"value":["m","z"]}}
    public=cases[:2]
    if layout:public=list(reversed(public))
    return {"version":env.VERSION,"task_id":"repair-"+m["task_id"]+"-"+variant+"-v1","family_id":"repair-"+m["task_id"],"source_group_id":m["source_group_id"],"mechanism":"bounded_program_repair","variant":variant,"fault":"stale_patch" if variant=="stale_patch" else "clean","split":m["split"],"rights":m["rights"],"origin":"real_incident_derived_environment","parent_task_id":m["task_id"],"source_sha256":common.digest(material),"source_incident":m["incident"]["incident_id"],"max_steps":config["max_steps"],"document_ids":ids,"document_order":list(ids.values()),"contract":m["contract"],"initial_code":m["initial"],"reference_code":m["reference"],"partial_code":m["partial"],"public_cases":public,"private_cases":cases[2:]+[extra],"missingness":m["missingness"],"variant_origin":"derived_reproduction" if variant=="clean" else "synthetic_perturbation_of_reproduction"}
def reference_action(initial,history,reference=None,mutation=None):
    def action(tool,**args):return {"tool":tool,"args":args}
    ids=initial["document_roles"];seen={}
    for event in history:
        if event["action"]["tool"]=="read" and event["observation"]["status"]==200:seen[event["action"]["args"]["document_id"]]=event["observation"]
    for key in initial["documents"]:
        if key not in seen:return action("read",document_id=key)
    reads=[x for x in history if x["action"]["tool"]=="read" and x["action"]["args"]["document_id"]==ids["worker"]]
    patches=[x for x in history if x["action"]["tool"]=="patch"]
    if patches and (not reads or history.index(reads[-1])<history.index(patches[-1])):return action("read",document_id=ids["worker"])
    worker=seen[ids["worker"]];tests=[x["observation"]["test"] for x in history if x["action"]["tool"]=="test" and x["observation"]["status"]==200]
    if not tests and mutation!="no_baseline":return action("test")
    changed=any(x["observation"]["status"]==200 for x in patches)
    if not changed and mutation!="initial_unfixed":
        code=worker["body"]["code"];target=reference
        if target is None:
            # Reference implementation selected by explicit task contract, never evaluator output.
            contract=seen[ids["contract"]]["body"]["text"]
            if "JSONL" in contract:target="def solve(data):\n    return [json.loads(x) for x in data['text'].split('\\n') if x.strip()]\n"
            elif "sha256_lf" in contract:target="def solve(data):\n    raw=data['text']; ref=data['ref']\n    normalized=raw.replace('\\r\\n','\\n').replace('\\r','\\n')\n    return ref.get('sha256_lf')==hashlib.sha256(normalized.encode()).hexdigest() and ('sha256_bytes' not in ref or ref['sha256_bytes']==hashlib.sha256(raw.encode()).hexdigest())\n"
            else:target="def solve(data):\n    return [i for i,d in sorted(json.loads(data['documents_json']).items()) if data['role'] in d['roles'] and d['effective_at']<=data['as_of']]\n"
        if "# Concurrent edit: preserve this note." in code:target+="\n# Concurrent edit: preserve this note.\n"
        return action("patch",if_version=worker["version"],old=code,new=target)
    if changed and (not tests or tests[-1]["version"]!=worker["version"]) and mutation!="no_retest":return action("test")
    if mutation=="edit_after_test" and len([x for x in patches if x["observation"]["status"]==200])==1:return action("patch",if_version=worker["version"],old=worker["body"]["code"],new=worker["body"]["code"]+"\n# unverified later edit\n")
    notes=[x["observation"]["note_id"] for x in history if x["action"]["tool"]=="write_note" and x["observation"]["status"]==200]
    if not notes:return action("write_note",report={"status":"ready","scope":"bounded_program_repair","code_sha256":"0"*64 if mutation=="wrong_binding" else worker["body"]["code_sha256"],"test_run_id":tests[-1]["test_run_id"] if tests else "none","diagnosis":"Reproduced baseline failure, changed the specified behavior and checked the latest candidate."})
    ticket=initial["ticket"]
    for event in history:
        if "ticket" in event["observation"]:ticket=event["observation"]["ticket"]
    if ticket["note_id"]!=notes[-1]:return action("update_ticket",if_version=ticket["version"],status="ready",note_id=notes[-1])
    return action("submit",note_id=notes[-1],ticket_version=ticket["version"])
def run_reference(scenario,mutation=None):
    if scenario["version"]=="research-repair-2":
        import repair_probe_tasks
        return repair_probe_tasks.run_reference(scenario,mutation)
    runtime=env.ResearchEnv(scenario)
    while not runtime.finished:
        effective="no_retest" if mutation=="edit_after_test" and sum(x["action"]["tool"]=="patch" and x["observation"]["status"]==200 for x in runtime.events)>1 else mutation
        target=scenario["partial_code"] if mutation=="partial_fix" else scenario.get("control_codes",{}).get(mutation)
        if target is None and scenario.get("origin")=="authored_synthetic_environment":target=scenario["reference_code"]
        action=reference_action(runtime.initial,runtime.events,target,effective)
        runtime.step(action)
    return env.record(runtime,"scripted_negative_control" if mutation else "scripted_reference")

def build(config_path,output):
    config=b.read(config_path);root=Path(output).resolve();common.check(not root.exists(),"output_exists")
    if config.get("source_mode")=="authored_synthetic":return build_authored(config,root)
    repo=Path(__file__).resolve().parents[1];source=repo/"data/agent-runtime-v0.4"
    common.check(b.sha((repo/"artifacts/agent-runtime-v0.4.zip").read_bytes())==config["source_archive_sha256"],"source_archive_changed")
    manifest=b.read(source/"manifest.json");common.check(b.sha((source/"manifest.json").read_bytes())==config["source_manifest_sha256"],"source_manifest_changed")
    b.put(root/"config.json",config);b.write(root/"source/manifest.json",(source/"manifest.json").read_bytes())
    names={"processing/events.jsonl","processing/incidents.jsonl"}
    for item in config["sources"]:
        names.update("tasks/"+item["task_id"]+"/"+name for name in ("task.json","instruction.md","environment/worker.py","controls/partial.py","solution/worker.py","tests/cases.json"))
    files={}
    for name in sorted(names):
        raw=b.local(source,name).read_bytes();common.check(b.sha(raw)==manifest["files"][name],"source_file_changed:"+name);files[name]=raw;b.write(root/"source"/name,raw)
    for name in RUNTIME_FILES:b.write(root/name,(Path(__file__).parent/name).read_bytes())
    tasks=[];controls=[]
    for item in config["sources"]:
        material=material_from(files,item["task_id"]);b.put(root/"inputs"/(item["task_id"]+".json"),material)
        for variant in item["variants"]:
            scenario=scenario_for(config,material,variant);tid=scenario["task_id"];folder=root/"tasks"/tid;b.put(folder/"scenario.json",scenario)
            reference=run_reference(scenario);common.check(reference["grade"]["reward"]==1,"reference_failed:"+tid);b.put(folder/"reference.json",reference)
            tasks.append({k:scenario[k] for k in ("task_id","family_id","source_group_id","mechanism","variant","split","rights","origin","parent_task_id","source_sha256")}|{"scenario":"tasks/"+tid+"/scenario.json","reference":"tasks/"+tid+"/reference.json"})
            for mutation in CONTROLS:
                run=run_reference(scenario,mutation);common.check(run["grade"]["reward"]==0,"negative_control_passed:"+mutation);path="tasks/"+tid+"/controls/"+mutation+".json";b.put(root/path,run);controls.append({"task_id":tid,"mutation":mutation,"path":path,"expected_reward":0})
    b.put_lines(root/"tasks.jsonl",tasks);b.put_lines(root/"controls.jsonl",controls);b.put_lines(root/"training/scripted-trajectories.jsonl",[])
    b.put(root/"manifest.json",{"version":VERSION,"files":b.hashes(root),"task_count":len(tasks),"real_incident_chains":len(config["sources"]),"source_groups":1,"new_independent_source_groups":0})
    return verify(root)
def verify(root):
    root=Path(root);manifest=b.read(root/"manifest.json");common.check(manifest["files"]==b.hashes(root),"batch_files_changed");config=b.read(root/"config.json")
    if config.get("source_mode")=="authored_synthetic":return verify_authored(root,config,manifest)
    common.check(config["version"]==VERSION and b.sha((root/"source/manifest.json").read_bytes())==config["source_manifest_sha256"],"source_manifest_changed")
    original=b.read(root/"source/manifest.json");files={p.relative_to(root/"source").as_posix():p.read_bytes() for p in (root/"source").rglob("*") if p.is_file() and p.name!="manifest.json"}
    for name,raw in files.items():common.check(original["files"].get(name)==b.sha(raw),"historical_source_changed:"+name)
    expected_tasks=[];expected_controls=[];rows=b.lines(root/"tasks.jsonl");task_map={x["task_id"]:x for x in rows}
    for item in config["sources"]:
        material=material_from(files,item["task_id"]);common.check(common.equal(material,b.read(root/"inputs"/(item["task_id"]+".json"))),"material_derivation_changed")
        common.check(material["split"]=="development" and material["rights"]["training_eligible"] is False,"inherited_use_changed")
        for variant in item["variants"]:
            expected=scenario_for(config,material,variant);tid=expected["task_id"];expected_tasks.append(tid);row=task_map[tid];scenario=b.read(b.local(root,row["scenario"]))
            common.check(common.equal(scenario,expected),"task_lineage_changed")
            for key in ("family_id","source_group_id","mechanism","variant","split","rights","origin","parent_task_id","source_sha256"):common.check(common.equal(row[key],scenario[key]),"task_index_changed")
            run=b.read(b.local(root,row["reference"]));common.check(env.verify_record(scenario,run)["reward"]==1 and common.equal(run,run_reference(scenario)),"reference_changed")
            for mutation in CONTROLS:expected_controls.append((tid,mutation))
    common.check([x["task_id"] for x in rows]==expected_tasks,"task_inventory_changed")
    controls=b.lines(root/"controls.jsonl");common.check([(x["task_id"],x["mutation"]) for x in controls]==expected_controls,"control_inventory_changed")
    for row in controls:
        scenario=b.read(root/task_map[row["task_id"]]["scenario"]);run=b.read(b.local(root,row["path"]))
        common.check(b.verify_episode(scenario,run)["reward"]==row["expected_reward"]==0 and common.equal(run,run_reference(scenario,row["mutation"])),"negative_control_changed")
    common.check(not b.lines(root/"training/scripted-trajectories.jsonl"),"historical_training_promotion")
    return {"passed":True,"tasks":len(rows),"families":len(config["sources"]),"real_incident_chains":len(config["sources"]),"source_groups":1,"new_independent_source_groups":0,"controls":len(controls),"scripted_train_trajectories":0,"model_calls":0,"source_family_overlap":0}


def authored_scenario(config,material,variant):
    """The same repair environment, with original authored inputs rather than archived incidents."""
    common.check(variant=="clean","unsupported_authored_variant")
    m=material;ids={"policy":"policy","contract":"contract","worker":"worker.py","sample":"sample"}
    result={"version":env.VERSION,"task_id":"repair-"+m["task_id"]+"-clean-v1","family_id":m.get("family_id","repair-"+m["task_id"]),
        "source_group_id":m["source_group_id"],"mechanism":"bounded_program_repair","variant":variant,"fault":"clean",
        "split":m["split"],"rights":copy.deepcopy(m["rights"]),"origin":"authored_synthetic_environment","parent_task_id":m.get("parent_task_id"),
        "source_sha256":common.digest(m),"source_incident":None,"max_steps":config["max_steps"],"document_ids":ids,"document_order":list(ids.values()),
        "contract":m["contract"],"initial_code":m["initial"],"reference_code":m["reference"],"partial_code":m["partial"],
        "public_cases":copy.deepcopy(m["public_cases"]),"private_cases":copy.deepcopy(m["private_cases"]),
        "control_codes":copy.deepcopy(m.get("control_codes",{})),"missingness":m["missingness"],"variant_origin":"derived_synthetic_initial_code_variant" if m.get("parent_task_id") else "authored_synthetic"}
    if config.get("environment_version")=="research-repair-2":
        result.update(version="research-repair-2",task_id="repair-"+m["task_id"]+"-clean-v2",mechanism="counterexample_driven_program_repair",oracle_id=m["oracle_id"],reference_probe=copy.deepcopy(m["reference_probe"]))
    return result

def authored_controls(scenario):
    extra=[]
    if scenario["version"]=="research-repair-2":
        import repair_probe_tasks
        extra=repair_probe_tasks.CONTROLS
    return CONTROLS+extra+sorted(scenario["control_codes"])

def parent_paths(item):
    prefix="source/parents/"+item["task_id"]
    return prefix+".tasks.jsonl",prefix+".manifest.json"

def freeze_authored_parent(repo,root,item):
    parent=item.get("parent")
    if parent is None:return
    archive=b.local(repo/"artifacts",parent["archive"])
    common.check(b.sha(archive.read_bytes())==parent["archive_sha256"],"parent_archive_changed")
    with zipfile.ZipFile(archive) as z:
        index=z.read("batch/tasks.jsonl");manifest=z.read("batch/manifest.json")
    for path,raw,key in zip(parent_paths(item),(index,manifest),("index_sha256","manifest_sha256")):
        common.check(b.sha(raw)==parent[key],"parent_snapshot_changed")
        b.write(b.local(root,path),raw)

def verify_authored_parent(root,item,material):
    parent=item.get("parent")
    if parent is None:
        common.check(not material.get("parent_task_id") and "family_id" not in material,"authored_parent_binding_missing")
        return
    index_path,manifest_path=parent_paths(item)
    raw=b.local(root,index_path).read_bytes();manifest_raw=b.local(root,manifest_path).read_bytes()
    common.check(b.sha(raw)==parent["index_sha256"] and b.sha(manifest_raw)==parent["manifest_sha256"],"parent_snapshot_changed")
    common.check(json.loads(manifest_raw)["files"].get("tasks.jsonl")==b.sha(raw),"parent_index_unbound")
    matches=[row for row in b.lines(root/index_path) if row["task_id"]==parent["task_id"]]
    common.check(len(matches)==1,"parent_task_missing_or_ambiguous")
    original=matches[0]
    common.check(material.get("parent_task_id")==original["task_id"] and material.get("family_id")==original["family_id"] and material["source_group_id"]==original["source_group_id"],"parent_lineage_changed")
    common.check(material["split"]==original["split"] and common.equal(material["rights"],original["rights"]),"parent_use_changed")

def authored_groups(rows):
    groups={r["source_group_id"] for r in rows}
    inherited={r["source_group_id"] for r in rows if r.get("parent_task_id")}
    return len(groups),len(groups-inherited)

def authored_material(root,config,item):
    raw=(root/"source"/(item["task_id"]+".json")).read_bytes()
    common.check(b.sha(raw)==item["sha256"],"authored_source_changed")
    material=json.loads(raw)
    common.check(material["task_id"]==item["task_id"] and material["origin"]=="authored_synthetic","authored_origin_changed")
    common.check(material["split"] in {"train","development","test"} and type(material["rights"]["training_eligible"]) is bool,"authored_use_missing")
    common.check(material["public_cases"] and material["private_cases"] and material["sources"] and material["missingness"],"authored_contract_incomplete")
    common.check(not set(CONTROLS)&set(material.get("control_codes",{})),"authored_control_collision")
    verify_authored_parent(root,item,material)
    return material

def build_authored(config,root):
    common.check(config["version"]==VERSION and config["sources"],"invalid_authored_config")
    repo=Path(__file__).resolve().parents[1];b.put(root/"config.json",config)
    for name in b.runtime_files(config):b.write(root/name,(Path(__file__).parent/name).read_bytes())
    tasks=[];controls=[];training=[]
    for item in config["sources"]:
        raw=b.local(repo,item["path"]).read_bytes();common.check(b.sha(raw)==item["sha256"],"authored_source_changed")
        freeze_authored_parent(repo,root,item)
        b.write(root/"source"/(item["task_id"]+".json"),raw);material=authored_material(root,config,item)
        b.put(root/"inputs"/(item["task_id"]+".json"),material)
        for variant in item["variants"]:
            scenario=authored_scenario(config,material,variant);tid=scenario["task_id"];folder=root/"tasks"/tid;b.put(folder/"scenario.json",scenario)
            reference=run_reference(scenario);common.check(reference["grade"]["reward"]==1,"reference_failed:"+tid);b.put(folder/"reference.json",reference)
            tasks.append({k:scenario[k] for k in ("task_id","family_id","source_group_id","mechanism","variant","split","rights","origin","parent_task_id","source_sha256")}|{"scenario":"tasks/"+tid+"/scenario.json","reference":"tasks/"+tid+"/reference.json"})
            if scenario["split"]=="train" and scenario["rights"]["training_eligible"]:training.append(reference)
            for mutation in authored_controls(scenario):
                run=run_reference(scenario,mutation);common.check(run["grade"]["reward"]==0,"negative_control_passed:"+mutation)
                path="tasks/"+tid+"/controls/"+mutation+".json";b.put(root/path,run);controls.append({"task_id":tid,"mutation":mutation,"path":path,"expected_reward":0})
    b.put_lines(root/"tasks.jsonl",tasks);b.put_lines(root/"controls.jsonl",controls);b.put_lines(root/"training/scripted-trajectories.jsonl",training)
    groups,new_groups=authored_groups(tasks)
    b.put(root/"manifest.json",{"version":VERSION,"files":b.hashes(root),"task_count":len(tasks),"real_incident_chains":0,
        "source_groups":groups,"new_independent_source_groups":new_groups})
    return verify(root)

def verify_authored(root,config,manifest):
    expected_tasks=[];expected_controls=[];expected_training=[];rows=b.lines(root/"tasks.jsonl");task_map={x["task_id"]:x for x in rows}
    common.check(config["version"]==VERSION and config["sources"],"invalid_authored_config")
    for item in config["sources"]:
        material=authored_material(root,config,item)
        common.check(common.equal(material,b.read(root/"inputs"/(item["task_id"]+".json"))),"authored_material_changed")
        for variant in item["variants"]:
            scenario=authored_scenario(config,material,variant);tid=scenario["task_id"];expected_tasks.append(tid);row=task_map[tid]
            common.check(common.equal(b.read(b.local(root,row["scenario"])),scenario),"task_lineage_changed")
            for key in ("family_id","source_group_id","mechanism","variant","split","rights","origin","parent_task_id","source_sha256"):
                common.check(common.equal(row[key],scenario[key]),"task_index_changed")
            reference=b.read(b.local(root,row["reference"]))
            common.check(b.verify_episode(scenario,reference)["reward"]==1 and common.equal(reference,run_reference(scenario)),"reference_changed")
            if scenario["split"]=="train" and scenario["rights"]["training_eligible"]:expected_training.append(reference)
            for mutation in authored_controls(scenario):expected_controls.append((tid,mutation))
    common.check([r["task_id"] for r in rows]==expected_tasks and len(set(expected_tasks))==len(expected_tasks),"task_inventory_changed")
    controls=b.lines(root/"controls.jsonl");common.check([(x["task_id"],x["mutation"]) for x in controls]==expected_controls,"control_inventory_changed")
    for row in controls:
        scenario=b.read(b.local(root,task_map[row["task_id"]]["scenario"]));run=b.read(b.local(root,row["path"]))
        common.check(b.verify_episode(scenario,run)["reward"]==row["expected_reward"]==0 and common.equal(run,run_reference(scenario,row["mutation"])),"negative_control_changed")
    common.check(common.equal(b.lines(root/"training/scripted-trajectories.jsonl"),expected_training),"authored_training_changed")
    groups,new_groups=authored_groups(rows)
    common.check(manifest["task_count"]==len(rows) and manifest["real_incident_chains"]==0 and manifest["source_groups"]==groups and manifest["new_independent_source_groups"]==new_groups,"authored_counts_changed")
    return {"passed":True,"tasks":len(rows),"families":len({r["family_id"] for r in rows}),"real_incident_chains":0,"source_groups":groups,
        "new_independent_source_groups":new_groups,"controls":len(controls),"scripted_train_trajectories":len(expected_training),"model_calls":0,"source_family_overlap":0,
        "boundary":"Original synthetic inputs; source-group counts are catalog bookkeeping, not independent company observations. Hidden behavioral cases are not an independent task test split."}
