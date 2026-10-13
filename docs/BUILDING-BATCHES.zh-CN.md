# 扩充数据批次

现有及以后的用户题、开发题、参考测试和案例均为真实独立任务；实际执行的测试都是真实测试。任务按研究问题区分，同题重复运行仍按重复运行记录。来源材料保留原有出处与性质，包括用户提供或构造的数据。Astra 在单独上下文中即可承担独立评审，无需外部人员、另一家模型或额外外部材料。分工、评审输入或验收标准变化时，应针对受影响部分复验。

## v0.16：只增材料时验证数据，并保留验收器自身的故障

本版继续使用 research-repair-1。先冻结格式契约、27 个手写预期和用途，再验证参考、错误控制与独立编码方向的往返输入。运行代码未变时复用旧回归回执，另存本轮数据验证及源码摘要，不重复执行或重复计数旧测试。

```powershell
python -B scripts/runtime_batch.py build configs/runtime-v0.16/batch.json data/runtime-batch-v0.16
python -B scripts/runtime_collect.py execute data/runtime-batch-v0.16 data/runtime-model-v0.16 --config configs/runtime-v0.16/collection.json --ledger data/production-current
```

输出已冻结，不应覆盖重采。后续验收器暴露问题时，保留原包与失败工作目录；修复外部检查并在新目录验收，分别绑定修复前后脚本。篡改反例先要确实改变语义，否则不能用验证器未拒绝来断言数据验证失效。本次只修正目录记录的选取，不改变评分或模型结果。

## v0.15：派生材料继承父任务，不增加独立来源

同源材料在 batch.json 的 source 项登记 parent：固定 ZIP 文件名与 SHA-256、父 task_id、原 batch/tasks.jsonl 及 batch/manifest.json 的摘要。构建器验证原包，保存父索引/清单到 source/parents/；离线验证继续从冻结快照检查谱系。材料声明的 parent_task_id、family_id、source_group_id、split、rights 必须与父任务一致。

本版修正 authored_groups 统计：有父绑定的来源组属于继承，new_independent_source_groups=0。catalog 仍跨版本连接这些记录。源码改动只在 repair_batch.py；已有模型工具、环境、评分和采集不变。九项新增测试覆盖谱系、用途、父包/快照绑定、重哈希篡改、行为漏检与十五个错误控制。

```powershell
python -B scripts/runtime_batch.py build configs/runtime-v0.15/batch.json data/runtime-batch-v0.15
python -B scripts/runtime_collect.py execute data/runtime-batch-v0.15 data/runtime-model-v0.15 --config configs/runtime-v0.15/collection.json --ledger data/production-current
python -B scripts/runtime_exports.py build configs/runtime-v0.15/exports.json data/runtime-consumer-v0.15 --source-root artifacts
```

上述输出已冻结，命令用于说明实际流程，不应覆盖重采。覆盖分析先于采集，依据原契约手工固定新增用例；不能在看到模型输出后追加评分要求。本次按既定 48 次/20 分钟上限采集，实际 12 次。

## v0.14：先证明需要自编测试，再增加环境行为

`configs/runtime-v0.14/scoped-event-regression.json` 在采集前固定公开契约、错误初态、参考程序、错误控制、2 个公开与 10 个评分侧隐藏用例、评价侧 reference_probe，以及原创 train 来源。候选原型证明：六种实现都通过固定公开例，只有参考与独立 oracle 通过隐藏例；旧环境拒绝自编 test 参数，即使最终正确也因缺少公开基线失败得 0 分。证据见 [候选说明](CANDIDATE-v0.14.zh-CN.md)。

新批次使用 `environment_version: research-repair-2` 和采集 profile `bounded_program_probe_repair`。新增 probe 接受有效 input 与模型声明的 expected，返回实际执行、代码摘要、版本、step 和 matches_claim；不查询 oracle，不暴露隐藏答案。最终评分独立核实初态反例、末态同例复测及说明中的 probe 引用，固定评分侧隐藏用例同时检查修复的其他行为。旧环境和 executor 不变。

```powershell
python -B scripts/runtime_batch.py build configs/runtime-v0.14/batch.json data/runtime-batch-v0.14
python -B scripts/runtime_collect.py execute data/runtime-batch-v0.14 data/runtime-model-v0.14 --config configs/runtime-v0.14/collection.json --ledger data/production-current
python -B scripts/runtime_exports.py build configs/runtime-v0.14/exports.json data/runtime-consumer-v0.14 --source-root artifacts
```

这些是已执行批次的构建记录，输出目录已存在，不能覆盖或换目录重采后冒充首次执行。新批次必须使用新配置及明确预算；本次 48 步/48 次上限，实际使用 12 次，账本 419→431。消费导出本身不调用模型。

