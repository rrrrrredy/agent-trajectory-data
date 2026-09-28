"""Acceptance of the independently extracted recovery archive; no model calls."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,shutil,subprocess,sys,zipfile
def load(p):return json.loads(p.read_bytes())
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
def rows(p):return [json.loads(x) for x in p.read_bytes().split(b"\n") if x.strip()]
def putrows(p,v):p.write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in v),encoding="utf-8",newline="\n")
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def accept(archive,work,report):
    archive,work,report=map(lambda p:Path(p).resolve(),(archive,work,report))
    if work.exists() or report.exists():raise ValueError("output_exists")
    work.mkdir(parents=True);base=work/"extracted";checks=[];negatives=[]
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if not (base/name).resolve().is_relative_to(base):raise ValueError("unsafe_archive_path")
        z.extractall(base)
    def run(label,args,expected):
        p=subprocess.run([sys.executable,"-X","utf8","-B",*map(str,args)],cwd=work,capture_output=True,text=True,encoding="utf-8",timeout=45)
        item={"check":label,"exit_code":p.returncode,"stdout":p.stdout,"stderr":p.stderr}
        checks.append(item)
        if p.returncode!=expected:raise AssertionError(item)
    run("standalone_recovery_verifier",[base/"verify_recovery.py","verify",base],0)
    spec=importlib.util.spec_from_file_location("recovery_acceptance",base/"verify_recovery.py")
    r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
    summary=r.verify(base);indices=rows(base/"recovery/episodes.jsonl")
    for row in indices:
        grader=base/"prior/curriculum/tasks"/row["task_id"]/"tests/verify.py"
        run("unchanged_grader_"+row["task_id"],[grader,base/"recovery"/row["path"]],0 if row["reward"] else 1)
    def mutate(name,change,error):
        target=work/("tamper-"+name);shutil.copytree(base,target);change(target)
        rr=target/"recovery"
        for row in rows(rr/"episodes.jsonl"):
            p=rr/row["path"];episode=load(p)
            for ref in episode["capture_refs"]:ref["capture_sha256"]=sha(rr/ref["path"]/"capture.json")
            save(p,episode)
        m=load(rr/"manifest.json");m["files"]=r.c.hashes(rr);save(rr/"manifest.json",m)
        m=load(target/"manifest.json");m["files"]=r.c.hashes(target);save(target/"manifest.json",m)
        try:r.verify(target)
        except (ValueError,KeyError,FileNotFoundError) as e:
            if error not in str(e):raise AssertionError((name,str(e),error))
            negatives.append({"case":name,"rehashed":True,"rejected":True,"reason":str(e)})
        else:raise AssertionError("accepted "+name)
    first=indices[0];path=Path("recovery")/first["path"]
    call=path.parent/"calls/001"
    def budget(root):
        p=root/call/"request.json";v=load(p);v["runtime_budget"]["environment_steps_remaining"]+=1;save(p,v)
        p=root/call/"capture.json";v=load(p);v["request_sha256"]=sha(root/call/"request.json");save(p,v)
    mutate("wrong_remaining_budget",budget,"recovery_observation_or_budget_changed")
    def contract(root):
        p=root/call/"request.json";v=load(p);del v["runtime_contract"];save(p,v)
        p=root/call/"capture.json";v=load(p);v["request_sha256"]=sha(root/call/"request.json");save(p,v)
    mutate("tool_contract_removed",contract,"recovery_observation_or_budget_changed")
    def prefix(root):
        p=root/path;v=load(p);v["prefix_steps"]-=1;save(p,v)
    mutate("original_failure_boundary_changed",prefix,"original_failure_prefix_changed")
    def hidden_failure(root):
        p=root/path;v=load(p);v["events"]=[e for e in v["events"] if e["observation"].get("status")!=429];save(p,v)
    mutate("old_rate_limits_deleted",hidden_failure,"mismatch")
    def first_attempt(root):
        p=root/path;v=load(p);v["evaluation_mode"]="independent_unseen_first_attempt";save(p,v)
    mutate("recovery_claimed_unseen",first_attempt,"recovery_claimed_independent_first_attempt")
    def training(root):
        p=root/"training/model-sft-recovery.jsonl";v=rows(p)
        v.append({"task_id":indices[1]["task_id"],"family_id":indices[1]["family_id"],"split":"train"});putrows(p,v)
    mutate("test_family_in_training",training,"recovery_sft_changed")
    def prefix_training(root):
        p=root/"training/model-trajectories.jsonl";v=rows(p)
        if v:v[0]["decisions"]=v[0]["decisions"][12:]
        else:v.append({"fabricated":True})
        putrows(p,v)
    mutate("failure_prefix_removed_from_training",prefix_training,"recovery_training_trajectories_changed")
    def ledger(root):
        p=root/"recovery/execution-evidence/ledger-after.json";v=load(p);v["reservations"]=v["reservations"][1:];save(p,v)
    mutate("prior_call_history_removed",ledger,"prior_reservations_changed")
    def pending(root):
        p=root/"recovery/config.json";v=load(p);v["execution_authorization"]="pending_new_batch_approval";save(p,v)
    mutate("missing_new_batch_approval",pending,"new_recovery_batch_approval_required")
    def cap(root):
        p=root/"recovery/config.json";v=load(p);v["max_new_calls"]+=1;save(p,v)
    mutate("expanded_call_budget",cap,"recovery_budget_not_environment_aligned")
    def excluded(root):
        p=root/"training/selection.json";v=load(p);v["excluded"]=[];save(p,v)
    mutate("test_exclusion_hidden",excluded,"recovery_exclusions_changed")
    def model(root):
        p=root/call/"capture.json";v=load(p);v["model_requested"]="unattested";save(p,v)
    mutate("model_identity_changed",model,"recovery_model_identity_changed")
    assert load(base/"manifest.json")["files"]==r.c.hashes(base)
    result={"verified":True,"archive_bytes":archive.stat().st_size,"archive_sha256":sha(archive),
      "manifest_sha256":sha(base/"manifest.json"),"independent_extraction":True,"summary":summary,
      "checks":checks,"negative_controls":negatives,"model_calls_in_acceptance":0,
      "parent_manifest_sha256":sha(base/"prior/manifest.json"),"unchanged_grader_used":True}
    report.parent.mkdir(parents=True,exist_ok=True);save(report,result)
    print(json.dumps({k:v for k,v in result.items() if k not in {"checks","negative_controls"}},ensure_ascii=False,indent=2))
    print("rejected_negative_controls",len(negatives))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("archive");p.add_argument("--work",required=True);p.add_argument("--report",required=True)
    a=p.parse_args();accept(a.archive,a.work,a.report)
