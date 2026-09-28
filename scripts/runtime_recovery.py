"""Resume frozen model attempts with a visible, environment-aligned runtime contract."""
from __future__ import annotations
import argparse,copy,importlib.util,json,shutil,sys,time,zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE=HERE/"model_rollout.py"
if not BASE.exists():BASE=HERE/"prior/verify_runtime.py"
spec=importlib.util.spec_from_file_location("runtime_v06",BASE)
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
c,b,rd,check=v.c,v.b,v.rd,v.check
CONTRACT={
 "search":"Literal case-insensitive substring matching over title and optional search_text. Multiple words are not split or ranked. An empty query lists currently accessible documents.",
 "evidence_ids":"For write_note and submit, use document_id values from search/read, not receipt_id values such as read-3. The host binds the document IDs to their actual read receipts.",
 "lifecycle":"This is a continuation: the preceding actions and their effects already happened. Do not reset or repeat completed work. A successful update_ticket does not finish the task; submit is the terminal action.",
 "version_conflict":"A 409 requires reading the current ticket version before a version-conditional update.",
 "scope":"Use only the supplied observations. No grading answers, reference actions or private environment state are provided."
}
def parents(root):
    tasks={t["task_id"]:t for t in c.lines(root/"curriculum/tasks.jsonl")}
    indices=c.lines(root/"rollouts/episodes.jsonl")
    return tasks,indices
def restore(scenario,prefix):
    b.verify_record(scenario,prefix);check(not prefix["complete"],"parent_already_terminal")
    env=b.BusinessEnv(scenario);initial,_=env.reset(prefix["seed"])
    for event in prefix["events"]:env.step(event["action"])
    check(env.snapshot()==prefix["final_state"],"checkpoint_restore_changed")
    return env,initial
def reference_continuation(env):
    """Offline preflight control; keeps the existing episode and never becomes model data."""
    def act(tool,**args):return env.step({"tool":tool,"args":args})[0]
    ticket=act("read_ticket")["ticket"]
    act("search",query="")
    observed={}
    for key in ("policy","handoff","claims","sources"):
        observation=act("read",document_id=key)
        while observation["status"]==429:observation=act("read",document_id=key)
        observed[key]=observation
    source=observed["sources"];missing=[];issues=[]
    if source["status"]!=200:status="blocked";missing=["sources"]
    else:
        ids={row["source_id"] for row in source["body"]["rows"]}
        issues=sorted([{"claim_id":row["claim_id"],"source_id":sid.strip()}
          for row in observed["claims"]["body"]["rows"] for sid in row["source_ids"].split("|")
          if sid.strip() and sid.strip() not in ids],key=lambda x:(x["claim_id"],x["source_id"]))
        status="needs_revision" if issues else "ready"
    evidence=list(observed)
    note=act("write_note",text="Registry links only; observed access limits and missing IDs retained.",evidence_ids=evidence)
    updated=act("update_ticket",if_version=ticket["version"],status=status,note_id=note["note_id"])
    if updated["status"]==409:
        ticket=act("read_ticket")["ticket"]
        updated=act("update_ticket",if_version=ticket["version"],status=status,note_id=note["note_id"])
    act("submit",status=status,dangling_references=issues,missing_tables=missing,
        evidence_ids=evidence,ticket_version=updated["ticket"]["version"],scope="registry_integrity_only")

def request_for(initial,events,prefix_steps,batch_remaining,seconds_remaining,config):
    used=len(events);limit=initial["budget_steps"]
    check(0<=prefix_steps<=used<limit,"invalid_remaining_step_budget")
    check(batch_remaining>=1 and seconds_remaining>0,"no_collection_budget")
    result=v.request_for(initial,events)
    result["runtime_contract"]=copy.deepcopy(CONTRACT)
    result["runtime_budget"]={
      "environment_total_steps":limit,"environment_steps_used":used,"environment_steps_remaining":limit-used,
      "parent_steps":prefix_steps,"continuation_decisions_used":used-prefix_steps,
      "batch_decisions_remaining":batch_remaining,"batch_seconds_remaining":seconds_remaining,
      "per_decision_timeout_seconds":config["max_call_seconds"],
      "stop_rule":"Run until submit or the environment step limit; no smaller per-episode collector cap."}
    return result
