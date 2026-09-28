"""Frozen mixed-origin research workspace batches and registered-material intake."""
from __future__ import annotations
import copy,csv,io,json,re,unicodedata
from pathlib import Path
import runtime_batch as b
import workspace_env as e
import workspace_tasks as tasks
VERSION="runtime-workspace-batch-1"
RUNTIME_FILES=["research_env_v3.py","runtime_batch.py","workspace_env.py","workspace_tasks.py","workspace_batch.py"]
VARIANTS={"clean","withheld_evidence","stale_artifact","source_refresh","uncertain_applied","uncertain_not_applied"}

def ref(document,row):return {"ref":[document,row]}
def normalize(text):return re.sub(r"\s+"," ",re.sub(r"\d+(?:\.\d+)?","#",unicodedata.normalize("NFKC",text).lower())).strip()
def shingles(text):
    normalized=normalize(text);return {normalized[i:i+12] for i in range(max(1,len(normalized)-11))}
def similarity(left,right):
    a,z=shingles(left),shingles(right);return len(a&z)/len(a|z) if a|z else 1.0

def source_text(material):return e.canonical(material["evidence_documents"])
def prior_text(material):return e.canonical(material.get("documents",{k:v for k,v in material.items() if k not in {"family_id","origin","rights","context"}}))
def structural_signature(material):return e.digest({"outputs":material["outputs"],"evidence_ids":sorted(material["evidence_documents"]),"decision_rule":material["decision_rule"]})

def archived_material(source,files):
    meta=json.loads(files["tasks.jsonl"].split(b"\n")[source["original_task_line"]-1]);report_path=meta["artifacts"]["report"];claims_path=meta["artifacts"]["claims"]
    report=files[report_path].decode("utf-8-sig");claims={r["claim_id"]:r for r in csv.DictReader(io.StringIO(files[claims_path].decode("utf-8-sig")))}
    e.check(meta["task_id"]==source["parent_task_id"] and meta["report_name"]==source["report_name"],"archived_task_identity_changed")
    claim=claims[source["claim_id"]];lines=report.split("\n");matches=[(i+1,line) for i,line in enumerate(lines) if source["excerpt_anchor"] in line];e.check(len(matches)==1,"source_excerpt_not_unique")
    line_no,excerpt=matches[0];evidence_id="archived-report"
    if source["report_name"]=="customer-service":
        match=re.fullmatch(r"Synthesia reports (\d+) percent Fin resolution and (\d+) percent elapsed time reduction",claim["claim"]);e.check(match is not None,"source_claim_changed")
        e.check(claim["scope_or_boundary"]=="Not 96 percent labor or cost reduction" and "2024" in excerpt and "96%" in excerpt,"source_qualification_missing")
        rows=[{"row_id":"RESOLUTION","value":int(match[1]),"unit":"percent","meaning":"Vendor-hosted customer case reported resolution rate."},{"row_id":"ELAPSED","value":int(match[2]),"unit":"percent","meaning":"Elapsed resolution-time reduction; not labor reduction or controlled attribution."}]
        outputs={"case_resolution_percent":{"expression":ref(evidence_id,"RESOLUTION"),"unit":"percent"},"elapsed_time_reduction_percent":{"expression":ref(evidence_id,"ELAPSED"),"unit":"percent"}}
        decision={"literal":"attributed_2024_case_not_controlled_labor_effect"};topic="Repair the scope of a historical customer-support case comparison."
    else:
        e.check(claim["claim"]=="Kling Chinese/English audio supported on selected fal endpoint" and "中文、英文、日文、韩文和西班牙文" in excerpt,"source_channel_scope_changed")
        rows=[{"row_id":"APP","value":["Chinese","English","Japanese","Korean","Spanish"],"unit":"languages","meaning":"Languages listed by the application guide in the archived report."},{"row_id":"ENDPOINT","value":["Chinese","English"],"unit":"languages","meaning":"Native audio languages explicitly reported for the selected fal endpoint."}]
        outputs={"application_languages":{"expression":ref(evidence_id,"APP"),"unit":"languages"},"endpoint_native_languages":{"expression":ref(evidence_id,"ENDPOINT"),"unit":"languages"}}
        decision={"literal":"channel_specific_capabilities_not_interchangeable"};topic="Reconcile application-level and endpoint-specific language claims in a historical video research report."
    return {"family_id":source["family_id"],"source_group_id":meta["source_group"],"parent_task_id":meta["task_id"],"origin":"derived_from_archived_report","rights":meta["rights"],"topic":topic,"result_scope":"archived_report_assertions_2026_09_07","evidence_documents":{evidence_id:{"rows":rows,"excerpt":excerpt,"attribution":"Frozen report assertion; external pages were not independently reverified.","claim":claim}},"outputs":outputs,"decision_rule":decision,"source_updates":[],"source_binding":{"report":report_path,"report_sha256":b.sha(files[report_path]),"line":line_no,"excerpt_sha256":b.sha(excerpt.encode()),"claim_file":claims_path,"claim_id":source["claim_id"],"claims_sha256":b.sha(files[claims_path]),"original_task_id":meta["task_id"],"original_task_index_line":source["original_task_line"]},"missingness":["historical_step_state_not_reconstructed","source_webpages_not_refetched","working_copy_errors_are_synthetic"],"template_group":"workspace-reconciliation-1"}

