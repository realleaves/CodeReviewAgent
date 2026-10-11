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
