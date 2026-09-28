"""Regression cases for observed reward loopholes and episode transport."""
import copy
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
SCRIPTS=Path(__file__).resolve().parents[1]/"scripts"
spec=importlib.util.spec_from_file_location("b2",SCRIPTS/"business_env_v2.py")
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

def scenario(fault="clean"):
    original=b.v1.make_scenario("fixture","fixture-family",[{"source_id":"S01"}],
                               [{"claim_id":"C01","source_ids":"S01"}],fault)
    return b.revise_scenario(original)

def act(env,tool,**args):return env.step({"tool":tool,"args":args})[0]

def evidence(env):
    for key in ("policy","handoff","claims","sources"):act(env,"read",document_id=key)

def submit(env,status,issues,note_id="note-1"):
    out=act(env,"update_ticket",if_version=env.ticket["version"],status=status,note_id=note_id)
    return env.step({"tool":"submit","args":{
        "status":status,"dangling_references":issues,"missing_tables":[],
        "scope":"registry_integrity_only","ticket_version":env.ticket["version"],
        "evidence_ids":["policy","handoff","sources","claims"]}})[1]

class EvidenceReceiptTests(unittest.TestCase):
    def test_a_429_is_not_document_evidence(self):
        env=b.BusinessEnv(scenario("tool_retry"));evidence(env)
        result=act(env,"write_note",text="guessed contents",evidence_ids=list(b.REQUIRED))
        self.assertEqual(result["status"],422)
        reward=submit(env,"needs_revision",[{"claim_id":"C01","source_id":"S_UNREGISTERED"}])
        self.assertEqual(reward,0)
        self.assertFalse(env.outcome["checks"]["observed_evidence"])

    def test_later_read_does_not_create_an_earlier_note(self):
        env=b.BusinessEnv(scenario("tool_retry"));evidence(env)
        act(env,"write_note",text="premature note",evidence_ids=list(b.REQUIRED))
        act(env,"read",document_id="sources");act(env,"read",document_id="sources")
        self.assertEqual(env.notes,[])
        self.assertEqual(submit(env,"needs_revision",[{"claim_id":"C01","source_id":"S_UNREGISTERED"}]),0)

    def test_recovery_creates_a_new_evidence_bound_note(self):
        env=b.BusinessEnv(scenario("tool_retry"));evidence(env)
        act(env,"write_note",text="too early",evidence_ids=list(b.REQUIRED))
        act(env,"read",document_id="sources");act(env,"read",document_id="sources")
        note=act(env,"write_note",text="current registry checked",evidence_ids=list(b.REQUIRED))
        self.assertEqual(note["status"],200)
        self.assertEqual(submit(env,"needs_revision",[{"claim_id":"C01","source_id":"S_UNREGISTERED"}]),1)
        self.assertIn(422,[e["observation"]["status"] for e in env.events])
        self.assertEqual(env.notes[0]["evidence_receipts"]["sources"]["status"],200)

    def test_new_note_can_correct_a_previously_updated_ticket(self):
        env=b.BusinessEnv(scenario());evidence(env)
        first=act(env,"write_note",text="first note",evidence_ids=list(b.REQUIRED))
        act(env,"update_ticket",if_version=1,status="needs_revision",note_id=first["note_id"])
        revised=act(env,"write_note",text="correction",evidence_ids=list(b.REQUIRED))
        self.assertEqual(submit(env,"ready",[],revised["note_id"]),1)
        self.assertEqual(len(env.notes),2);self.assertEqual(len(env.ticket_updates),2)

    def test_denied_source_supports_a_blocked_result(self):
        env=b.BusinessEnv(scenario("access_revoked"));b.reference_policy(env)
        self.assertEqual(env.outcome["reward"],1)
        self.assertEqual(env.notes[0]["evidence_receipts"]["sources"]["status"],403)

    def test_reference_keeps_all_five_states_solvable(self):
        for fault in ("clean","missing_reference","tool_retry","access_revoked","concurrent_edit"):
            env=b.BusinessEnv(scenario(fault));b.reference_policy(env)
            run=b.record(env,"scripted_control")
            self.assertEqual(b.verify_record(env.scenario,run)["reward"],1)

    def test_altered_receipt_cannot_be_replayed(self):
        env=b.BusinessEnv(scenario());b.reference_policy(env);run=b.record(env,"scripted_control")
        run["final_state"]["notes"][0]["evidence_receipts"]["sources"]["status"]=429
        with self.assertRaisesRegex(ValueError,"run_result_mismatch"):b.verify_record(env.scenario,run)

    def test_boolean_is_not_a_ticket_version(self):
        env=b.BusinessEnv(scenario());evidence(env)
        note=act(env,"write_note",text="note",evidence_ids=list(b.REQUIRED))
        result=act(env,"update_ticket",if_version=True,status="ready",note_id=note["note_id"])
        self.assertEqual(result["status"],400);self.assertEqual(env.ticket_updates,[])

