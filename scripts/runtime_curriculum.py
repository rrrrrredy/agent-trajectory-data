"""Build source-separated runtime tasks and transparent training exports."""
from __future__ import annotations
import argparse,copy,csv,hashlib,importlib.util,io,json,re,shutil,sys,zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
def module(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+".py"))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
b=module("business_env_v2");rd=module("research_dataset")
VERSION="runtime-curriculum-1"
FAULTS=("clean","missing_reference","tool_retry","access_revoked","concurrent_edit")
SYNTHETIC={
 "capacity": {
  "title":"虚构实验室算力交接备忘",
  "sources":[("CAP-A","设备盘点","可使用的四台设备，容量数据只用于练习。"),
             ("CAP-B","维护窗口","每周三安排维护，盘点与可用容量不能混用。"),
             ("CAP-C","审批记录","新增设备尚未完成验收。"),
             ("CAP-D","历史变更","上周可用设备数与本周不同。")],
  "claims":[("CAP-C1","盘点数量不等于即时可用数量。","CAP-A|CAP-B"),
            ("CAP-C2","新增设备不能计入已验收容量。","CAP-C"),
            ("CAP-C3","历史数量不替代当前盘点。","CAP-A|CAP-D"),
            ("CAP-C4","交接需要同时说明维护约束。","CAP-B")]},
 "retention":{
  "title":"虚构档案归档期限交接备忘",
  "sources":[("RET-A","档案目录","草稿、正式记录和附件具有不同的保存标签。"),
             ("RET-B","版本规则","正式记录的修改需要建立新版本。"),
             ("RET-C","访问记录","只有档案角色可以查阅限制附件。"),
             ("RET-D","迁移记录","迁移完成不证明旧链接仍然有效。")],
  "claims":[("RET-C1","记录标签与版本关系应分别核对。","RET-A|RET-B"),
            ("RET-C2","附件访问受角色限制。","RET-C"),
            ("RET-C3","迁移后仍需检查链接。","RET-D"),
            ("RET-C4","不能用附件不可见推断其内容。","RET-A|RET-C")]}
}
TRAIN_RIGHTS={"allowed_uses":["diagnostic","sft","preference"],"training_eligible":True,
 "distribution":"private_internal_only","basis":"new_fictional_material_authored_for_user_requested_dataset"}
EVAL_RIGHTS={"allowed_uses":["diagnostic"],"training_eligible":False,
 "distribution":"private_internal_only","basis":"selected_archived_research_material_for_evaluation"}
SOURCE_PATHS={
 "muse":Path(r"D:\Documents\写作\muse-personal-ai-insights-2026-09-24"),
 "looped":Path(r"D:\Documents\写作\looped-transformer-research-2026-09-10")}
def check(ok,reason):
    if not ok:raise ValueError(reason)
def hashes(root):
    return {p.relative_to(root).as_posix():rd.sha(p.read_bytes()) for p in root.rglob("*")
            if p.is_file() and p!=root/"manifest.json"}
def read(p):return rd.load_json(p)
def lines(p):return rd.load_lines(p)
def text_hash(text):return rd.sha(text.replace("\r\n","\n").replace("\r","\n").encode())
def shingles(text):
    text=re.sub(r"\s+","",text.casefold())
    return {text[i:i+12] for i in range(max(0,len(text)-11))}
def similarity(a,b):
    return len(a&b)/max(1,min(len(a),len(b)))
def rows(raw):return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
def normalize_tables(source_raw,claim_raw):
    sources=rows(source_raw);claims=rows(claim_raw)[:8]
    check(sources and claims,"empty_tables")
    selected=[];needed=set()
    for row in claims:
        ids=[x.strip() for x in re.split(r"[;|]",row["supporting_sources"]) if x.strip()]
        check(all(re.fullmatch(r"[A-Za-z0-9_-]+",x) for x in ids),"ambiguous_source_separator")
        needed.update(ids)
        selected.append({"claim_id":row["claim_id"],"claim":row["claim"],"source_ids":"|".join(ids)})
    minimal=[{"source_id":r["source_id"],"title":r["title"],
              "url":r.get("url",r.get("url_or_path",""))} for r in sources if r["source_id"] in needed]
    check(len({r["source_id"] for r in minimal})==len(minimal),"duplicate_source_rows")
    return minimal,selected
