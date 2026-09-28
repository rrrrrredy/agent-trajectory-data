"""Evidence-derived failure labels and observable recovery pairs; no inferred reasoning."""
from __future__ import annotations
import argparse,copy,json,re
from collections import Counter
from pathlib import Path
import runtime_batch as b
from research_env_v3 import check,digest,equal
SOURCES=[("v0.6","runtime-model-v0.6-first","agent-runtime-v0.6/curriculum/tasks.jsonl"),("v0.7","runtime-model-v0.7-recovery","agent-runtime-v0.6/curriculum/tasks.jsonl"),("v0.8","runtime-model-v0.8","runtime-batch-v0.8/tasks.jsonl"),("v0.9","runtime-model-v0.9","runtime-batch-v0.9/tasks.jsonl")]
def classify(event):
    observation=event["observation"];status=observation.get("status")
    if event["action"]["tool"]=="test" and status==200 and not observation["test"]["passed"]:
        return "expected_reproduction_failure" if observation["test"]["version"]==1 else "candidate_test_failure"
    if status in (403,404) and event["action"]["tool"] not in ("read","search"):return "policy_action_contract_error"
    return {429:"transient_tool_failure",409:"concurrent_version_conflict",403:"evidence_unavailable",404:"evidence_unavailable",400:"policy_action_contract_error",412:"policy_action_contract_error",422:"policy_action_contract_error"}.get(status)
def target(action):return (action["tool"],{k:v for k,v in action["args"].items() if k in ("document_id","doc_id","claim_id","note_id")})
def project(component,index,run,initial,rights):
    episodes=[];pairs=[];events=run["events"];goal=bool(index["reward"]==1 and index["complete"])
    base={"episode_id":component+":"+index["task_id"],"component":component,"task_id":index["task_id"],"family_id":index["family_id"],"split":index["split"],"rights":rights,"actor_kind":run["actor_kind"],"episode_goal_verified":goal,"episode_stop_reason":run.get("stop_reason")}
    for i,event in enumerate(events):
        category=classify(event)
        if category is None:continue
        fingerprint=digest({"task":index["task_id"],"step":event["step"],"action":event["action"],"observation":event["observation"]})
        row={**base,"failure_id":base["episode_id"]+":"+str(event["step"]),"event_fingerprint":fingerprint,"step":event["step"],"category":category,"action":event["action"],"observation":event["observation"],"censored":False,"resolution":None}
        later=None
        if category not in {"evidence_unavailable"}:
            for j in range(i+1,len(events)):
                candidate=events[j]
                if candidate["observation"].get("status")!=200:continue
                if category in {"expected_reproduction_failure","candidate_test_failure"}:
                    test=candidate["observation"].get("test",{})
                    if candidate["action"]["tool"]=="test" and test.get("passed") and test.get("code_sha256")!=event["observation"]["test"]["code_sha256"]:later=j;break
                elif target(candidate["action"])==target(event["action"]):later=j;break
        if later is not None:
            row["resolution"]={"step":events[later]["step"],"kind":"public_tests_passed" if event["action"]["tool"]=="test" else "tool_action_accepted","observation":events[later]["observation"],"goal_verified_separately":goal}
            pairs.append({"failure_id":row["failure_id"],"event_fingerprint":fingerprint,"task_id":index["task_id"],"split":index["split"],"rights":rights,"category":category,"context_kind":"derived_from_recorded_public_observations","context":{"initial_observation":initial,"history":[{"action":x["action"],"observation":x["observation"]} for x in events[:i+1]]},"recovery":[{"action":x["action"],"observation":x["observation"]} for x in events[i+1:later+1]],"verification":row["resolution"],"training_eligible":index["split"]=="train" and rights.get("training_eligible") is True and goal and initial is not None})
        elif category=="evidence_unavailable" and goal and run["final_state"]["ticket"]["status"]=="blocked":row["resolution"]={"kind":"legitimate_blocked","goal_verified_separately":True}
        episodes.append(row)
    reason=run.get("stop_reason")
    if reason:
        censored="budget" in reason or "limit" in reason
        category="environment_budget_truncation" if reason=="environment_step_budget_exhausted" else "external_budget_truncation" if censored else "unknown_inflight_call" if "unknown" in reason else "provider_or_transport_failure"
        episodes.append({**base,"failure_id":base["episode_id"]+":stop","event_fingerprint":digest({"episode":base["episode_id"],"stop":reason}),"step":len(events),"category":category,"action":None,"observation":{"stop_reason":reason},"censored":censored,"resolution":None})
    elif index["complete"] and not goal:
        grade=run.get("grade",run.get("outcome",{}));episodes.append({**base,"failure_id":base["episode_id"]+":terminal","event_fingerprint":digest({"episode":base["episode_id"],"grade":grade}),"step":len(events),"category":"terminal_verification_failure","action":None,"observation":{"grading":grade},"censored":False,"resolution":None})
    return episodes,pairs

