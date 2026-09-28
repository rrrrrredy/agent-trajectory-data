# Agent Trajectory Data

Private task data, observable agent trajectories, executable environments and reproducible evaluation.

**Latest package: v0.10.** Three archived real incident chains provide nine derived repair tasks. Six selected model first attempts all succeed in 62 calls (10, 10, 10, 12, 10, 10 steps), preserving baseline failures, code edits, a version conflict, retries and terminal verification. These new trajectories retain inherited development-only use; seven eligible recovery pairs from earlier train sources are exported separately.

[数据说明](docs/DATASET-v0.10.zh-CN.md) · [扩充批次](docs/BUILDING-BATCHES.zh-CN.md) · [RL 环境](docs/RL-ENVIRONMENT.zh-CN.md) · [当前结论](docs/CONCLUSION.zh-CN.md) · [验收](docs/ACCEPTANCE.zh-CN.md)

## Delivered components

- Nine tasks with contracts, initial code, public and private behavioral tests, reset/step environments, graders and reference entrypoints.
- Nine passing scripted references and 54 rejected negative controls; references remain distinct from model trajectories.
- Six actual model trajectories with requests, visible replies, edits, test receipts, failures, checkpoints, rewards and terminal states.
- A cumulative provenance catalog: 205 retained records across 11 index components and 64 connected lineage groups, with split and inherited-use checks.
- Failure and recovery exports: 25 records, 21 distinct events, 17 recovery pairs and seven eligible deduplicated training pairs.
- 63 visible processing events with three linked diagnosis, patch and verification chains, plus a separate acceptance supplement.
- 225 passing regression tests, 20 independent archive execution/behavior checks and 16 rejected rehashed semantic mutations.

The new tasks reconstruct minimal reproductions of observed incidents. Layout and concurrency perturbations are synthetic; current model executions are real. All three incident families share one prior diagnostic source group, so this release adds zero independent source groups and zero complete train-eligible model trajectories. It does not reconstruct the historical machine or establish cross-company generalization.

## Run the standalone package

Extract the [private v0.10 release](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.10), then run:

    py -3 -X utf8 -B runtime_release.py verify .
    py -3 -X utf8 -B task-entrypoints/repair-manifest-hashes-stale_patch-v1/tests/verify.py model/episodes/repair-manifest-hashes-stale_patch-v1/episode.json
    py -3 -X utf8 -B task-entrypoints/repair-manifest-hashes-stale_patch-v1/solution/reference.py ../reference-v10.json
    py -3 -X utf8 -B repair_env.py batch/tasks/repair-manifest-hashes-stale_patch-v1/scenario.json --output ../episode-v10.json

The environment accepts one JSON action per line, beginning with:

    {"tool":"read","args":{"document_id":"policy"}}

For layout variants, use document_roles from the initial observation. Only public reset/step observations go to the policy; full scenarios, graders and reference solutions remain evaluator-side. The runtime uses Python's standard library and a restricted pure-function subset. The collector records model identity from requested configuration, without independent provider attestation.

## Build a batch

    py -3 -X utf8 -B scripts/runtime_batch.py build configs/<batch>/batch.json data/<new-batch>
    py -3 -X utf8 -B scripts/runtime_batch.py verify data/<new-batch>

Use configs/runtime-v0.10/ for the supported archived repairs, runtime-v0.9/ for dependency/conflict/revision tasks and runtime-v0.8/ for preserved v3 tasks. Output directories are immutable. Adding a new repair class requires its reproduction contract, adapter and independent behavioral controls. Catalogs inherit the prior version; failure exports discover completed earlier model batches. See the construction guide for prerequisite archives and full commands.

Raw data stays outside Git and is delivered as private release assets. The separate public research-toolkit remains at [2852444](https://github.com/rrrrrredy/research-toolkit/commit/28524448eaf6534125a24dd1ea26e986016c8aea); this release makes no toolkit changes.
