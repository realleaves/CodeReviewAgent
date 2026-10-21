# GitHub 仓库代码审查报告

- 仓库：https://github.com/ytdl-org/youtube-dl
- 分支：blinded-snapshot
- Commit：`435e382423f860aca82a58d7c3db58cbfa242b40`
- 状态：**completed**；模式：evidence；模型：deepseek-flash
- 完成语义审查：0/837 个已索引 Python 文件
- 调用：6；耗时：16.981 秒

## 范围与限制

- BugsInPy定范围评测：使用参考补丁选择代码窗口，Agent未看到补丁、测试、标签或另一版本。
- completed仅表示所选窗口及复核完成；完整文件审查数为0，不表示全仓库或全文件审查。
- 修复版本可能含其他缺陷；额外发现不自动计为误报。
- evidence模式使用Agent自行生成的测试与隔离执行，契约语义仍由模型核验；官方回归测试不提供给Agent。

## 已复现缺陷（1）

正式缺陷附测试与运行证据；其余候选和静态建议单列，不表示已经证实。

### [高] 字符串过滤器取反逻辑错误：对函数对象取非而非调用结果

- 位置：`youtube_dl/YoutubeDL.py:1081`
- 来源：llm
- 复核：已复现 — 证据充分。源码第1080-1083行确实为 `op = lambda attr, value: not str_op`，str_op 是函数对象，Python 中函数对象真值恒为 True，故 `not str_op` 恒为 False，且未调用 str_op(attr, value)。取反过滤器语义应为比较结果的逻辑非，即 not str_op(attr, value)。测试真实调用 _build_format_filter('!ext=mp4') 并对 {'ext':'mp4'} 断言 False，实际返回 True（AssertionError: True is not false），与候选描述的失败一致。输入 '!ext=mp4' 符合正则语法，前置条件有效，断言基于取反语义的语言规则，未假设未约定语义。缺陷成立。
- 问题：在字符串过滤器分支中，当 filter_spec 含取反前缀（如 '!ext=mp4'）时，代码执行 `op = lambda attr, value: not str_op`。str_op 是函数对象，其真值恒为 True，因此 `not str_op` 恒为 False。该 lambda 无论 attr/value 为何都返回 False，导致所有带取反的字符串过滤器把每个格式都判为不匹配，过滤结果与预期完全相反。正确写法应为 `op = lambda attr, value: not str_op(attr, value)`。
- 触发条件：调用 _build_format_filter('!ext=mp4') 得到 _filter，再对任意格式 f（如 {'ext':'mp4'} 或 {'ext':'webm'}）调用 _filter(f)，均返回 False。
- 依据：第1080-1083行：`if m.group('negation'): op = lambda attr, value: not str_op` else: `op = str_op`。lambda 体内 `not str_op` 对函数对象取非，恒为 False，未调用 str_op(attr, value)。
- 修复建议：改为 `op = lambda attr, value: not str_op(attr, value)`，使取反作用于实际比较结果。
- 验证方式：两次独立隔离执行出现同类型失败并触达目标代码；预期行为经模型对照引用原文核验，仍供维护者复查。

```python
1079:                 str_op = STR_OPERATORS[m.group('op')]
1080:                 if m.group('negation'):
1081:                     op = lambda attr, value: not str_op
1082:                 else:
1083:                     op = str_op
```

- 复现状态：reproduced
- 证据说明：证据充分。源码第1080-1083行确实为 `op = lambda attr, value: not str_op`，str_op 是函数对象，Python 中函数对象真值恒为 True，故 `not str_op` 恒为 False，且未调用 str_op(attr, value)。取反过滤器语义应为比较结果的逻辑非，即 not str_op(attr, value)。测试真实调用 _build_format_filter('!ext=mp4') 并对 {'ext':'mp4'} 断言 False，实际返回 True（AssertionError: True is not false），与候选描述的失败一致。输入 '!ext=mp4' 符合正则语法，前置条件有效，断言基于取反语义的语言规则，未假设未约定语义。缺陷成立。

[运行证据](evidence/9758e8ca5215/evidence.json)

复现测试：

```python
import unittest
from youtube_dl.YoutubeDL import YoutubeDL


class ReproductionTest(unittest.TestCase):
    def test_reproduction(self):
        ydl = YoutubeDL({'quiet': True})
        f = ydl._build_format_filter('!ext=mp4')
        self.assertFalse(f({'ext': 'mp4'}))
        self.assertTrue(f({'ext': 'webm'}))

```

执行1：镜像 `sha256:a255ffcb469f2ec40f2958a76beb0c2bbebfe92ce9af67a9b48d84b4cb695ac8`；Python `3.7.17`；状态 `failure_observed`。

