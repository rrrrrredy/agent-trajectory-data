"""Versioned research deliverables with evidence refresh and uncertain write recovery.
Only public tool observations enter the policy; frozen source facts remain bounded evidence.
"""
from __future__ import annotations
import argparse,copy,json,sys
from pathlib import Path
import research_env_v3 as base
VERSION="research-workspace-1"
TOOLS=("search","read","read_ticket","revise_artifact","operation_status","validate","write_note","update_ticket","submit")
canonical,digest,check,equal=base.canonical,base.digest,base.check,base.equal
POLICY={
 "scope":"Resolve the supplied frozen evidence only. Report assertions and synthetic measurements are not independent verification of external reality.",
 "workflow":"Read brief and its evidence references. Reconcile BOTH deliverables using brief.outputs and decision_rule; preserve each deliverable's preserved text. Read before writing and reread after writes. Run validate on the final state, write_note, update_ticket and submit. A ready ticket means the assigned reconciliation is complete; the substantive decision may still be unsupported.",
 "content_contract":{"result":"mapping of output names to {value,unit}, computed from brief.outputs","decision":"brief.decision_rule result","scope":"brief.result_scope","citations":"one {document_id,version,row_ids} per required evidence document, using current observations","preserved":"exact existing preserved text from this artifact"},
 "expressions":"A ref is {ref:[document_id,row_id]} and returns that row's value. op accepts sum, subtract (left minus right), multiply, floor_divide, minimum, maximum with args expressions. Outputs name their required unit. A literal decision uses literal; threshold compares its named output using >= or <=, choosing yes/no.",
 "versions":"A 409 can mean evidence changed or an artifact version changed. Read the indicated current documents and recompute affected outputs. Never cite a version before reading it.",
 "uncertain_write":"504 is an unknown write outcome, not proof that nothing happened. Inspect operation_status with the SAME operation_id. committed means the original operation applied; absent permits retry of the same payload and key. Retrying the exact same key/payload is idempotent. New keys can cause duplicate effects.",
 "missing_evidence":"If required evidence returns 404, preserve both initial deliverables, validate, and submit blocked with the missing document IDs. Never infer its unseen content.",
 "note_contract":{"status":"ready or blocked","scope":"research_workspace_reconciliation","artifact_versions":"mapping of both artifact IDs to their current versions","validation_id":"latest passing validate receipt","missing_documents":"sorted missing required IDs, otherwise []","diagnosis":"brief visible explanation of the observations and changes"},
 "grading":"Validate checks public consistency and freshness, not the correctness of the research result. Terminal grading also computes results from the supplied evidence and checks scope, protected content, citations at write time, current-version rereads and duplicate effects. Freeform diagnosis is retained but not semantically graded. Different valid read and write orders are accepted."}
HELP={
 "search":{"args":{"query":"literal substring; empty lists available document IDs"}},
 "read":{"args":{"document_id":"a document from initial observation or brief references"}},
 "read_ticket":{"args":{}},
 "revise_artifact":{"args":{"document_id":"one of brief.artifact_ids","if_version":"current integer version","operation_id":"unique stable string for this intended write; reuse for uncertain retry","content":"policy.content_contract object"}},
 "operation_status":{"args":{"operation_id":"original write key"}},
 "validate":{"args":{}},
 "write_note":{"args":{"report":"policy.note_contract object"}},
 "update_ticket":{"args":{"if_version":"current ticket version","status":"same as note status","note_id":"returned note ID"}},
 "submit":{"args":{"note_id":"returned note ID","ticket_version":"current ticket version"}}}

def expression(spec,documents):
    if "ref" in spec:
        key,row=spec["ref"];return next(x["value"] for x in documents[key]["body"]["rows"] if x["row_id"]==row)
    values=[expression(x,documents) for x in spec["args"]];op=spec["op"]
    check(values and all(type(v) is int for v in values),"non_numeric_expression")
    if op=="sum":return sum(values)
    if op=="minimum":return min(values)
    if op=="maximum":return max(values)
    check(len(values)==2,"binary_operation_arity")
    if op=="subtract":return values[0]-values[1]
    if op=="multiply":return values[0]*values[1]
    check(op=="floor_divide" and values[1]!=0,"invalid_division");return values[0]//values[1]

