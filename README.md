# Agent Trajectory Data

Private task data, observable agent trajectories, executable environments and reproducible evaluation.

**Latest package: v0.8.** Six new synthetic source families produce 24 runnable scenarios across evidence updates, numeric consistency and review-driven revision. All six selected model first attempts completed: 52 actual calls, with 9, 7, 7, 9, 10 and 10 steps. Three train-family trajectories and 26 decisions are exported; three test families remain excluded.

[数据说明](docs/DATASET-v0.8.zh-CN.md) · [扩充批次](docs/BUILDING-BATCHES.zh-CN.md) · [RL 环境](docs/RL-ENVIRONMENT.zh-CN.md) · [当前结论](docs/CONCLUSION.zh-CN.md) · [验收](docs/ACCEPTANCE.zh-CN.md)

## What is delivered

- Frozen material, task context, public tools, deterministic state transitions, graders and per-task test/reference entrypoints.
- 24 scripted positive references, 120 negative controls and 12 explicitly scripted train trajectories.
- Six actual model trajectories with requests, visible replies, actions, read receipts, state checkpoints, token usage and terminal grading.
- Successful recovery from two tool rate limits and one concurrent-edit conflict, without deleting those failures.
- Structured result, scope and citation grading tied to the delivered note and actual final state.
- Durable call admission, crash-safe capture replay and quarantine of unknown in-flight calls.
- Source-family separation, explicit export exclusions, original ledger history and development-process evidence.

The new material is synthetic; the model executions are real. Earlier real reports, observed research runs and original failed attempts remain in the unchanged prior releases. Six successful development tasks do not establish broad research quality, cross-company generalization or a causal toolkit improvement.

## Run the standalone package

Download and extract the [private v0.8 release](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.8), then verify:

    py -3 -X utf8 -B runtime_release.py verify .

Grade an actual model trajectory:

    py -3 -X utf8 -B task-entrypoints/orchid-quota-counterfactual-v3/tests/verify.py model/episodes/orchid-quota-counterfactual-v3/episode.json

Run the reference solution:

    py -3 -X utf8 -B task-entrypoints/orchid-quota-counterfactual-v3/solution/reference.py ../reference-v8.json

Start a fresh environment:

    py -3 -X utf8 -B research_env_v3.py batch/tasks/orchid-quota-counterfactual-v3/scenario.json --output ../episode-v8.json

Send one JSON action per line, beginning with:

    {"tool":"read","args":{"document_id":"policy"}}

The policy receives reset/step observations. Evaluator state, reference solutions and grading checks must remain outside its context. The runtime needs only Python's standard library. The model collector is a separate optional component with explicit per-batch limits.

## Build another batch

    py -3 -X utf8 -B scripts/runtime_batch.py build configs/<batch>/batch.json data/<new-batch>
    py -3 -X utf8 -B scripts/runtime_batch.py verify data/<new-batch>

The example configuration is in configs/runtime-v0.8/. Source material, as-of time, mechanism, faults, split and step limits are explicit. Output directories are immutable; repeated or ineffective variants must not be counted as new independent sources.

Model identity is recorded as requested configuration (gpt-6-astra), not independently provider-attested. These are authored development tasks with shared mechanisms and disjoint source families. The new grader verifies structured facts and state, not arbitrary prose truth.

Raw data stays outside Git and is delivered through private release assets. The public [research-toolkit fix](https://github.com/rrrrrredy/research-toolkit/commit/28524448eaf6534125a24dd1ea26e986016c8aea) contains only generic parsing code and synthetic regression tests.
