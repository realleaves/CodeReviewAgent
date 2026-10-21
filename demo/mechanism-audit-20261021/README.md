# P2 协议：候选机制/排序审计（2026-10-21，已准备，未运行）

**状态：协议和 20 次预算已落盘，0 次模型调用，尚未执行。** 这是针对 [P1 轨迹分析](../discovery-trace-analysis-20261021/README.md) 的下一步单变量实验。

## 依据

轨迹分析把 6 个开发样本分为：

- 1 个 hit（youtube-dl-4 baseline）；
- 1 个 **promotion gap**（youtube-dl-2：P1 hypothesis 已写重复 `representation_id` 覆盖 fragments，并给具体反例，但没有输出成 finding）；
- 3 个 **precision gap**（tornado-3、tornado-7、youtube-dl-8：参考概念/邻近机制已在 reasoning 或 findings，但模型选了另一个机制）；
- 1 个 discovery gap（tornado-1）。

因此 P2 不再改工具、读取对象或提示结构，只改“候选机制比较/替换”这一步。

## 设计

- 样本：`youtube-dl-2`（promotion gap）+ `tornado-3`（precision gap），两侧各 1 个 r0 窗口；每臂 4 窗口，共 8 次运行。
- 两臂：`baseline` vs `mechanism_audit`。
- 唯一变量：`review_strategy`。
- 固定条件：`deepseek-flash`、thinking disabled、temperature 0.1、最大输出 6000、`legacy` 上下文、每窗口最多 3 次调用。
- 重复：1 次；预算 20 次，新账本；失败/重试全部计入，不退款。
- 范围：只跑候选发现，不启动证据引擎；官方测试/标签/相反版本不进入 Agent 输入。

## mechanism_audit 做什么

1. 第一轮仍用 P1 的假设提示，产生 `checked`/`hypotheses`/`findings`；
2. 第二轮审计拿到第一轮的 `initial_checked`/`initial_hypotheses`/`initial_findings`，要求：
   - 对每条 initial finding，指出它对应哪条 hypothesis、具体反例和契约违反；
   - 比较所有 hypothesis；如果另一条的反例更具体、契约违反更直接，而当前 finding 只是邻近问题/较弱机制，就**替换**它；
   - 最终 findings 只保留机制依据最强的候选，最多 4 条；不为了数量保留邻近问题；
   - 不编造 initial hypotheses 中没有的反例；现有 findings 已是最强则原样返回。
3. 审计提示**不包含参考标签/参考问题文本**，只使用模型自己的假设和代码；
4. 如果审计返回空 findings，代码回退到第一轮 findings，并记录 `fallback_initial=true`；否则以审计结果作为最终候选，并记录 `removed`/`added`。

## 判读

- 主指标：`youtube-dl-2` 和 `tornado-3` 的参考候选命中；修复侧同参考问题告警。
- 次指标：`removed`/`added` 数量、`fallback_initial`、完成窗口、调用/tokens。
- 采用条件：mechanism_audit 在这两个样本上至少产生 1 个参考候选命中，且修复侧告警不增加；4 窗口 smoke，只作探索性证据，不能据此宣称整体召回提高。
- 如果审计没有替换/命中，或第一轮没有复现必要假设（P1e 的教训），如实记录为负结果或不结论。

## 预算与停止条件

- 新账本上限 20 次；到达上限保留已完成结果。
- 没有达到采用条件，不扩到完整 6 个开发样本或 holdout。
- 不把 smoke 的命中写成新样本收益；不做跨 benchmark 比较。

## 运行（用户已授权 20 次；提交协议后执行）

接手核查后补齐运行控制：运行前核对已准备的源码哈希、模型配置和未使用账本；拒绝更改 smoke 的 phase/limit；首次 provider 连接/认证失败即保存记录并停止。manifest 的总上限从实际账本读取，P2 为 20，原先通用运行器写死的 600 已纠正。这些修正不改变审查提示、样本、评分规则或默认策略；全部在首次模型请求前冻结。

准备（已执行，0 次调用）：

```bash
PYTHONPATH= .venv/bin/python evaluation/discovery_mechanism_audit.py prepare
```

启动（尚未执行；会真实调用模型）：

```bash
ALL_PROXY= all_proxy= NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1 \
PYTHONPATH= .venv/bin/python evaluation/discovery_mechanism_audit.py run
```

## 资料

- [协议](p2-goal.json)、[两臂配置](arms-p2.json)、[setup 校验](setup-p2.json)、[预算](budget.json)
- 运行器：[discovery_mechanism_audit.py](../../evaluation/discovery_mechanism_audit.py)
- 离线校验：[verify-protocol.py](verify-protocol.py)：4 窗口、2 样本、20/0 预算、源码哈希；不调用模型

## 限制

- 单次重复；模型波动大，P1e 已出现“P1 的参考假设未复现”；如果 P2 第一轮没有形成可替换的假设，审计无法发挥。
- 只测 2 个开发样本，不是完整开发集/holdout。
- 关键词/判读仍需人工复核；额外候选不自动算误报。