def synthetic_material(key):
    spec=SYNTHETIC[key]
    return {"title":spec["title"],"origin":"new_fully_fictional_material",
            "sources":[{"source_id":i,"title":t,"content":c} for i,t,c in spec["sources"]],
            "claims":[{"claim_id":i,"claim":c,"source_ids":s} for i,c,s in spec["claims"]]}
def scenario_for(source,fault):
    parent=b.v1.make_scenario(source["source_id"],source["family_id"],source["sources"],source["claims"],fault)
    parent["as_of"]="2026-09-28"
    for key,doc in parent["documents"].items():
        doc["effective_at"]="2026-09-29" if key=="future" else "2026-09-27" if key=="old-note" else "2026-09-28"
    s=b.revise_scenario(parent)
    s.update(split=source["split"],rights=source["rights"],origin=source["origin"])
    s["instruction"]+="\n本题材料来源："+source["origin"]+"。只检查给定表格的登记关系。"
    s["documents"]["handoff"]["body"]["origin"]=source["origin"]
    return s
def control(scenario,mode):
    env=b.BusinessEnv(scenario);b.reference_policy(env,mode)
    run=b.record(env,"scripted_reference" if mode=="reference" else "scripted_negative")
    run["policy"]=mode
    return run
def messages(scenario,run):
    env=b.BusinessEnv(scenario);observation,_=env.reset(run["seed"])
    result=[{"role":"user","content":b.stable({"initial_observation":observation})}]
    for event in run["events"]:
        result.append({"role":"assistant","content":b.stable(event["action"])})
        if not event["terminated"] and not event["truncated"]:
            result.append({"role":"user","content":b.stable({"tool_result":event["observation"]})})
    return result
def training_rows(root,tasks):
    sft=[];pairs=[]
    for task in tasks:
        if task["split"]!="train":continue
        scenario=read(root/task["environment"])
        run=read(root/task["reference_episode"])
        check(b.verify_record(scenario,run)["reward"]==1,"reference_not_passing")
        positive=messages(scenario,run)
        row={"task_id":task["task_id"],"family_id":task["family_id"],"split":"train",
             "actor_kind":"scripted_reference","rights":task["rights"],"messages":positive,
             "trace_path":task["reference_episode"],"format":"visible-action-messages-1",
             "label_basis":"deterministic_environment_reward","model_demonstration":False}
        sft.append(row)
        negative=read(root/task["wrong_episode"]);bad=messages(scenario,negative)
        check(positive[:-1]==bad[:-1],"preference_context_differs")
        pairs.append({"task_id":task["task_id"],"family_id":task["family_id"],"split":"train",
            "actor_kind":"scripted_counterfactual","model_preference":False,"prompt":positive[:-1],
            "chosen":positive[-1],"rejected":bad[-1],"chosen_reward":1,"rejected_reward":0,
            "label_basis":"same_observations_and_state_only_final_scope_differs",
            "rights":task["rights"]})
    return sft,pairs