def expected_content(documents):
    brief=documents["brief"]["body"]
    result={name:{"value":expression(spec["expression"],documents),"unit":spec["unit"]} for name,spec in brief["outputs"].items()}
    rule=brief["decision_rule"]
    if "literal" in rule:decision=rule["literal"]
    else:
        value=result[rule["output"]]["value"];passed=value>=rule["threshold"] if rule["operator"]==">=" else value<=rule["threshold"]
        decision=rule["yes"] if passed else rule["no"]
    return {"result":result,"decision":decision,"scope":brief["result_scope"]}

def content_shape(value):
    if not isinstance(value,dict) or set(value)!={"result","decision","scope","citations","preserved"}:return False
    if not isinstance(value["result"],dict) or not all(isinstance(value[k],str) for k in ("decision","scope","preserved")):return False
    if not isinstance(value["citations"],list):return False
    return all(isinstance(c,dict) and set(c)=={"document_id","version","row_ids"} and isinstance(c["document_id"],str) and type(c["version"]) is int and isinstance(c["row_ids"],list) and all(isinstance(x,str) for x in c["row_ids"]) for c in value["citations"])

def render_artifact(key,content):
    if key.endswith('.json'):return json.dumps(content,ensure_ascii=False,sort_keys=True,indent=2)+"\n"
    rows=["# Reconciled research note", "",content["preserved"],"", "Scope: "+content["scope"],"Decision: "+content["decision"],""]
    rows.extend(name+": "+canonical(value) for name,value in sorted(content["result"].items()))
    rows.extend(["","Evidence:"]+[c["document_id"]+" version "+str(c["version"])+" rows "+", ".join(c["row_ids"]) for c in content["citations"]])
    return "\n".join(rows)+"\n"

