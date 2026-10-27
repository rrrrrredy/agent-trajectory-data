# 从一个真实执行的问题开始用轨迹

本库最有价值的现成用途，是检查 Agent 如何处理给定证据、输出契约、资料缺失与不确定写入。任务材料包含原创构造记录，轨迹来自实际模型执行；它们不是企业生产日志，也没有证明参数训练能提升业务能力。

**许可先按现状理解：**仓库可公开下载，但根目录 [LICENSE](../LICENSE) 仍保留所有权利；归档中的 `private_internal` 等历史来源字段也没有被改写。本库不是已经获得开放训练许可的数据集。以下训练资格只描述历史任务切分和来源筛选，不向外部使用者授予训练或再分发权。外部复用需要权利人明确许可，不能把公开访问和历史 `training_eligible=true` 当作许可。

## 选择已有发布包

| 要做什么 | 已有资产 | 适用边界 |
| --- | --- | --- |
| 读取标准化 action/observation/reward 和原请求 | [v0.16 consumer ZIP](https://github.com/rrrrrredy/agent-trajectory-data/releases/download/dataset-v0.16/agent-runtime-v0.16-consumer.zip) | 22 条执行、276 步；91 步满足历史训练筛选、7 条满足正向示范筛选。不是 22 道彼此无关的题，也不是训练收益证明。 |
| 判断完整示范是否值得放进上下文 | [用途实验 ZIP](https://github.com/rrrrrredy/agent-trajectory-data/releases/download/study-2026-09-29/workspace-usefulness-20260929.zip) | 4 个任务 × 4 个模型 × 3 个条件，48 条诊断执行；不进入训练导出。 |
| 分清格式适配、理由缺失与最终内容失败 | [格式实验 ZIP](https://github.com/rrrrrredy/agent-trajectory-data/releases/download/format-study-2026-09-29/workspace-format-20260929.zip) | 同 4 个任务 × 4 个模型 × 2 个条件，32 条诊断执行；不进入训练导出。 |
| 研究报告及模型审查的历史修订 | [历史目录](PUBLIC-EVALUATIONS.zh-CN.md) | 保留首次结果、失败和修订，不能将作者尝试、评审票数和任务数相加。 |

`training/rl-transitions.jsonl` 已经存在，不需要另建一套导出。它按用途筛选，且 `observation` 是局部观察；完整决策输入要从 `public_request_ref` 指向的原请求读取。不要把 `final_state` 中评分侧快照当作模型观察，或把 test/development 数据自动提升为 train。同源任务变体与修订版应按来源关系一起处理。

## 无需 API 的第一次使用

Python 3.10+，标准库即可。先下载并解压对应现有 ZIP。下例在本仓库根目录执行，把 `../usefulness`、`../format`、`../consumer` 替换为实际解压位置。

```sh
# 汇总已有结果，不新调用模型；返回每条件及每供应商的数据。
python -X utf8 examples/read_study.py ../usefulness/data/usefulness-study-20260929
python -X utf8 examples/read_study.py ../format/data/format-study-20260929

# 展开完整案例：任务、全部观察事件、每回合请求/响应链接、最终文件和评分。
python -X utf8 examples/read_study.py ../usefulness/data/usefulness-study-20260929 --run kimi/wren-delivery-A --output wren-case.md
python -X utf8 examples/read_study.py ../format/data/format-study-20260929 --run longcat/cedar-pilot-N --output cedar-case.md
```

输出文件已存在时示例停止，避免覆盖已有阅读笔记。它读取 `results.json` 或指定 run，不重新标注，不把旧版采集器写入的 `invalid_model_output` 当作业务动作。旧包把格式拒绝计入 steps，新包分开记录模型回合与环境动作；汇总输出对齐这两个口径，同时保留原始记录。

要检查原始记录而不只是汇总，沿用包内已有命令：

```sh
# 分别在两份实验包根目录执行；离线重放全部既有执行，不是再次采集。
python -B scripts/analyze_workspace_study.py data/usefulness-study-20260929
python -B scripts/analyze_workspace_format_study.py data/format-study-20260929

# 在 consumer 包根目录执行。
python -B runtime_exports.py verify .
python -B runtime_exports.py history . v0.16/repair-quoted-report-rows-clean-v1/0007
```

v0.16 的这个原始请求对应修订后再次测试之前的公开历史；完整任务包含初态 6/8 失败、一次修改后通过以及最终代码，见[既有数据卡](DATASET-v0.16.zh-CN.md)。没有观察到修改后再次失败，不能拿它演示“语义修复失败后的再修复”。

## 三个值得直接看的任务

### 写入超时后，先查结果再重试

用途实验 `kimi/wren-delivery-A`，基础条件、无完整示范。任务要求依据库存和订单材料协调 `report.md` 与 `analysis.json`。库存 72，分配上限 75，需求 80，最终分配 72、缺口 8，结论 `partial_allocation`。

| 原环境步 | 实际动作与观察 |
| --- | --- |
| 1—6 | 读取 policy、brief、两份待改文件、库存与订单材料。 |
| 7 | 用 `revise-report-md-1` 写报告，得到环境预设的 504，写入结果未知。 |
| 8 | 查询同一 operation_id，返回 `absent`。 |
| 9—10 | 沿用原编号重试报告写入，更新 analysis.json。 |
| 11—16 | 复读两份文件，validate、记录与提交；最终 reward=1。 |

这条有 16 回合、35,622 个上报输入 token。能示范幂等写入恢复；504 是构造环境故障，不是供应商真实网络事故。A 条件已经成功，不能归功于完整示范。用途是分析可见行动和结果、检查消费程序能否保持 operation_id，不是证明真实企业恢复率。

### 校验通过，内容仍然交付失败

格式实验 `longcat/cedar-pilot-N`。更新后的试点记录对应 74%，结论为 `further_pilot_required`。实际执行 28 个模型回合，其中 8 次格式拒绝、20 次环境动作，78,996 个上报输入 token。

第 7 步写报告遇 409，第 8 步重读新数据，第 9 步修订报告。第 10 步修改 analysis.json 时损坏保护文字；第 13 步恢复文字，却仍把结果写成 `{"result":{"value":74,"unit":"percent"}}`，缺少约定的 `success_percent` 层。第 14 步 validate 要求补读，第 15—16 步补读，第 17 步 validate 通过；第 20 步提交后的最终评分仍为 0，失败项 `correct_content`。

完整案例保留最终错误输出，不把它改成正确示范。它适合检查“通用一致性校验通过”是否被错误解释成任务成功，也能定位正确数字放错结构的失败；它不是计算错误，更不是已完成业务纠错。

### 正确阻塞也可能伴随多余操作

用途实验 `glm/linden-retention-C`，完整示范条件。必需材料 `retention-waiver` 缺失；第 5、10、12、13、16 步读取同一缺失材料，均为环境预设 404。最终正确提交 blocked，reward=1，原交付件保持未解决状态；共 18 步，含 2 次格式拒绝。A 条件同题只读缺失材料 2 次、共 13 步，也正确阻塞。

用 `--run glm/linden-retention-C` 可展开全文。这能分析不必要重读；一格一次，不能据此确定完整示范导致了额外重读，也不能把正确阻塞叫作完成了原业务目标。

## 已有研究给出的明确取舍

| 条件 | 评分成功 | 模型回合 | 格式拒绝 | 扣除格式拒绝后的环境动作 | 上报输入 token |
| --- | ---: | ---: | ---: | ---: | ---: |
| A 基础说明 | 16/16 | 308 | 58 | 250 | 705,489 |
| B 短经验摘要 | 16/16 | 327 | 83 | 244 | 806,511 |
| C 完整示范 | 16/16 | 266 | 17 | 249 | 2,467,220 |
| N 修复接口、无格式例 | 15/16 | 334 | 68 | 266 | 934,600 |
| E 同接口、一个 JSON 例 | 16/16 | 312 | 56 | 256 | 841,240 |

A/B/C 属同一轮；N/E 属另一轮。C 相比 A 少 42 回合，其中 41 来自格式拒绝减少，环境动作仅少 1；输入约 3.50 倍。这个结果支持优先排查接口格式负担，尚不支持默认注入长示范。N/E 中有效动作的理由缺失由 141/266 变为 9/256；有理由文字不等于理由正确，15/16 到 16/16 仅差一个样本。

两批改变了采集器、提示和调用时间，不能把 C/E 差异归因于示范长度。跨供应商 token 也不是同质货币成本。80 条执行仍来自同四个开发任务，不是 80 个独立问题。完整协议与分模型结果见[用途实验](USEFULNESS-STUDY.zh-CN.md)、[格式实验](FORMAT-STUDY.zh-CN.md)。

下一步最有价值的是已有失败类型上的小规模接口对照，以及真正增加判断难度的有权使用材料：固定任务与公共规则，先比较当前文本接口和供应商原生结构化接口，分开记录格式拒绝、动作、最终内容和计费用量。若各条件仍全部成功，应换有实质判断分歧的任务，而非重复同模板扩容。参数训练收益需要另行训练和来源家族隔离的未见任务，当前没有完成这样的实验。
