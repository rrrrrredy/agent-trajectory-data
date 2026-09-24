# Agent Trajectory Data

Private, proprietary repository for an automated agent trajectory data pipeline. The product direction is real observed executions plus executed synthetic tasks, with automatic quality gates and no human annotation or review queue.

The current implementation is a **local control prototype**: fictional research tasks, scripted agents, deterministic grading, failure retention, family splits, and gated JSON exports. It does not yet produce authenticated model trajectories or operate a commercial service.

[中文产品与构建方案](docs/PLAN.zh-CN.md) · [Protocol and boundaries](docs/PROTOCOL.md)

## Run

Python 3.10+; runtime uses only the standard library. Run from this repository:

```powershell
py -3 -B -m agentdata --root data generate --families 8 --seed 1
py -3 -B -m agentdata --root data run --policy reference
py -3 -B -m agentdata --root data run --policy broken
py -3 -B -m agentdata --root data run --policy loop --max-steps 2
py -3 -B -m agentdata --root data export artifacts/diagnostic.json
py -3 -B -m agentdata --root data export artifacts/sft.json --purpose sft
py -3 -B -m agentdata --root data stats
py -3 -B -m unittest discover -s tests -v
```

Use `python` instead of `py -3` where appropriate. Exports are immutable: use a new destination for a new release. Generation is idempotent; each execution creates a new attempt. No model credentials, network calls, or paid inference are required for these controls.

## What is implemented

- Three synthetic task variants: available evidence, missing evidence, and a transient tool failure.
- Observable action/observation traces, the initial visible task, terminal events, and immutable task snapshots.
- Separate pass, fail, and not-assessed outcomes; unsuccessful attempts are retained.
- Step, time, and tool-retry limits. An unknown remote cancellation is not automatically retried.
- Deterministic answer/evidence checks; abstention without trying the required source fails.
- Family-level train/development/holdout assignment and consistency checks.
- Export regrading, event-chain and hash checks, purpose-specific rights checks, and automatic quarantine.
- A trusted external-command protocol and a narrow importer for Research Toolkit review metadata.

The `diagnostic` export is an internal inspection package, including failed and ungraded executions when their records are consistent. It is **not** a public benchmark release. It may include solutions from holdout families. Keep this package private.

The default `sft` export rejects scripted controls and unverified external-command provenance. An empty training export is expected for the controls above. `--allow-scripted` enables explicit control-data export only; it does not turn scripts into model demonstrations.

## Remaining product work

A model-provider adapter with execution identity and usage capture; full authorized real-run capture; environment reset/replay packaging; broader semantic validators; automatic model judging with an explicit uncertain state; monetary admission control; unattended scheduling; packaged evaluation releases; customer delivery, payment, and licensing enforcement.

These are future components, not verified capabilities of this version. There are no customer interviews, manual labeling jobs, or human escalation queues in the design.

Data and artifacts are excluded from Git. The repository uses a proprietary license. Third-party source permissions and provider terms must be represented separately before admitting those sources to a commercial release.
