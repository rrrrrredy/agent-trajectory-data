# 研究任务片段数据集 v0.1

首批真实材料与合成数据已构建并跑通。数据来自 research-toolkit 的两份既有报告，覆盖历史报告评审和主张—来源登记检查；没有把它扩大描述为完整研究 Agent 轨迹。

## 可以直接使用的文件

- 本地数据目录：D:\Codex\agent-trajectory-data\data\research-slices-v0.1
- 本地 ZIP：D:\Codex\agent-trajectory-data\artifacts\research-slices-v0.1.zip
- 数据集版本：research-slices-v1；发布名：dataset-v0.1。
- ZIP 大小：255,663 字节。
- SHA256：32e06f349abf3dfbcb12ce7a760c5ec5e77823e56f161b813e714d3e1dcf0693。

解压后，在解压目录执行：

    py -3 -B verify_dataset.py verify .

Python 3.10+，标准库即可。验证不访问网络、不调用模型，也不依赖本地 research-toolkit 仓库。

## 本版实际数据

| 内容 | 数量与边界 |
|---|---|
| 既有研究报告 | 2 份：AI 客服选型、可灵/Runway/Veo 商业视频 |
| 来源与主张 | 42 条来源登记、54 条主张记录 |
| 原始评审任务 | 2 个，同一份报告对应两个模型请求 |
| 历史模型评审记录 | 4 条：3 条正常完成、1 条输出长度截断 |
| 产物衍生检查任务 | 2 条，使用各报告真实的主张表和来源表 |
| 合成故障任务 | 6 条：未知来源编号、来源表缺失、429 后恢复，各报告各 3 条 |
| 脚本执行 | 16 条：12 次通过、4 次失败 |
| 可见事件 | 96 条，分别标明模型请求响应与脚本动作观察 |
| 切分 | 全部 10 个任务在 development；train 0、holdout 0 |
| 本次新增模型调用 | 0 |
| 可训练记录 | 0 |

既有管线的 5 条模型轨迹、300 条脚本控制和 319 条部分会话事件另在 inventory.json 中盘点，没有重复计入本版的 4 条历史评审或 96 条事件。

## 真实材料怎样对齐

来源为本地 research-toolkit，版本 9b1e11fe50d55a7fdb54b0e7bb25266b49324dcb；使用 evals/diagnostics/2026-09-07 的冻结材料。

两份报告均保存了原始需求、修订说明、诊断前正文、来源表、主张表、模型输入，以及 DeepSeek、Kimi 的请求与响应。本版只导入同时具有请求和响应文件的这两个模型记录，没有根据其他评审摘要补造请求。

报告正文和修订说明都逐字出现在对应实际模型输入中。每条响应的 input_sha256 与冻结输入相符。所选 20 份源文件都通过上游冻结清单核对；上游采用换行归一化哈希，包内还保存原始字节哈希。

原始需求、来源表和主张表作为关联产物保留。它们没有全部直接发给历史评审模型，所以不会把关联文件冒充模型当时看到的完整上下文。

## 失败怎样保留

视频报告的 Kimi 评审响应记录 finish_reason=length，可见正文为空，parsed=null。保留原文件、usage 和请求绑定，派生标签为：

    runtime_status: output_limit
    failure_type: response_truncated
    outcome: not_assessed
    research_quality_verified: false

没有重写为空的正文，也没有把截断归因成模型对研究内容的判断。其他三条完成响应里的 usable_with_limits 保留为模型判断，不当作事实正确性标签。

合成任务的失败来自明确标记的脚本策略：reference 检查已读表格，unchecked 读取后始终提交 consistent。后者在未知编号和来源表缺失场景失败，共 4 次；在正常与 429 恢复场景通过。这些属于控制实验，不能算新的模型失败。

## 合成与切分规则

先从两份真实报告的表格建立产物衍生任务，再注入单一条件。派生任务记录父任务、来源家族、变体和配方；标签由表格与工具终态重新计算。未把历史截断失败解释成这些引用故障的起因。

同一报告、历史评审、原始检查题和所有变体留在同一来源家族。两组材料已经用于历史诊断，本版全部保持 development。这样可以做开发回归，但无法据此估计隐藏测试表现或跨场景泛化。

任务只验证编号与登记表的结构一致性。它不判断一个网页是否真的支持某条主张，也不判断报告洞察、文风或最新事实。

## 文件结构

| 文件 | 内容 |
|---|---|
| tasks.jsonl | 10 个任务及来源、家族、切分、变体、规则和参考结果 |
| episodes.jsonl | 4 条历史模型记录与 16 条脚本运行的结果、主体和终态 |
| events/ | 对应可见请求响应或实际脚本动作、工具返回 |
| assets/ | 冻结报告、任务说明、登记表、历史输入、请求与响应 |
| source_provenance.json | 原仓库版本、原文件位置、上游哈希关联 |
| inventory.json | 既有数据的独立盘点，不包含旧会话正文 |
| manifest.json | 版本、实际数量、文件哈希 |
| DATA_CARD.md | 用途、标签、采集范围和已知限制 |
| verify_dataset.py | 可独立运行的构建、验证与打包脚本 |
| LICENSE / UPSTREAM_LICENSE.txt | 私有内部诊断用途及原项目许可证 |

## 已完成验证

- 同一构建命令重复执行，数据文件和记录数不变。
- 91 项工程与数据测试通过；新增测试覆盖输入错绑、失败被删或改成成功、伪造工具观察、同源派生改为 holdout、正确答案但未读取证据，以及真实日志中的 Unicode 分隔字符。
- ZIP 已解压到独立目录，只用包内脚本验证，49 个内容文件通过检查，全部事件重放与重新评分一致。
- 数据保持私有；未增加服务、模型调用、人工生产步骤或训练用途。

构建方式（从仓库目录运行）：

    py -3 -B scripts/research_dataset.py build --source D:\Codex\research-toolkit --output data/research-slices-v0.1 --existing-root data/production-current --existing-root data/production-v0.2

验证方式：

    py -3 -B scripts/research_dataset.py verify data/research-slices-v0.1

已经完成的是首批数据版本。完整研究的检索、写作与多轮修订轨迹，更多独立来源家族，以及未见任务评测，仍需要后续数据；它们没有被本版结果代替。
