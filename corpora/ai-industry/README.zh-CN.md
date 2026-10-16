# AI 行业研究材料集

[English](README.md) · [简体中文](README.zh-CN.md)

供研究者按题目选择的材料集：AI 公司、产品、模型、产业趋势和论文相关的历史报告、保存正文、摘要与来源线索。材料来自 `aiknowledge-cli` 和 `ai-knowledge-graph` 的固定版本。清洗后的文件可以直接阅读，也可以作为当前研究任务的附件；无需安装检索服务或导入 Toolkit。

**[在线分类目录：281 份材料](BROWSE.zh-CN.md) · [五份重点整理](recovered/README.zh-CN.md) · [下载完整历史版本包](https://github.com/rrrrrredy/agent-trajectory-data/releases/download/ai-industry-corpus-v1/ai-industry-v1.zip)**

## 使用

在线可直接阅读分类目录和单篇材料；需要原始记录与其他历史版本时，下载 [ai-industry-v1.zip](https://github.com/rrrrrredy/agent-trajectory-data/releases/download/ai-industry-corpus-v1/ai-industry-v1.zip)，解压后打开 `README.zh-CN.md`，按标题选择材料，再打开对应的 `documents/` 文件；五份重点恢复材料从 `recovered/README.zh-CN.md` 进入。每份阅读稿标明所选记录、正文性质及其他历史版本的位置。[Release 页面](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/ai-industry-corpus-v1)另附 SHA-256 校验值和盘点结果。

例如，研究历史 API 价格变化时，读取《大模型降价潮分析》的保存正文与表格，保留元／千 tokens、元／百万 tokens、输入／输出及时间差异。旧生成摘要放在单独章节，不能代替正文证据。要判断当下价格，需要另外读取当前官方资料。

| 文件 | 用途 |
| --- | --- |
| `README.zh-CN.md`、`documents/` | 可浏览的全量目录与单篇阅读稿。 |
| `catalog.jsonl`、`versions.jsonl` | 材料目录、各版本的规范字段和正文性质；实体字符串与对象统一为名称列表，原字段保留。 |
| `versions/`、`lineage.jsonl` | 每份不同的原记录，以及它出现在哪个仓库、提交、文件和 JSON 位置。 |
| `history-inputs.zip`、`inventory.json` | 两个固定提交中所有已跟踪文件的原始字节，以及逐文件数量、类型、哈希。包括已有检查点；没有拼接未知的版本历史。 |
| `snippets.jsonl`、`categories.json` | 原有片段和分类。仅按标题关联的片段不补成全文。 |
| `graph/` | 去重后保留出处的节点与关系，供浏览线索使用；关系不是已经核实的事实。 |
| `existing-source-map.jsonl`、`existing-source-pack/` | 与 Toolkit 已有来源包的对应关系及未改动的冻结输入。 |
| `recovery-notes.zh-CN.md` | 本次按价值选择的恢复结果、可使用内容与尚缺依据。 |

日期保留原字段及其出处。`created_date` 不自动当作发布日期；未知日期留空。`raw_text` 中明确由元数据生成的内容单列，不作原文。阅读稿只整理展示格式，不改写事实，也不补写缺失内容。材料沿用原有使用限制，清洗不增加再分发或训练授权。

## 与原有数据的关系

材料集回答“可以读什么”；来源包回答“这个任务实际提供了什么”；任务集包含问题与适用的判断依据；运行记录保存某个 Agent 真正执行过什么。四者用材料与版本引用关联，分别计数。

这次只增加材料和关联说明，不增加评测任务、模型运行、训练示范或质量分数。已有来源包、测试题、隔离结论和运行档案保持原样。新研究可以选用本次恢复的正文；如果未来据此修订任务输入，应另存新版本，不回写历史结果。

材料集是可选资源，不进入 Toolkit 核心安装，也不会自动加入每次研究上下文。它不提供跨项目检索。

## 重建本地交付

将 `aiknowledge-cli`、`ai-knowledge-graph` 和 `research-toolkit` 克隆到同一父目录，确保包含脚本固定的提交。在本仓库执行：

```bash
python scripts/build_ai_industry_corpus.py --inputs .. --output artifacts/ai-industry-v1
```

Python 标准库即可。脚本使用 `git show` 读取固定提交，复用现有数据集的哈希和不可覆盖写入逻辑，不调用模型或原站服务。输出目录已存在时停止；选择新目录才能生成另一版本。原始材料遵循仓库现有约定保存在 `artifacts/`，不写入 Git 源码树。本轮已将原有材料包原样发布为独立的 `ai-industry-corpus-v1` 预发布资产，保留历史版本及未核实标记，不替换现有运行数据集的 latest。

盘点结果见 [inventory-summary.json](inventory-summary.json)，深度恢复说明见 [recovery-notes.zh-CN.md](recovery-notes.zh-CN.md)。