def validate_material(source,material):
    e.check(source["family_id"]==material["family_id"] and source["split"] in {"train","test","development"},"material_identity_changed")
    e.check(set(source["variants"])<=VARIANTS and len(set(source["variants"]))==len(source["variants"]),"invalid_workspace_variants")
    e.check(material["evidence_documents"] and all(re.fullmatch(r"[a-z][a-z0-9-]+",k) for k in material["evidence_documents"]),"invalid_evidence_documents")
    if source["kind"]=="archive":e.check(source["split"]=="development" and material["rights"]["training_eligible"] is False,"inherited_rights_changed")
    else:
        e.check(material["origin"]=="authored_synthetic" and material["rights"]=={"distribution":"private_internal","allowed_uses":["diagnostic","evaluation","training"],"training_eligible":True},"synthetic_use_declaration_changed")
    if "source_refresh" in source["variants"]:e.check(bool(material["source_updates"]),"missing_source_refresh")
    for key,body in material["evidence_documents"].items():e.check(len({r["row_id"] for r in body["rows"]})==len(body["rows"]),"duplicate_source_rows")

def scenario_for(config,source,material,variant):
    validate_material(source,material);documents={key:{"version":1,"body":copy.deepcopy(body)} for key,body in material["evidence_documents"].items()}
    ids=["report.md","analysis.json"];brief={"topic":material["topic"],"artifact_ids":ids,"evidence_ids":list(material["evidence_documents"]),"outputs":material["outputs"],"decision_rule":material["decision_rule"],"result_scope":material["result_scope"],"material_origin":material["origin"],"task":"Replace the synthetic erroneous working-copy conclusions in both artifacts. Evaluate only these supplied assertions and measurements; preserve the original boundary note."}
    documents["brief"]={"version":1,"body":brief};documents["policy"]={"version":1,"body":e.POLICY}
    documents["old-note"]={"version":1,"body":{"rows":[{"row_id":"OLD","value":999,"unit":"unsupported","meaning":"Superseded discussion draft, not source evidence."}]}}
    for key in ids:
        documents[key]={"version":1,"body":{"content":{"result":{"draft":{"value":999,"unit":"unverified"}},"decision":"unsupported_draft_conclusion","scope":"unqualified_draft","citations":[],"preserved":"Boundary: supplied historical assertions or synthetic measurements only. No external-world validation."},"draft_origin":"synthetic_erroneous_working_copy"}}
    scenario={"version":e.VERSION,"task_id":source["family_id"]+"-"+variant+"-w1","family_id":source["family_id"],"source_group_id":material["source_group_id"],"parent_task_id":material.get("parent_task_id"),"split":source["split"],"rights":material["rights"],"origin":material["origin"],"mechanism":source["mechanism"],"variant":variant,"fault":variant if variant!="clean" else "none","unavailable_documents":[brief["evidence_ids"][0]] if variant=="withheld_evidence" else [],"source_updates":material["source_updates"],"documents":documents,"max_steps":config["max_steps"],"source_sha256":e.digest(material),"template_group":material["template_group"],"missingness":material.get("missingness",[]),"perturbation_origin":"authored_synthetic","grading_scope":"bounded_supplied_evidence_and_deliverable_state"}
    e.expected_content(documents)
    return scenario

