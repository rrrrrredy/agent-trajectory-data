# 从自有产物到可运行评测包

本文保留早期事实入口和定时触发工具的历史说明；它们已退出当前主流程，不作为最新交付范围。当前数据包见 [v0.5](DATASET-v0.5.zh-CN.md)，完整历史语料见 [v0.4](DATASET-v0.4.zh-CN.md)。

## 自动采集

入口接受一个 JSON 产物、一组 JSON Pointer、稳定的来源组和用途政策。适配器从所选字段确定性生成事实与答案；目前支持标量字段和正常、404、429 后恢复三种工具环境。

```powershell
py -3 -B -m agentdata --root data/my-workflow capture-facts path/to/result.json --selectors configs/fact-selectors.json --source-group my-workflow-series --rights configs/rights-internal.json
```

默认来源是 artifact_derived。字段映射应按实际业务产物配置，示例映射针对本项目批次汇总。source-group 应长期代表同一来源或业务母题，不能为了换切分而随意修改。实际任务入口可以传入 --origin observed_task 和 --task-receipt；收据必须包含 task_id、occurred_at、workflow_id，来源仍标为调用方声明。

capture_facts 函数返回 task_ids。自动工作流将这些 ID 写入 pipeline 配置的 task_ids，再调用 run_pipeline。已有的生成参数保留兼容；提供 task_ids 后不再生成虚构事实。整个过程可在同一脚本中执行：

```python
from pathlib import Path
from agentdata.core import read
from agentdata.taskpacks import capture_facts
from agentdata.pipeline import run_pipeline
from agentdata.release import build_release

root = Path("data/my-workflow")
intake = capture_facts(
    root, Path("path/to/result.json"),
    read("configs/fact-selectors.json"),
    "my-workflow-series", read("configs/rights-internal.json"),
)
config = read("configs/control.json")  # 本地控制；模型配置会发送任务至该模型服务
config["task_ids"] = intake["task_ids"]
run_pipeline(root, config, "daily-20260924")
build_release(root, Path("artifacts/internal-eval.zip"), "daily-20260924")
```

批次 ID 对应冻结输入。新产物使用新 ID；同一 ID 重跑不会重新执行已完成任务。新旧内容冲突不会覆盖旧记录。新入口采用 closed-facts-v2，严格区分布尔和数值；历史固定事实任务保留原评分协议。

## 评测包

```powershell
py -3 -B -m agentdata --root data/my-workflow release artifacts/internal-eval.zip --release-id internal-001
```

包内包含 tasks.json、evaluate.py、control_agent.py、DATA_CARD.json、manifest.json 和专有许可。它不依赖工厂仓库，也不包含原模型轨迹。

默认只供内部评测。--audience licensed 只接受用途政策含 evaluation_distribution 的任务；政策声明不自动创造第三方权利。两个出口都排除 holdout。训练切分中的任务可作为公开答案的开发/回归套件交付，不能因此称为新的隐藏测试。

解压后，为可信本地代理创建 argv 配置，例如：

```json
{"argv":["python","D:/Agents/your_agent.py"]}
```

运行：

```powershell
python evaluate.py --agent-config agent.json --output result.json
```

代理每次从 stdin 读取 task 与 observations，向 stdout 返回一个 fetch_source 或 submit_answer 动作。运行器每题重置工具响应计数，默认最多 5 步、30 秒，保存结果与可见事件；不覆盖已有结果文件。control_agent.py 是脚本正控制，不是模型。运行器验证文件哈希，但这些哈希只是本地一致性检查。

下载包带有答案，适合回归测试。它不是服务端秘密测试集，也不隔离不可信客户代码。详细排除名单只在数据根目录的 releases/ 构建记录中保存；交付包只给出原因计数。

## 定时执行与预算

```powershell
py -3 -B -m agentdata --root data/scheduled cycle --config configs/codex-scheduled.json --period-hours 24
```

cycle 使用 UTC 时间窗口和配置生成稳定批次 ID；同一窗口重复触发会恢复原批次。所附模型配置最多每批 8 次、同一数据根目录每 UTC 月 40 次调用。月账本在调用之前持锁写入；丢失或取消状态未知的调用不返还预算。不同模型批次要共享同一个数据根目录及一致的月上限政策。

该月上限只覆盖启用了 monthly_model_calls 的入口，不能约束绕过该入口的调用或其他数据根目录。它是调用次数上限，实际账单仍未知。当前没有安装操作系统定时任务或常驻服务；将该命令放入既有调度器即可按需触发。电脑关闭时不能执行，重启不会补跑所有错过的周期。

## 本次实际验证

58 项自动测试通过。既有真实模型批次为三个合成任务、七次可见模型调用，三个确定性结果通过；原始证据在 data/production-v0.2。

新入口使用该批次的自有运行汇总，生成一个产物衍生家族的三个变体。本地脚本执行全部通过；导出的 ZIP 在独立解压目录重跑也全部通过。详细记录在 data/artifact-delivery/delivery-verification.json，包为 artifacts/agent-evaluation-internal.zip。

新示例外传至模型的调用被自动审批拒绝，因此没有把本地控制验证算成模型验证。原始拒绝前生成的记录保留，未覆盖修复。

本文保留旧版采集与打包行为说明。当前只推进数据内容构建；定时扩产和交付管理退出主流程，具体范围见[构建计划](PLAN.zh-CN.md)。