`probe_claim_mismatch` 只表明断言与当前程序结果不同，未必是模型错误。恢复对必须比较同一 input/expected、不同代码版本，并由终局 validated_regression_pairs 确认为真实回归修复，才标记 contract_regression_verified 和训练资格。构造脚本失败另存 processing，不混入模型动作错误。

批次的 prior_release 仍指向 v0.13；由于 v0.13 只含消费投影，来源目录的 catalog_prior_release 明确指向最后含目录的 v0.12，并验证两个上游包摘要。累计目录与失败导出保留历史，消费包仅合并实际 episode 索引，防止重复计数。

当前管线只依赖 Python 标准库、JSON 配置和不可变输出目录。每批先冻结素材、切分、环境规则与预算，离线检验参考轨迹和错误对照，再收集实际模型动作。每次发布保留上一版的地址和摘要。

## v0.10：历史故障适配、跨版本目录和恢复导出

新增配置为 configs/runtime-v0.10/。当前适配器从 dataset-v0.4 的三个归档修复任务读取原始契约、代码、用例、失败事件和修复参考；核对原 ZIP 与 manifest 摘要后，再生成可执行复现。每个派生任务保留 parent_task_id、source_group_id、split、rights 与 missingness。新的问题类别需要新的复现契约、适配逻辑和行为反例；增加 seed、重命名或复制变体不增加独立来源。

首次构建要求已公开的历史归档按既有目录恢复到 data/，含 research-slices-v0.1、research-history-v0.2、research-corpus-v0.3 及 agent-runtime-v0.4 至 v0.9；原始 archive 放在 artifacts/。首次来源目录使用这些原始索引，后续继承上一版 runtime-catalog-v<version> 并追加当前批次。失败导出读取 runtime-model-v0.6-first、runtime-model-v0.7-recovery 及已完成的旧 runtime-model-v<version> 和对应任务批次；不读取候选或缺少 manifest 的采集目录。独立发布包已经包含验证需要的历史索引与轨迹快照，解包验收无需连接旧仓库。

完成任务批次和真实模型采集后，按顺序构建附加产物。以下输出目录必须尚不存在：

    py -3 -X utf8 -B scripts/source_catalog.py build . data/<任务批次> data/<来源目录>
    py -3 -X utf8 -B scripts/failure_exports.py build . data/<任务批次> data/<模型批次> data/<失败导出>
    py -3 -X utf8 -B scripts/runtime_release.py build data/<任务批次> data/<模型批次> data/<处理记录> artifacts/<验证回执> data/<发布包> --catalog data/<来源目录> --failures data/<失败导出>
    py -3 -X utf8 -B scripts/runtime_release.py pack data/<发布包> artifacts/<发布包>.zip
    py -3 -X utf8 -B scripts/accept_runtime_release.py artifacts/<发布包>.zip D:/Codex/_tmp/<独立验收目录> artifacts/<验收报告>.json

catalog/ 保留原索引、原清单与投影结果，根据 family、parent_task、related_task 和精确内容摘要连接来源；阻止已知关系的 train/test 交叉和受限来源用途升级。它没有提供语义近重复识别。不同组件的保留版本要按 record_version_id 标识，不能丢弃同一 case_id 的修订。

failures/ 区分预期复现失败、修改后测试失败、动作错误、工具暂时失败、证据不可取得、版本冲突、外部预算截断和终局验证失败。恢复对只携带当时公开观察，单次工具接受、公开测试通过和最终目标通过分别标明。恢复前缀用事件指纹去重；正向训练恢复导出还要求来源允许、train 切分、完整终局成功及可用上下文。

本版六条新模型执行成功，但原始过程数据只允许诊断，所以新增完整模型训练导出为 0。七组可训练恢复样本来自以前已允许的来源。不要为增加训练量改写原始用途。主包按冻结前缀记录处理证据，后续验收事件放独立补充包，避免自引用。

## 使用构造材料的研究任务的配置与输入

新机制参考 `configs/runtime-v0.9/batch.json`，原 v3 机制保留 `configs/runtime-v0.8/batch.json`。每个来源声明 family_id、train/test、mechanism、material 和 variants；批次声明 as_of、max_steps、评分范围、上游 toolkit 提交及上一发布版本。

v4 的素材文件保存文档、行标识、引用依赖、文档版本、可取得时间、任务上下文、原始主张和用途权利。按 documents 的实质内容检查完全重复；仅更改 handoff 中的公司名不能成为新家族。该检查不是语义去重，改写后的近重复仍需另行识别。同源素材及全部变体必须属于同一切分。

v3/v4 合成研究适配器只接纳明确标注的 authored_synthetic 材料。历史真实报告继续使用原导入器，不能改标签后混入新合成来源；生成题目也不能补造原报告没有记录的工具调用。

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

新增材料、环境变更、评分变更和模型变更分别版本化。只有发现可复现的通用 toolkit 缺陷，才向 toolkit 仓库提交修复；数据和企业场景实现留在公开数据集仓库。


