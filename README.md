# Agent Trajectory Data

Private task data, observable agent trajectories, executable environments and reproducible evaluation.

**Latest: v0.14.** One new original synthetic training task records a model constructing a regression input when the supplied public tests already pass, reproducing the bug, repairing the worker and verifying the same input again. The first attempt succeeds in 12 calls and contributes one eligible positive demonstration and 12 training transitions. [Private release](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.14) · [Data card](docs/DATASET-v0.14.zh-CN.md) · [Next-stage plan](docs/PLAN.zh-CN.md).

- The model exposes an event-inbox bug: two tenants using the same event ID must retain distinct events. Its initial probe loses one event; the final-code probe preserves both.
- Two public and ten private behavioral cases, one passing scripted reference and fourteen rejected erroneous controls accompany this single task. The final model code passes all twelve cases.
- Probe results compare execution with the model's assertion. Terminal grading separately verifies that assertion against an independent contract oracle and binds initial failure, final code, same-case retest and submission evidence.
- 264 regression tests, nine independent extracted-package execution checks and twenty-one rejected rehashed semantic mutations passed.

The new source was registered as original synthetic train material before collection. Existing development, test and archived-source restrictions remain intact. This is one observed task success; it does not establish blind generalization or coverage of every failure cause. Model identity is the requested `gpt-6-astra` configuration, without independent provider attestation.

## Read the combined trajectories

Extract `agent-runtime-v0.14-consumer.zip` from the private release:

    python -B runtime_exports.py verify .
    python -B runtime_exports.py history . v0.14/repair-scoped-event-regression-clean-v2/0005
    python -B runtime_exports.py replay . --work ../runtime-v014-replay

The consumer embeds the unchanged v0.10, v0.11, v0.12 and v0.14 source ZIPs. It exposes **20 actual episodes, 254 transitions, 69 eligible training transitions and five positive demonstrations**, including nineteen ready outcomes and one correct blocked outcome. The projection itself makes no model calls; the new v0.14 source used twelve calls.

Read `transitions.jsonl` for public steps, `training/rl-transitions.jsonl` for eligible training steps, and the original request references for complete public history. Evaluator snapshots stay separate from policy input. Final repair code remains at `final_state.code`; workspace deliverables retain their original artifact references.

## Run the new standalone environment

Extract `agent-runtime-v0.14.zip`, then run from its root:

    python -B runtime_release.py verify .
    python -B task-entrypoints/repair-scoped-event-regression-clean-v2/tests/verify.py model/episodes/repair-scoped-event-regression-clean-v2/episode.json
    python -B task-entrypoints/repair-scoped-event-regression-clean-v2/solution/reference.py ../reference-v14.json
    python -B repair_probe_env.py batch/tasks/repair-scoped-event-regression-clean-v2/scenario.json --output ../episode-v14.json

Send one JSON action per line, beginning with:

    {"tool":"read","args":{"document_id":"policy"}}

The environment exposes reset/step observations, reward, terminated and truncated. Python's standard library is sufficient; code execution uses the documented bounded pure-function subset. Hidden cases, reference probes and oracle implementations remain evaluator-side.

## Preserve and extend the data

`configs/runtime-v0.14/` contains the new material, batch, collection and consumer configuration. New material must carry its contract, source/use declaration, fixed cases, reference and erroneous controls before collection. Frozen outputs are immutable.

[Construction guide](docs/BUILDING-BATCHES.zh-CN.md) · [Current conclusions](docs/CONCLUSION.zh-CN.md) · [Acceptance](docs/ACCEPTANCE.zh-CN.md) · [Candidate evidence](docs/CANDIDATE-v0.14.zh-CN.md) · [Reference-method decisions](docs/REFERENCE-REVIEW-2026-09-28.zh-CN.md).

Previous releases remain unchanged. [v0.13](docs/DATASET-v0.13.zh-CN.md) introduced the combined consumer; [v0.12](docs/DATASET-v0.12.zh-CN.md) contains the complete-denominator repair; [v0.11](docs/DATASET-v0.11.zh-CN.md) contains twelve research-workspace episodes; [v0.10](docs/DATASET-v0.10.zh-CN.md) preserves six actual repairs derived from archived incidents.

Raw data stays outside Git and is delivered through private release assets. Public research-toolkit remains unchanged at [2852444](https://github.com/rrrrrredy/research-toolkit/commit/28524448eaf6534125a24dd1ea26e986016c8aea). This repository contains the dataset implementation and artifacts.
