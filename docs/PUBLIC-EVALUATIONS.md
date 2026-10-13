# Public evaluation inventory

[English](PUBLIC-EVALUATIONS.md) · [简体中文](PUBLIC-EVALUATIONS.zh-CN.md)

As of 2026-10-13, research-toolkit and agent-trajectory-data are public. All 19 published releases and 79 assets in this data repository returned HTTP 200 without authentication. [Machine-readable receipt](public-access-receipt.json).

Toolkit's dedicated seven cases, conversation packs, semantic cases, studies and actual-run diagnostics are in [research-toolkit/evals](https://github.com/rrrrrredy/research-toolkit/tree/main/evals). The data repository supplies historical research records, executable tasks, model trajectories, replay code and study archives. The v0.4 archive embeds prior v0.3/v0.2/v0.1 contents; v0.2 is also independently downloadable. Public availability does not change task identity, outcomes or source-use permissions.


## What is inside the public archives

All existing and future user tasks, development tasks, tests and cases are real independent tasks; executed tests are real tests. Astra can review in a separate context, including with the same model as the author. Changed assignments, reviewer inputs and acceptance require targeted revalidation.

Paths below are relative to the root of `agent-runtime-v0.4.zip` unless noted. Count record types separately; versions and repeated runs overlap.

| Path / release | Actual content | Use |
|---|---|---|
| `prior/tasks.jsonl` | 45 report-review inputs: 23 development and 22 paired-study | Full research/report evaluation |
| `prior/reviews.jsonl`; `prior/author_attempts.jsonl` | 221 retained review records; 34 author-attempt records | First outputs, failures and review provenance |
| `prior/prior/runs.jsonl`; `prior/prior/turns.jsonl` | Four historical research runs, eight retained turns | Original multi-turn work and observed tool actions |
| `prior/prior/base/tasks.jsonl` | Ten earlier task rows | Original research/source-operation slices |
| `tasks.jsonl`; `coverage.jsonl` | 17 executable task rows; 98 overlapping coverage rows | Environment tasks and links to underlying research |
| v0.5–v0.9; v0.6-curriculum | Evidence receipts, measurement/constraint tasks, curriculum, model collection and recovery | Evidence handling and executable trajectories |
| v0.10–v0.12 | Code repair, workspace research delivery and denominator integrity | Real error diagnosis and repair |
| v0.13–v0.16 | Replay/export, counterexample-driven repair, event identity and report-row parsing | Current-code evidence and behavioral regression |
| study-2026-09-29; format-study-2026-09-29 | 48 and 32 actual episodes on four shared task identities | Demonstration-usefulness and output-format comparisons |

The dated data cards and [building guide](BUILDING-BATCHES.zh-CN.md) identify contracts and entry commands. Current generators produce current usage/access descriptions. Released ZIPs retain their original transcripts, embedded code and outcomes; historical access labels record the former state. Source permissions and training eligibility stay attached to their data. [Toolkit collection-to-method coverage](https://github.com/rrrrrredy/research-toolkit/blob/main/docs/correction-audit-2026-10-13.md).

| Release | Public assets |
|---|---:|
| [study-2026-09-29](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/study-2026-09-29) | 2 |
| [format-study-2026-09-29](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/format-study-2026-09-29) | 2 |
| [dataset-v0.16](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.16) | 8 |
| [dataset-v0.15](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.15) | 7 |
| [dataset-v0.14](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.14) | 7 |
| [dataset-v0.13](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.13) | 5 |
| [dataset-v0.12](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.12) | 5 |
| [dataset-v0.11](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.11) | 5 |
| [dataset-v0.9](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.9) | 5 |
| [dataset-v0.8](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.8) | 5 |
| [dataset-v0.7](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.7) | 5 |
| [dataset-v0.6-curriculum](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.6-curriculum) | 4 |
| [dataset-v0.6](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.6) | 4 |
| [dataset-v0.5](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.5) | 3 |
| [dataset-v0.10](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.10) | 5 |
| [v0.3.0](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/v0.3.0) | 1 |
| [dataset-v0.4](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.4) | 3 |
| [dataset-v0.2](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.2) | 2 |
| [dataset-v0.1](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.1) | 1 |
