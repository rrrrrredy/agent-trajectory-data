"""Executable minimal repairs grounded in retained failure incidents."""
from __future__ import annotations
import argparse,copy,json,hashlib,sys
from pathlib import Path
import research_env_v3 as base
import repair_executor as runner
VERSION="research-repair-1"
TOOLS=("read","patch","test","read_ticket","write_note","update_ticket","submit")
canonical,digest,check,equal=base.canonical,base.digest,base.check,base.equal
def code_hash(code):return hashlib.sha256(code.encode()).hexdigest()
POLICY={"workflow":"Read the contract and current worker; reproduce a failing baseline with test BEFORE patching. Patch solve(data), reread the worker, run test again, then write_note, update_ticket and submit. A passing test is valid only for that exact current code/version. On 409 reread before retrying.",
"python_subset":"Exactly one solve function, one argument; json.loads/dumps and hashlib.sha256 are provided. Builtins len, sorted, list, dict, set, tuple, bool, str, int, any, all, isinstance and ValueError are available. Conditionals, for/comprehensions, simple assignments and lambda sort keys are supported. No imports, files, network, classes, recursion, while, try or private attributes; 20000 executed instructions per case. Only the worker can be patched.",
"note_contract":{"status":"ready","scope":"bounded_program_repair","code_sha256":"from current worker read or test","test_run_id":"latest successful test id","diagnosis":"short visible evidence-based diagnosis"},
"grade_boundary":"Public tests aid diagnosis. Independent held-back behavioral cases also grade submission. Historical source records and reference solutions are evaluator-only. This is a minimal reproduction, not recovery of the entire historical machine."}
HELP={"read":{"args":{"document_id":"one of the initial document IDs"}},"patch":{"args":{"if_version":"current worker integer version","old":"exact nonempty substring occurring once","new":"replacement text"}},"test":{"args":{},"rule":"Runs public behavioral tests against current worker and returns a code-bound receipt."},"read_ticket":{"args":{}},"write_note":{"args":{"report":"policy note_contract object"}},"update_ticket":{"args":{"if_version":"ticket version","status":"ready","note_id":"returned note id"}},"submit":{"args":{"note_id":"returned note id","ticket_version":"current ticket version"}}}
class ResearchEnv(base.ResearchEnv):
    def __init__(self,scenario):
        self.scenario=copy.deepcopy(scenario);check(scenario["version"]==VERSION,"unsupported_scenario");check(12<=scenario["max_steps"]<=100,"invalid_budget");self.reset()
    def reset(self,seed=0):
        check(type(seed) is int,"invalid_seed");self.seed=seed;self.code=self.scenario["initial_code"];self.version=1;self.read_version=None;self.reads=[];self.tests=[];self.notes={};self.events=[];self.conflict_injected=False;self.submission=None;self.finished=self.terminated=self.truncated=False
        self.ticket={"id":"task-"+digest(self.scenario["task_id"])[:16],"version":1,"status":"open","note_id":None}
        self.initial={"task_id":self.ticket["id"],"mechanism":"bounded_program_repair","task":"Diagnose and repair the supplied pure-function worker, reproduce the failure, and verify the fix.","max_steps":self.scenario["max_steps"],"tools":HELP,"documents":list(self.scenario["document_order"]),"document_roles":self.scenario["document_ids"],"ticket":copy.deepcopy(self.ticket)}
        return copy.deepcopy(self.initial),{"environment_version":VERSION,"seed":seed}
    def snapshot(self):return copy.deepcopy({"code":self.code,"version":self.version,"read_version":self.read_version,"reads":self.reads,"tests":self.tests,"notes":self.notes,"ticket":self.ticket,"conflict_injected":self.conflict_injected,"submission":self.submission})
    def _action(self,action,step):
        if not isinstance(action,dict) or set(action)!={"tool","args"} or not isinstance(action["args"],dict):return {"status":400,"error":"invalid_action"}
        tool,args=action["tool"],action["args"]
        if tool not in TOOLS:return {"status":400,"error":"unknown_tool"}
        ids=self.scenario["document_ids"]
        if tool=="read":
            if set(args)!={"document_id"}:return {"status":422,"error":"document_id_required"}
            key=args["document_id"];role=next((r for r,k in ids.items() if k==key),None)
            if role is None:return {"status":404,"error":"document_not_found"}
            body={"policy":POLICY,"contract":{"text":self.scenario["contract"]},"sample":{"cases":self.scenario["public_cases"]},"worker":{"code":self.code,"code_sha256":code_hash(self.code)}}[role]
            if role=="worker":self.read_version=self.version
            self.reads.append({"role":role,"version":self.version if role=="worker" else 1,"step":step})
            return {"status":200,"document_id":key,"version":self.version if role=="worker" else 1,"body":copy.deepcopy(body)}
        if tool=="patch":
            if set(args)!={"if_version","old","new"} or type(args.get("if_version")) is not int or not all(isinstance(args.get(k),str) for k in ("old","new")):return {"status":422,"error":"patch_contract"}
            if self.scenario["fault"]=="stale_patch" and not self.conflict_injected:
                self.code+="\n# Concurrent edit: preserve this note.\n";self.version+=1;self.conflict_injected=True;return {"status":409,"error":"worker_version_conflict"}
            if args["if_version"]!=self.version:return {"status":409,"error":"worker_version_conflict"}
            if self.read_version!=self.version:return {"status":412,"error":"read_current_worker"}
            if not args["old"] or self.code.count(args["old"])!=1:return {"status":422,"error":"patch_match_must_be_unique"}
            candidate=self.code.replace(args["old"],args["new"],1)
            try:runner.validate(candidate)
            except (ValueError,SyntaxError) as error:return {"status":422,"error":"candidate_rejected","detail":str(error)[:160]}
            self.code=candidate;self.version+=1;return {"status":200,"version":self.version,"code_sha256":code_hash(self.code)}
        if tool=="test":
            if args:return {"status":422,"error":"no_arguments"}
            result=runner.run_cases(self.code,self.scenario["public_cases"]);row={"test_run_id":"test-"+str(len(self.tests)+1),"version":self.version,"code_sha256":code_hash(self.code),"step":step,**result};self.tests.append(row)
            return {"status":200,"test":copy.deepcopy(row)}
        if tool=="write_note":
            report=args.get("report")
            if set(args)!={"report"} or not isinstance(report,dict) or set(report)!={"status","scope","code_sha256","test_run_id","diagnosis"} or not all(isinstance(v,str) for v in report.values()):return {"status":422,"error":"report_contract"}
            key="note-"+str(len(self.notes)+1);self.notes[key]={"report":copy.deepcopy(report),"step":step,"worker_version":self.version,"read_version":self.read_version,"test_ids":[r["test_run_id"] for r in self.tests]};return {"status":200,"note_id":key}
        return super()._action(action,step)
    def step(self,action):
        result=super().step(action);self.events[-1]["reward"]=result[1];return result
    def grade(self):
        note=self.notes.get((self.submission or {}).get("note_id"));report=(note or {}).get("report",{});last=self.tests[-1] if self.tests else {};code=code_hash(self.code)
        checks={"terminal":self.terminated and not self.truncated,"baseline_failure_observed":any(t["version"]==1 and not t["passed"] and t["code_sha256"]==code_hash(self.scenario["initial_code"]) for t in self.tests),"contract_read":any(r["role"]=="contract" for r in self.reads),"actual_edit":self.version>1 and code!=code_hash(self.scenario["initial_code"]),"current_test_pass":bool(last.get("passed")) and last.get("version")==self.version and last.get("code_sha256")==code,"fresh_read":self.read_version==self.version,"private_behavior":False,"verified_note":False,"ticket":False,"concurrent_note_preserved":not self.conflict_injected or "# Concurrent edit: preserve this note." in self.code}
        if self.terminated:checks["private_behavior"]=runner.run_cases(self.code,self.scenario["private_cases"])["passed"]
        if note:
            checks["verified_note"]=report.get("status")=="ready" and report.get("scope")=="bounded_program_repair" and report.get("code_sha256")==code and report.get("test_run_id")==last.get("test_run_id") and last.get("test_run_id") in note["test_ids"] and note["worker_version"]==note["read_version"]==self.version and bool(report.get("diagnosis","").strip())
            checks["ticket"]=self.ticket["status"]=="ready" and self.ticket["note_id"]==self.submission["note_id"] and self.ticket["version"]==self.submission["ticket_version"]
        return {"reward":int(all(checks.values())),"checks":checks,"grader_version":VERSION,"assessed_capability":"bounded_program_repair","research_truth_assessed":False}
