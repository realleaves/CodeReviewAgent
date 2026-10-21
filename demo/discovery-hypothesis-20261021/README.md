# P1 协议：baseline vs 假设—反例式发现（2026-10-21）

**状态：协议与 setup 已完成，尚未启动模型调用。预算 0/80。** 这一步只写实验条件和预算，实际运行需要单独执行 `run` 命令。

## 为什么做这个实验

P0 失败分类（[链接](../evidence-failure-taxonomy-20261021/README.md)）显示：

- 26 个有效参考对中，候选命中 4 个、有效证据 1 个；
- 22 个漏检中，**8 个完全没有候选**、14 个有候选但偏题；
- 真正的“候选对但证据失败”只有 3 个。

所以当前最该改的是发现阶段的工作方式。r0 的 callgraph、r1 的 thinking、r2 的输出上限都没有带来参考命中；继续加同类上下文或推理 token 不是答案。

## 假设

当前单次“广撒网”提示在不确定时返回 0 条，或报告邻近问题。改成结构化的 **理解 → 枚举 → 反例 → 核对 → 候选** 提示后，参考候选召回应提高，同时不增加修复侧同问题告警、不降低完整度。

## 设计

- 样本：r0 使用的 6 个开发样本 `tornado-1/3/7`、`youtube-dl-2/4/8`，缺陷/修复两侧，沿用 r0 的 18 个输入窗口。
- 两臂：`baseline`（当前证据审查提示）vs `hypothesis`（假设—反例式提示）。
- 唯一变量：`review_strategy`（`baseline` / `hypothesis`）。
- 固定条件：`deepseek-flash`、thinking disabled、temperature 0.1、最大输出 6000、`legacy` 上下文、每窗口最多 3 次调用。
- 重复：1 次；36 个计划窗口（18 窗口 × 2 臂）。
- 预算上限：80 次 provider 调用；失败、重试和中断全部计入，不退款。
- 范围：**只跑候选发现**，不启动测试生成/证据引擎；官方测试、补丁、参考标签和相反版本都不进入 Agent 输入。已知位置窗口，不是全仓库或新样本盲测。

## 两臂提示的差异

`baseline`：当前 `EVIDENCE_REVIEW_PROMPT`，一次调用，最多 4 条候选，可以为空。

`hypothesis`：`HYPOTHESIS_REVIEW_PROMPT`，要求模型先输出：

1. **理解**：契约、前置条件、不变量、支持输入域、错误路径、状态/资源生命周期。
2. **枚举**：3–5 个行为假设，优先 None/False/0/空列表、bytes/str、非法/边界输入、已关闭/已清理状态、协议头大小写、regex/编码、跨文件数据来源。
3. **反例**：每个假设的最小输入/调用序列 + 预期 vs 可能实际。
4. **核对**：每个保留假设至少核对一个调用方/被调用定义/文档/测试，并在 `checked` 中记录实际读了什么。
5. **候选**：只输出有具体反例和可定位契约的 findings；没有 findings 时，`checked`/`hypotheses` 仍要说明检查过什么。

结构化输出 schema：`checked`、`hypotheses`、`findings`。`findings` 仍走原有的行号校验和候选去重。

## 指标

- buggy 侧参考候选识别率（主指标）；
- fixed 侧同参考问题告警；
- 额外候选数量（不自动算误报）；
- 完整窗口数、provider 失败/中断；
- 调用次数和上报 tokens。

## 采用条件

- `hypothesis` 比 `baseline` 至少多正确识别 **2 个参考缺陷对**；
- 不增加 fixed 侧同参考问题告警；
- 不降低完整窗口数；
- 单次重复只作探索性证据；达到条件后需要重复运行或扩到 holdout 才能考虑默认采用。

## 预算与停止条件

- 开发集上限 80 次；达到上限保留已完成结果，剩余窗口标记预算耗尽。
- 如果开发集没有达到采用条件，不启动 holdout。
- 如果达到条件，另开 4 个 holdout 样本的独立 phase 和预算；不能把开发集成绩写成新样本收益。

## 资料与运行

- [完整协议](goal.json)、[setup 校验](setup.json)、[两臂配置](arms.json)、[预算](budget.json)
- 运行器：[discovery_hypothesis.py](../../evaluation/discovery_hypothesis.py)
- 公共运行设施：[discovery_experiment.py](../../evaluation/discovery_experiment.py) 的 `AttemptBudget` / `RecordedLLM`

准备（已执行，0 次调用）：

```bash
.venv/bin/python evaluation/discovery_hypothesis.py prepare \
  --output outputs/hypothesis-discovery-20261021
```

启动（尚未执行；会真实调用模型）：

```bash
ALL_PROXY= all_proxy= NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1 \
.venv/bin/python evaluation/discovery_hypothesis.py run \
  --output outputs/hypothesis-discovery-20261021
```

`ALL_PROXY`/`NO_PROXY` 是当前机器代理兼容处理；正常环境可去掉。

## 限制

- 6 个开发样本已被前几轮看过，不是盲测；成绩只说明开发集变化。
- 单次重复，模型输出有波动；单次成功不足以归因。
- 只跑发现阶段，不测量有效证据转化；如果候选召回提高，下一步再测证据阶段。
- 两臂共享上下文/模型/窗口，只隔离提示与结构化输出；不是“旧版 vs 新版”的完整对照。
- 判读仍需人工复查；额外候选不自动算误报。

## 下一步

等预算确认后执行 `run`；完成后逐窗口/逐样本判读，先在开发集比较候选识别率和固定侧告警，再决定是否扩到 holdout。不要把“假设提示产出了更多候选”当成“检出率提高”。
