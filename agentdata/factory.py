"""Durable local source-to-release worker. No manual review or hidden model sends."""
from __future__ import annotations
import hashlib
import json
import time
from pathlib import Path
from .core import read, digest, now, write_new
from .pipeline import atomic_json, batch_lock, run_pipeline, normalize_config
from .taskpacks import capture_facts
from .training import export_training
from .release import build_release


def normalize_factory(config):
    if not isinstance(config, dict) or set(config) - {"pipeline", "generators", "inbox", "sources", "max_jobs_per_tick", "release_audience"}:
        raise ValueError("invalid_factory_config")
    pipeline = normalize_config(config.get("pipeline", {"policy": "reference"}))
    if "task_ids" in pipeline:
        raise ValueError("factory_selects_tasks_from_sources_and_generators")
    if pipeline["policy"] == "codex" and "monthly_model_calls" not in pipeline:
        raise ValueError("factory_models_require_monthly_cap")
    count = config.get("max_jobs_per_tick", 20)
    if type(count) is not int or not 1 <= count <= 100:
        raise ValueError("invalid_tick_limit")
    audience = config.get("release_audience", "internal")
    if audience not in {"internal", "licensed"}:
        raise ValueError("invalid_audience")
    generators = config.get("generators", [])
    sources = config.get("sources", {})
    if not isinstance(generators, list) or not isinstance(sources, dict):
        raise ValueError("invalid_sources")
    for item in generators:
        if (not isinstance(item, dict) or set(item) != {"id", "profile", "families", "seed"}
                or not isinstance(item["id"], str) or not item["id"]
                or item["profile"] not in {"closed-facts-v1", "research-evidence-v1"}
                or type(item["families"]) is not int or not 1 <= item["families"] <= 1000
                or type(item["seed"]) is not int):
            raise ValueError("invalid_generator")
    for name, source in sources.items():
        if (not isinstance(name, str) or not isinstance(source, dict)
                or set(source) - {"root", "kind", "selectors", "rights", "external_model_allowed"}
                or not isinstance(source.get("root"), str)
                or source.get("kind", "facts") not in {"facts", "session"}
                or (source.get("kind", "facts") == "facts" and (
                    not isinstance(source.get("selectors"), dict) or not isinstance(source.get("rights"), dict)))
                or type(source.get("external_model_allowed", False)) is not bool
                or (source.get("kind") == "session" and source.get("external_model_allowed", False))):
            raise ValueError("invalid_source_policy")
    return {"pipeline": pipeline, "generators": generators, "sources": sources,
            "inbox": config.get("inbox"), "max_jobs_per_tick": count, "release_audience": audience}


def candidate_jobs(config, base):
    for generator in config["generators"]:
        descriptor = {"kind": "generated", "generator": generator}
        yield digest(descriptor)[:32], descriptor, None
    if not config["inbox"]:
        return
    inbox = (base / config["inbox"]).resolve()
    inbox.mkdir(parents=True, exist_ok=True)
    for item in sorted(inbox.glob("*.json")):
        # A malformed envelope has a stable quarantine key; it cannot stop other jobs.
        try:
            if item.stat().st_size > 65536:
                raise ValueError("envelope_too_large")
            envelope = read(item)
            if (not isinstance(envelope, dict) or set(envelope) - {"source", "path", "source_group", "origin", "task_receipt"}
                    or envelope.get("source") not in config["sources"]):
                raise ValueError("unknown_source_or_envelope_field")
            source = config["sources"][envelope["source"]]
            allowed_root = (base / source["root"]).resolve()
            path = (allowed_root / envelope["path"]).resolve()
            path.relative_to(allowed_root)
            size_limit = 100_000_000 if source.get("kind") == "session" else 2_000_000
            if not path.is_file() or path.stat().st_size > size_limit:
                raise ValueError("invalid_source_file")
            source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            descriptor = {"kind": "intake", "envelope": envelope, "source_policy": source,
                          "source_path": str(path), "source_sha256": source_hash}
            yield digest(descriptor)[:32], descriptor, None
        except (OSError, ValueError, TypeError, KeyError) as exc:
            try:
                raw = item.read_bytes() if item.is_file() and item.stat().st_size <= 65536 else b"oversize"
            except OSError:
                raw = b"unavailable"
            yield digest([item.name, hashlib.sha256(raw).hexdigest()])[:32], {
                "kind": "invalid_envelope", "file": item.name}, type(exc).__name__


