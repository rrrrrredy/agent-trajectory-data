"""Loopback evaluation API: durable credits, frozen trials and idempotent actions."""
from __future__ import annotations
import hashlib
import json
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager, closing
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from .core import read, digest, grade, now
from .taskpacks import validate_task
from .governance import withdrawal_reason

IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}")


class APIError(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code
        super().__init__(code)


class EvaluationStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.folder = self.root / "evaluation"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.database = self.folder / "service.sqlite3"
        with closing(self.connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS clients (
                    token_hash TEXT PRIMARY KEY, label TEXT NOT NULL,
                    credits INTEGER NOT NULL CHECK(credits >= 0), created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS trials (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, request_id TEXT NOT NULL,
                    request_hash TEXT NOT NULL, task TEXT NOT NULL, state TEXT NOT NULL,
                    deadline REAL NOT NULL, UNIQUE(owner, request_id));
                CREATE TABLE IF NOT EXISTS requests (
                    trial_id TEXT NOT NULL, request_id TEXT NOT NULL, request_hash TEXT NOT NULL,
                    response TEXT NOT NULL, PRIMARY KEY(trial_id, request_id));
            """)

    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        return db

    @contextmanager
    def transaction(self, token):
        if not isinstance(token, str) or not 20 <= len(token) <= 256:
            raise APIError(401, "invalid_token")
        owner = hashlib.sha256(token.encode()).hexdigest()
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            client = db.execute("SELECT * FROM clients WHERE token_hash=?", (owner,)).fetchone()
            if client is None:
                raise APIError(401, "invalid_token")
            yield db, owner, client
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def issue_key(self, path, label, credits):
        if (not isinstance(label, str) or not IDENTIFIER.fullmatch(label)
                or type(credits) is not int or not 1 <= credits <= 100000):
            raise ValueError("invalid_client_policy")
        path = Path(path).resolve()
        path.relative_to(self.root)  # Credentials stay inside the ignored data tree.
        path.parent.mkdir(parents=True, exist_ok=True)
        token = secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(token.encode()).hexdigest()
        # Never overwrite an existing credential or print the token.
        with path.open("x", encoding="utf-8") as stream:
            json.dump({"token": token, "label": label}, stream)
        with closing(self.connect()) as db, db:
            db.execute("INSERT INTO clients VALUES (?, ?, ?, ?)", (key_hash, label, credits, now()))
        return {"key_file": str(path), "key_id": key_hash[:12], "credits": credits,
                "credit_unit": "one_trial", "payment_recorded": False}

    def task(self, task_id):
        if not isinstance(task_id, str) or not IDENTIFIER.fullmatch(task_id):
            raise APIError(400, "invalid_task_id")
        try:
            task = validate_task(read(self.root / "tasks" / (task_id + ".json")))
        except (OSError, ValueError, TypeError, KeyError):
            raise APIError(404, "task_unavailable")
        self.allowed(task)
        return task

    def allowed(self, task):
        if "diagnostic" not in task.get("rights", {}).get("allowed_uses", []):
            raise APIError(403, "diagnostic_rights_missing")
        if withdrawal_reason(self.root, task):
            raise APIError(410, "source_withdrawn")

    def catalogue(self, token):
        with self.transaction(token) as (_, __, client):
            items = []
            for path in sorted((self.root / "tasks").glob("*.json")):
                try:
                    task = self.task(path.stem)
                    items.append({"task_id": task["task_id"], "profile": task.get("profile", "closed-facts-v1"),
                                  "split": task["split"]})
                except APIError:
                    continue
            return {"tasks": items, "credits": client["credits"], "scope": "internal_diagnostics"}

    @staticmethod
    def request_id(value):
        if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
            raise APIError(400, "invalid_request_id")

    @staticmethod
    def public_view(trial_id, task, state):
        return {"trial_id": trial_id, "task": task["public"], "step": state["step"],
                "status": state["status"], "terminal_reason": state.get("terminal_reason"),
                "evaluation": state.get("evaluation"), "max_steps": 8,
                "actor_kind": "external_client", "model_identity": "unverified_client",
                "observations": state["observations"]}

    def start(self, token, body):
        if not isinstance(body, dict) or set(body) != {"request_id", "task_id"}:
            raise APIError(400, "invalid_start_request")
        self.request_id(body["request_id"])
        fingerprint = digest(body)
        with self.transaction(token) as (db, owner, client):
            old = db.execute("SELECT * FROM trials WHERE owner=? AND request_id=?",
                             (owner, body["request_id"])).fetchone()
            if old:
                if old["request_hash"] != fingerprint:
                    raise APIError(409, "idempotency_conflict")
                task, state = json.loads(old["task"]), json.loads(old["state"])
                self.allowed(task)
                return self.public_view(old["id"], task, state)
            task = self.task(body["task_id"])
            if client["credits"] <= 0:
                raise APIError(429, "trial_credits_exhausted")
            identifier = uuid.uuid4().hex
            state = {"step": 0, "status": "running", "observations": [], "calls": {}, "actions": [],
                     "created_at": now(), "task_hash": digest(task)}
            db.execute("UPDATE clients SET credits=credits-1 WHERE token_hash=?", (owner,))
            db.execute("INSERT INTO trials VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (identifier, owner, body["request_id"], fingerprint,
                        json.dumps(task), json.dumps(state), time.time() + 300))
            return self.public_view(identifier, task, state)

    def get(self, token, trial_id):
        with self.transaction(token) as (db, owner, _):
            trial, task, state = self.load_trial(db, owner, trial_id)
            if state["status"] == "running" and time.time() >= trial["deadline"]:
                self.finish(task, state, "trial_deadline")
                db.execute("UPDATE trials SET state=? WHERE id=?", (json.dumps(state), trial_id))
            return self.public_view(trial_id, task, state)

    def load_trial(self, db, owner, trial_id):
        if not isinstance(trial_id, str) or not re.fullmatch(r"[a-f0-9]{32}", trial_id):
            raise APIError(404, "trial_unavailable")
        row = db.execute("SELECT * FROM trials WHERE id=? AND owner=?", (trial_id, owner)).fetchone()
        if not row:
            raise APIError(404, "trial_unavailable")
        task, state = json.loads(row["task"]), json.loads(row["state"])
        self.allowed(task)
        return row, task, state

    @staticmethod
    def finish(task, state, reason, submission=None):
        state.update(status="finished", terminal_reason=reason, ended_at=now(),
                     evaluation=grade(task, submission, state["observations"]))
        # No expected answer or private failure details in the response.
        state["evaluation"] = {k: state["evaluation"][k] for k in ("outcome", "passed")}

    def action(self, token, trial_id, body):
        if not isinstance(body, dict) or set(body) != {"request_id", "expected_step", "action"}:
            raise APIError(400, "invalid_action_request")
        self.request_id(body["request_id"])
        action = body["action"]
        if type(body["expected_step"]) is not int or not isinstance(action, dict):
            raise APIError(400, "invalid_action_request")
        if action.get("tool") == "fetch_source":
            if set(action) != {"tool", "source_id"} or not isinstance(action["source_id"], str):
                raise APIError(400, "invalid_fetch_action")
        elif action.get("tool") == "submit_answer":
            if set(action) != {"tool", "verdict", "answer", "evidence_ids"}:
                raise APIError(400, "invalid_submit_action")
        else:
            raise APIError(400, "unsupported_tool")
        fingerprint = digest(body)
        with self.transaction(token) as (db, owner, _):
            trial, task, state = self.load_trial(db, owner, trial_id)
            old = db.execute("SELECT * FROM requests WHERE trial_id=? AND request_id=?",
                             (trial_id, body["request_id"])).fetchone()
            if old:
                if old["request_hash"] != fingerprint:
                    raise APIError(409, "idempotency_conflict")
                return json.loads(old["response"])
            if state["status"] != "running":
                raise APIError(409, "trial_finished")
            if body["expected_step"] != state["step"]:
                raise APIError(409, "step_conflict")
            if time.time() >= trial["deadline"]:
                self.finish(task, state, "trial_deadline")
            else:
                state["actions"].append(action)
                state["step"] += 1
                if action["tool"] == "submit_answer":
                    self.finish(task, state, "submitted", action)
                else:
                    source = action["source_id"]
                    if source not in task["environment"]:
                        self.finish(task, state, "disallowed_source")
                    elif state["calls"].get(source, 0) >= 3:
                        self.finish(task, state, "tool_retry_exhausted")
                    else:
                        count = state["calls"].get(source, 0)
                        cfg = task["environment"][source]
                        status = cfg["responses"][min(count, len(cfg["responses"]) - 1)]
                        observation = {"source_id": source, "status": status, "attempt": count + 1}
                        if status == 200:
                            observation["document"] = cfg["document"]
                        state["calls"][source] = count + 1
                        state["observations"].append(observation)
                    if state["status"] == "running" and state["step"] >= 8:
                        self.finish(task, state, "step_limit")
            response = self.public_view(trial_id, task, state)
            db.execute("UPDATE trials SET state=? WHERE id=?", (json.dumps(state), trial_id))
            db.execute("INSERT INTO requests VALUES (?, ?, ?, ?)",
                       (trial_id, body["request_id"], fingerprint, json.dumps(response)))
            return response


def make_server(root, port=8765):
    store = EvaluationStore(root)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # No headers, tokens or request bodies in access logs.

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def do_GET(self):
            self.respond()

        def do_POST(self):
            self.respond()

        def respond(self):
            status = 200
            try:
                header = self.headers.get("Authorization", "")
                token = header[7:] if header.startswith("Bearer ") else ""
                body = None
                if self.command == "POST":
                    if self.headers.get("Transfer-Encoding"):
                        raise APIError(400, "unsupported_transfer_encoding")
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 65536:
                        # Drain a small oversized request so Windows can deliver the 413
                        # without resetting a connection with unread buffered bytes.
                        if 65536 < size <= 131072:
                            self.rfile.read(size)
                        raise APIError(413, "body_limit")
                    body = json.loads(self.rfile.read(size), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                pieces = self.path.split("/")
                if self.command == "GET" and self.path == "/v1/tasks":
                    response = store.catalogue(token)
                elif self.command == "POST" and self.path == "/v1/trials":
                    response = store.start(token, body)
                elif len(pieces) == 4 and pieces[1:3] == ["v1", "trials"] and self.command == "GET":
                    response = store.get(token, pieces[3])
                elif len(pieces) == 5 and pieces[1:3] == ["v1", "trials"] and pieces[4] == "actions" and self.command == "POST":
                    response = store.action(token, pieces[3], body)
                else:
                    raise APIError(404, "route_unavailable")
            except APIError as exc:
                status, response = exc.status, {"error": exc.code}
            except (ValueError, TypeError, OverflowError, RecursionError):
                status, response = 400, {"error": "invalid_json_request"}
            except (OSError, sqlite3.Error, KeyError):
                status, response = 503, {"error": "service_unavailable"}
            data = json.dumps(response, ensure_ascii=False, allow_nan=False).encode()
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass
    server = HTTPServer(("127.0.0.1", port), Handler)
    server.timeout = 0.5
    return server
