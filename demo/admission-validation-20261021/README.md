# 准入固定案例验证（2026-10-21）

**结论：结构化准入在 4 个已见固定案例上保留了文档正例，并把 3 个语言规则负例降级；总调用 5 次。** 这不是新样本检出率，也不是全局精确率；样本是 2026-10-14 已看过的候选，历史旧判定作为参考，不是重新采样的成对基线。

## 运行条件

- 模型：`deepseek-flash`，thinking disabled，temperature 0.1，最大输出 6000 tokens。
- 样例：4 个冻结候选（候选、源码窗口和执行镜像来自 2026-10-14 报告）。
- 流程：模型重新生成计划与测试 → 两次隔离 Docker → `requirement_gate` → 通过后才调用 `audit_gate`。
- 预算：上限 24 次，实际 5 次；每次请求先扣预算，失败不退款。
- 官方测试、参考补丁、标签和相反版本均未提供给 Agent。
- 源码冻结哈希、模型配置和逐案结果见 [protocol.json](protocol.json)、[summary.json](summary.json)、[results.json](results.json)。

## 结果

| 案例 | 模型计划 | 实际执行 | 准入结果 | 调用 | 容器 |
|---|---|---|---|---:|---:|
| PySnooper-3（文档正例） | `documented_behavior`，state_change | 两次 NameError，目标行触达 | requirement + audit 全通过，`reproduced` | 2 | 2 |
| tornado-1 fixed（负例） | 模型直接返回 `applicable=false` | 未执行 | `unsupported`，说明“语言规则不能要求 ValueError” | 1 | 0 |
| youtube-dl-4 fixed（负例） | 模型直接返回 `applicable=false` | 未执行 | `unsupported`，说明“没有契约要求 ExtractorError” | 1 | 0 |
| youtube-dl-8 buggy（负例） | `language_rule`，要求 SyntaxError | 两次 AttributeError，目标行触达 | 确定性门控拒绝：语言规则只能解释 AttributeError；`contract_unconfirmed`，未花审计调用 | 1 | 2 |

合计：**5 次 provider 调用、4 次容器执行**。PySnooper-3 的两次执行都是 `failure_observed`，审计的 6 项检查全部为 true；youtube-dl-8 的测试确实触达目标并复现了 `AttributeError`，但它的预期 `SyntaxError` 没有文档/测试依据，因此不进入正式缺陷。

## 这证明了什么

1. **文档正例没有被新门控误杀。** PySnooper-3 同时通过确定性准入和结构化审计，仍为 `reproduced`。
2. **新提示让模型在计划阶段就拒绝无依据预期。** tornado-1 fixed 与 youtube-dl-4 fixed 都返回 `applicable=false`，没有消耗执行和审计调用。
3. **确定性门控能拦截“语言规则要求另一种异常”。** youtube-dl-8 的实际异常是 `AttributeError`，模型要求 `SyntaxError`；`requirement_gate` 在审计前拒绝，状态为 `contract_unconfirmed`。
4. **成本可控。** 4 个案例只花 5 次调用；相比历史上 4 个案例都被接受、还需要执行与审计，这一轮的主要节省来自“计划阶段拒绝”和“审计前确定性拒绝”。

## 不能从这轮推出的结论

- **样本是已看过的固定案例**，不是新样本盲测；不能据此声称检出率、召回率或全局精确率提升。
- **没有重新采样旧基线。** 历史旧判定（4 个都曾是 `reproduced`）只作为参考；旧计划使用旧提示词，不是同一批新采样的成对对照。
- **单次重复，模型输出会有波动。** 两个 `unsupported` 是本次模型判断；不能保证每次都会这样回答。
- **可能误杀真实问题。** youtube-dl-8 的底层 `AttributeError` 看起来是真实问题，但“应抛 SyntaxError”只是源码一致性推断，没有文档/测试承诺；新门控把它降级为待确认，是保守取舍，不等于问题不存在。
- **没有验证新样本上的证据转化。** 下一步仍需在未参与修改的样本上跑 baseline vs admission，比较 `reproduced` 数、自动接受判真率、被降级但实为真缺陷的数量、调用/tokens。

## 运行环境注意

本机当前沙箱的 Docker daemon 看不到 `/tmp` 下的临时 bind mount，直接运行会报：

```text
bind source path does not exist: /tmp/code-review-evidence-.../work
```

这是环境挂载问题，不是测试内容问题。把 `TMPDIR` 指到工作区内即可：

```bash
mkdir -p outputs/admission-validation-tmp
ALL_PROXY= all_proxy= \
NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1 \
TMPDIR="$PWD/outputs/admission-validation-tmp" \
.venv/bin/python evaluation/admission_validation.py \
  --limit 24 --output outputs/admission-validation-20261021-clean
```

`ALL_PROXY` / `NO_PROXY` 的两行是当前机器代理配置的兼容处理；正常情况下不需要。第一次诊断运行确实发过 5 次请求（其中 PySnooper-3 和 youtube-dl-8 因挂载失败为 `environment_failed`），单跑正例又用了 2 次，最终干净重跑用 5 次；**三轮合计 12 次，全部有请求/响应或失败记录**。本目录的 `summary.json` 只统计最终干净运行的 5 次。

## 复核

离线校验不调用模型、不启动 Docker：

```bash
python demo/admission-validation-20261021/verify.py
```

校验内容：4 个案例、5 次请求/响应配对、预算账本、正例/负例状态、PySnooper-3 的审计字段全 true、youtube-dl-8 的确定性拒绝、逐文件附件哈希和源码冻结哈希。

## 资料

- [协议与源码哈希](protocol.json)、[汇总](summary.json)、[逐案结果](results.json)、[预算](budget.json)
- `cases/<案例>/`：`result.json`、`finding.json`、`calls.json`、`trace.json`、`requests/`、`artifacts/`
- [离线校验脚本](verify.py)
- 相关实现：[admission_validation.py](../../evaluation/admission_validation.py)、[reproduction.py](../../src/reproduction.py:194)、[schemas.py](../../src/schemas.py:72)

## 下一步

1. 用同一门控在**未参与修改的新 evidence 样本**上做 baseline vs admission 成对运行；当前 4 个案例只证明“固定正反例行为”，不能证明泛化。
2. 评估是否把 youtube-dl-8 这类“源码一致性支持但无明文契约”的候选保留为 `pending_evidence` 并交由维护者查看；当前门控的选择是保守降级。
3. 如果新样本仍无证据收益，再回到候选发现瓶颈（native tool 协议或提示结构），不要重复已证明无增益的上下文/thinking/输出预算实验。
