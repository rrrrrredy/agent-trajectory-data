# Agent Trajectory Data

Private task data, observable agent trajectories, executable environments and reproducible evaluation.

**Latest: v0.15.** A measured coverage gap produces one additional repair task in the existing synthetic training family. The previous recorded probe misses delimiter-key collisions; replacing the delimiter also passes all twelve previous fixed cases. One new fixed case rejects that partial repair. [Private release](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.15) · [Data card](docs/DATASET-v0.15.zh-CN.md) · [Candidate evidence](docs/CANDIDATE-v0.15.zh-CN.md) · [Next-stage plan](docs/PLAN.zh-CN.md).

- The actual model constructs a collision input, observes a missing event, replaces the string key with a tuple, and verifies the identical input on final code. Its first attempt succeeds in twelve calls.
- One reference passes and fifteen erroneous controls fail; final code passes two public and eleven private cases. These are thirteen cases within one same-family task.
- The increment adds one eligible positive demonstration, twelve training transitions and one contract-verified recovery pair. It adds zero independent source groups.
- Parent archive/index hashes bind the original family, split and rights. The builder now distinguishes inherited sources from new ones. Runtime, tools, executor, grader and collector are unchanged.
- 273 regression tests pass, with nine independent main-package execution checks, twenty-one rejected rehashed mutations and three independent consumer commands.

The model repairs this example in one edit. It does not actually attempt the scripted partial repair or recover from that repair's failure. Recorded source eligibility and task success do not establish generalization. Model identity is the requested `gpt-6-astra` configuration without independent provider attestation.

## Read the combined trajectories

Extract `agent-runtime-v0.15-consumer.zip`:

    python -B runtime_exports.py verify .
    python -B runtime_exports.py history . v0.15/repair-scoped-event-key-encoding-clean-v2/0005
    python -B runtime_exports.py replay . --work ../runtime-v015-replay

The consumer embeds the unchanged v0.10, v0.11, v0.12, v0.14 and v0.15 source ZIPs. It exposes **21 actual episodes, 266 transitions, 81 eligible training transitions and six positive demonstrations**, including twenty ready outcomes and one correct blocked outcome. The projection itself makes no model calls; this new source used twelve calls.

Read `transitions.jsonl` for public steps, `training/rl-transitions.jsonl` for eligible training steps, and original request references for complete public history. Evaluator snapshots remain separate from policy inputs. Final repair code stays at `final_state.code`; workspace deliverables retain their original references.

## Run the new standalone environment

Extract `agent-runtime-v0.15.zip`, then run from its root:

    python -B runtime_release.py verify .
    python -B task-entrypoints/repair-scoped-event-key-encoding-clean-v2/tests/verify.py model/episodes/repair-scoped-event-key-encoding-clean-v2/episode.json
    python -B task-entrypoints/repair-scoped-event-key-encoding-clean-v2/solution/reference.py ../reference-v15.json
    python -B repair_probe_env.py batch/tasks/repair-scoped-event-key-encoding-clean-v2/scenario.json --output ../episode-v15.json

Send one JSON action per line, beginning with:

    {"tool":"read","args":{"document_id":"policy"}}

The environment exposes reset/step observations, reward, terminated and truncated. Python's standard library is sufficient; execution uses the documented bounded pure-function subset. Hidden cases, reference probes and oracle implementations remain evaluator-side.

## Preserve and extend the data

`configs/runtime-v0.15/` contains the material, parent binding, batch, collection and consumer configuration. Contracts, cases, reference, controls, source/use declarations and budgets are fixed before collection. Frozen outputs are immutable; inherited families are not relabeled as new sources.

[Construction guide](docs/BUILDING-BATCHES.zh-CN.md) · [Current conclusions](docs/CONCLUSION.zh-CN.md) · [Acceptance](docs/ACCEPTANCE.zh-CN.md) · [Reference-method decisions](docs/REFERENCE-REVIEW-2026-09-28.zh-CN.md).

Previous releases remain unchanged: [v0.14](docs/DATASET-v0.14.zh-CN.md) introduced model-authored probes; [v0.13](docs/DATASET-v0.13.zh-CN.md) introduced the consumer; [v0.12](docs/DATASET-v0.12.zh-CN.md) covers complete-denominator repair; [v0.11](docs/DATASET-v0.11.zh-CN.md) contains twelve research-workspace episodes; [v0.10](docs/DATASET-v0.10.zh-CN.md) preserves six actual repairs derived from archived incidents.

Raw data stays outside Git and is delivered through private release assets. Public research-toolkit remains unchanged at [2852444](https://github.com/rrrrrredy/research-toolkit/commit/28524448eaf6534125a24dd1ea26e986016c8aea). This repository contains the dataset implementation and artifacts.
