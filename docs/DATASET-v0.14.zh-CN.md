# v0.14：模型自己构造反例，再验证修复

更新：2026-09-29。本版新增一个使用原创构造材料的训练任务，检验模型能否在现成公开测试全部通过时，自行构造有用的回归用例，暴露程序错误并验证修复。一次实际首次执行已完成：12 次模型调用、终局奖励 1，最终程序通过全部 12 个固定行为用例。264 项回归通过；主包独立解包完成 9 项执行与行为检查，21 类重算哈希后的篡改被拒绝。

任务模拟一个有界的事件收件箱函数：不同租户可以使用相同事件 ID，去重身份必须是 `(tenant_id, event_id)`。同一身份、相同内容的重放只保留首次事件；同一身份出现不同内容时应抛出 `ValueError`。输入最多 32 个事件，每个事件只有三个字符串字段，长度均不超过 80；标识非空，内容可以为空。顺序、大小写、Unicode 和分隔符都须原样保留。

初始程序只按事件 ID 去重，漏掉了租户范围；两个固定公开用例恰好都通过。模型必须从契约构造新输入及预期结果，不能仅运行已有测试后宣告完成。这项新增要求由独立版本 `research-repair-2` 承载，复用旧有界执行器；既有环境、归档数据和用途切分保持原样。

| 内容 | 已核实结果 |
|---|---|
| 新增任务 | 1 个家族、1 条任务：`repair-scoped-event-regression-clean-v2` |
| 来源与用途 | 全新原创合成来源；实际采集前登记为 `train`，许可允许训练 |
| 固定行为用例 | 2 个公开、10 个隐藏，预期值事先手写；合计仍是 1 个任务 |
| 脚本控制 | 1 条参考执行通过；14 个负向控制被拒绝，包括 6 个既有修复控制、6 个 probe 控制、2 个语义错误程序 |
| 实际模型执行 | 请求配置 `gpt-6-astra`，首次执行 1 条、12 次调用、奖励 1 |
| 本版训练导出 | 1 条实际正向示范、12 条 SFT 决策、12 条合格 RL transitions；脚本参考另列 |
| 统一消费数据 | 20 次实际执行、254 条公开 transitions；其中 69 条合格训练 transitions、5 条正向训练示范 |
| 累计来源索引 | 219 条记录、70 个已登记来源关系组，无 train/test 冲突或用途提升 |
| 累计失败与恢复 | 34 条失败记录、30 个不同事件、25 组恢复；其中 10 组具备训练用途 |
| 调用账本 | 本次增加 12 次，累计预留 431 次；原有 419 次保留 |

20 次实际执行来自 v0.10、v0.11、v0.12 与 v0.14 四个原始数据包，含 19 次 ready 和 1 次正确 blocked。来源索引中的历史记录不能再加进执行总数。14 个负向控制也不代表 14 个独立机制、任务或来源。

实际轨迹中的关键证据是：

1. 第 1—4 步读取策略、契约、程序并运行公开测试，两个公开用例均通过。
2. 第 5 步模型提交自己构造的 probe：租户 alpha 和 beta 各有一个 `evt-1`，内容均为 hello；预期保留两条，原程序实际只保留一条。这个输入与脚本参考所用的输入不完全相同。
3. 第 6—9 步修改程序、复读，再对完全相同的输入和预期复测。第 8 步返回两条正确事件，第 9 步固定公开测试通过。
4. 第 10—12 步提交绑定最终代码、固定测试和回归 probe 的说明，更新任务并终局提交。独立 oracle 确认预期正确、初态确有错误、同例修后通过；10 个隐藏用例也全部通过。

这里的 `probe.matches_claim` 只比较实际结果与模型自己填写的预期。模型填写错误预期也可能制造“不一致”，所以该字段本身不能证明发现了程序缺陷。终局评分另外用独立契约实现核对预期，要求初态证据发生在任何成功修改之前，修后记录使用相同输入与预期，并绑定最终代码版本及说明创建时已经存在的 probe。伪造预期、无信息用例、换用另一个用例复测、未复测、复测后再修改、引用未来 probe 都不能获得成功奖励。

独立 oracle 按已接受事件逐项比较两个标识，参考解法使用复合键字典；固定用例的期望值另行给定。probe 工具只执行模型提供的输入，不返回 oracle 答案，不运行隐藏用例。终局还检查固定公开/隐藏行为，因而仅让自编用例通过的部分修复也会被拒绝。

模型本次只构造了一种跨租户冲突输入，并在修复前后各执行一次。结果支持“能够自建反例并验证同例修复”，不支持“主动构造多组实验、区分所有可能成因”的更强结论。12 次工具调用状态均为 200；初态 probe 的行为不一致是任务内的错误复现，没有额外模型工具操作失败。

