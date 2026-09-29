# Agent Trajectory Data

Private task data, observable agent trajectories, executable environments and reproducible evaluation.

**Latest consumer package: v0.13.** Read 19 existing actual episodes and 242 transitions from the unchanged v0.10-v0.12 packages through one format. It preserves all outcomes and the existing 57 eligible training transitions/four positive demonstrations; it creates no new tasks, sources or model calls. [Private consumer package](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.13) · [Consumer guide](docs/DATASET-v0.13.zh-CN.md) · [Next-stage plan](docs/PLAN.zh-CN.md).

From the extracted v0.13 consumer package:

    python -B runtime_exports.py verify .
    python -B runtime_exports.py history . v0.12/repair-denominator-integrity-clean-v1/0006
    python -B runtime_exports.py replay . --work ../runtime-v013-replay

Six focused regression tests, including eight semantic mutation cases, and independent package checks passed. All three original frozen verifiers replayed the nineteen episodes successfully. Public transition files and full prior public request references are ready to read; original evaluator archives remain separate from policy input.

**Latest new-task package: v0.12.** One original synthetic repair task checks complete task coverage, final usability and accounting for failed attempts. The first model attempt succeeds in 13 calls, preserving a baseline test failure, two edits, a real 412 read-before-write violation, its recovery and final verification. [Private package](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.12) · [Data card](docs/DATASET-v0.12.zh-CN.md).

- One executable task with two public and sixteen private behavioral cases; these are cases within one development task, not eighteen independent tasks.
- One passing scripted reference and eleven rejected erroneous controls, including always rejecting, substituting local labels for usability, discarding failed elapsed time, comparing only counts and silently deduplicating records.
- Actual requests, visible action summaries, tool responses, code edits, test receipts, checkpoints, terminal reward and final code retained. Final code independently passes all eighteen cases.
- 243 passing regression tests, eight independent extracted-package execution/behavior checks and seventeen rejected rehashed semantic mutations.
- Cumulative catalog: 218 records and 69 lineage groups. Cumulative failure exports: 33 records, 29 distinct events, 24 recovery pairs and nine eligible historical training recovery pairs.

This task is development-only and adds no training trajectories. The original synthetic material's declared rights do not override its split. Model identity is the requested `gpt-6-astra` configuration, without independent provider attestation. One observed success does not establish generalization.

## Run the standalone package

Extract the [private v0.12 package](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.12), then run from its root:

    py -3 -X utf8 -B runtime_release.py verify .
    py -3 -X utf8 -B task-entrypoints/repair-denominator-integrity-clean-v1/tests/verify.py model/episodes/repair-denominator-integrity-clean-v1/episode.json
    py -3 -X utf8 -B task-entrypoints/repair-denominator-integrity-clean-v1/solution/reference.py ../reference-v12.json
    py -3 -X utf8 -B repair_env.py batch/tasks/repair-denominator-integrity-clean-v1/scenario.json --output ../episode-v12.json

Send one JSON action per line, beginning with:

    {"tool":"read","args":{"document_id":"policy"}}

The environment exposes reset/step observations, reward, terminated and truncated. Only public observations reach the policy. Private behavioral cases, control implementations and reference code remain evaluator-side. Final code is retained at `final_state.code` in the recorded episode. Python's standard library is sufficient; execution is limited to the documented pure-function subset.

## Preserve and extend the data

Use `configs/runtime-v0.12/` for the original repair material, `runtime-v0.11/` for workspace reconciliation and `runtime-v0.10/` for archived incident repairs. Outputs are immutable. New material carries a contract, source/use declaration, fixed cases, reference and erroneous controls before model collection.

[Construction guide](docs/BUILDING-BATCHES.zh-CN.md) · [Current conclusions](docs/CONCLUSION.zh-CN.md) · [Acceptance](docs/ACCEPTANCE.zh-CN.md) · [Reference-method decisions](docs/REFERENCE-REVIEW-2026-09-28.zh-CN.md).

Previous releases remain unchanged. [v0.11](docs/DATASET-v0.11.zh-CN.md) retains twelve actual episodes, eleven ready results and one correct blocked outcome, with four eligible positive demonstrations and 57 training transitions. [v0.10](docs/DATASET-v0.10.zh-CN.md) preserves six actual repair attempts derived from retained incident evidence.

Raw data stays outside Git and is delivered through private release assets. Public research-toolkit remains unchanged at [2852444](https://github.com/rrrrrredy/research-toolkit/commit/28524448eaf6534125a24dd1ea26e986016c8aea). This repository contains the dataset implementation and artifacts.