def freeze(prior,output):
    prior=Path(prior).resolve();output=Path(output).resolve()
    check(not output.exists(),"output_exists")
    manifest=read(prior/"manifest.json")
    actual={p.relative_to(prior).as_posix():rd.sha(p.read_bytes()) for p in prior.rglob("*")
            if p.is_file() and p!=prior/"manifest.json"}
    check(actual==manifest["files"],"prior_changed")
    old_inputs=prior/"prior/inputs"
    old_reports={p.name:shingles(read(p)["user"]) for p in old_inputs.glob("*.json")}
    check(len(old_reports)==45,"prior_report_inventory_changed")
    output.mkdir(parents=True)
    for name in ("business_env.py","business_env_v2.py","research_dataset.py"):
        rd.put(output/name,(HERE/name).read_bytes())
    rd.put(output/"verify_curriculum.py",Path(__file__).read_bytes())
    rd.put(output/"LICENSE",(prior/"LICENSE").read_bytes())
    rd.put_json(output/"parent.json",{"release":"dataset-v0.4","manifest_sha256":rd.sha((prior/"manifest.json").read_bytes()),
                                    "historical_data_policy_unchanged":True})
    sources=[]
    for key in SYNTHETIC:
        material=synthetic_material(key);sid="synthetic-"+key
        path="sources/"+sid+"/authored.json";rd.put_json(output/path,material)
        sources.append({"source_id":sid,"family_id":"family-"+sid,"split":"train","origin":material["origin"],
                        "rights":TRAIN_RIGHTS,"sources":material["sources"],"claims":material["claims"],
                        "artifacts":{path:rd.sha((output/path).read_bytes())},
                        "new_independent_source_from_other_split":True})
    checks=[]
    for key,folder in SOURCE_PATHS.items():
        sid="archived-"+key;artifacts={}
        for name in ("final.md","data/source_registry.csv","data/claims_registry.csv"):
            raw=(folder/name).read_bytes();path="sources/"+sid+"/"+name
            rd.put(output/path,raw);artifacts[path]=rd.sha(raw)
        report=(folder/"final.md").read_text(encoding="utf-8-sig")
        ranked=sorted(((similarity(shingles(report),value),name) for name,value in old_reports.items()),reverse=True)
        # A conservative overlap alarm, not a claim of pretraining decontamination.
        check(ranked[0][0]<0.15,"possible_prior_report_overlap:"+key)
        source_rows,claim_rows=normalize_tables((folder/"data/source_registry.csv").read_bytes(),
                                               (folder/"data/claims_registry.csv").read_bytes())
        sources.append({"source_id":sid,"family_id":"family-"+sid,"split":"test","origin":"artifact_derived_from_archived_report",
                        "rights":EVAL_RIGHTS,"sources":source_rows,"claims":claim_rows,
                        "artifacts":artifacts,"report_normalized_sha256":text_hash(report),
                        "extraction":"first_eight_claim_rows; exact source IDs; only referenced source rows; semicolon normalized to pipe",
                        "new_independent_source_from_other_split":True})
        checks.append({"source_id":sid,"compared_prior_inputs":45,"max_12gram_containment":ranked[0][0],
                       "nearest_prior_input":ranked[0][1],"alarm_threshold":0.15,"exact_match":False,
                       "pretraining_contamination_known":False,"scope":"selected_source_documents_only"})
    rd.put_lines(output/"sources.jsonl",sources)
    rd.put_json(output/"split-lock.json",{"policy":"whole_source_family_locked_before_model_execution",
        "families":{s["family_id"]:s["split"] for s in sources},
        "source_artifact_hashes":{s["source_id"]:s["artifacts"] for s in sources},
        "template_shared_across_splits":True,"independent_template_claim":False,
        "test_export_policy":"never_in_training_exports","prior_source_checks":checks})
    tasks=[]
    for source in sources:
        for fault in FAULTS:
            scenario=scenario_for(source,fault);tid=scenario["task_id"];base="tasks/"+tid
            rd.put_json(output/(base+"/environment/scenario.json"),scenario)
            rd.put(output/(base+"/instruction.md"),(scenario["instruction"]+"\n").encode())
            rd.put(output/(base+"/solution/reference.py"),SOLUTION.encode())
            rd.put(output/(base+"/tests/verify.py"),VERIFIER.encode())
            for mode in ("reference","empty","wrong_answer"):
                rd.put_json(output/("episodes/"+tid+"/"+mode+".json"),control(scenario,mode))
            task={"task_id":tid,"source_id":source["source_id"],"family_id":source["family_id"],
                  "split":source["split"],"rights":source["rights"],"fault":fault,"origin":source["origin"],
                  "environment":base+"/environment/scenario.json","instruction":base+"/instruction.md",
                  "grader":base+"/tests/verify.py","solution":base+"/solution/reference.py",
                  "reference_episode":"episodes/"+tid+"/reference.json",
                  "wrong_episode":"episodes/"+tid+"/wrong_answer.json"}
            rd.put_json(output/(base+"/task.json"),task);tasks.append(task)
    rd.put_lines(output/"tasks.jsonl",tasks)
    sft,pairs=training_rows(output,tasks)
    rd.put_lines(output/"training/scripted-sft.jsonl",sft)
    rd.put_lines(output/"training/scripted-preferences.jsonl",pairs)
    rd.put_json(output/"training/selection.json",{
        "accepted_families":sorted({r["family_id"] for r in sft}),
        "rejected_families":[{"family_id":s["family_id"],"reasons":["test_split","diagnostic_use_only"]}
                             for s in sources if s["split"]=="test"],
        "archived_prior_records":"excluded; prior diagnostic permissions unchanged",
        "synthetic_reference_demonstrations":len(sft),"scripted_preference_pairs":len(pairs),
        "model_demonstrations":0,"hidden_reasoning_included":False})
    rd.put(output/"DATA_CARD.md",CARD.encode())
    rd.put_json(output/"manifest.json",{"version":VERSION,"files":hashes(output),"summary":summary(output)})
    return verify(output)
