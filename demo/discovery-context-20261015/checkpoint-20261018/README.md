# 发现阶段三轮单变量对照（真实 DeepSeek，2026-10-15 至 10-18）

**结论：三轮都没有发现参考缺陷的候选增益，默认配置保持不变（legacy 上下文、thinking disabled、输出上限 6000）。** 因为没有任何可核验的发现收益，按预先约定不启动新样本验证。已查看的 6 个开发样本只用于诊断，不能写成新的召回率或泛化结论。

本报告整理 `outputs/discovery-goal-20261015/` 中已完成的 r0/r1/r2 记录。判读沿用冻结的 `evaluation/bugsinpy-rubric.json` 与未修改的 `score_pairs`，由 Codex 对照源码、候选和触发条件完成，仍待人工复查。额外候选不自动算误报，候选条数不是已证实缺陷数。

## 三轮的问题与结果

所有轮次使用现有 `deepseek-flash`、温度 0.1、每窗口最多 3 次调用、固定 6 个已漏检样本的缺陷/修复两侧、2 次重复。每轮只改变一个变量，失败和重试全部保留并计入预算。

| 轮次 | 唯一变量 | 实际尝试 | 完整窗口 | 参考缺陷命中 | 同参考问题修复版告警 | 决定 |
|---|---|---:|---:|---:|---:|---|
| r0 | 初始上下文 legacy vs callgraph | 99 | legacy 33/36；callgraph 33/36 | 0 | 0 | 无增益，默认保持 legacy |
| r1 | thinking disabled vs enabled | 119 | callgraph 31/36；thinking 17/36 | 0 | 0 | enabled 大量截断/格式失败，保持 disabled |
| r2 | thinking 输出上限 6000 vs 12000 | 146 | 6000 14/36；12000 13/36 | 0 | 0 | 提高上限没有恢复完整审查，停止调参 |

三轮合计 365 次真实 provider 尝试，未超过预先设定的 600 次总上限；剩余 235 次未使用。没有把失败或超时从分母中删除。完整窗口数不等于完整缺陷对：r1/r2 多数成对审查不完整，eligible 缺陷对只有 0–1 个，表中的 0 命中只能说明“没有观察到增益”，不能估计真实检出率或做等样本优劣比较。

### r0：调用关系上下文

- legacy：33 个完整窗口、60 次请求、47 条候选、220834 输入 tokens、20378 输出 tokens。
- callgraph：33 个完整窗口、39 次请求、39 条候选、135572 输入 tokens、12343 输出 tokens。
- 两轮重复中两种策略都没有识别 6 个参考问题；6 个窗口出现 `APIConnectionError`，全部保留。
- callgraph 的调用和 tokens 更少，但这只是成本差异，不是检出收益；它仅作为后续轮次成本更低的固定上下文。

### r1：thinking 模式

- callgraph/disabled：31/36 完整、38 次调用、41 条候选、126868 输入 tokens、11324 输出 tokens。
- thinking/enabled：17/36 完整、81 次调用、13 条候选、439458 输入 tokens、236207 输出 tokens。
- enabled 的失败主要是 16 次 `ModelResponseError`（达到 6000 completion token 上限）、2 次 `JSONDecodeError` 和 1 次网络错误；两个重复的完整缺陷对分别为 0 和 1，不能当作等样本对照。
- 参考缺陷没有命中，修复版也没有同参考问题告警。

### r2：输出预算 6000 → 12000

- thinking6000：14/36 完整、72 次调用、10 条候选行。
- thinking12000：13/36 完整、74 次调用、18 条候选行。
- 提高输出上限没有减少长度失败；`RuntimeError`/`JSONDecodeError`/`ValidationError` 仍大量出现，参考缺陷仍 0 命中。两种设置的 eligible 缺陷对分别只有 1 和 0，不能当作等样本对照。
- 最后一个计划窗口（rep2 youtube-dl-8 fixed）在 provider 请求 0365 期间进程中断：预算已扣、响应未落盘，按失败保留且未重试，不伪造结果。该窗口不影响“没有发现增益”的结论，但使 r2 的完整度更低。

## 判读边界

- 本轮只运行发现阶段，没有生成新的复现证据，不替换历史 1/26 的有效证据得分。
- 评分只针对预先选定的参考问题；额外候选没有逐条自动判真伪，也没有全局精确率。
- 失败类型是运行诊断，不是代码证据；不能把“JSON 错误减少”写成“检出率提高”。
- r1/r2 的判读文件和分数在 2026-10-18 已完成离线汇总，本文只整理既有记录，没有新增模型调用。

## 资料

- [r0 分数](r0-scores.json)、[r0 逐组判读](r0-adjudications.json)
- [r1 分数](r1-scores.json)、[r1 逐组判读](r1-adjudications.json)
- [r2 分数](r2-scores.json)、[r2 逐组判读](r2-adjudications.json)、[运行摘要](r2-operational-summary.json)
- [r2 启动前协议](r2-protocol.md)
- 完整请求/响应、初始输入、工具读取、候选与冻结源码在 `outputs/discovery-goal-20261015/`（已加入 `.gitignore`，不随仓库提交）。
- 离线校验：`python evaluation/verify_discovery_run.py outputs/discovery-goal-20261015` 核对预算账本、请求/响应配对和冻结源码；不调用模型或 Docker。

## 下一步

发现阶段的三条单变量假设都没有显示收益，继续在这 6 个已查看样本上调上下文、thinking 或输出上限缺乏依据。下一项改动转向取证阶段的**预期依据准入**：用结构化字段和确定性规则区分“语言规则解释了实际异常”与“项目契约要求不同结果”，固定正反例见 [预期准入对照](../expectation-admission-20261018/README.md)。该改动仍需在新的未参与修改样本上做模型对照，当前不能声称检出率提升。
