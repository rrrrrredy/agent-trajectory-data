# 当前闭源数据生产与评测系统

本项目已经接通数据采集、任务生成、执行记录、程序判定、训练格式导出、评测包交付和本地评测 API。日常处理不需要访谈、标注员、复核员或异常工单。无法验证的输入自动隔离；达到预算或失败上限即停止。

项目位置为 `D:\Codex\agent-trajectory-data`，远端为私有仓库。下面所有命令从该目录执行。商业定位与业界参考见[完整方案](CONCLUSION.zh-CN.md)；本文说明当前实际实现。

## 已有的数据

| 数据 | 实际数量 | 可以支持的结论 |
|---|---:|---|
| 多来源合成任务 | 30 个程序生成家族、300 个任务、10 种场景模板 | 确定性环境与规则能够运行 |
| 脚本控制轨迹 | 300 次通过 | 执行器与验收规则的联通验证 |
| 当前协议的模型轨迹 | 2 个任务、8 次调用、2 次通过 | 模型实际完成年费换算和两次 429 后恢复 |
| 明确选择的真实会话快照 | 319 条可见事件、156 个工具调用、155 个工具结果 | 自有工作过程确实发生过；有 1 个调用尚未配对 |
| 当前可交付评测包 | 260 个任务、26 个家族、10 种模板 | 可脱离工厂仓库独立运行 |
| 当前真实 SFT / 偏好对导出 | 0 / 0 | 输出用途仅许可内部诊断，不将脚本或未核验会话混入训练集 |

任务按家族固定切分：train 180、development 80、holdout 40。下载包排除 holdout；训练导出排除 development 和 holdout。同模板的数值、名称变化仍共享生成机制，30 个家族不能解释为 30 类独立能力，隐藏家族通过也不证明跨模板泛化。

真实会话、模型在合成环境中的真实执行、合成任务和脚本控制分别标识。会话导入没有冻结其外部工具环境，不能精确重放原始开放网络，也不具有自动确立的正确答案。

## 一条命令生产，持续运行接收新输入

```powershell
py -3 -B -m agentdata --root data/production-current factory --config configs/factory-control.json
```

该命令完成：生成或读取输入 → 冻结任务与环境 → 执行 → 保存事件及失败 → 程序验收 → 按用途导出 → 生成带清单的评测 ZIP。相同输入与配置再次运行不会重复生产。

持续处理入口：

```powershell
py -3 -B -m agentdata --root data/production-current service-start --kind factory --config configs/factory-control.json --interval 60
py -3 -B -m agentdata --root data/production-current service-status --kind factory
py -3 -B -m agentdata --root data/production-current service-stop --kind factory
```

后台进程隐藏启动，有独占锁、心跳和停止请求。重复启动返回同一进程；退出后可重新启动。停止是协作式的：当前有限批次完成后退出，不强杀取消状态未知的模型请求。它不会安装 Windows 服务或开机任务。验收结束后测试进程已停止。

默认工厂只运行本地脚本控制，不产生外部模型调用。生成器不是每天机械复制同一批任务：只有配置或允许来源出现新输入才建立新工作项。

## 真实数据怎样进入

**结构化产物**使用 JSON Pointer 选择字段。在默认配置下，将 JSON 产物写入 `data/factory-input/sources`，再由上游程序向 `data/factory-input/inbox` 写入输入描述：

```json
{
  "source": "own-structured-workflow",
  "path": "completed-batch.json",
  "source_group": "one-stable-workflow-series",
  "origin": "artifact_derived"
}
```

默认字段映射是 `/status`、`/jobs`、`/calls_reserved`；更换产物类型时修改配置中的 selectors。source_group 应绑定同一来源系列，版本和变体继承其切分。同一输入哈希与字段映射冒用不同组名会被隔离。

产物衍生任务标为 artifact_derived。声称是实际任务时，origin 设为 observed_task，并提供 task_id、occurred_at、workflow_id 收据；这是来源记录，不是第三方真实性认证。真实来源默认禁止传给外部模型。

**真实运行日志**从明确选定的 Codex JSONL 导入：

```powershell
py -3 -B -m agentdata --root data/production-current import-session "D:\path\to\selected-session.jsonl"
```

保留用户消息、助手的 commentary/final 消息、顶层工具调用和结果；排除 analysis、reasoning、系统和开发者消息。缺失配对、坏行、来源哈希和模型配置分别记录。凭据过滤只覆盖已定义模式，不等于全面个人信息匿名化；现有会话只供本地诊断。

自动入口也支持来源配置 `{"root":"允许目录","kind":"session","external_model_allowed":false}`，输入描述提供 source 和相对 path。这个来源只采集日志，不启动模型、评分或训练。优先投递已完成的不可变日志，避免把持续增长的会话反复保存成完整快照。

## 决策、失败与恢复规则

| 情况 | 自动动作 |
|---|---|
| 来源格式、路径、用途或证据不符合要求 | 隔离，并保存机器可读原因 |
| 多来源时间、地区、权威等级冲突 | 按题面固定规则选择，不由评分模型臆测 |
| 同等级且同时间的来源冲突、关键字段缺失、全部不可用 | 必须回答证据不足 |
| 429 | 在每来源最多 3 次读取和任务预算内重试 |
| 明确提交了错误答案 | 配置允许时新建关联尝试，最多 3 次，保留第一次失败 |
| 超时、进程丢失、远端取消状态未知 | 保留原记录，不自动重发同一请求 |
| 同一输入或同一 API request_id 再次到达 | 返回已有结果；内容冲突则拒绝 |
| 步骤、时间、批调用或月调用达到上限 | 停止，未完成不能记为成功 |
| 来源被撤回 | 阻断后续导出、API 访问和受控交付 |

