"""Version 2 of the offline business environment; frozen v1 remains unchanged."""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASE=HERE/"business_env.py"
if not BASE.is_file():BASE=HERE/"prior/business_env.py"
_spec=importlib.util.spec_from_file_location("business_environment_v1",BASE)
v1=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(v1)
stable,digest=v1.stable,v1.digest
VERSION="business-env-2"
REQUIRED={"policy","handoff","sources","claims"}
POLICY_ADDITION="""
读取成功的证据须有当前版本的 200 返回。429 只是一次失败请求，不是读到了材料。
来源表或主张表的 403/404 可以证明被阻塞；不得把尚可重试的 429 当成材料内容。
交接说明的证据以写入时已获得的读取回执为准，后续读取不会追溯补全旧说明；
读到新证据后应另写说明并更新任务单。可以修正已有任务单，旧说明和旧更新都保留。
"""

def revise_scenario(original):
    if original["schema_version"]!="business-env-1":raise ValueError("unsupported_parent_environment")
    value=copy.deepcopy(original)
    value.update(schema_version=VERSION,task_id=original["task_id"]+"-v2",
                 parent_task_id=original["task_id"],parent_scenario_sha256=digest(original),
                 revision_reason="Bind evidence to successful reads at note creation; preserve failed observations.")
    value["initial_ticket"]["id"]=value["task_id"]
    value["documents"]["policy"]["body"]+=POLICY_ADDITION
    value["documents"]["policy"]["version"]+=1
    return value

class BusinessEnv(v1.BusinessEnv):
    def __init__(self,scenario):
        if scenario.get("schema_version")!=VERSION:raise ValueError("use_matching_environment_version")
        super().__init__(scenario)
    def reset(self,seed=0,options=None):
        if type(seed) is not int:raise ValueError("seed_must_be_integer")
        result=super().reset(seed,options)
        self.receipts=[];self.ticket_updates=[]
        return result
    def snapshot(self):
        return dict(super().snapshot(),receipts=copy.deepcopy(self.receipts),
                    ticket_updates=copy.deepcopy(self.ticket_updates))
    def expected(self):
        docs=self.scenario["documents"]
        missing=sorted(key for key in ("sources","claims") if key not in docs
                       or not self.accessible(docs[key]) or docs[key].get("unavailable"))
        if missing:return {"status":"blocked","dangling_references":[],"missing_tables":missing}
        return super().expected()
    def latest_receipt(self,key):
        return next((r for r in reversed(self.receipts) if r["document_id"]==key),None)
    def valid_receipt(self,key,receipt):
        if not isinstance(receipt,dict) or receipt.get("document_id")!=key:return False
        doc=self.scenario["documents"].get(key)
        if key in self.expected()["missing_tables"]:
            return receipt.get("status") in {403,404}
        if doc is None or not self.accessible(doc) or doc.get("unavailable"):return False
        return (receipt.get("status")==200 and receipt.get("version")==doc["version"]
                and receipt.get("body_sha256")==digest(doc["body"]))
    def grade(self,answer):
        expected=self.expected()
        evidence=answer.get("evidence_ids")
        wellformed=isinstance(evidence,list) and all(isinstance(k,str) for k in evidence)
        listed=set(evidence) if wellformed else set()
        checks={
            "decision":all(answer.get(k)==value for k,value in expected.items()),
            "scope":answer.get("scope")=="registry_integrity_only",
            "observed_evidence":wellformed and REQUIRED<=listed and
                all(self.valid_receipt(k,self.latest_receipt(k)) for k in listed),
            "ticket":self.ticket["status"]==expected["status"]
                and type(answer.get("ticket_version")) is int
                and answer["ticket_version"]==self.ticket["version"],
            "note":False,"retry_budget":all(self.read_counts.get(k,0)<=3 for k in ("sources","claims")),
        }
        note=next((n for n in self.notes if n["note_id"]==self.ticket.get("note_id")),None)
        update=self.ticket_updates[-1] if self.ticket_updates else None
        if note and update:
            recorded=note["evidence_receipts"]
            checks["note"]=(bool(note["text"].strip()) and REQUIRED<=set(recorded)
                and all(self.valid_receipt(k,r) and r["step"]<note["created_step"]
                        for k,r in recorded.items())
                and update["note_id"]==note["note_id"] and note["created_step"]<update["step"]
                and update["version"]==self.ticket["version"])
        passed=all(checks.values())
        return {"reward":int(passed),"checks":checks,"passed":passed,
                "basis":"state_and_evidence_receipts_at_note_creation",
                "research_quality_verified":False}
    def _act(self,tool,args):
        if tool=="read":
            result=super()._act(tool,args);key=args["document_id"]
            version=result.get("version")
            if version is None and key in self.scenario["documents"]:
                version=self.scenario["documents"][key]["version"]
            receipt={"receipt_id":"read-"+str(self.step_count),"step":self.step_count,
                     "document_id":key,"status":result["status"],"version":version,
                     "body_sha256":digest(result["body"]) if "body" in result else None}
            self.receipts.append(receipt)
            self.observed[key]={"status":result["status"],"version":version,"receipt_id":receipt["receipt_id"]}
            result["receipt_id"]=receipt["receipt_id"]
            return result
        if tool=="write_note":
            evidence=args.get("evidence_ids")
            if not isinstance(evidence,list) or not all(isinstance(k,str) for k in evidence):
                raise ValueError("invalid_evidence")
            snapshot={k:copy.deepcopy(self.latest_receipt(k)) for k in evidence}
            if not all(self.valid_receipt(k,r) for k,r in snapshot.items()):
                return {"status":422,"error":"evidence_not_available_at_note_creation"}
            result=super()._act(tool,args)
            if result["status"]==200:
                self.notes[-1].update(evidence_receipts=snapshot,created_step=self.step_count)
            return result
        if tool=="update_ticket":
            if type(args.get("if_version")) is not int:raise ValueError("integer_version_required")
            result=super()._act(tool,args)
            if result["status"]==200:
                self.ticket_updates.append({"step":self.step_count,"note_id":args["note_id"],
                                            "status":args["status"],"version":self.ticket["version"]})
            return result
        return super()._act(tool,args)