class ResearchEnv(base.ResearchEnv):
    def __init__(self,scenario):
        self.scenario=copy.deepcopy(scenario);check(scenario["version"]==VERSION,"unsupported_scenario")
        check(24<=scenario["max_steps"]<=48,"invalid_budget");self.reset()
    def reset(self,seed=0):
        check(type(seed) is int,"invalid_seed");self.seed=seed;self.documents=copy.deepcopy(self.scenario["documents"])
        self.ticket={"id":"task-"+digest(self.scenario["task_id"])[:16],"version":1,"status":"open","note_id":None}
        self.notes={};self.receipts=[];self.events=[];self.operations={};self.validations=[];self.external_events=[];self.uncertain=[]
        self.finished=self.terminated=self.truncated=False;self.submission=None;self.conflict_injected=False
        self.initial={"task_id":self.ticket["id"],"mechanism":"research_workspace","task":"Reconcile a report and its analysis file against the supplied evidence; diagnose failures and verify the final deliverables.","max_steps":self.scenario["max_steps"],"documents":["policy","brief",*self.artifacts],"tools":HELP,"ticket":copy.deepcopy(self.ticket)}
        return copy.deepcopy(self.initial),{"environment_version":VERSION,"seed":seed}
    @property
    def brief(self):return self.documents["brief"]["body"]
    @property
    def artifacts(self):return self.documents["brief"]["body"]["artifact_ids"]
    def available(self,key):return key in self.documents and key not in self.scenario["unavailable_documents"]
    def missing(self):return sorted(k for k in self.brief["evidence_ids"] if not self.available(k))
    def snapshot(self):
        return copy.deepcopy({"documents":self.documents,"ticket":self.ticket,"notes":self.notes,"receipts":self.receipts,"operations":self.operations,"validations":self.validations,"external_events":self.external_events,"uncertain":self.uncertain,"submission":self.submission,"terminated":self.terminated,"truncated":self.truncated})
    def read_current(self,key,receipts=None):
        doc=self.documents[key]
        return any(r["document_id"]==key and r["status"]==200 and r["version"]==doc["version"] and r["body_sha256"]==digest(doc["body"]) for r in (self.receipts if receipts is None else receipts))
    def citations_valid(self,content,receipts):
        cs=content.get("citations",[]);keys=self.brief["evidence_ids"]
        if len(cs)!=len(keys) or {x["document_id"] for x in cs}!=set(keys):return False
        return all(self.available(c["document_id"]) and c["version"]==self.documents[c["document_id"]]["version"] and len(c["row_ids"])==len(set(c["row_ids"])) and set(c["row_ids"])=={r["row_id"] for r in self.documents[c["document_id"]]["body"]["rows"]} and self.read_current(c["document_id"],receipts) for c in cs)
    def artifact_state(self):return {key:{"version":self.documents[key]["version"],"body_sha256":digest(self.documents[key]["body"])} for key in self.artifacts}
    def required_preserved(self,key):
        text=self.scenario["documents"][key]["body"]["content"]["preserved"]
        if any(x["kind"]=="artifact_revision" and x["document_id"]==key for x in self.external_events):text+="\nConcurrent editor: keep the supplied evidence boundary."
        return text
    def public_checks(self):
        missing=self.missing();contents=[self.documents[k]["body"]["content"] for k in self.artifacts]
        if missing:
            return {"unavailable_observed":all(any(r["document_id"]==k and r["status"]==404 for r in self.receipts) for k in missing),"deliverables_unchanged":all(equal(self.documents[k],self.scenario["documents"][k]) for k in self.artifacts)}
        return {"artifact_agreement":all(equal({k:c[k] for k in ("result","decision","scope","citations")},{k:contents[0][k] for k in ("result","decision","scope","citations")}) for c in contents),"current_evidence":all(self.citations_valid(c,self.receipts) for c in contents),"fresh_artifact_reads":all(self.read_current(k) for k in self.artifacts),"protected_text":all(c["preserved"]==self.required_preserved(k) for k,c in zip(self.artifacts,contents))}
    def _action(self,action,step):
        if not isinstance(action,dict) or set(action)!={"tool","args"} or not isinstance(action["args"],dict):return {"status":400,"error":"invalid_action"}
        tool,args=action["tool"],action["args"]
        if tool not in TOOLS:return {"status":400,"error":"unknown_tool"}
        if tool=="search":
            if set(args)!={"query"} or not isinstance(args["query"],str):return {"status":422,"error":"query_string_required"}
            return {"status":200,"documents":[k for k in sorted(self.documents) if self.available(k) and args["query"].lower() in (k+canonical(self.documents[k]["body"])).lower()]}
        if tool=="read":
            if set(args)!={"document_id"} or not isinstance(args["document_id"],str):return {"status":422,"error":"document_id_required"}
            key=args["document_id"];status=200 if self.available(key) else 404;doc=self.documents.get(key) if status==200 else None
            receipt={"document_id":key,"status":status,"version":doc["version"] if doc else None,"body_sha256":digest(doc["body"] if doc else None),"step":step};self.receipts.append(receipt)
            out={"status":status,"document_id":key,"version":receipt["version"],"receipt":copy.deepcopy(receipt)}
            if doc:out["body"]=copy.deepcopy(doc["body"])
            else:out["error"]="document_unavailable"
            return out
        if tool=="operation_status":
            if set(args)!={"operation_id"} or not isinstance(args["operation_id"],str):return {"status":422,"error":"operation_id_required"}
            op=self.operations.get(args["operation_id"])
            return {"status":200,"operation_id":args["operation_id"],"state":"committed" if op else "absent",**({"document_id":op["document_id"],"version":op["version"],"content_sha256":op["content_sha256"]} if op else {})}
        if tool=="revise_artifact":
            if set(args)!={"document_id","if_version","operation_id","content"} or type(args.get("if_version")) is not int or not all(isinstance(args.get(k),str) and bool(args[k]) for k in ("document_id","operation_id")) or not content_shape(args.get("content")):return {"status":422,"error":"artifact_contract"}
            key=args["document_id"];oid=args["operation_id"]
            if key not in self.artifacts:return {"status":403,"error":"artifact_not_editable"}
            if oid in self.operations:
                op=self.operations[oid]
                if op["payload_sha256"]!=digest(args):return {"status":409,"error":"operation_key_payload_conflict"}
                return {"status":200,"operation_id":oid,"document_id":key,"version":op["version"],"replayed":True}
            fault=self.scenario["fault"]
            if fault=="source_refresh" and not self.external_events:
                for update in self.scenario["source_updates"]:
                    doc=self.documents[update["document_id"]];row=next(x for x in doc["body"]["rows"] if x["row_id"]==update["row_id"]);row["value"]=update["value"];doc["version"]+=1
                    self.external_events.append({"kind":"source_revision","document_id":update["document_id"],"version":doc["version"],"step":step})
                return {"status":409,"error":"evidence_revision_conflict","changed_documents":[x["document_id"] for x in self.external_events]}
            if fault=="stale_artifact" and not self.external_events:
                self.external_events.append({"kind":"artifact_revision","document_id":key,"step":step});doc=self.documents[key];doc["body"]["content"]["preserved"]=self.required_preserved(key);doc["version"]+=1
                return {"status":409,"error":"artifact_version_conflict","changed_documents":[key]}
            doc=self.documents[key]
            if args["if_version"]!=doc["version"]:return {"status":409,"error":"artifact_version_conflict","changed_documents":[key]}
            if not self.read_current(key):return {"status":412,"error":"read_current_artifact"}
            if fault=="uncertain_not_applied" and not self.uncertain:
                self.uncertain.append({"operation_id":oid,"document_id":key,"step":step,"applied":False});return {"status":504,"error":"unknown_write_outcome","operation_id":oid}
            doc["body"]["content"]=copy.deepcopy(args["content"]);doc["version"]+=1
            self.operations[oid]={"document_id":key,"version":doc["version"],"payload_sha256":digest(args),"content_sha256":digest(args["content"]),"read_receipts":copy.deepcopy(self.receipts),"content":copy.deepcopy(args["content"]),"step":step}
            if fault=="uncertain_applied" and not self.uncertain:
                self.uncertain.append({"operation_id":oid,"document_id":key,"step":step,"applied":True});return {"status":504,"error":"unknown_write_outcome","operation_id":oid}
            return {"status":200,"document_id":key,"version":doc["version"],"operation_id":oid,"replayed":False}
        if tool=="validate":
            if args:return {"status":422,"error":"no_arguments"}
            checks=self.public_checks();validation={"validation_id":"validation-"+str(len(self.validations)+1),"checks":checks,"passed":all(checks.values()),"artifact_state":self.artifact_state(),"step":step};self.validations.append(validation)
            return {"status":200,"validation":copy.deepcopy(validation)}
        if tool=="write_note":
            report=args.get("report")
            if set(args)!={"report"} or not isinstance(report,dict) or set(report)!={"status","scope","artifact_versions","validation_id","missing_documents","diagnosis"} or report["status"] not in ("ready","blocked") or not isinstance(report["artifact_versions"],dict) or not isinstance(report["missing_documents"],list) or not all(isinstance(report[k],str) for k in ("scope","validation_id","diagnosis")):return {"status":422,"error":"note_contract"}
            key="note-"+str(len(self.notes)+1);self.notes[key]={"report":copy.deepcopy(report),"created_step":step,"artifact_state":self.artifact_state(),"read_receipts":copy.deepcopy(self.receipts),"validation_ids":[x["validation_id"] for x in self.validations]};return {"status":200,"note_id":key}
        return super()._action(action,step)
    def step(self,action):
        result=super().step(action);self.events[-1]["reward"]=result[1];return result
    def grade(self):
        missing=self.missing();note=self.notes.get((self.submission or {}).get("note_id"));report=(note or {}).get("report",{});latest=self.validations[-1] if self.validations else {}
        checks={"terminal":self.terminated and not self.truncated,"contract_read":self.read_current("brief"),"correct_content":False,"protected_content":all(self.documents[k]["body"]["content"]["preserved"]==self.required_preserved(k) for k in self.artifacts),"actual_reconciliation":False,"write_time_evidence":False,"fresh_reads":all(self.read_current(k) for k in self.artifacts),"validated_current_state":bool(latest.get("passed")) and equal(latest.get("artifact_state"),self.artifact_state()),"no_duplicate_effects":len({(x["document_id"],x["content_sha256"]) for x in self.operations.values()})==len(self.operations),"verified_note":False,"ticket":False}
        if missing:
            checks["correct_content"]=checks["actual_reconciliation"]=all(equal(self.documents[k],self.scenario["documents"][k]) for k in self.artifacts)
            checks["write_time_evidence"]=all(any(r["document_id"]==k and r["status"]==404 for r in self.receipts) for k in missing)
        else:
            expected=expected_content(self.documents)
            checks["correct_content"]=all(all(equal(self.documents[key]["body"]["content"].get(k),v) for k,v in expected.items()) for key in self.artifacts)
            checks["actual_reconciliation"]=all(any(op["document_id"]==key for op in self.operations.values()) for key in self.artifacts)
            checks["write_time_evidence"]=all(any(op["document_id"]==key and op["version"]==self.documents[key]["version"] and self.citations_valid(op["content"],op["read_receipts"]) for op in self.operations.values()) for key in self.artifacts)
        if note:
            checks["verified_note"]=report.get("status")==("blocked" if missing else "ready") and report.get("scope")=="research_workspace_reconciliation" and report.get("missing_documents")==missing and report.get("artifact_versions")=={k:self.documents[k]["version"] for k in self.artifacts} and report.get("validation_id")==latest.get("validation_id") and report.get("validation_id") in note["validation_ids"] and equal(note["artifact_state"],self.artifact_state()) and all(self.read_current(k,note["read_receipts"]) for k in self.artifacts) and bool(report.get("diagnosis","").strip())
            checks["ticket"]=self.ticket["status"]==report.get("status") and self.ticket["note_id"]==self.submission["note_id"] and self.ticket["version"]==self.submission["ticket_version"]
        return {"reward":int(all(checks.values())),"checks":checks,"grader_version":VERSION,"assessed_capability":"bounded_research_deliverable_reconciliation","research_truth_assessed":False}
    def deliverables(self):return {key:render_artifact(key,self.documents[key]["body"]["content"]) for key in self.artifacts}

