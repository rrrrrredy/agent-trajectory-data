# 按任务读轨迹

本目录覆盖两份已发布研究归档的 4 个开发任务、80 次执行；不是整个仓库所有版本的任务清单。它把同一个任务的不同模型与条件放在一起，保留失败和正确阻塞。

[首次使用与研究发现](../START-HERE.zh-CN.md) · [v0.16 消费包说明](../DATASET-v0.16.zh-CN.md) · [全部历史资产](../PUBLIC-EVALUATIONS.zh-CN.md) · [机器可读目录](catalog.json)

任务材料为原创构造记录，轨迹来自实际模型执行。这 80 次执行均为诊断用途，不进入训练导出；[现有许可](../../LICENSE)未改变。

## 先选一个完整案例

以下页面包含全部可观察事件和最终交付文件；模型回合逐一给出归档路径，完整请求与响应需下载原包。折叠事件便于阅读，没有删除中间失败。

- [写入未知后的查询与重试](wren-write-recovery.md)：16 回合、0 次格式拒绝，最终评分 1。504 是构造环境的预设故障。基础条件已经成功，不能归功于完整示范。
- [校验通过但内容交付失败](cedar-content-failure.md)：28 回合包含 8 次格式拒绝、20 次环境动作。数值 74 正确，但最终结构缺少 success_percent 层，最终评分 0；错误输出原样保留。
- [正确阻塞与重复读取](linden-correct-block.md)：18 回合包含 2 次格式拒绝，读取同一缺失材料 5 次。最终评分 1 表示正确阻塞，不表示原业务目标已完成；单次对照不能建立因果。

## 四个任务