def summary(root):
    tasks=lines(root/"tasks.jsonl")
    return {"source_families":4,"synthetic_train_families":2,"archived_test_families":2,
            "train_tasks":sum(t["split"]=="train" for t in tasks),"test_tasks":sum(t["split"]=="test" for t in tasks),
            "scripted_control_episodes":len(tasks)*3,"scripted_sft_records":len(lines(root/"training/scripted-sft.jsonl")),
            "scripted_preference_pairs":len(lines(root/"training/scripted-preferences.jsonl")),
            "independent_model_episodes_in_frozen_tasks":0}
def verify(root):
    root=Path(root).resolve();m=read(root/"manifest.json")
    check(m["version"]==VERSION and m["files"]==hashes(root),"content_changed")
    sources=lines(root/"sources.jsonl");tasks=lines(root/"tasks.jsonl");lock=read(root/"split-lock.json")
    expected_ids={"synthetic-capacity","synthetic-retention","archived-muse","archived-looped"}
    check({s["source_id"] for s in sources}==expected_ids and len(sources)==4,"source_membership_changed")
    check(lock["template_shared_across_splits"] is True and lock["independent_template_claim"] is False,"template_independence_overclaim")
    check({s["family_id"]:s["split"] for s in sources}==lock["families"],"split_lock_changed")
    check({s["source_id"]:s["artifacts"] for s in sources}==lock["source_artifact_hashes"],"source_lock_changed")
    seen_hashes={}
    for s in sources:
        synthetic=s["source_id"].startswith("synthetic-")
        check(s["split"]==("train" if synthetic else "test"),"source_split_promoted")
        check(s["rights"]==(TRAIN_RIGHTS if synthetic else EVAL_RIGHTS),"source_rights_changed")
        for path,digest in s["artifacts"].items():
            check(rd.sha(rd.local_file(root,path).read_bytes())==digest,"source_artifact_changed")
            if digest in seen_hashes:check(seen_hashes[digest]==s["split"],"artifact_crosses_splits")
            seen_hashes[digest]=s["split"]
        if synthetic:
            key=s["source_id"].removeprefix("synthetic-");material=synthetic_material(key)
            check(read(root/"sources"/s["source_id"]/"authored.json")==material,"synthetic_authoring_changed")
            check(s["sources"]==material["sources"] and s["claims"]==material["claims"],"synthetic_tables_changed")
        else:
            base=root/"sources"/s["source_id"]
            expected_sources,expected_claims=normalize_tables((base/"data/source_registry.csv").read_bytes(),
                                                             (base/"data/claims_registry.csv").read_bytes())
            check(s["sources"]==expected_sources and s["claims"]==expected_claims,"archived_extraction_changed")
            check(text_hash((base/"final.md").read_text(encoding="utf-8-sig"))==s["report_normalized_sha256"],"report_binding_changed")
    by_source={s["source_id"]:s for s in sources}
    check(len(tasks)==20 and {(t["source_id"],t["fault"]) for t in tasks}=={(s,f) for s in expected_ids for f in FAULTS},"task_membership_changed")
    for t in tasks:
        s=by_source[t["source_id"]]
        check(t["family_id"]==s["family_id"] and t["split"]==s["split"] and t["rights"]==s["rights"],"task_split_or_rights_changed")
        check(t==read(root/"tasks"/t["task_id"]/"task.json"),"task_metadata_changed")
        scenario=read(rd.local_file(root,t["environment"]))
        check(scenario==scenario_for(s,t["fault"]),"scenario_derivation_changed")
        check((root/t["solution"]).read_text(encoding="utf-8")==SOLUTION and
              (root/t["grader"]).read_text(encoding="utf-8")==VERIFIER,"task_entrypoint_changed")
        for mode in ("reference","empty","wrong_answer"):
            run=read(root/"episodes"/t["task_id"]/(mode+".json"))
            check(run==control(scenario,mode),"scripted_control_changed")
            check(b.verify_record(scenario,run)["reward"]==int(mode=="reference"),"control_reward_changed")
    sft,pairs=training_rows(root,tasks)
    check(lines(root/"training/scripted-sft.jsonl")==sft,"sft_export_changed")
    check(lines(root/"training/scripted-preferences.jsonl")==pairs,"preference_export_changed")
    check(summary(root)==m["summary"],"summary_changed")
    return {"verified":True,"files":len(m["files"]),**m["summary"]}
