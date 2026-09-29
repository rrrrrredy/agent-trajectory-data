"""Offline acceptance of an extracted runtime archive, including rehashed mutations."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,shutil,subprocess,sys,zipfile

def read(path):return json.loads(Path(path).read_bytes())
def save(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n",encoding="utf-8",newline="\n")
def rows(path):return [json.loads(x) for x in Path(path).read_bytes().split(b"\n") if x.strip()]
def row_save(path,values):Path(path).write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in values),encoding="utf-8")
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def accept(archive,work,report):
    archive,work,report=map(lambda p:Path(p).resolve(),(archive,work,report))
    if work.exists() or report.exists():raise ValueError("output_exists")
    base=work/"extracted";base.mkdir(parents=True);checks=[];negatives=[]
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
    version=read(base/"batch/config.json")["version"]
    repair=version=="runtime-repair-batch-1"
    workspace=version=="runtime-workspace-batch-1"
    if not workspace:raise ValueError("workspace_release_required")
    tasks=(["repair-jsonl-unicode-layout-v1","repair-manifest-hashes-stale_patch-v1","repair-stable-observations-clean-v1"] if repair else ["willow-dispatch-tool_retry-v4","cedar-access-clean-v4","aster-routing-stale_revision-v4"]
           if version=="runtime-batch-2" else ["orchid-quota-counterfactual-v3"])
    tasks=["archive-support-withheld_evidence-w1","summit-capacity-source_refresh-w1","mosaic-coverage-uncertain_applied-w1","rivet-routing-uncertain_not_applied-w1"]
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
        scenario=read(base/"batch/tasks/repair-manifest-hashes-clean-v1/scenario.json")
        partial=r.b.run_reference(scenario,"partial_fix")
        assert partial["final_state"]["tests"][-1]["passed"] and partial["grade"]["reward"]==0 and not partial["grade"]["checks"]["private_behavior"]
        public=r.b.new_env(scenario);assert public.step({"tool":"read","args":{"document_id":"private_cases"}})[0]["status"]==404
        checks.append({"name":"partial_public_pass_rejected_by_private_behavior","exit_code":0,"stdout":"Public tests alone do not certify completion; private cases remain unavailable.","stderr":""})
    wrong=r.b.run_reference(read(base/"batch/tasks/delta-quality-clean-w1/scenario.json"),"wrong_result")
    assert wrong["final_state"]["validations"][-1]["passed"] and wrong["grade"]["reward"]==0
    assert not wrong["grade"]["checks"]["correct_content"]
    checks.append({"name":"public_consistency_is_not_research_correctness","exit_code":0,"stdout":"Consistent artifacts with wrong results are rejected by terminal evaluation.","stderr":""})
    first=index[0];episode_rel=Path("model")/first["path"];call=episode_rel.parent/"calls/001"
    def mutate(name,change,expected):
        target=work/("mutation-"+name);shutil.copytree(base,target);change(target)
        model=target/"model"
        for row in rows(model/"episodes.jsonl"):
            path=model/row["path"];run=read(path)
            for ref in run["capture_refs"]:ref["capture_sha256"]=sha(model/ref["path"]/"capture.json")
            save(path,run)
        continuation=model/"continuation.json"
        if continuation.exists():
            receipt=read(continuation)
            # Rehash the declared historical files without repairing omitted baseline keys.
            receipt["baseline_files"]={name:sha(model/name) for name in receipt["baseline_files"]}
            save(continuation,receipt)
            for started in model.glob("episodes/*/calls/*/started.json"):
                if started.relative_to(model).as_posix() not in receipt["baseline_files"]:
                    value=read(started);value["continuation_sha256"]=sha(continuation);save(started,value)
        for component in ([target/"batch",model,target/"catalog",target/"failures",target/"exports"] if workspace else [target/"batch",model,target/"catalog",target/"failures"] if repair else [target/"batch",model]):
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
        p=root/episode_rel;value=read(p);value["final_state"]["notes"]["note-1"]["text"]="All facts externally verified.";save(p,value)
    mutate("unsupported_delivered_text",note,"final_state_changed")
    def missing_failure(root):
        p=root/episode_rel;value=read(p);value["events"]=[event for event in value["events"] if not (event["action"]["tool"]=="test" and not event["observation"].get("test",{}).get("passed",True))] if repair else [event for event in value["events"] if event["observation"]["status"]!=429];save(p,value)
    def uncertain_removed(root):
        row=next(x for x in index if any(y["observation"]["status"]==504 for y in read(root/"model"/x["path"])["events"]))
        p=root/"model"/row["path"];value=read(p);value["events"]=[x for x in value["events"] if x["observation"]["status"]!=504];save(p,value)
    mutate("uncertain_write_history_removed",uncertain_removed,"event_replay_changed")
    def model_origin(root):
        p=root/episode_rel;value=read(p);value["evaluation_mode"]="independent_blind_benchmark";save(p,value)
    mutate("development_claimed_blind",model_origin,"model_origin_changed")
    def train(root):
        p=root/"model/training/model-sft.jsonl";values=rows(p);values.append({"task_id":index[1]["task_id"],"split":"train"});row_save(p,values)
    mutate("restricted_source_in_training" if repair else "test_family_in_training",train,"model_training_selection_changed")
    def ledger(root):
        p=root/"model/ledger-final.json";value=read(p);value["entries"]=value["entries"][1:];save(p,value)
    mutate("prior_reservation_removed",ledger,"prior_ledger_changed")
    def missing_baseline(root):
        p=root/"model/continuation.json";value=read(p);del value["baseline_files"]["started.json"];save(p,value)
    mutate("continuation_original_deadline_unprotected",missing_baseline,"continuation_baseline_incomplete")
    def late_continuation(root):
        model=root/"model";receipt=read(model/"continuation.json")
        p=next(path for path in sorted(model.glob("episodes/*/calls/*/started.json"))
               if path.relative_to(model).as_posix() not in receipt["baseline_files"])
        value=read(p);value["started_epoch"]=receipt["deadline_epoch"]+1;save(p,value)
    mutate("continuation_call_after_deadline",late_continuation,"continuation_call_time_changed")
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
        mutate("patch_conflict_history_removed",conflict_removed,"event_replay_changed")
        def source_evidence(root):
            p=root/"batch/inputs/jsonl-unicode.json";value=read(p);value["source_events"]=value["source_events"][1:];save(p,value)
        mutate("historical_failure_evidence_removed",source_evidence,"material_derivation_changed")
        def catalog_promotion(root):
            p=root/"catalog/records.jsonl";values=rows(p);values[-1].update(split="train",training_eligible=True);row_save(p,values)
        mutate("catalog_rights_promoted",catalog_promotion,"catalog_projection_changed")
        def censoring(root):
            p=root/"failures/failures.jsonl";values=rows(p);row=next(x for x in values if x["censored"]);row.update(category="model_error",censored=False);row_save(p,values)
        mutate("budget_censoring_claimed_model_error",censoring,"failure_export_projection_changed")
        def restricted_pair(root):
            all_pairs=rows(root/"failures/recovery-pairs.jsonl");pair=next(x for x in all_pairs if x["split"]=="development");pair.update(split="train",training_eligible=True)
            p=root/"failures/training/recovery-pairs.jsonl";values=rows(p);values.append(pair);row_save(p,values)
        mutate("restricted_recovery_pair_in_training",restricted_pair,"failure_export_projection_changed")
    mutate("wrong_remaining_batch_calls",lambda root:request_change(root,"batch"),"visible_batch_calls_changed")
    def transition(root):
        p=root/"exports/transitions.jsonl";values=rows(p);values[0]["reward"]=1;row_save(p,values)
    mutate("transition_reward_forged",transition,"workspace_export_projection_changed")
    def delivered(root):
        p=root/episode_rel.parent/"deliverables/report.md";p.write_text("Unsupported final artifact",encoding="utf-8")
    mutate("delivered_report_forged",delivered,"delivered_artifact_changed")
    def archived_source(root):
        p=root/"batch/inputs/archive-support.json";value=read(p);value["source_binding"]["line"]+=1;save(p,value)
    mutate("source_line_detached",archived_source,"archived_material_derivation_changed")
    def source_conflict(root):
        row=next(x for x in index if any(y["observation"].get("error")=="evidence_revision_conflict" for y in read(root/"model"/x["path"])["events"]))
        p=root/"model"/row["path"];value=read(p);value["events"]=[x for x in value["events"] if x["observation"].get("error")!="evidence_revision_conflict"];save(p,value)
    mutate("source_refresh_history_removed",source_conflict,"event_replay_changed")
    def catalog_promotion(root):
        p=root/"catalog/records.jsonl";values=rows(p);values[-1].update(split="train",training_eligible=True);row_save(p,values)
    mutate("catalog_rights_promoted",catalog_promotion,"catalog_projection_changed")
    def train_transition(root):
        values=rows(root/"exports/transitions.jsonl");row=next(x for x in values if x["split"]=="test");row.update(split="train",training_eligible=True)
        p=root/"exports/training/rl-transitions.jsonl";values=rows(p);values.append(row);row_save(p,values)
    mutate("test_transition_in_training",train_transition,"workspace_export_projection_changed")
    def ambiguous_resolution(root):
        p=root/"failures/failures.jsonl";values=rows(p);row=next(x for x in values if x["category"]=="uncertain_write_outcome");row["resolution"]={"kind":"assumed_success"};row_save(p,values)
    mutate("uncertain_write_assumed_success",ambiguous_resolution,"failure_export_projection_changed")
    report.parent.mkdir(parents=True,exist_ok=True)
    result={"passed":True,"archive_sha256":sha(archive),"archive_bytes":archive.stat().st_size,"summary":summary,
            "acceptance_script_sha256":sha(Path(__file__)),"packaged_verifier_sha256":sha(base/"runtime_release.py"),
            "commands":checks,"rehashed_negative_controls":negatives,"model_calls_during_acceptance":0}
    save(report,result);return {"passed":True,"commands":len(checks),"rehashed_negative_controls":len(negatives),"archive_sha256":result["archive_sha256"]}

def main():
    parser=argparse.ArgumentParser();parser.add_argument("archive");parser.add_argument("work");parser.add_argument("report");args=parser.parse_args()
    print(json.dumps(accept(args.archive,args.work,args.report),indent=2))
if __name__=="__main__":main()
