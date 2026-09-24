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
    commands.add_parser("stats")
    args = parser.parse_args(argv)
    if args.operation == "capture-facts":
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
        result = {"tasks": len(generate(args.root, args.families, args.seed)),
                  "origin": "synthetic", "actor": "not_executed"}
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
