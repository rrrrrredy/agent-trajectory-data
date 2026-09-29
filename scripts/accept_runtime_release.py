"""Offline acceptance of an extracted runtime archive, including rehashed mutations."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,shutil,subprocess,sys,zipfile

def read(path):return json.loads(Path(path).read_bytes())
def save(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n",encoding="utf-8",newline="\n")
def rows(path):return [json.loads(x) for x in Path(path).read_bytes().split(b"\n") if x.strip()]
def row_save(path,values):Path(path).write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in values),encoding="utf-8")
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def verify_probe_pairs(scenario,run,module):
    """Check actual regression evidence independently of the aggregate reward."""
    state=run["final_state"];pairs=run["grade"]["validated_regression_pairs"]
    probes=state["probes"];by_id={probe["probe_id"]:probe for probe in probes}
    assert len(by_id)==len(probes)
    visible=[event for event in run["events"] if event["action"]["tool"]=="probe" and event["observation"].get("status")==200]
    assert module.equal([event["observation"]["probe"] for event in visible],probes)
    for event in visible:
        probe=event["observation"]["probe"]
        assert module.equal(event["action"]["args"],{"input":probe["input"],"expected":probe["expected"]})
        assert event["step"]==probe["step"]
    patches=[event["step"] for event in run["events"] if event["action"]["tool"]=="patch" and event["observation"].get("status")==200]
    seen=set()
    for pair in pairs:
        identity=(pair["baseline_probe_id"],pair["fixed_probe_id"])
        assert identity not in seen;seen.add(identity)
        before,after=(by_id[identifier] for identifier in identity)
        assert before["version"]==1 and before["code_sha256"]==module.code_hash(scenario["initial_code"])
        assert before["matches_claim"] is False and patches and before["step"]<min(patches)
        assert after["version"]==state["version"] and after["code_sha256"]==module.code_hash(state["code"])
        assert after["matches_claim"] is True and after["step"]>before["step"]
        assert module.equal([before["input"],before["expected"]],[after["input"],after["expected"]])
        assert module.valid_input(before["input"])
        expected=module.oracle(before["input"])
        assert module.equal(expected,before["expected"])
        assert not module.equal(before["actual"],expected) and module.equal(after["actual"],expected)
        assert module.equal(module.runner.execute(scenario["initial_code"],before["input"]),before["actual"])
        assert module.equal(module.runner.execute(state["code"],after["input"]),after["actual"])
    assert bool(pairs)==run["grade"]["checks"]["current_regression_pass"]
    if run["grade"]["reward"]:
        assert pairs and run["complete"]
        note=state["notes"][state["submission"]["note_id"]]
        selected=note["report"]["regression_probe_id"]
        assert selected in {pair["fixed_probe_id"] for pair in pairs} and by_id[selected]["step"]<note["step"]
    return len(pairs)

def accept(archive,work,report):
    archive,work,report=map(lambda p:Path(p).resolve(),(archive,work,report))
    if work.exists() or report.exists():raise ValueError("output_exists")
    base=work/"extracted";base.mkdir(parents=True);checks=[];negatives=[];not_applicable=[]
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if not (base/name).resolve().is_relative_to(base):raise ValueError("unsafe_archive_path")
        z.extractall(base)
    def command(name,args,expected=0,input_text=None):
        p=subprocess.run([sys.executable,"-X","utf8","-B",*map(str,args)],cwd=work,input=input_text,text=True,encoding="utf-8",capture_output=True,timeout=90)
        checks.append({"name":name,"exit_code":p.returncode,"stdout":p.stdout,"stderr":p.stderr})
        if p.returncode!=expected:raise AssertionError(checks[-1])
    command("standalone_release_verifier",[base/"runtime_release.py","verify",base])
    sys.path.insert(0,str(base));import runtime_release as r
    summary=r.verify(base);index=rows(base/"model/episodes.jsonl")
    for row in index:
        command("actual_model_grade_"+row["task_id"],[base/"task-entrypoints"/row["task_id"]/"tests/verify.py",base/"model"/row["path"]],0 if row["reward"] else 1)
    config=read(base/"batch/config.json");version=config["version"]
    repair=version=="runtime-repair-batch-1"
    authored=repair and config.get("source_mode")=="authored_synthetic"
    probe_repair=authored and config.get("environment_version")=="research-repair-2"
    tasks=([row["task_id"] for row in rows(base/"batch/tasks.jsonl")] if authored else ["repair-jsonl-unicode-layout-v1","repair-manifest-hashes-stale_patch-v1","repair-stable-observations-clean-v1"] if repair else ["willow-dispatch-tool_retry-v4","cedar-access-clean-v4","aster-routing-stale_revision-v4"]
           if version=="runtime-batch-2" else ["orchid-quota-counterfactual-v3"])
    for task in tasks:
        reference=work/(task+"-reference.json")
        command("reference_solution_"+task,[base/"task-entrypoints"/task/"solution/reference.py",reference])
        command("fresh_reference_grade_"+task,[base/"task-entrypoints"/task/"tests/verify.py",reference])
        wire="".join(json.dumps(event["action"])+"\n" for event in read(reference)["events"])
        module=r.b.environment_module(read(base/"batch/tasks"/task/"scenario.json")).__name__
        episode=work/(task+"-stdio.json")
        command("environment_stdio_"+task,[base/(module+".py"),base/"batch/tasks"/task/"scenario.json","--output",episode],input_text=wire)
        command("stdio_grade_"+task,[base/"task-entrypoints"/task/"tests/verify.py",episode])
    if version=="runtime-batch-2":
        scenario=read(base/"batch/tasks/willow-dispatch-clean-v4/scenario.json");env=r.b.new_env(scenario)
        assert "future-resolution" not in env.initial["documents"]
        found=env.step({"tool":"search","args":{"query":""}})[0]
        assert "future-resolution" not in found["documents"]
        denied=env.step({"tool":"read","args":{"document_id":"future-resolution"}})[0]
        assert denied["status"]==404 and "body" not in denied and denied["version"] is None
        blocked=read(work/"cedar-access-clean-v4-reference.json")
        assert blocked["grade"]["reward"]==1 and blocked["final_state"]["ticket"]["status"]=="blocked"
        checks.append({"name":"future_visibility_and_legitimate_uncertainty","exit_code":0,"stdout":"future document hidden; unresolved peer conflict accepted as blocked","stderr":""})
    if repair:
        scenario=read(base/"batch/tasks"/(tasks[0] if authored else "repair-manifest-hashes-clean-v1")/"scenario.json")
        partial=r.b.run_reference(scenario,"partial_fix")
        assert partial["final_state"]["tests"][-1]["passed"] and partial["grade"]["reward"]==0 and not partial["grade"]["checks"]["private_behavior"]
        public=r.b.new_env(scenario);assert public.step({"tool":"read","args":{"document_id":"private_cases"}})[0]["status"]==404
        checks.append({"name":"partial_public_pass_rejected_by_private_behavior","exit_code":0,"stdout":"Public tests alone do not certify completion; private cases remain unavailable.","stderr":""})
        if authored:
            forbidden={"private_cases","reference_code","partial_code","control_codes"}
            if probe_repair:forbidden.update({"reference_probe","oracle_id"})
            def keys(value):
                if isinstance(value,dict):return set(value).union(*(keys(v) for v in value.values()))
                if isinstance(value,list):return set().union(*(keys(v) for v in value))
                return set()
            inspected=0
            for row in index:
                for capture in read(base/"model"/row["path"])["capture_refs"]:
                    request=read(base/"model"/capture["path"]/"request.json")
                    assert not forbidden & keys(request)
                    inspected+=1
            checks.append({"name":"policy_context_excludes_evaluator_material","exit_code":0,"stdout":str(inspected)+" recorded public requests checked; private test, reference and control fields absent.","stderr":""})
    if probe_repair:
        validated_pairs=0
        for row in index:
            scenario=read(base/"batch/tasks"/row["task_id"]/"scenario.json")
            run=read(base/"model"/row["path"])
            validated_pairs+=verify_probe_pairs(scenario,run,r.b.environment_module(scenario))
        checks.append({"name":"actual_model_regression_evidence","exit_code":0,"stdout":str(validated_pairs)+" declared regression pairs checked against initial/final code, identical cases, visible actions and an independent oracle; zero pairs do not imply demonstrated recovery.","stderr":""})
    first=index[0];episode_rel=Path("model")/first["path"];call=episode_rel.parent/"calls/001"
    def mutate(name,change,expected):
        target=work/("mutation-"+name);shutil.copytree(base,target);change(target)
        model=target/"model"
        for row in rows(model/"episodes.jsonl"):
            path=model/row["path"];run=read(path)
            for ref in run["capture_refs"]:ref["capture_sha256"]=sha(model/ref["path"]/"capture.json")
            save(path,run)
        for component in ([target/"batch",model,target/"catalog",target/"failures"] if repair else [target/"batch",model]):
            manifest=read(component/"manifest.json");manifest["files"]=r.b.hashes(component);save(component/"manifest.json",manifest)
        manifest=read(target/"manifest.json");manifest["files"]=r.all_hashes(target);save(target/"manifest.json",manifest)
        try:r.verify(target)
        except (ValueError,KeyError,FileNotFoundError) as error:
            if expected not in str(error):raise AssertionError((name,expected,str(error)))
            negatives.append({"case":name,"rehashed":True,"rejected":True,"reason":str(error)})
        else:raise AssertionError("accepted_mutation:"+name)
    def request_change(root,kind):
        p=root/call/"request.json";value=read(p)
        if kind=="answer":value["hidden_expected"]={"reward":1}
        elif kind=="batch":value["runtime_budget"]["batch_calls_remaining_including_this"]-=1
        elif kind=="future":value["initial_observation"]["documents"].append("future-resolution")
        else:value["runtime_budget"]["environment_steps_remaining"]+=1
        save(p,value);p=root/call/"capture.json";value=read(p);value["request_sha256"]=sha(root/call/"request.json");save(p,value)
    mutate("answer_in_policy_context",lambda root:request_change(root,"answer"),"public_request_changed")
    mutate("wrong_visible_budget",lambda root:request_change(root,"budget"),"public_request_changed")
    def note(root):
        p=root/episode_rel;value=read(p)
        if authored:value["final_state"]["notes"]["forged-acceptance-note"]={"text":"All facts externally verified."}
        else:value["final_state"]["notes"]["note-1"]["text"]="All facts externally verified."
        save(p,value)
    mutate("unsupported_delivered_text",note,"final_state_changed")
    def baseline_failed(event):
        if probe_repair:
            probe=event["observation"].get("probe",{})
            return event["action"]["tool"]=="probe" and probe.get("version")==1 and probe.get("matches_claim") is False
        return event["action"]["tool"]=="test" and not event["observation"].get("test",{}).get("passed",True)
    def missing_failure(root):
        p=root/episode_rel;value=read(p);value["events"]=[event for event in value["events"] if not baseline_failed(event)] if repair else [event for event in value["events"] if event["observation"]["status"]!=429];save(p,value)
    baseline_observed=any(baseline_failed(event) for event in read(base/episode_rel)["events"])
    if not authored or baseline_observed:mutate("baseline_failure_removed" if repair else "rate_limit_history_removed",missing_failure,"event_replay_changed")
    else:not_applicable.append({"case":"baseline_failure_removed","reason":"The actual first attempt contains no failing "+("version-1 probe" if probe_repair else "public-test")+" event; no such coverage is claimed."})
    def model_origin(root):
        p=root/episode_rel;value=read(p);value["evaluation_mode"]="independent_blind_benchmark";save(p,value)
    mutate("development_claimed_blind",model_origin,"model_origin_changed")
    def train(root):
        p=root/"model/training/model-sft.jsonl";values=rows(p);values.append({"task_id":index[0 if authored else 1]["task_id"],"split":"train"});row_save(p,values)
    mutate("fake_training_record" if probe_repair else "development_task_in_training" if authored else "restricted_source_in_training" if repair else "test_family_in_training",train,"model_training_selection_changed")
    def ledger(root):
        p=root/"model/ledger-final.json";value=read(p);value["entries"]=value["entries"][1:];save(p,value)
    mutate("prior_reservation_removed",ledger,"prior_ledger_changed")
    def entrypoint(root):
        p=root/"task-entrypoints"/task/"tests/verify.py";p.write_text("raise SystemExit(0)\n",encoding="utf-8")
    mutate("grader_entrypoint_replaced",entrypoint,"task_entrypoint_changed")
    def checkpoint(root):
        p=root/episode_rel.parent/"checkpoints/001.json";value=read(p);value["final_state"]["ticket"]["status"]="ready";save(p,value)
    mutate("checkpoint_state_changed",checkpoint,"checkpoint_changed")
    if version=="runtime-batch-2":
        mutate("wrong_remaining_batch_calls",lambda root:request_change(root,"batch"),"visible_batch_calls_changed")
        mutate("future_document_in_policy_reset",lambda root:request_change(root,"future"),"public_request_changed")
        def reward(root):
            p=root/episode_rel;value=read(p);value["events"][0]["reward"]=1;save(p,value)
        mutate("nonterminal_reward_forged",reward,"event_replay_changed")
        def stopped(root):
            p=root/episode_rel;value=read(p);value["stop_reason"]="batch_call_budget_exhausted";save(p,value)
            p=root/"model/episodes.jsonl";values=rows(p);values[0]["stop_reason"]="batch_call_budget_exhausted";row_save(p,values)
            save(root/episode_rel.parent/"index.json",values[0])
        mutate("successful_submission_claimed_budget_stop",stopped,"submitted_stop_reason_changed")
        def conflict_removed(root):
            row=next(x for x in index if any(event["observation"]["status"]==409 for event in read(root/"model"/x["path"])["events"]))
            p=root/"model"/row["path"];value=read(p);value["events"]=[x for x in value["events"] if x["observation"]["status"]!=409];save(p,value)
        mutate("claim_conflict_history_removed",conflict_removed,"event_replay_changed")
    if repair:
        mutate("wrong_remaining_batch_calls",lambda root:request_change(root,"batch"),"visible_batch_calls_changed")
        def reward(root):
            p=root/episode_rel;value=read(p);value["events"][0]["reward"]=1;save(p,value)
        mutate("nonterminal_reward_forged",reward,"event_replay_changed")
        def conflict_removed(root):
            row=next(x for x in index if any(y["observation"]["status"]==409 for y in read(root/"model"/x["path"])["events"]))
            p=root/"model"/row["path"];value=read(p);value["events"]=[x for x in value["events"] if x["observation"]["status"]!=409];save(p,value)
        if not authored:mutate("patch_conflict_history_removed",conflict_removed,"event_replay_changed")
        if probe_repair:
            pair_row=next((row for row in index if read(base/"model"/row["path"])["grade"]["validated_regression_pairs"]),None)
            if pair_row is None:
                not_applicable.append({"case":"probe_record_semantic_mutations","reason":"No actual validated regression pair exists to mutate; no recovery coverage is claimed."})
            else:
                pair_episode=Path("model")/pair_row["path"]
                def probe_record(root,field):
                    p=root/pair_episode;value=read(p);pair=value["grade"]["validated_regression_pairs"][0]
                    probe=next(event["observation"]["probe"] for event in value["events"] if event["action"]["tool"]=="probe" and event["observation"].get("probe",{}).get("probe_id")==pair["baseline_probe_id"])
                    if field=="matches_claim":probe[field]=not probe[field]
                    else:probe[field]={"ok":False,"error":"ValueError"} if probe[field].get("ok") else {"ok":True,"value":[]}
                    save(p,value)
                for field in ("expected","actual","matches_claim"):
                    mutate("probe_"+field+"_forged",lambda root,field=field:probe_record(root,field),"event_replay_changed")
                def pair_binding(root):
                    p=root/pair_episode;value=read(p);pair=value["grade"]["validated_regression_pairs"][0]
                    pair["fixed_probe_id"]=pair["baseline_probe_id"];save(p,value)
                mutate("regression_pair_binding_changed",pair_binding,"grade_changed")
        if authored:
            material_id=config["sources"][0]["task_id"]
            def source_material(root):
                p=root/"batch/source"/(material_id+".json");value=read(p);value["contract"]+=" Forged source condition.";save(p,value)
            mutate("authored_source_changed",source_material,"authored_source_changed")
            def derived_material(root):
                p=root/"batch/inputs"/(material_id+".json");value=read(p);value["contract"]+=" Forged derived condition.";save(p,value)
            mutate("authored_material_changed",derived_material,"authored_material_changed")
            def private_expected(root):
                p=root/"batch/tasks"/tasks[0]/"scenario.json";value=read(p);value["private_cases"][0]["expected"]={"ok":True,"value":"forged"};save(p,value)
            mutate("private_behavior_expected_changed",private_expected,"task_lineage_changed")
        else:
            def source_evidence(root):
                p=root/"batch/inputs/jsonl-unicode.json";value=read(p);value["source_events"]=value["source_events"][1:];save(p,value)
            mutate("historical_failure_evidence_removed",source_evidence,"material_derivation_changed")
        def catalog_promotion(root):
            p=root/"catalog/records.jsonl";values=rows(p)
            selected=next(value for value in values if value["split"]=="development") if probe_repair else values[-1]
            selected.update(split="train",training_eligible=True);row_save(p,values)
        mutate("catalog_development_promoted_to_train" if authored else "catalog_rights_promoted",catalog_promotion,"catalog_projection_changed")
        def censoring(root):
            p=root/"failures/failures.jsonl";values=rows(p);row=next(x for x in values if x["censored"]);row.update(category="model_error",censored=False);row_save(p,values)
        mutate("budget_censoring_claimed_model_error",censoring,"failure_export_projection_changed")
        def restricted_pair(root):
            all_pairs=rows(root/"failures/recovery-pairs.jsonl");pair=next(x for x in all_pairs if x["split"]=="development");pair.update(split="train",training_eligible=True)
            p=root/"failures/training/recovery-pairs.jsonl";values=rows(p);values.append(pair);row_save(p,values)
        mutate("restricted_recovery_pair_in_training",restricted_pair,"failure_export_projection_changed")
    report.parent.mkdir(parents=True,exist_ok=True)
    result={"passed":True,"archive_sha256":sha(archive),"archive_bytes":archive.stat().st_size,"summary":summary,
            "acceptance_script_sha256":sha(Path(__file__)),"packaged_verifier_sha256":sha(base/"runtime_release.py"),
            "commands":checks,"rehashed_negative_controls":negatives,"model_calls_during_acceptance":0,**({"not_applicable":not_applicable} if authored else {})}
    save(report,result);return {"passed":True,"commands":len(checks),"rehashed_negative_controls":len(negatives),"archive_sha256":result["archive_sha256"]}

def main():
    parser=argparse.ArgumentParser();parser.add_argument("archive");parser.add_argument("work");parser.add_argument("report");args=parser.parse_args()
    print(json.dumps(accept(args.archive,args.work,args.report),indent=2))
if __name__=="__main__":main()