def pack(root,output):
    root=Path(root).resolve();output=Path(output).resolve();verify(root)
    check(not output.exists(),"output_exists");output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,"x",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                info=zipfile.ZipInfo(p.relative_to(root).as_posix(),date_time=(2026,9,28,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,p.read_bytes())
    return {"sha256":rd.sha(output.read_bytes()),"bytes":output.stat().st_size}
SOLUTION='''import argparse,sys
from pathlib import Path
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root))
from business_env_v2 import BusinessEnv,reference_policy,record,stable
p=argparse.ArgumentParser();p.add_argument("--output",required=True);a=p.parse_args()
if Path(a.output).exists():raise ValueError("output_exists")
e=BusinessEnv.from_file(Path(__file__).resolve().parents[1]/"environment/scenario.json")
reference_policy(e)
with open(a.output,"x",encoding="utf-8",newline="\\n") as f:f.write(stable(record(e,"scripted_reference"))+"\\n")
'''
VERIFIER='''import json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root))
from business_env_v2 import verify_record,stable
scenario=json.loads((Path(__file__).resolve().parents[1]/"environment/scenario.json").read_bytes())
r=verify_record(scenario,json.loads(Path(sys.argv[1]).read_bytes()))
print(stable(r));raise SystemExit(0 if r["reward"] else 1)
'''
CARD="""# Source-separated runtime curriculum
Four source families, twenty executable development and evaluation task variants.
Two newly authored fictional source families form the training side. Two independently
selected archived research reports form the test side; their whole families are excluded
from training. The same workflow template is shared. No unseen-template or pretraining
decontamination claim is made.
All ten training demonstrations and ten preference pairs in this frozen task package are
explicitly scripted. Preferences share the full observed prefix and differ only in the final
scope decision. They are synthetic supervision, not model-generated trajectories.
The archived reports and their tables are copied as historical artifacts; their claims are not
certified factual. First eight claim rows are projected with their referenced source rows.
Report text is evaluator-side provenance, not learner input. Old diagnostic records keep
their original use policy. Learners receive initial observations and actual tool responses,
never the full package. Runtime v2, reference scripts and deterministic graders are included.
Run python -X utf8 -B verify_curriculum.py verify .
"""
def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="cmd",required=True)
    x=sub.add_parser("freeze");x.add_argument("--prior",required=True);x.add_argument("--output",required=True)
    x=sub.add_parser("verify");x.add_argument("root")
    x=sub.add_parser("pack");x.add_argument("root");x.add_argument("output")
    a=p.parse_args()
    result=freeze(a.prior,a.output) if a.cmd=="freeze" else verify(a.root) if a.cmd=="verify" else pack(a.root,a.output)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