def derive(root):
    root=Path(root);spec=b.read(root/"sources.json");failures=[];pairs=[]
    components={}
    for proof in b.read(root/"components.json"):
        for key in ("tasks","index","model_manifest","task_manifest"):
            check(b.sha(b.local(root,proof[key]).read_bytes())==proof[key+"_sha256"],"failure_proof_changed")
        tasks=b.lines(root/proof["tasks"]);index=b.lines(root/proof["index"]);model_manifest=b.read(root/proof["model_manifest"]);task_manifest=b.read(root/proof["task_manifest"])
        check(task_manifest["files"][proof["task_index_path"]]==proof["tasks_sha256"],"failure_rights_source_changed")
        check(model_manifest["files"]["episodes.jsonl"]==proof["index_sha256"],"failure_episode_index_changed")
        components[proof["component"]]={"tasks":{x["task_id"]:x for x in tasks},"index":{x["task_id"]:x for x in index},"manifest":model_manifest}

    for source in spec:
        raw=b.local(root,source["snapshot"]).read_bytes();check(b.sha(raw)==source["sha256"],"failure_snapshot_changed");data=json.loads(raw)
        check(b.sha(b.local(root,source["original_episode"]).read_bytes())==source["original_episode_sha256"],"original_failure_episode_changed")
        original=b.read(root/source["original_episode"]);check(equal(data["run"],original),"failure_episode_projection_changed")
        proof=components[source["component"]];tid=original["task_id"]
        check(equal(data["index"],proof["index"][tid]) and equal(data["rights"],proof["tasks"][tid]["rights"]),"failure_rights_or_index_changed")
        check(proof["manifest"]["files"][data["index"]["path"]]==source["original_episode_sha256"],"failure_original_binding_changed")
        if "initial_observation" in original:check(equal(data["initial_observation"],original["initial_observation"]),"failure_context_changed")
        else:
            request_raw=b.local(root,source["initial_request"]).read_bytes();check(b.sha(request_raw)==proof["manifest"]["files"][source["initial_request_path"]],"failure_context_source_changed")
            check(equal(data["initial_observation"],json.loads(request_raw)["initial_observation"]),"failure_context_changed")
        grade=original.get("grade") or original.get("outcome")
        check(data["index"]["task_id"]==original["task_id"] and data["index"]["complete"]==original["complete"],"failure_label_binding_changed")
        check((not original["complete"] and data["index"]["reward"]==0 and grade is None) or isinstance(grade,dict) and data["index"]["reward"]==grade.get("reward"),"failure_grade_binding_changed")
        a,z=project(source["component"],data["index"],original,data["initial_observation"],data["rights"]);failures.extend(a);pairs.extend(z)
    eligible=[];seen=set()
    for pair in pairs:
        if pair["training_eligible"] and pair["event_fingerprint"] not in seen:eligible.append(pair);seen.add(pair["event_fingerprint"])
    return failures,pairs,eligible

