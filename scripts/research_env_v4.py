"""Longer evidence dependencies, unresolved conflicts and verified multi-claim repairs."""
from __future__ import annotations
import argparse,copy,json,sys
from pathlib import Path
import research_env_v3 as base
VERSION="research-runtime-4"
TOOLS=base.TOOLS
SCOPES={"evidence_chain":"supplied_dependency_graph","evidence_conflict":"supplied_authority_policy","revision_workflow":"verified_review_batch"}
LIMITS=["synthetic_material","no_external_verification","as_of_snapshot"]
canonical,digest,check,equal,render=base.canonical,base.digest,base.check,base.equal,base.render

def available(scenario,key):
    return key in scenario["documents"] and scenario["documents"][key]["available_at"]<=scenario["as_of"]

def required_documents(scenario):
    required={};queue=list(scenario["entry_documents"])
    while queue:
        key=queue.pop(0)
        if key in required:continue
        if not available(scenario,key):required[key]=set();continue
        body=scenario["documents"][key]["body"]
        required[key]={row["row_id"] for row in body.get("rows",[])}
        queue.extend(body.get("references",[]))
    return required

def graph_value(documents,node,visiting=None):
    visiting=set() if visiting is None else set(visiting)
    check(node not in visiting,"cyclic_dependency");visiting.add(node)
    row=documents[node]["body"]["rows"][0]
    if row["kind"]=="value":return row["value"]*{"units":1,"thousand_units":1000}[row["unit"]]
    values=[graph_value(documents,key,visiting) for key in row["inputs"]]
    if row["kind"]=="sum":return sum(values)
    check(row["kind"]=="subtract" and len(values)==2,"unsupported_graph_operation")
    return values[0]-values[1]

def expected(scenario,documents):
    required=required_documents(scenario);missing=sorted(key for key in required if not available(scenario,key))
    initial=scenario["documents"];mechanism=scenario["mechanism"]
    if missing:
        return {"status":"blocked","result":{"unavailable_documents":missing},"limitations":LIMITS+["unavailable_evidence"]},required,documents["claims"]==initial["claims"]
    if mechanism=="evidence_chain":
        claim=initial["claims"]["body"]["rows"][0];value=graph_value(initial,initial["handoff"]["body"]["root_node"])
        result={"metric":claim["metric"],"value":value,"unit":"units","claim_supported":equal(value,claim["value"]) and claim["unit"]=="units"}
        return {"status":"ready" if result["claim_supported"] else "needs_revision","result":result,"limitations":LIMITS},required,documents["claims"]==initial["claims"]
    if mechanism=="evidence_conflict":
        witnesses=[initial[key]["body"]["rows"][0] for key in initial["handoff"]["body"]["witnesses"]]
        highest=max(row["authority"] for row in witnesses);leaders=[row for row in witnesses if row["authority"]==highest]
        same=len({canonical([row["value"],row["unit"]]) for row in leaders})==1
        result={"resolution":"resolved" if same else "unresolved_conflict","value":leaders[0]["value"] if same else None,"unit":leaders[0]["unit"]}
        return {"status":"ready" if same else "blocked","result":result,"limitations":LIMITS+([] if same else ["unresolved_peer_conflict"])},required,documents["claims"]==initial["claims"]
    findings=initial["review"]["body"]["rows"];resolved=[];rejected=[];corrections={}
    for finding in findings:
        fact=initial[finding["source_document"]]["body"]["rows"][0]
        supported=equal(finding["proposed_value"],fact["value"]) and finding["unit"]==fact["unit"]
        (resolved if supported else rejected).append(finding["row_id"])
        if supported:corrections[finding["claim_id"]]={"claim_id":finding["claim_id"],"value":fact["value"],"unit":fact["unit"]}
    current={row["row_id"]:row for row in documents["claims"]["body"]["rows"]}
    fixed=all(equal(current[key]["value"],row["value"]) and current[key]["unit"]==row["unit"] for key,row in corrections.items())
    untouched=all(equal(current[row["row_id"]],row) for row in initial["claims"]["body"]["rows"] if row["row_id"] not in corrections)
    result={"resolved_findings":sorted(resolved),"rejected_findings":sorted(rejected),"remaining_findings":[],"corrected_claims":[corrections[key] for key in sorted(corrections)]}
    return {"status":"ready","result":result,"limitations":LIMITS},required,fixed and untouched