def audit_materials(current,prior):
    comparisons=[]
    for i,left in enumerate(current):
        for right in current[:i]+prior:
            same=left["source_group_id"]==right["source_group_id"];score=similarity(left["text"],right["text"])
            suspicious=score>=0.88 or left["normalized_sha256"]==right["normalized_sha256"]
            if not same and suspicious and {left["split"],right["split"]}=={"train","test"}:raise ValueError("near_duplicate_cross_split:"+left["family_id"]+":"+right["family_id"])
            comparisons.append({"left":left["family_id"],"right":right["family_id"],"similarity":round(score,6),"known_same_source":same,"near_duplicate":suspicious})
    return {"comparisons":comparisons,"cross_split_near_duplicates":0,"normalization":"NFKC, lowercase, whitespace and number normalization; character 12-shingle Jaccard >= 0.88. This is a conservative lexical screen, not semantic independence certification.","shared_runtime_template":True}

def audit_row(material,split):
    text=source_text(material);return {"family_id":material["family_id"],"source_group_id":material["source_group_id"],"split":split,"origin":material["origin"],"text":text,"normalized_sha256":b.sha(normalize(text).encode()),"template_group":material["template_group"]}

def build(config_path,output):
    config_path=Path(config_path).resolve();repo=Path(__file__).resolve().parents[1];root=Path(output).resolve();e.check(not root.exists(),"output_exists");config=b.read(config_path)
    e.check(config["version"]==VERSION and config["max_steps"]==48,"workspace_config_changed")
    source_root=repo/"data/research-slices-v0.1";manifest_raw=(source_root/"manifest.json").read_bytes();e.check(b.sha(manifest_raw)==config["archive_manifest_sha256"],"archive_manifest_changed");manifest=json.loads(manifest_raw)
    required={"tasks.jsonl"}
    for source in config["sources"]:
        if source["kind"]=="archive":
            meta=b.lines(source_root/"tasks.jsonl")[source["original_task_line"]-1];required.update([meta["artifacts"]["report"],meta["artifacts"]["claims"]])
    files={name:b.local(source_root,name).read_bytes() for name in sorted(required)}
    for name,raw in files.items():e.check(manifest["files"][name]==b.sha(raw),"archive_source_changed");b.write(root/"source"/name,raw)
    b.write(root/"source/original-manifest.json",manifest_raw);b.put(root/"config.json",config)
    for name in RUNTIME_FILES:b.write(root/name,(Path(__file__).parent/name).read_bytes())
    prior=[]
    for version in ("0.8","0.9"):
        prior_root=repo/("data/runtime-batch-v"+version);prior_config=b.read(prior_root/"config.json");prior_manifest=(prior_root/"manifest.json").read_bytes();b.write(root/"audit/proofs"/(version+"-manifest.json"),prior_manifest)
        for source in prior_config["sources"]:
            name=source["family_id"];path=prior_root/"inputs"/(name+".json");raw=path.read_bytes();e.check(json.loads(prior_manifest)["files"]["inputs/"+name+".json"]==b.sha(raw),"prior_material_changed")
            b.write(root/"audit/proofs"/(version+"-"+name+".json"),raw)
            material=json.loads(raw);body=prior_text(material);prior.append({"family_id":name,"source_group_id":name,"split":source["split"],"origin":material["origin"],"text":body,"normalized_sha256":b.sha(normalize(body).encode()),"input_path":"audit/proofs/"+version+"-"+name+".json","manifest_path":"audit/proofs/"+version+"-manifest.json","source_index_path":"inputs/"+name+".json"})
    b.put(root/"audit/prior.json",prior)
    rows=[];controls=[];candidates=[];current=[];training=[]
    for source in config["sources"]:
        material=archived_material(source,files) if source["kind"]=="archive" else b.read(b.local(config_path.parent,source["material"]))
        validate_material(source,material);b.put(root/"inputs"/(source["family_id"]+".json"),material);current.append(audit_row(material,source["split"]))
        candidates.append({"family_id":source["family_id"],"origin":material["origin"],"source_group_id":material["source_group_id"],"split":source["split"],"rights":material["rights"],"quality":{"material_bound":True,"historical_full_trajectory":False,"executable_task":True},"missingness":material.get("missingness",[]),"disposition":"accepted","mechanism":source["mechanism"],"variants":source["variants"]})
        for variant in source["variants"]:
            scenario=scenario_for(config,source,material,variant);tid=scenario["task_id"];folder=root/"tasks"/tid;b.put(folder/"scenario.json",scenario)
            good=tasks.run_reference(scenario);e.check(e.verify_record(scenario,good)["reward"]==1,"reference_failed:"+tid);b.put(folder/"reference.json",good)
            alternative=tasks.run_reference(scenario,reverse=True);e.check(e.verify_record(scenario,alternative)["reward"]==1,"alternative_reference_failed");b.put(folder/"alternative-reference.json",alternative)
            for name in tasks.control_names(scenario):
                run=tasks.run_reference(scenario,name);e.check(e.verify_record(scenario,run)["reward"]==0,"control_accepted:"+name);path="tasks/"+tid+"/controls/"+name+".json";b.put(root/path,run);controls.append({"task_id":tid,"mutation":name,"path":path,"expected_reward":0})
            row={k:scenario[k] for k in ("task_id","family_id","source_group_id","parent_task_id","split","rights","origin","mechanism","variant","source_sha256","template_group")};row.update(scenario="tasks/"+tid+"/scenario.json",reference="tasks/"+tid+"/reference.json",normalized_content_sha256=current[-1]["normalized_sha256"]);rows.append(row)
            if source["split"]=="train" and material["rights"]["training_eligible"]:training.append({"task_id":tid,"actor_kind":"scripted_reference","trajectory":good})
    b.put(root/"intake/candidates.json",candidates);b.put(root/"audit/current.json",current);b.put(root/"audit/similarity.json",audit_materials(current,prior));b.put_lines(root/"tasks.jsonl",rows);b.put_lines(root/"controls.jsonl",controls);b.put_lines(root/"training/scripted-trajectories.jsonl",training)
    b.put(root/"manifest.json",{"version":VERSION,"files":b.hashes(root)})
    return verify(root)

