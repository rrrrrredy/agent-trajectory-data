"""Configuration adapters and public-observation reference policies for v4 tasks."""
from __future__ import annotations
import copy,re
import research_env_v4 as e
POLICY={
 "purpose":"Resolve only supplied records available as of the task date; preserve uncertainty and unrelated claims.",
 "report_contract":{"status":"ready | needs_revision | blocked","scope":"mechanism scope below","result":"exact mechanism fields below","limitations":e.LIMITS,
    "citations":[{"document_id":"every required document once","version":"current read version, null for 404","status":"200 or 404","row_ids":"all rows in that required document, empty for 404 or documents without rows"}]},
 "dependencies":"Read the initial documents and recursively follow each body's references array. Cite exactly this dependency closure. A 404 stops traversal of that branch. Unreferenced distractors are not evidence.",
 "availability":"Only records available_at <= as_of can be searched or read. A future record is unavailable, including if its ID is guessed. Do not invent its content.",
 "evidence_chain":{"scope":"supplied_dependency_graph","rule":"Start at handoff.root_node. Value nodes normalize thousand_units to 1000 units; sum adds inputs; subtract is first input minus second. Compare the result with C1.",
    "result_fields":["metric","value","unit","claim_supported"],"status":"ready iff claim_supported, otherwise needs_revision"},
 "evidence_conflict":{"scope":"supplied_authority_policy","rule":"Read every handoff.witnesses record. Highest authority wins. If equally highest authorities disagree, retain unresolved_conflict with value null and status blocked. observed_at recency does not break an authority tie. If they agree, resolve to their common value.",
    "result_fields":["resolution","value","unit"],"limitations_if_unresolved":"Append unresolved_peer_conflict"},
 "revision_workflow":{"scope":"verified_review_batch","rule":"For every review finding, compare proposed_value and unit against source_document. Apply all supported corrections; reject unsupported suggestions. Only C1 and C2 are editable; preserve C0. Read current claims before EACH revision and reread after the last revision.",
    "result_fields":["resolved_findings","rejected_findings","remaining_findings","corrected_claims"],
    "corrected_claims":"Sorted objects {claim_id,value,unit} for supported corrections; list finding IDs in the other fields. status ready after verifying all corrections."},
 "unavailable_rule":"If any required document returns 404, do not revise claims. Use status blocked, result {unavailable_documents: sorted missing IDs}, and append unavailable_evidence to limitations. This takes precedence over the mechanism result schema.",
 "tool_failures":"Retry a 429 at most twice: at most three reads of that document. A 404 is permanent. On claim 409 read current claims and retry with its version. 412 means read current claims before revising.",
 "completion":"Write the structured note only after all required evidence and final claim versions were read. Update the task ticket to the same status and note ID, then submit using the latest ticket version. Host renders the note; do not add unsupported free text."}
HELP={
 "search":{"args":{"query":"literal substring; empty lists currently available documents"}},
 "read":{"args":{"document_id":"an initial document or a reference discovered in a body"}},
 "read_ticket":{"args":{}},
 "revise_claim":{"args":{"if_version":"integer current claims version","claim_id":"C1 or C2","value":"integer","unit":"string"},"rule":"Only revision_workflow; reread claims after a successful revision or 409."},
 "write_note":{"args":{"report":"object matching policy.report_contract"}},
 "update_ticket":{"args":{"if_version":"integer ticket version","status":"report status","note_id":"returned note ID"}},
 "submit":{"args":{"note_id":"returned note ID","ticket_version":"latest integer ticket version"}}}
VARIANTS={"clean","counterfactual","tool_retry","withheld_evidence","stale_revision"}

def validate_material(source,material,as_of):
    e.check(source["mechanism"] in e.SCOPES and source["family_id"]==material["family_id"],"invalid_v4_source")
    e.check(material["origin"]=="authored_synthetic" and material["rights"]=={"distribution":"private","training_eligible":source["split"]=="train"},"rights_mismatch")
    e.check(set(source["variants"])<=VARIANTS and len(source["variants"])==len(set(source["variants"])),"invalid_variants")
    docs=material["documents"]
    e.check(all(key in docs and docs[key]["available_at"]<=as_of for key in ("handoff","claims")),"entry_document_unavailable")
    for key,doc in docs.items():
        e.check(re.fullmatch(r"[a-z0-9-]+",key) and doc["version"]==1,"invalid_document")
        rows=doc["body"].get("rows",[]);e.check(len({r["row_id"] for r in rows})==len(rows),"duplicate_row_id")
        refs=doc["body"].get("references",[]);e.check(len(set(refs))==len(refs) and all(r in docs for r in refs),"invalid_document_reference")
        for row in rows:
            if row.get("kind") in {"sum","subtract"}:e.check(row["inputs"]==refs,"graph_reference_mismatch")
    if source["mechanism"]=="evidence_chain":e.graph_value(docs,docs["handoff"]["body"]["root_node"])
    if source["mechanism"]!="revision_workflow":e.check("stale_revision" not in source["variants"],"revision_fault_out_of_scope")

