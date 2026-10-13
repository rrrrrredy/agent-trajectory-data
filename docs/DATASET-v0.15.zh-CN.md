# v0.15：复合键碰撞的同源修复轨迹

更新：2026-09-29。本批次从 v0.14 的覆盖核对中选出一个具体缺口：上一条模型反例无法识别分隔符拼接导致的复合键碰撞；将冒号改成竖线的局部修补还会通过原先全部 12 个固定用例。本版以旧错误控制作为新初态，加一个竖线碰撞用例，复用现有环境，采到另一条完整实际修复轨迹。交付见 [v0.15 公开发布](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.15)。

| 内容 | 核实结果 |
|---|---|
| 新增任务 | 1 条原训练家族内的派生任务；新增独立来源 0 |
| 固定行为用例 | 2 个公开、11 个评分侧隐藏用例；共 13 个用例，仍是 1 个任务 |
| 参考与对照 | 1 条参考通过，15 条错误控制被拒绝 |
| 实际模型执行 | 首次尝试，12 次调用后主动提交，reward=1；上限 48 次/48 步/20 分钟 |
| 新增训练数据 | 1 条成功模型示范、12 条 SFT 决策、12 条 RL transitions、1 组契约核实的恢复过程 |
| 统一消费数据 | 21 条实际执行、266 个步骤、81 条合格训练 transitions、6 条成功示范；20 条 ready、1 条正确 blocked |
| 累计来源目录 | 220 条记录，70 个来源关系组；已知分割冲突和用途提升均为 0 |
| 累计失败导出 | 35 条记录、31 个不同事件、26 组恢复对；其中 11 组具备训练用途 |
| 采集账本 | 431→443，保留原历史；没有以脚本补成模型成功 |

## 模型实际做了什么

第 1—4 步读取策略、契约和代码，运行两个固定公开测试，结果都通过。第 5 步，模型自行构造两个事件：tenant_id/event_id 分别为 (a:b,c) 和 (a,b:c)，payload 均为 same。契约要求保留两条，初始程序将二者拼成同一个字符串 a:b:c，只返回一条。

第 6 步把键改为元组，第 7 步复读代码，第 8 步用完全相同的输入和预期复测，正确返回两条。第 9—12 步再次运行公开测试，写下绑定代码、测试和 probe 的说明，更新任务并提交。独立执行确认初态反例、同例修复和全部 13 个固定行为用例通过。

工具调用状态全部为 200。probe 的 matches_claim 从 false 变为 true，表示当前程序输出与模型断言的关系；是否真是合法反例、是否完成正确修复，另由终局独立 oracle、代码版本和固定用例核实。仅修改分隔符的脚本错误控制通过局部复测，却无法通过新增竖线用例，因此不能得到成功评分。

模型实际只执行了一种冒号碰撞反例，并且首次修改即成功。它没有实际尝试竖线修补、没有因该修补失败而重试，也没有主动区分所有错误原因。两条相同家族的成功轨迹不能解释为两个独立来源或泛化能力提高。

## 来源与软件变动

任务 ID 为 repair-scoped-event-key-encoding-clean-v2；父任务是 v0.14 的 repair-scoped-event-regression-clean-v2。两者的 family_id 均为 repair-scoped-event-regression，source_group_id 均为 authored-scoped-event-regression-20260929，保持原 train 分割和完整用途声明。材料为同源合成派生，不代表真实企业记录或新评测来源。

构建器新增父任务绑定：核验固定父 ZIP 的摘要，复制并核验父任务索引和清单，要求新任务的父 ID、家族、来源组、分割、用途与父记录相同。修正同源派生任务被误计为新增来源的问题。运行环境、probe、执行器、评分器和模型采集器均未修改；旧发布包保持原始字节。

本次通过 Codex 请求 gpt-6-astra，身份按实际调用记录报告。本任务是真实独立任务，沿用已见过的训练契约；隐藏用例用于同一任务的评分，不增加独立题数。新增合格训练条数只表示来源与筛选条件符合，不代表任何训练效果。

## 使用与证据

解压 agent-runtime-v0.15.zip，在其根目录运行：

```powershell
python -B runtime_release.py verify .
python -B task-entrypoints/repair-scoped-event-key-encoding-clean-v2/tests/verify.py model/episodes/repair-scoped-event-key-encoding-clean-v2/episode.json
python -B task-entrypoints/repair-scoped-event-key-encoding-clean-v2/solution/reference.py ../reference-v15.json
python -B repair_probe_env.py batch/tasks/repair-scoped-event-key-encoding-clean-v2/scenario.json --output ../episode-v15.json
```

环境接受逐行 JSON 动作，提供 reset/step、观察、奖励与终止状态。最终代码位于实际 episode 的 final_state.code；逐步请求、动作、可见反馈、代码修改、检查点与评分保留。完整场景、参考 probe、旧模型轨迹、隐藏用例和 oracle 不进入模型公开请求。

解压 agent-runtime-v0.15-consumer.zip，在根目录运行：

```powershell
python -B runtime_exports.py verify .
python -B runtime_exports.py history . v0.15/repair-scoped-event-key-encoding-clean-v2/0005
python -B runtime_exports.py replay . --work ../runtime-v015-replay
```

消费包按原摘要嵌入 v0.10、v0.11、v0.12、v0.14、v0.15 五个源 ZIP；公开步骤位于 transitions.jsonl，训练范围位于 training/rl-transitions.jsonl，完整公开历史通过原请求引用取得。转换过程本身没有模型调用；新源包实际使用了 12 次调用。累计目录与失败记录不再重复计入执行总数。

273 项回归测试通过，103 个源码/配置文件的执行前后摘要一致。独立主包验收通过 9 项执行检查，拒绝 21 类重算外围哈希的语义篡改。消费包另有 3 条命令通过，核对投影和第 5/8 步原始公开历史；五个源包与原始字节一致，导出器与已测试源码一致。既有环境没有被重复改写或重采。

主包保留 46 个可见处理事件、20 对工具调用/结果，以及两项真实构造问题：测试夹具用不可变写入器做预期篡改，处理证据筛选又匹配到脚本正文中的相同词。相应失败、修改和复验均保留；失败的第一次部分捕获另外留存，后续验收进入过程补充包。这些属于构造过程，不能记成模型本次操作失败，且不进入策略训练。

完整覆盖矩阵位于 checks/runtime-v0.15-candidate-coverage.json，独立模型行为核对位于 checks/runtime-v0.15-model-behavior.json。原材料 SHA-256 为 10289b0e0de711bd117fca12a7589b542e2f9d6dc03ae050803d9a6e2ac42a7b。

主包 1,472,540 字节，SHA-256：9de49c2c2ce0074d7e5e97dc39103ccbc551f0d8a36919db2d4ce054655a191a。消费包 9,825,098 字节，SHA-256：bf05772185f0e625fe9febe809180c57d086bb26ce13a5f42a5c31cc74e0c19f。测试、主包验收、消费验收、源码提交绑定和过程补充作为独立公开附件交付。
