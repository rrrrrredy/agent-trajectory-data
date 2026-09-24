# Agent Trajectory Data

A private repository for building an agent execution-trajectory and evaluation dataset from observed research workflows and explicitly labeled synthetic tasks.

**Current status:** the first research-slice dataset is built and independently verified. It aligns two existing research reports with four archived model reviews, including one truncated response, and adds six explicit fault variants with observed scripted controls. It covers review subtask inputs/outputs and registry-link checks; full research authoring trajectories remain outside this version.

[首版数据集](docs/DATASET-v0.1.zh-CN.md) · [构建计划](docs/PLAN.zh-CN.md) · [当前数据与缺口](docs/CONCLUSION.zh-CN.md) · [已有运行方式](docs/SYSTEM.zh-CN.md) · [验证记录](docs/ACCEPTANCE.zh-CN.md) · [Protocol](docs/PROTOCOL.md)

## Research-slice dataset v0.1

The private archive contains two report families, 42 source registrations, 54 claim records, ten tasks and twenty episodes: four archived model reviews plus sixteen scripted runs. Its 96 events retain the original truncation and four deliberate control failures. All tasks are development data; no hidden-test or training claim is made. No new model calls were used.

Build and verify using the standalone standard-library script:

```powershell
py -3 -B scripts/research_dataset.py build --source D:\Codex\research-toolkit --output data/research-slices-v0.1
py -3 -B scripts/research_dataset.py verify data/research-slices-v0.1
```

The ZIP also includes its own verifier. See [the dataset guide](docs/DATASET-v0.1.zh-CN.md) for counts, provenance, commands and limitations. The complete implementation suite passed 91 tests.

## Earlier control-pipeline data

| Asset | Observed count | Boundary |
|---|---:|---|
| Current synthetic tasks | 300; 30 parameter groups; 10 templates | Shared templates do not establish independent task coverage |
| Scripted control trajectories | 300 | These are not model trajectories |
| Current-profile model trajectories | 2; 8 adapter calls | Actual model execution on synthetic tasks |
| Earlier-profile model trajectories | 3; 7 adapter calls | A separate synthetic family |
| Selected real-session snapshot | 319 visible events | Partial; one unmatched call and no frozen external environment |
| Real training exports | 0 SFT records; 0 preference pairs | Current model-output policies allow diagnostics only |

The original capture of one failed integration probe is retained separately. Five successful model runs do not establish broad research quality or failure coverage.

## Minimal local workflow

Python 3.10+, standard library runtime; Windows/Python 3.11 has been exercised.

```powershell
# Inspect existing data without generating or calling a model.
py -3 -B -m agentdata --root data/production-current stats

# Export existing eligible observations for local diagnostics.
py -3 -B -m agentdata --root data/production-current export artifacts/diagnostic.json

# Verify the implementation.
py -3 -B -m unittest discover -s tests
```

The existing finite runner and import commands are documented in [the operating notes](docs/SYSTEM.zh-CN.md). Background workers, HTTP evaluation and client credits are outside the active construction plan.

## Dataset rules

Preserve source snapshots, visible actions, tool observations, outputs, failures and lineage. Keep real-session records, model runs on synthetic tasks, and scripted controls distinct. Do not reconstruct missing events or private reasoning.

Group source-related tasks, attempts and derived variants before splitting. Unverifiable or incomplete samples retain an explicit status; routine processing has no interview, annotation or human review queue.

Raw data, model captures and credentials stay outside Git. The repository and existing evaluation archive remain private. Passing implementation tests does not mark dataset construction complete.