def report_shape(report):
    if not isinstance(report,dict) or report.get("scope") not in SCOPES.values():return False
    converted=copy.deepcopy(report);converted["scope"]="snapshot_evidence_only"
    return base.report_shape(converted)

class ResearchEnv(base.ResearchEnv):
    def __init__(self,scenario):
        self.scenario=copy.deepcopy(scenario)
        check(scenario["version"]==VERSION and scenario["mechanism"] in SCOPES,"unsupported_scenario")
        check(type(scenario["max_steps"]) is int and 16<=scenario["max_steps"]<=100,"invalid_budget")
        self.reset()

    def reset(self,seed=0):
        super().reset(seed);self.revisions=[]
        self.ticket["id"]="task-"+digest(self.scenario["task_id"])[:16]
        self.initial["task_id"]=self.ticket["id"];self.initial["ticket"]=copy.deepcopy(self.ticket)
        self.initial["documents"]=list(self.scenario["entry_documents"])
        return copy.deepcopy(self.initial),{"environment_version":VERSION,"seed":seed}

    def snapshot(self):
        state=super().snapshot();state["revisions"]=copy.deepcopy(self.revisions);return state

    def _action(self,action,step):
        if not isinstance(action,dict) or set(action)!={"tool","args"} or not isinstance(action["args"],dict):return {"status":400,"error":"invalid_action"}
        tool,args=action["tool"],action["args"]
        if tool=="search":
            if set(args)!={"query"} or not isinstance(args["query"],str):return {"status":422,"error":"query_string_required"}
            return {"status":200,"documents":[key for key in sorted(self.documents) if available(self.scenario,key) and args["query"].lower() in (key+canonical(self.documents[key]["body"])).lower()]}
        if tool=="read":
            if set(args)!={"document_id"} or not isinstance(args["document_id"],str):return {"status":422,"error":"document_id_required"}
            key=args["document_id"];self.attempts[key]=self.attempts.get(key,0)+1
            status=200 if available(self.scenario,key) else 404
            if status==200 and self.scenario["fault"]=="tool_retry" and key==self.scenario["fault_document"] and self.attempts[key]<=2:status=429
            version=self.documents[key]["version"] if status==200 else None
            body=copy.deepcopy(self.documents[key]["body"]) if status==200 else None
            receipt={"document_id":key,"version":version,"status":status,"step":step,"body_sha256":digest(body)};self.receipts.append(receipt)
            result={"status":status,"document_id":key,"version":version,"receipt":copy.deepcopy(receipt)}
            if body is not None:result["body"]=body
            if status==404:result["error"]="document_unavailable"
            if status==429:result["error"]="transient_rate_limit"
            return result
        if tool=="revise_claim":
            if set(args)!={"if_version","claim_id","value","unit"} or type(args.get("if_version")) is not int or type(args.get("value")) is not int or not isinstance(args.get("unit"),str):return {"status":422,"error":"revision_contract"}
            if self.scenario["mechanism"]!="revision_workflow" or args["claim_id"] not in self.scenario["editable_claims"]:return {"status":403,"error":"revision_not_in_scope"}
            doc=self.documents["claims"]
            if self.scenario["fault"]=="stale_revision" and not self.conflict_injected:
                self.conflict_injected=True;doc["version"]+=1;doc["body"]["concurrent_note"]="Another editor added a note; keep all unrelated claims."
                return {"status":409,"error":"claim_version_conflict","message":"Read current claims before revising."}
            if args["if_version"]!=doc["version"]:return {"status":409,"error":"claim_version_conflict"}
            if not any(r["document_id"]=="claims" and r["status"]==200 and r["version"]==doc["version"] and r["body_sha256"]==digest(doc["body"]) for r in self.receipts):return {"status":412,"error":"read_current_claims_before_revision"}
            row=next(r for r in doc["body"]["rows"] if r["row_id"]==args["claim_id"])
            row.update(value=args["value"],unit=args["unit"]);doc["version"]+=1
            self.revisions.append({"step":step,"claim_id":args["claim_id"],"value":args["value"],"unit":args["unit"],"version":doc["version"]})
            return {"status":200,"document_id":"claims","version":doc["version"],"message":"Reread claims before another revision or a final note."}
        if tool=="write_note":
            report=args.get("report")
            if set(args)-{"report","text"} or not report_shape(report):return {"status":422,"error":"structured_report_required"}
            if "text" in args and args["text"]!=render(report):return {"status":422,"error":"text_disagrees_with_structured_report"}
            key="note-"+str(len(self.notes)+1);self.notes[key]={"report":copy.deepcopy(report),"text":render(report),"created_step":step,"read_receipts":copy.deepcopy(self.receipts)}
            return {"status":200,"note_id":key}
        return super()._action(action,step)

    def step(self,action):
        observation,reward,terminated,truncated,info=super().step(action)
        self.events[-1]["reward"]=reward
        return observation,reward,terminated,truncated,info

    def grade(self):
        exp,required,resolved=expected(self.scenario,self.documents)
        note=self.notes.get((self.submission or {}).get("note_id"));report=(note or {}).get("report",{})
        revised={r["claim_id"] for r in self.revisions}
        if self.scenario["mechanism"]=="revision_workflow" and exp["status"]=="ready":resolved=resolved and set(self.scenario["editable_claims"])<=revised
        checks={"terminal":self.terminated and not self.truncated,"structured_report":report_shape(report),
            "correct_result":all(equal(report.get(key),value) for key,value in exp.items()),"scope":report.get("scope")==SCOPES[self.scenario["mechanism"]],
            "task_resolution":resolved,"evidence_links":False,"note_content":False,"ticket":False,
            "retry_budget":self.scenario["fault"]!="tool_retry" or self.attempts.get(self.scenario["fault_document"],0)<=3}
        if note and report_shape(report):
            citations=report["citations"];valid=len(citations)==len(required) and {c["document_id"] for c in citations}==set(required)
            for cite in citations:
                key=cite["document_id"]
                if key not in required:valid=False;continue
                status=200 if available(self.scenario,key) else 404
                body=self.documents[key]["body"] if status==200 else None;version=self.documents[key]["version"] if status==200 else None
                valid=valid and cite["status"]==status and equal(cite["version"],version) and len(cite["row_ids"])==len(required[key]) and set(cite["row_ids"])==required[key]
                valid=valid and any(r["document_id"]==key and r["status"]==status and equal(r["version"],version) and r["body_sha256"]==digest(body) for r in note["read_receipts"])
            checks["evidence_links"]=bool(valid);checks["note_content"]=note["text"]==render(report)
            checks["ticket"]=self.ticket["status"]==report["status"] and self.ticket["note_id"]==self.submission.get("note_id") and equal(self.ticket["version"],self.submission.get("ticket_version"))
        return {"reward":int(all(checks.values())),"checks":checks,"grader_version":VERSION,"assessed_capability":"bounded_dependency_conflict_revision","research_truth_assessed":False}

