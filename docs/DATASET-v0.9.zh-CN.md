# 数据集 v0.9：证据依赖、冲突判断和分项修订

本版完成 6 个新合成来源家族、24 个场景及 3 种机制。每题交付任务、文档和时间快照、可执行环境、评分器、参考解法、错误对照；实际模型任务另含完整公开请求、回复、工具动作、失败、状态检查点及奖励。

六条选定任务使用请求模型 gpt-6-astra，首次尝试成功 6/6，共 70 次调用，步数为 13、11、8、8、16、14。导出 3 条成功训练轨迹与 37 条决策；三个测试家族保持排除。模型身份来自请求配置，没有服务端独立身份回执。

## 新增机制

| 机制 | 训练家族 / 测试家族 | 任务要求 |
|---|---|---|
| evidence_chain | willow-dispatch / marina-capacity | 沿多份材料追到叶节点，换算单位、求和、扣除预留，并核对主张 |
| evidence_conflict | cedar-access / flint-retention | 根据公开权威规则处理冲突；同级异值保留不确定性 |
| revision_workflow | aster-routing / cobalt-release | 修复两处主张、保留受保护内容、拒绝错误建议、处理版本变化并逐项复读 |

每个家族四个变体，计为一个来源家族。反事实必须改变正确结果。另有临时 429、不可取得材料，以及修订时的 409；场景类型不同，不把所有故障简单笛卡尔积扩成新来源。

未来材料按 available_at 与 as_of 比较，不能搜索到，直接读取返回无正文、无版本的 404。任务编号采用不含故障和切分名称的公开标识。该环境是静态时间快照，不模拟企业长期运转或时钟自动推进。

## 真实模型结果

| 任务 | 切分 | 动作数 | 最终状态 | 奖励 |
|---|---|---:|---|---:|
| willow-dispatch-tool_retry-v4 | train | 13 | needs_revision | 1 |
| marina-capacity-counterfactual-v4 | test | 11 | ready | 1 |
| cedar-access-clean-v4 | train | 8 | blocked | 1 |
| flint-retention-counterfactual-v4 | test | 8 | ready | 1 |
| aster-routing-stale_revision-v4 | train | 16 | ready | 1 |
| cobalt-release-counterfactual-v4 | test | 14 | ready | 1 |

正确的 blocked 可以得到奖励 1。模型的 decision_summary 是可见的简短动作理由，不是隐藏推理。每个决策使用独立上下文并携带先前公开动作和工具观察；评价侧完整场景、答案与参考解法不进入请求。

预算在调用前冻结：每题 32 步、整批 192 次、每次 90 秒、整批 1,800 秒。原 107 条调用预留不变，最终累计 177。每个请求都看到实际剩余步数、调用数和时间。失败及停止原因原样保存；未产生未知在途调用。

## 评分、轨迹与用途

24 条脚本参考全部通过，158 条错误对照全部被拒绝；其中包含未来证据引用、按较新日期强解同级冲突，以及只修一项却宣告完成。12 条脚本训练示范标为 scripted_reference，单独保存，不计为模型示范。

环境显式记录逐步 reward、terminated、truncated、公开观察及状态摘要。评分器重放每个动作，核对提交内容、证据读取时机、当前版本引用、实际修订和任务单末态。中间奖励为 0；终局全部约束满足为 1。32 步耗尽与任务失败分别记录。

测试家族、处理诊断和失败或不完整的模型尝试不进入当前正向训练导出。成功轨迹内的工具失败及恢复不会被删掉。此筛选服务于正向示范；不把排除记录改写为无价值数据。

处理记录保留 84 条本轮可见事件，语法失败、定位、修复和验证互相关联。原始行摘要与冻结前缀摘要用于追溯；命令只是惰性记录。验收后补充记录单独交付，避免主包反复引用自身。

## 独立运行与验收

在公开发布包的解压目录：

    py -3 -X utf8 -B runtime_release.py verify .
    py -3 -X utf8 -B task-entrypoints/aster-routing-stale_revision-v4/tests/verify.py model/episodes/aster-routing-stale_revision-v4/episode.json
    py -3 -X utf8 -B task-entrypoints/aster-routing-stale_revision-v4/solution/reference.py ../reference-v9.json
    py -3 -X utf8 -B research_env_v4.py batch/tasks/aster-routing-stale_revision-v4/scenario.json --output ../episode-v9.json

最后一条接受逐行工具 JSON，从读取 policy 开始。模型只接收宿主公开观察；包含评价侧资料的完整包不能直接作为策略上下文。

195 项工程测试通过。独立解包执行及行为检查 20 项通过，14 类重算外围哈希的语义篡改均被拒绝。反例包括删除 429/409、伪造中间奖励、伪造剩余预算、泄露未来材料、测试数据混入训练及伪造停止原因。验收不调用模型。

主包 2,066,311 字节，SHA-256 为 `ccdf8879c035dbaa1b85bba2d4addab6b9acf4d0fc14db9a8278b70e29efafa0`。发布为 [dataset-v0.9](https://github.com/rrrrrredy/agent-trajectory-data/releases/tag/dataset-v0.9)，上一版通过 lineage.json 的标签和 SHA-256 关联，旧包未改动。

## 证据边界

新材料是合成的，执行是实际模型调用。旧版本的真实研究报告、执行记录和原失败继续保留，没有把新合成场景描述成新增真实企业记录。来源家族分离、机制共享、开发者已见素材；六条开发任务不能证明跨公司泛化、开放式研究质量或 toolkit 的因果收益。

本轮只更新公开数据集仓库。toolkit 保持 `28524448eaf6534125a24dd1ea26e986016c8aea`，没有混入数据、素材或场景代码。
