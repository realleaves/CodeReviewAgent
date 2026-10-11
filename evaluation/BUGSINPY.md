# BugsInPy 真实缺陷评测

本评测使用 [BugsInPy](https://github.com/soarsmu/BugsInPy) 的真实缺陷、修复版本和测试，在现有 CodeReviewAgent 上比较 `direct` 与 `full`。这是基于标准数据的自建审查评测协议，没有官方排行榜成绩。

## 数据与范围

- 数据版本固定为 `11c5f1eea954a42132cfd06bf257766a7963e0fd`。
- [固定样本清单](bugsinpy-manifest.json)：PySnooper 1–3、Tornado 1–8、youtube-dl 1–9，共20个缺陷，按项目交错排列；前3项各来自一个项目。
- 样本按编号预先确定，不根据模型表现筛选。所有失败、无法复现与未完成项保留。
- 使用参考补丁的生产代码 hunk 选择函数或邻近窗口，属于**已知位置的缺陷识别**；没有测试全仓库自动定位。
- Reviewer 的索引与工具排除测试目录；不提供标签、补丁、缺陷编号、测试名称、版本类别或另一版本。两个版本用独立模型会话审查。
- 修复快照遵循 BugsInPy checkout 的重建方式：从缺陷 commit 起步，恢复修复 commit 修改的文件。复现测试文件从修复 commit 复制到两个版本。修复快照不冒充上游完整 fixed tree。

## 准备

在项目根目录运行。需要已安装的项目依赖、可用的 Docker 服务，以及模型配置。

```bash
mkdir -p outputs
git clone https://github.com/soarsmu/BugsInPy.git outputs/bugsinpy-data
git -C outputs/bugsinpy-data checkout 11c5f1eea954a42132cfd06bf257766a7963e0fd
.venv/bin/python evaluation/bugsinpy.py prepare
docker pull python:3.7-slim@sha256:b53f496ca43e5af6994f8e316cf03af31050bf7944e0e4a308ad86c001cf028b
docker build -f evaluation/bugsinpy-python38.Dockerfile -t code-review-bugsinpy:py38 .
```

`prepare` 在 `outputs/bugsinpy-work/` 中下载固定 commit 并生成快照，不执行目标项目安装脚本。完成的快照可以复用；准备中断留下不完整快照时，使用新的 `--work` 目录。

若 Git 可以访问 GitHub，而镜像构建下载依赖超时，请让构建使用本机已有的代理。代理只用于构建下载，不用于复现测试；不要将模型密钥传给 Docker 构建。项目 `.dockerignore` 排除了 `.env`、虚拟环境、缓存和运行输出。

## 运行

先运行3个缺陷、两个版本和两种模式，共12次审查：

```bash
.venv/bin/python evaluation/bugsinpy.py run --limit 3 --reproduce --max-calls 24 --max-total-calls 240 --python37-image python:3.7-slim@sha256:b53f496ca43e5af6994f8e316cf03af31050bf7944e0e4a308ad86c001cf028b --output outputs/bugsinpy-pilot-new
```

完整20个缺陷的80次审查：

```bash
.venv/bin/python evaluation/bugsinpy.py run --limit 20 --reproduce --max-calls 24 --max-total-calls 720 --python37-image python:3.7-slim@sha256:b53f496ca43e5af6994f8e316cf03af31050bf7944e0e4a308ad86c001cf028b --output outputs/bugsinpy-20-new
```

输出目录必须是新路径。模型读取与主程序相同的 `.env` 配置；每次实际调用计入单次和总预算，格式纠正也计入预算。达到上限保留已完成结果，剩余项标记未完成。可以通过 `--modes full` 仅运行完整 Agent。

不带 `--reproduce` 可以只审查代码，但该运行缺少成对复现证据，评分程序不会将其纳入有效缺陷对。

## 独立复现环境

测试在临时快照的 Docker 容器内运行：禁用外网、只读根文件系统、普通用户、移除 capabilities、禁止权限提升、限制进程/内存/CPU。容器仅收到代码副本和指定测试命令，不接收模型密钥或用户主目录。

测试选择器来自固定数据中的 `run_test.sh`，解析为参数列表，仅支持选定样本使用的 unittest/pytest；不执行 shell 脚本、项目 `setup.sh` 或任意拼接命令。只在测试实际执行且排除明显环境错误时，记录缺陷版失败、修复版通过为 `reproduced`。退出码非零、全部跳过、依赖导入失败或超时不会单独证明缺陷复现。

Python 使用与数据相同的主/次版本；镜像实际是较新的维护小版本，镜像 ID 与实际解释器版本记录在复现 JSON 中。测试依赖采用最小锁定集合，而非恢复历史完整 pip freeze。

PySnooper-1 是默认文本编码缺陷：UTF-8 locale 会掩盖问题。该样本两版本都使用 `LC_ALL=C`、`PYTHONCOERCECLOCALE=0`、`PYTHONUTF8=0`，保持测试及代码不变；其他样本使用 `C.UTF-8`。此环境适配明确保存在证据中。

如果测试因历史依赖缺失而未启动，可以在**整批审查结束后**补齐镜像，再只复跑测试。例如：

```bash
.venv/bin/python evaluation/bugsinpy_recheck.py --run outputs/bugsinpy-20-new --cases PySnooper-1 PySnooper-2 PySnooper-3 --python38-image code-review-bugsinpy:py38 --reason '补齐声明的历史依赖，代码、测试和模型回答不变'
```

此命令保留初次日志，在 `reproduction-attempts/` 保存新证据，并更新评分所用的复现状态；没有模型调用。不要在原批次仍运行时使用它。复跑后重新生成评分。此次实际运行补齐了 PySnooper-3 声明的 `future`、`decorator`，三个 PySnooper 样本统一复跑；PySnooper-2 仍因重建快照的跨文件依赖不一致而未复现，予以排除。

## 结果与评分

运行目录包含：

```text
run_config.json                  # 数据版本、源码哈希和预算
selection.json                   # 本次选择与版本来源
reproduction/<样本>/             # 两版本测试日志、镜像及环境证据
reviews/<样本>/<模式>/<版本>/     # 原始 HTML、Markdown、JSON 审查报告
results.json                     # 逐次状态、耗时、调用与 token 用量
comparison.md                    # 审查流程汇总
adjudication-template.json        # 语义判读表，初始判定为 null
```

自动位置重叠只筛选待复查项，不自动认定检出。对照官方修复、实际测试日志和完整审查解释，填写判读表的 `target_issue_detected`、`matched_finding_ids`、`reason`、`adjudicator`。`true` 必须对应真实保留问题 ID；含糊的断言优化、格式建议或其他邻近问题不能当成已知缺陷命中。

保存为 `adjudications.json` 后评分：

```bash
.venv/bin/python evaluation/bugsinpy_score.py --run outputs/bugsinpy-20-new --adjudications outputs/bugsinpy-20-new/adjudications.json
```

有效缺陷对必须同时满足：两版本审查完成、成对复现成功、两版本语义判读明确。未完成或未复现项列出排除理由，不能当作“没有问题”。

- 已知缺陷检出率：缺陷版正确描述参考问题的比例。
- 修复后同问题误报率：修复版仍报告同一参考问题的比例。
- 成对区分正确率：缺陷版检出且修复版不再报告同问题的比例。
- 另列完成率、复现成功率、模型调用、token 与耗时。

修复版本可能存在其他缺陷，额外候选不会自动归为误报。因此这些指标不是全仓库精确率。模型辅助语义判读需要注明判读者并供人类复查；默认空白判读表不会产生准确率。

实际运行结果见 [结果与限制](../demo/bugsinpy/README.md)。仓库保留80份原始 JSON 审查报告、判读依据与测试证据；完整 HTML/Markdown 报告、大体积源码快照只保存在本地 `outputs/`，不上传密钥或运行环境。
