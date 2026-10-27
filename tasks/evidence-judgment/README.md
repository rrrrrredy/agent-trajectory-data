# 两个需要判断证据的开发任务

这里提供两份可以直接交给 Agent 的任务：从已有实验判断宣传说法，及在证据不足时选择可用的编辑数据。材料来自我们实际发布的项目记录；任务情境和待审文案为本次编写，不是客户请求或生产任务日志。

与历史四题给定公式、输出字段和判定阈值不同，这两题要求区分相互关联的数字、方法条件和结论，再交付能使用的建议。它们增加了两种判断要求，尚未证明难度、区分度或真实业务代表性。

| 任务 | 要交付什么 | 输入 | 评阅者材料 |
| --- | --- | --- | --- |
| `study-claims` | 修订研究宣传稿、逐项证据判断、最小后续比较 | [题目](study-claims/input/TASK.md) | [参考判断与典型错误](study-claims/review.md) |
| `editorial-selection` | 本周能执行的数据使用方案、可发布说明、补证据计划 | [题目](editorial-selection/input/TASK.md) | [参考判断与典型错误](editorial-selection/review.md) |

## 直接使用

在仓库根目录运行，Python 3.10+、仅标准库，不调用模型：

```sh
python -X utf8 examples/export_judgment_task.py study-claims --output ../study-claims-input
python -X utf8 examples/export_judgment_task.py editorial-selection --output ../editorial-selection-input
```

将导出目录单独交给 Agent，从 `TASK.md` 开始。导出包含题目、证据、来源与许可，**不包含 `review.md`**；输出目录必须不存在。只有这个目录作为工作区，并关闭网络和其他仓库访问，才有机会避免任务期间查到参考判断；普通文件复制本身不提供权限隔离。同一用户可读全盘时不声称实现盲评。

完成后，评阅者对照对应 `review.md`，逐项记录“支持／部分支持／不支持／无法判断”和候选原句。先按证据评阅，再看参考答案；不同但有依据的取舍可以成立，不按参考措辞匹配。自动格式检查不能代替语义评阅，也不输出一个未经校准的总分。

## 来源、身份和结果状态

两题均为 `development`，`training_eligible=false`；没有模型执行记录、通过率、独立裁判或训练结果。参考判断和典型错误均为本次作者模型编写，后者不是实际模型失败。未来执行另行保留完整输入、原始输出、具体模型与日期、用量及评阅分歧，不能回写成历史 80 次执行的一部分。

来源版本、Git blob SHA-256、选取位置在每题 `input/sources.json`。`study-claims` 的两轮记录复用相同四个开发任务；`editorial-selection` 的统计、文章案例、标注来源同属一个项目。两题的材料也都来自同一维护者的项目组合。不得按文件数、视图数或候选数增加独立任务和来源的计数；公开任务及参考判断不构成未见保留集。

目录按使用者分开：`input/` 给求解者，旁边的 `review.md` 给评阅者；历史运行索引仍在 [docs/tasks](../../docs/tasks/README.md)，原发布包和研究不搬动。任务包不加入旧的标量字段自动评分器。

本仓库原创任务和 Agent 材料继续遵循根目录 [LICENSE](../../LICENSE)，没有新增开放训练或再分发授权。第二题的 Editorial Guard 材料另按其 CC BY 4.0 许可标示来源、署名与改动；该许可不会被本仓库条款收紧，也不扩展到本仓库其他内容。详情见该题 `input/NOTICE.md`。
