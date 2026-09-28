# Agent Trajectory Data

Private data for agent tasks, observable execution trajectories, runnable environments and evaluation.

**Latest package: v0.7.** The three interrupted v0.6 attempts now have successful, actual model continuations. Original attempts and the unchanged environment and grader are preserved. All local verification uses Python's standard library.

[数据说明](docs/DATASET-v0.7.zh-CN.md) · [修复经过](docs/RECOVERY-v0.7.zh-CN.md) · [RL 环境](docs/RL-ENVIRONMENT.zh-CN.md) · [当前结论](docs/CONCLUSION.zh-CN.md) · [验收](docs/ACCEPTANCE.zh-CN.md)

## Actual results

| Content | Result |
|---|---|
| Curriculum | 20 runnable scenarios, two fictional train families and two archived test families |
| Scripted supervision | 60 controls, ten scripted demonstrations and ten counterfactual preference pairs |
| Original model attempts | Three interrupted 12-step attempts, preserved unchanged |
| Actual continuations | 11 new calls in distinct contexts; all three completed and passed the original grader |
| Total steps after recovery | 17, 17 and 13, including the original 12 steps in each |
| Model training export | One successful 17-decision trajectory, including its failed prefix; five new recovery decisions for SFT |
| Test-family export | Both archived families remain excluded from training |
| Ledger | Original 44 reservations retained; 55 total; approved ceiling 98 |
| Verification | 160 tests; independent extraction of 490 content files; 12 rejected rehashed mutations |

The original collector stopped after 12 decisions while the model saw only a 30-step environment budget. Every recovery request now exposes the actual remaining steps and batch limits. Public tool help explains literal search, document IDs versus read receipt IDs, and the terminal submit action. The grader was not relaxed.

These are repair-validation continuations of previously observed tasks, not new unseen first attempts. Success means a correct registry-integrity handoff, including a properly supported blocked result when access is denied. It does not establish factual correctness of the reports.

## Run the package

Verify the [private v0.7 archive](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.7) after extraction:

    py -3 -X utf8 -B verify_recovery.py verify .

Grade the completed capacity trajectory using the unchanged task grader:

    py -3 -X utf8 -B prior/curriculum/tasks/business-synthetic-capacity-tool_retry-v2/tests/verify.py recovery/episodes/business-synthetic-capacity-tool_retry-v2/episode.json

Start a fresh interactive environment, writing outside the archive:

    py -3 -X utf8 -B prior/curriculum/business_env_v2.py prior/curriculum/tasks/business-synthetic-capacity-tool_retry-v2/environment/scenario.json --output ../episode-v7.json

The process emits an initial observation and accepts one JSON action per line:

    {"tool":"search","args":{"query":""}}
    {"tool":"read","args":{"document_id":"policy"}}

Give a policy only public observations through the host. The full archive also contains evaluator-only state and reference solutions.

## Files and lineage

- prior/: exact v0.6 contents, including frozen sources, tasks, environments, graders, references, scripted controls and the three original model attempts.
- recovery/: actual requests, visible replies, actions, failures, grading, approval and ledger evidence.
- recovery/resumptions/: original crash evidence, the corrected collector and preserved-file bindings. Two captured calls were replayed locally without reissuing them; the original call and time limits were retained.
- training/model-trajectories.jsonl: one complete successful train-family trajectory with all 17 actual request/reply pairs.
- training/model-sft-recovery.jsonl: five newly observed recovery decisions from that trajectory.
- training/selection.json: explicit exclusions for both test families.

The release includes acceptance, test and processing-evidence assets. The processing supplement preserves diagnosis, approval rejection and resolution, the checkpoint failure, repair, retry and final verification.

Model identity records the requested configuration, gpt-6-astra; the provider did not independently attest the served version. Requests exclude report prose, claim prose, source titles and URLs. Source-family overlap between train and test is zero; the workflow template is shared. No broad generalization claim is made.

Historical corpus and seven coding repair tasks remain in [v0.4](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.4), with prior grading fixes in [v0.5](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.5). Data stays outside Git and is delivered through private release assets.