def scenario_for(config,source,material,variant):
    validate_material(source,material,config["as_of"]);docs=copy.deepcopy(material["documents"])
    docs["policy"]={"version":1,"available_at":config["as_of"],"body":copy.deepcopy(POLICY)}
    mechanism=source["mechanism"]
    if variant=="counterfactual":
        change=material["counterfactual"]
        if mechanism=="evidence_chain":
            root=docs[docs["handoff"]["body"]["root_node"]]["body"]
            root["references"][1]=change["switch_reservation_to"];root["rows"][0]["inputs"][1]=change["switch_reservation_to"]
        elif mechanism=="evidence_conflict":docs[change["higher_authority_document"]]["body"]["rows"][0]["authority"]=change["authority"]
        else:docs["review"]["body"]["rows"].append(copy.deepcopy(change["additional_finding"]))
    if variant=="withheld_evidence":docs[material["fault_document"]]["available_at"]="9999-12-31"
    return {"version":e.VERSION,"task_id":source["family_id"]+"-"+variant+"-v4","family_id":source["family_id"],"split":source["split"],
        "mechanism":mechanism,"variant":variant,"origin":material["origin"],"as_of":config["as_of"],"max_steps":config["max_steps"],
        "documents":docs,"document_order":sorted(docs),"entry_documents":["policy","handoff","claims"],"tool_help":HELP,
        "fault":variant if variant in {"tool_retry","stale_revision","withheld_evidence"} else "none","fault_document":material["fault_document"],
        "editable_claims":material["editable_claims"],"rights":material["rights"],"source_sha256":e.digest(material),"grading_scope":config["grading_scope"],
        "instruction":"Complete the "+mechanism+" task. Start with policy, handoff and claims; follow actual document references. Resolve evidence conflicts under the stated authority policy, preserve uncertainty when needed, verify required revisions, create a cited note, update the ticket and submit."}

def public_state(initial,history):
    seen={}
    for event in history:
        obs=event["observation"]
        if "receipt" in obs and obs["status"] in (200,404):seen[obs["document_id"]]=obs
    queue=list(initial["documents"]);required=[]
    while queue:
        key=queue.pop(0)
        if key in required:continue
        required.append(key)
        if key in seen and seen[key]["status"]==200:queue.extend(seen[key]["body"].get("references",[]))
    return seen,required

def public_report(initial,history):
    seen,required=public_state(initial,history)
    missing=sorted(key for key in required if seen[key]["status"]==404)
    mechanism=initial["mechanism"];limits=list(e.LIMITS)
    if missing:status="blocked";result={"unavailable_documents":missing};limits.append("unavailable_evidence")
    elif mechanism=="evidence_chain":
        pending={key:obs["body"]["rows"][0] for key,obs in seen.items() if obs["status"]==200 and obs["body"].get("rows") and "kind" in obs["body"]["rows"][0]}
        values={}
        while pending:
            progress=False
            for key,row in list(pending.items()):
                if row["kind"]=="value":value=row["value"]*(1000 if row["unit"]=="thousand_units" else 1)
                elif all(ref in values for ref in row["inputs"]):
                    amounts=[values[ref] for ref in row["inputs"]];value=sum(amounts) if row["kind"]=="sum" else amounts[0]-amounts[1]
                else:continue
                values[key]=value;del pending[key];progress=True
            e.check(progress,"unresolved_public_graph")
        claim=seen["claims"]["body"]["rows"][0];total=values[seen["handoff"]["body"]["root_node"]]
        supported=claim["value"]==total and claim["unit"]=="units";status="ready" if supported else "needs_revision"
        result={"metric":claim["metric"],"value":total,"unit":"units","claim_supported":supported}
    elif mechanism=="evidence_conflict":
        rows=[seen[key]["body"]["rows"][0] for key in seen["handoff"]["body"]["witnesses"]]
        rows.sort(key=lambda row:row["authority"],reverse=True);leaders=[row for row in rows if row["authority"]==rows[0]["authority"]]
        agreed=all((row["value"],row["unit"])==(leaders[0]["value"],leaders[0]["unit"]) for row in leaders)
        status="ready" if agreed else "blocked";result={"resolution":"resolved" if agreed else "unresolved_conflict","value":leaders[0]["value"] if agreed else None,"unit":leaders[0]["unit"]}
        if not agreed:limits.append("unresolved_peer_conflict")
    else:
        resolved=[];rejected=[];corrections={}
        for row in seen["review"]["body"]["rows"]:
            fact=seen[row["source_document"]]["body"]["rows"][0]
            if (row["proposed_value"],row["unit"])==(fact["value"],fact["unit"]):
                resolved.append(row["row_id"]);corrections[row["claim_id"]]={"claim_id":row["claim_id"],"value":fact["value"],"unit":fact["unit"]}
            else:rejected.append(row["row_id"])
        status="ready";result={"resolved_findings":sorted(resolved),"rejected_findings":sorted(rejected),"remaining_findings":[],"corrected_claims":[corrections[key] for key in sorted(corrections)]}
    citations=[]
    for key in required:
        obs=seen[key];citations.append({"document_id":key,"version":obs["version"],"status":obs["status"],"row_ids":[r["row_id"] for r in obs.get("body",{}).get("rows",[])]})
    return {"status":status,"scope":e.SCOPES[mechanism],"result":result,"limitations":limits,"citations":citations}

