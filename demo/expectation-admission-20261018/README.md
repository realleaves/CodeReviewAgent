# 预期依据准入：实现与固定正反例离线对照（2026-10-18）

**改动目标：正式 `reproduced` 不再只靠模型一句 `accepted=true`。** 新增结构化预期字段和确定性准入规则，专门处理 2026-10-15 复测暴露的两类问题：语言规则只能解释实际异常，却被用来要求另一种结果；以及只约束错误消息文案的“缺陷”。本轮 0 次模型 API 调用、0 次 Docker 执行，没有新的检出率结论。

## 改了哪里

- `ContractReference` 新增可选字段：`expected_outcome`（exception/return_value/state_change/output/error_message/unspecified）、`expected_exception`、`precondition`、`assumptions`。旧证据缺少这些字段仍可解析和复跑。
- 新生成的复现计划必须先过 `validate_requirement`：必须说明预期结果类型、触发前提；异常类预期必须给出异常名；`error_message` 直接拒绝，因为文案不属于行为缺陷；`unspecified` 不再被当作有效预期。
- 两次执行都触达目标后，先过 `requirement_gate`，再决定是否花一次审计调用：
  - 语言规则 + 非异常预期 → 拒绝；返回值/状态/输出需要文档或既有测试。
  - 语言规则 + 异常预期，但实际观察到的是另一种异常 → 拒绝；语言规则解释的是实际异常，不能反推“应抛另一种异常”。
  - 语言规则 + 异常预期，且代码没有抛出该异常（测试因断言失败）→ 允许进入语义审计。
  - `error_message` → 拒绝。
  - 文档/既有测试契约不受这条确定性限制，仍由审计判断。
- 审计 `EvidenceDecision` 新增结构化字段：`input_supported`、`requirement_supported`、`failure_matches_candidate`、`requirement_class`、`unresolved_assumptions`。`audit_gate` 重新检查：任一为 false、缺失（None）、类别为 `diagnostic_quality` 或存在未决假设，即使模型写 `accepted=true`，也只保留为 `pending_evidence`，不进入正式缺陷。
- 所有判定都写入 `reproduction.admission`，包括确定性门控和审计检查的逐项结果，便于复查。

改动文件：`src/schemas.py`、`src/reproduction.py`、`tests/test_evidence.py`；新增离线对照脚本 `evaluation/expectation_controls.py`。

## 固定正反例对照

用 2026-10-15 复测的 13 条历史自动接受记录，原计划、原执行日志和原判读全部冻结。旧计划没有新字段，因此脚本按每条计划自身的文本和当时的逐条判读，固定标注 `expected_outcome`/`expected_exception`，再运行新的确定性 `requirement_gate`。这是策略对照，不是重新采样模型。

结果：**13 条中只有 PySnooper-3 进入语义审计，12 条被降级为待确认，不再自动成为正式缺陷。**

| 类别 | 数量 | 记录 |
|---|---:|---|
| 通过确定性门控，进入审计 | 1 | PySnooper-3（文档明确承诺 output_path 文件输出） |
| 仅错误消息文案 | 1 | tornado-1 buggy（`ValueError` 的 `%r` 格式化） |
| 语言规则解释实际异常，却要求另一种异常 | 7 | tornado-1 fixed（KeyError→ValueError）、youtube-dl-4 fixed（ValueError→ExtractorError）、youtube-dl-8 五条（AttributeError→SyntaxError） |
| 语言规则被用来证明返回值/状态/输出 | 4 | PySnooper-1、youtube-dl-6 fixed、youtube-dl-9 buggy、youtube-dl-12 buggy |

逐条结果和原因见 [controls.json](controls.json)。复现命令：

```bash
PYTHONPATH= .venv/bin/python evaluation/expectation_controls.py \
  --output demo/expectation-admission-20261018/controls.json
```

脚本会断言只放行 `9261f543fc85`，且总数保持 13；不调用模型，不运行 Docker。

## 怎么解读这 12 条降级

- **不是把 12 条判成误报。** 它们仍保留原测试、日志、执行记录和候选，只是在正式报告里从 `reproduced` 变为 `pending_evidence`，并附带具体缺失的契约类型。
- 其中 youtube-dl-8 的五条有源码一致性支持，2026-10-15 判读也标为“待维护者确认”；新规则把“需要文档/测试才能升级”的要求落到代码里，而不是继续依赖模型口头接受。
- PySnooper-3 是唯一有明文文档承诺的正例，保持通过；youtube-dl-12 原本已被执行位置判定拦住，这次预期门控也独立拒绝，两个层次不互相替代。
- 代价是可能降低正式 `reproduced` 数量，并让一些真实但缺少文档的缺陷停留在待确认。这是有意的保守取舍：宁可让维护者看到“缺什么依据”，不把语言规则解释当成项目契约。

## 验证

- `PYTHONPATH= .venv/bin/python -m pytest -q tests`：107 passed。
- `PYTHONPATH= .venv/bin/python -m ruff check --isolated --select F,E9 main.py src tests evaluation`：通过。
- 改动文件 `ruff format --check`：通过。
- 本轮没有模型调用或容器执行；没有重跑 72 次测评、没有改历史 1/26 得分、没有改评分器或参考 rubric。
- 旧证据复跑路径不受影响：`replay_evidence` 仍只做原有结构校验，不会因为旧计划缺少新字段而拒绝。

## 限制与下一步

这次只验证了确定性准入策略在固定历史记录上的行为，不能证明：

- 模型在新提示下会稳定产出合格的 `expected_outcome`/`precondition`；
- 新规则会提高真实缺陷检出，或降低新样本上的误接受；
- 被降级的 12 条里哪些其实是真缺陷。

下一步必须用同一模型、同一提示词、同一预算，在未参与修改的新样本上做成对运行，分别报告：进入审计数、正式 `reproduced` 数、自动接受证据的人工判真率、被降级但实为真缺陷的数量、调用/tokens。只有在固定正例仍通过、错误接受下降且真实缺陷不明显减少时，才考虑把该准入设为默认；否则如实回退。
