# BugsInPy 实际评测结果

2026-10-11，使用用户配置的 `api.deepseek.com` / `deepseek-flash`，预选20个真实缺陷，分别审查缺陷版与修复版，比较 `direct` 和 `full`。没有在模型审查输入中提供补丁、测试、缺陷标签或另一版本。

**结果显示当前 Agent 对真实缺陷的检出能力仍然偏弱；这批样本中 full 没有优于直接审查。** 已知缺陷位置用于选择代码窗口，所以这不是全仓库定位测试，也不是 BugsInPy 官方排行榜分数。

| 项目 | direct | full |
|---|---:|---:|
| 完整审查 / 计划审查 | 39/40 | 40/40 |
| 有效缺陷对 / 计划缺陷对 | 18/20 | 19/20 |
| 已知缺陷检出 | 4/18（22.2%） | 3/19（15.8%） |
| 修复后报告同一参考缺陷 | 0/18 | 0/19 |
| 缺陷检出且修复后不报告同问题 | 4/18 | 3/19 |
| 实际模型调用 | 64 | 193 |
| 输入 token | 113,774 | 1,205,816 |
| 输出 token | 44,791 | 85,491 |
| 累计审查耗时 | 277.802 s | 574.574 s |

共79/80次审查完整完成，257次模型调用。耗时为各次审查耗时之和，不包含下载和复现测试。19/20个缺陷实现了指定测试在缺陷版失败、修复版通过。模型调用、token、失败记录均来自实际运行，没有估算 API 费用。

两个模式共同有效的18个缺陷对上，direct 检出4个，full 检出3个。direct 检出 PySnooper-3、tornado-4、tornado-6、youtube-dl-6；full 检出 PySnooper-3、youtube-dl-5、youtube-dl-6。多个候选匹配同一参考问题仍只计一个缺陷。

## 判读与限制

评分由 **Codex 对照参考补丁、测试证据与候选解释进行模型辅助判读，人类复查待完成**。所有理由和匹配 ID 均在 [adjudications.json](adjudications.json)，规则在 [评测协议](../../evaluation/BUGSINPY.md) 和 [参考缺陷说明](../../evaluation/bugsinpy-rubric.json)。这批是固定的小样本结果，不能据此断言双 Agent 总是更差。

“修复后同问题报告为零”仅按同一触发条件和失败原因判断。它不表示所有候选都正确：报告仍包含其他待核对问题，甚至对修复行为提出错误建议。尤其 tornado-4 的后缀范围和 youtube-dl-7 的转义处理，判读理由列出了与参考问题的区别，需人工复查。位置接近、相同函数名或泛化的 assert 建议不计作检出。youtube-dl-5 的 full 命中的是补丁修复的 PM 回退偏移子问题，没有识别 tuple.timetuple() 异常。

排除项：

- PySnooper-1 / direct：修复版一次返回无效 JSON，审查为 partial，该缺陷对未计分，保留失败证据。
- PySnooper-2 / 两模式：指定重建协议下测试无法收集，缺少 tests.mini_toolbox，修复快照又缺 pycompat.PY2。补齐测试依赖仍失败，未修改代码或测试来掩盖问题，两模式均排除。

PySnooper-3 初次因缺少 `future` 无法启动测试。补齐项目声明的 `future`、`decorator` 后，三个 PySnooper 样本使用同一新镜像只复跑测试：1、3复现成功，2仍失败。初次证据保存在 `reproduction/`，新证据保存在 `reproduction-attempts/`；`results.json` 中的 `reproduction_evidence` 指向有效复跑记录。模型报告未重跑或改写。PySnooper-1 的两版本统一使用 ASCII locale，避免 UTF-8 默认编码掩盖原缺陷。

## 查看证据

- [逐次运行汇总](comparison.md)、[结构化结果](results.json)、[评分](scores.md)。
- [PySnooper-3 / full 缺陷版 HTML](reviews/PySnooper-3/full/buggy/report.html) 与 [修复版 HTML](reviews/PySnooper-3/full/fixed/report.html)。下载到本地后用浏览器打开 HTML；GitHub 页面显示的是源码。
- `reviews/` 保留80份原始 JSON 报告，包括候选、驳回、模型调用和工具读取记录；[哈希清单](artifact-provenance.json) 可验证它们与本地原报告逐字节一致。
- [数据及源码哈希](run_config.json)、[选定版本](selection.json)，以及 `reproduction/`、`reproduction-attempts/` 中的测试日志、镜像 ID、解释器版本和退出码。

大体积仓库快照及全部 HTML/Markdown 报告保留在本机 `outputs/bugsinpy-20/`。复跑命令见 [evaluation/BUGSINPY.md](../../evaluation/BUGSINPY.md)。