class TransportTests(unittest.TestCase):
    def test_malformed_inputs_are_logged_and_consume_budget(self):
        env=b.BusinessEnv(scenario());out=io.StringIO()
        raw=("{bad\n[]\nnull\n"+'{"tool":"read","args":{"document_id":NaN}}\n')*10
        run=b.serve(env,io.StringIO(raw),out)
        self.assertEqual(len(run["events"]),30)
        self.assertEqual(len(run["transport"]),30)
        self.assertTrue(run["complete"]);self.assertEqual(run["outcome"]["reason"],"step_budget_exhausted")
        self.assertEqual(b.verify_record(env.scenario,run)["reward"],0)

    def test_reset_cannot_erase_failed_attempts(self):
        env=b.BusinessEnv(scenario())
        run=b.serve(env,io.StringIO('{"tool":"bad"}\n{"command":"reset","seed":2}\n'),io.StringIO())
        self.assertEqual(len(run["events"]),2);self.assertEqual(run["seed"],0)
        self.assertEqual(run["events"][1]["action"]["tool"],"protocol_error")
        self.assertFalse(run["complete"])
        self.assertEqual(b.verify_record(env.scenario,run)["reason"],"incomplete_episode")

    def test_edited_wire_action_and_seed_are_rejected(self):
        env=b.BusinessEnv(scenario())
        run=b.serve(env,io.StringIO('{"command":"reset","seed":7}\n{"tool":"read_ticket"}\n'),io.StringIO())
        self.assertEqual(b.verify_record(env.scenario,run)["reason"],"incomplete_episode")
        tampered=copy.deepcopy(run);tampered["transport"][1]["applied_action"]={"tool":"submit"}
        with self.assertRaisesRegex(ValueError,"wire_action_changed"):b.verify_record(env.scenario,tampered)
        tampered=copy.deepcopy(run);row=tampered["transport"][0]
        row["raw_input"]='{"command":"reset","seed":8}\n'
        row["raw_sha256"]=b.hashlib.sha256(row["raw_input"].encode()).hexdigest()
        with self.assertRaisesRegex(ValueError,"transport_reset_seed_changed"):b.verify_record(env.scenario,tampered)

    def test_reference_cli_produces_a_gradable_record(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);src=root/"scenario.json";dst=root/"episode.json"
            src.write_text(b.stable(scenario("tool_retry")),encoding="utf-8")
            command=[sys.executable,"-X","utf8","-B",str(SCRIPTS/"business_env_v2.py"),str(src)]
            r=subprocess.run(command+["--policy","reference","--output",str(dst)],capture_output=True,text=True,encoding="utf-8",timeout=20)
            self.assertEqual(r.returncode,0,r.stderr)
            saved=json.loads(dst.read_bytes());self.assertEqual(saved["task_id"],scenario("tool_retry")["task_id"])
            r=subprocess.run(command+["--verify",str(dst)],capture_output=True,text=True,encoding="utf-8",timeout=20)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(json.loads(r.stdout)["reward"],1)
            before=dst.read_bytes()
            r=subprocess.run(command+["--policy","reference","--output",str(dst)],capture_output=True,text=True,encoding="utf-8",timeout=20)
            self.assertNotEqual(r.returncode,0);self.assertEqual(dst.read_bytes(),before)
if __name__=="__main__":unittest.main()