```text

CODE_REVIEW_EXECUTION={"python": "3.7.17", "tests_run": 1, "failures": 1, "errors": 0, "skipped": 0, "load_error": null, "observations": [{"test": "generated_reproduction.ReproductionTest.test_reproduction", "outcome": "failure", "exception_type": "AssertionError", "message": "True is not false", "traceback": "Traceback (most recent call last):\n  File \"/usr/local/lib/python3.7/unittest/case.py\", line 59, in testPartExecutor\n    yield\n  File \"/usr/local/lib/python3.7/unittest/case.py\", line 628, in run\n    testMethod()\n  File \"/harness/test_reproduction.py\", line 9, in test_reproduction\n    self.assertFalse(f({'ext': 'mp4'}))\n  File \"/usr/local/lib/python3.7/unittest/case.py\", line 699, in assertFalse\n    raise self.failureException(msg)\nAssertionError: True is not false\n"}], "target_lines": [4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 29, 31, 45, 95, 96, 97, 98, 99, 100, 108, 110, 114, 319, 321, 322, 332, 333, 334, 335, 336, 337, 339, 341, 343, 344, 345, 346, 347, 348, 349, 350, 353, 355, 356, 358, 359, 363, 365, 369, 370, 371, 373, 400, 401, 410, 415, 417, 418, 419, 421, 428, 431, 433, 449, 451, 452, 456, 468, 472, 473, 475, 480, 484, 497, 501, 504, 515, 525, 536, 545, 554, 558, 564, 594, 611, 623, 630, 719, 761, 767, 768, 829, 837, 1032, 1036, 1037, 1038, 1039, 1040, 1041, 1043, 1048, 1049, 1050, 1063, 1065, 1066, 1067, 1068, 1070, 1075, 1076, 1077, 1078, 1079, 1080, 1083, 1085, 1088, 1089, 1090, 1092, 1093, 1095, 1119, 1384, 1402, 1407, 1644, 1693, 1992, 2017, 2034, 2040, 2062, 2073, 2092, 2101, 2102, 2118, 2174, 2188, 2200, 2211, 2217, 2218, 2219, 2293, 2294, 2295, 2297, 2298, 2300, 2301, 2308, 2309, 2315, 2317, 2319, 2321, 2322, 2323, 2324, 2330, 2332, 2334, 2336, 2337, 2342, 2343, 2345, 2355, 2361], "target_calls": [["<module>", 4], ["YoutubeDL", 114], ["__init__", 339], ["_build_format_filter", 1032], ["_filter", 1088], ["_setup_opener", 2293], ["add_default_info_extractors", 468], ["add_info_extractor", 449], ["check_deprecated", 358], ["print_debug_header", 2217]]}

```

执行2：镜像 `sha256:a255ffcb469f2ec40f2958a76beb0c2bbebfe92ce9af67a9b48d84b4cb695ac8`；Python `3.7.17`；状态 `failure_observed`。

```text

CODE_REVIEW_EXECUTION={"python": "3.7.17", "tests_run": 1, "failures": 1, "errors": 0, "skipped": 0, "load_error": null, "observations": [{"test": "generated_reproduction.ReproductionTest.test_reproduction", "outcome": "failure", "exception_type": "AssertionError", "message": "True is not false", "traceback": "Traceback (most recent call last):\n  File \"/usr/local/lib/python3.7/unittest/case.py\", line 59, in testPartExecutor\n    yield\n  File \"/usr/local/lib/python3.7/unittest/case.py\", line 628, in run\n    testMethod()\n  File \"/harness/test_reproduction.py\", line 9, in test_reproduction\n    self.assertFalse(f({'ext': 'mp4'}))\n  File \"/usr/local/lib/python3.7/unittest/case.py\", line 699, in assertFalse\n    raise self.failureException(msg)\nAssertionError: True is not false\n"}], "target_lines": [4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 29, 31, 45, 95, 96, 97, 98, 99, 100, 108, 110, 114, 319, 321, 322, 332, 333, 334, 335, 336, 337, 339, 341, 343, 344, 345, 346, 347, 348, 349, 350, 353, 355, 356, 358, 359, 363, 365, 369, 370, 371, 373, 400, 401, 410, 415, 417, 418, 419, 421, 428, 431, 433, 449, 451, 452, 456, 468, 472, 473, 475, 480, 484, 497, 501, 504, 515, 525, 536, 545, 554, 558, 564, 594, 611, 623, 630, 719, 761, 767, 768, 829, 837, 1032, 1036, 1037, 1038, 1039, 1040, 1041, 1043, 1048, 1049, 1050, 1063, 1065, 1066, 1067, 1068, 1070, 1075, 1076, 1077, 1078, 1079, 1080, 1083, 1085, 1088, 1089, 1090, 1092, 1093, 1095, 1119, 1384, 1402, 1407, 1644, 1693, 1992, 2017, 2034, 2040, 2062, 2073, 2092, 2101, 2102, 2118, 2174, 2188, 2200, 2211, 2217, 2218, 2219, 2293, 2294, 2295, 2297, 2298, 2300, 2301, 2308, 2309, 2315, 2317, 2319, 2321, 2322, 2323, 2324, 2330, 2332, 2334, 2336, 2337, 2342, 2343, 2345, 2355, 2361], "target_calls": [["<module>", 4], ["YoutubeDL", 114], ["__init__", 339], ["_build_format_filter", 1032], ["_filter", 1088], ["_setup_opener", 2293], ["add_default_info_extractors", 468], ["add_info_extractor", 449], ["check_deprecated", 358], ["print_debug_header", 2217]]}

```

## 待验证候选与静态建议

### [低] B904: Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling

- 位置：`youtube_dl/YoutubeDL.py:1058`
- 来源：ruff B904
- 复核：未复核 — 尚未复核；未运行待审代码。
- 问题：Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling
- 触发条件：触发条件需结合业务调用确认。
- 依据：ruff B904: Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling
- 修复建议：根据诊断检查对应代码。
- 验证方式：静态诊断或代码推断；未执行复现测试。

```python
1056:                     comparison_value = parse_filesize(m.group('value') + 'B')
1057:                 if comparison_value is None:
1058:                     raise ValueError(
1059:                         'Invalid value %r in format specification %r' % (
1060:                             m.group('value'), filter_spec))
```

## 覆盖范围

| 文件 | 静态检查 | 语义审查 | 完成分块 |
|---|---|---|---|
| youtube_dl/YoutubeDL.py | completed | window_completed | 1/1 |

## 失败记录

```json
[]
```

## 驳回的问题（0）


## 跳过文件

{"unsupported_language_or_resource": 62, "sensitive_file": 1, "benchmark_tests_hidden": 31}

逐文件跳过原因、模型调用用量和复核轨迹见 report.json / run.json。