def reference_action(initial,history,skip_revisions=False):
    def action(tool,**args):return {"tool":tool,"args":args}
    seen,required=public_state(initial,history)
    for key in required:
        if key not in seen:return action("read",document_id=key)
    report=public_report(initial,history)
    if initial["mechanism"]=="revision_workflow" and report["status"]=="ready" and not skip_revisions:
        if history and history[-1]["action"]["tool"]=="revise_claim":return action("read",document_id="claims")
        claims={r["row_id"]:r for r in seen["claims"]["body"]["rows"]}
        for desired in report["result"]["corrected_claims"]:
            current=claims[desired["claim_id"]]
            if (current["value"],current["unit"])!=(desired["value"],desired["unit"]):
                return action("revise_claim",if_version=seen["claims"]["version"],**desired)
    notes=[event["observation"]["note_id"] for event in history if event["action"]["tool"]=="write_note" and event["observation"]["status"]==200]
    if not notes:return action("write_note",report=report)
    ticket=initial["ticket"]
    for event in history:
        if "ticket" in event["observation"]:ticket=event["observation"]["ticket"]
    if ticket["note_id"]!=notes[-1]:return action("update_ticket",if_version=ticket["version"],status=report["status"],note_id=notes[-1])
    return action("submit",note_id=notes[-1],ticket_version=ticket["version"])

def control_names(scenario):
    names=["overclaim_text","empty_assertion","wrong_scope","wrong_result","missing_citation","future_citation"]
    if scenario["mechanism"]=="revision_workflow" and scenario["variant"]!="withheld_evidence":names.append("partial_repair")
    if scenario["mechanism"]=="evidence_conflict":names.append("prefer_latest_over_authority")
    return names

def run_reference(scenario,mutation=None):
    env=e.ResearchEnv(scenario);changed=False;skip=False
    while not env.finished:
        action=reference_action(env.initial,env.events,skip)
        if mutation=="partial_repair" and action["tool"]=="revise_claim" and action["args"]["claim_id"]=="C2":
            skip=True;action=reference_action(env.initial,env.events,skip)
        if mutation and action["tool"]=="write_note" and not changed:
            report=action["args"]["report"]
            if mutation=="overclaim_text":action["args"]["text"]="All records are externally verified."
            elif mutation=="empty_assertion":action["args"]["text"]="Done."
            elif mutation=="wrong_scope":report["scope"]=next(scope for scope in e.SCOPES.values() if scope!=report["scope"])
            elif mutation=="wrong_result":report["result"]={"unsupported":True}
            elif mutation=="missing_citation":report["citations"]=report["citations"][:-1]
            elif mutation=="future_citation":report["citations"].append({"document_id":"future-resolution","version":1,"status":200,"row_ids":["FUTURE"]})
            elif mutation=="prefer_latest_over_authority":
                seen,_=public_state(env.initial,env.events)
                witnesses=[seen[key]["body"]["rows"][0] for key in seen["handoff"]["body"]["witnesses"] if seen[key]["status"]==200]
                newest=max(witnesses,key=lambda row:row["observed_at"])
                report.update(status="ready",result={"resolution":"resolved","value":newest["value"],"unit":newest["unit"]},limitations=list(e.LIMITS))
            changed=True
        env.step(action)
        if changed and mutation in {"overclaim_text","empty_assertion"}:break
    return e.record(env,"scripted_negative_control" if mutation else "scripted_reference")