def validate_config(config,parent):
    tasks,indices=parents(parent)
    check(config["task_ids"]==[x["task_id"] for x in indices],"recovery_selection_changed")
    remaining=0
    for row in indices:
        scenario=c.read(parent/"curriculum"/tasks[row["task_id"]]["environment"])
        run=c.read(parent/"rollouts"/row["path"]);b.verify_record(scenario,run)
        check(not run["complete"] and run["stop_reason"]=="episode_decision_budget_exhausted","not_a_censored_parent")
        remaining+=scenario["max_steps"]-len(run["events"])
    check(config["max_new_calls"]==remaining==54,"recovery_budget_not_environment_aligned")
    check(config["monthly_model_calls"]==44+remaining==98,"recovery_monthly_limit_changed")
    check(config["model"]=="gpt-6-astra" and config["max_call_seconds"]==90 and config["max_batch_seconds"]==1200,"recovery_execution_limits_changed")
    check(config["evaluation_mode"]=="repair_validation_previously_observed_tasks","recovery_claimed_unseen")
    check(config.get("execution_authorization") in {"pending_new_batch_approval","approved_by_user"}
          and config.get("authorization_record"),"invalid_recovery_authorization_state")
    return tasks,indices
def require_recovery_approval(config,evidence):
    check(config.get("execution_authorization")=="approved_by_user" and config.get("approval_record"),
          "new_recovery_batch_approval_required")
    approval=c.read(evidence/"approval.json")
    check(config["approval_record"]["sha256"]==rd.sha((evidence/"approval.json").read_bytes()),"recovery_approval_changed")
    check(approval["status"]=="approved_by_user" and approval["maximum_additional_calls"]==config["max_new_calls"]
          and approval["monthly_limit_after"]==config["monthly_model_calls"],"recovery_approved_budget_changed")
    check(approval["request_record_sha256"]==rd.sha((evidence/"authorization.json").read_bytes())
          and approval["payload_preview_sha256"]==rd.sha((evidence/"payload-preview.json").read_bytes()),"recovery_approved_payload_changed")
    return approval

def prepare(parent,config_path,evidence,output,ledger_root):
    parent=Path(parent).resolve();output=Path(output).resolve();evidence=Path(evidence).resolve()
    v.verify_bundle(parent);config=c.read(config_path);tasks,indices=validate_config(config,parent)
    require_recovery_approval(config,evidence)
    check(not output.exists(),"output_exists")
    ledger_root=Path(ledger_root).resolve()
    check(ledger_root==HERE.parent/"data/production-current","must_use_existing_ledger")
    before=c.read(evidence/"ledger-before.json")
    current=ledger_root/"budgets"/(before["month_utc"]+".json")
    check(current.read_bytes()==(evidence/"ledger-before.json").read_bytes() and before["calls_reserved"]==44,"ledger_changed_since_repair_request")
    auth=c.read(evidence/"authorization.json")
    check(config["authorization_record"]["sha256"]==rd.sha((evidence/"authorization.json").read_bytes()),"authorization_binding_changed")
    check(auth["scope"]=="repair_and_continue_three_censored_attempts","repair_scope_changed")
    output.mkdir(parents=True);shutil.copytree(evidence,output/"execution-evidence")
    rd.put_json(output/"config.json",config);rd.put(output/"collector.py",Path(__file__).read_bytes())
    rd.put_json(output/"input-freeze.json",{"parent_manifest_sha256":rd.sha((parent/"manifest.json").read_bytes()),
       "collector_sha256":rd.sha(Path(__file__).read_bytes()),"contract_sha256":b.digest(CONTRACT)})
    previews=[]
    for row in indices:
        scenario=c.read(parent/"curriculum"/tasks[row["task_id"]]["environment"]);prefix=c.read(parent/"rollouts"/row["path"])
        env,initial=restore(scenario,prefix)
        previews.append({"task_id":row["task_id"],"parent_path":row["path"],
                        "request":request_for(initial,env.events,len(prefix["events"]),config["max_new_calls"],config["max_batch_seconds"],config)})
    rd.put_json(output/"request-preview.json",previews)
    return parent,output,ledger_root,config,tasks,indices,current
