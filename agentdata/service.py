"""Local background processes with OS locks, heartbeats and cooperative stop."""
from __future__ import annotations
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from .core import now, read
from .pipeline import atomic_json, batch_lock


def folder_for(root, kind):
    if kind not in {"factory", "eval"}:
        raise ValueError("unknown_service_kind")
    folder = Path(root).resolve() / "services" / kind
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def status(root, kind):
    folder = folder_for(root, kind)
    record = read(folder / "status.json") if (folder / "status.json").exists() else {"status": "not_started"}
    try:
        with batch_lock(folder / "process.lock"):
            active = False
    except RuntimeError:
        active = True
    if active:
        record["status"] = "stop_requested" if (folder / "stop").exists() else "running"
    elif record.get("status") in {"running", "starting"}:
        record["status"] = "not_running"
    return {**record, "lock_held": active, "kind": kind}


def start(root, kind, config=None, interval=60, port=8765):
    root = Path(root).resolve()
    folder = folder_for(root, kind)
    with batch_lock(folder / "start.lock"):
        current = status(root, kind)
        if current["lock_held"]:
            return current
        if kind == "factory":
            from .factory import normalize_factory
            if config is None:
                raise ValueError("factory_config_required")
            config = Path(config).resolve()
            normalize_factory(read(config))
        if type(interval) is not int or not 1 <= interval <= 3600 or type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("invalid_service_limits")
        (folder / "stop").unlink(missing_ok=True)
        generation = uuid.uuid4().hex
        argv = [sys.executable, "-B", "-m", "agentdata", "--root", str(root),
                "service-run", "--kind", kind, "--interval", str(interval), "--port", str(port),
                "--generation", generation]
        if config:
            argv.extend(["--config", str(config)])
        with (folder / "process.log").open("ab") as output:
            options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
            child = subprocess.Popen(argv, cwd=Path(__file__).resolve().parent.parent,
                                     stdin=subprocess.DEVNULL, stdout=output, stderr=output, **options)
        until = time.monotonic() + 10
        while time.monotonic() < until:
            current = status(root, kind)
            if current.get("generation") == generation and current.get("status") == "running":
                return current
            if child.poll() is not None:
                raise RuntimeError("service_start_failed_see_local_process_log")
            time.sleep(0.1)
        return {"status": "starting", "pid": child.pid, "kind": kind, "generation": generation}


def stop(root, kind, wait_seconds=10):
    folder = folder_for(root, kind)
    (folder / "stop").touch()
    until = time.monotonic() + wait_seconds
    while time.monotonic() < until:
        current = status(root, kind)
        if not current["lock_held"]:
            return current
        time.sleep(0.1)
    return status(root, kind)  # Never kill a potentially in-flight model request.


def run(root, kind, config=None, interval=60, port=8765, generation=None):
    root = Path(root).resolve()
    folder = folder_for(root, kind)
    with batch_lock(folder / "process.lock"):
        record = {"status": "running", "pid": os.getpid(), "kind": kind, "started_at": now(),
                  "generation": generation, "data_root": str(root)}
        if kind == "factory":
            from .factory import normalize_factory, run_factory
            if not config:
                raise ValueError("factory_config_required")
            config = Path(config).resolve()
            frozen_config = normalize_factory(read(config))
            record.update(config_file=str(config), interval_seconds=interval)
            server = None
        else:
            from .evalapi import make_server
            server = make_server(root, port)
            record["url"] = "http://127.0.0.1:" + str(server.server_port)
        def heartbeat():
            record["heartbeat_at"] = now()
            atomic_json(folder / "status.json", record)
        heartbeat()
        try:
            while not (folder / "stop").exists():
                if server:
                    server.handle_request()
                    heartbeat()
                else:
                    record["last_tick"] = run_factory(root, frozen_config, config.parent,\
                        stop_requested=lambda: (folder / "stop").exists())
                    heartbeat()
                    until = time.monotonic() + interval
                    while time.monotonic() < until and not (folder / "stop").exists():
                        time.sleep(min(1, max(0, until - time.monotonic())))
                        heartbeat()
        except KeyboardInterrupt:
            record["stop_reason"] = "keyboard_interrupt"
        except BaseException as exc:
            record.update(status="failed", error_type=type(exc).__name__)
            raise
        finally:
            if server:
                server.server_close()
            if record["status"] != "failed":
                record["status"] = "stopped"
            record["ended_at"] = now()
            heartbeat()
