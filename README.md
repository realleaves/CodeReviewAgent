# CodeReviewAgent

输入公开 GitHub 仓库 URL，获取固定 commit 的代码，通过静态工具、HelloAgents 审查 Agent 和复核 Agent，输出带文件、行号、触发条件和修复建议的 HTML、Markdown、JSON 报告。

这是基于 [Hello-Agents 第十六章](https://github.com/datawhalechina/hello-agents/tree/main/docs/chapter16) 的智能代码审查毕业设计项目。首版支持 **Python 代码**，提供命令行入口和可以在浏览器中筛选的审查报告。

## 功能

- 审查 GitHub 仓库或本地目录，记录本次审查的 commit 和覆盖范围。
- 使用 AST 建立代码索引，结合 Ruff 和 Bandit 获取静态分析线索。
- 审查 Agent 提出候选问题，复核 Agent 检查证据、保护条件和设计上下文。
- 每项问题包含文件位置、风险等级、触发条件、代码证据和修改建议。
- 限制文件数量与模型调用次数，记录实际用量，保存未完成部分及失败原因。
- 生成 HTML、Markdown、JSON 报告，保留复核与只读工具调用记录。

## 快速运行

准备 Python 和 Git；已在 Python 3.13.5、Git 2.34.1 上验证。需要一个支持 OpenAI 兼容 Chat Completions 接口和 JSON 输出的模型服务。静态模式不需要模型 API。

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
| `--mode` | `full` | 选择静态、直接模型、工具辅助或工具辅助加复核模式 |
| `--max-files` | `12` | 最多选择多少个 Python 文件 |
| `--max-calls` | `24` | 一次审查的模型调用总上限，包含审查与复核 |
| `--ref` | 仓库默认分支 | 指定分支或 tag |
| `--scope` | 仓库根目录 | 限定仓库内的目录或文件 |
| `--local` | 关闭 | 将输入作为本地目录 |
| `--output` | 自动生成 | 指定一个尚不存在的报告目录 |

`direct` 为直接模型审查，`assisted` 加入静态工具线索与只读代码工具，`full` 在工具辅助审查后增加复核，`static` 仅运行静态工具。

默认预算为 12 个 Python 文件、24 次模型调用、单文件 200KB、单块 180 行/20000 字符、单次请求 45 秒。模型自动重试关闭；工具读取最多120行，单次上下文上限90000字符。实际费用由配置服务商计价；报告记录调用次数与 token 使用量。

DeepSeek 服务默认关闭 thinking，以避免内部推理占满小预算而没有最终 JSON；可设置 `LLM_THINKING_MODE=enabled` 使用 low effort。单次输出上限6000 tokens。健康检查和真实报告记录实际模式与用量。参数依据：[DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)。

每次运行输出到独立 `outputs/<时间>-<随机后缀>/`，包含：

- `report.html`：本地浏览器打开，按风险、复核状态、文本筛选，跳转固定 commit 的代码。
- `report.md`：可读审查报告。
- `report.json`：问题、复核轨迹、模型调用用量、只读工具读取记录。
- `run.json`：commit、内容快照摘要、配置、覆盖范围、跳过原因和失败记录。

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
审查 Agent ← search_symbol / read_code
        ↓
复核 Agent → 结构与行号校验 → 去重
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
│   ├── pipeline.py         # 审查流程与覆盖统计
│   ├── schemas.py          # 输入及结果结构
│   ├── deduplication.py    # 诊断去重与证据保留
│   └── report.py           # 多格式报告
├── examples/               # 缺陷代码和正常代码演示
├── evaluation/             # 对比样本及评测入口
├── tests/                  # 功能测试
├── demo/                   # 精选实际报告与浏览器验证截图
├── .env.example            # 模型配置模板
├── requirements.txt        # 锁定依赖版本
└── VALIDATION.md           # 实际验证记录
```

## 分析能力与边界

首版支持 Python。AST 建立函数、类和 import 索引；Ruff 检查 F/E9/B 规则；Bandit 检查常见安全风险。工具在独立代码快照上运行，忽略待审仓库扫描配置。Agent 可以调用 `search_symbol` 和 `read_code` 获取有限跨文件上下文。

审查 Agent 提出问题，复核 Agent 找保护条件、反例和设计意图；结果通过结构校验、文件与行号校验后汇总。相同诊断精确去重；已知规则与模型发现只有在位置、类别、复核状态一致且映射唯一时合并，原工具诊断保存在 related_diagnostics。scope 同时限定代码索引范围，scope 之外的文件不会作为关联上下文读取。

仓库代码仅作为文本读取和解析，不安装它的依赖、不执行它的程序、测试或 hooks。`.env`、密钥文件、符号链接、生成目录及非 Python 资源按原因跳过。公开仓库无需 GitHub 登录；私有仓库要求 Git 已有访问权限。

`supported` 仅表示模型复核认为有代码依据，未进行运行复现；`needs_context` 为待确认；`unverified` 为尚未复核；`rejected` 为复核驳回。驳回项保留在 JSON/HTML。模型、工具超时或失败均记录，预算耗尽保留已完成的结果。报告不保证发现所有缺陷。

覆盖率是所选 scope 内已索引 Python 文件中完成所有语义分块的文件比例。相关文件的片段读取不计作完整审查。文件大小、索引总量、语言限制导致的排除项另列；报告会标明 partial，避免把部分审查当作全仓库结论。

## 运行状态

| 状态 | 含义 |
|---|---|
| completed | 当前索引范围内的选定分析完成 |
| partial | 覆盖受限、调用预算耗尽，或存在执行/复核失败 |
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

本次运行的源码、模型与工具验证记录见 [VALIDATION.md](VALIDATION.md)。精选实际报告在 `demo/`：

- [真实 requests 仓库报告](demo/github-review/report.html)：src/requests 下选定3/19个Python文件，12次模型调用，未发生执行失败，范围受限所以标为partial。
- [已知缺陷演示](demo/known-defects/report.html)：检出3个已知问题，正常文件无保留问题。
- [同模型三种方式对比](demo/comparison.md)：4个小样本的实际结果。

`tests/` 覆盖真实扫描器、路径和行号校验、只读工具、复核ID对应、调用失败、预算耗尽、语法错误、空文件、HTML转义与报告格式。

`evaluation/cases.json` 包含四组缺陷/正常代码对。`evaluation/run.py` 对同一批样本、同一模型比较 direct（纯模型）、assisted（工具辅助）、full（工具辅助加复核），输出每个样本的实际报告和 `comparison.md/json`。默认运行前4个样本，限制总调用24次。

评测按位置和类别粗匹配；同一标注被多个诊断命中只算一次。失败样本不计入准确性指标且单列完成数。小样本结果尚需人工核对触发条件和语义，不能当作泛化准确率或双Agent必然优于单Agent的证明。

## 技术与提交

使用 HelloAgents 0.2.9，匹配教程学习版本；补充 `huggingface-hub` 解决基础导入所需依赖。依赖完整锁定，未拷贝框架源码。主程序是 `main.py`，可以作为第十六章的可运行 Python 脚本交付。

提交毕业设计时，将项目源码放入 `Co-creation-projects/realleaves-CodeReviewAgent/`，排除 `.venv`、`.env`、缓存及批量输出；保留少量实际演示报告，按上游要求控制提交大小。依赖安装目录不属于提交内容。

教程与框架：[Hello-Agents](https://github.com/datawhalechina/hello-agents)、[HelloAgents](https://github.com/jjyaoao/HelloAgents/tree/learn_version)。