def execute(parent,config_path,evidence,output,ledger_root):
    parent,output,ledger_root,config,tasks,indices,current=prepare(parent,config_path,evidence,output,ledger_root)
    sys.path.insert(0,str(HERE.parent))
    from agentdata.pipeline import reserve_monthly
    from agentdata.providers import BudgetExceeded
    started=time.monotonic();calls=0;rows=[]
    for row in indices:
        task=tasks[row["task_id"]];scenario=c.read(parent/"curriculum"/task["environment"])
        prefix=c.read(parent/"rollouts"/row["path"]);env,initial=restore(scenario,prefix)
        folder=output/"episodes"/row["task_id"];folder.mkdir(parents=True)
        refs=[];reason=None;prefix_steps=len(prefix["events"])
        while not env.finished:
            seconds=max(0,int(config["max_batch_seconds"]-(time.monotonic()-started)))
            if calls>=config["max_new_calls"] or seconds<=0:reason="batch_budget_exhausted";break
            request=request_for(initial,env.events,prefix_steps,config["max_new_calls"]-calls,seconds,config)
            try:reserve_monthly(ledger_root,config["monthly_model_calls"],"runtime-v07-"+row["task_id"])
            except BudgetExceeded:reason="monthly_call_budget_exhausted";break
            calls+=1;path="episodes/"+row["task_id"]+"/calls/"+str(len(refs)+1).zfill(3)
            capture=v.invoke(request,output/path,config,min(seconds,config["max_call_seconds"]))
            refs.append({"path":path,"capture_sha256":rd.sha((output/path/"capture.json").read_bytes())})
            if capture["status"]!="completed":reason=capture["error"];break
            obs,reward,terminated,truncated,_=env.step(capture["action"])
            rd.put_json(folder/"checkpoint.json",{"run":b.record(env,"isolated_model_cli"),"capture_refs":refs})
            print(json.dumps({"task":row["task_id"],"new_call":calls,"total_step":len(env.events),
                "tool":capture["action"]["tool"],"status":obs.get("status"),"terminal":terminated or truncated,"reward":reward}),flush=True)
        run=b.record(env,"isolated_model_cli")
        run.update(model_identity="requested:"+config["model"],capture_refs=refs,stop_reason=reason,
             evaluation_mode=config["evaluation_mode"],origin_kind="repair_continuation",
             parent_path=row["path"],parent_sha256=rd.sha((parent/"rollouts"/row["path"]).read_bytes()),prefix_steps=prefix_steps)
        path="episodes/"+row["task_id"]+"/episode.json";rd.put_json(output/path,run)
        grade=b.verify_record(scenario,run)
        result={"task_id":row["task_id"],"family_id":task["family_id"],"split":task["split"],"path":path,
                "complete":run["complete"],"reward":grade["reward"] if run["complete"] else None,
                "new_model_calls":len(refs),"total_steps":len(env.events),"stop_reason":reason,
                "origin_kind":"repair_continuation","evaluation_mode":config["evaluation_mode"]}
        rows.append(result);rd.put_lines(output/"episodes.jsonl",rows)
    rd.put(output/"execution-evidence/ledger-after.json",current.read_bytes())
    rd.put_json(output/"manifest.json",{"version":"runtime-recovery-1","files":c.hashes(output),"calls":calls})
    return verify_recoveries(parent,output)