def record(env,actor_kind):
    value=base.record(env,actor_kind);value["environment_version"]=VERSION;return value
def verify_record(scenario,run):
    env=ResearchEnv(scenario);initial,_=env.reset(run["seed"])
    check(run["environment_version"]==VERSION and run["task_id"]==scenario["task_id"] and run["scenario_sha256"]==digest(scenario),"scenario_binding_changed");check(equal(initial,run["initial_observation"]),"initial_observation_changed")
    for event in run["events"]:
        env.step(event["action"]);check(equal(env.events[-1],event),"event_replay_changed")
    check(equal(env.snapshot(),run["final_state"]) and run["complete"]==env.finished,"final_state_changed");check(equal(env.grade(),run["grade"]),"grade_changed");return env.grade()
def main():
    parser=argparse.ArgumentParser();parser.add_argument("scenario");parser.add_argument("--output",required=True);args=parser.parse_args();env=ResearchEnv(json.loads(Path(args.scenario).read_bytes()));print(canonical({"observation":env.initial}),flush=True)
    for line in sys.stdin:
        if not line.strip():continue
        observation,reward,terminated,truncated,info=env.step(json.loads(line));Path(args.output).write_text(canonical(record(env,"external_policy"))+"\n",encoding="utf-8",newline="\n");print(canonical({"observation":observation,"reward":reward,"terminated":terminated,"truncated":truncated,"info":info}),flush=True)
        if env.finished:break
if __name__=="__main__":main()
