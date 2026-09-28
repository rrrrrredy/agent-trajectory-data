"""Verified exports of completed collection stages; never a complete-release claim."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import runtime_batch as b,runtime_collect as c,workspace_exports as w,failure_exports as f
from research_env_v3 import check,equal

def inspect(batch,model,count):
    batch,model=Path(batch),Path(model);config=b.read(model/"config.json");freeze=b.read(model/"input-freeze.json")
    check(0<count<=len(config["task_ids"]),"invalid_prefix_size")
    check(freeze["batch_manifest_sha256"]==b.sha((batch/"manifest.json").read_bytes()),"prefix_batch_changed")
    for name,h in freeze["source_sha256"].items():check(b.sha((model/"code"/name).read_bytes())==h,"prefix_frozen_source_changed")
    tasks={x["task_id"]:x for x in b.lines(batch/"tasks.jsonl")};index=[];failures=[];pairs=[];positive=[];decisions=[]
    files={p.as_posix() for p in (Path("config.json"),Path("input-freeze.json"),Path("started.json"))}
    files.update("code/"+name for name in freeze["source_sha256"])
    ordinal=0;threads=set();admission_order={}
    for tid in config["task_ids"][:count]:
        for path in sorted((model/"episodes"/tid/"calls").glob("*/admission.json")):admission_order[path.parent.relative_to(model).as_posix()]=len(admission_order)+1
    for tid in config["task_ids"][:count]:
        folder=model/"episodes"/tid;row=b.read(folder/"index.json");run=b.read(folder/"episode.json");scenario=b.read(batch/tasks[tid]["scenario"])
        check(row["task_id"]==tid and row["path"]=="episodes/"+tid+"/episode.json" and row["split"]==scenario["split"] and row["family_id"]==scenario["family_id"],"prefix_index_changed")
        grade=b.verify_episode(scenario,run);check(row["reward"]==grade["reward"] and row["complete"]==run["complete"] and row["model_calls"]==len(run["capture_refs"]),"prefix_grade_changed")
        env=b.new_env(scenario);public_pairs=[]
        for ref in run["capture_refs"]:
            cap=c.verify_capture(model/ref["path"],env,config);ordinal+=1
            check(ref["capture_sha256"]==b.sha((model/ref["path"]/"capture.json").read_bytes()),"prefix_capture_changed")
            request=b.read(model/ref["path"]/"request.json");check(request["runtime_budget"]["batch_calls_remaining_including_this"]==config["max_new_calls"]-admission_order[ref["path"]]+1,"prefix_budget_changed")
            if cap["status"]=="completed":
                check(cap["thread_id"] not in threads,"prefix_context_reused");threads.add(cap["thread_id"])
                env.step(cap["action"]);check(equal(b.read(folder/"checkpoints"/(str(len(env.events)).zfill(3)+".json")),b.record_env(env,"isolated_model_cli")),"prefix_checkpoint_changed")
                public_pairs.append({"request":request,"action":cap["action"],"decision_summary":cap["decision_summary"],"capture_path":ref["path"]})
        check(equal(env.events,run["events"]),"prefix_action_changed")
        check(row["stop_reason"]==run["stop_reason"],"prefix_stop_reason_changed")
        if env.terminated:check(run["stop_reason"] is None,"prefix_submitted_stop_changed")
        elif env.truncated:check(run["stop_reason"]=="environment_step_budget_exhausted","prefix_truncation_changed")
        check(row["actor_kind"]==run["actor_kind"]=="isolated_model_cli" and run["evaluation_mode"]==config["evaluation_mode"] and run["model_identity"]=="requested:"+config["model"],"prefix_origin_changed")
        for name,content in env.deliverables().items():check((folder/"deliverables"/name).read_bytes()==content.encode(),"prefix_deliverable_changed")
        index.append(row);a,z=f.project("v"+config["dataset_version"]+"-stage",row,run,run["initial_observation"],scenario["rights"]);failures.extend(a);pairs.extend(z)
        if c.training_eligible(row,scenario):
            positive.append({"task_id":tid,"family_id":row["family_id"],"actor_kind":"isolated_model_cli","pairs":public_pairs});decisions.extend({"task_id":tid,"decision":i+1,**pair} for i,pair in enumerate(public_pairs))
        files.update(p.relative_to(model).as_posix() for p in folder.rglob("*") if p.is_file())
    episodes,transitions,evaluation=w.derive(batch,model,index)
    pending=config["task_ids"][count:];result={"passed":True,"collection_complete":not pending,"release_accepted":False,"pending_task_ids":pending,"model_calls":ordinal,"admissions":len(admission_order),**w.summary(episodes,transitions,evaluation),"failures":f.summary(failures,pairs,[x for x in pairs if x["training_eligible"]])}
    exports={"episodes.jsonl":episodes,"transitions.jsonl":transitions,"training/rl-transitions.jsonl":[x for x in transitions if x["training_eligible"]],"training/model-trajectories.jsonl":positive,"training/model-sft.jsonl":decisions,"failures.jsonl":failures,"recovery-pairs.jsonl":pairs,"training/recovery-pairs.jsonl":[x for x in pairs if x["training_eligible"]]}
    proof={"batch_manifest_sha256":freeze["batch_manifest_sha256"],"completed_prefix_size":count,"model_files":{name:b.sha((model/name).read_bytes()) for name in sorted(files)}}
    return result,exports,proof

def build(batch,model,output,count):
    root=Path(output);check(not root.exists(),"output_exists");b.verify(batch);result,exports,proof=inspect(batch,model,count)
    for name,rows in exports.items():b.put_lines(root/name,rows)
    b.put(root/"summary.json",result);b.put(root/"proof.json",proof);b.put(root/"manifest.json",{"files":b.hashes(root)})
    return verify(batch,model,root)

def verify(batch,model,root):
    root=Path(root);check(b.read(root/"manifest.json")["files"]==b.hashes(root),"prefix_export_files_changed")
    result,exports,proof=inspect(batch,model,b.read(root/"proof.json")["completed_prefix_size"])
    check(equal(proof,b.read(root/"proof.json")),"prefix_source_files_changed");check(equal(result,b.read(root/"summary.json")),"prefix_counts_changed")
    for name,expected in exports.items():check(equal(expected,b.lines(root/name)),"prefix_export_projection_changed")
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument("command",choices=("build","verify"));p.add_argument("batch");p.add_argument("model");p.add_argument("output");p.add_argument("--count",type=int);a=p.parse_args();print(json.dumps(build(a.batch,a.model,a.output,a.count) if a.command=="build" else verify(a.batch,a.model,a.output),indent=2))
if __name__=="__main__":main()