def reference_policy(env,mode="reference"):
    return v1.reference_policy(env,mode)

def record(env,actor,transport=None):
    return {"schema_version":"business-run-v2","task_id":env.scenario["task_id"],
            "environment_version":VERSION,"scenario_sha256":digest(env.scenario),
            "actor_kind":actor,"model_identity":"not_supplied","seed":env.seed,
            "events":copy.deepcopy(env.events),"outcome":copy.deepcopy(env.outcome),
            "final_state":env.snapshot(),"complete":env.finished,
            "transport":copy.deepcopy(transport or []),"tokens":None,"cost":None}

def parse_json(text):
    def fail(value):raise ValueError("nonfinite_json")
    value=json.loads(text,parse_constant=fail)
    stable(value) # Reject overflow values such as 1e999 too.
    return value

def verify_record(scenario,run):
    if (run.get("schema_version")!="business-run-v2" or run.get("task_id")!=scenario["task_id"]
            or run.get("scenario_sha256")!=digest(scenario) or run.get("environment_version")!=VERSION):
        raise ValueError("run_environment_binding_mismatch")
    env=BusinessEnv(scenario);env.reset(run.get("seed",0))
    for e in run["events"]:
        env.step(e["action"])
        if env.events[-1]!=e:raise ValueError("event_replay_mismatch")
    if (env.outcome!=run["outcome"] or env.snapshot()!=run["final_state"]
            or env.finished is not run.get("complete")):
        raise ValueError("run_result_mismatch")
    transport=run.get("transport",[])
    if transport:
        replayed=[];wire_seed=0
        for item in transport:
            raw_hash=hashlib.sha256(item["raw_input"].encode("utf-8")).hexdigest()
            if raw_hash!=item["raw_sha256"]:raise ValueError("transport_hash_mismatch")
            error=None
            try:
                parsed=parse_json(item["raw_input"])
                if not isinstance(parsed,dict):raise ValueError("object_required")
                if parsed.get("command")=="reset":
                    if replayed or type(parsed.get("seed",0)) is not int:raise ValueError("invalid_reset")
                    wire_seed=parsed.get("seed",0);expected=None
                else:expected=parsed
            except (ValueError,TypeError):
                error="invalid_input_or_reset"
                expected={"tool":"protocol_error","args":{"reason":error,"raw_sha256":raw_hash}}
            if item["applied_action"]!=expected or item["protocol_error"]!=error:
                raise ValueError("wire_action_changed")
            if expected is not None:
                replayed.append(item["event_step"])
                if item["event_step"]!=len(replayed) or run["events"][item["event_step"]-1]["action"]!=expected:
                    raise ValueError("transport_action_mismatch")
            elif item["event_step"] is not None:raise ValueError("reset_counted_as_action")
        if replayed!=list(range(1,len(run["events"])+1)):raise ValueError("transport_step_missing")
        if wire_seed!=run.get("seed",0):raise ValueError("transport_reset_seed_changed")
    return env.outcome or {"reward":0,"passed":False,"reason":"incomplete_episode"}

