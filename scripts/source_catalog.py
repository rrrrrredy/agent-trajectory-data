"""Cross-version provenance catalog rebuilt from frozen original index snapshots."""
from __future__ import annotations
import argparse,copy,json
from collections import Counter,defaultdict
from pathlib import Path
import runtime_batch as b
from research_env_v3 import check,digest,equal
SOURCES=[("v0.1","research-slices-v0.1","tasks.jsonl"),("v0.2-runs","research-history-v0.2","runs.jsonl"),("v0.2-cases","research-history-v0.2","semantic_cases.jsonl"),("v0.3","research-corpus-v0.3","tasks.jsonl"),("v0.4","agent-runtime-v0.4","tasks.jsonl"),("v0.5","agent-runtime-v0.5","tasks.jsonl"),("v0.6","agent-runtime-v0.6","curriculum/tasks.jsonl"),("v0.7","agent-runtime-v0.7","prior/curriculum/tasks.jsonl"),("v0.8","agent-runtime-v0.8","batch/tasks.jsonl"),("v0.9","agent-runtime-v0.9","batch/tasks.jsonl")]
def project(source,row,line):
    identity=row.get("task_id",row.get("run_id",row.get("case_id")))
    check(isinstance(identity,str),"catalog_identity_missing")
    family=row.get("source_group_id",row.get("source_group",row.get("family_id",identity)))
    rights=row.get("rights",{});eligible=rights.get("training_eligible",row.get("training_eligible",False)) is True
    parent=row.get("parent_task_id",row.get("lineage",{}).get("parent_task_id",row.get("revision_of")))
    fingerprint=row.get("source_sha256",row.get("report_sha256",row.get("payload_sha256")))
    return {"record_id":source+":"+row.get("case_version_id",identity),"record_version_id":row.get("case_version_id",identity),"component":source,"task_id":identity,"kind":"run" if "run_id" in row else "case" if "case_id" in row else "task","family_id":family,"split":row.get("split","development"),"training_eligible":eligible,"rights":rights,"parent_task_id":parent,"content_fingerprint":fingerprint,"related_task_ids":row.get("related_task_ids",[]),"origin":row.get("origin",row.get("task_origin",row.get("task_kind","retained_record"))),"source_index_line":line}
def resolve(rows):
    rows=copy.deepcopy(rows);parents={};owners={}
    def find(x):
        parents.setdefault(x,x)
        if parents[x]!=x:parents[x]=find(parents[x])
        return parents[x]
    def join(a,z):
        a,z=find(a),find(z)
        if a!=z:parents[max(a,z)]=min(a,z)
    for row in rows:
        rid=row["record_id"];find(rid)
        tokens=["family:"+row["family_id"],"task:"+row["task_id"]]
        if row["parent_task_id"]:tokens.append("task:"+row["parent_task_id"])
        tokens.extend("task:"+x for x in row["related_task_ids"])
        if row["content_fingerprint"]:tokens.append("content:"+row["content_fingerprint"])
        for token in tokens:
            if token in owners:join(rid,owners[token])
            else:owners[token]=rid
    groups=defaultdict(list)
    for row in rows:groups[find(row["record_id"])].append(row)
    for members in groups.values():
        splits={x["split"] for x in members}
        check(not {"train","test"}<=splits,"cross_version_train_test_leakage")
        check(not (any(x["split"]=="train" and x["training_eligible"] for x in members) and any(not x["training_eligible"] for x in members)),"inherited_use_promotion")
        group_id="lineage-"+digest(min(x["record_id"] for x in members))[:20]
        for row in members:row["lineage_group_id"]=group_id;row["reuses_prior_component"]=any(x["component"]!=row["component"] for x in members)
    return rows

def derive(root):
    root=Path(root);spec=b.read(root/"sources.json");rows=[]
    for item in spec:
        raw=b.local(root,item["snapshot"]).read_bytes();manifest_raw=b.local(root,item["manifest"]).read_bytes()
        check(b.sha(raw)==item["index_sha256"] and b.sha(manifest_raw)==item["manifest_sha256"],"catalog_snapshot_changed")
        upstream=json.loads(manifest_raw);check(upstream["files"].get(item["index_path"])==b.sha(raw),"catalog_upstream_binding_changed")
        rows.extend(project(item["component"],row,i+1) for i,row in enumerate(b.lines(root/item["snapshot"])))
    check(len({x["record_id"] for x in rows})==len(rows),"duplicate_catalog_identity")
    return resolve(rows)
def stats(rows):
    newest=[x for x in rows if x["component"]==(rows[-1]["component"] if rows else None)]
    return {"records":len(rows),"components":len({x["component"] for x in rows}),"lineage_groups":len({x["lineage_group_id"] for x in rows}),"records_by_component":dict(Counter(x["component"] for x in rows)),"new_task_variants":len(newest),"new_independent_source_groups":len({x["lineage_group_id"] for x in newest if not x["reuses_prior_component"]}),"train_test_conflicts":0,"rights_promotions":0,"boundary":"Recorded family, parent-task and exact content fingerprints only. Near-duplicate semantics and unrecorded relationships are not certified."}
def build(repo,batch,output):
    repo,batch,root=map(Path,(repo,batch,output));check(not root.exists(),"output_exists");sources=[];config=b.read(batch/"config.json");component="v"+config["dataset_version"]
    tag=config["prior_release"]["tag"];check(tag.startswith("dataset-v"),"unknown_prior_release")
    previous=b.local(repo/"data","runtime-catalog-v"+tag.removeprefix("dataset-v"))
    if previous.exists():
        verify(previous);sources=b.read(previous/"sources.json")
        for item in sources:
            for key in ("snapshot","manifest"):b.write(root/item[key],b.local(previous,item[key]).read_bytes())
        additions=[(component,None,"tasks.jsonl")]
    else:
        check(component=="v0.10","prior_catalog_required");additions=SOURCES+[(component,None,"tasks.jsonl")]
    for name,folder,index in additions:
        check(name not in {x["component"] for x in sources},"catalog_component_already_present")
        source=batch if folder is None else repo/"data"/folder;raw=(source/index).read_bytes();manifest=(source/"manifest.json").read_bytes()
        snapshot="snapshots/"+name+".jsonl";manifest_name="snapshots/"+name+".manifest.json";b.write(root/snapshot,raw);b.write(root/manifest_name,manifest)
        sources.append({"component":name,"index_path":index,"index_sha256":b.sha(raw),"manifest_sha256":b.sha(manifest),"snapshot":snapshot,"manifest":manifest_name})
    b.put(root/"sources.json",sources);rows=derive(root);b.put_lines(root/"records.jsonl",rows);b.put(root/"summary.json",stats(rows));b.put(root/"manifest.json",{"files":b.hashes(root)})
    return verify(root)

def verify(root):
    root=Path(root);check(b.read(root/"manifest.json")["files"]==b.hashes(root),"catalog_files_changed");rows=derive(root);check(equal(rows,b.lines(root/"records.jsonl")),"catalog_projection_changed");summary=stats(rows);check(summary==b.read(root/"summary.json"),"catalog_counts_changed");return {"passed":True,**summary}
def main():
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest="command",required=True);p=sub.add_parser("build");p.add_argument("repo");p.add_argument("batch");p.add_argument("output");p=sub.add_parser("verify");p.add_argument("root");a=parser.parse_args();print(json.dumps(build(a.repo,a.batch,a.output) if a.command=="build" else verify(a.root),indent=2))
if __name__=="__main__":main()
