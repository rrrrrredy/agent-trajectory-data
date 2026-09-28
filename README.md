# Agent Trajectory Data

Private task data, observable agent trajectories, executable environments and reproducible evaluation.

**Latest package: v0.9.** Six new synthetic source families provide 24 tasks across dependency tracing, unresolved evidence conflicts and verified multi-claim revision. Selected model first attempts: 6/6 successful in 70 calls (13, 11, 8, 8, 16, 14 steps). 3 train-family trajectories and 37 decisions are exported; test families remain excluded.

[数据说明](docs/DATASET-v0.9.zh-CN.md) · [扩充批次](docs/BUILDING-BATCHES.zh-CN.md) · [RL 环境](docs/RL-ENVIRONMENT.zh-CN.md) · [当前结论](docs/CONCLUSION.zh-CN.md) · [验收](docs/ACCEPTANCE.zh-CN.md)

## Delivered components

- Task context, documents, availability snapshots, executable state transitions, graders and per-task reference/test entrypoints.
- 24 scripted references, 158 rejected negative controls and 12 separately labeled scripted train trajectories.
- Six actual model trajectories with requests, visible replies, actions, failures, receipts, checkpoints, per-step rewards and terminal grades.
- Future-document visibility enforcement, opaque policy task identifiers, legitimate unresolved outcomes and repair validation against actual state.
- Original rate limits and revision conflicts, current-version rereads and rejection of unsupported review advice.
- Frozen collection budgets, capture replay after interruption, source-family separation and explicit export exclusions.
- 195 passing tests, 20 independent archive execution/behavior checks and 14 rejected rehashed semantic mutations.

The material added in this release is synthetic; model executions are real. Earlier real research reports, recorded runs and failed attempts remain in unchanged prior releases. Authored development tasks with shared mechanisms do not establish broad research quality or cross-company generalization.

## Run the standalone package

Extract the [private v0.9 release](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.9), then run:

    py -3 -X utf8 -B runtime_release.py verify .
    py -3 -X utf8 -B task-entrypoints/aster-routing-stale_revision-v4/tests/verify.py model/episodes/aster-routing-stale_revision-v4/episode.json
    py -3 -X utf8 -B task-entrypoints/aster-routing-stale_revision-v4/solution/reference.py ../reference-v9.json
    py -3 -X utf8 -B research_env_v4.py batch/tasks/aster-routing-stale_revision-v4/scenario.json --output ../episode-v9.json

The environment accepts one JSON action per line, beginning with:

    {"tool":"read","args":{"document_id":"policy"}}

Only reset/step observations go to the policy. Full scenarios, graders and reference solutions remain evaluator-side. The environment requires Python's standard library. The optional model collector records model identity from the requested configuration, not independent provider attestation.

## Build a batch

    py -3 -X utf8 -B scripts/runtime_batch.py build configs/<batch>/batch.json data/<new-batch>
    py -3 -X utf8 -B scripts/runtime_batch.py verify data/<new-batch>

Use configs/runtime-v0.9/ for the new mechanisms and configs/runtime-v0.8/ for the preserved v3 tasks. Output directories are immutable. Source families, variants and actual trajectories are counted separately; changed names and repeated runs do not establish independent sources.

Raw data stays outside Git and is delivered as private release assets. The separate public research-toolkit remains at [2852444](https://github.com/rrrrrredy/research-toolkit/commit/28524448eaf6534125a24dd1ea26e986016c8aea); this release makes no toolkit changes.