def run_factory(root, config, config_base=None, stop_requested=None):
    root = Path(root).resolve()
    base = Path(config_base or Path.cwd()).resolve()
    config = normalize_factory(config)
    folder = root / "factory"
    folder.mkdir(parents=True, exist_ok=True)
    with batch_lock(folder / "worker.lock"):
        state_path = folder / "state.json"
        state = read(state_path) if state_path.exists() else {"schema_version": 1, "jobs": {}}
        processed = 0
        for input_id, descriptor, error in candidate_jobs(config, base):
            job_id = digest([input_id, config["pipeline"], config["release_audience"]])[:32]
            old = state["jobs"].get(job_id)
            if old and old["status"] in {"completed", "quarantined", "stopped"}:
                continue
            if processed >= config["max_jobs_per_tick"]:
                break
            if stop_requested and stop_requested():
                break
            processed += 1
            job = old or {"job_id": job_id, "created_at": now(), "attempts": 0}
            state["jobs"][job_id] = job
            if job["attempts"] >= 3:
                job.update(status="quarantined", reason="factory_attempt_limit")
                atomic_json(state_path, state)
                continue
            job.update(status="running", attempts=job["attempts"] + 1)
            atomic_json(state_path, state)
            try:
                if error:
                    raise ValueError(error)
                pipeline = dict(config["pipeline"])
                if descriptor["kind"] == "generated":
                    recipe = descriptor["generator"]
                    pipeline.update(profile=recipe["profile"], families=recipe["families"], seed=recipe["seed"])
                else:
                    source = descriptor["source_policy"]
                    if source.get("kind") == "session":
                        from .sessions import import_session
                        imported = import_session(root, descriptor["source_path"])
                        job.update(status="completed", completed_at=now(), runtime_import=imported,
                                   pipeline_mode="capture_only_no_model_send")
                        atomic_json(state_path, state)
                        continue
                    if pipeline["policy"] == "codex" and not source.get("external_model_allowed", False):
                        raise ValueError("external_model_send_disallowed_for_source")
                    if hashlib.sha256(Path(descriptor["source_path"]).read_bytes()).hexdigest() != descriptor["source_sha256"]:
                        raise ValueError("source_changed_before_intake")
                    envelope = descriptor["envelope"]
                    source_group = envelope["source"] + ":" + envelope["source_group"]
                    source_key = digest([descriptor["source_sha256"], source["selectors"]])
                    registry = state.setdefault("source_registry", {})
                    if source_key in registry and registry[source_key] != source_group:
                        raise ValueError("duplicate_source_across_groups")
                    registry[source_key] = source_group
                    atomic_json(state_path, state)
                    intake = capture_facts(root, descriptor["source_path"], source["selectors"],
                        envelope["source"] + ":" + envelope["source_group"], source["rights"],
                        envelope.get("origin", "artifact_derived"), envelope.get("task_receipt"))
                    if intake["lineage"]["source_sha256"] != descriptor["source_sha256"]:
                        raise ValueError("source_changed_during_intake")
                    pipeline["task_ids"] = intake["task_ids"]
                # Save before execution so resuming cannot silently adopt a changed factory policy.
                frozen = folder / (job_id + "-pipeline.json")
                if frozen.exists():
                    pipeline = read(frozen)
                else:
                    write_new(frozen, pipeline)
                batch_id = "factory-" + job_id
                batch = run_pipeline(root, pipeline, batch_id)
                batch_state = read(root / "batches" / batch_id / "state.json")
                run_ids = {j["run_id"] for j in batch_state["jobs"]}
                task_ids = {j["task_id"] for j in batch_state["jobs"]}
                training = export_training(root, root / "batches" / batch_id / "training", run_ids)
                release = None
                try:
                    release = build_release(root, root / "products" / (job_id + ".zip"), job_id,
                                            config["release_audience"], task_ids=task_ids)
                except ValueError as exc:
                    if str(exc) != "no_eligible_tasks":
                        raise
                    release = {"status": "retained_without_download", "reason": "no_eligible_nonholdout_tasks"}
                completed = batch["status"] in {"completed", "completed_with_errors"}
                job.update(status="completed" if completed else "stopped",
                           completed_at=now(), batch_id=batch_id,
                           batch_status=batch["status"], release=release,
                           training_counts={"sft": training["sft_records"], "preferences": training["preference_pairs"]})
            except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
                # No manual queue. Errors are retained; a new corrected input is a new immutable job.
                reason = str(exc)
                safe_reason = reason if reason.replace("_", "").isalnum() and len(reason) < 100 else type(exc).__name__
                job.update(status="quarantined", reason=safe_reason, ended_at=now())
            atomic_json(state_path, state)
        summary = {"jobs": len(state["jobs"]), "processed_this_tick": processed,
                   "statuses": {key: sum(j["status"] == key for j in state["jobs"].values())
                                for key in ("completed", "running", "quarantined", "stopped")},
                   "policy": config["pipeline"]["policy"], "data_root": str(root)}
        atomic_json(folder / "summary.json", summary)
        return summary


def worker(root, config, config_base=None, interval=60, ticks=1):
    if type(ticks) is not int or ticks < 0 or not 1 <= interval <= 3600:
        raise ValueError("invalid_worker_limits")
    count = 0
    while ticks == 0 or count < ticks:
        print(json.dumps(run_factory(root, config, config_base), ensure_ascii=False), flush=True)
        count += 1
        if ticks == 0 or count < ticks:
            time.sleep(interval)