def verify_recoveries(parent,root):
    parent=Path(parent).resolve();root=Path(root).resolve()
    config=c.read(root/"config.json");tasks,indices=validate_config(config,parent);m=c.read(root/"manifest.json")
    check(m["files"]==c.hashes(root),"recovery_file_changed")
    freeze=c.read(root/"input-freeze.json")
    check(freeze=={"parent_manifest_sha256":rd.sha((parent/"manifest.json").read_bytes()),
       "collector_sha256":rd.sha((root/"collector.py").read_bytes()),"contract_sha256":b.digest(CONTRACT)},"recovery_freeze_changed")
    evidence=root/"execution-evidence";require_recovery_approval(config,evidence)
    auth=c.read(evidence/"authorization.json")
    check(config["authorization_record"]["sha256"]==rd.sha((evidence/"authorization.json").read_bytes())
          and auth["scope"]=="repair_and_continue_three_censored_attempts","recovery_authorization_changed")
    before=c.read(evidence/"ledger-before.json");after=c.read(evidence/"ledger-after.json")
    check(before==c.read(parent/"execution-evidence/ledger-after.json"),"recovery_prior_ledger_changed")
    check(after["reservations"][:44]==before["reservations"] and before["calls_reserved"]==44,"prior_reservations_changed")
    check(after["month_utc"]==before["month_utc"] and after["calls_reserved"]==44+m["calls"]==len(after["reservations"])<=98,"recovery_accounting_changed")
    rows=c.lines(root/"episodes.jsonl")
    check([r["task_id"] for r in rows]==config["task_ids"],"recovery_task_missing")
    parent_by_id={r["task_id"]:r for r in indices};count=0;last_seconds=config["max_batch_seconds"];threads=set()
    for cap in (parent/"rollouts/episodes").glob("*/calls/*/capture.json"):
        value=c.read(cap)
        if value["thread_id"]:threads.add(value["thread_id"])
    reservations=[]
    for row in rows:
        task=tasks[row["task_id"]];pr=parent_by_id[row["task_id"]]
        scenario=c.read(parent/"curriculum"/task["environment"]);prefix=c.read(parent/"rollouts"/pr["path"])
        run=c.read(rd.local_file(root,row["path"]));grade=b.verify_record(scenario,run)
        check(run["parent_path"]==pr["path"] and run["parent_sha256"]==rd.sha((parent/"rollouts"/pr["path"]).read_bytes()),"recovery_parent_changed")
        check(run["prefix_steps"]==len(prefix["events"]) and run["events"][:run["prefix_steps"]]==prefix["events"],"original_failure_prefix_changed")
        check(run["actor_kind"]=="isolated_model_cli" and run["model_identity"]=="requested:"+config["model"],"recovery_actor_changed")
        check(run["origin_kind"]==row["origin_kind"]=="repair_continuation"
          and run["evaluation_mode"]==row["evaluation_mode"]==config["evaluation_mode"],"recovery_claimed_independent_first_attempt")
        env,initial=restore(scenario,prefix);actions=[]
        for n,ref in enumerate(run["capture_refs"]):
            folder=rd.local_file(root,ref["path"]);cap=c.read(folder/"capture.json");request=c.read(folder/"request.json")
            check(ref["capture_sha256"]==rd.sha((folder/"capture.json").read_bytes()),"recovery_capture_changed")
            seconds=request["runtime_budget"]["batch_seconds_remaining"]
            check(type(seconds) is int and 0<seconds<=last_seconds,"recovery_time_budget_changed");last_seconds=seconds
            expected=request_for(initial,env.events,run["prefix_steps"],config["max_new_calls"]-count,seconds,config)
            check(request==expected,"recovery_observation_or_budget_changed")
            check(cap["request_sha256"]==rd.sha((folder/"request.json").read_bytes())
              and cap["visible_events_sha256"]==rd.sha((folder/"visible-events.jsonl").read_bytes()),"recovery_provider_source_changed")
            check(c.read(folder/"action.schema.json")==v.SCHEMA,"recovery_action_schema_changed")
            check(cap["model_requested"]==config["model"] and cap["model_reported"] is None
              and cap["model_identity_basis"]=="requested_configuration","recovery_model_identity_changed")
            check(cap["isolation"]=={"empty_working_directory":True,"built_in_tools_disabled":list(v.DISABLED),
              "user_config_ignored":True,"project_instructions_disabled":True},"recovery_isolation_changed")
            events=c.lines(folder/"visible-events.jsonl")
            check(not any(e.get("item",{}).get("type")=="reasoning" for e in events),"private_reasoning_in_recovery")
            if cap["status"]=="completed":
                check(cap["error"] is None and cap["exit_code"]==0,"successful_recovery_capture_has_error")
                action,summary,thread,usage=v.parsed_action(events)
                check(action==cap["action"] and summary==cap["decision_summary"] and thread==cap["thread_id"] and usage==cap["usage"],"recovery_action_not_model_sourced")
                check(thread not in threads,"recovery_context_reused");threads.add(thread)
                env.step(action);actions.append(action)
            else:
                check(cap["status"]=="failed" and cap["action"] is None and n==len(run["capture_refs"])-1
                      and run["stop_reason"]==cap["error"] and not run["complete"],"recovery_failure_hidden")
            count+=1;reservations.append("runtime-v07-"+row["task_id"])
        check(actions==[e["action"] for e in run["events"][run["prefix_steps"]:]],"recovery_actions_not_from_model")
        check(row["family_id"]==task["family_id"] and row["split"]==task["split"],"recovery_split_changed")
        check(row["complete"]==run["complete"] and row["reward"]==(grade["reward"] if run["complete"] else None),"recovery_reward_changed")
        check(row["new_model_calls"]==len(run["capture_refs"]) and row["total_steps"]==len(run["events"]),"recovery_count_changed")
        check(row["stop_reason"]==run["stop_reason"] and (run["stop_reason"] is None if run["complete"] else bool(run["stop_reason"])),"recovery_stop_reason_changed")
    check([r["run_id"] for r in after["reservations"][44:]]==reservations,"recovery_reservations_changed")
    check(count==m["calls"]<=config["max_new_calls"],"recovery_call_limit_changed")
    return {"verified":True,"recovered_episodes":len(rows),"new_model_calls":count,
            "completed":sum(r["complete"] for r in rows),"passed":sum(r["reward"]==1 for r in rows),
            "prior_first_attempts_preserved":True,"unseen_evaluation_claimed":False}
