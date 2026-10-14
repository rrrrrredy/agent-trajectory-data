# 公开评测与数据目录

[English](PUBLIC-EVALUATIONS.md) · [简体中文](PUBLIC-EVALUATIONS.zh-CN.md)

截至2026年10月13日，research-toolkit 与 agent-trajectory-data 均已公开。本数据仓库19个已发布版本、79个发布资产均在未登录状态返回 HTTP 200。[逐项回执](public-access-receipt.json)。

Toolkit 的专门七题、长程对话要求、语义案例、研究批次和真实运行记录位于 [evals](https://github.com/rrrrrredy/research-toolkit/tree/main/evals)。本仓库提供历史研究与评审记录、可执行任务、模型轨迹、重放代码和实验归档。v0.4包内保留v0.3、v0.2、v0.1的历史内容，v0.2亦可单独下载。公开状态不改变任务身份、实际结果及来源材料的用途声明。

现有及以后的用户题、开发题、参考测试和案例均为真实独立任务；实际执行的测试都是真实测试。任务按研究问题区分，同题重复运行仍按重复运行记录。来源材料保留原有出处与性质，包括用户提供或构造的数据。Astra 在单独上下文中即可承担独立评审，无需外部人员、另一家模型或额外外部材料。分工、评审输入或验收标准变化时，应针对受影响部分复验。


## 公开归档里面有什么

[10 月 13 日 Toolkit 版本对比](https://github.com/rrrrrredy/research-toolkit/tree/main/evals/studies/2026-10-13-before-after)于 10 月 14 日完成修复：七道原题加三道新题，保留 20 篇完整报告、20 次首次盲评及另存的修订稿。首评均分 100 → 99.5，三题偏好随顺序变化，未观察到稳定的总体提升；合计 87 次模型调用，其中五次属于针对性修复与复验。新集合公开在 Toolkit，不改写下方历史发布数量，也不把复用任务重复计为新增独立问题。

现有及以后的用户题、开发题、参考测试与案例均为真实独立任务；实际执行的测试都是真实测试。Astra可以在单独上下文中评审，作者和评审可用相同模型。分工、评审输入和验收变化时，针对受影响部分复验。

下列路径默认相对于 `agent-runtime-v0.4.zip` 根目录。各行按记录类型分别计数，版本与重复运行有交叉。

| 路径／发布版本 | 实际内容 | 用途 |
|---|---|---|
| `prior/tasks.jsonl` | 45份报告评审输入：23份开发、22份配对研究 | 完整研究／报告评测 |
| `prior/reviews.jsonl`；`prior/author_attempts.jsonl` | 221条保留评审；34条作者尝试记录 | 首次输出、失败与评审来源 |
| `prior/prior/runs.jsonl`；`prior/prior/turns.jsonl` | 4次历史研究运行、8轮保留记录 | 原多轮研究及实际工具观察 |
| `prior/prior/base/tasks.jsonl` | 10条早期任务记录 | 原研究与来源操作切片 |
| `tasks.jsonl`；`coverage.jsonl` | 17条可执行任务、98条交叉覆盖记录 | 环境任务与原研究的对应关系 |
| v0.5–v0.9；v0.6-curriculum | 证据回执、测量／约束任务、课程、模型采集及恢复 | 证据处理与实际执行轨迹 |
| v0.10–v0.12 | 代码修复、工作区研究交付和分母完整性 | 真实错误诊断与修复 |
| v0.13–v0.16 | 回放／导出、反例驱动修复、事件身份和报告行解析 | 当前代码证据与行为回归 |
| study-2026-09-29；format-study-2026-09-29 | 同四个任务身份上的48条与32条实际轨迹 | 示范用途及输出格式比较 |

各版本数据卡及[批次构建说明](BUILDING-BATCHES.zh-CN.md)给出任务契约与执行入口。当前生成器输出当前用途／访问说明。已发布ZIP保留原始对话、内嵌代码与结果，历史访问标记记录当时状态；数据的来源权限与训练用途继续随数据保留。[Toolkit完整集合与方法映射](https://github.com/rrrrrredy/research-toolkit/blob/main/docs/correction-audit-2026-10-13.zh-CN.md)。

| 发布版本 | 公开资产数 |
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
