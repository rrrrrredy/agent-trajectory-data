# v0.13：统一读取既有研究交付与程序修复轨迹

更新：2026-09-29。本版将 v0.10、v0.11、v0.12 已有的实际执行整理成同一种消费格式。原始任务、环境、评分和轨迹不变；新增任务、来源、模型调用和训练示范均为 0。已通过下述针对性测试和独立解包验收，交付见 [v0.13 公开发布](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.13)。

## 为什么需要这一版

v0.11 已提供结构化的公开 RL transitions。v0.10 和 v0.12 同样保存完整轨迹，并且环境支持 reset/step，但使用者此前要自行解析修复 episode、对齐模型捕获和公开输入。统一导出解决读取上的差异，复用原包的环境与验证，不新增运行框架。

| 原包 | 实际执行 | 公开操作步骤 | 训练 transitions | 正向训练示范 |
|---|---:|---:|---:|---:|
| v0.10，归档故障派生修复 | 6 | 62 | 0 | 0 |
| v0.11，归档报告与原创合成研究交付 | 12 | 167 | 57 | 4 |
| v0.12，原创合成分母修复 | 1 | 13 | 0 | 0 |
| 合计 | 19 | 242 | 57 | 4 |

这些是三个包的实际模型执行索引之和。累计 catalog 和 failures 中重复保留的历史记录不再累加。18 条 ready 与 1 条正确 blocked 分开计数；blocked 表示合理保留结果，不能冒充已交付新报告。两个既有 test 任务继续属于原来的开发评测，不因为统一导出变成新的盲测。

## 使用方法

消费包包含脚本、统一投影和三个原始 ZIP。解包后使用 Python 3.10+，无需网络和第三方依赖：

```powershell
python -B runtime_exports.py verify .
python -B runtime_exports.py history . v0.12/repair-denominator-integrity-clean-v1/0006
python -B runtime_exports.py replay . --work ../runtime-v013-replay
```

`history` 读取该动作之前模型收到的完整公开请求，其中包含初始观察、此前历史和实际剩余预算。它不把最终代码、隐藏用例或评价快照补进早期上下文。`replay` 在新的输出目录中分别解包原发布包，用各包自己冻结的 runtime_release.py 执行验证与轨迹重放，避免不同版本的模块互相覆盖。

直接使用数据时，读取 `transitions.jsonl`；只需既有训练范围时，读取 `training/rl-transitions.jsonl`。每行保留 observation、action、next_observation、reward、terminated、truncated，以及来源、split、rights、公开请求引用与原 episode 摘要。observation 是当前一步可见的观察，完整历史通过请求引用读取；不能把这个部分可观察任务理解成只需要最后一条观察。

`episodes.jsonl` 保留任务和家族、原用途、完整性、最终状态、调用数、步骤数、训练资格以及产物引用。repair 产物引用指向原 episode 中的 final_state.code；workspace 产物引用指向原 deliverables，不会为兼容格式人造交付文件。

三个 ZIP 中仍有评价侧文件。它们用于重放和核验，不应整体加入模型输入；策略输入使用公开请求或公开 transitions。终局奖励是训练反馈，不代表隐藏用例可以作为动作前证据。

## 保留什么，不作何种推断

每一步的实际返回与恢复保留，包括 v0.12 第六步的 412、v0.10 的版本冲突、v0.11 的不确定写入。环境终止、环境步数截断与外部采集停止分别记录。失败的 train 轨迹可以在原用途许可下成为 RL 数据，但只有成功且来源合格的 train 执行才能成为正向示范。

原始 ZIP 的固定 SHA-256 记录在 config.json。投影验证重新读取来源并逐项对比，因此重新计算外围 manifest 不能掩盖动作、反馈、奖励、终止状态、用途或公开请求引用的变化。此处保证的是转换忠实，不是模型泛化、真实企业覆盖或新的任务独立性。

## 构建与验收记录

从仓库根目录构建新的、尚不存在的输出目录：

```powershell
python -B scripts/runtime_exports.py build configs/runtime-v0.13/exports.json data/runtime-consumer-v0.13 --source-root artifacts
```

6 项针对性测试通过，其中 8 类重算清单后的篡改被拒绝，覆盖动作、下一观察、奖励、terminated、truncated、用途、公开请求引用和最终代码引用。最终审查修正了一处测试证明不足：篡改样本原先同时改变 JSON 格式。修正后先验证规范格式的无语义重写能通过，再运行八类反例，排除格式差异造成的拒绝；前次回执保留为 pre-review。原 v0.11 的公开 transition 语义逐项保持一致；外部采集停止测试使用明确标注的假设性检查点，不增加实际执行数。

独立解包后通过三个命令级检查：消费投影核验、真实 412 之前的公开上下文读取、三个原包各自的冻结验证器执行。三个原包合计 19 次实际执行、242 步全部通过原环境重放，新增模型调用为 0。这里的 3 个命令级检查包含 3 次原包验证，不把它们相加冒充 6 项独立实验。

主包 7,066,060 字节，SHA-256：`805a0374fa36200ee98c8c87b869e7be32f1de3dc7b0759154b9b95bb09678f4`。测试回执为 `artifacts/agent-runtime-v0.13-tests.json`，独立验收为 `artifacts/agent-runtime-v0.13-acceptance.json`。可见构建过程另附公开过程包，保留主线程及两个任务子代理的规划、实现、测试和重放记录。

旧发布包未重新生成；本轮验收只验证新增读取与转换行为及其对既有环境的复放调用。完整来源 ZIP 的原始摘要继续由配置约束。
