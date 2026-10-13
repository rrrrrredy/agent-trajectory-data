# Agent 运行数据 v0.5：证据读取、失败保留与环境评分

本次交付已经跑通的业务环境修订包。每个场景都包含任务、初态、工具、轨迹、评分器和参考解法。v0.5 单独解压即可执行，不依赖源码仓库；完整历史语料与七个 Python 排错题继续保存在未修改的 v0.4 包中。

## 修复的是评分可信度

实际复现了两条旧版误判：来源表只返回 429，仍能得到“证据齐全”的通过结果；在证据缺失时写说明，随后补读材料，也能把旧说明补成通过。另一个接口问题是参考命令的输出缺少 task_id，交给任务评分器会抛出 KeyError。

v0.5 使用 business-env-2，旧版 business-env-1 原样保留。新规则要求：

- 可用材料必须有当前版本的 200 读取回执。403/404 可以支持实际被阻塞的结论；429 保留为临时失败。
- 说明绑定写入当时已有的回执，保存读取步骤、文档版本和正文摘要。证据不足时写入返回 422；补读成功后要新写说明，再更新任务单。
- 任务单更新保留版本和历史。并发冲突后须读取当前任务单再重试。
- 无效 JSON、非对象输入和试图重置正在执行的任务，都会成为失败事件并消耗步骤。30 步上限和首次失败无法靠重置清除。
- 参考命令与实际交互使用同一份运行记录格式，评分器重新执行动作并核对观察和末态。

说明的语义质量没有被自动认证。当前奖励检查登记关系、状态和证据约束，不证明报告事实正确。

## 数据构成

| 内容 | 数量及含义 |
|---|---|
| 环境 | 10 个旧场景的新版本，仍来自两组归档研究材料；独立任务家族没有增加 |
| 脚本控制 | 48 条：22 条通过、26 条未通过；未通过中 1 条因提前结束而不完整 |
| 实际交互 | 当前作者助手执行 2 条，各 10 步，分别包含连续 429 和并发冲突后的恢复 |
| 原始误判 | 2 条旧版 reward=1 的完整反例，连同旧环境与原评分代码保存 |
| 参考命令失败 | 原命令产物和真实 KeyError 返回保留 |
| 处理过程 | 36 条可见事件，包含工具请求、返回、诊断说明、代码修改与验证 |
| 独立包 | 139 个内容文件，另有 manifest.json |

脚本控制中的攻击使用了评分真值，明确标为 oracle_assisted_adversarial_control。恢复控制也属于脚本，不能用于计算模型成功率。

两条实际交互由当前助手通过 JSONL 工具接口执行，保存原始输入、逐步观察、失败、重试与提交，并绑定原会话工具调用。执行前作者已经看过环境、评分器和参考实现，所以标为 seen_development_integration_run；不称为盲测。原生记录没有可靠提供具体模型身份、token 和费用，这些字段保持未验证或空值。

## 文件结构与运行

    tasks/<id>/instruction.md        题面
    tasks/<id>/environment/          冻结状态
    tasks/<id>/rubric.json           评分范围
    tasks/<id>/tests/verify.py       评分入口
    tasks/<id>/solution/reference.py 参考解法
    episodes/<id>/                  完整运行与未完成尝试
    episodes.jsonl                  来源、角色、奖励与用途索引
    processing/                     原始可见事件与实际动作的对应关系
    sources/audit/                  原误判和参考命令失败
    sources/tasks/                  原版十个场景
    sources/parent-manifest.json     v0.4 原文件清单与摘要
    audit-findings.json              发现的问题及修订结果
    verify_dataset.py               验证、导出和打包

在仓库根目录验证：

    py -3 -X utf8 -B scripts/runtime_revision.py verify data/agent-runtime-v0.5

在 v0.5 解压目录验证并执行参考运行：

    py -3 -X utf8 -B verify_dataset.py verify .
    py -3 -X utf8 -B business_env_v2.py tasks/business-customer-service-tool_retry-v2/environment/scenario.json --policy reference --output ../reference-v5.json
    py -3 -X utf8 -B tasks/business-customer-service-tool_retry-v2/tests/verify.py ../reference-v5.json

运行记录写在数据包外，使用新路径，已有文件不会被覆盖。去掉 --policy reference 就是逐行 JSON 交互入口。完整包有参考答案，给模型时只导出题面、初始观察和工具说明：

    py -3 -X utf8 -B verify_dataset.py export-learner . --task business-customer-service-tool_retry-v2 --output ../learner-v5

业务状态由独立评价进程维护。reset/step 接口可用于收集 rollout，但本轮没有运行参数训练。

## 如何确认修好了

同样的旧攻击动作先由原环境重放，必须复现 reward=1；再由新环境重放，必须得到 0。这样保留了原错误，也避免把失败版本偷偷改成正确版本。另有恢复控制证明成功读取、重写说明并正确提交后可以通过。

独立解包后，参考命令、任务内参考脚本、评分命令和输入导出都实际执行。连续 429 与并发冲突的两条作者交互也经保存、加载和逐步重放确认。132 项工程测试通过，新增打包器另由独立包验收覆盖。

八种篡改在重算外层哈希后仍被拒绝：脚本冒充模型、已见任务冒充盲测、删除原始传输记录、失败改成功、抹去旧误判、删除失败 episode、替换原始动作、删除无效输入事件。它们是这些具体行为的回归验证，不是对所有可能攻击的完整证明。

## 交付与边界

[公开 v0.5](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.5) 交付 ZIP、验收回执和测试回执。ZIP 为 558,416 字节，SHA-256：

    7d43c1e0ea59e29346ec48bf49c07b0e5d01edbe1188b1b3c7f16f337eb44086

正式构建与独立验收过的 ZIP 完全一致。v0.4 目录和原 ZIP 的摘要也保持不变。

当前构建解决了可执行性、可追溯性和已发现的评分漏洞；独立模型能力、真实企业适用性与跨企业泛化尚未验证。训练记录为 0，全部仍为开发诊断用途。没有增加调用预算、人工环节、企业平台集成或商业功能。
