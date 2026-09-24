# Agent Trajectory Data

Private, proprietary software for automated agent trajectories and evaluation data. The production path uses deterministic acceptance, bounded retries, quarantine and budget stops. It has no interview, annotation or human review queue.

[产品结论与完整方案](docs/CONCLUSION.zh-CN.md) · [数据采集与评测包运行](docs/DELIVERY.zh-CN.md) · [模型调用说明](docs/RUN.zh-CN.md) · [Protocol](docs/PROTOCOL.md) · [Validation](docs/VALIDATION.md)

## Complete local workflow

Python 3.10+, standard library runtime.

```powershell
# Create, execute, grade and export an offline control batch.
py -3 -B -m agentdata --root data/control pipeline --config configs/control.json --batch-id control-001

# Produce a standalone proprietary evaluation ZIP, excluding holdouts.
py -3 -B -m agentdata --root data/control release artifacts/control-eval.zip --release-id control-001

# Model batch using an existing local Codex login and durable admission limits.
py -3 -B -m agentdata --root data/model pipeline --config configs/codex-local.json --batch-id model-001

# Safe repeated scheduler entry; a monthly call limit is mandatory for this model route.
py -3 -B -m agentdata --root data/scheduled cycle --config configs/codex-scheduled.json --period-hours 24

py -3 -B -m unittest discover -s tests
```

A complete batch can be invoked again to resume without repeating completed tasks. Use a new batch ID for changed inputs. Data and release artifacts are excluded from Git.

## Data sources and outputs

Synthetic tasks and selected structured facts share frozen environments, visible tool traces and deterministic grading. The structured-fact adapter records original artifact hashes and source groups; task requests claimed as observed require a workflow receipt. These are caller records, not independent authenticity certifications.

The pipeline retains the first failures, separates pass/fail/not-assessed outcomes, checks provenance consistency and purpose permissions, and keeps family splits stable. Captured Codex events include returned usage and requested model configuration; the CLI does not report an authoritative served model version or billing amount here.

A standalone evaluation package contains task snapshots, a resettable local command runner, grader, scripted control, manifest, data card and proprietary license. Downloaded answers are visible to recipients. Holdout bodies and internal exclusion filenames are omitted. The command runner is for trusted local agents, not a sandbox for untrusted programs.

The default real-model output policy allows internal diagnostics only; it does not allow SFT. The SFT exporter is a gated trajectory container, not a trainer-specific converter. Distribution policies do not themselves establish legal rights.

## Operational scope

The scheduler command supports idempotent time buckets; it does not install an always-on service. Optional monthly call admission is shared within one data root by participating batches; it is not an account-wide or monetary budget. Unknown costs stay unknown.

The working deliverable is a local data/evaluation pipeline and standalone internal sample. Payment, customer entitlements, hosted hidden evaluation, training gains and revenue have not been established. The linked Chinese conclusion explains the commercial product, licensing, pricing experiments and automatic expansion/stopping rules.
