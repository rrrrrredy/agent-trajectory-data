"""Public-observation transitions and replay-bound eval selection for workspace tasks."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import runtime_batch as b, runtime_collect as c
from research_env_v3 import check,equal

def derive(batch,model,index=None):
    batch,model=Path(batch),Path(model);tasks={x["task_id"]:x for x in b.lines(batch/"tasks.jsonl")};transitions=[];episodes=[];evaluation=[]
    for row in (b.lines(model/"episodes.jsonl") if index is None else index):
        task=tasks[row["task_id"]];scenario=b.read(batch/task["scenario"]);run=b.read(model/row["path"]);b.verify_episode(scenario,run)
        eligible=row["split"]=="train" and scenario["rights"].get("training_eligible") is True
        episode_hash=b.sha((model/row["path"]).read_bytes());observed=run["initial_observation"]
        refs=iter(run["capture_refs"]);completed=[]
        for ref in refs:
            cap=b.read(model/ref["path"]/"capture.json")
            if cap["status"]=="completed":completed.append((ref,cap))
        check(len(completed)==len(run["events"]),"transition_capture_count_changed")
        for event,(ref,cap) in zip(run["events"],completed):
            transitions.append({"episode_id":row["task_id"],"step":event["step"],"split":row["split"],"origin":scenario["origin"],"actor_kind":"isolated_model_cli","rights":scenario["rights"],"training_eligible":eligible,"observation":observed,"action":event["action"],"next_observation":event["observation"],"reward":event["reward"],"terminated":event["terminated"],"truncated":event["truncated"],"collection_stop_reason":run["stop_reason"] if event["step"]==len(run["events"]) else None,"recording_last_transition":event["step"]==len(run["events"]),"decision_summary":cap["decision_summary"],"full_public_history_path":"model/"+ref["path"]+"/request.json","capture_sha256":ref["capture_sha256"],"original_episode_sha256":episode_hash})
            observed=event["observation"]
        episodes.append({"task_id":row["task_id"],"family_id":row["family_id"],"split":row["split"],"origin":scenario["origin"],"rights":scenario["rights"],"reward":row["reward"],"complete":row["complete"],"stop_reason":row["stop_reason"],"terminal_status":run["final_state"]["ticket"]["status"],"episode_path":"model/"+row["path"],"episode_sha256":episode_hash,"transition_count":len(run["events"]),"training_transition_eligible":eligible,"positive_demonstration_eligible":c.training_eligible(row,scenario),"deliverable_paths":["model/episodes/"+row["task_id"]+"/deliverables/"+x for x in scenario["documents"]["brief"]["body"]["artifact_ids"]]})
        if row["split"]=="test":evaluation.append({"task_id":row["task_id"],"family_id":row["family_id"],"scenario_path":"batch/"+task["scenario"],"scenario_sha256":b.sha((batch/task["scenario"]).read_bytes()),"environment_version":scenario["version"],"max_steps":scenario["max_steps"],"seed":0,"grader_entrypoint":"task-entrypoints/"+row["task_id"]+"/tests/verify.py","policy_surface":"reset/step observations only; scenario, solutions and grader stay evaluator-side"})
    return episodes,transitions,evaluation

def summary(episodes,transitions,evaluation):
    eligible=[x for x in episodes if x["positive_demonstration_eligible"]]
    return {"episodes":len(episodes),"verified_ready_episodes":sum(x["reward"]==1 and x["terminal_status"]=="ready" for x in episodes),"verified_blocked_episodes":sum(x["reward"]==1 and x["terminal_status"]=="blocked" for x in episodes),"transitions":len(transitions),"training_transitions":sum(x["training_eligible"] for x in transitions),"positive_demonstrations":len(eligible),"positive_train_families":sorted({x["family_id"] for x in eligible}),"eval_tasks":len(evaluation),"contract":"Partially observable reset/step task environments with terminal reward. Transitions contain public observations; request paths retain full public history. Evaluator snapshots are excluded. Failed train episodes may supply RL transitions but not positive SFT demonstrations. Collection stops remain separate from environment terminal flags. Correct blocked handling is counted separately from ready deliverables. Shared environment templates limit independence claims."}

def build(batch,model,output):
    root=Path(output);check(not root.exists(),"output_exists");b.verify(batch);c.verify(batch,model)
    episodes,transitions,evaluation=derive(batch,model)
    b.put(root/"binding.json",{"batch_manifest_sha256":b.sha((Path(batch)/"manifest.json").read_bytes()),"model_manifest_sha256":b.sha((Path(model)/"manifest.json").read_bytes())})
    b.put_lines(root/"episodes.jsonl",episodes);b.put_lines(root/"transitions.jsonl",transitions);b.put_lines(root/"training/rl-transitions.jsonl",[x for x in transitions if x["training_eligible"]]);b.put(root/"evaluation.json",{"tasks":evaluation,"fixed_selection":True,"tuned_on_this_test_selection":False,"boundary":"Two tasks from one newly authored test family; this is a held-out development evaluation, not a broad blind benchmark."});b.put(root/"summary.json",summary(episodes,transitions,evaluation));b.put(root/"manifest.json",{"files":b.hashes(root)})
    return verify(root,batch,model)

def verify(root,batch,model):
    root=Path(root);check(b.read(root/"manifest.json")["files"]==b.hashes(root),"workspace_export_files_changed")
    check(b.read(root/"binding.json")=={"batch_manifest_sha256":b.sha((Path(batch)/"manifest.json").read_bytes()),"model_manifest_sha256":b.sha((Path(model)/"manifest.json").read_bytes())},"workspace_export_binding_changed")
    episodes,transitions,evaluation=derive(batch,model)
    for name,expected in [("episodes.jsonl",episodes),("transitions.jsonl",transitions),("training/rl-transitions.jsonl",[x for x in transitions if x["training_eligible"]])]:check(equal(b.lines(root/name),expected),"workspace_export_projection_changed:"+name)
    ev=b.read(root/"evaluation.json");check(ev=={"tasks":evaluation,"fixed_selection":True,"tuned_on_this_test_selection":False,"boundary":"Two tasks from one newly authored test family; this is a held-out development evaluation, not a broad blind benchmark."},"eval_selection_changed")
    result=summary(episodes,transitions,evaluation);check(result==b.read(root/"summary.json"),"workspace_export_counts_changed");return {"passed":True,**result}

def main():
    p=argparse.ArgumentParser();p.add_argument("command",choices=["build","verify"]);p.add_argument("batch");p.add_argument("model");p.add_argument("output");a=p.parse_args();print(json.dumps(build(a.batch,a.model,a.output) if a.command=="build" else verify(a.output,a.batch,a.model),indent=2))
if __name__=="__main__":main()
