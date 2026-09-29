# Agent Trajectory Data

Private task data, observable agent trajectories, executable environments and reproducible evaluation.

**Latest verified package: v0.11.** Twelve actual model first attempts use 167 calls: eleven reconcile their deliverables and one correctly stops as blocked when required evidence is unavailable. Four train-eligible positive demonstrations, 57 SFT decisions and 57 training transitions are exported. Independent archive acceptance passed: 30 execution/behavior checks and 19 rejected rehashed mutations. [Private package](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.11). [Results and boundaries](docs/DATASET-v0.11.zh-CN.md) · [Reference review](docs/REFERENCE-REVIEW-2026-09-28.zh-CN.md).

**Previous package: v0.10.** Its nine real-incident-derived repair tasks, six successful model attempts in 62 calls and original development-only restrictions remain preserved. [v0.10 data card](docs/DATASET-v0.10.zh-CN.md) · [Private release](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.10).

[扩充批次](docs/BUILDING-BATCHES.zh-CN.md) · [RL 环境](docs/RL-ENVIRONMENT.zh-CN.md) · [当前结论](docs/CONCLUSION.zh-CN.md) · [验收说明](docs/ACCEPTANCE.zh-CN.md)

## Current collection

- Twelve tasks across six source families: two archived report sources and four newly authored synthetic sources.
- Twenty-four passing scripted references with alternate action orders and 93 rejected negative controls; references remain distinct from model executions.
- Twelve actual trajectories with public requests, visible replies, tool actions, failures, checkpoints, rewards and terminal states. There are 167 public transitions.
- Twenty-four saved artifact snapshots, two per episode. The blocked episode preserves its initial files; it does not count as a completed report.
- A cumulative catalog of 217 records and 68 connected lineage groups, adding four source groups while preserving splits and inherited-use restrictions.
- Cumulative failure exports: 31 records, 27 distinct events, 22 recovery pairs and nine eligible training recovery pairs. This increment adds six observed fault events and five recovery pairs, two eligible for training.
- A processing record of 277 visible events, 123 paired calls/results and two linked construction-failure diagnosis, patch and verification chains.
- 238 passing regression tests, 30 independent archive execution/behavior checks and 19 rejected rehashed semantic mutations.

The v0.11 environment reconciles bounded structured report content and evidence versions through a reset/step tool interface. It is not a reconstruction of an entire company platform or an unrestricted research environment. Archived report excerpts retain diagnostic-only development use. Only the two eligible synthetic train families supply the four new positive demonstrations. Sources, derived tasks, synthetic faults, scripted controls and actual model executions are separately labeled.

## Run the standalone workspace package

Extract the [private v0.11 package](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.11), then run from its root:

    py -3 -X utf8 -B runtime_release.py verify .
    py -3 -X utf8 -B task-entrypoints/delta-quality-source_refresh-w1/tests/verify.py model/episodes/delta-quality-source_refresh-w1/episode.json
    py -3 -X utf8 -B task-entrypoints/delta-quality-source_refresh-w1/solution/reference.py ../reference-v11.json
    py -3 -X utf8 -B workspace_env.py batch/tasks/delta-quality-source_refresh-w1/scenario.json --output ../episode-v11.json

The environment accepts one JSON action per line, beginning with:

    {"tool":"read","args":{"document_id":"policy"}}

Only public reset/step observations go to the policy; full scenarios, future changes, graders and reference solutions remain evaluator-side. The runtime uses Python's standard library. The collector records the requested model as `gpt-6-astra`, without independent provider attestation. A correct blocked outcome earns task reward but remains separate from a ready deliverable.

## Build a batch

    py -3 -X utf8 -B scripts/runtime_batch.py build configs/<batch>/batch.json data/<new-batch>
    py -3 -X utf8 -B scripts/runtime_batch.py verify data/<new-batch>

Use `configs/runtime-v0.11/` for the bounded workspace tasks, `runtime-v0.10/` for archived repairs, `runtime-v0.9/` for dependency/conflict/revision tasks and `runtime-v0.8/` for preserved v3 tasks. Output directories are immutable. New sources need explicit provenance, use restrictions, a verifiable task contract and independent behavioral controls. The catalog inherits prior versions; cumulative failure exports retain completed earlier model batches.

Raw data stays outside Git and is delivered as private release assets. The separate public research-toolkit and this private dataset keep distinct repository histories. Report provenance in this batch is bound to toolkit commit [2852444](https://github.com/rrrrrredy/research-toolkit/commit/28524448eaf6534125a24dd1ea26e986016c8aea). The reference review retracts the preset two-family/six-variant expansion: existing coverage is retained, and one denominator-checking task remains an unimplemented candidate.
