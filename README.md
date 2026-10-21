# CodeReviewAgent

输入公开 GitHub 仓库 URL，获取固定 commit 的代码。默认审查模式生成最小测试，在隔离 Docker 中执行；正式缺陷附测试、环境和实际日志，未证实候选单列。输出 HTML、Markdown、JSON 报告。

这是基于 [Hello-Agents 第十六章](https://github.com/datawhalechina/hello-agents/tree/main/docs/chapter16) 的智能代码审查毕业设计项目。首版支持 **Python 代码**，提供命令行入口和可以在浏览器中筛选的审查报告。

## 功能

**2026-10-18 预期依据准入：** 正式 `reproduced` 不再只依赖模型一句 `accepted=true`。复现计划必须给出结构化的预期结果、触发前提和异常类，并通过代码侧准入检查；语言规则只能解释实际异常，不能单独证明“应抛出另一种异常”或返回值/状态；仅错误消息文案不进入正式缺陷。13条历史自动接受记录离线对照中1条保留、12条降级为待确认，0次模型/Docker调用。见[实现与固定对照](demo/expectation-admission-20261018/README.md)。这仍不是新样本检出率提升的证明。

**2026-10-21 发现对照与新样本验证已结束：** 完成legacy/callgraph及两轮单变量改进，再验证预选4新样本，共436/600次保守扣减。没有证实参考发现能力提升，默认配置保持不变；独立复现的1项额外问题单独报告。新样本关闭思考完整22/22窗口、两次参考区分2/4和1/4；开启完整11/22，共同可评分样本没有优势。全部失败、中断与冻结源码保留，见[最终对照与原始归档](demo/discovery-context-20261015/README.md)；[框架说明](docs/ARCHITECTURE.md)。

**2026-10-21 准入固定案例验证：** 用4个已见固定候选做真实模型对照，共5次调用、4次容器执行。PySnooper-3文档正例保留为`reproduced`；tornado-1 fixed和youtube-dl-4 fixed由模型直接`unsupported`；youtube-dl-8 buggy由确定性语言规则门控降级为`contract_unconfirmed`。这验证了固定正反例行为，不是新样本检出率。见[固定案例验证](demo/admission-validation-20261021/README.md)。

**2026-10-21 新样本 evidence 对照：** 4个holdout样本×2侧×baseline/admission两臂，16次运行、37次调用。两臂都是1/4有效检出、0固定侧同问题告警；admission多1次调用、多5条待确认候选，没有显示端到端增益，也没有破坏唯一正例。见[对照报告](demo/evidence-holdout-compare-20261021/README.md)。这是第一次evidence-stage pilot，样本少且单次重复，不能据此关闭安全门控，也不能声称检出率提升。

**2026-10-21 漏检失败分类：** 对2026-10-14的26个有效参考对逐条归类：候选命中4个、有效证据1个；22个漏检中8个完全没有候选、14个有候选但偏题；另有3个候选命中但证据失败。结论是瓶颈在发现阶段，不在Docker/取证/准入门控。见[失败分类与P1依据](demo/evidence-failure-taxonomy-20261021/README.md)。

**2026-10-21 P1 协议（未运行）：** 已实现“理解→枚举→反例→核对→候选”的假设—反例式发现提示和结构化输出，并冻结 6 个开发样本、18 个窗口、baseline/hypothesis 两臂、单次重复、80 次调用上限。只跑发现阶段，不启动证据引擎；尚未发出模型请求。见[P1 协议](demo/discovery-hypothesis-20261021/README.md)。

**2026-10-15 上下文检索实验：** 已接入`--context-strategy callgraph`，在evidence发现阶段补充静态调用方、被调用定义、相关导入与文档片段；默认仍为`legacy`。86项项目测试通过，6个历史样本两版本共18组初始输入核对通过，0次模型API调用。新增上下文尚未做模型效果对照，不能声称检出率提高；见[实现与离线检查](demo/context-callgraph-20261015/README.md)。

**2026-10-15 历史证据复测：** 冻结实现，旧13条已接受记录用旧/新执行器各重跑两次，并补做相反版本及调用链检查，共67次容器执行、0次模型API调用。新判定接受12条，稳定拦住1条错误触发，保留原有效参考复现；其余仍含预期无依据、质量建议及待定项，不能解释为12个真实缺陷。见[逐条复测报告](demo/evidence-retest13-20261015/README.md)。本轮没有测量新的检出率。

**2026-10-15 首轮改进：** 参考Primuus的证据约束与有限反馈机制，修正了“调用同一函数就算触达问题位置”的误接受。真实Docker正反例通过；一次反馈修正在3组固定候选对照中未增加有效证据，因此保持默认关闭。见[改动与对照结果](demo/primuus-controls-20261015/README.md)。本轮没有新的全量检出率结论。

**2026-10-14 实际测评：** 完成原20个及新8个BugsInPy缺陷的72次审查、434次DeepSeek调用。证据模式在26个有效缺陷对中，仅1个获得匹配参考问题的有效生成证据（3.8%）；新8个为0/8，并发现一条模型误认可的错误证据。当前是需要人工核对的原型。见[完整测评与原始资料](demo/evidence-assessment-20261014/README.md)及[浏览器总览](demo/evidence-assessment-20261014/report.html)。使用方式和限制见 [复现证据说明](evaluation/EVIDENCE.md)。

- 审查 GitHub 仓库或本地目录，记录本次审查的 commit 和覆盖范围。
- 使用 AST 建立代码索引，结合 Ruff 和 Bandit 获取静态分析线索。
- 审查 Agent 提出候选问题，复核 Agent 检查证据、保护条件和设计上下文。
- 每项问题包含文件位置、风险等级、触发条件、代码证据和修改建议。
- 证据模式两次独立容器执行，并核验测试预期的来源；保存可重新运行的测试与日志。
- 正式证据须通过结构化预期准入：语言规则不能单独证明不同的异常类型或业务返回值，错误消息文案不计行为缺陷。
- 限制文件数量与模型调用次数，记录实际用量，保存未完成部分及失败原因。
- 生成 HTML、Markdown、JSON 报告，保留复核与只读工具调用记录。

## 快速运行

准备 Python、Git 和可用的 Docker；默认证据模式需要事先准备测试镜像。需要支持 OpenAI 兼容 Chat Completions 接口和 JSON 输出的模型服务。其他审查模式可不使用 Docker，静态模式不需要模型 API。

```bash
git clone https://github.com/realleaves/CodeReviewAgent.git
cd CodeReviewAgent
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

编辑 `.env`，填写自己的模型配置：

```dotenv
LLM_MODEL_ID=your-model-name
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://your-provider.example/v1
LLM_THINKING_MODE=disabled
```

验证配置，然后开始第一次审查：

```bash
python main.py doctor
docker pull python:3.13-slim
python main.py review https://github.com/realleaves/quadruped-rl-learning --max-files 3 --max-calls 20
```

也可以先运行不调用模型的演示，确认依赖和报告生成正常：

```bash
python main.py review examples --local --mode static
```

程序优先读取本项目 `.env`，没有时读取上一级 `.env`，已有环境变量优先。密钥只从环境读取，不写入报告；`.env` 和 `.venv` 已在 `.gitignore` 中排除。

未激活虚拟环境时，将命令中的 `python` 换成 `.venv/bin/python`。Windows 对应 `.venv\Scripts\python.exe`。

## 使用方式

```bash
# GitHub 仓库：先审查最多 3 个 Python 文件
python main.py review https://github.com/realleaves/quadruped-rl-learning --max-files 3 --max-calls 20

# 分支和目录；scope 是目标仓库中的实际相对路径
python main.py review https://github.com/psf/requests --ref main --scope src/requests --max-files 3 --max-calls 20

# 对单个仓库文件作完整分析，便于有限预算的首次验证
python main.py review https://github.com/psf/requests --scope src/requests/api.py

# 本地仓库或目录
python main.py review ../my-project --local

# 带明确契约的缺陷/正常代码演示
python main.py review examples/evidence --local --max-files 2 --max-calls 16

# 只读代码推断模式，保留原有完整Agent作对照
python main.py review ../my-project --local --mode full

# 静态模式不调用模型
python main.py review examples --local --mode static

# 模式对比与功能测试
python evaluation/run.py --limit 4 --max-total-calls 24
python -m pytest -q tests
```

支持 `--ref`（分支或 tag）、`--scope`、`--model`、`--env-file`、`--output`。输出目录必须是新路径。

**替换仓库 URL 后，应同时修改或去掉 `--scope`。** `src/requests` 只适用于对应的 Requests 仓库；不指定 `--scope` 时从整个仓库中选择 Python 文件。

| 参数 | 默认值 | 用途 |
|---|---|---|
| `--mode` | `evidence` | 默认生成并执行复现测试；可选择旧的推断审查模式 |
| `--max-files` | `12` | 最多选择多少个 Python 文件 |
| `--max-calls` | `24` | 一次审查的模型调用总上限，包含审查与复核 |
| `--ref` | 仓库默认分支 | 指定分支或 tag |
| `--scope` | 仓库根目录 | 限定仓库内的目录或文件 |
| `--local` | 关闭 | 将输入作为本地目录 |
| `--output` | 自动生成 | 指定一个尚不存在的报告目录 |
| `--repro-image` | `python:3.13-slim` | 已准备的隔离镜像；目标有第三方依赖时需自备兼容镜像 |
| `--repro-timeout` | `15` | 每次隔离执行的秒数上限 |
| `--max-reproductions` | `4` | 最多验证几个候选，生成和核验仍计入总模型调用预算 |
| `--max-repro-repairs` | `0` | 实验功能：未调用到目标函数时，最多允许一次反馈修正；可设为1，仍计入模型预算 |
| `--context-strategy` | `legacy` | evidence发现阶段上下文；`callgraph`为调用关系检索实验，补充内容含JSON元数据最多10000字符，尚未验证检出收益 |
| `--review-strategy` | `baseline` | evidence发现策略；`hypothesis`为假设—反例式实验，尚未验证检出收益 |
| `--enforce-admission` | 开启 | 结构化预期准入；`--no-enforce-admission`仅用于baseline对照实验，不是生产建议 |

`evidence` 优先审查行为缺陷，生成测试、两次隔离执行并核验契约；`direct`、`assisted`、`full` 保留原来的代码推断流程；`static` 仅运行静态工具。后四种模式不将代码推断称为运行证明。

默认预算为 12 个 Python 文件、24 次模型调用、单文件 200KB、单块 180 行/20000 字符、单次请求 45 秒。模型自动重试关闭；工具读取最多120行，单次上下文上限90000字符。实际费用由配置服务商计价；报告记录调用次数与 token 使用量。

DeepSeek 服务默认关闭 thinking，以避免内部推理占满小预算而没有最终 JSON；可设置 `LLM_THINKING_MODE=enabled` 使用 low effort。单次输出上限6000 tokens。健康检查和真实报告记录实际模式与用量。参数依据：[DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)。

每次运行输出到独立 `outputs/<时间>-<随机后缀>/`，包含：

- `report.html`：本地浏览器打开，按风险、复核状态、文本筛选，跳转固定 commit 的代码。
- `report.md`：可读审查报告。
- `report.json`：问题、复核轨迹、模型调用用量、只读工具读取记录。
- `run.json`：commit、内容快照摘要、配置、覆盖范围、跳过原因和失败记录。
- `evidence/<问题ID>/`：生成测试、两次执行日志及结构化证据；生成失败的测试和理由也保留。

这些是生成的报告文件。运行结束后，复制终端显示的 `report` 路径，在 Linux 上打开：

```bash
xdg-open outputs/<本次运行目录>/report.html
```

也可以在文件管理器中双击 `report.html`，或把它拖入浏览器。GitHub 文件页面显示 HTML 源码，查看随仓库附带的演示时，请下载文件后在浏览器打开；在线阅读可直接查看 [Markdown 演示报告](demo/known-defects/report.md)。

## 工作流程

```text
仓库地址 / 本地目录
        ↓
固定版本 → 筛选 Python 文件 → AST 索引与分块
        ↓
Ruff / Bandit 静态诊断
        ↓
审查 Agent ← search_symbol / search_code / read_code
        ↓
生成最小测试 → 契约引用与结构检查 → 两次隔离执行
        ↓
核验预期行为与实际失败 → 已复现缺陷 / 待验证候选
        ↓
HTML / Markdown / JSON 报告与覆盖记录
```

## 项目结构

```text
CodeReviewAgent/
├── main.py                 # 命令行入口
├── src/
│   ├── repository.py       # 固定仓库版本与文件筛选
│   ├── code_index.py       # AST 索引、分块与只读工具
│   ├── static_analysis.py  # Ruff / Bandit 扫描
│   ├── agents.py           # 模型客户端、审查与复核 Agent
│   ├── reproduction.py     # 测试生成、执行、契约核验与证据复跑
│   ├── reproduction_runner.py # 容器内测试入口
│   ├── review_context.py   # 可选的调用关系上下文补充
│   ├── pipeline.py         # 审查流程与覆盖统计
│   ├── schemas.py          # 输入及结果结构
│   ├── deduplication.py    # 诊断去重与证据保留
│   └── report.py           # 多格式报告
├── examples/               # 缺陷代码和正常代码演示
├── evaluation/             # 对比样本、固定对照及评测入口
├── tests/                  # 功能测试
├── demo/                   # 精选实际报告、实验对照与浏览器验证截图
├── .env.example            # 模型配置模板
├── requirements.txt        # 锁定依赖版本
└── VALIDATION.md           # 实际验证记录
```

## 分析能力与边界

首版支持 Python。AST 建立函数、类和 import 索引；Ruff 检查 F/E9/B 规则；Bandit 检查常见安全风险。工具在独立代码快照上运行，忽略待审仓库扫描配置。Agent 可以调用 `search_symbol` 和 `read_code` 获取有限跨文件上下文。

证据模式的审查 Agent 提出问题，生成最小测试，再核验契约和实际失败。旧 full 模式保留模型复核。结果通过结构与行号校验后汇总。证据模式的 scope 限制主要审查位置，允许查阅仓库其他 Python 定义并复制其源码作隔离导入；旧模式保持原来的索引范围。

证据模式会在限制网络、权限和资源的 Docker 中导入目标代码并运行生成测试，源文件只读；不执行仓库安装脚本或 hooks，不将模型密钥或用户主目录传给容器。其他模式只读取和解析代码。`.env`、密钥文件、符号链接及非 Python 资源不进入执行快照。公开仓库无需 GitHub 登录；私有仓库要求 Git 已有访问权限。

`supported` 仅表示模型复核认为有代码依据，未进行运行复现；`needs_context` 为待确认；`unverified` 为尚未复核；`rejected` 为复核驳回。驳回项保留在 JSON/HTML。模型、工具超时或失败均记录，预算耗尽保留已完成的结果。报告不保证发现所有缺陷。

`reproduced` 表示两次隔离执行出现对应失败，且预期依据通过结构化准入和模型语义核验；仍需维护者复查。准入要求计划说明预期结果类型、触发前提及异常类；语言规则只能解释实际异常，不能单独证明另一种异常、返回值、状态或输出；仅错误消息文案会被降级。审计的结构化检查由代码再次核对，模型口头接受但字段缺失或为 false 时不会成为正式缺陷。`pending_evidence` 为未证实候选，保留具体缺失依据。导入错误、超时、未触达目标代码、测试通过或契约不足均不会成为正式缺陷。证据模式的默认报告视图和缺陷计数只显示 `reproduced`。

覆盖率是所选 scope 内已索引 Python 文件中完成所有语义分块的文件比例。相关文件的片段读取不计作完整审查。文件大小、索引总量、语言限制导致的排除项另列；报告会标明 partial，避免把部分审查当作全仓库结论。

## 运行状态

| 状态 | 含义 |
|---|---|
| completed | 当前索引范围内的选定分析完成 |
| partial | 覆盖受限、预算耗尽、执行/复核失败，或证据模式还有未证实候选 |
| static_only | 仅运行静态检查 |
| no_supported_files | 当前范围没有可审查的 Python 文件 |

CLI 退出码：0 为 completed/static_only；2 表示已保存报告但分析不完整或没有支持文件；1 为参数、仓库获取等启动失败；130 为手动中止。

## 常见问题

**提示 Git 操作失败。** 检查仓库 URL 拼写、访问权限和网络。可以先用 `git ls-remote https://github.com/owner/repo.git HEAD` 验证访问；已有本地副本时使用 `--local`。

**提示 scope 不存在。** `--scope` 必须是该仓库内存在的相对路径；不知道目录结构时先去掉这个参数。

**没有可审查文件。** 当前只支持 `.py` 文件。其他语言会被列入跳过项；确认范围中包含 Python 代码。

**程序退出码为 2，但生成了报告。** 打开报告查看范围、剩余文件和失败记录。`--max-files 3` 只审查选定的三个文件，仓库更大时可能为 `partial`；需要时调整文件数及调用预算。

**模型配置失败或输出不完整。** 先运行 `python main.py doctor`，检查 API 地址、模型名、服务商 JSON 输出支持及网络；审查中遇到失败会保留已完成的结果。

## 验证与评测

复现证据版已完成同版本冻结测评，源码commit为`40034c2`：原20个只运行evidence，新8个同时运行direct/evidence。26个有效缺陷对的有效生成证据命中为1/26；判读是模型辅助参考核对、待人工复查，窗口位置提前给定。复现失败的候选留在分母；只排除官方测试未复现或窗口审查不完整的对。所有计划样本、72次原始报告与失败记录保留在[2026-10-14测评资料](demo/evidence-assessment-20261014/README.md)。

已增加基于标准真实缺陷数据的 **BugsInPy 评测入口**，固定20个缺陷，比较缺陷/修复两版本与直接审查/双Agent模式。准备和复跑方法见 [BugsInPy 评测说明](evaluation/BUGSINPY.md)。这项评测限定参考代码窗口，单独验证测试复现；语义评分需要证据判读，不将行号重叠直接当作检出。

已用 `deepseek-flash` 实跑80次审查：79次完整完成，19/20个缺陷成对复现。模型辅助判读中，direct 检出4/18个有效缺陷，full 检出3/19个；当前检出能力仍需改进。这是已知位置窗口的小样本评测，人类复查待完成。原始报告、判读依据和失败项见 [BugsInPy 实际结果](demo/bugsinpy/README.md)。

本次运行的源码、模型与工具验证记录见 [VALIDATION.md](VALIDATION.md)。精选实际报告在 `demo/`：

- [真实 requests 仓库报告](demo/github-review/report.html)：src/requests 下选定3/19个Python文件，12次模型调用，未发生执行失败，范围受限所以标为partial。
- [已知缺陷演示](demo/known-defects/report.html)：检出3个已知问题，正常文件无保留问题。
- [同模型三种方式对比](demo/comparison.md)：4个小样本的实际结果。
- [发现阶段三轮与新样本对照](demo/discovery-context-20261015/README.md)：436次真实DeepSeek尝试，未证实参考发现增益，默认配置不变。
- [预期依据准入固定对照](demo/expectation-admission-20261018/README.md)：13条历史接受记录中1条进入审计、12条降级，0次模型调用。
- [准入固定案例验证](demo/admission-validation-20261021/README.md)：4个已见候选、5次调用，正例保留、3个负例降级。
- [新样本evidence对照](demo/evidence-holdout-compare-20261021/README.md)：4个holdout样本、16次运行、37次调用；两臂均1/4检出，admission无端到端增益。
- [漏检失败分类](demo/evidence-failure-taxonomy-20261021/README.md)：26个有效对中4个候选命中；22个漏检=8个无候选+14个偏题。
- [P1 假设—反例协议](demo/discovery-hypothesis-20261021/README.md)：6个开发样本、18个窗口、两臂、80次上限；尚未运行。

`tests/` 覆盖真实扫描器、路径与行号校验、只读工具、复核ID对应、调用失败、预算耗尽、语法错误、空文件、HTML转义与报告格式，以及结构化预期准入、语言规则边界和执行位置判定。

`evaluation/cases.json` 包含四组缺陷/正常代码对。`evaluation/run.py` 对同一批样本、同一模型比较 direct（纯模型）、assisted（工具辅助）、full（工具辅助加复核），输出每个样本的实际报告和 `comparison.md/json`。默认运行前4个样本，限制总调用24次。

四组演示样本按位置和类别粗匹配，同一标注被多个诊断命中只算一次；其失败样本单列。BugsInPy采用参考问题语义核对，证据版使用运行前声明的成对分母，候选复现失败仍计为未命中。小样本结果尚需人工核对触发条件和语义，不能当作泛化准确率或双Agent必然优于单Agent的证明。

## 技术与提交

使用 HelloAgents 0.2.9，匹配教程学习版本；补充 `huggingface-hub` 解决基础导入所需依赖。依赖完整锁定，未拷贝框架源码。主程序是 `main.py`，可以作为第十六章的可运行 Python 脚本交付。

提交毕业设计时，将项目源码放入 `Co-creation-projects/realleaves-CodeReviewAgent/`，排除 `.venv`、`.env`、缓存及批量输出；保留少量实际演示报告，按上游要求控制提交大小。依赖安装目录不属于提交内容。

教程与框架：[Hello-Agents](https://github.com/datawhalechina/hello-agents)、[HelloAgents](https://github.com/jjyaoao/HelloAgents/tree/learn_version)。