def export_training(parent,root):
    tasks,_=parents(parent);trajectories=[];decisions=[];excluded=[]
    for row in c.lines(root/"episodes.jsonl"):
        task=tasks[row["task_id"]];reasons=[]
        if task["split"]!="train":reasons.append("test_family")
        if not task["rights"]["training_eligible"]:reasons.append("diagnostic_only")
        if not row["complete"] or row["reward"]!=1:reasons.append("not_successful_complete")
        if reasons:excluded.append({"task_id":row["task_id"],"reasons":reasons});continue
        run=c.read(root/row["path"]);all_decisions=[]
        prefix=c.read(parent/"rollouts"/run["parent_path"])
        for source,refs,is_new in ((parent/"rollouts",prefix["capture_refs"],False),(root,run["capture_refs"],True)):
            for ref in refs:
                folder=source/ref["path"];events=c.lines(folder/"visible-events.jsonl")
                response=[e["item"]["text"] for e in events if e.get("type")=="item.completed" and e.get("item",{}).get("type")=="agent_message"][-1]
                request=c.read(folder/"request.json")
                sample={"task_id":row["task_id"],"family_id":row["family_id"],"split":"train","actor_kind":"isolated_model_cli",
                  "origin_kind":"repair_continuation" if is_new else "preserved_original_prefix","model_identity":"requested:gpt-6-astra",
                  "source_path":("recovery/" if is_new else "prior/rollouts/")+ref["path"],
                  "messages":[{"role":"user","content":b.stable(request)},{"role":"assistant","content":response}],
                  "rights":task["rights"]}
                all_decisions.append(sample)
                if is_new:decisions.append(sample)
        trajectories.append({"task_id":row["task_id"],"family_id":row["family_id"],"split":"train",
              "origin_kind":"repair_continuation","complete":True,"reward":1,"decisions":all_decisions})
    return trajectories,decisions,{"accepted_trajectories":len(trajectories),"sft_recovery_decisions":len(decisions),
             "excluded":excluded,"original_failed_prefix_in_trajectory":True,"sft_contains_only_new_recovery_decisions":True}
