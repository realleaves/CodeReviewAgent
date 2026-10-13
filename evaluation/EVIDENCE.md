# 复现证据首版

2026-10-13 当前版本作为检查点发布。CLI 默认 `evidence` 模式；原 direct/assisted/full/static 保留作对照。完整真实样本复跑还未完成，这个版本没有新的泛化检出率结论。

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
3. 测试在两个全新受限容器中失败，触达候选代码，失败类型一致。
4. 模型核验实际失败、输入前置条件和预期行为；失败的断言本身不证明程序有缺陷。

只有满足这些要求的候选标记 `reproduced`，进入默认的正式缺陷视图。测试通过、引用不成立、无关错误、缺少依赖/资源或预算不足的项目保留为待验证。语义核验仍依赖模型，`reproduced` 不是独立人工确认或无误报保证。

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

## 当前验证与未完成工作

已运行明确规定空输入返回0.0的缺陷/正常代码演示；最初运行5次 DeepSeek 调用。上传检查点用当前代码和默认镜像再次运行4次调用，Python 3.13.16，缺陷两次隔离复现，正常代码无保留候选。上传的证据独立复跑成功，0次模型调用。实际报告见 [demo/evidence-checkpoint/report.md](../demo/evidence-checkpoint/report.md)。

三个真实缺陷对的初次试跑完成6次审查；发现标准库导入限制过严和生成格式问题，已加入允许列表提示、保存原回答以及一次有预算限制的纠正。试跑不作为能力提升证明。

新增8个固定样本：tornado 9–12、youtube-dl 10–13，清单见 [evidence-holdout-manifest.json](evidence-holdout-manifest.json)。初次运行因入口修正被中止，完整复跑尚未完成。运行入口：

```bash
.venv/bin/python evaluation/evidence_run.py --prepare
.venv/bin/python evaluation/evidence_run.py --official-tests --output outputs/evidence-holdout-new
```

准备命令需要先按 [BugsInPy说明](BUGSINPY.md) 下载固定数据版本和历史测试镜像，默认工作目录为 `outputs/evidence-holdout-work`。Agent索引和容器都排除官方测试；官方回归测试只由评测程序执行。未匹配参考问题的其他已复现问题不能自动算已知缺陷命中，待验证候选不能通过从评分分母删除来抬高成绩。
