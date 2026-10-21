# 复现证据首版

2026-10-13 版本作为实现检查点发布，CLI 默认 `evidence` 模式；原 direct/assisted/full/static 保留作对照。2026-10-14已完成原20个及新8个BugsInPy的72次审查、434次DeepSeek调用。26个有效缺陷对只有1个获得有效生成证据，新8个为0/8；发现一条模型误认可的错误证据。见[完整测评](../demo/evidence-assessment-20261014/README.md)。这是已知位置的模型辅助判读，待人工复查。

## 使用

准备 Docker 服务和镜像，然后使用已有模型配置运行：

```bash
docker pull python:3.13-slim
.venv/bin/python main.py review examples/evidence --local --max-files 2 --max-calls 16
.venv/bin/python main.py review https://github.com/owner/repository --max-files 3 --max-calls 24
```

目标有第三方依赖或使用较旧 Python 时，准备匹配的镜像并使用 `--repro-image your-image`。执行入口只使用本机已有镜像，记录实际镜像 ID，不在审查中自动下载或执行目标安装脚本。

默认每个测试15秒、最多4个候选；通过 `--repro-timeout`、`--max-reproductions` 调整。审查、生成、格式纠正及契约核验都计入 `--max-calls` 总预算。

## 正式缺陷的要求

1. 生成测试导入原目标模块，实际调用目标代码，没有复制另一份实现。
2. 预期行为有逐字可定位的引用及理由；来自文档、已有测试或明确语言规则。业务约定不能仅从错误实现推导。
3. 测试在两个全新受限容器中失败，实际执行行或真实异常栈触达候选位置，失败类型一致；仅调用同一函数不能替代目标触达。导入阶段的定义不算测试阶段执行。
4. 模型核验实际失败、输入前置条件和预期行为；失败的断言本身不证明程序有缺陷。
5. 计划必须结构化说明预期结果类型、触发前提和异常类。`language_rule` 只能解释实际异常，不能单独要求另一种异常、返回值、状态或输出；仅错误消息措辞属于诊断质量，不进入正式缺陷。审计的结构化字段由代码再次核对，缺失、false 或存在未决假设时保持待确认。

程序将通过上述自动检查的候选标记 `reproduced`，进入默认的正式缺陷视图。测试通过、引用不成立、无关错误、缺少依赖/资源或预算不足的项目保留为待验证。语义核验仍依赖模型，`reproduced` 不是独立人工确认或无误报保证。本次测评已证实：错误输入产生的断言失败也可能被模型误认可，因此标签必须结合实际触发条件和日志复查。

## 隔离与支持范围

Docker 无外网、只读根文件系统和源代码、普通用户、移除 capabilities、禁止权限提升，限制内存、CPU、进程及输出量；仅挂载 Python 源码快照和测试入口，临时文件写到容器 `/tmp`。没有模型密钥、宿主主目录或 Docker socket 挂载。

生成测试当前使用标准库 unittest：一个 `ReproductionTest(unittest.TestCase)`，一个同步测试方法。入口检查引用、导入和结构，禁止无条件失败及运行时改写测试入口。允许的测试标准库列表会提供给生成器。AST检查用于限制测试结构，执行隔离依靠 Docker。

执行快照只含 UTF-8 Python 文件，不包含数据文件、证书或其他资源；依赖复杂资源的项目可能无法复现。scope 限制主审查位置，证据模式可读取其他仓库 Python 定义，完整源码摘要与主审查摘要分别记录。

## 证据与复跑

每个候选有 `evidence/<ID>/evidence.json`。生成成功时同时保存 `test_reproduction.py` 和 `attempt-1.log`、`attempt-2.log`。JSON包含原测试、引用、模型核验、实际解释器版本、镜像 ID、执行摘要与源码快照哈希；生成失败的回答和纠正理由也保留。

在同一代码快照和本机镜像上复跑，不调用模型：

```bash
.venv/bin/python main.py reproduce outputs/<run>/evidence/<ID>/evidence.json examples/evidence --output outputs/replay-new
```

第二个参数是当时审查的本地目录。GitHub审查需先取得对应 commit 的本地副本。源码哈希不一致会拒绝复跑，输出目录必须是新路径。成功返回 `failure_observed` 只说明保存的失败再次出现，不重新判定业务契约。

## 当前验证与测评

已运行明确规定空输入返回0.0的缺陷/正常代码演示；最初运行5次 DeepSeek 调用。上传检查点用当前代码和默认镜像再次运行4次调用，Python 3.13.16，缺陷两次隔离复现，正常代码无保留候选。上传的证据独立复跑成功，0次模型调用。实际报告见 [demo/evidence-checkpoint/report.md](../demo/evidence-checkpoint/report.md)。

三个真实缺陷对的初次试跑完成6次审查；发现标准库导入限制过严和生成格式问题，已加入允许列表提示、保存原回答以及一次有预算限制的纠正。试跑不作为能力提升证明。