def assemble(parent,recovery,output):
    parent=Path(parent).resolve();recovery=Path(recovery).resolve();output=Path(output).resolve()
    v.verify_bundle(parent);result=verify_recoveries(parent,recovery);check(not output.exists(),"output_exists")
    output.mkdir(parents=True);shutil.copytree(parent,output/"prior");shutil.copytree(recovery,output/"recovery")
    rd.put(output/"verify_recovery.py",Path(__file__).read_bytes());rd.put(output/"LICENSE",(parent/"LICENSE").read_bytes())
    trajectories,decisions,selection=export_training(parent,recovery)
    rd.put_lines(output/"training/model-trajectories.jsonl",trajectories);rd.put_lines(output/"training/model-sft-recovery.jsonl",decisions)
    rd.put_json(output/"training/selection.json",selection)
    rd.put(output/"README.md",README.encode())
    rd.put_json(output/"manifest.json",{"version":"agent-runtime-v7","files":c.hashes(output),
          "summary":{**result,"model_training_trajectories":len(trajectories),"model_sft_recovery_decisions":len(decisions)}})
    return verify(output)
def verify(root):
    root=Path(root).resolve();m=c.read(root/"manifest.json")
    check(m["version"]=="agent-runtime-v7" and m["files"]==c.hashes(root),"recovery_bundle_changed")
    v.verify_bundle(root/"prior");result=verify_recoveries(root/"prior",root/"recovery")
    trajectories,decisions,selection=export_training(root/"prior",root/"recovery")
    check(c.lines(root/"training/model-trajectories.jsonl")==trajectories,"recovery_training_trajectories_changed")
    check(c.lines(root/"training/model-sft-recovery.jsonl")==decisions,"recovery_sft_changed")
    check(c.read(root/"training/selection.json")==selection,"recovery_exclusions_changed")
    summary={**result,"model_training_trajectories":len(trajectories),"model_sft_recovery_decisions":len(decisions)}
    check(m["summary"]==summary,"recovery_summary_changed")
    return {"files":len(m["files"]),**summary}
def pack(root,output):
    root=Path(root).resolve();output=Path(output).resolve();verify(root);check(not output.exists(),"output_exists")
    with zipfile.ZipFile(output,"x",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                info=zipfile.ZipInfo(p.relative_to(root).as_posix(),date_time=(2026,9,28,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,p.read_bytes())
    return {"bytes":output.stat().st_size,"sha256":rd.sha(output.read_bytes())}
README="""# Agent runtime recovery v0.7
Run python -X utf8 -B verify_recovery.py verify .
prior/ preserves v0.6 exactly, including its three censored first attempts.
recovery/ contains real model continuations from those checkpoints. The request now makes
remaining environment steps, actual collection limits and document-ID semantics explicit.
The environment and grader are unchanged. These are repair-validation continuations of
previously observed tasks, not new independent held-out first attempts.
training/model-trajectories.jsonl exports complete successful train-family trajectories with
every actual model request and visible response, including the original failed prefix.
training/model-sft-recovery.jsonl exports only the newly observed recovery decisions from
successful train-family trajectories. Test families remain excluded.
All scripted examples retain their separate origin labels in prior/curriculum/training/.
"""
def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="cmd",required=True)
    x=sub.add_parser("run")
    for name in ("parent","config","evidence","output","ledger-root"):x.add_argument("--"+name,required=True)
    x=sub.add_parser("verify-runs");x.add_argument("parent");x.add_argument("recovery")
    x=sub.add_parser("assemble")
    for name in ("parent","recovery","output"):x.add_argument("--"+name,required=True)
    x=sub.add_parser("verify");x.add_argument("root")
    x=sub.add_parser("pack");x.add_argument("root");x.add_argument("output")
    a=p.parse_args()
    if a.cmd=="run":result=execute(a.parent,a.config,a.evidence,a.output,a.ledger_root)
    elif a.cmd=="verify-runs":result=verify_recoveries(a.parent,a.recovery)
    elif a.cmd=="assemble":result=assemble(a.parent,a.recovery,a.output)
    elif a.cmd=="verify":result=verify(a.root)
    else:result=pack(a.root,a.output)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
