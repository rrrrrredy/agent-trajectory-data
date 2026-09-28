"""Import real incident bindings and reconstruct bounded executable repair tasks."""
from __future__ import annotations
import ast,copy,json
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
    runtime=env.ResearchEnv(scenario)
    while not runtime.finished:
        effective="no_retest" if mutation=="edit_after_test" and sum(x["action"]["tool"]=="patch" and x["observation"]["status"]==200 for x in runtime.events)>1 else mutation
        action=reference_action(runtime.initial,runtime.events,scenario["partial_code"] if mutation=="partial_fix" else None,effective)
        runtime.step(action)
    return env.record(runtime,"scripted_negative_control" if mutation else "scripted_reference")

def build(config_path,output):
    config=b.read(config_path);root=Path(output).resolve();common.check(not root.exists(),"output_exists")
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
        common.check(env.verify_record(scenario,run)["reward"]==row["expected_reward"]==0 and common.equal(run,run_reference(scenario,row["mutation"])),"negative_control_changed")
    common.check(not b.lines(root/"training/scripted-trajectories.jsonl"),"historical_training_promotion")
    return {"passed":True,"tasks":len(rows),"families":len(config["sources"]),"real_incident_chains":len(config["sources"]),"source_groups":1,"new_independent_source_groups":0,"controls":len(controls),"scripted_train_trajectories":0,"model_calls":0,"source_family_overlap":0}
