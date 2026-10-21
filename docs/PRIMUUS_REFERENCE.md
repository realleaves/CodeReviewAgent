# Primuus-Agent 源码对照与可借鉴设计

查阅日期：2026-10-15。参考仓库：[Primuus/Primuus-Agent](https://github.com/Primuus/Primuus-Agent)，固定commit `1ee6c94a513c8c0a36fb54d41f64522acb10c1b9`。Git与GitHub API核实仓库公开且默认分支为main；网页抓取曾返回404，随后通过Git成功取得源码。

阅读范围包括README、运行配置、SessionRunner、SessionState、上下文与计划、工具调用适配、恢复策略、Harness、独立Verifier、重复基线及部分实验报告。本次为静态源码对照，没有安装或执行第三方Agent，没有进行新的模型调用，也没有修改本项目生产源码。

## 两个项目的任务差异

Primuus-Agent执行给定需求的开发与修复任务，支持独立Git工作区、Docker工具、计划、上下文续接、项目检查及任务验证。本项目主动审查仓库并提出未知缺陷，需要先确定输入约定、预期行为和错误触发条件。

Primuus评测任务包有预先编写的Verifier，Agent运行时只取得repo与task.md。Verifier由评测侧在另一容器检查工作区快照。这个安排适合验证“是否完成已知需求”，不能直接提供未知缺陷的正确预期，也不能据它的任务成功率推断代码审查检出率。

来源：[任务加载](https://github.com/Primuus/Primuus-Agent/blob/1ee6c94a513c8c0a36fb54d41f64522acb10c1b9/coding_agent/harness/task.py)、[任务运行](https://github.com/Primuus/Primuus-Agent/blob/1ee6c94a513c8c0a36fb54d41f64522acb10c1b9/coding_agent/eval/evaluator.py#L63)、[独立Verifier](https://github.com/Primuus/Primuus-Agent/blob/1ee6c94a513c8c0a36fb54d41f64522acb10c1b9/coding_agent/verifier/docker.py)。

## 具体可借鉴项

| 机制 | 参考仓库中的实现 | 本项目已有内容与缺口 | 拟验证的最小改动 |
|---|---|---|---|
| 状态必须引用真实证据 | 计划完成须引用实际成功Shell的call_id；源码变化或恢复后旧引用失效；项目检查关联当前补丁摘要 | 已有源码摘要、真实执行与日志；但同函数被调用可替代精确目标触达，模型接受即可标reproduced | 强化候选位置与实际分支/异常栈的对应；明确执行观察、契约依据与核验结论的区别。只用执行失败不能证明预期正确 |
| 假设与观察分开保存 | 计划分别记录files、hypothesis、next_action、evidence；上下文明确将假设标为未证实 | 已有候选、source、trace和失败理由；缺少单候选执行反馈后的受控下一动作 | 每个候选保留输入前置条件、预期来源、观察结果和缺失事实；只有具体缺失事实才触发下一步，结论不能从计划描述继承 |
| 按失败类型有限恢复 | 分开处理模型服务、工具、测试/构建、权限等失败，限制重试并拦截重复失败动作 | 生成格式错误可纠正一次；实际测试未形成有效失败通常直接结束 | 在有明确测试构造错误依据时允许一次反馈修正，修正不改变原行为约定。预算和所有失败保留；测试通过时先反驳候选，不追求制造失败 |
| 结构化工具调用 | 通过API的tools与tool_calls传递函数名、参数和调用ID | 当前BoundedAgent用文本标记解析工具调用，每阶段最多2轮、每轮4次 | 单独测试原生工具协议能否减少参数/格式错误；工具能力、模型与预算保持一致，不能把协议可靠性提升当成语义检出提升 |
| 可追溯的上下文 | 历史输出被裁剪时提供output_ref，可按call_id回读；摘要区分源码快照与工作假设 | 可分段读取源码并保存trace；每次阶段启动新的Agent，缺少候选后续反馈状态 | 先在固定候选诊断中保留原始读码与执行引用，按需回读，检验能否减少错误假设与重复读取；不直接增加长期记忆系统 |
| 固定条件的重复对照 | 保存code_commit、完整config、task_digests、task_order、repeats；续跑不一致即拒绝，恢复开关对照交替运行顺序 | 已冻结src摘要、样本和预算并保留失败；本轮未做多次重复 | 下一轮预先保存基线/修改版本与完整运行配置，成对重复并记录波动；源码、模型配置、任务或环境变化须另立实验 |

对应源码：[证据与状态](https://github.com/Primuus/Primuus-Agent/blob/1ee6c94a513c8c0a36fb54d41f64522acb10c1b9/coding_agent/session/state.py#L286)、[上下文](https://github.com/Primuus/Primuus-Agent/blob/1ee6c94a513c8c0a36fb54d41f64522acb10c1b9/coding_agent/session/context.py)、[恢复策略](https://github.com/Primuus/Primuus-Agent/blob/1ee6c94a513c8c0a36fb54d41f64522acb10c1b9/coding_agent/session/recovery.py)、[工具协议](https://github.com/Primuus/Primuus-Agent/blob/1ee6c94a513c8c0a36fb54d41f64522acb10c1b9/coding_agent/models/openai_compatible.py#L32)、[重复基线](https://github.com/Primuus/Primuus-Agent/blob/1ee6c94a513c8c0a36fb54d41f64522acb10c1b9/coding_agent/eval/evaluator.py#L180)。

本项目对应位置：[文本工具循环](../src/agents.py#L233)、[复现生成与执行](../src/reproduction.py#L389)、[执行判定](../src/reproduction.py#L339)。

## 优先级与实验边界

先借鉴证据约束与单候选的有限反馈循环，分别处理已确认错误接受、已识别但测试构造失败的问题。按已有[改进实验方法](IMPROVEMENT_METHOD.md)逐项比较，不能同时重写整套Agent再把收益归因于某个设计。

首轮机制检查保留PySnooper-3有效证据；youtube-dl-12走错分支的测试必须被拒绝。取证诊断固定已评测样本的正确候选，对比一次反馈是否改善真实目标调用和有效证据转化；这些有参考信息的诊断不计独立检出。

随后单独验证工具调用协议与上下文获取对候选识别的影响。本轮26个有效对只识别4个参考问题，22个候选阶段漏检仍需独立实验；改善执行恢复不能直接解释或解决这些漏检。

## 不能从该仓库推导的结论

- Docker、日志和隔离验证环境本项目已经具备；进一步搭容器本身不是证据语义正确性的解决方案。
- `behavior_evidence_error`机械检查call_id真实、执行成功及版本时效，没有自动证明命令断言覆盖正确需求。其文档也保留了模型理解与独立验收的职责。
- 参考仓库的默认模型配置同样是deepseek-flash，但工作阶段推理设置、任务、轮数与预算不同，不能用来证明同模型一定能解决本项目，也不能据此归因于模型优劣。
- 已查看的受控恢复/记忆实验包含预设行为模型，其通过只验证机制。仓库还保留跨文件真实任务未通过的记录；最新查看的2026-10-11 real_010仍未完成，并区分服务中断、未完成算法工作与运行时缺口。复杂机制存在不等于真实能力已验证。
- 仓库会话的`run_checks`缓存复用与评测任务的私有Verifier是两个层次，不能把现有项目测试通过当成目标需求完成，也不能把换成另一个模型复核称为独立正确性依据。

来源：[受控恢复实验](https://github.com/Primuus/Primuus-Agent/blob/1ee6c94a513c8c0a36fb54d41f64522acb10c1b9/docs/experiments/2026-09-27-recovery-controlled/README.md)、[运行配置](https://github.com/Primuus/Primuus-Agent/blob/1ee6c94a513c8c0a36fb54d41f64522acb10c1b9/config/default.json)、[最近查看的真实实验](https://github.com/Primuus/Primuus-Agent/blob/1ee6c94a513c8c0a36fb54d41f64522acb10c1b9/experiments/2026-10-11-s-real010/report.json)、[失败归因](https://github.com/Primuus/Primuus-Agent/blob/1ee6c94a513c8c0a36fb54d41f64522acb10c1b9/experiments/2026-10-11-s-real010/analysis.json)。

以上记录初次阅读时的借鉴建议与源码观察。用户认可后于2026-10-15完成[首轮实现与对照](../demo/primuus-controls-20261015/README.md)：已知错误证据被拒绝、有效正例保留；一次反馈未显示有效取证收益，默认关闭。未验证候选发现或新样本检出率提升。
