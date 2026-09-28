"""Independently extract a v0.6 bundle and test replay, exports and negative controls."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,shutil,subprocess,sys,zipfile

def load(path):return json.loads(path.read_bytes())
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
def rows(path):return [json.loads(x) for x in path.read_bytes().split(b"\n") if x.strip()]
def putrows(path,value):path.write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in value),encoding="utf-8",newline="\n")
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def accept(archive,work,report):
    archive=Path(archive).resolve();work=Path(work).resolve();report=Path(report).resolve()
    if work.exists() or report.exists():raise ValueError("output_exists")
    work.mkdir(parents=True);base=work/"extracted";checks=[];negatives=[]
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if not (base/name).resolve().is_relative_to(base):raise ValueError("unsafe_archive_path")
        z.extractall(base)
    def run(label,args,expected):
        p=subprocess.run([sys.executable,"-X","utf8","-B",*map(str,args)],cwd=work,
                         capture_output=True,text=True,encoding="utf-8",timeout=45)
        item={"check":label,"args":[str(x).replace(str(work),"<acceptance-work>") for x in args],
              "exit_code":p.returncode,"stdout":p.stdout,"stderr":p.stderr}
        checks.append(item)
        if p.returncode!=expected:raise AssertionError(item)
    run("standalone_verification",[base/"verify_runtime.py","verify",base],0)
    spec=importlib.util.spec_from_file_location("accept_bundle",base/"verify_runtime.py")
    v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
    summary=v.verify_bundle(base);indices=rows(base/"rollouts/episodes.jsonl")
    for row in indices:
        task=base/"curriculum/tasks"/row["task_id"];reference=work/(row["task_id"]+".json")
        run("model_grade_"+row["task_id"],[task/"tests/verify.py",base/"rollouts"/row["path"]],0 if row["reward"] else 1)
        run("reference_"+row["task_id"],[task/"solution/reference.py","--output",reference],0)
        run("reference_grade_"+row["task_id"],[task/"tests/verify.py",reference],0)

    def mutate(name,change,error):
        target=work/("tamper-"+name);shutil.copytree(base,target);change(target)
        roll=target/"rollouts"
        for row in rows(roll/"episodes.jsonl"):
            path=roll/row["path"];episode=load(path)
            for ref in episode["capture_refs"]:ref["capture_sha256"]=sha(roll/ref["path"]/"capture.json")
            save(path,episode)
        m=load(roll/"manifest.json");m["files"]=v.c.hashes(roll);save(roll/"manifest.json",m)
        m=load(target/"manifest.json");m["files"]=v.all_hashes(target);save(target/"manifest.json",m)
        try:v.verify_bundle(target)
        except (ValueError,KeyError,FileNotFoundError) as e:
            if error not in str(e):raise AssertionError((name,str(e),error))
            negatives.append({"case":name,"rehashed":True,"rejected":True,"reason":str(e)})
        else:raise AssertionError("accepted "+name)

    first=indices[0];call=Path("rollouts")/Path(first["path"]).parent/"calls/001"
    def changed_cap(root,field,value):
        p=root/call/"capture.json";obj=load(p);obj[field]=value;save(p,obj)
    mutate("model_identity_changed",lambda root:changed_cap(root,"model_requested","unattested-model"),"capture_model_identity_changed")
    mutate("isolation_claim_changed",lambda root:changed_cap(root,"isolation",{}),"isolation_record_changed")
    def observation(root):
        p=root/call/"request.json";obj=load(p);obj["private_grader"]={"answer":"injected"};save(p,obj)
        p=root/call/"capture.json";obj=load(p);obj["request_sha256"]=sha(root/call/"request.json");save(p,obj)
    mutate("private_answer_in_request",observation,"model_observation_boundary_changed")
    def schema(root):
        p=root/call/"action.schema.json";obj=load(p);obj["additionalProperties"]=True;save(p,obj)
    mutate("schema_changed",schema,"model_schema_changed")
    def reward(root):
        p=root/"rollouts/episodes.jsonl";value=rows(p);value[0]["reward"]=1;putrows(p,value)
    mutate("incomplete_promoted_to_success",reward,"model_reward_changed")
    def event_removed(root):
        p=root/"rollouts"/first["path"];obj=load(p)
        obj["events"]=[e for e in obj["events"] if e["observation"].get("status")!=429];save(p,obj)
    mutate("rate_limit_deleted",event_removed,"mismatch")
    def training(root):
        putrows(root/"training/model-sft.jsonl",[{"task_id":indices[1]["task_id"],"split":"train","actor_kind":"isolated_model_cli"}])
    mutate("test_trajectory_in_training",training,"model_training_selection_changed")
    def exclusions(root):
        p=root/"training/selection.json";obj=load(p);obj["excluded"]=[];save(p,obj)
    mutate("exclusions_hidden",exclusions,"selection_exclusions_changed")
    def ledger(root):
        p=root/"execution-evidence/ledger-after.json";obj=load(p);obj["reservations"]=obj["reservations"][1:];save(p,obj)
    mutate("old_reservation_removed",ledger,"old_reservations_removed")
    def pending(root):
        p=root/"rollouts/config.json";obj=load(p);obj["execution_authorization"]="pending";save(p,obj)
    mutate("unapproved_execution",pending,"external_model_execution_not_approved")
    def stop(root):
        p=root/"rollouts/episodes.jsonl";obj=rows(p);obj[0]["stop_reason"]=None;putrows(p,obj)
    mutate("stop_reason_hidden",stop,"stop_reason_changed")
    def limit(root):
        p=root/"execution-evidence/execution-limits.json";obj=load(p);obj["collector_limit_disclosed_in_model_request"]=True;save(p,obj)
    mutate("collector_limit_misrepresented",limit,"execution_limit_disclosure_changed")
    assert load(base/"manifest.json")["files"]==v.all_hashes(base)
    result={"verified":True,"archive_sha256":sha(archive),"archive_bytes":archive.stat().st_size,
            "manifest_sha256":sha(base/"manifest.json"),"independent_extraction":True,"summary":summary,
            "checks":checks,"negative_controls":negatives,"execution_accounting":v.verify_execution_evidence(base),
            "external_model_calls_in_acceptance":0}
    report.parent.mkdir(parents=True,exist_ok=True);save(report,result)
    print(json.dumps({k:x for k,x in result.items() if k not in {"checks","negative_controls"}},ensure_ascii=False,indent=2))
    print("rejected_negative_controls",len(negatives))

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("archive");p.add_argument("--work",required=True);p.add_argument("--report",required=True)
    args=p.parse_args();accept(args.archive,args.work,args.report)
