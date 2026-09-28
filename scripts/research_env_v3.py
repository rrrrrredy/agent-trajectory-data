"""Versioned, executable synthetic research tasks with structured evidence grading.
Only reset/step observations are exposed to a policy. Scenario and grade are evaluator-only.
"""
from __future__ import annotations
import argparse, copy, hashlib, json, sys
from pathlib import Path
VERSION = "research-runtime-3"
TOOLS = ("search", "read", "read_ticket", "revise_claim", "write_note", "update_ticket", "submit")
SCOPES = {"evidence_update": "snapshot_evidence_only", "numeric_consistency": "period_metric_only",
          "review_revision": "review_findings_only"}

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def check(condition, message):
    if not condition: raise ValueError(message)

def equal(left, right):
    return canonical(left) == canonical(right)

def render(report):
    # No unrestricted assertion is accepted as the delivered note. Preserve the submitted
    # structured content, then bind its exact rendering and evidence to terminal grading.
    return "\n".join(["Conclusion: " + report["status"], "Scope: " + report["scope"],
        "Result: " + canonical(report["result"]), "Limitations: " + canonical(report["limitations"]),
        "Evidence: " + canonical(report["citations"])])

def report_shape(report):
    if not isinstance(report, dict) or set(report) != {"status", "scope", "result", "limitations", "citations"}: return False
    if report["status"] not in ("ready", "needs_revision", "blocked") or report["scope"] not in SCOPES.values(): return False
    if not isinstance(report["result"], (dict, type(None))): return False
    if not isinstance(report["limitations"], list) or not all(isinstance(x,str) for x in report["limitations"]): return False
    if not isinstance(report["citations"], list): return False
    for citation in report["citations"]:
        if not isinstance(citation, dict) or set(citation) != {"document_id", "version", "status", "row_ids"}: return False
        if not isinstance(citation["document_id"], str) or type(citation["status"]) is not int: return False
        if citation["version"] is not None and type(citation["version"]) is not int: return False
        if not isinstance(citation["row_ids"], list) or not all(isinstance(x,str) for x in citation["row_ids"]): return False
    return True

def expected(scenario, documents):
    """Evaluator computes answers from frozen inputs; never included in observations."""
    mechanism = scenario["mechanism"]
    denied = scenario["fault"] == "access_revoked"
    limitations = ["synthetic_material", "no_external_verification", "as_of_snapshot"]
    if denied:
        return {"status":"blocked", "result":None, "limitations":limitations + ["source_access_denied"]}, {}, True
    claim = scenario["documents"]["claims"]["body"]["rows"][0]
    rows = scenario["documents"]["sources"]["body"]["rows"]
    if mechanism == "evidence_update":
        valid = [r for r in rows if r["metric"] == claim["metric"] and r["effective_at"] <= scenario["as_of"]]
        chosen = max(valid, key=lambda r:(r["effective_at"],r["revision"]))
        result = {"metric":claim["metric"], "as_of":scenario["as_of"], "value":chosen["value"], "unit":chosen["unit"],
                  "claim_supported":equal(claim["value"],chosen["value"]) and claim["unit"]==chosen["unit"]}
        used = {chosen["row_id"]}
        status = "ready" if result["claim_supported"] else "needs_revision"
        resolved = True
    elif mechanism == "numeric_consistency":
        selected = [r for r in rows if r["metric"]==claim["metric"] and r["period"]==claim["period"]]
        total = sum(r["value"] * {"units":1,"thousand_units":1000}[r["unit"]] for r in selected)
        result = {"metric":claim["metric"], "period":claim["period"], "value":total, "unit":"units",
                  "claim_supported":equal(claim["value"],total) and claim["unit"]=="units"}
        used = {r["row_id"] for r in selected}
        status = "ready" if result["claim_supported"] else "needs_revision"
        resolved = True
    else:
        fact = next(r for r in rows if r["metric"]==claim["metric"])
        findings = scenario["documents"]["review"]["body"]["rows"]
        supported = [f["row_id"] for f in findings if equal(f["proposed_value"],fact["value"]) and f["unit"]==fact["unit"]]
        rejected = [f["row_id"] for f in findings if f["row_id"] not in supported]
        result = {"resolved_findings":sorted(supported), "rejected_findings":sorted(rejected), "remaining_findings":[]}
        current = documents["claims"]["body"]["rows"][0]
        resolved = equal(current["value"],fact["value"]) and current["unit"]==fact["unit"] and documents["claims"]["version"]>1
        used, status = {fact["row_id"]}, "ready"
    return {"status":status,"result":result,"limitations":limitations}, {"sources":used}, resolved

