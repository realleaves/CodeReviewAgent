# GitHub 仓库代码审查报告

- 仓库：local-benchmark
- 分支：blinded-snapshot
- Commit：`snapshot`
- 状态：**completed**；模式：evidence；模型：deepseek-flash
- 完成语义审查：0/62 个已索引 Python 文件
- 调用：1；耗时：1.473 秒

## 范围与限制

- BugsInPy定范围评测：使用参考补丁选择代码窗口，Agent未看到补丁、测试、标签或另一版本。
- completed仅表示所选窗口及复核完成；完整文件审查数为0，不表示全仓库或全文件审查。
- 修复版本可能含其他缺陷；额外发现不自动计为误报。
- evidence模式使用Agent自行生成的测试与隔离执行，契约语义仍由模型核验；官方回归测试不提供给Agent。

## 已复现缺陷（0）

正式缺陷附测试与运行证据；其余候选和静态建议单列，不表示已经证实。

本次已完成的分析未保留候选问题。请结合覆盖范围和失败记录解读；不代表仓库没有问题。

## 覆盖范围

| 文件 | 静态检查 | 语义审查 | 完成分块 |
|---|---|---|---|
| tornado/ioloop.py | completed | window_completed | 1/1 |

## 失败记录

```json
[]
```

## 驳回的问题（0）


## 跳过文件

{"unsupported_language_or_resource": 168, "sensitive_file": 1, "benchmark_tests_hidden": 44}

逐文件跳过原因、模型调用用量和复核轨迹见 report.json / run.json。
