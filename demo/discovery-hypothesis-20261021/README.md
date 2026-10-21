# P1 结果：baseline vs 假设—反例式发现（2026-10-21）

**状态：已运行，未达到采用条件，已否决当前假设提示。** 36/36 窗口完成，39/80 次调用。baseline 候选命中 1/6，hypothesis 0/6；hypothesis 候选更多（33 vs 29），但**没有一次真实工具读取**，`checked` 中声称的核对没有对应工具调用。默认仍为 `baseline`。

## 为什么做这个实验

P0 失败分类（[链接](../evidence-failure-taxonomy-20261021/README.md)）显示：

- 26 个有效参考对中，候选命中 4 个、有效证据 1 个；
- 22 个漏检中，**8 个完全没有候选**、14 个有候选但偏题；
- 真正的“候选对但证据失败”只有 3 个。

所以当前最该改的是发现阶段的工作方式。r0 的 callgraph、r1 的 thinking、r2 的输出上限都没有带来参考命中；继续加同类上下文或推理 token 不是答案。

## 假设

当前单次“广撒网”提示在不确定时返回 0 条，或报告邻近问题。改成结构化的 **理解 → 枚举 → 反例 → 核对 → 候选** 提示后，参考候选召回应提高，同时不增加修复侧同问题告警、不降低完整度。

**本轮结果：未支持该假设。** hypothesis 0/6，baseline 1/6；hypothesis 候选更多但没有真实工具读取。

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

## 结果

| 臂 | 候选命中 | 修复侧告警 | 成对区分 | 候选数 | 调用 | 完成窗口 | 工具读取 | completion tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 1/6 | 0 | 1/6 | 29 | 21 | 18/18 | 6 | 8,187 |
| hypothesis | 0/6 | 0 | 0/6 | 33 | 18 | 18/18 | **0** | 19,165 |

- 唯一候选命中：baseline 的 youtube-dl-4，指出函数调用 args 正则要求非空、`f()` 无参调用不匹配；匹配参考根因。
- hypothesis 在 youtube-dl-4 讨论成员调用 tuple、splice、未定义参数，没有指出无参 regex，未命中。
- 其余 5 个样本两臂都没有命中参考问题；两边修复侧都没有同参考问题告警。
- hypothesis 的候选数更多（33 vs 29），额外候选包括 tornado-1 `check_origin` Host 大小写、tornado-3 `__new__/io_loop`、tornado-7 `set_default_executor(None)` 等；这些不是参考问题，也不自动算误报。
- 预算：39/80；所有 36 个窗口完成，无 provider 失败/中断。

### 关键机制失败：`checked` 没有工具证据

- baseline 有 **6 次真实工具读取**（2 个窗口）；hypothesis **0 次**。
- hypothesis 的 `checked` 声称“读取主片段/上下文/函数定义/…”，但 `tool_reads` 为空，说明这些核对没有实际执行。
- 提示词把“核对”写成了自由文本字段，没有要求引用真实工具调用或可验证路径；模型可以只写声明就返回 JSON。
- 这解释了为什么候选更多却没有参考命中：结构化输出增加了文字量，但没有增加真实探索。completion tokens 从 8,187 增到 19,165，工具调用却从 6 降到 0。

## P1b smoke：强制真实工具证据（已运行，未采用）

P1 的 `checked` 是自报；P1b 新增 `hypothesis_tools`：首轮没有任何真实工具读取时，做一次有界修正；修正后仍无读取，则丢弃 findings 并记录 `findings_dropped=no_tool_evidence`。

- 样本：tornado-3、youtube-dl-4、youtube-dl-8；两侧各 1 个 r0 窗口；每臂 6 窗口，共 12 次运行。
- 预算：P1 已用 39/80；P1b phase 上限 41，实际 19；总 58/80。
- 同一模型/上下文/thinking/输出上限；唯一变量是 `review_strategy`（baseline vs hypothesis_tools）。

| 臂 | 有效对 | 候选命中 | 修复侧告警 | 完成/失败 | 工具读取 | 重试 | 丢弃 findings | 调用 | 候选数 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 3/3 | 0/3 | 0 | 6/0 | 2 | 0 | 0 | 7 | 16 |
| hypothesis_tools | 1/3 | 0/3 | 0 | 4/2 | 4 | 4 | 2 | 12 | 3 |

关键观察：