class ResearchEnv:
    def __init__(self, scenario):
        self.scenario = copy.deepcopy(scenario)
        check(scenario["version"]==VERSION and scenario["mechanism"] in SCOPES,"unsupported_scenario")
        check(type(scenario["max_steps"]) is int and 12<=scenario["max_steps"]<=100,"invalid_budget")
        self.reset()

    def reset(self, seed=0):
        check(type(seed) is int,"invalid_seed")
        self.seed=seed; self.documents=copy.deepcopy(self.scenario["documents"])
        self.ticket={"id":self.scenario["task_id"],"version":1,"status":"open","note_id":None}
        self.notes={}; self.receipts=[]; self.events=[]; self.attempts={}; self.finished=False
        self.terminated=False; self.truncated=False; self.conflict_injected=False; self.submission=None
        self.initial={"task_id":self.scenario["task_id"],"mechanism":self.scenario["mechanism"],
                      "as_of":self.scenario["as_of"],"task":self.scenario["instruction"],
                      "max_steps":self.scenario["max_steps"],"tools":self.scenario["tool_help"],
                      "documents":self.scenario["document_order"],"ticket":copy.deepcopy(self.ticket)}
        return copy.deepcopy(self.initial), {"environment_version":VERSION,"seed":seed}

    def snapshot(self):
        return copy.deepcopy({"documents":self.documents,"ticket":self.ticket,"notes":self.notes,
            "receipts":self.receipts,"attempts":self.attempts,"conflict_injected":self.conflict_injected,
            "submission":self.submission,"terminated":self.terminated,"truncated":self.truncated})

    def _action(self, action, step):
        if not isinstance(action,dict) or set(action)!={"tool","args"} or not isinstance(action["args"],dict):
            return {"status":400,"error":"invalid_action"}
        tool,args=action["tool"],action["args"]
        if tool not in TOOLS:return {"status":400,"error":"unknown_tool"}
        if tool=="search":
            if set(args)!={"query"} or not isinstance(args["query"],str):return {"status":422,"error":"query_string_required"}
            return {"status":200,"documents":[k for k in self.scenario["document_order"] if args["query"].lower() in (k+canonical(self.documents[k])).lower()]}
        if tool=="read":
            if set(args)!={"document_id"} or not isinstance(args["document_id"],str):return {"status":422,"error":"document_id_required"}
            key=args["document_id"]; self.attempts[key]=self.attempts.get(key,0)+1
            status=200 if key in self.documents else 404
            if key=="sources":
                if self.scenario["fault"]=="access_revoked":status=403
                elif self.scenario["fault"]=="tool_retry" and self.attempts[key]<=2:status=429
            version=self.documents[key]["version"] if status==200 else None
            body=copy.deepcopy(self.documents[key]["body"]) if status==200 else None
            receipt={"document_id":key,"version":version,"status":status,"step":step,"body_sha256":digest(body)}
            self.receipts.append(receipt)
            result={"status":status,"document_id":key,"version":version,"receipt":copy.deepcopy(receipt)}
            if body is not None:result["body"]=body
            if status==429:result["error"]="transient_rate_limit"
            if status==403:result["error"]="source_access_denied"
            return result
        if tool=="read_ticket":
            if args:return {"status":422,"error":"no_arguments"}
            return {"status":200,"ticket":copy.deepcopy(self.ticket)}
        if tool=="revise_claim":
            if set(args)!={"if_version","claim_id","value","unit"} or type(args.get("value")) is not int or not isinstance(args.get("unit"),str):
                return {"status":422,"error":"revision_contract"}
            if self.scenario["mechanism"]!="review_revision":return {"status":403,"error":"revision_not_in_scope"}
            doc=self.documents["claims"]
            if type(args["if_version"]) is not int or args["if_version"]!=doc["version"]:return {"status":409,"error":"claim_version_conflict"}
            rows=[r for r in doc["body"]["rows"] if r["row_id"]==args["claim_id"]]
            if len(rows)!=1:return {"status":404,"error":"claim_not_found"}
            rows[0].update(value=args["value"],unit=args["unit"]); doc["version"]+=1
            return {"status":200,"document_id":"claims","version":doc["version"],"message":"Read the revised document before citing it."}
        if tool=="write_note":
            report=args.get("report")
            if set(args)-{"report","text"} or not report_shape(report):return {"status":422,"error":"structured_report_required"}
            if "text" in args and args["text"]!=render(report):return {"status":422,"error":"text_disagrees_with_structured_report"}
            note_id="note-"+str(len(self.notes)+1)
            self.notes[note_id]={"report":copy.deepcopy(report),"text":render(report),"created_step":step,
                                 "read_receipts":copy.deepcopy(self.receipts)}
            return {"status":200,"note_id":note_id}
        if tool=="update_ticket":
            if set(args)!={"if_version","status","note_id"} or type(args["if_version"]) is not int or not isinstance(args["note_id"],str):return {"status":422,"error":"ticket_contract"}
            if self.scenario["fault"]=="concurrent_edit" and not self.conflict_injected:
                self.ticket["version"]+=1; self.conflict_injected=True
                return {"status":409,"error":"ticket_version_conflict","message":"Read current ticket before retrying."}
            if args["if_version"]!=self.ticket["version"]:return {"status":409,"error":"ticket_version_conflict"}
            if args["note_id"] not in self.notes or args["status"] not in ("ready","needs_revision","blocked"):return {"status":422,"error":"invalid_note_or_status"}
            self.ticket.update(version=self.ticket["version"]+1,status=args["status"],note_id=args["note_id"])
            return {"status":200,"ticket":copy.deepcopy(self.ticket)}
        if set(args)!={"note_id","ticket_version"} or type(args["ticket_version"]) is not int or not isinstance(args["note_id"],str):return {"status":422,"error":"submit_contract"}
        self.submission=copy.deepcopy(args); self.terminated=True; self.finished=True
        return {"status":200,"submitted":True}

    def step(self, action):
        check(not self.finished,"episode_finished")
        before=self.snapshot()
        try: observation=self._action(copy.deepcopy(action),len(self.events)+1)
        except (TypeError, KeyError, ValueError): observation={"status":400,"error":"invalid_argument_type_or_value"}
        if len(self.events)+1>=self.scenario["max_steps"] and not self.terminated:self.truncated=True; self.finished=True
        after=self.snapshot()
        event={"step":len(self.events)+1,"action":copy.deepcopy(action),"observation":observation,
               "before_sha256":digest(before),"after_sha256":digest(after),"terminated":self.terminated,"truncated":self.truncated}
        self.events.append(event)
        reward=self.grade()["reward"] if self.finished else 0
        return copy.deepcopy(observation),reward,self.terminated,self.truncated,{"steps_remaining":self.scenario["max_steps"]-len(self.events)}

    def grade(self):
        exp, rows, resolved=expected(self.scenario,self.documents)
        note=self.notes.get((self.submission or {}).get("note_id")); report=(note or {}).get("report",{})
        checks={"terminal":self.terminated and not self.truncated,"structured_report":report_shape(report),
                "correct_result":all(equal(report.get(k),v) for k,v in exp.items()),
                "scope":report.get("scope")==SCOPES[self.scenario["mechanism"]],
                "task_resolution":resolved,"evidence_links":False,"note_content":False,"ticket":False,
                "retry_budget":self.attempts.get("sources",0)<=3}
        if note and report_shape(report):
            checks["note_content"]=note["text"]==render(report)
            citations=report["citations"]
            valid=len(citations)==len(self.documents) and {c["document_id"] for c in citations}==set(self.documents)
            for cite in citations:
                key=cite["document_id"]; doc=self.documents.get(key)
                denied=key=="sources" and self.scenario["fault"]=="access_revoked"
                if doc is None:valid=False;continue
                status,version,body=(403,None,None) if denied else (200,doc["version"],doc["body"])
                needed=set() if denied else rows.get(key,{r["row_id"] for r in doc["body"].get("rows",[])})
                valid=valid and cite["status"]==status and equal(cite["version"],version) and set(cite["row_ids"])==needed and len(cite["row_ids"])==len(needed)
                valid=valid and any(r["document_id"]==key and r["status"]==status and equal(r["version"],version) and r["body_sha256"]==digest(body) for r in note["read_receipts"])
            checks["evidence_links"]=bool(valid)
            checks["ticket"]=self.ticket["status"]==report["status"] and self.ticket["note_id"]==self.submission.get("note_id") and equal(self.ticket["version"],self.submission.get("ticket_version"))
        return {"reward":int(all(checks.values())),"checks":checks,"grader_version":VERSION,
                "assessed_capability":"bounded_structured_evidence_tasks","research_truth_assessed":False}

