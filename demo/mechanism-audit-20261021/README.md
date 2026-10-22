# P2 结果：机制/排序审计未产生候选收益（2026-10-21）

**已运行并完成判读；未达到 smoke 采用条件，不扩展，默认仍为 `baseline`。** 8/8 窗口完成，12/20 次真实 DeepSeek 调用，失败 0；剩余 8 次不追加采样。本轮只测候选发现，没有运行证据引擎或 Docker。

## 对照结果

| 臂 | 有效参考对 | 候选命中 | 修复侧同参考问题告警 | 候选数 | 完成/失败窗口 | 调用 | prompt / completion tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 2/2 | 0/2 | 0 | 6 | 4/0 | 4 | 13,775 / 1,730 |
| mechanism_audit | 2/2 | 0/2 | 0 | 7 | 4/0 | 8 | 34,441 / 8,198 |
| 差值 | 0 | 0 | 0 | +1 | 0/0 | +4 | +20,666 / +6,468 |

审计执行 4 次，`removed=0`、`added=0`、`fallback_initial=1`。四次审计的原始响应均与各自初始响应完全相同。唯一 fallback 是 tornado-3 buggy 的空 findings 回退到初始空 findings，没有救回或丢弃任何候选。移除/新增计数比较 path、line、category、title，不自动代表机制改变。

采用门槛是审计臂至少 1 个严格参考候选命中、修复侧同参考问题告警不增加；本轮两臂均完整，不存在用排除失败窗口提高分数的情况。门槛未达到。调用翻倍、候选多一条不能算召回提高。

## 逐样本判读

| 样本/侧 | baseline | mechanism_audit | 对照冻结参考的判读 |
|---|---|---|---|
| tornado-3 buggy | 0 候选 | 0 候选 | 未识别 HTTPClient 析构前 weak cache entry 已清理，close 仍假定条目存在而失败 |
| tornado-3 fixed | 0 候选 | 2 候选 | loop 切换/缓存键不一致假定和 kwargs 异常类型，不是参考机制；不计同参考问题告警 |
| youtube-dl-2 buggy | 3 候选 | 2 候选 | SegmentTimeline 数量越界和 ISM 缺属性，未识别重复 Representation ID 导致格式/分片被合并覆盖 |
| youtube-dl-2 fixed | 3 候选 | 3 候选 | 时间线/URL 数量不匹配、ISM 缺属性；分片丢失症状相似但根因不同，不计参考告警 |

判读要求具体参考根因/症状与有效触发同时成立，不能只按关键词、行号或症状相似匹配。13 条额外候选逐条记录；没有做独立真实性验证，不自动算误报。判读由 Codex 对照冻结 rubric 和双版本生产代码差异完成，独立人工复查待完成，没有为判读另调 DeepSeek。

## 失败发生在哪里

本轮两个 buggy 侧都没有形成可供晋升/替换的参考假设：

- tornado-3 的初始 5 条假设讨论 `__new__`、force_instance、fetch 参数/关闭状态及 headers=None；没有析构时 weak entry 已清理的反例。
- youtube-dl-2 的初始 4 条假设讨论 SegmentTimeline 越界、零 duration、ISM Duration 和空文档；没有重复 `representation_id` / `format_id` 合并覆盖的反例。

因此可确认的是**本次端到端候选流程没有收益**；对已有正确假设时机制审计能否有效晋升的判断仍是**前提未复现/不确定**，不能写成审计机制已被证明无效。P1 轨迹中出现过的正确假设没有在这次单次采样中重现。审计没有产生新机制，也没有替换邻近候选。

对照变量为 `review_strategy`：实验臂包含假设初始提示和机制审计，baseline 使用原审查提示；不能把两臂差异解释为只隔离了第二次审计的因果效应。

## 冻结设计与运行控制

协议提交为 `3900197`，已在模型调用前提交并推送。样本固定为 youtube-dl-2（历史 promotion gap）和 tornado-3（precision gap），两侧各一个 r0 窗口，4 窗口/臂，重复 1 次。模型 `deepseek-flash`，thinking disabled，temperature 0.1，输出上限 6000，legacy 上下文，每窗口最多 3 次调用。只改变 `review_strategy`，不加入参考标签、官方测试或相反版本。