def summary(failures,pairs,eligible):return {"failure_records":len(failures),"unique_observed_failures":len({x["event_fingerprint"] for x in failures}),"categories":dict(Counter(x["category"] for x in failures)),"recovery_pairs":len(pairs),"trainable_recovery_pairs":len(eligible),"excluded_recovery_pairs":len(pairs)-len(eligible),"boundary":"Observed tool acceptance or public tests plus separately recorded terminal grade; not a judgment of hidden reasoning or unrestricted real-world correctness. Reused failure prefixes are fingerprinted, not new independent failures."}
def build(repo,batch,model,output):
    repo,batch,model,root=map(Path,(repo,batch,model,output));check(not root.exists(),"output_exists");sources=[];components=[]
    current=b.read(batch/"config.json")["dataset_version"];version=lambda value:tuple(map(int,value.split(".")))
    history=list(SOURCES[:2])
    for candidate in sorted((repo/"data").glob("runtime-model-v*")):
        match=re.fullmatch(r"runtime-model-v([0-9]+\.[0-9]+)",candidate.name)
        if match and candidate.is_dir() and (candidate/"manifest.json").exists() and version(match[1])<version(current):
            history.append(("v"+match[1],candidate.name,"runtime-batch-v"+match[1]+"/tasks.jsonl"))
    for component,folder,index_path in history+[("v"+current,None,None)]:
        source=model if folder is None else repo/"data"/folder;tasks=b.lines(batch/"tasks.jsonl") if index_path is None else b.lines(repo/"data"/index_path);tasks={x["task_id"]:x for x in tasks}
        task_root=batch if index_path is None else repo/"data"/Path(index_path).parts[0]
        task_index="tasks.jsonl" if index_path is None else Path(*Path(index_path).parts[1:]).as_posix()
        proof={"component":component,"task_index_path":task_index}
        for key,origin in [("tasks",task_root/task_index),("index",source/"episodes.jsonl"),("model_manifest",source/"manifest.json"),("task_manifest",task_root/"manifest.json")]:
            name="proofs/"+component+"-"+key+".json";raw=origin.read_bytes();b.write(root/name,raw);proof[key]=name;proof[key+"_sha256"]=b.sha(raw)
        components.append(proof)
        for index in b.lines(source/"episodes.jsonl"):
            path=b.local(source,index["path"]);raw=path.read_bytes();run=json.loads(raw);initial=run.get("initial_observation")
            if initial is None and run.get("capture_refs"):
                request=b.read(b.local(source,run["capture_refs"][0]["path"])/"request.json");initial=request.get("initial_observation")
            name=component+"-"+index["task_id"];snapshot="snapshots/"+name+".json";original="episodes/"+name+".json"
            data={"run":run,"index":index,"initial_observation":initial,"rights":tasks[index["task_id"]]["rights"]};b.put(root/snapshot,data);b.write(root/original,raw)
            entry={"component":component,"snapshot":snapshot,"sha256":b.sha((root/snapshot).read_bytes()),"original_episode":original,"original_episode_sha256":b.sha(raw)}
            if "initial_observation" not in run:
                request_path=run["capture_refs"][0]["path"]+"/request.json";entry.update(initial_request="proofs/"+name+"-request.json",initial_request_path=request_path);b.write(root/entry["initial_request"],b.local(source,request_path).read_bytes())
            sources.append(entry)
    b.put(root/"components.json",components);b.put(root/"sources.json",sources);failures,pairs,eligible=derive(root)
    b.put_lines(root/"failures.jsonl",failures);b.put_lines(root/"recovery-pairs.jsonl",pairs);b.put_lines(root/"training/recovery-pairs.jsonl",eligible);b.put(root/"summary.json",summary(failures,pairs,eligible));b.put(root/"manifest.json",{"files":b.hashes(root)})
    return verify(root)
def verify(root):
    root=Path(root);check(b.read(root/"manifest.json")["files"]==b.hashes(root),"failure_export_files_changed");failures,pairs,eligible=derive(root)
    for name,expected in [("failures.jsonl",failures),("recovery-pairs.jsonl",pairs),("training/recovery-pairs.jsonl",eligible)]:check(equal(b.lines(root/name),expected),"failure_export_projection_changed:"+name)
    result=summary(failures,pairs,eligible);check(result==b.read(root/"summary.json"),"failure_export_counts_changed");return {"passed":True,**result}
def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest="command",required=True);x=s.add_parser("build");[x.add_argument(k) for k in ("repo","batch","model","output")];s.add_parser("verify").add_argument("root");a=p.parse_args();print(json.dumps(build(a.repo,a.batch,a.model,a.output) if a.command=="build" else verify(a.root),indent=2))
if __name__=="__main__":main()
