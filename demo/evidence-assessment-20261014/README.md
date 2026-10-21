# CodeReviewAgent 复现证据版测评（2026-10-14）

**结论：流程可以跑通，真实缺陷检出与证据核验仍不可靠。** 当前证据版在26个有效缺陷对中，仅1个已知缺陷获得有效的Agent生成复现证据（3.8%）；新8对是0/8。发现一条模型误认可的错误证据。

72次审查、434次现有 DeepSeek `deepseek-flash` 调用，全部原始报告与失败记录保留。没有为本次成绩修改源码、提示词、预算规则或已有评分器。

## 分数

| 样本 / 模式 | 计划 / 有效缺陷对 | 已知问题候选识别 | 有效生成证据命中 | 修复版同一已知问题告警 |
|---|---:|---:|---:|---:|
| 原20个 / evidence | 20 / 18 | 3/18 (16.7%) | 1/18 (5.6%) | 0 |
| 新8个 / direct | 8 / 7 | 1/7 (14.3%) | 不生成测试 | 0 |
| 新8个 / evidence | 8 / 8 | 1/8 (12.5%) | 0/8 (0.0%) | 0 |

候选识别与有效运行证据是两个指标，不能直接对比为能力提升。参考补丁定位窗口已提前给定；这不是从全仓库自主寻找缺陷，也不是官方排行榜成绩。判读为 Codex 模型辅助参考核对，仍待人工复查。修复版“同一参考问题”告警为0，不代表所有额外候选都正确或全局误报率为0。

候选匹配需要参考根因/症状与有效触发输入。youtube-dl-11 找到了整数输入的 TypeError，但错误主张返回 None，因此只计症状识别；youtube-dl-12 证据版虽指出 lambda 根因，却用错输入、走错分支，不计严格候选命中。direct 对 youtube-dl-12 的正确候选单列保留，因修复版请求超时，不纳入该模式成对分母。

## 一个有效命中

[PySnooper-3 原始审查报告](valid-hit/agent-report/report.html)：`get_write_function` 的文件输出闭包引用未定义的 `output_path`，实际 `@snoop(path)` 调用抛出 NameError。原Agent测试两次失败；独立运行同一未改测试，缺陷版失败、修复版通过，0次模型调用。

- [生成测试](valid-hit/agent-report/evidence/9261f543fc85/test_reproduction.py)
- [原始证据与两次执行](valid-hit/agent-report/evidence/9261f543fc85/evidence.json)
- [缺陷 / 修复独立对照](valid-hit/controls/original-test-control/control.json)

## 一个错误证据

[youtube-dl-12 原始审查报告](invalid-evidence/agent-report/report.html)仍保留Agent当时的 reproduced 标签，供核查，**该标签已被本次评测否定**。参考问题的合法否定过滤器是 `ext!=mp4`；Agent生成的是 `!ext=mp4`。regex 搜索忽略前面的 `!`，匹配普通 `ext=mp4`，没有执行错误的否定 lambda。

| 测试 | 缺陷版 | 修复版 | 判定 |
|---|---|---|---|
| Agent原测试：`!ext=mp4` | AssertionError: True is not false | 相同 AssertionError | 错误预期，不能证明目标缺陷 |
| 评测侧只纠正输入：`ext!=mp4` | AssertionError: False is not true | 通过 | 证明触发输入错误；不计Agent命中 |

执行判定允许“同一个函数被调用”代替精确分支触达；后续模型核验没有识别实际失败与候选解释的矛盾。两个新容器中重复出现同一断言错误，并不能单独证明代码有问题。

- [Agent原测试](invalid-evidence/agent-report/evidence/9758e8ca5215/test_reproduction.py)
- [同一原测试在修复版的执行](invalid-evidence/controls/fixed-execution.json)
- [评测侧纠正输入的对照](invalid-evidence/controls/evaluator-corrected-input-diagnostic/control.json)

## 完成度与排除

| 批次 / 模式 | 审查次数 | 所选窗口审查完成 | 整条流程 completed | 模型调用 | 输入 / 输出 tokens | 审查耗时之和 |
|---|---:|---:|---:|---:|---:|---:|
| evidence-original20-20261014 / evidence | 40 | 38 | 15 | 313 | 1356710 / 82396 | 807.1s |
| evidence-new8-20261014 / direct | 16 | 15 | 15 | 22 | 31769 / 14760 | 180.9s |
| evidence-new8-20261014 / evidence | 16 | 16 | 5 | 99 | 403533 / 25742 | 225.8s |

