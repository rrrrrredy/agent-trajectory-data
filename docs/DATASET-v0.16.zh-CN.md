# v0.16：报告行解析、真实恢复缺口审计与验收修复

更新：2026-09-29。本批次采到一条新的报告行解析修复轨迹：模型在 10 次调用内完成一次修改，终局成功。它扩展了任务内容，但没有出现修改后行为仍错，因此“语义修改失败后重试”的实际策略样本缺口仍然存在。数据与回执见 [v0.16 公开发布](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.16)。

## 实际数据与过程

| 项目 | 结果 |
|---|---|
| 新任务/来源 | 1 个使用原创构造材料的真实 train 任务、1 个新来源组 |
| 任务行为 | 8 个公开、19 个评分侧隐藏固定用例；1 个任务共 27 个用例 |
| 参考验证 | 27 个手写预期用例、36 组独立编码方向的往返检查、9 条错误控制 |
| 实际模型 | 请求配置 gpt-6-astra；首次执行 10 次调用，1 次接受的修改，reward=1 |
| 新增训练导出 | 1 条成功示范、10 条 SFT 决策、10 条 RL transitions |
| 统一消费包 | 22 条实际执行、276 个步骤；91 条合格训练 transitions、7 条成功示范 |
| 结果口径 | 21 条 ready、1 条正确 blocked；两个既有 test 任务继续保留原范围 |
| 来源目录 | 221 条记录、71 个来源关系组，已知切分冲突和用途提升均为 0 |
| 失败导出 | 36 条记录、32 个不同事件、27 组恢复对，其中 12 组具备训练用途 |
| 调用预算 | 上限 48 次、48 步、1200 秒；实际 10 次，原账本 443→453 |

格式契约明确规定分号分字段、LF/CRLF 分记录、引号内数据保留、双引号转义、空字段、EOF 与非法语法。它是自定义的合成报告导出格式，不声称符合外部 CSV 标准。初始程序只做 splitlines 和分号切分。

模型第 1—3 步读取策略、契约和代码；第 4 步测试，8 个公开例中 6 个失败。第 5 步修改，第 6 步复读，第 7 步测试全部通过；第 8—10 步写说明、更新任务和提交。独立执行确认最终代码通过 27 个固定用例与同一组预先生成的 36 个往返输入。

全部工具状态为 200。没有修改被拒绝，也没有修改后的行为测试失败；不能将初态复现、脚本错误控制或构造故障替换成模型的语义失败重试。采集前对保留实际轨迹的审计发现 7 次初态固定测试失败、2 次初态 probe 不一致、2 次被拒绝的修改，修改后行为失败为 0。本次之后这项计数仍为 0。

## 独立验收发现并修复的真实问题

首次独立验收失败，原因是外部检查脚本对普通 repair 任务选取目录末条记录，试图将它改成 train；本版末条记录原本就是 train，修改没有改变语义。该脚本之前只为 probe 分支选择实际 development 记录，本轮将同样的正确选择用于全部 repair 分支。改动只有这一处目标选择，任务环境、执行器、评分和采集器未改动。

修复回执实际比较了原目录与两次变更：旧变更在 JSON 语义上与原目录完全相同；新变更确实将一条 development / training_eligible=false 记录改成 train / true，并被 catalog_projection_changed 拒绝。修复后的主包独立验收通过 8 项执行检查，拒绝 17 类重哈希篡改。

第一次消费包核验因主验收回执尚未生成而中断，保留该工作目录后重新核验；3 条命令通过，确认统一投影、初态第 4 步与修后第 7 步的原始公开请求，以及六个源 ZIP 的固定摘要。两个失败都属于构建/验收过程，模型轨迹及其得分没有被改写。

本轮没有重跑全部 273 项回归测试。新数据验证复用其对未变运行代码的既有回执，并执行新增用例、参考、控制与往返检查。冻结后外部验收脚本发生了一处修复；原数据验证回执保留旧源码摘要，acceptance-repair 回执和源码提交绑定另记修复后的摘要，不能声称所有源码始终未变。主包、消费包及模型记录均未因修复重建。

## 任务环境与使用

解压 agent-runtime-v0.16.zip，在根目录运行：

```powershell
python -B runtime_release.py verify .
python -B task-entrypoints/repair-quoted-report-rows-clean-v1/tests/verify.py model/episodes/repair-quoted-report-rows-clean-v1/episode.json
python -B task-entrypoints/repair-quoted-report-rows-clean-v1/solution/reference.py ../reference-v16.json
python -B repair_env.py batch/tasks/repair-quoted-report-rows-clean-v1/scenario.json --output ../episode-v16.json
```

逐行输入 JSON 动作，环境提供 reset/step、观察、奖励和终止状态。test 失败后仍可继续修改。最终代码保存在 episode 的 final_state.code；原请求、可见动作、反馈、代码修改、检查点、说明与终局评分一起保存。参考程序、评分侧隐藏用例和脚本错误控制留在评价侧。

解压 agent-runtime-v0.16-consumer.zip：

```powershell
python -B runtime_exports.py verify .
python -B runtime_exports.py history . v0.16/repair-quoted-report-rows-clean-v1/0007
python -B runtime_exports.py replay . --work ../runtime-v016-replay
```

公开步骤位于 transitions.jsonl，合格训练步骤位于 training/rl-transitions.jsonl，完整公开历史从原请求引用读取。消费包原样嵌入 v0.10/v0.11/v0.12/v0.14/v0.15/v0.16 六个源包。投影本身不调用模型；本版原始采集实际调用十次。

主包 1,405,494 字节，SHA-256：adae343fc3f14fb292aa1f46cf66b2ed4befbdd91fa3bfd03c8ac9a03e362df3。消费包 11,157,738 字节，SHA-256：15d9eab45b0690673cd1ca5ef62c4eb6d10348d3c74e735010b1fbcf6f94c967。材料摘要：60e017b72a6ee91797eb86d69a84b0371d5aefa452ee60a0f1b0bf975f26b7fb。

主包冻结前保留 21 个可见构造事件、8 对工具调用与结果；之后的验收失败、修复、复核和下一候选筛查进入过程补充包。原始验证器失败目录和提前启动的消费核验目录继续保留，不覆盖成成功记录。

## 下一步已有的证据

从 v0.15 失败时保留的前缀抽出 3 个原始事件，已复现处理脚本自匹配：只按输入词语筛选会选出两个调用，加上对应成功结果约束后仅选出正确的一个。输入 6710 字节，现有有界执行器即可运行重建的选择函数。

这只是由真实故障支持的最小复现候选：选择函数是从记录的谓词重建的，不是原完整脚本的历史快照，也不是新模型轨迹。候选继承 development_diagnostic 与 training_eligible=false。完整筛查回执随过程补充包保存；下一阶段可以补任务契约与反例，不必新建运行框架或继续猜测哪道合成题能让模型犯错。

该真实独立解析任务使用原创构造材料，在采集前登记为 train；既有归档中的开发、测试和处理记录保持各自真实来源及用途。模型身份按实际调用记录中的请求配置报告。用例通过和来源资格不能证明泛化、训练效果或真实企业覆盖。toolkit 本轮未修改。
