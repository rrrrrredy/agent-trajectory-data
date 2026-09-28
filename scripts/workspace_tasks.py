"""Reference policy and deliberate mistakes using only public workspace observations."""
from __future__ import annotations
import copy
import workspace_env as e

def observed(initial,history,mutation=None):
    seen={}
    for event in history:
        action,obs=event["action"],event["observation"]
        if action["tool"]=="read" and obs["status"] in (200,404):seen[obs["document_id"]]=obs
        if action["tool"]=="revise_artifact":
            if obs["status"] in (200,504):seen.pop(action["args"]["document_id"],None)
            elif obs["status"]==409:
                for key in obs.get("changed_documents",[]):
                    if mutation!="stale_source" or key in initial["documents"]:seen.pop(key,None)
    return seen

def calculate(spec,seen):
    # Separate public policy implementation, not the evaluator's expression function.
    if "ref" in spec:
        document,row_id=spec["ref"]
        for row in seen[document]["body"]["rows"]:
            if row["row_id"]==row_id:return copy.deepcopy(row["value"])
        raise ValueError("public_row_missing")
    arguments=[calculate(child,seen) for child in spec["args"]]
    operations={"sum":lambda x:sum(x),"subtract":lambda x:x[0]-x[1],"multiply":lambda x:x[0]*x[1],"floor_divide":lambda x:x[0]//x[1],"minimum":min,"maximum":max}
    return operations[spec["op"]](arguments)

def desired(brief,seen,mutation=None):
    result={key:{"value":calculate(spec["expression"],seen),"unit":spec["unit"]} for key,spec in brief["outputs"].items()};rule=brief["decision_rule"]
    if "literal" in rule:decision=rule["literal"]
    else:
        value=result[rule["output"]]["value"]
        accepted=(value>=rule["threshold"]) if rule["operator"]==">=" else (value<=rule["threshold"])
        decision=rule["yes"] if accepted else rule["no"]
    scope=brief["result_scope"]
    if mutation=="wrong_result":
        key=sorted(result)[0];value=result[key]["value"];result[key]["value"]=value+1 if type(value) is int else value+["unsupported-language"]
    if mutation=="wrong_scope":scope="independently_verified_universal_effect"
    citations=[{"document_id":key,"version":seen[key]["version"],"row_ids":[r["row_id"] for r in seen[key]["body"]["rows"]]} for key in sorted(brief["evidence_ids"])]
    if mutation=="irrelevant_citation":citations[0]={"document_id":"old-note","version":seen["old-note"]["version"],"row_ids":["OLD"]}
    return {"result":result,"decision":decision,"scope":scope,"citations":citations}

def reference_action(initial,history,mutation=None,reverse=False):
    def action(tool,**args):return {"tool":tool,"args":args}
    seen=observed(initial,history,mutation)
    if history and history[-1]["observation"]["status"]==504:return action("operation_status",operation_id=history[-1]["action"]["args"]["operation_id"])
    queue=list(initial["documents"])
    if "brief" in seen:queue+=seen["brief"]["body"]["evidence_ids"]
    if mutation=="irrelevant_citation":queue.append("old-note")
    if reverse and "brief" in seen:queue=list(reversed(queue))
    for key in queue:
        if key not in seen:return action("read",document_id=key)
    brief=seen["brief"]["body"];keys=list(brief["artifact_ids"]);missing=sorted(k for k in brief["evidence_ids"] if seen[k]["status"]==404)
    if reverse:keys.reverse()
    if not missing:
        expected=desired(brief,seen,mutation)
        for n,key in enumerate(keys):
            if mutation=="initial_unfixed" or mutation=="partial_repair" and n==1:continue
            doc=seen[key];content={**expected,"preserved":doc["body"]["content"]["preserved"]}
            if mutation=="protected_text":content["preserved"]="Protection removed."
            if not e.equal(doc["body"]["content"],content):
                oid="write-"+e.digest([key,doc["version"],content])[:16]
                return action("revise_artifact",document_id=key,if_version=doc["version"],operation_id=oid,content=content)
        if mutation=="duplicate_effect" and not any(x["action"]["args"].get("operation_id")=="extra-duplicate" for x in history):
            key=keys[0];doc=seen[key];return action("revise_artifact",document_id=key,if_version=doc["version"],operation_id="extra-duplicate",content=doc["body"]["content"])
    elif mutation=="edit_while_blocked" and not any(x["action"]["tool"]=="revise_artifact" for x in history):
        key=keys[0];doc=seen[key];value=copy.deepcopy(doc["body"]["content"]);value["decision"]="guessed"
        return action("revise_artifact",document_id=key,if_version=doc["version"],operation_id="blocked-edit",content=value)
    validations=[x["observation"]["validation"] for x in history if x["action"]["tool"]=="validate" and x["observation"]["status"]==200]
    if not validations and mutation!="no_validation":return action("validate")
    notes=[x["observation"]["note_id"] for x in history if x["action"]["tool"]=="write_note" and x["observation"]["status"]==200]
    status="blocked" if missing else "ready"
    if mutation=="false_ready":status="ready"
    if not notes:
        report={"status":status,"scope":"research_workspace_reconciliation","artifact_versions":{k:seen[k]["version"] for k in brief["artifact_ids"]},"validation_id":validations[-1]["validation_id"] if validations else "absent","missing_documents":[] if mutation=="omit_missing" else missing,"diagnosis":"Reconciled the supplied records and versions; final public validation is recorded."}
        return action("write_note",report=report)
    ticket=initial["ticket"]
    for event in history:
        if "ticket" in event["observation"]:ticket=event["observation"]["ticket"]
    if ticket["note_id"]!=notes[-1]:return action("update_ticket",if_version=ticket["version"],status=status,note_id=notes[-1])
    return action("submit",note_id=notes[-1],ticket_version=ticket["version"])

def control_names(scenario):
    if scenario["unavailable_documents"]:return ["false_ready","omit_missing","edit_while_blocked"]
    names=["initial_unfixed","partial_repair","wrong_result","wrong_scope","irrelevant_citation","protected_text","no_validation","duplicate_effect"]
    if scenario["fault"]=="source_refresh":names.append("stale_source")
    return names

def run_reference(scenario,mutation=None,reverse=False):
    env=e.ResearchEnv(scenario)
    while not env.finished:env.step(reference_action(env.initial,env.events,mutation,reverse))
    result=e.record(env,"scripted_negative_control" if mutation else "scripted_reference")
    return result