- 工具强制**确实增加了真实读取**：tornado-3 buggy 和 youtube-dl-8 fixed 各有 2 次读取，并保留了 findings；4 个窗口触发了一次重试。
- 但在最关键的 youtube-dl-4 buggy 窗口，重试后仍然没有工具调用，按规则 findings 被丢弃；该窗口没有命中参考问题。
- P1b 的 baseline 也没有命中 youtube-dl-4：它生成的是 `f( )` 空白参数/嵌套逗号候选，而不是参考的 `f()` 无参 regex。说明单次采样波动很大，不能用一次运行判断提示优劣。
- 两个 hypothesis_tools 窗口失败：`Hypothesis.expected_behavior` 最短 10 字符的 schema 拒绝了“越界应受控处理”“应报语法错误”这类短但合法的字符串。该 schema 已在本轮之后放宽到 1，避免未来无意义失败；这个修复不影响上面的关键窗口结论。
- 两臂都没有严格参考命中，hypothesis_tools 完成窗口更少、候选更少、调用更多；未达到采用条件。

**决定：P1b 当前实现不采用。** 理由不是“工具读取没增加”，而是：强制后仍无法让模型在关键窗口真正读工具，且严格丢弃 findings 让召回更差。下一轮如果继续工具证据方向，应采用更强的 tool-first 流程或原生 tool calling，而不是再加一次同样的文字重试。

P1b 资料：[结果](p1b-tools/results.json)、[判读](p1b-tools/adjudications.json)、[评分](p1b-tools/scores.json)、[离线校验](verify-p1b.py)。

## P1c smoke：tool-first（已运行，机械成功、性能未提升）

P1b 的“文字重试”仍可能被忽略，所以 P1c 改成两阶段：

1. **只读阶段**：模型只能返回 `[TOOL_CALL:...]`，不能返回 JSON/候选；代码执行工具。没有工具调用就直接记录 `no_tool_call`，不再进入第二阶段。
2. **假设阶段**：把真实 `tool_calls`/`tool_results` 交给假设提示，再返回 `checked`/`hypotheses`/`findings`。

样本：tornado-3、youtube-dl-4 两侧各 1 个 r0 窗口，每臂 4 窗口，共 8 次运行。P1 账本 58/80，P1c 上限 22，实际 12，总 70/80。

| 臂 | 有效对 | 候选命中 | 修复侧告警 | 完成/失败 | 工具调用 | read_code | no-tool 窗口 | 调用 | 候选数 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 2/2 | 0/2 | 0 | 4/0 | 0 | 0 | 0 | 4 | 5 |
| tool_first | 2/2 | 0/2 | 0 | 4/0 | 12 | 6 | 0 | 8 | 12 |

关键观察：

- **机械目标达成**：4/4 个 tool_first 窗口都在第一阶段执行了 3 个真实工具调用（read_code + search_symbol/search_code），0 个 no-tool 窗口；2 阶段总计每窗口 2 次模型调用，8/8 完成。
- **性能目标未达成**：两臂严格参考命中都是 0/2；修复侧告警 0。tool_first 候选更多（12 vs 5），但没有打中参考根因。
- 工具读取仍集中在主片段附近/同文件局部范围（如 `httpclient.py:286-330`、`jsinterp.py:1-36/219-280`）；没有真正去读调用方、测试或契约来源。即使强制了“调用工具”，模型仍然选择局部读码，假设仍偏邻近问题。
- 调用从 4→8，completion tokens 1,372→6,813；没有召回收益，成本明显增加。

**决定：tool-first 作为实验开关保留，但不作为默认/检出提升。** 这轮排除了“模型只是不肯用工具”的单一解释：工具执行问题已经解决，剩下的瓶颈是**读什么、如何形成正确假设**。下一轮如果继续，应改变“读什么”（例如强制读取调用方/测试/契约来源或使用静态调用图选定外部片段），而不是继续改“是否调用工具”。

P1c 资料：[结果](p1c-tool-first/results.json)、[判读](p1c-tool-first/adjudications.json)、[评分](p1c-tool-first/scores.json)、[离线校验](verify-p1c.py)。

## P1d smoke：静态外部读取（已运行，机械成功、性能未提升）

P1c 证明工具会被执行，但模型仍选主片段附近的局部读码。P1d 把“读什么”从模型选择改为**静态调用图选择**：`CallContext.supplement` 选出 caller/callee/enclosing span，代码直接 `read_code`，再把真实结果交给假设阶段。

