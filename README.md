# Agent Trajectory Data

Private data for agent tasks, execution trajectories, runnable environments and evaluation.

**Current version: dataset v0.4.** It combines retained research records, actual processing failures, executable repair tasks and an offline research-handoff RL environment. Everything runs locally with Python's standard library.

[数据说明](docs/DATASET-v0.4.zh-CN.md) · [RL 环境](docs/RL-ENVIRONMENT.zh-CN.md) · [当前结论](docs/CONCLUSION.zh-CN.md) · [构建范围](docs/PLAN.zh-CN.md) · [验收](docs/ACCEPTANCE.zh-CN.md)

## Run

From this repository:

    py -3 -X utf8 -B scripts/runtime_dataset.py verify data/agent-runtime-v0.4

From the independently extracted private release ZIP:

    py -3 -X utf8 -B verify_dataset.py verify .
    py -3 -X utf8 -B verify_dataset.py export-learner . --task jsonl-unicode --output YOUR_LEARNER_DIR
    py -3 -X utf8 -B tasks/jsonl-unicode/tests/verify.py YOUR_LEARNER_DIR

Start a business environment. It emits an initial observation and accepts one JSON action per line:

    py -3 -X utf8 -B business_env.py tasks/business-customer-service-tool_retry/environment/scenario.json --output episode.json

For example:

    {"tool":"search","args":{"query":""}}
    {"tool":"read","args":{"document_id":"policy"}}

The full archive contains evaluator data and reference solutions. Give an agent only learner exports and tool observations. The local repair executor runs trusted programs; isolated Python import mode is not an OS security sandbox.

## What is included

| Material | Coverage |
|---|---|
| Retained research corpus | 45 frozen review inputs, 221 review records and native observations for four existing runs |
| Actual processing incidents | Nine evidence-linked failures and repairs; 93 visible events and 44 tool-call batches |
| Executable repair tasks | Seven tasks with broken initial code, partial fixes, reference solutions and behavioral tests |
| Business RL scenarios | Ten scenarios over two archived research-source families |
| Executed controls | 70 attempts: 34 expected passes and 36 expected failures |
| Component coverage | 98 task, case-version or run entries with explicit gaps |

The business environment exposes reset/step, scoped document access, historical and future records, mutable tickets, retries, version conflicts, termination and deterministic outcome grading. Organizational context and fault events are synthetic over archived research artifacts.

Repair tasks cover Unicode JSONL, client footers, legacy hashes, frozen input formats, attempt retention, credential-pattern false positives and observation ordering after serialization. These are minimal reproductions, with the observed records kept separately.

## Evidence and limits

120 implementation tests passed. The acceptance receipt records independent extraction, real CLI runs, learner exports and rehashed negative controls. Every new task has an environment, verifier, reference and executed controls.

The unchanged v0.3 under prior/ retains v0.2 and v0.1. First failures, incomplete attempts, truncated returns and subsequent repairs remain distinct. Historical gaps are marked rather than reconstructed as fictional events. Frozen input binding and runtime completion do not certify research quality.

All current material is development data. Scripted controls are not model rollouts. There are no new paid model calls, completed model training, held-out results or claims of cross-company transfer. Archived material remains private diagnostic data; an RL-compatible interface does not change its permitted uses.

Raw data stays outside Git and is distributed as [private release assets](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.4). Earlier versions: [v0.3](docs/DATASET-v0.3.zh-CN.md), [v0.2](docs/DATASET-v0.2.zh-CN.md), [v0.1](docs/DATASET-v0.1.zh-CN.md).