本任务是真实独立任务；代码与用例使用原创构造材料，没有导入真实企业程序、历史故障或第三方源码。新来源在实际采集前登记为训练家族；旧开发与测试材料没有提升用途。模型身份按实际调用记录中的请求配置报告。这是在既有训练任务上的真实首次执行；隐藏评分用例属于同一任务，不增加独立题数，本次未测量跨任务泛化成功率。

任务、操作轨迹、环境和评分脚本都随主包交付。最终程序位于 `model/episodes/repair-scoped-event-regression-clean-v2/episode.json` 的 `final_state.code`；修改文本、版本、公开反馈、终止状态与奖励保留在同一 episode，逐步请求和可见响应位于对应 `calls/`。统一消费包将这些公开步骤投影为 transitions，完整历史通过 `public_request_ref` 读取；评价快照、参考解法和 oracle 源码不能作为策略输入。

解压主包后，从其根目录使用 Python 3.10+ 运行，无需网络或第三方依赖：

```powershell
python -B runtime_release.py verify .
python -B task-entrypoints/repair-scoped-event-regression-clean-v2/tests/verify.py model/episodes/repair-scoped-event-regression-clean-v2/episode.json
python -B task-entrypoints/repair-scoped-event-regression-clean-v2/solution/reference.py ../scoped-event-reference-v14.json
python -B repair_probe_env.py batch/tasks/repair-scoped-event-regression-clean-v2/scenario.json --output ../scoped-event-episode-v14.json
```

最后一条命令先返回初始观察，之后每行接受一个 `{tool,args}` JSON 动作。参考执行及 episode 输出应使用新的文件路径，避免覆盖已有证据。

解压统一消费包后，可核验投影、查看模型发出初态 probe 前的完整公开上下文，以及逐包重放：

```powershell
python -B runtime_exports.py verify .
python -B runtime_exports.py history . v0.14/repair-scoped-event-regression-clean-v2/0005
python -B runtime_exports.py replay . --work ../runtime-v014-replay
```

消费包独立解包验收通过：包内 verify 和第 5、第 8 步 history 共 3 条命令均成功；两步公开历史与原始请求一致，同一 probe 的 matches_claim 由 false 变为 true。四个嵌入源包摘要与原包一致，导出器与已测试源码一致。回执为 artifacts/agent-runtime-v0.14-consumer-acceptance.json。此处没有重复旧环境重放；9 项执行检查与 21 类篡改检查另指主任务包。

构建过程也是交付数据的一部分。主包保存 76 个可见处理事件、34 对工具调用与结果，并绑定两项实际构造错误的发现、修改与核验：测试夹具名称遮蔽 `unittest.TestCase.run`，以及辅助验收命令引用了不存在的比较函数。这两项属于数据构建过程，不能记成这次模型轨迹的操作失败；过程记录维持开发诊断用途，不进入新增训练样本。仅保留可见工具记录与消息，不声称记录隐藏推理。

可核对的本地来源与回执如下：

- `configs/runtime-v0.14/scoped-event-regression.json`：原创契约、函数、固定用例与脚本控制。文件 SHA-256：`d3c16e936f9cf9734216b0798db369d5913dbfefd557d2f5aa4d346b6b6fd1cf`。
- `data/runtime-model-v0.14/input-freeze.json`：环境与采集源码冻结摘要。其中 `repair_probe_env.py` 的 SHA-256 为 `0a694d4b83ec99181e37f0ebacb0dda258e5398d217d93596c31075182e59cd9`。
- `artifacts/runtime-v0.14-model-behavior.json`：实际反例、初态/终态执行结果及全部 12 个固定用例的独立检查。最终程序 SHA-256：`06f64bcf8f890ecf62fc585200e64beb5d8bc8173d1775089359893538790661`。
- `artifacts/agent-runtime-v0.14-tests.json`：264 项回归通过，运行前后源码摘要一致；`artifacts/agent-runtime-v0.14-acceptance.json`：主包 9 项执行检查通过、21 类篡改被拒绝，验收没有模型调用。
- `artifacts/agent-runtime-v0.14.zip`：1,449,207 字节，SHA-256：`5190303045ecbc3ca5b7d55fdda61d4cb4c3f43a9f6360709f8bdc0ed4126070`。
- `artifacts/agent-runtime-v0.14-consumer.zip`：8,436,549 字节，SHA-256：`716607e222234dd55776d6276aca3f461b3480be2af7faa4c3ea9399cbd3bddd`。

本轮增量集中在公开数据集：让“自行提出检验”成为可执行、可评分、可重放的任务要求。toolkit 未因此修改。
