# Agent Trajectory Data

Private data for agent tasks, observable execution trajectories, runnable environments and evaluation.

**Latest package: v0.6. Full historical corpus: unchanged v0.4.** v0.6 adds a source-separated curriculum, actual isolated model attempts, synthetic supervision and execution evidence. All local runtime and verification commands use Python's standard library.

[数据说明](docs/DATASET-v0.6.zh-CN.md) · [RL 环境](docs/RL-ENVIRONMENT.zh-CN.md) · [当前结论](docs/CONCLUSION.zh-CN.md) · [构建范围](docs/PLAN.zh-CN.md) · [验收](docs/ACCEPTANCE.zh-CN.md)

## Actual contents and results

| Content | v0.6 |
|---|---|
| Source families | Two newly authored fictional train families; two archived research test families |
| Runnable tasks | Ten train and ten test scenarios, with environment, grader and reference solution |
| Scripted controls | 60 preserved attempts |
| Synthetic supervision | Ten scripted SFT demonstrations and ten scripted counterfactual preference pairs |
| Actual isolated model collection | Three first attempts, 36 decision calls and 36 distinct contexts |
| Completed model tasks | Zero; every attempt stopped at the collector's 12-decision cap |
| Successful model SFT demonstrations | Zero; all exclusions are retained |
| Processing evidence | 59 core events, the preceding 50-event record, and 18 final acceptance events in the delivery-evidence asset |
| Verification | 149 implementation tests; independent extraction of 391 content files; 12 rejected rehashed mutations |

The model requests exposed a 30-step environment budget, but did not disclose the collector's 12-decision cap. These attempts are externally truncated observations, not full-horizon task verdicts. The concurrent-edit attempt also stopped before reaching its intended conflict branch. See the preserved assessment in execution-evidence/runtime-assessment.json.

Each decision used a fresh CLI context with built-in tools and project instructions disabled. The host supplied only public rules, synthetic ticket state, registry identifiers and relationships, and the actual prior observations. Report prose and source URLs were excluded. Model identity is the requested configuration (gpt-6-astra), not an independently attested provider identity.

## Run the package

From this repository:

    py -3 -X utf8 -B scripts/model_rollout.py verify data/agent-runtime-v0.6

After independently extracting the [private v0.6 ZIP](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.6):

    py -3 -X utf8 -B verify_runtime.py verify .

Run a reference attempt and grade it, writing to a new path outside the immutable archive:

    py -3 -X utf8 -B curriculum/tasks/business-synthetic-capacity-tool_retry-v2/solution/reference.py --output ../reference-v6.json
    py -3 -X utf8 -B curriculum/tasks/business-synthetic-capacity-tool_retry-v2/tests/verify.py ../reference-v6.json

For interactive environment use:

    py -3 -X utf8 -B curriculum/business_env_v2.py curriculum/tasks/business-synthetic-capacity-tool_retry-v2/environment/scenario.json --output ../episode-v6.json

The process emits an initial observation, then accepts one JSON action per line:

    {"tool":"search","args":{"query":""}}
    {"tool":"read","args":{"document_id":"policy"}}

In write_note and submit, evidence_ids means document IDs such as policy, handoff, sources and claims. Read receipt IDs such as read-3 are retained by the host; they are not valid evidence_ids arguments in this environment.

The archive includes evaluator-only state and reference solutions. Give a policy only the public observations through the host, and keep its actual collection budget visible. The original v0.6 requests remain unchanged for reproducibility.

## Files and lineage

- curriculum/: frozen sources, source-family split, tasks, environments, graders, references and scripted controls.
- rollouts/: exact requests, visible model replies, usage, actions, observations and all first attempts.
- training/: successful-model export and explicit exclusion reasons. The successful-model export is empty for this batch.
- curriculum/training/: synthetic SFT and preference exports, separately labelled.
- execution-evidence/: approval, payload preview, original ledger prefix, final ledger, observed limitations and processing records.

The approved batch consumed exactly 36 new calls. The original monthly ledger retains its first eight reservations and now records 44. Verification and packaging make no model calls.

The train/test source-family overlap is zero; the workflow template is shared. Archived research material remains private diagnostic data and is excluded from training exports. No broad model-generalization or unknown pretraining-decontamination claim is made.

Historical material is retained in [v0.4](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.4): 45 frozen review inputs, 221 review records, observations from four research runs, processing incidents and seven coding repair tasks. [v0.5](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.5) preserves the previous receipt-grading corrections and two author-seen development interactions. These archives were not rewritten.

Data stays outside Git and is delivered through private release assets.