第一轮使用假设提示，第二轮根据模型自己的 hypotheses/findings 比较机制并允许替换；空审计结果按冻结实现回退到初始 findings。审计提示不含参考答案。原始请求证明两臂同侧主输入相同，审计输入仅额外带第一轮 checked/hypotheses/findings。

接手时补齐了两处运行控制：manifest 总上限读取实际账本（P2 为 20），首次 provider 连接/认证失败立即保留扣账和失败并停止；另增加源码/模型/未使用账本核对及 phase/limit 冻结检查。全部在首次请求前完成，不改变实验提示、样本或评分。预算调用前预留，SDK 自动重试关闭，失败不退款。

顶层 [budget.json](budget.json) 是准备时的 **0/20 历史快照**，供 `verify-protocol.py` 核对；最终账本是 [p2-mechanism-audit/budget.json](p2-mechanism-audit/budget.json)，为 **12/20**。没有重置 P2 账本，也没有改动 P1 的 80/80 账本或冻结文件。共享 manifest 内的采用条件文案是通用模板，本轮以冻结 [p2-goal.json](p2-goal.json) 为准，两者都不会支持本次负结果扩展。

## 资料与离线复核

交付检查：142 项 pytest 通过，Ruff F/E9 通过，P2 协议/结果及全部 P1/P1b/P1c/P1d/P1e/轨迹分析离线校验通过；仅有原先 HelloAgents/Pydantic 弃用警告。检查摘要见 [checks.json](checks.json)。

- [原始结果](p2-mechanism-audit/results.json)、[8 条判读与 13 条逐候选理由](p2-mechanism-audit/adjudications.json)、[结构化评分/差值](p2-mechanism-audit/scores.json)、[评分表](p2-mechanism-audit/scores.md)。
- [协议](p2-mechanism-audit/p2-goal.json)、[两臂](p2-mechanism-audit/arms-p2.json)、[setup](p2-mechanism-audit/setup-p2.json)、[调用前预留记录](p2-mechanism-audit/attempts.jsonl)、[结束状态](p2-mechanism-audit/completion.json)。
- `p2-mechanism-audit/windows/` 保留全部 8 条 record、输入、stdout、12 份原始请求及响应；没有 provider 失败或隐藏重试。
- `p2-mechanism-audit/implementation/` 保留调用时实现；[评分器快照](p2-mechanism-audit/scoring/discovery_mechanism_audit_score.py) 与评分一起冻结。
- [输入源码 ZIP](p2-mechanism-audit/input-sources.zip) 保留四个生产代码快照共 1,726 个 Python 文件，可离线重算 setup 摘要；官方测试不在 Agent 快照中。[评测侧参考](p2-mechanism-audit/references/) 单独保存 rubric、选定版本和生产代码差异。
- [逐文件 SHA256](artifacts-sha256.json) 覆盖协议、报告、原始记录、输入快照及冻结源码；[verify-p2.py](verify-p2.py) 离线校验请求/响应、预留顺序、判读完整性、评分重算、两臂输入一致性和源码哈希，不调用模型或 Docker。

```bash
PYTHONPATH= .venv/bin/python demo/mechanism-audit-20261021/verify-protocol.py
PYTHONPATH= .venv/bin/python demo/mechanism-audit-20261021/verify-p2.py
PYTHONPATH= .venv/bin/python evaluation/discovery_mechanism_audit_score.py \
  --phase demo/mechanism-audit-20261021/p2-mechanism-audit \
  --adjudications demo/mechanism-audit-20261021/p2-mechanism-audit/adjudications.json \
  --output /tmp/p2-rescored.json
```

## 停止与下一维度

不扩到完整 6 个开发样本或 4 个 holdout，不改默认，不把候选结果写成有效证据转化提升。本轮只有两个已见开发样本、一次重复，没有 holdout，不能声称可复现或新样本收益。

下一优先级改为**模型能力对照**，保持同一 baseline 提示/窗口/预算规则，只换模型。[草案](next-model-comparison-draft.json) 提议两次重复、最多 48 次尝试，但模型名与新预算均待用户确认；没有创建新账本或执行新调用。P1/P2 的账本均不复用，也不继续微调读取协议。本轮交付负结果后停止。
