# Agent Trajectory Data

[English](README.md) · [简体中文](README.zh-CN.md)

Existing and future user tasks, development tasks, reference tests and cases are real independent tasks; tests actually executed are real tests. Task identity follows the research question, so repeated runs of one task remain repeated runs. Source materials retain their stated provenance, including supplied or constructed data. Astra in a separate context can review independently; no outside person, different model vendor or additional external material is required. Changes to task assignment, reviewer inputs or acceptance criteria require targeted revalidation.

Public since 2026-10-13. See the [public evaluation inventory](docs/PUBLIC-EVALUATIONS.md) for repositories and release assets.

Public task data, observable agent trajectories, executable environments and reproducible evaluation.

**Optional research input: [AI industry research corpus](corpora/ai-industry/README.md).** Browse prepared texts, summaries and historical versions, associated with the existing source pack. Materials are counted separately from evaluation tasks and actual runs.

**Collector repair and format study completed (2026-09-29).** All 32 new episodes reach a terminal state; 31 pass and one retains a real deliverable-contract failure. A minimal JSON example reduces aggregate model turns from 334 to 312 and missing visible rationales from 141 to 9, but 56 format rejections remain. The collector now separates model rationale, missingness, explicit parser feedback and actual environment actions. All captures remain diagnostic-only. [Results and limitations](docs/FORMAT-STUDY.zh-CN.md) · [Public study data](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/format-study-2026-09-29).

**Four-model usefulness study completed (2026-09-29).** All 48 episodes pass, including the baseline condition. Full demonstrations reduce 42 aggregate steps, of which 41 are fewer outer-format rejections, while reported input tokens increase to 3.50x baseline. This does not demonstrate better business outcomes. The study preserves 901 environment steps and 906 service attempts, including five recovered unusable responses. All new episodes remain diagnostic-only. [Results and limitations](docs/USEFULNESS-STUDY.zh-CN.md) · [Public study data](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/study-2026-09-29).

**Latest: v0.16.** One original report-row parsing task adds an actual ten-call first attempt using the existing repair environment. The model succeeds in one edit; the targeted gap in actual post-edit failure/retry data remains unfilled. [Public release](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.16) · [Data card](docs/DATASET-v0.16.zh-CN.md) · [Candidate evidence](docs/CANDIDATE-v0.16.zh-CN.md) · [Next-stage plan](docs/PLAN.zh-CN.md).

- The explicit synthetic grammar covers quoted delimiters/newlines, doubled quotes, empty fields, EOF and invalid syntax. It makes no external CSV-standard claim.
- Final model code passes 27 fixed cases and 36 preregistered encoding round trips. One scripted reference passes and nine erroneous controls fail.
- The increment adds one eligible demonstration and ten training transitions. It does not add a model-observed post-edit behavioral failure.
- Independent acceptance exposed a no-op mutation in the external checker. Selecting a real development record fixes the check; the actual change is rejected. Frozen runtime, model data and archives stay unchanged.
- Eight independent main-package checks, seventeen rehashed mutations and three consumer commands pass. New data checks reuse the unchanged runtime's prior 273-test receipt; that full suite was not rerun. The later checker fix has a separate before/after receipt.

## Read the combined trajectories

Extract `agent-runtime-v0.16-consumer.zip`:

    python -B runtime_exports.py verify .
    python -B runtime_exports.py history . v0.16/repair-quoted-report-rows-clean-v1/0007
    python -B runtime_exports.py replay . --work ../runtime-v016-replay

The consumer embeds six unchanged source archives: v0.10, v0.11, v0.12, v0.14, v0.15 and v0.16. It exposes **22 actual episodes, 276 transitions, 91 eligible training transitions and seven positive demonstrations**, including 21 ready outcomes and one correct blocked outcome. Projection itself makes no model calls.

Read `transitions.jsonl` for public steps, `training/rl-transitions.jsonl` for eligible training steps, and original request references for full public history. Keep evaluator snapshots separate from policy input. Repair artifacts remain at `final_state.code`.

## Run the new standalone task

Extract `agent-runtime-v0.16.zip`:

    python -B runtime_release.py verify .
    python -B task-entrypoints/repair-quoted-report-rows-clean-v1/tests/verify.py model/episodes/repair-quoted-report-rows-clean-v1/episode.json
    python -B task-entrypoints/repair-quoted-report-rows-clean-v1/solution/reference.py ../reference-v16.json
    python -B repair_env.py batch/tasks/repair-quoted-report-rows-clean-v1/scenario.json --output ../episode-v16.json

The environment accepts one JSON action per line, such as `{"tool":"read","args":{"document_id":"policy"}}`. It exposes reset/step observations, reward and terminal flags; failed tests allow continued repair. Python's standard library is sufficient, within the documented pure-function subset.

## Preserve and extend the data

`configs/runtime-v0.16/` freezes material, source/use declarations, collection budget and consumer inputs. Original synthetic, inherited diagnostic, scripted and actual-model records remain distinct. Frozen outputs are immutable.

A retained three-event prefix from a real construction failure now supports the next reconstruction candidate. Its small selection functions run in the existing executor, retain diagnostic-only rights and are not counted as new model demonstrations. Model identity records the requested `gpt-6-astra` configuration without independent provider attestation; observed success does not establish generalization.

[Construction guide](docs/BUILDING-BATCHES.zh-CN.md) · [Current conclusions](docs/CONCLUSION.zh-CN.md) · [Acceptance](docs/ACCEPTANCE.zh-CN.md) · [Reference-method decisions](docs/REFERENCE-REVIEW-2026-09-28.zh-CN.md).

Earlier releases remain unchanged: [v0.15](docs/DATASET-v0.15.zh-CN.md), [v0.14](docs/DATASET-v0.14.zh-CN.md), [v0.13](docs/DATASET-v0.13.zh-CN.md), [v0.12](docs/DATASET-v0.12.zh-CN.md), [v0.11](docs/DATASET-v0.11.zh-CN.md), [v0.10](docs/DATASET-v0.10.zh-CN.md).

Raw data is delivered through public release assets. The September dataset runs used Toolkit commit [2852444](https://github.com/rrrrrredy/research-toolkit/commit/28524448eaf6534125a24dd1ea26e986016c8aea); the current Toolkit has since advanced. Commits and artifacts in this repository concern the dataset.
