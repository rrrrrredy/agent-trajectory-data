# Agent Trajectory Data

A private repository for building an agent execution-trajectory and evaluation dataset from observed research workflows and explicitly labeled synthetic tasks.

**Current delivery: dataset v0.2.** The local pipeline imports existing records, links tasks to visible events and report versions, verifies derived tables, and produces a portable archive. This version adds four observed research runs with 646 visible events, 98 artifact snapshots, eight report versions, and eight archived semantic-review calls containing 104 judgments.

[数据集 v0.2](docs/DATASET-v0.2.zh-CN.md) · [首版 v0.1](docs/DATASET-v0.1.zh-CN.md) · [构建计划](docs/PLAN.zh-CN.md) · [当前结论](docs/CONCLUSION.zh-CN.md) · [验证记录](docs/ACCEPTANCE.zh-CN.md)

## Use the dataset

Python 3.10+ and its standard library are sufficient.

    py -3 -B scripts/research_history.py verify data/research-history-v0.2
    py -3 -B scripts/research_history.py show data/research-history-v0.2 --run run-03

The private release archive includes its own verifier and an unchanged copy of v0.1 under base/. After extraction:

    py -3 -B verify_dataset.py verify .

See the [dataset guide](docs/DATASET-v0.2.zh-CN.md) for build commands, file relationships, counts, source revisions and limitations.

## What the records establish

The four research runs cover two authored development tasks under two historical conditions. Eight turns contain 291 paired actions: 111 commands, 47 file changes and 133 web operations. Six checkpoint manifests bind retained snapshots to turn boundaries; other final-workspace artifacts explicitly lack that boundary evidence.

The semantic material contains twenty synthetic case families and two retained revisions. Model judgments, author annotations and revisions remain distinct; none is automatically promoted to a gold label. One changed judgment across reordered batches is retained without assigning a causal explanation.

Web events contain action metadata without returned page bodies. Eight unrelated global-context outputs are omitted with their digests retained. Commands remain inert text. Runtime completion does not establish report quality, and later revisions do not inherit earlier review verdicts. All related data stays in development; training exports and held-out tasks are zero.

## Existing data retained

| Asset | Scope |
|---|---|
| v0.1 research slices | Two report families; four archived reviews, including one truncated response |
| v0.1 controlled checks | Two artifact-derived tasks, six fault variants and sixteen scripted runs |
| Earlier control pipeline | 300 template tasks, 300 scripted controls and five actual model trajectories on synthetic tasks |
| Earlier selected session | 319 visible events; partial tool pairing and no frozen external environment |

These quantities use different units and are not added together as independent real research tasks. v0.2 uses the same two report families as v0.1.

## Verification and scope

101 implementation tests passed. The archive also passed independent extraction and verification. Five deliberately rehashed alterations were rejected: removing a nonzero exit, promoting a seen turn to holdout, inventing a web response, replacing a model judgment and transferring approval to a revised report.

The active workflow uses local Python and JSON/JSONL files. Existing service code is outside this dataset construction workflow. There are no interviews, annotation queues, commerce features or new model calls in this release.

Raw data and model captures remain outside Git and are delivered only as private release assets. Preserve source snapshots, explicit unknowns, failures, lineage and allowed uses. Passing technical checks does not prove research quality or framework effectiveness.