## v0.11 研究交付任务

在 configs/runtime-v0.11/batch.json 登记来源、用途、切分、机制和变体。归档报告用原任务行号、报告与登记表哈希、原文行和 claim_id 绑定；合成材料有单独的 material_sha256。新增材料先注册再构建，不自动扩大任务范围。

```powershell
py -3 -B scripts/runtime_batch.py build configs/runtime-v0.11/batch.json data/runtime-batch-v0.11
py -3 -B scripts/runtime_batch.py verify data/runtime-batch-v0.11
```

构建输出包含 intake 候选记录、同源分组、字面相似度筛查、十二个 scenario、两种操作顺序的参考执行和九十三条错误控制。构建命令拒绝覆盖已有输出；修复环境时保留失败候选，在新目录重建并说明版本变化。

参考执行只使用公开观察和 brief 中的计算规则。实际模型执行保存两个独立交付文件；模型采集开始后冻结 runtime 和配置。重新开始进程复用已完成的捕获，未知在途调用隔离，截止时间与账本不会重置。

workspace_exports.py 从原始模型执行重建 transitions、可训练 transitions 和固定评测选择；failure_exports.py 从实际错误事件派生恢复片段。缺失或失败不能用脚本参考补成模型成功。每批成功数量与可训练数量依据真实执行填写。

跨天等待授权而导致原窗口过期时，默认续跑在写入新 episode 前拒绝执行，不把未尝试任务伪造成超时失败。本次四条归档任务使用显式 continuation 授权：

```powershell
py -3 -B scripts/runtime_collect.py execute data/runtime-batch-v0.11 data/runtime-model-v0.11 --config configs/runtime-v0.11/collection.json --ledger data/production-current --continuation-approval configs/runtime-v0.11/archive-continuation.json
```

这一入口只接续完整前缀后尚未尝试的任务。原始 started.json、冻结环境、八条轨迹和原月账本保持不变；新增 continuation.json 记录已批准的片段、模型、任务范围、新窗口和上限，另存续跑 collector 代码。新增调用在原总额度以内，还受新窗口上限约束。重复执行复用同一窗口，不能刷新截止时间；改变已冻结环境仍会被拒绝。

## 原创合成修复材料

v0.12 在已有 repair_batch 中支持 `source_mode: authored_synthetic`，环境和执行器复用原实现。材料 JSON 固定 contract、错误初始程序、reference、partial、public_cases、private_cases 和有区分作用的 control_codes；预期结果独立给定，不能调用待验证的参考程序来生成。sources 只登记概念参考，没有导入第三方代码或原始评审记录。

材料的 origin、source_group_id、split、rights 与 missingness 必须明确。batch.json 的 sources 绑定文件路径与 SHA-256，当前仅使用 clean 变体；不为达到数量预设机械生成变体。按下面命令构建，输出存在时会拒绝覆盖：

```powershell
py -3 -B scripts/runtime_batch.py build configs/runtime-v0.12/batch.json data/runtime-batch-v0.12
py -3 -B scripts/runtime_batch.py verify data/runtime-batch-v0.12
```

开发集任务不会进入成功训练导出，材料训练用途许可与任务切分分别判断。题内评分侧隐藏用例只能证明该任务的行为约束，不构成独立任务测试集。参考、错误控制、实际模型执行和处理过程分别保存。

## v0.13：统一消费既有发布包

`configs/runtime-v0.13/exports.json` 固定三个来源 ZIP 的名称与 SHA-256。`runtime_exports.py` 直接读取每包的实际模型 episode 索引，按版本给 ID 加命名空间，避免把累计来源或失败索引中的重复历史再计入执行数量。

```powershell
python -B scripts/runtime_exports.py build configs/runtime-v0.13/exports.json data/runtime-consumer-v0.13 --source-root artifacts
python -B scripts/runtime_exports.py verify data/runtime-consumer-v0.13
python -B scripts/runtime_exports.py history data/runtime-consumer-v0.13 v0.12/repair-denominator-integrity-clean-v1/0006
python -B scripts/runtime_exports.py replay data/runtime-consumer-v0.13 --work D:/Codex/_tmp/runtime-v013-replay
```

构建与复放目录必须尚不存在。输出继承来源的 split 和 rights，保留每一步原观察、动作、反馈、实际奖励、环境终止标记与采集停止原因。公开 history 按原请求引用加载，不读取最终状态来补早期上下文。原 ZIP 原样嵌入，复放时各自在独立子进程中加载自己的代码；不改旧环境或评分，也不重新采集模型。

转换校验从冻结来源重新派生所有消费文件。`training/rl-transitions.jsonl` 只含原来允许且属于 train 的步骤；`evaluation.json` 只列既有 test 选择，不是新盲测。新增来源或机制仍走原批次构建和采集流程；这个入口只解决跨包读取，不能代替数据生成。
