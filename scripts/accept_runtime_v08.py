"""Offline acceptance of an extracted v0.8 archive, including rehashed mutations."""
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
    task="orchid-quota-counterfactual-v3";reference=work/"fresh-reference.json"
    command("reference_solution_cli",[base/"task-entrypoints"/task/"solution/reference.py",reference])
    command("fresh_reference_grader",[base/"task-entrypoints"/task/"tests/verify.py",reference])
    wire="".join(json.dumps(event["action"])+"\n" for event in read(reference)["events"])
    command("environment_stdio_real_transition",[base/"research_env_v3.py",base/"batch/tasks"/task/"scenario.json","--output",work/"stdio-episode.json"],input_text=wire)
    command("stdio_episode_grader",[base/"task-entrypoints"/task/"tests/verify.py",work/"stdio-episode.json"])
    first=index[0];episode_rel=Path("model")/first["path"];call=episode_rel.parent/"calls/001"
    def mutate(name,change,expected):
        target=work/("mutation-"+name);shutil.copytree(base,target);change(target)
        model=target/"model"
        for row in rows(model/"episodes.jsonl"):
            path=model/row["path"];run=read(path)
            for ref in run["capture_refs"]:ref["capture_sha256"]=sha(model/ref["path"]/"capture.json")
            save(path,run)
        for component in (target/"batch",model):
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
        else:value["runtime_budget"]["environment_steps_remaining"]+=1
        save(p,value);p=root/call/"capture.json";value=read(p);value["request_sha256"]=sha(root/call/"request.json");save(p,value)
    mutate("answer_in_policy_context",lambda root:request_change(root,"answer"),"public_request_changed")
    mutate("wrong_visible_budget",lambda root:request_change(root,"budget"),"public_request_changed")
    def note(root):
        p=root/episode_rel;value=read(p);value["final_state"]["notes"]["note-1"]["text"]="All facts externally verified.";save(p,value)
    mutate("unsupported_delivered_text",note,"final_state_changed")
    def missing_failure(root):
        p=root/episode_rel;value=read(p);value["events"]=[event for event in value["events"] if event["observation"]["status"]!=429];save(p,value)
    mutate("rate_limit_history_removed",missing_failure,"event_replay_changed")
    def model_origin(root):
        p=root/episode_rel;value=read(p);value["evaluation_mode"]="independent_blind_benchmark";save(p,value)
    mutate("development_claimed_blind",model_origin,"model_origin_changed")
    def train(root):
        p=root/"model/training/model-sft.jsonl";values=rows(p);values.append({"task_id":index[1]["task_id"],"split":"train"});row_save(p,values)
    mutate("test_family_in_training",train,"model_training_selection_changed")
    def ledger(root):
        p=root/"model/ledger-final.json";value=read(p);value["entries"]=value["entries"][1:];save(p,value)
    mutate("prior_reservation_removed",ledger,"prior_ledger_changed")
    def entrypoint(root):
        p=root/"task-entrypoints"/task/"tests/verify.py";p.write_text("raise SystemExit(0)\n",encoding="utf-8")
    mutate("grader_entrypoint_replaced",entrypoint,"task_entrypoint_changed")
    def checkpoint(root):
        p=root/episode_rel.parent/"checkpoints/001.json";value=read(p);value["final_state"]["ticket"]["status"]="ready";save(p,value)
    mutate("checkpoint_state_changed",checkpoint,"checkpoint_changed")
    report.parent.mkdir(parents=True,exist_ok=True)
    result={"passed":True,"archive_sha256":sha(archive),"archive_bytes":archive.stat().st_size,"summary":summary,
            "acceptance_script_sha256":sha(Path(__file__)),"packaged_verifier_sha256":sha(base/"runtime_release.py"),
            "commands":checks,"rehashed_negative_controls":negatives,"model_calls_during_acceptance":0}
    save(report,result);return {"passed":True,"commands":len(checks),"rehashed_negative_controls":len(negatives),"archive_sha256":result["archive_sha256"]}

def main():
    parser=argparse.ArgumentParser();parser.add_argument("archive");parser.add_argument("work");parser.add_argument("report");args=parser.parse_args()
    print(json.dumps(accept(args.archive,args.work,args.report),indent=2))
if __name__=="__main__":main()
