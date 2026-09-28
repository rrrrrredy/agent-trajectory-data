# v0.6：来源分离的数据与实际模型首次尝试

v0.6 已完成数据构建、限定模型采集和独立包验收。现在可以独立运行任务、记录动作与失败、重放评分，并分别读取合成监督和实际模型记录。实际模型尚未完成一条端到端任务，这个结果原样交付。

## 这份包有什么

| 内容 | 数量与用途 |
|---|---|
| 来源家族 | 4 组：容量规划、资料保留两组新虚构材料；Muse、循环 Transformer 两组归档研究材料 |
| 训练任务 | 10 个，全部来自两组新虚构材料 |
| 评测任务 | 10 个，全部来自两组归档；整组排除训练导出 |
| 每题交付 | 题面、初态、工具与运行环境、评分脚本、参考解法 |
| 脚本控制 | 60 条：每题的成功参考、空提交、范围错误提交 |
| 合成监督 | 10 条 scripted_reference 示范；10 组 scripted_counterfactual 偏好对 |
| 实际模型记录 | 3 条首次尝试、36 次决策、36 个独立上下文 |
| 成功模型示范 | 0；未完成与评测来源的排除原因均保留 |
| 处理记录 | 本次 59 条可见事件，加上原封保留的前阶段 50 条 |

Muse 和循环 Transformer 的原报告、来源表、主张表按原字节冻结。适配器取前八条主张及对应来源行，只检查登记关系，不把登记完整当成报告事实正确。真实资料、派生场景、虚构组织事件、脚本控制和模型执行有独立标签。

训练与评测家族交叉为 0，同一来源的修订及故障变体留在同一侧。四个来源家族共享工作流模板；这里的分离是来源分离，不代表跨模板泛化。与旧评审输入的片段排重检查也不构成预训练去污染证明。

## 实际模型跑到了哪里

| 首次任务 | 实际过程 | 停止位置 |
|---|---|---|
| 合成容量材料：限流恢复 | 空检索后缩短关键词；定位规则和主张；读取来源表两次得到 429 | 第 12 次决策，仍未读到来源表 |
| Muse：并发修改场景 | 读到四份材料；把读取回执编号作为证据参数，写说明得到 422；随后补读 | 第 12 次决策，尚未更新任务单，并发冲突未触发 |
| 循环 Transformer：权限拒绝 | 来源表返回 403；写明限制；把任务单更新为 blocked | 第 12 次决策，尚未 submit |

三条都能逐步重放，均是未完成轨迹。环境评分入口返回 incomplete_episode，reward=0；它不代表已经作出完整任务的终局能力判断。

本批模型看到的环境预算是 30 步，外部采集器按批准的每条 12 次决策停止，但没有在请求中显示该较小上限。因此这组结果同时反映采集设置的限制。原始请求、失败和停止位置都保留，没有补一个模型从未作出的提交。

第二条还暴露了工具说明歧义：evidence_ids 实际接受 policy、handoff、sources、claims 等文档编号，公开类型只有 list[string]，模型使用了 read-3 一类回执编号。本版说明明确了两者；原环境及首次请求保持冻结。

## 如何使用

解压 agent-runtime-v0.6.zip 后验证：

    py -3 -X utf8 -B verify_runtime.py verify .

运行参考解法：

    py -3 -X utf8 -B curriculum/tasks/business-synthetic-capacity-tool_retry-v2/solution/reference.py --output ../reference-v6.json
    py -3 -X utf8 -B curriculum/tasks/business-synthetic-capacity-tool_retry-v2/tests/verify.py ../reference-v6.json

观察式环境入口：

    py -3 -X utf8 -B curriculum/business_env_v2.py curriculum/tasks/business-synthetic-capacity-tool_retry-v2/environment/scenario.json --output ../episode-v6.json

完整归档供评价端使用；策略只接收题面、工具接口和实际观察。运行文件写在包外，新运行不覆盖旧文件。执行时应把实际调用上限与剩余额度明确提供给策略。

合成监督位于 curriculum/training/；模型示范筛选结果位于 training/。model-sft.jsonl 本批为空，selection.json 解释每条排除原因。偏好对共享完全相同的观察前缀，只改变最后一次提交范围，不能当作真实模型偏好实验。

## 验证、来源与限度

149 项实现测试通过。独立解压校验 391 个内容文件，分别执行三条实际轨迹的评分与三条参考解法；12 类篡改即使重算外围哈希仍被拒绝。参考可解、失败能检出、数据能重放，和模型实际完成任务是不同的结果。

批准、冻结输入、原账本前缀及最终账本一同交付：新增调用 36 次，原 8 条预留未改，总数 44。CLI 报告 input_tokens=422760、cached_input_tokens=49152、output_tokens=2294；费用未推算。模型身份记录请求配置 gpt-6-astra，不声称服务端身份得到独立认证。

主 ZIP 为 860,494 字节，SHA-256：

    982f9867b6356f9d777addb7e18c9919317b4f99622b3a503254ed2e73c15d37

[私有发布](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.6)同时提供独立验收及测试回执。旧 v0.4 完整历史语料和 v0.5 环境修订保持不变。本版是可运行、可检查的小型数据集；没有足够证据支持模型能力提升或跨企业迁移结论。

主包冻结后的提取修复结果、打包与独立验收另有 18 条可见事件，随 agent-runtime-v0.6-delivery-evidence.zip 交付；其摘要绑定主包及两份验收回执，衔接主包内处理记录的结束位置。
