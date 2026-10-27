# 从一个实际拒绝回合准备接口对照

已有格式实验里，`deepseek/cedar-pilot-E` 第 2 回合已经带有合法 JSON 示例，模型仍返回 DSML 工具标记。文本采集器给出 `non_json_tool_markup`，没有执行环境动作。第 3 回合收到反馈后，才以合法 JSON 读取 `brief`。这说明仅加示例没有消除该次接口不匹配；它不说明换接口一定能修复，更不说明业务判断失败。

这份消费示例把该回合的**实际公共输入**导出为两份请求，只在其中一份增加 `response_format: {"type": "json_object"}`。系统指令、已有格式例子、历史、模型名、推理参数与输出上限保持一致。不读取任务隐藏状态、参考解或最终评分来构造输入，不改写冻结的采集器。

## 现在可以离线完成

先按[使用入口](START-HERE.zh-CN.md#无需-api-的第一次使用)下载并解压已有格式实验 ZIP。在仓库根目录运行，替换实际解压路径：

```sh
python -X utf8 examples/prepare_format_probe.py prepare ../format/data/format-study-20260929 --output ../format-probe
python -X utf8 examples/prepare_format_probe.py inspect ../format/data/format-study-20260929/runs/deepseek/cedar-pilot-E/calls/002/response-1.json
python -X utf8 examples/prepare_format_probe.py inspect ../format/data/format-study-20260929/runs/deepseek/cedar-pilot-E/calls/003/response-1.json
```

第一条写出 `text-request.json`、`json-request.json` 和含来源哈希的 `manifest.json`；目标目录须不存在。后两条应分别显示 `envelope_accepted=false` 与 `true`，后者动作是读取 `brief`。这些命令不访问网络、不会重新调用模型，也不会执行返回动作。第 3 回合已经看过错误反馈，不能把它当成只改变接口后的实验结果。

检查自己保存的 Chat Completions 响应时，同样运行 `inspect response.json`。返回是否完整、外层动作契约能否解析、错误及服务上报用量；它不检查动作参数是否满足环境要求，不执行任务，也不给业务内容打分。可解析、可执行、最终正确是不同判断。

## 接通服务后怎样比较

[DeepSeek 官方 JSON Output 说明](https://api-docs.deepseek.com/guides/json_mode/)要求设置该参数、在提示中说明 JSON 并提供示例，同时提示仍可能返回空内容。这里选 E 条件，已有 JSON 要求与示例；本方案是 JSON 输出模式，**不是原生 function calling**。旧采集器的模型名是 `deepseek-flash`，`max_tokens` 是 16384；这是原调用配置，不保证今天的端点、版本或计费条件相同。

具备服务访问条件后，将两份请求分别交给该端点，使用自己的本地凭据，保存响应再检查。若更换模型或参数，两边须同步修改并记录实际配置；原始 2026-09-29 响应只作失败定位，不能充当今天的新基线。不要把凭据、请求头或隐藏推理提交到数据仓库。

最小筛查可在同一当前模型上交错运行两条件各 3 次，共 6 次单回合调用，全部保留；空输出、截断和服务失败单列，不能靠择优重试消失。比较响应完整性、动作契约接受情况、用量和延时，只回答**这个已选失败状态**是否改善。不能估计整体格式错误率，也不代表完成整条任务。

若要回答业务收益，还缺独立材料和真正要求判断的任务。当前四题的 `brief.outputs` 已给计算公式，`decision_rule` 已给阈值或字面结论；例如 cedar 明确给出成功率计算和 80% 门槛，主要测证据更新、执行与输出契约。后续应选未参与示范的有权材料，要求模型自行选择适用时间、证据范围或拒绝不支持的结论，并保留原文出处与可核对答案。只更换任务名称、数值或同一公式不增加这类覆盖。

截至 2026-10-27，本示例已完成原包输入导出和拒绝/修正响应的离线检查；**尚未运行上述 6 次服务对照**，没有新增成功率、成本或业务收益结论。原数据资格和许可保持不变。