关联重试目前是同一任务和策略重新运行，不能叫已实现“定位根因并修复策略”。偏好对要求同任务、模型配置和运行限制，且成功与失败的用途都许可。它表达结果偏好，不证明某一步造成了改进。转换后的 messages 还需要按训练器的聊天模板接入。

## 运行模型

当前新协议联通配置只选择两个纯虚构任务，最多 8 次适配器调用：

```powershell
py -3 -B -m agentdata --root data/production-current pipeline --config configs/codex-research-smoke.json --batch-id research-model-smoke-001
```

当前数据目录里的这个批次已完成；同命令复跑已确认仍为 8 次调用。新机器先执行默认工厂命令生成任务，并具备有效的本地 Codex 登录。凭据不复制到仓库。

本次返回 input_tokens 90,048、cached_input_tokens 0、output_tokens 519。请求配置为 gpt-6-astra，实际服务模型版本和账单金额未获权威返回。调用预留是适配器次数，CLI 底层可能重试传输；月额度按同一数据根目录共享，不是账号范围额度，也不是货币硬上限。

生产工厂切换到模型策略时必须配置月调用上限，真实来源还必须逐来源允许外传。本项目没有替先前被拒绝的真实产物发送寻找绕行路径。

## 服务端评测与本地客户端

```powershell
py -3 -B -m agentdata --root data/production-current issue-key --file data/production-current/keys/demo.json --label demo --credits 20
py -3 -B -m agentdata --root data/production-current service-start --kind eval --port 8765
py -3 -B -m agentdata evaluate-api --key-file data/production-current/keys/demo.json --output artifacts/api-control.json --limit 10
py -3 -B -m agentdata --root data/production-current service-stop --kind eval
```

密钥只写入被 Git 忽略的数据目录，不打印。每个新 trial 扣一个本地额度；重复开始请求不重复扣，两个并发请求不能超支。试次拥有者、冻结环境、工具读取次数、动作、返回结果和额度保存在 SQLite 中，重启后保留。

默认客户端是脚本控制。接入自己的 Agent 时，为 evaluate-api 加 `--agent-config agent.json`。配置形如 `{"argv":["你的程序","参数"]}`：程序从 stdin 读取 task 和 observations，从 stdout 输出 fetch_source 或 submit_answer 的 JSON。该程序在客户端本地执行。

接口使用 Bearer 密钥：

| 接口 | 输入与行为 |
|---|---|
| GET /v1/tasks | 列出可用任务及剩余额度 |
| POST /v1/trials | request_id、task_id；冻结并开始一次试次 |
| GET /v1/trials/{id} | 仅允许拥有者读取；过期返回 not_assessed |
| POST /v1/trials/{id}/actions | request_id、expected_step、action；幂等执行下一步 |

每个试次最多 8 步、300 秒，每个来源最多读取 3 次。评分返回 pass/fail/not_assessed，不返回参考答案。客户端可以看到题面和其请求的工具观察；这不承诺题库无法被提取。服务端不能认证外部客户端实际用了哪个模型。

当前 HTTP 服务只绑定 127.0.0.1，面向本地诊断。生产公网托管、HTTPS 网关、商户收款和支付权益同步未部署；不能把本地额度当成真实付款。

## 发布、撤回与定位数据

```powershell
py -3 -B -m agentdata --root data/production-current release artifacts/my-release.zip --release-id my-release --audience licensed
py -3 -B -m agentdata --root data/production-current resolve-release --release-id my-release --audience licensed
py -3 -B -m agentdata --root data/production-current withdraw --kind source_group --value "某个来源组" --reason owner_withdrawal
```

商业授权打包要求任务具有 evaluation_distribution 用途；默认模型轨迹不会随评测包分发。生成配方、完整轨迹、会话日志、隐藏集和凭据保留在私有目录。专有许可下载包含可读的任务、环境、答案、客户端与评分器；代码可读不等于授予开源许可。

受控交付必须经过 resolve-release 实时检查。它会核对任务哈希、撤回状态和 ZIP 哈希。旧版缺少来源关联的发布收据需要重新构建。撤回不删除原始证据，也无法抹除已经下载的副本。

当前最终包为 `artifacts/research-evidence-eval-20260924.zip`，SHA256：
`bfa0ae5f7257e129faf5fbcee16e9dee6f91e99f011ffae72cf6863296ee2173`。

| 路径 | 内容 |
|---|---|
| data/production-current/tasks | 冻结任务、环境和答案 |
| data/production-current/runs | 执行事件、模型捕获与结果 |
| data/production-current/runtime_sessions | 真实会话可见事件及完整度说明 |
| data/production-current/factory | 输入状态、失败隔离、冻结配置 |
| data/production-current/batches | 调用预留、批次导出、训练格式与拒绝原因 |
| data/production-current/evaluation/service.sqlite3 | 本地 API 额度与试次状态 |
| data/production-current/governance/withdrawals | 撤回记录 |
| data/production-current/acceptance-v2.json | 当前实测结果及口径修正 |

当前系统证明了自动生产和可执行评测闭环。对外销售应仍以小型专有评测包、自助试用和真实付费行为来验证；当前未建立客户需求、训练收益或盈利证据。