def record(env,actor_kind):
    result=base.record(env,actor_kind);result["environment_version"]=VERSION;return result

def verify_record(scenario,run):
    env=ResearchEnv(scenario);initial,_=env.reset(run["seed"])
    check(run["environment_version"]==VERSION and run["task_id"]==scenario["task_id"] and run["scenario_sha256"]==digest(scenario),"scenario_binding_changed");check(equal(initial,run["initial_observation"]),"initial_observation_changed")
    for event in run["events"]:env.step(event["action"]);check(equal(env.events[-1],event),"event_replay_changed")
    check(equal(env.snapshot(),run["final_state"]) and run["complete"]==env.finished,"final_state_changed");check(equal(env.grade(),run["grade"]),"grade_changed");return env.grade()

def main():
    p=argparse.ArgumentParser();p.add_argument("scenario");p.add_argument("--output",required=True);a=p.parse_args();env=ResearchEnv(json.loads(Path(a.scenario).read_bytes()));print(canonical({"observation":env.initial}),flush=True)
    for line in sys.stdin:
        if not line.strip():continue
        observation,reward,terminated,truncated,info=env.step(json.loads(line));Path(a.output).write_text(canonical(record(env,"external_policy"))+"\n",encoding="utf-8",newline="\n");print(canonical({"observation":observation,"reward":reward,"terminated":terminated,"truncated":truncated,"info":info}),flush=True)
        if env.finished:break
if __name__=="__main__":main()
