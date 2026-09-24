"""Offline business-task RL environment. Pure data actions; no external services."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path

def stable(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)

def digest(value):
    return hashlib.sha256(stable(value).encode()).hexdigest()

TOOLS = {
    "search": {"query":"string"},
    "read": {"document_id":"string"},
    "read_ticket": {},
    "write_note": {"text":"string","evidence_ids":"list[string]"},
    "update_ticket": {"if_version":"int","status":"ready|needs_revision|blocked","note_id":"string"},
    "submit": {"status":"ready|needs_revision|blocked","dangling_references":"list[{claim_id,source_id}]",
               "missing_tables":"list[string]","evidence_ids":"list[string]","ticket_version":"int",
               "scope":"registry_integrity_only"},
}
STATUSES={"ready","needs_revision","blocked"}

class BusinessEnv:
    """reset/step signature follows the five-value RL convention, without Gym dependency."""
    def __init__(self, scenario):
        self.scenario=copy.deepcopy(scenario)
        self.reset()
    @classmethod
    def from_file(cls,path):
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))
    def reset(self,seed=0,options=None):
        if not isinstance(seed,int):raise ValueError("seed_must_be_integer")
        self.seed=seed
        self.ticket=copy.deepcopy(self.scenario["initial_ticket"])
        self.notes=[];self.events=[];self.read_counts={};self.observed={}
        self.step_count=0;self.finished=False;self.conflict_injected=False
        self.outcome=None
        return {"instruction":self.scenario["instruction"],"ticket":copy.deepcopy(self.ticket),
                "role":self.scenario["role"],"as_of":self.scenario["as_of"],
                "tools":copy.deepcopy(TOOLS),"budget_steps":self.scenario["max_steps"]}, {"task_id":self.scenario["task_id"]}
    def snapshot(self):
        return {"ticket":copy.deepcopy(self.ticket),"notes":copy.deepcopy(self.notes),
                "observed":copy.deepcopy(self.observed),"read_counts":dict(self.read_counts),
                "steps":self.step_count,"finished":self.finished,"seed":self.seed,
                "conflict_injected":self.conflict_injected}
    def accessible(self,doc):
        return (self.scenario["role"] in doc["roles"] and doc["effective_at"]<=self.scenario["as_of"])
    def expected(self):
        """Evaluator-only answer computed from state, not a historical business truth label."""
        docs=self.scenario["documents"]
        source=docs["sources"]; claims=docs["claims"]
        if not self.accessible(source) or source.get("unavailable"):
            return {"status":"blocked","dangling_references":[],"missing_tables":["sources"]}
        ids={r["source_id"] for r in source["body"]["rows"]}
        issues=sorted([{"claim_id":r["claim_id"],"source_id":s.strip()}
                      for r in claims["body"]["rows"] for s in r["source_ids"].split("|")
                      if s.strip() and s.strip() not in ids],key=lambda x:(x["claim_id"],x["source_id"]))
        return {"status":"needs_revision" if issues else "ready","dangling_references":issues,"missing_tables":[]}
    def grade(self,answer):
        expected=self.expected()
        required={"policy","handoff","claims"}
        required.add("sources")
        # A denied observation is valid evidence of a blocked decision.
        evidence=answer.get("evidence_ids")
        observed=set(self.observed)
        checks={
            "decision":all(answer.get(k)==v for k,v in expected.items()),
            "scope":answer.get("scope")=="registry_integrity_only",
            "observed_evidence":isinstance(evidence,list) and all(isinstance(x,str) for x in evidence)
                and required<=set(evidence)<=observed,
            "ticket":self.ticket["status"]==expected["status"] and answer.get("ticket_version")==self.ticket["version"],
            "note":False,
            "retry_budget":self.read_counts.get("sources",0)<=3,
        }
        note=next((n for n in self.notes if n["note_id"]==self.ticket.get("note_id")),None)
        checks["note"]=bool(note and note["text"].strip() and required<=set(note["evidence_ids"])<=observed
                            and note["status_at_write"]=="open")
        passed=all(checks.values())
        return {"reward":int(passed),"checks":checks,"passed":passed,
                "basis":"observable_state_and_frozen_registry_contract",
                "research_quality_verified":False}
    def step(self,action):
        if self.finished:raise ValueError("episode_finished_reset_required")
        before=digest(self.snapshot());self.step_count+=1
        result={"status":400,"error":"invalid_action"};reward=0;terminated=False;truncated=False
        if isinstance(action,dict) and isinstance(action.get("tool"),str) and action.get("tool") in TOOLS and isinstance(action.get("args",{}),dict):
            tool=action["tool"];args=action.get("args",{})
            try: result=self._act(tool,args)
            except (KeyError,TypeError,ValueError):result={"status":400,"error":"invalid_arguments"}
            if tool=="submit" and result["status"]==200:
                self.outcome=self.grade(args);reward=self.outcome["reward"];terminated=True
                result={"status":200,"accepted":True,"outcome":"passed" if reward else "failed"}
        if self.step_count>=self.scenario["max_steps"] and not terminated:
            truncated=True;self.outcome={"reward":0,"passed":False,"reason":"step_budget_exhausted"}
        self.finished=terminated or truncated
        event={"step":self.step_count,"action":copy.deepcopy(action),"observation":copy.deepcopy(result),
               "reward":reward,"terminated":terminated,"truncated":truncated,
               "before_sha256":before,"after_sha256":digest(self.snapshot())}
        self.events.append(event)
        # Keep detailed grading private; the agent gets outcome reward, not expected answers.
        return copy.deepcopy(result),reward,terminated,truncated,{"step":self.step_count}
    def _act(self,tool,args):
        docs=self.scenario["documents"]
        if tool=="search":
            query=args["query"]
            if not isinstance(query,str) or len(query)>1000:raise ValueError()
            found=[{"document_id":i,"title":d["title"],"effective_at":d["effective_at"]}
                   for i,d in sorted(docs.items()) if self.accessible(d)
                   and query.casefold() in (d["title"]+" "+d.get("search_text","")).casefold()]
            return {"status":200,"results":found}
        if tool=="read":
            key=args["document_id"]
            if not isinstance(key,str):raise ValueError()
            if key not in docs or docs[key]["effective_at"]>self.scenario["as_of"]:
                return {"status":404,"error":"not_found"}
            doc=docs[key];self.read_counts[key]=self.read_counts.get(key,0)+1
            if not self.accessible(doc) or doc.get("unavailable"):
                self.observed[key]={"status":403,"version":doc["version"]}
                return {"status":403,"error":"access_denied","document_id":key}
            if self.read_counts[key]<=doc.get("transient_failures",0):
                self.observed[key]={"status":429,"version":doc["version"]}
                return {"status":429,"error":"temporary_rate_limit","retry_after_steps":1}
            self.observed[key]={"status":200,"version":doc["version"]}
            return {"status":200,"document_id":key,"version":doc["version"],"body":copy.deepcopy(doc["body"])}
        if tool=="read_ticket":return {"status":200,"ticket":copy.deepcopy(self.ticket)}
        if tool=="write_note":
            text=args["text"];evidence=args["evidence_ids"]
            if not isinstance(text,str) or not text.strip() or len(text)>8000 or not isinstance(evidence,list):raise ValueError()
            if not all(isinstance(i,str) for i in evidence) or not set(evidence)<=set(self.observed):
                return {"status":422,"error":"unobserved_evidence"}
            note={"note_id":"note-"+str(len(self.notes)+1),"text":text,"evidence_ids":list(evidence),
                  "status_at_write":self.ticket["status"]}
            self.notes.append(note);return {"status":200,"note_id":note["note_id"]}
        if tool=="update_ticket":
            if args["status"] not in STATUSES or not isinstance(args["if_version"],int):raise ValueError()
            if self.scenario["fault"]=="concurrent_edit" and not self.conflict_injected:
                self.ticket["version"]+=1;self.ticket["upstream_change"]="deadline_reconfirmed"
                self.conflict_injected=True
            if args["if_version"]!=self.ticket["version"]:return {"status":409,"error":"version_conflict"}
            if args["note_id"] not in {n["note_id"] for n in self.notes}:return {"status":422,"error":"note_required"}
            self.ticket.update(status=args["status"],note_id=args["note_id"],version=self.ticket["version"]+1)
            return {"status":200,"ticket":copy.deepcopy(self.ticket)}
        if tool=="submit":
            # Detailed data correctness is scored; malformed submissions terminate with zero too.
            return {"status":200}
        raise ValueError("unknown_tool")

INSTRUCTION = """你在一个离线研究交接工作区担任证据分析员。任务是判断给定报告的来源登记是否具备交接条件，
记录证据和限制，更新任务单，再提交结构化结果。工作区含交接记录、来源表、主张表、历史版本和无权访问的资料。
先自行查阅适用规则。不得把来源登记完整等同于报告事实正确，不得用未来材料补当时结论。
目标是业务状态和交付物正确；系统不要求唯一操作顺序，也不奖励操作次数。
本工作区的组织、任务单和事件均为合成，嵌入的研究表格来自归档；不代表真实企业内部流程。"""
POLICY = """验收范围仅为主张与来源登记的链接完整性。以当前 claims/sources 表为准；handoff 说明交接边界。
存在未登记的来源链接则 needs_revision；来源表无权读取或缺失则 blocked；否则 ready。
ready 只代表登记完整，不是事实审核。输出 scope 必须是 registry_integrity_only。
必须建立交接 note（包含非空说明和已观察的 policy/handoff/claims/sources 证据 ID），
再以版本条件更新任务单；提交 status、dangling_references、missing_tables、evidence_ids、ticket_version、scope。
每个 dangling 项含 claim_id/source_id 并排序。临时 429 最多重试两次；403 不可绕过。
发生 409 应读取当前任务单后再判断和更新。任务单、说明和提交状态应一致。"""

def make_scenario(report,family,sources,claims,fault):
    task_id="business-"+report+"-"+fault
    rows=copy.deepcopy(claims)
    if fault in {"missing_reference","tool_retry"}:
        rows[0]["source_ids"]+="|S_UNREGISTERED"
    def document(title,body,version=2,roles=None,date="2026-09-07"):
        return {"title":title,"body":body,"version":version,"roles":roles or ["evidence_analyst"],
                "effective_at":date}
    docs={
        "policy":document("研究交接规则",POLICY),
        "handoff":document("研究交接记录",{"report":report,"prior_note":"旧记录曾标为可交接，需按当前表重新检查。",
                                       "limits":"来源 ID 完整不证明主张真实，归档材料可能已经过期。",
                                       "origin":"synthetic_context_over_archived_research"}),
        "sources":document("当前来源登记",{"rows":copy.deepcopy(sources)}),
        "claims":document("当前主张登记",{"rows":rows}),
        "old-note":document("历史交接结论",{"decision":"ready","superseded":True},1,date="2026-09-06"),
        "restricted":document("其他团队资料",{"internal":"not_needed_for_task"},roles=["other_team"]),
        "future":document("未来补录资料",{"decision":"ready"},date="2026-09-08"),
    }
    if fault=="tool_retry":docs["sources"]["transient_failures"]=2
    if fault=="access_revoked":docs["sources"]["roles"]=["other_team"]
    return {"schema_version":"business-env-1","task_id":task_id,"family_id":family,
            "origin":"synthetic_business_scenario_over_real_artifacts","split":"development",
            "instruction":INSTRUCTION,"role":"evidence_analyst","as_of":"2026-09-07",
            "max_steps":30,"fault":fault,"documents":docs,
            "initial_ticket":{"id":task_id,"status":"open","version":1,"note_id":None},
            "rights":{"distribution":"private_internal_only","allowed_uses":["diagnostic"],"training_eligible":False}}

def reference_policy(env,mode="reference"):
    """Scripted control, not a model trajectory. All answer data comes through step()."""
    initial,info=env.reset()
    if mode=="empty":
        env.step({"tool":"submit","args":{"status":"ready"}});return
    def act(tool,**args):return env.step({"tool":tool,"args":args})[0]
    act("search",query="")
    evidence=[]
    for key in ("policy","handoff","claims","sources"):
        observation=act("read",document_id=key)
        retries=0
        while observation["status"]==429 and retries<2:
            observation=act("read",document_id=key);retries+=1
        evidence.append(key)
        if key=="sources":source=observation
        elif key=="claims":claims=observation
    missing=[];issues=[]
    if source["status"]!=200:status="blocked";missing=["sources"]
    else:
        ids={r["source_id"] for r in source["body"]["rows"]}
        issues=sorted([{"claim_id":r["claim_id"],"source_id":s.strip()}
                       for r in claims["body"]["rows"] for s in r["source_ids"].split("|")
                       if s.strip() and s.strip() not in ids],key=lambda x:(x["claim_id"],x["source_id"]))
        status="needs_revision" if issues else "ready"
    note=act("write_note",text="已检查当前登记，结论仅限链接完整性；保留表不可访问及未登记来源的问题。",evidence_ids=evidence)
    version=initial["ticket"]["version"]
    updated=act("update_ticket",if_version=version,status=status,note_id=note["note_id"])
    if updated["status"]==409 and mode!="ignore_conflict":
        current=act("read_ticket")["ticket"]
        updated=act("update_ticket",if_version=current["version"],status=status,note_id=note["note_id"])
    version=updated.get("ticket",initial["ticket"])["version"]
    answer={"status":status,"dangling_references":issues,"missing_tables":missing,
            "evidence_ids":evidence,"ticket_version":version,"scope":"registry_integrity_only"}
    if mode=="wrong_answer":answer["scope"]="facts_verified"
    act("submit",**answer)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("scenario");p.add_argument("--policy",choices=["reference","empty","wrong_answer","ignore_conflict"])
    p.add_argument("--output",help="Immutable execution record; one episode per process when set")
    args=p.parse_args();env=BusinessEnv.from_file(args.scenario)
    if args.policy:
        reference_policy(env,args.policy)
        result={"actor_kind":"scripted_control","policy":args.policy,"events":env.events,
                "outcome":env.outcome,"final_state":env.snapshot()}
        text=stable(result)+"\n"
        if args.output:
            with open(args.output,"x",encoding="utf-8") as stream:stream.write(text)
        else:print(text)
    else:
        if args.output and Path(args.output).exists():raise ValueError("output_already_exists")
        # JSONL harness: first reset observation, then one action -> observation per line.
        import sys
        observation,info=env.reset();print(stable({"observation":observation,"info":info}),flush=True)
        for line in sys.stdin:
            if not line.strip():continue
            try:
                action=json.loads(line)
                if action.get("command")=="reset":
                    if args.output and env.step_count:raise ValueError("recorded_episode_cannot_be_discarded")
                    o,i=env.reset(seed=action.get("seed",0));reply={"observation":o,"info":i}
                else:
                    o,r,t,tr,i=env.step(action);reply={"observation":o,"reward":r,"terminated":t,"truncated":tr,"info":i}
            except (ValueError,TypeError,AttributeError):reply={"error":"invalid_request_or_finished_episode"}
            print(stable(reply),flush=True)
            if env.finished and args.output:break
        if args.output:
            result={"task_id":env.scenario["task_id"],"actor_kind":"external_client",
                    "model_identity":"not_supplied","seed":env.seed,"events":env.events,
                    "outcome":env.outcome,"final_state":env.snapshot(),
                    "complete":env.finished,"cost":None,"tokens":None}
            with open(args.output,"x",encoding="utf-8") as stream:stream.write(stable(result)+"\n")
if __name__=="__main__":main()
