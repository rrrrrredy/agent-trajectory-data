# Agent Trajectory Data

Private data for agent tasks, observable execution trajectories, runnable environments and evaluation.

**Current environment update: v0.5. Full historical corpus: v0.4.** The new standalone ZIP revises the ten business scenarios and their evidence grading. The unchanged v0.4 ZIP retains the complete research corpus and seven coding repair tasks. Both run locally using Python's standard library.

[数据说明](docs/DATASET-v0.5.zh-CN.md) · [RL 环境](docs/RL-ENVIRONMENT.zh-CN.md) · [当前结论](docs/CONCLUSION.zh-CN.md) · [构建范围](docs/PLAN.zh-CN.md) · [验收](docs/ACCEPTANCE.zh-CN.md)

## Run v0.5

From this repository:

    py -3 -X utf8 -B scripts/runtime_revision.py verify data/agent-runtime-v0.5

From the independently extracted v0.5 ZIP:

    py -3 -X utf8 -B verify_dataset.py verify .
    py -3 -X utf8 -B verify_dataset.py export-learner . --task business-customer-service-tool_retry-v2 --output ../learner-v5
    py -3 -X utf8 -B business_env_v2.py tasks/business-customer-service-tool_retry-v2/environment/scenario.json --output ../episode.json

The last command emits an initial observation and accepts one JSON action per line:

    {"tool":"search","args":{"query":""}}
    {"tool":"read","args":{"document_id":"policy"}}

Run and grade a reference attempt, using a new output path:

    py -3 -X utf8 -B business_env_v2.py tasks/business-customer-service-tool_retry-v2/environment/scenario.json --policy reference --output ../reference-v5.json
    py -3 -X utf8 -B tasks/business-customer-service-tool_retry-v2/tests/verify.py ../reference-v5.json

The archive contains evaluator data and reference solutions. Give an agent only learner exports and tool observations. Write episodes outside the immutable dataset directory.

## What changed

A successful evidence read now needs a current 200 receipt. A 429 is retained as a failed observation. Notes bind the receipts available when written; later reads cannot validate an earlier unsupported note. Malformed JSON and attempts to reset an active episode remain in the trace and consume the step budget. Reference CLI output uses the same verifiable episode format as interactive runs.

Two v0.4 false positives are preserved with their original reward of 1. Replaying the same actions in v0.5 produces 0; explicit recovery controls pass after successful reads and a new note. The v0.4 reference CLI contract failure is also retained.

| v0.5 content | Coverage |
|---|---|
| Revised business environments | Ten versions of existing development scenarios; zero new independent families |
| Scripted controls | 48 attempts: 22 passes and 26 non-passes, including one incomplete attempt |
| Current-assistant interactions | Two actual ten-step runs, covering 429 retries and concurrent-edit recovery |
| Processing evidence | 36 visible events with source-line bindings, diagnosis, edits and verification |
| Independent package acceptance | 139 content files; reference, grading and learner-export commands; eight rejected rehashed mutations |

The authoring assistant had already seen the scenarios, grader and reference code. Its two interactions are development integration checks, not independent model evaluation. Raw inputs, environment events and native tool-call bindings are retained; external model identity, tokens and costs remain unverified.

132 implementation tests passed. Independent acceptance separately checks the new bundle builder. Scripted or seen-run success does not measure model capability or research quality.

## Historical corpus and limits

The unchanged [v0.4 asset](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.4) contains 45 frozen review inputs, 221 review records, observations from four research runs, nine processing incidents, seven coding repair tasks and the original ten business scenarios. Its prior/ directory preserves earlier releases. v0.5 does not duplicate this historical archive.

All current research-derived material remains private diagnostic development data. There are no held-out results, new independent model evaluations or completed model training. The existing eight-call budget remains unchanged. Organizational context and faults are synthetic over archived research artifacts. The local repair executor runs trusted programs and is not an OS security sandbox.

Data stays outside Git and is delivered through [private release assets](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.5). Historical documentation: [v0.4](docs/DATASET-v0.4.zh-CN.md), [v0.3](docs/DATASET-v0.3.zh-CN.md), [v0.2](docs/DATASET-v0.2.zh-CN.md), [v0.1](docs/DATASET-v0.1.zh-CN.md).