总计69/72个审查窗口完整，35/72条流程为completed。其余包括未取得候选证据导致的partial；partial不等同于窗口没有读完。两个批次并行执行，上表是逐项耗时之和，不是墙钟用时或API收费金额。

原20个的官方测试复现19/20，新8个复现8/8。采用运行前声明的分母：官方测试成对复现且两侧窗口审查完整；unsupported、invalid_plan、复现失败、证据预算不足都留在分母并算未命中。

- 原20 / evidence：PySnooper-2官方测试无法收集；youtube-dl-9两侧APIStatusError导致窗口不完整。有效18对。
- 新8 / evidence：无成对排除，有效8对。
- 新8 / direct：youtube-dl-12修复版APITimeoutError导致窗口不完整。有效7对。

所有计划样本仍在记录中；按全部28个计划样本计，有效生成证据覆盖率为1/28（3.6%）。不通过只保留成功复现的候选或completed运行提高分数。

## 证据生成为什么受阻

| 候选证据状态 | 数量 |
|---|---:|
| budget_exhausted | 15 |
| contract_unconfirmed | 3 |
| invalid_plan | 16 |
| not_reproduced | 9 |
| reproduced | 13 |
| unrelated_failure | 6 |
| unsupported | 41 |

证据模式共103条模型候选，其中Agent自动接受13条为reproduced；只有1条匹配参考问题且具备有效证据，另有1条已通过独立对照证实为错误证据。其余额外问题只判“不匹配参考问题”，未全部作真实性判定，不能用1/13当作全局精确率。

可定位的失败例：tornado-4 找对了负 Range 问题，但生成测试复制计算代码，没有调用目标处理逻辑；youtube-dl-6 找到了缺 dur 的 KeyError，但计划字段/测试结构不合规则；mock辅助类和复杂初始化容易导致invalid_plan；部分 js_to_json 输出错误经 json.loads 暴露，但异常在目标文件之外被判unrelated_failure。最后一种需重新核对证据归因，不能一概认为候选正确。

## 建议的修改顺序

1. 修正证据判定：验证合法输入和实际触发分支，逐项核对观察值与候选解释；增加错误断言与相邻分支反例。此次修复版对照仅在评测侧使用，不将参考修复泄露给Agent。
2. 提高测试生成可用性：允许受限的mock/辅助构造，拒绝复制目标实现，同时接受能明确归因于错误返回值的下游失败。
3. 提高候选发现：当前存在大量无候选、无真实契约或错误逻辑推演；选择更丰富上下文及有依据的触发条件后，用另一批未用于调试的固定样本测量。

建议把当前版本作为可运行的毕业设计原型，审查意见由人确认；已有结果不足以支持自动判定代码质量或声称相对旧版检出率提升。旧版direct/full的4/18、3/19是代码推断指标，与本次“有效生成证据”指标不同；没有同标准旧20 direct/full重新运行对照。

## 复核资料

- [浏览器测评总览](report.html)
- [结构化指标](metrics.json)
- [逐次判读、原始候选ID与理由](adjudications.json)
- [72次运行记录](run-records.json)与[运行前冻结配置](run-configs.json)
- [全部原始报告、证据、官方测试和对照日志 ZIP](raw-results.zip)与[逐文件 SHA256](raw-manifest.json)

执行 `python demo/evidence-assessment-20261014/verify.py` 可验证634个归档文件、72份报告身份及指标算术，0次API调用；该校验不代替对语义判读的人工复查。浏览器总览可搜索样本、原因和候选ID。

审查源码 commit：`40034c2dd8e7a948f267218e272486be8cbc874e`。BugsInPy 数据：`11c5f1eea954a42132cfd06bf257766a7963e0fd`。两批11个src文件的SHA256均与运行前配置一致。Python3.7.17 / 3.8.20及实际镜像ID见原始证据。

原20入口：`evaluation/evidence_run.py --work outputs/bugsinpy-work --modes evidence --max-calls 24 --max-total-calls 480 --max-reproductions 3 --official-tests --output <新目录>`。新8入口：`evaluation/evidence_run.py --max-calls 24 --max-total-calls 320 --official-tests --output <新目录>`。使用已准备的数据和镜像；复跑会产生新的模型结果，原始评测不会被覆盖。