新增8个固定样本：tornado 9–12、youtube-dl 10–13，清单见 [evidence-holdout-manifest.json](evidence-holdout-manifest.json)。初次运行因入口修正被中止；2026-10-14冻结源码完成完整复跑与参考问题判读。新8个direct候选识别1/7、evidence候选识别1/8，有效生成证据0/8；原20个evidence有效生成证据1/18。唯一有效命中PySnooper-3的未改测试，独立对照在缺陷版失败、修复版通过。youtube-dl-12的Agent原测试在两版同样失败，被扣除；评测侧纠正输入只用于诊断，不计Agent成绩。运行入口：

```bash
.venv/bin/python evaluation/evidence_run.py --prepare
.venv/bin/python evaluation/evidence_run.py --official-tests --output outputs/evidence-holdout-new
```

准备命令需要先按 [BugsInPy说明](BUGSINPY.md) 下载固定数据版本和历史测试镜像，默认工作目录为 `outputs/evidence-holdout-work`。Agent索引和容器都排除官方测试；官方回归测试只由评测程序执行。未匹配参考问题的其他已复现问题不能自动算已知缺陷命中，待验证候选不能通过从评分分母删除来抬高成绩。

完整结果、逐次判读、源码哈希、两项独立对照及全部原始资料见[测评目录](../demo/evidence-assessment-20261014/README.md)。原20个排除PySnooper-2（官方测试无法收集）与youtube-dl-9（两侧API错误，窗口不完整）；新8个证据模式无排除，direct排除youtube-dl-12（修复版请求超时）。35/72条流程为completed，69/72个窗口完整；未取得候选证据造成的partial继续计入评分分母。优先需要改进合法输入与分支触达检查、生成测试的实际目标调用、mock构造及下游错误归因；本次评测没有改动审查源码。

## 2026-10-15 执行位置修复与反馈对照

删除同函数调用的触达兜底，增加结构化异常帧并只记录测试执行阶段的行和调用。PySnooper-3的真实NameError异常栈仍能支持证据；youtube-dl-12走错分支的断言失败不再被接受。两例均在缺陷/修复两版本上用新Docker执行验证，另有只导入未调用、相邻分支两个通用反例。原有保存证据仍可用可信旧异常栈格式复跑，不能把异常消息中的目标路径当成新结构化帧。

新增实验参数`--max-repro-repairs 1`：当测试未记录到候选函数调用时，最多请求一次反馈修正。原contract所有字段及expected_behavior必须不变，测试通过、已调用目标却走错分支或缺少依赖不重写。仍需两次有效失败与契约核验。保存各版测试、全部执行及其版本/哈希，不能只展示最终成功尝试。

该功能默认0。冻结tornado-4原候选与计划的3组off/on对照，实际新增5次DeepSeek调用，两条件有效证据均为0/3，未达到预定收益条件。故保持实验功能默认关闭；原始失败保留，未追加采样或改断言提高成绩。65项项目测试通过。详见[首轮改进结果](../demo/primuus-controls-20261015/README.md)。导入阶段缺陷与目标文件外的下游错误仍存在保守归因限制，本轮未改变候选发现，也未重跑全量盲测。

## 2026-10-18 预期依据准入

新增结构化预期字段和代码侧准入。新计划必须填写 `expected_outcome`、`precondition`，异常预期还要填写 `expected_exception`；`error_message` 直接拒绝，`unspecified` 不再作为有效预期。两次执行触达目标后，先运行确定性 `requirement_gate`：语言规则只能解释实际异常，若实际异常与期望不同，不能推出“应抛出另一种异常”；语言规则也不能单独证明返回值、状态或输出。通过后再询问模型审计，并用 `input_supported`、`requirement_supported`、`failure_matches_candidate`、`requirement_class`、`unresolved_assumptions` 重新检查；任一失败、缺失或存在未决假设时保持 `pending_evidence`，即使模型写 `accepted=true`。

用2026-10-15复测的13条历史自动接受记录做离线固定对照：只有PySnooper-3（文档明确承诺output_path输出）进入审计，12条被降级为待确认，其中1条仅错误消息文案、7条用语言规则要求实际未发生的另一种异常、4条用语言规则证明返回值/状态/输出。这里不是把12条判成误报；原测试、日志和执行记录保留，只是不进入正式`reproduced`。0次模型调用、0次Docker执行，未改历史1/26得分、评分器或参考rubric。

`replay_evidence`仍只校验旧证据结构和源码哈希，不会因旧计划缺少新字段拒绝复跑。新增测试覆盖结构化字段、语言规则正反例、审计字段不一致、旧格式接受和13条固定对照。当前107项项目测试通过，Ruff F/E9与格式检查通过。限制：该结果只证明准入策略在固定历史记录上的行为，不能证明模型在新提示下稳定填写字段，也不能证明新样本检出或误接受改善；仍需未参与修改的新样本成对运行。详见[预期准入对照](../demo/expectation-admission-20261018/README.md)。