def verify(root):
    root=Path(root);e.check(b.read(root/"manifest.json")["files"]==b.hashes(root),"workspace_batch_files_changed");config=b.read(root/"config.json");raw=(root/"source/original-manifest.json").read_bytes();e.check(b.sha(raw)==config["archive_manifest_sha256"],"archive_manifest_changed");manifest=json.loads(raw);files={}
    for path in (root/"source").rglob('*'):
        if path.is_file() and path.name!="original-manifest.json":
            name=path.relative_to(root/"source").as_posix();files[name]=path.read_bytes();e.check(manifest["files"][name]==b.sha(files[name]),"archive_source_changed")
    expected_rows=[];expected_controls=[];candidates=[];current=[];training=[]
    for source in config["sources"]:
        material=b.read(root/"inputs"/(source["family_id"]+".json"));validate_material(source,material)
        if source["kind"]=="archive":e.check(e.equal(material,archived_material(source,files)),"archived_material_derivation_changed")
        else:e.check(e.digest(material)==source["material_sha256"],"synthetic_material_changed")
        current.append(audit_row(material,source["split"]));candidates.append({"family_id":source["family_id"],"origin":material["origin"],"source_group_id":material["source_group_id"],"split":source["split"],"rights":material["rights"],"quality":{"material_bound":True,"historical_full_trajectory":False,"executable_task":True},"missingness":material.get("missingness",[]),"disposition":"accepted","mechanism":source["mechanism"],"variants":source["variants"]})
        for variant in source["variants"]:
            scenario=scenario_for(config,source,material,variant);tid=scenario["task_id"];folder=root/"tasks"/tid;e.check(e.equal(b.read(folder/"scenario.json"),scenario),"workspace_scenario_changed")
            for name,reverse in (("reference.json",False),("alternative-reference.json",True)):
                run=b.read(folder/name);e.check(run["actor_kind"]=="scripted_reference" and e.verify_record(scenario,run)["reward"]==1,"workspace_reference_changed");e.check(e.equal(run,tasks.run_reference(scenario,reverse=reverse)),"public_reference_changed")
            for name in tasks.control_names(scenario):
                path="tasks/"+tid+"/controls/"+name+".json";run=b.read(root/path);e.check(run["actor_kind"]=="scripted_negative_control" and e.verify_record(scenario,run)["reward"]==0,"workspace_control_changed");e.check(e.equal(run,tasks.run_reference(scenario,name)),"public_control_changed");expected_controls.append({"task_id":tid,"mutation":name,"path":path,"expected_reward":0})
            row={k:scenario[k] for k in ("task_id","family_id","source_group_id","parent_task_id","split","rights","origin","mechanism","variant","source_sha256","template_group")};row.update(scenario="tasks/"+tid+"/scenario.json",reference="tasks/"+tid+"/reference.json",normalized_content_sha256=current[-1]["normalized_sha256"]);expected_rows.append(row)
            if source["split"]=="train" and material["rights"]["training_eligible"]:training.append({"task_id":tid,"actor_kind":"scripted_reference","trajectory":b.read(folder/"reference.json")})
    e.check(e.equal(expected_rows,b.lines(root/"tasks.jsonl")),"workspace_task_index_changed");e.check(e.equal(expected_controls,b.lines(root/"controls.jsonl")),"workspace_controls_index_changed");e.check(e.equal(training,b.lines(root/"training/scripted-trajectories.jsonl")),"scripted_training_changed")
    e.check(e.equal(candidates,b.read(root/"intake/candidates.json")) and e.equal(current,b.read(root/"audit/current.json")),"intake_projection_changed")
    prior=b.read(root/"audit/prior.json")
    for row in prior:
        raw=b.local(root,row["input_path"]).read_bytes();proof=b.read(b.local(root,row["manifest_path"]));e.check(proof["files"][row["source_index_path"]]==b.sha(raw),"prior_material_proof_changed");text=prior_text(json.loads(raw));e.check(text==row["text"] and row["normalized_sha256"]==b.sha(normalize(text).encode()),"prior_material_projection_changed")
    e.check(e.equal(b.read(root/"audit/similarity.json"),audit_materials(current,prior)),"similarity_audit_changed")
    return {"passed":True,"tasks":len(expected_rows),"families":len(config["sources"]),"source_groups":len({x["source_group_id"] for x in expected_rows}),"retained_real_source_groups":len({x["source_group_id"] for x in expected_rows if x["origin"]!="authored_synthetic"}),"new_synthetic_source_groups":len({x["source_group_id"] for x in expected_rows if x["origin"]=="authored_synthetic"}),"controls":len(expected_controls),"alternative_references":len(expected_rows),"scripted_train_trajectories":len(training),"cross_split_near_duplicates":0,"model_calls":0}