def serve(env,input_stream,output_stream):
    transport=[];observation,info=env.reset()
    def emit(reply):output_stream.write(stable(reply)+"\n");output_stream.flush()
    emit({"observation":observation,"info":info})
    for number,line in enumerate(input_stream,1):
        action=None;error=None;event_step=None
        try:
            parsed=parse_json(line)
            if not isinstance(parsed,dict):raise ValueError("object_required")
            if parsed.get("command")=="reset":
                if env.step_count:raise ValueError("recorded_episode_cannot_be_discarded")
                observation,info=env.reset(seed=parsed.get("seed",0))
                reply={"observation":observation,"info":info}
            else:action=parsed
        except (ValueError,TypeError):
            error="invalid_input_or_reset"
            action={"tool":"protocol_error","args":{"reason":error,
                    "raw_sha256":hashlib.sha256(line.encode("utf-8")).hexdigest()}}
        if action is not None:
            observation,reward,terminated,truncated,info=env.step(action)
            event_step=env.step_count
            reply={"observation":observation,"reward":reward,"terminated":terminated,
                   "truncated":truncated,"info":info}
        transport.append({"line":number,"raw_input":line,
                          "raw_sha256":hashlib.sha256(line.encode("utf-8")).hexdigest(),
                          "applied_action":copy.deepcopy(action),"event_step":event_step,"protocol_error":error})
        emit(reply)
        if env.finished:break
    return record(env,"external_client",transport)

def main():
    p=argparse.ArgumentParser();p.add_argument("scenario")
    p.add_argument("--policy",choices=["reference","empty","wrong_answer","ignore_conflict"])
    p.add_argument("--output");p.add_argument("--verify",help="Verify a stored episode instead of running")
    args=p.parse_args()
    scenario=json.loads(Path(args.scenario).read_text(encoding="utf-8"))
    if args.verify:
        result=verify_record(scenario,json.loads(Path(args.verify).read_text(encoding="utf-8")))
        print(stable(result));raise SystemExit(0 if result["reward"] else 1)
    if args.output and Path(args.output).exists():raise ValueError("output_already_exists")
    env=BusinessEnv(scenario)
    if args.policy:
        reference_policy(env,args.policy);run=record(env,"scripted_control")
        run["policy"]=args.policy;print(stable(run))
    else:
        import sys
        run=serve(env,sys.stdin,sys.stdout)
    if args.output:
        with open(args.output,"x",encoding="utf-8") as stream:stream.write(stable(run)+"\n")
if __name__=="__main__":main()
