from contextlib import closing
import copy
import json
import os
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from agentdata.core import read, run_task, quality_decision, split_for
from agentdata.factory import run_factory
from agentdata.research_tasks import generate_research
from agentdata.research_protocol import reference_action
from agentdata.sessions import import_session
from agentdata.governance import withdraw, resolve_release
from agentdata.release import build_release
from agentdata.evalapi import EvaluationStore, APIError, make_server


class OperationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "data"
        seed = next(i for i in range(100) if split_for(f"research-{i}-00000") == "train")
        self.paths = generate_research(self.root, 1, seed)
        self.task = next(read(p) for p in self.paths if read(p)["variant"] == "transient_retry")

    def key(self, store, name="client", credits=3):
        path = self.root / "keys" / (name + ".json")
        store.issue_key(path, name, credits)
        return read(path)["token"]

    def test_development_split_stays_out_of_training_even_with_script_override(self):
        seed = next(i for i in range(100) if split_for(f"research-{i}-00000") == "development")
        task = read(generate_research(self.root, 1, seed)[0])
        record = run_task(self.root, task)
        decision = quality_decision(self.root, record, "sft", allow_scripted=True)
        self.assertIn("development_not_for_training", decision["reasons"])

    def test_atomic_state_update_survives_temporary_windows_reader_lock(self):
        from agentdata.pipeline import atomic_json
        path = self.root / "state.json"
        atomic_json(path, {"status": "old"})
        real_replace = os.replace
        calls = 0
        def locked_then_replace(source, target):
            nonlocal calls
            calls += 1
            if calls < 3:
                self.assertEqual(read(path), {"status": "old"})
                raise PermissionError("simulated_shared_reader")
            real_replace(source, target)
        with patch("agentdata.pipeline.os.replace", side_effect=locked_then_replace):
            atomic_json(path, {"status": "new"})
        self.assertEqual(read(path), {"status": "new"})
        self.assertEqual(calls, 3)

    def test_withdrawal_blocks_existing_release_trace_and_future_packages(self):
        run = run_task(self.root, self.task)
        release = self.root / "products/suite.zip"
        build_release(self.root, release, "suite", "licensed")
        self.assertEqual(resolve_release(self.root, "suite", "licensed"), release.resolve())
        withdraw(self.root, "source_group", self.task["source_group"], "owner_withdrawal")
        self.assertIn("source_withdrawn", quality_decision(self.root, run)["reasons"])
        with self.assertRaisesRegex(ValueError, "source_withdrawn"):
            resolve_release(self.root, "suite", "licensed")
        with self.assertRaisesRegex(ValueError, "no_eligible_tasks"):
            build_release(self.root, self.root / "products/after.zip", "after", "licensed")
        self.assertTrue(release.exists())  # Original evidence is retained; downloaded copies cannot be recalled.

    def test_session_filters_hidden_content_and_marks_incomplete_tools(self):
        rows = [
            {"type": "session_meta", "payload": {"id": "same-session"}},
            {"type": "turn_context", "payload": {"model": "configured-model"}},
            {"type": "response_item", "payload": {"type": "message", "role": "system",
              "content": [{"type": "input_text", "text": "private-system-sentinel"}]}},
            {"type": "response_item", "payload": {"type": "message", "role": "assistant",
              "channel": "analysis", "content": [{"type": "output_text", "text": "private-analysis-sentinel"}]}},
            {"type": "response_item", "payload": {"type": "reasoning", "text": "private-reasoning-sentinel"}},
            {"type": "response_item", "payload": {"type": "message", "role": "user",
              "content": [{"type": "input_text", "text": "Make a report"}]}},
            {"type": "response_item", "payload": {"type": "function_call", "call_id": "a",
              "name": "fetch", "arguments": '{"url":"example.test"}'}},
            {"type": "response_item", "payload": {"type": "function_call", "call_id": "b",
              "name": "fetch", "arguments": "{}"}},
            {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "a", "output": "visible"}},
            {"type": "response_item", "payload": {"type": "message", "role": "assistant", "channel": "final",
              "content": [{"type": "output_text", "text": "Report complete"}]}}]
        source = self.base / "session.jsonl"
        source.write_text("\n".join(json.dumps(x) for x in rows) + "\n{bad", encoding="utf-8")
        summary = import_session(self.root, source)
        self.assertEqual(summary["unmatched_calls"], 1)
        self.assertFalse(summary["training_eligible"])
        body = (self.root / "runtime_sessions" / summary["import_id"] / "events.jsonl").read_text()
        self.assertNotIn("private-", body)
        self.assertIn("Report complete", body)
        self.assertEqual(import_session(self.root, source), summary)
        rows.append({"type": "response_item", "payload": {"type": "function_call_output", "call_id": "b", "output": "done"}})
        source.write_text("\n".join(json.dumps(x) for x in rows), encoding="utf-8")
        later = import_session(self.root, source)
        self.assertEqual(later["family_id"], summary["family_id"])
        self.assertNotEqual(later["import_id"], summary["import_id"])

    def test_session_factory_never_calls_model_and_deduplicates(self):
        source = self.base / "source"
        inbox = self.base / "inbox"
        source.mkdir()
        inbox.mkdir()
        (source / "run.jsonl").write_text(json.dumps({"type": "response_item", "payload": {
            "type": "message", "role": "user", "content": [{"type": "input_text", "text": "visible"}]}}))
        (inbox / "run.json").write_text(json.dumps({"source": "runtime", "path": "run.jsonl"}))
        config = {"pipeline": {"policy": "codex", "monthly_model_calls": 8},
                  "inbox": str(inbox), "sources": {"runtime": {"root": str(source), "kind": "session"}}}
        with patch("agentdata.factory.run_pipeline") as model:
            result = run_factory(self.root, config)
        model.assert_not_called()
        self.assertEqual(result["statuses"]["completed"], 1)
        self.assertEqual(run_factory(self.root, config)["processed_this_tick"], 0)

    def test_duplicate_artifact_cannot_enter_two_split_groups(self):
        source, inbox = self.base / "source", self.base / "inbox"
        source.mkdir()
        inbox.mkdir()
        (source / "same.json").write_text('{"jobs":3}')
        for name in ("a", "b"):
            (inbox / (name + ".json")).write_text(json.dumps({
                "source": "facts", "path": "same.json", "source_group": name}))
        config = {"inbox": str(inbox), "sources": {"facts": {"root": str(source),
                  "selectors": {"jobs": "/jobs"}, "rights": {"basis": "owned", "allowed_uses": ["diagnostic"]}}}}
        result = run_factory(self.root, config)
        self.assertEqual(result["statuses"]["completed"], 1)
        state = read(self.root / "factory/state.json")
        self.assertIn("duplicate_source_across_groups", [x.get("reason") for x in state["jobs"].values()])

    def test_api_durable_idempotency_ownership_and_credits(self):
        store = EvaluationStore(self.root)
        first, second = self.key(store, "one", 1), self.key(store, "two", 1)
        body = {"task_id": self.task["task_id"], "request_id": "start"}
        initial = store.start(first, body)
        self.assertEqual(store.start(first, body), initial)
        self.assertEqual(store.catalogue(first)["credits"], 0)
        self.assertNotIn("oracle", json.dumps(initial))
        with self.assertRaises(APIError) as error:
            store.start(first, {**body, "request_id": "another"})
        self.assertEqual(error.exception.status, 429)
        with self.assertRaises(APIError) as error:
            store.get(second, initial["trial_id"])
        self.assertEqual(error.exception.status, 404)
        state = initial
        for step in range(8):
            action = reference_action(state["task"], state["observations"])
            request = {"request_id": "action-" + str(step), "expected_step": state["step"], "action": action}
            state = store.action(first, initial["trial_id"], request)
            self.assertEqual(store.action(first, initial["trial_id"], request), state)
            if state["status"] == "finished":
                break
        self.assertEqual(state["evaluation"], {"outcome": "pass", "passed": True})
        self.assertEqual(state["step"], 5)
        restarted = EvaluationStore(self.root)
        self.assertEqual(restarted.get(first, initial["trial_id"]), state)
        with self.assertRaises(APIError) as error:
            restarted.action(first, initial["trial_id"], {**request, "expected_step": 999})
        self.assertEqual(error.exception.code, "idempotency_conflict")

    def test_api_deadline_and_withdrawal_block_mid_trial(self):
        store = EvaluationStore(self.root)
        token = self.key(store)
        initial = store.start(token, {"task_id": self.task["task_id"], "request_id": "start"})
        with closing(store.connect()) as db, db:
            db.execute("UPDATE trials SET deadline=0")
        self.assertEqual(store.get(token, initial["trial_id"])["evaluation"]["outcome"], "not_assessed")
        other = store.start(token, {"task_id": self.task["task_id"], "request_id": "second"})
        withdraw(self.root, "source_group", self.task["source_group"], "owner_withdrawal")
        with self.assertRaises(APIError) as error:
            store.get(token, other["trial_id"])
        self.assertEqual(error.exception.status, 410)

    def test_credit_reservation_is_atomic_across_workers(self):
        store = EvaluationStore(self.root)
        token = self.key(store, credits=1)
        outcomes = []
        barrier = threading.Barrier(2)
        def start(identifier):
            barrier.wait()
            try:
                outcomes.append(store.start(token, {"task_id": self.task["task_id"], "request_id": identifier})["status"])
            except APIError as error:
                outcomes.append(error.code)
        threads = [threading.Thread(target=start, args=(str(i),)) for i in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertCountEqual(outcomes, ["running", "trial_credits_exhausted"])

    def test_http_auth_body_limits_and_allowed_action_surface(self):
        store = EvaluationStore(self.root)
        token = self.key(store)
        server = make_server(self.root, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        base = "http://127.0.0.1:" + str(server.server_port)
        def request(path, body=None, auth=True):
            data = None if body is None else json.dumps(body).encode()
            req = urllib.request.Request(base + path, data=data, headers={
                "Authorization": "Bearer " + (token if auth else "wrong"), "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.load(response)
        with self.assertRaises(urllib.error.HTTPError) as error:
            request("/v1/tasks", auth=False)
        self.assertEqual(error.exception.code, 401)
        trial = request("/v1/trials", {"request_id": "web", "task_id": self.task["task_id"]})
        with self.assertRaises(urllib.error.HTTPError) as error:
            request("/v1/trials/" + trial["trial_id"] + "/actions",
                    {"request_id": "shell", "expected_step": 0, "action": {"tool": "shell", "command": "never execute"}})
        self.assertEqual(error.exception.code, 400)
        self.assertEqual(request("/v1/trials/" + trial["trial_id"])["step"], 0)
        self.assertNotIn("environment", json.dumps(trial))
        with self.assertRaises(urllib.error.HTTPError) as error:
            request("/v1/trials", {"request_id": "oversize", "x": "a" * 70000})
        self.assertEqual(error.exception.code, 413)


if __name__ == "__main__":
    unittest.main()