def record(env,actor_kind):
    value=base.record(env,actor_kind);value["environment_version"]=VERSION;return value

def verify_record(scenario,run):
    env=ResearchEnv(scenario);initial,_=env.reset(run["seed"])
    check(run["environment_version"]==VERSION and run["task_id"]==scenario["task_id"] and run["scenario_sha256"]==digest(scenario),"scenario_binding_changed")
    check(equal(initial,run["initial_observation"]),"initial_observation_changed")
    for event in run["events"]:
        env.step(event["action"]);check(equal(env.events[-1],event),"event_replay_changed")
    check(equal(env.snapshot(),run["final_state"]) and run["complete"]==env.finished,"final_state_changed")
    check(equal(env.grade(),run["grade"]),"grade_changed");return env.grade()

def main():
    parser=argparse.ArgumentParser();parser.add_argument("scenario");parser.add_argument("--output",required=True);args=parser.parse_args()
    env=ResearchEnv(json.loads(Path(args.scenario).read_text(encoding="utf-8-sig")));print(canonical({"observation":env.initial}),flush=True)
    for line in sys.stdin:
        if not line.strip():continue
        try:observation,reward,terminated,truncated,info=env.step(json.loads(line))
        except (ValueError,TypeError,KeyError) as error:print(canonical({"error":str(error)}),flush=True);continue
        Path(args.output).write_text(canonical(record(env,"external_policy"))+"\n",encoding="utf-8",newline="\n")
        print(canonical({"observation":observation,"reward":reward,"terminated":terminated,"truncated":truncated,"info":info}),flush=True)
        if env.finished:break
if __name__=="__main__":main()
