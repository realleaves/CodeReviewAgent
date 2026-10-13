# 验证记录

验证日期：2026-10-11。环境：Python 3.13.5、Git 2.34.1；依赖完整版本见 requirements.txt。使用工作区现有 deepseek-flash API 配置完成实际调用，凭据未写入源码或报告。

## 功能与依赖

- `python -m pytest -q tests`：25 passed。包含真实 Ruff/Bandit 调用、路径与行号校验、工具轮数收尾、同位置诊断去重、模型预算/输出截断、失败熔断和报告转义。
- `python -m ruff check --isolated --select F,E9 main.py src tests evaluation`：通过。
- `python -m pip check`：无依赖冲突。
- HelloAgents 0.2.9 有一条上游 Pydantic Config 弃用警告，不影响本次运行；没有修改第三方源码。

## 真实 GitHub 仓库

仓库： https://github.com/psf/requests

commit：611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60。

实际命令：

```bash
python main.py review https://github.com/psf/requests \
  --scope src/requests --max-files 3 --max-calls 20
```

完成 __init__.py、__version__.py、_internal_utils.py 三个文件的全部分块，执行12次模型调用，分析耗时35.833秒（不含仓库获取）。19个已索引Python文件中完成3个，覆盖15.8%，按范围限制标为partial；失败记录为空。

保留5个候选项：4个被模型复核为有代码依据、1个待确认；驳回19个候选项。该结果是静态诊断和模型判断，未执行 requests 程序或运行复现。保留项需要维护者结合项目设计继续判断，不能当成5个已确认漏洞。

另对 src/requests/api.py 完成单文件范围的实际审查，状态completed，未保留候选项。结论仅适用于该文件范围。

## 已知缺陷与正常代码

examples/buggy_code.py 的三个已知问题均被检出并复核：

- 第6行：允许空输入的 average 会除零。
- 第9行：默认列表导致 collect 跨调用共享状态。
- 第17行：不可信 username 直接拼接到 SQL。

examples/clean_code.py 无保留问题。静态规则与模型发现合并后共3项，工具证据仍可在JSON追溯。实际模型调用3次，运行耗时21.197秒。为验证去重，最终报告使用既有实际候选和复核结果执行新版后处理；原始调用与复核轨迹保留。

## 三种方式对比

最终版本运行 evaluation/cases.json 前4个样本：2个缺陷、2个正常。三种模式均完成4/4样本。

| 模式 | 命中已知缺陷 | 额外bug候选 | 调用 | 耗时 |
|---|---:|---:|---:|---:|
| direct | 2 | 1 | 4 | 5.772s |
| assisted | 2 | 0 | 4 | 5.713s |
| full | 2 | 0 | 6 | 7.484s |

direct 的额外候选认为正常 average 的空输入返回 int 0、非空返回 float 是bug；样本约定没有要求统一float返回类型，因此该候选缺少必要契约依据。自动评分仅按位置与类别粗匹配；这组数据是冒烟验证，不足以推断泛化准确率或复核的普遍收益。每个样本报告和原始匹配信息保留在本工作区 outputs/evaluation-final/。

## HTML 报告

浏览器插件没有可用连接，使用本机独立 Firefox headless 配置作验证。桌面1440px和手机390px下，各8项实际DOM检查通过：全部/保留问题、风险和状态筛选、无匹配搜索、空结果提示、文件搜索、视口横向溢出。截图已目视检查。验收脚本中的PASS横条只出现在验收截图，正式报告不包含此横条。

原始检查结果和截图见 demo/browser-qa/。没有在用户已有浏览器配置中登录或读取会话。

## BugsInPy 真实缺陷验证（2026-10-11）

固定官方数据 commit `11c5f1eea954a42132cfd06bf257766a7963e0fd`，预选 PySnooper 1–3、tornado 1–8、youtube-dl 1–9。使用现有 `deepseek-flash` 配置，20个缺陷×2版本×2模式共80次审查，79次完整完成，257次真实模型调用。

19/20个缺陷在隔离容器中实现指定测试的缺陷版失败、修复版通过。PySnooper-2 因重建快照依赖不一致排除；PySnooper-1/direct 因修复版模型 JSON 无效排除。补齐 PySnooper 历史依赖后的测试复跑保留初次日志，并未再次调用模型或修改目标代码。

对照参考补丁、测试和解释的模型辅助判读：direct 检出4/18个有效缺陷（22.2%），full 检出3/19个（15.8%）；共同有效的18对上分别为4和3。限定已知位置窗口，不代表全仓库检测能力；语义判读仍需人类复查。详细依据、80份原始 JSON、复现日志和排除理由见 [demo/bugsinpy/README.md](demo/bugsinpy/README.md)。

新增评测协议、固定清单、可重复准备/审查/隔离复现/只复跑测试/显式语义评分入口。格式纠正使用额外实际模型调用并计入预算，仍不能保证服务商总返回有效 JSON。单元和集成检查覆盖补丁解析、快照重建、数据泄漏排除、窗口预算、JSON纠正、测试命令限制及评分证据约束。

项目 pytest 的收集范围固定为 `tests/`，避免下载的历史仓库测试混入当前 Python 环境；历史缺陷复现由 Docker 入口单独执行。此前默认全目录收集导致1140项历史测试收集错误，该次未运行测试，不能作为项目测试结果。

最终项目检查：`pytest -q` 为42项通过，只有 HelloAgents 上游 Pydantic 弃用警告；Ruff F/E9检查通过，新增评测文件格式检查通过。80份上传的 JSON 报告与本地原报告哈希一致，文档链接与报告路径已核对。

## 复现证据首版检查点（2026-10-13）

CLI默认 evidence，新增行为审查、最小 unittest 生成、契约引用检查、两次隔离执行、模型契约核验和保存证据复跑。仅 reproduced 进入正式缺陷计数；静态建议和未证实候选单列。保留旧推断模式作对照。

当前代码实际运行 `main.py review examples/evidence --local --max-files 2 --max-calls 16`，使用已有 deepseek-flash 配置，4次模型调用，状态 completed。按文档承诺空输入返回0.0的平均值实现，在两个全新容器中都产生 ZeroDivisionError；正常实现无候选。实际镜像中的 Python为3.13.16，镜像 ID和日志见 [实际报告](demo/evidence-checkpoint/report.md)。从上传证据运行 reproduce 命令再次观察到同一失败，0次模型调用。

54项项目测试通过，Ruff F/E9检查通过，只有原有上游 Pydantic 弃用警告。新增检查涵盖伪造契约、无条件失败、无关失败、导入错误、测试通过、两次执行、核验预算不足、一次纠正及源码哈希变化。

真实缺陷首轮试跑已完成3个缺陷对共6次审查，暴露导入白名单和输出格式限制，结果留在本地 outputs/evidence-real-pilot。8个新固定样本初次试跑在修正入口时中止；完整复跑与参考问题判读未完成。这个提交是用户要求先上传的实现检查点，不能声称新版真实缺陷检出率已经提升，也未完成新版HTML浏览器交互回归。
