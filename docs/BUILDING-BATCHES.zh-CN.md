# 扩充数据批次

当前管线只依赖 Python 标准库、JSON 配置和不可变输出目录。每批先冻结素材、切分、环境规则与预算，离线检验参考轨迹和错误对照，再收集实际模型动作。每次发布保留上一版的地址和摘要。

## 配置与输入

新机制参考 `configs/runtime-v0.9/batch.json`，原 v3 机制保留 `configs/runtime-v0.8/batch.json`。每个来源声明 family_id、train/test、mechanism、material 和 variants；批次声明 as_of、max_steps、评分范围、上游 toolkit 提交及上一发布版本。

v4 的素材文件保存文档、行标识、引用依赖、文档版本、可取得时间、任务上下文、原始主张和用途权利。按 documents 的实质内容检查完全重复；仅更改 handoff 中的公司名不能成为新家族。该检查不是语义去重，改写后的近重复仍需另行识别。同源素材及全部变体必须属于同一切分。

适配器只接纳明确标注的 authored_synthetic 材料。历史真实报告继续使用原导入器，不能改标签后混入新合成来源；生成题目也不能补造原报告没有记录的工具调用。

| 环境与机制 | 必要材料 | 可验证结果 |
|---|---|---|
| v3 evidence_update | 生效时间、修订号、指标与主张 | 适用记录及主张一致性 |
| v3 numeric_consistency | 期间、数量、单位与主张 | 同期间单位归一和合计 |
| v3 review_revision | 来源事实与评审意见 | 单项修订、拒绝错误建议、重新读取 |
| v4 evidence_chain | 入口文档、依赖图、单位、求和与减项 | 追到叶节点计算结果，引用完整依赖 |
| v4 evidence_conflict | 相互冲突的记录、权威等级、时间 | 依据公开规则选证；同级冲突保留不确定性 |
| v4 revision_workflow | 两处错误、可验证评审、受保护主张 | 分项修改、处理版本冲突、逐项复读及保留无关内容 |

v4 的 available_at 决定材料能否出现在 search/read 中；未来文档不出现在搜索结果，直接读取返回不带正文和版本的 404。它是固定 as_of 快照，不模拟时间自动流逝。带依赖的不可取得材料必须留有 404 回执，提交 blocked 并保持主张未被修改。

故障与反事实分别标记。tool_retry 在指定叶文档上产生两次 429，最多第三次成功；stale_revision 在第一次修改时引入并发版本冲突。每次实际修改后都必须重新读取 claims，才能继续修改或写最终说明。反事实必须改变正确结论；构建器拒绝没有 clean 基线或结果没有变化的反事实。

## 离线构建

在仓库根目录运行，输出目录必须尚不存在：

    py -3 -X utf8 -B scripts/runtime_batch.py build configs/<新批次>/batch.json data/<新批次>
    py -3 -X utf8 -B scripts/runtime_batch.py verify data/<新批次>

构建器冻结输入，为每题生成场景、只按公开观察执行的参考轨迹和错误对照。v0.9 的 24 题共 158 条错误对照，包含未来引用、以时间打破权威平局、只修一项及错误结果等。参考解法使用独立的公开材料计算路径，不调用评分器索要答案。保存后重新加载逐步回放；只检查内存对象或清单哈希不算通过。

scripted_reference 与真实模型轨迹分别存储和计数。交付脚本另外生成每题 environment.json、tests/verify.py 和 solution/reference.py。`scripts/accept_runtime_release.py` 解包后执行实际入口，再重算外围哈希测试语义篡改。

## 实际采集与续跑

collection.json 固定 task_ids、model、max_new_calls、monthly_model_calls、max_call_seconds、max_batch_seconds 及本批授权记录。旧批次的剩余额度不自动转给下一批。

模型请求只含公开任务、工具观察和真实剩余预算。v4 的公开任务编号不含故障名称或 train/test 标记；完整场景、隐藏未来材料、评分规则代码和参考解法留在评价侧。当前模型身份标为 requested configuration，不把请求参数冒充服务端身份回执。

    py -3 -X utf8 -u -B scripts/runtime_collect.py execute data/<任务批次> data/<模型批次> --config configs/<新批次>/collection.json --ledger data/production-current

调用前先在原全局账本预留；请求、可见回复、动作和检查点逐次落盘。相同命令续跑会核对冻结输入并复用完整捕获；已经启动却没有完整返回的调用标为 unknown_inflight_call_quarantined，不盲目重发。恢复不重置截止时间和步数。模型不会获得本地文件、隐藏状态或其他执行工具。

首次尝试、恢复、预算截断和提供方故障分别记录。当前正向训练导出只接纳成功的 train 家族，保留其工具失败和恢复；test 家族即使成功也排除。错误动作和外部截断保留原标签，不能混成同一种失败样本。处理过程用于 development_diagnostic，默认不进入策略训练。

## 持续扩充的判据

每批分别统计新增来源家族、任务机制、有效反事实、实际轨迹、终局结果、停止原因、训练导出和调用用量。改名、重复运行、增加 seed 或重复故障组合不会自动增加来源独立性。

下一批优先补当前没有的能力边界：依赖深度变化、文档布局变化、合法操作顺序差异、非暂时工具故障以及多项约束之间的取舍。先定义可验证末态和失败反例，再扩充数据量。当前 train/test 虽按来源分离，但机制共享且开发者已见素材；不能作为外部盲测或跨企业迁移的证明。

新增材料、环境变更、评分变更和模型变更分别版本化。只有发现可复现的通用 toolkit 缺陷，才向 toolkit 仓库提交修复；数据和企业场景实现留在私有数据集仓库。