| 问题 | 任务 | 执行数 |
| --- | --- | ---: |
| [写入结果未知时如何恢复](#wren-delivery) | `wren-delivery` | 20 |
| [证据变化后，内容与结构是否都修正](#cedar-pilot) | `cedar-pilot` | 20 |
| [关键材料缺失时是否正确阻塞](#linden-retention) | `linden-retention` | 20 |
| [结论不变时，是否仍修正基础数据](#harbor-backlog) | `harbor-backlog` | 20 |

A/B/C 分别为基础说明、短经验摘要、完整示范；N/E 为另一轮修复接口后的无格式示例／单个 JSON 示例。只在同一轮内比较；跨轮差异不能直接归因于示范长度。输入 token 是供应商上报口径，不是统一货币成本。

## wren-delivery

**写入结果未知时如何恢复。** 观察同一 operation_id 的查询与重试，以及两份交付件的最终一致性。

| 研究 | 模型 | 条件 | 最终评分 | 交付状态 | 回合 | 格式拒绝 | 环境动作 | 输入 token | 完整案例 |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| format | deepseek | E | 1 | ready | 19 | 2 | 17 | 53,625 | 见原归档 |
| format | deepseek | N | 1 | ready | 20 | 1 | 19 | 53,937 | 见原归档 |
| format | glm | E | 1 | ready | 19 | 3 | 16 | 44,565 | 见原归档 |
| format | glm | N | 1 | ready | 19 | 1 | 18 | 47,456 | 见原归档 |
| format | kimi | E | 1 | ready | 17 | 0 | 17 | 42,111 | 见原归档 |
| format | kimi | N | 1 | ready | 17 | 1 | 16 | 38,526 | 见原归档 |
| format | longcat | E | 1 | ready | 28 | 11 | 17 | 77,746 | 见原归档 |
| format | longcat | N | 1 | ready | 21 | 5 | 16 | 53,705 | 见原归档 |
| usefulness | deepseek | A | 1 | ready | 23 | 7 | 16 | 51,115 | 见原归档 |
| usefulness | deepseek | B | 1 | ready | 27 | 10 | 17 | 70,300 | 见原归档 |
| usefulness | deepseek | C | 1 | ready | 18 | 1 | 17 | 171,303 | 见原归档 |
| usefulness | glm | A | 1 | ready | 18 | 2 | 16 | 39,085 | 见原归档 |
| usefulness | glm | B | 1 | ready | 17 | 1 | 16 | 41,983 | 见原归档 |
| usefulness | glm | C | 1 | ready | 17 | 1 | 16 | 150,584 | 见原归档 |
| usefulness | kimi | A | 1 | ready | 16 | 0 | 16 | 35,622 | [打开](wren-write-recovery.md) |
| usefulness | kimi | B | 1 | ready | 17 | 1 | 16 | 40,666 | 见原归档 |
| usefulness | kimi | C | 1 | ready | 16 | 0 | 16 | 141,693 | 见原归档 |
| usefulness | longcat | A | 1 | ready | 20 | 4 | 16 | 46,933 | 见原归档 |
| usefulness | longcat | B | 1 | ready | 31 | 15 | 16 | 84,161 | 见原归档 |
| usefulness | longcat | C | 1 | ready | 16 | 0 | 16 | 155,301 | 见原归档 |

原记录位置：各归档的 `data/<研究目录>/runs/<provider>/wren-delivery-<condition>/`；每条精确路径也保留在 catalog.json。

## cedar-pilot

**证据变化后，内容与结构是否都修正。** 区分新数据读取、保护文字恢复、公开校验和最终内容评分。

| 研究 | 模型 | 条件 | 最终评分 | 交付状态 | 回合 | 格式拒绝 | 环境动作 | 输入 token | 完整案例 |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| format | deepseek | E | 1 | ready | 17 | 1 | 16 | 42,627 | 见原归档 |
| format | deepseek | N | 1 | ready | 25 | 5 | 20 | 74,416 | 见原归档 |
| format | glm | E | 1 | ready | 23 | 3 | 20 | 63,206 | 见原归档 |
| format | glm | N | 1 | ready | 29 | 5 | 24 | 99,149 | 见原归档 |
| format | kimi | E | 1 | ready | 18 | 0 | 18 | 49,025 | 见原归档 |
| format | kimi | N | 1 | ready | 18 | 0 | 18 | 44,386 | 见原归档 |
| format | longcat | E | 1 | ready | 32 | 15 | 17 | 113,107 | 见原归档 |
| format | longcat | N | 0 | ready | 28 | 8 | 20 | 78,996 | [打开](cedar-content-failure.md) |
| usefulness | deepseek | A | 1 | ready | 25 | 5 | 20 | 64,909 | 见原归档 |
| usefulness | deepseek | B | 1 | ready | 24 | 7 | 17 | 60,886 | 见原归档 |
| usefulness | deepseek | C | 1 | ready | 22 | 2 | 20 | 222,980 | 见原归档 |
| usefulness | glm | A | 1 | ready | 23 | 3 | 20 | 59,638 | 见原归档 |
| usefulness | glm | B | 1 | ready | 22 | 5 | 17 | 54,303 | 见原归档 |
| usefulness | glm | C | 1 | ready | 19 | 2 | 17 | 172,848 | 见原归档 |
| usefulness | kimi | A | 1 | ready | 17 | 0 | 17 | 41,399 | 见原归档 |
| usefulness | kimi | B | 1 | ready | 16 | 0 | 16 | 40,265 | 见原归档 |
| usefulness | kimi | C | 1 | ready | 16 | 0 | 16 | 141,934 | 见原归档 |
| usefulness | longcat | A | 1 | ready | 24 | 6 | 18 | 62,572 | 见原归档 |
| usefulness | longcat | B | 1 | ready | 20 | 4 | 16 | 51,240 | 见原归档 |
| usefulness | longcat | C | 1 | ready | 19 | 2 | 17 | 188,152 | 见原归档 |

原记录位置：各归档的 `data/<研究目录>/runs/<provider>/cedar-pilot-<condition>/`；每条精确路径也保留在 catalog.json。

## linden-retention

**关键材料缺失时是否正确阻塞。** 观察是否保留未解决交付件，并检查对同一缺失材料的重复读取。

| 研究 | 模型 | 条件 | 最终评分 | 交付状态 | 回合 | 格式拒绝 | 环境动作 | 输入 token | 完整案例 |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| format | deepseek | E | 1 | blocked | 14 | 2 | 12 | 29,216 | 见原归档 |
| format | deepseek | N | 1 | blocked | 15 | 3 | 12 | 29,875 | 见原归档 |
| format | glm | E | 1 | blocked | 13 | 1 | 12 | 25,704 | 见原归档 |
| format | glm | N | 1 | blocked | 10 | 0 | 10 | 17,227 | 见原归档 |
| format | kimi | E | 1 | blocked | 9 | 0 | 9 | 14,878 | 见原归档 |
| format | kimi | N | 1 | blocked | 12 | 1 | 11 | 20,898 | 见原归档 |
| format | longcat | E | 1 | blocked | 15 | 5 | 10 | 30,668 | 见原归档 |
| format | longcat | N | 1 | blocked | 12 | 2 | 10 | 22,014 | 见原归档 |
| usefulness | deepseek | A | 1 | blocked | 14 | 4 | 10 | 22,643 | 见原归档 |
| usefulness | deepseek | B | 1 | blocked | 24 | 13 | 11 | 47,428 | 见原归档 |
| usefulness | deepseek | C | 1 | blocked | 10 | 0 | 10 | 87,515 | 见原归档 |
| usefulness | glm | A | 1 | blocked | 13 | 1 | 12 | 23,893 | 见原归档 |
| usefulness | glm | B | 1 | blocked | 14 | 0 | 14 | 30,174 | 见原归档 |
| usefulness | glm | C | 1 | blocked | 18 | 2 | 16 | 154,761 | [打开](linden-correct-block.md) |
| usefulness | kimi | A | 1 | blocked | 10 | 0 | 10 | 16,500 | 见原归档 |
| usefulness | kimi | B | 1 | blocked | 11 | 1 | 10 | 19,515 | 见原归档 |
| usefulness | kimi | C | 1 | blocked | 10 | 0 | 10 | 82,599 | 见原归档 |
| usefulness | longcat | A | 1 | blocked | 18 | 7 | 11 | 32,619 | 见原归档 |
| usefulness | longcat | B | 1 | blocked | 16 | 6 | 10 | 29,396 | 见原归档 |
| usefulness | longcat | C | 1 | blocked | 11 | 1 | 10 | 99,935 | 见原归档 |

原记录位置：各归档的 `data/<研究目录>/runs/<provider>/linden-retention-<condition>/`；每条精确路径也保留在 catalog.json。

## harbor-backlog

**结论不变时，是否仍修正基础数据。** 核对已关闭数量和剩余积压，不能因队列结论未变就保留错误数值。

| 研究 | 模型 | 条件 | 最终评分 | 交付状态 | 回合 | 格式拒绝 | 环境动作 | 输入 token | 完整案例 |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| format | deepseek | E | 1 | ready | 20 | 1 | 19 | 57,840 | 见原归档 |
| format | deepseek | N | 1 | ready | 23 | 3 | 20 | 67,187 | 见原归档 |
| format | glm | E | 1 | ready | 22 | 2 | 20 | 62,448 | 见原归档 |
| format | glm | N | 1 | ready | 19 | 2 | 17 | 50,184 | 见原归档 |
| format | kimi | E | 1 | ready | 19 | 1 | 18 | 47,917 | 见原归档 |
| format | kimi | N | 1 | ready | 18 | 1 | 17 | 41,239 | 见原归档 |
| format | longcat | E | 1 | ready | 27 | 9 | 18 | 86,557 | 见原归档 |
| format | longcat | N | 1 | ready | 48 | 30 | 18 | 195,405 | 见原归档 |
| usefulness | deepseek | A | 1 | ready | 23 | 6 | 17 | 54,630 | 见原归档 |
| usefulness | deepseek | B | 1 | ready | 29 | 12 | 17 | 80,383 | 见原归档 |
| usefulness | deepseek | C | 1 | ready | 22 | 4 | 18 | 212,885 | 见原归档 |
| usefulness | glm | A | 1 | ready | 20 | 3 | 17 | 46,589 | 见原归档 |
| usefulness | glm | B | 1 | ready | 20 | 3 | 17 | 51,274 | 见原归档 |
| usefulness | glm | C | 1 | ready | 17 | 0 | 17 | 154,230 | 见原归档 |
| usefulness | kimi | A | 1 | ready | 16 | 0 | 16 | 36,889 | 见原归档 |
| usefulness | kimi | B | 1 | ready | 16 | 0 | 16 | 41,133 | 见原归档 |
| usefulness | kimi | C | 1 | ready | 16 | 0 | 16 | 142,841 | 见原归档 |
| usefulness | longcat | A | 1 | ready | 28 | 10 | 18 | 70,453 | 见原归档 |
| usefulness | longcat | B | 1 | ready | 23 | 5 | 18 | 63,404 | 见原归档 |
| usefulness | longcat | C | 1 | ready | 19 | 2 | 17 | 187,659 | 见原归档 |

原记录位置：各归档的 `data/<研究目录>/runs/<provider>/harbor-backlog-<condition>/`；每条精确路径也保留在 catalog.json。

## 下载与筛选

[用途实验原包](https://github.com/rrrrrredy/agent-trajectory-data/releases/download/study-2026-09-29/workspace-usefulness-20260929.zip) · [格式实验原包](https://github.com/rrrrrredy/agent-trajectory-data/releases/download/format-study-2026-09-29/workspace-format-20260929.zip)

在仓库根目录运行，路径替换为实际解压位置：

```sh
python -X utf8 examples/read_study.py ../format/data/format-study-20260929 --task cedar-pilot --provider longcat --condition N
python -X utf8 scripts/build_reading_index.py --usefulness-root ../usefulness/data/usefulness-study-20260929 --format-root ../format/data/format-study-20260929 --output ../rebuilt-reading-index
```

目录由原 results.json 汇总，案例由原 episode.json、summary.json、calls 和 deliverables 生成，不重新调用模型或评审。生成输入的哈希见 catalog.json；输出目录须为空，避免覆盖阅读笔记。
