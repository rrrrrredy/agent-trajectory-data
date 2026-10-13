# 数据构建的现有运行入口

当前交付为 [v0.7](DATASET-v0.7.zh-CN.md)：scripts/model_rollout.py 验证整体包，scripts/runtime_curriculum.py 验证冻结课程，scripts/business_env_v2.py 提供 JSONL 与 reset/step 接口。完整历史及排错任务在 v0.4。本文以下保留早期管线记录，不能用于读取当前数量或结果。

当前建设顺序以[构建计划](PLAN.zh-CN.md)为准。下面说明已经可用的本地工具；工具存在不代表数据集内容已完成。

项目位置：D:\Codex\agent-trajectory-data。命令从该目录执行，运行环境为 Python 3.10+，实际验证为 Windows / Python 3.11。

## 查看已有数据

```powershell
py -3 -B -m agentdata --root data/production-current stats
```

当前目录保留 300 条使用构造材料的任务、300 条脚本控制和 2 条模型轨迹。旧模型批次在 data/production-v0.2，另有 3 条模型轨迹。数据完整度与来源边界见[当前判断](CONCLUSION.zh-CN.md)。

当前任务切分为 train 180、development 80、holdout 40。同一参数家族不跨切分，但各切分共享场景模板，不能因此宣称跨模板泛化。

## 导入已明确选择的真实记录

```powershell
py -3 -B -m agentdata --root data/production-current import-session "D:\path\to\selected-session.jsonl"
```

这里只处理明确选定的文件，不扫描全部历史。当前导入器保留可见消息和顶层工具请求、结果，排除 analysis、reasoning、系统和开发者消息。它会记录缺失配对和坏行，不会补造事件。

这一旧会话仍缺少冻结的外部环境，旧 import-session 入口本身没有完成任务与产物对齐。v0.2 针对明确选定的历史研究运行另行完成了对应关系；v0.3 已补回部分实际网页返回，原始截断与完整外部环境缺失继续保留。

结构化产物入口 capture-facts 可按 JSON Pointer 选择已有字段并保存来源哈希。它得到的是 artifact_derived 样本；程序自身汇总派生的题不能替代研究任务轨迹。

## 有限执行与验证

已有 pipeline 入口支持冻结配置、有限任务数、调用预留、失败保存和中断恢复。相同已完成批次再次运行会返回已有结果，不重新发送完成的调用。

当前两个新协议模型任务的批次为 research-model-smoke-001，配置为 configs/codex-research-smoke.json。它已经使用该数据根目录本月配置的 8 次调用预算。本轮清理与重新规划不提高预算，也不通过换数据目录绕过上限。

第一次错误保留；后续尝试使用新 run_id 并关联父记录。命令执行控制只面向可信本地程序，不作为运行任意外部代码的隔离环境。

## 本地导出

```powershell
py -3 -B -m agentdata --root data/production-current export artifacts/diagnostic.json
py -3 -B -m agentdata --root data/production-current training artifacts/training
```

导出目标不可变；内容改变时使用新的目标文件或目录。默认诊断导出按用途和完整性检查记录，默认不将脚本控制当模型训练示范。训练导出还要求用途许可、有效结果和 train 切分。

当前真实 SFT 和偏好对数量均为 0。允许用途是来源元数据，不是由“文件存在”自动推导的权利。来源撤回检查继续用于阻止不合适的数据导出。

## 数据位置

| 路径 | 内容 |
|---|---|
| data/production-current/tasks | 当前冻结任务、环境与参考答案 |
| data/production-current/runs | 当前真实执行事件、模型捕获与脚本控制 |
| data/production-current/runtime_sessions | 真实会话可见事件和完整度说明 |
| data/production-current/batches | 原批次配置、调用预留、结果与导出记录 |
| data/production-v0.2 | 旧协议的 3 条实际模型轨迹 |
| data/live-probe-v0.2 | 独立保存的接入失败探测 |
| artifacts/research-evidence-eval-20260924.zip | 既有 260 条非 holdout 任务的独立评测包 |

既有 ZIP 的 SHA256 为 bfa0ae5f7257e129faf5fbcee16e9dee6f91e99f011ffae72cf6863296ee2173。它不包含真实会话、模型轨迹或 holdout 任务；下载内容含参考答案，只用作本地回归材料。

## 当前退出主流程的功能

后台常驻、目录轮询、定时扩产、HTTP 评测、客户端额度和受控交付管理保留为旧实现，但当前不启动、不扩展。相关历史测试只能证明各自工程行为，不计作数据集完成条件。

商城和支付开发已删除。当前工作只围绕数据集文件、必要执行脚本和验证结果展开。
