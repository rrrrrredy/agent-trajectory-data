from __future__ import annotations
import argparse
import json
from pathlib import Path
from .core import generate, read, run_task, import_workflow, export_runs, stats


def main(argv=None):
    parser = argparse.ArgumentParser(description="Private automated trajectory data pipeline")
    parser.add_argument("--root", type=Path, default=Path("data"))
    commands = parser.add_subparsers(dest="operation", required=True)
    gen = commands.add_parser("generate")
    gen.add_argument("--families", type=int, default=8)
    gen.add_argument("--seed", type=int, default=1)
    gen.add_argument("--profile", choices=["closed-facts-v1", "research-evidence-v1"],
                     default="closed-facts-v1")
    run = commands.add_parser("run")
    run.add_argument("--policy", choices=["reference", "broken", "loop", "command"],
                     default="reference")
    run.add_argument("--command-config", type=Path)
    run.add_argument("--max-steps", type=int, default=8)
    run.add_argument("--max-seconds", type=float, default=30)
    imported = commands.add_parser("import-workflow")
    imported.add_argument("source", type=Path)
    exported = commands.add_parser("export")
    exported.add_argument("destination", type=Path)
    exported.add_argument("--purpose", choices=["diagnostic", "sft"], default="diagnostic")
    exported.add_argument("--allow-scripted", action="store_true")
    pipeline = commands.add_parser("pipeline")
    pipeline.add_argument("--config", type=Path, required=True)
    pipeline.add_argument("--batch-id", required=True)
    intake = commands.add_parser("capture-facts")
    intake.add_argument("source", type=Path)
    intake.add_argument("--selectors", type=Path, required=True)
    intake.add_argument("--source-group", required=True)
    intake.add_argument("--rights", type=Path, required=True)
    intake.add_argument("--origin", choices=["artifact_derived", "observed_task"],
                        default="artifact_derived")
    intake.add_argument("--task-receipt", type=Path)
    release = commands.add_parser("release")
    release.add_argument("destination", type=Path)
    release.add_argument("--release-id", required=True)
    release.add_argument("--audience", choices=["internal", "licensed"], default="internal")
    cycle = commands.add_parser("cycle")
    cycle.add_argument("--config", type=Path, required=True)
    cycle.add_argument("--period-hours", type=int, default=24)
    training = commands.add_parser("training")
    training.add_argument("destination", type=Path)
    factory = commands.add_parser("factory")
    factory.add_argument("--config", type=Path, required=True)
    factory.add_argument("--ticks", type=int, default=1,
                         help="0 keeps watching until interrupted")
    factory.add_argument("--interval", type=int, default=60)
    native = commands.add_parser("import-session")
    native.add_argument("source", type=Path)
    withdrawal = commands.add_parser("withdraw")
    withdrawal.add_argument("--kind", choices=["source_group", "source_sha256"], required=True)
    withdrawal.add_argument("--value", required=True)
    withdrawal.add_argument("--reason", required=True)
    deliver = commands.add_parser("resolve-release")
    deliver.add_argument("--release-id", required=True)
    deliver.add_argument("--audience", choices=["internal", "licensed"], default="internal")
    api_client = commands.add_parser("evaluate-api")
    api_client.add_argument("--url", default="http://127.0.0.1:8765")
    api_client.add_argument("--key-file", type=Path, required=True)
    api_client.add_argument("--output", type=Path, required=True)
    api_client.add_argument("--limit", type=int, default=10)
    api_client.add_argument("--agent-config", type=Path)
    key = commands.add_parser("issue-key")
    key.add_argument("--file", type=Path, required=True)
    key.add_argument("--label", required=True)
    key.add_argument("--credits", type=int, default=20)
    for name in ("service-start", "service-status", "service-stop", "service-run"):
        service = commands.add_parser(name)
        service.add_argument("--kind", choices=["factory", "eval"], required=True)
        if name in {"service-start", "service-run"}:
            service.add_argument("--config", type=Path)
            service.add_argument("--interval", type=int, default=60)
            service.add_argument("--port", type=int, default=8765)
        if name == "service-run":
            service.add_argument("--generation")
    commands.add_parser("stats")
    args = parser.parse_args(argv)
    if args.operation == "evaluate-api":
        from .client import evaluate_api
        result = evaluate_api(args.url, args.key_file, args.output, args.limit, args.agent_config)
    elif args.operation == "issue-key":
        from .evalapi import EvaluationStore
        result = EvaluationStore(args.root).issue_key(args.file, args.label, args.credits)
    elif args.operation.startswith("service-"):
        from . import service
        action = args.operation.removeprefix("service-")
        if action == "run":
            service.run(args.root, args.kind, args.config, args.interval, args.port, args.generation)
            return 0
        if action == "start":
            result = service.start(args.root, args.kind, args.config, args.interval, args.port)
        elif action == "stop":
            result = service.stop(args.root, args.kind)
        else:
            result = service.status(args.root, args.kind)
    elif args.operation == "import-session":
        from .sessions import import_session
        result = import_session(args.root, args.source)
    elif args.operation == "withdraw":
        from .governance import withdraw
        result = withdraw(args.root, args.kind, args.value, args.reason)
    elif args.operation == "resolve-release":
        from .governance import resolve_release
        result = {"path": str(resolve_release(args.root, args.release_id, args.audience))}
    elif args.operation == "factory":
        from .factory import worker
        worker(args.root, read(args.config), args.config.resolve().parent,
               interval=args.interval, ticks=args.ticks)
        return 0
    elif args.operation == "training":
        from .training import export_training
        result = export_training(args.root, args.destination)
    elif args.operation == "capture-facts":
        from .taskpacks import capture_facts
        result = capture_facts(args.root, args.source, read(args.selectors), args.source_group,
                               read(args.rights), args.origin,
                               read(args.task_receipt) if args.task_receipt else None)
    elif args.operation == "release":
        from .release import build_release
        result = build_release(args.root, args.destination, args.release_id, args.audience)
    elif args.operation == "cycle":
        from .pipeline import run_cycle
        result = run_cycle(args.root, read(args.config), args.period_hours)
    elif args.operation == "pipeline":
        from .pipeline import run_pipeline
        result = run_pipeline(args.root, read(args.config), args.batch_id)
    elif args.operation == "generate":
        generator = generate
        if args.profile == "research-evidence-v1":
            from .research_tasks import generate_research
            generator = generate_research
        result = {"tasks": len(generator(args.root, args.families, args.seed)),
                  "profile": args.profile, "origin": "synthetic", "actor": "not_executed"}
    elif args.operation == "run":
        command = read(args.command_config).get("argv") if args.command_config else None
        paths = sorted((args.root / "tasks").glob("*.json"))
        if not paths:
            parser.error("No tasks. Generate or import a supported task pack first.")
        runs = [run_task(args.root, read(path), args.policy, args.max_steps,
                         args.max_seconds, command=command) for path in paths]
        result = {"executed_runs": len(runs), **stats(args.root)}
    elif args.operation == "import-workflow":
        result = import_workflow(args.root, args.source)
    elif args.operation == "export":
        result = export_runs(args.root, args.destination, args.purpose, args.allow_scripted)
    else:
        result = stats(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