样本：youtube-dl-2 两侧各 1 个 r0 窗口，每臂 2 窗口，共 4 次运行。P1 账本 70/80，P1d 上限 10，实际 4，总 74/80。

| 臂 | 有效对 | 候选命中 | 修复侧告警 | 完成 | 调用 | 外部调用 | read_code | no-external 窗口 | 候选数 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 1/1 | 0/1 | 0 | 2/2 | 2 | 0 | 0 | 0 | 6 |
| tool_first_external | 1/1 | 0/1 | 0 | 2/2 | 2 | 6 | 6 | 0 | 5 |

关键观察：

- **机械目标达成**：外部读取每窗口 3 个 span（caller `_extract_mpd_formats`、callee `report_warning`/`location_key`），共 6 次真实 read_code；0 个 no-external 窗口；4/4 完成。
- **性能目标未达成**：两臂仍 0/1 参考命中；模型外部读取后仍报 SegmentTimeline 越界、segment_duration=0，而不是参考的 DASH `format_id` 唯一性/合并问题。
- 外部读取让 prompt tokens 从 5,844 增到 7,804、completion 从 1,665 增到 2,593；没有召回收益。
- 这轮排除了“只是没读外部上下文”的单一解释：外部 caller/callee 已经真实读入，模型仍未形成正确假设。

**决定：P1d 不采用；P1 系列（prompt、工具重试、tool-first、外部读取）都没有产生候选召回收益。** P1 账本只剩 6 次（74/80），不再在同一方向追加采样。下一步应换假设：模型能力、任务形式（diff/PR 审查、测试引导）或更强的外部知识，而不是继续改读取协议/提示措辞。

P1d 资料：[结果](p1d-tool-external/results.json)、[判读](p1d-tool-external/adjudications.json)、[评分](p1d-tool-external/scores.json)、[离线校验](verify-p1d.py)。

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

**本轮结论：未达到。** 候选命中 0 vs 1（少 1 个），固定侧告警 0 vs 0，完整窗口 18/18 vs 18/18；没有理由采用当前 hypothesis 提示。

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

启动（已执行；结果见上）：

```bash
ALL_PROXY= all_proxy= NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1 \
.venv/bin/python evaluation/discovery_hypothesis.py run \
  --output outputs/hypothesis-discovery-20261021
```

`ALL_PROXY`/`NO_PROXY` 是当前机器代理兼容处理；正常环境可去掉。

## 结果资料

- [逐窗口结果](p1-hypothesis/results.json)、[运行前 manifest](p1-hypothesis/manifest.json)
- [逐案判读](p1-hypothesis/adjudications.json)、[评分](p1-hypothesis/scores.json)、[评分表](p1-hypothesis/scores.md)
- `p1-hypothesis/windows/`：每个窗口的初始输入、请求/响应、工具读取、候选和 trace
- [离线校验](verify.py)：36 窗口、39 次请求/响应、24 条判读、评分重算、源码冻结哈希；不调用模型/Docker

## 限制

- 6 个开发样本已被前几轮看过，不是盲测；成绩只说明开发集变化。
- 单次重复，模型输出有波动；单次结果不足以证明提示在所有样本上无效，但本轮没有达到采用条件。
- 只跑发现阶段，不测量有效证据转化；如果候选召回提高，下一步再测证据阶段。
- 两臂共享上下文/模型/窗口，只隔离提示与结构化输出；不是“旧版 vs 新版”的完整对照。
- 判读仍需人工复查；额外候选不自动算误报。

## 下一步：P1b 必须强制真实工具证据

本轮否决的是“只在提示词里要求核对、用自由文本 `checked` 自报”的实现，不是“假设—反例”这个方向本身。下一轮应做 P1b：

1. `checked`/`hypotheses` 必须引用实际工具读取（路径+行号或 call_id），并由代码对照 `index.reads` 校验；没有对应读取的声明不能作为核对依据。
2. 如果模型首轮没有发出任何工具调用，允许一次有界修正，要求它先调用工具再返回；修正计入预算，原回答保留。
3. 仍用同一模型、同一窗口、同一预算；P1b 只改“工具证据强制”这一项，不同时改上下文或 reasoning 模式。
4. 先用剩余 41 次预算在开发集做 smoke；如果工具读取确实增加、候选召回没有变差，再决定是否扩到完整 36 窗口或 holdout。

不要把“候选更多”或“`checked` 文字更多”当成召回提高；下一轮的主指标仍是参考候选识别率和固定侧告警。