def record(env, actor_kind):
    return {"task_id":env.scenario["task_id"],"scenario_sha256":digest(env.scenario),"environment_version":VERSION,
            "seed":env.seed,"actor_kind":actor_kind,"initial_observation":env.initial,"events":env.events,
            "final_state":env.snapshot(),"complete":env.finished,"grade":env.grade()}

def verify_record(scenario, run):
    env=ResearchEnv(scenario); initial,_=env.reset(run["seed"])
    check(run["task_id"]==scenario["task_id"] and run["scenario_sha256"]==digest(scenario),"scenario_binding_changed")
    check(equal(initial,run["initial_observation"]),"initial_observation_changed")
    for event in run["events"]:
        env.step(event["action"]);check(equal(env.events[-1],event),"event_replay_changed")
    check(equal(env.snapshot(),run["final_state"]) and run["complete"]==env.finished,"final_state_changed")
    check(equal(env.grade(),run["grade"]),"grade_changed")
    return env.grade()

def main():
    parser=argparse.ArgumentParser();parser.add_argument("scenario");parser.add_argument("--output",required=True)
    args=parser.parse_args();scenario=json.loads(Path(args.scenario).read_text(encoding="utf-8-sig"));env=ResearchEnv(scenario)
    print(canonical({"observation":env.initial}),flush=True)
    for line in sys.stdin:
        if not line.strip():continue
        try: result=env.step(json.loads(line))
        except (ValueError,TypeError,KeyError) as error:print(canonical({"error":str(error)}),flush=True);continue
        Path(args.output).write_text(canonical(record(env,"external_policy"))+"\n",encoding="utf-8")
        observation,reward,terminated,truncated,info=result
        print(canonical({"observation":observation,"reward":reward,"terminated":terminated,"truncated":truncated,"info":info}),flush=True)
        if env.finished:break

if __name__=="__main__":main()
