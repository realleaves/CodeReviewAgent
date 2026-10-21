# GitHub 仓库代码审查报告

- 仓库：https://github.com/tornadoweb/tornado
- 分支：blinded-snapshot
- Commit：`a8420fc681c5423d072978f00eab4d0645057d16`
- 状态：**partial**；模式：evidence；模型：deepseek-flash
- 完成语义审查：0/62 个已索引 Python 文件
- 调用：3；耗时：7.021 秒

## 范围与限制

- 固定已知候选与原始生成计划的开发集诊断，不是Agent独立发现或全仓库审查。
- 模型调用只包含本轮修正/核验，原始计划由2026-10-14记录重放。
- 两种条件使用同一新执行判定，仅切换一次反馈修正；参考修复仅由评测侧对照。

## 已复现缺陷（0）

正式缺陷附测试与运行证据；其余候选和静态建议单列，不表示已经证实。

## 待验证候选与静态建议

### [中] suffix range 长度超过文件大小时 start 变为负数导致 416 判定失效

- 位置：`tornado/web.py:2603`
- 来源：llm
- 复核：待验证 — 尚未复核；未运行待审代码。
- 问题：当 Range 头为后缀形式（如 bytes=-N）时，_parse_request_range 返回 (start=-N, end=None)。第 2603 行的不可满足判定只检查 start >= size 或 end == 0，对负 start 不成立，因此不会返回 416。随后第 2611-2612 行执行 start += size，若 N > size，start 仍为负数。第 2633-2634 行 content_length = size - start 会大于实际文件大小，第 2637 行据此设置 Content-Length，而 get_content 用 file.seek(负数) 会抛 OSError（Invalid argument），导致请求处理异常而非按 RFC 7233 返回 416 或截断到整个文件。
- 触发条件：请求一个大小为 size 的静态文件，携带 Range: bytes=-{N}，其中 N > size（例如文件 10 字节，Range: bytes=-100）。
- 依据：第 2603 行条件 `(start is not None and start >= size) or end == 0` 对负 start 为 False；第 2611-2612 行 `if start is not None and start < 0: start += size` 后 start 仍为负；第 2634 行 `content_length = size - start` 得到大于 size 的值；get_content 第 2801 行 `file.seek(start)` 传入负数。
- 修复建议：在后缀范围处理后将 start 夹紧到 0（如 start = max(0, start + size)），或在 start + size < 0 时返回 416。
- 验证方式：执行未形成与候选对应的有效失败；不作为正式缺陷。

```python
2601:         if request_range:
2602:             start, end = request_range
2603:             if (start is not None and start >= size) or end == 0:
2604:                 # As per RFC 2616 14.35.1, a range is not satisfiable only: if
2605:                 # the first requested byte is equal to or greater than the
```

- 复现状态：unrelated_failure
- 证据说明：执行未形成与候选对应的有效失败；不作为正式缺陷。

[运行证据](evidence/3e533c03160d/evidence.json)

复现测试：

```python
import os
import tempfile
import unittest

from tornado.httputil import _parse_request_range
from tornado.web import StaticFileHandler


class ReproductionTest(unittest.TestCase):
    def test_reproduction(self):
        # 构造一个 10 字节的临时文件
        fd, path = tempfile.mkstemp()
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(b"0123456789")
            size = os.path.getsize(path)
            self.assertEqual(size, 10)

            # 后缀范围 bytes=-100，N=100 > size=10
            # _parse_request_range 返回 (-100, None)
            request_range = _parse_request_range("bytes=-100")
            self.assertEqual(request_range, (-100, None))
            start, end = request_range

            # 模拟 web.py 第 2603 行的不可满足判定
            not_satisfiable = (start is not None and start >= size) or end == 0
            self.assertFalse(not_satisfiable)
            # 模拟 web.py 第 2611-2612 行的修正
            if start is not None and start < 0:
                start += size
            # 修正后 start 仍为负，这是缺陷所在
            self.assertGreaterEqual(
                start,
                0,
                "suffix range 长度超过文件大小时 start 修正后仍为负: %r" % (start,),
            )

            # 直接调用目标函数 get_content，传入负 start，
            # 真实实现会执行 file.seek(负数) 抛 OSError
            with self.assertRaises(OSError):
                list(StaticFileHandler.get_content(path, start, end))
        finally:
            os.unlink(path)

```

执行1：镜像 `sha256:a255ffcb469f2ec40f2958a76beb0c2bbebfe92ce9af67a9b48d84b4cb695ac8`；Python `3.7.17`；状态 `unrelated_failure`；测试版本 1。

```text

CODE_REVIEW_EXECUTION={"python": "3.7.17", "tests_run": 1, "failures": 1, "errors": 0, "skipped": 0, "load_error": null, "observations": [{"test": "generated_reproduction.ReproductionTest.test_reproduction", "outcome": "failure", "exception_type": "AssertionError", "message": "-90 not greater than or equal to 0 : suffix range \u957f\u5ea6\u8d85\u8fc7\u6587\u4ef6\u5927\u5c0f\u65f6 start \u4fee\u6b63\u540e\u4ecd\u4e3a\u8d1f: -90", "traceback": "Traceback (most recent call last):\n  File \"/usr/local/lib/python3.7/unittest/case.py\", line 59, in testPartExecutor\n    yield\n  File \"/usr/local/lib/python3.7/unittest/case.py\", line 628, in run\n    testMethod()\n  File \"/harness/test_reproduction.py\", line 33, in test_reproduction\n    \"suffix range \u957f\u5ea6\u8d85\u8fc7\u6587\u4ef6\u5927\u5c0f\u65f6 start \u4fee\u6b63\u540e\u4ecd\u4e3a\u8d1f: %r\" % (start,),\n  File \"/usr/local/lib/python3.7/unittest/case.py\", line 1257, in assertGreaterEqual\n    self.fail(self._formatMessage(msg, standardMsg))\n  File \"/usr/local/lib/python3.7/unittest/case.py\", line 693, in fail\n    raise self.failureException(msg)\nAssertionError: -90 not greater than or equal to 0 : suffix range \u957f\u5ea6\u8d85\u8fc7\u6587\u4ef6\u5927\u5c0f\u65f6 start \u4fee\u6b63\u540e\u4ecd\u4e3a\u8d1f: -90\n", "traceback_frames": [{"path": "/usr/local/lib/python3.7/unittest/case.py", "line": 59, "function": "testPartExecutor"}, {"path": "/usr/local/lib/python3.7/unittest/case.py", "line": 628, "function": "run"}, {"path": "/harness/test_reproduction.py", "line": 33, "function": "test_reproduction"}, {"path": "/usr/local/lib/python3.7/unittest/case.py", "line": 1257, "function": "assertGreaterEqual"}, {"path": "/usr/local/lib/python3.7/unittest/case.py", "line": 693, "function": "fail"}]}], "target_lines": [], "target_calls": [], "target_trace_scope": "test_execution"}

```

执行2：镜像 `sha256:a255ffcb469f2ec40f2958a76beb0c2bbebfe92ce9af67a9b48d84b4cb695ac8`；Python `3.7.17`；状态 `unrelated_failure`；测试版本 2。

```text

CODE_REVIEW_EXECUTION={"python": "3.7.17", "tests_run": 1, "failures": 1, "errors": 0, "skipped": 0, "load_error": null, "observations": [{"test": "generated_reproduction.ReproductionTest.test_reproduction", "outcome": "failure", "exception_type": "AssertionError", "message": "-90 not greater than or equal to 0 : suffix range \u957f\u5ea6\u8d85\u8fc7\u6587\u4ef6\u5927\u5c0f\u65f6 start \u4fee\u6b63\u540e\u4ecd\u4e3a\u8d1f: -90", "traceback": "Traceback (most recent call last):\n  File \"/usr/local/lib/python3.7/unittest/case.py\", line 59, in testPartExecutor\n    yield\n  File \"/usr/local/lib/python3.7/unittest/case.py\", line 628, in run\n    testMethod()\n  File \"/harness/test_reproduction.py\", line 35, in test_reproduction\n    \"suffix range \u957f\u5ea6\u8d85\u8fc7\u6587\u4ef6\u5927\u5c0f\u65f6 start \u4fee\u6b63\u540e\u4ecd\u4e3a\u8d1f: %r\" % (start,),\n  File \"/usr/local/lib/python3.7/unittest/case.py\", line 1257, in assertGreaterEqual\n    self.fail(self._formatMessage(msg, standardMsg))\n  File \"/usr/local/lib/python3.7/unittest/case.py\", line 693, in fail\n    raise self.failureException(msg)\nAssertionError: -90 not greater than or equal to 0 : suffix range \u957f\u5ea6\u8d85\u8fc7\u6587\u4ef6\u5927\u5c0f\u65f6 start \u4fee\u6b63\u540e\u4ecd\u4e3a\u8d1f: -90\n", "traceback_frames": [{"path": "/usr/local/lib/python3.7/unittest/case.py", "line": 59, "function": "testPartExecutor"}, {"path": "/usr/local/lib/python3.7/unittest/case.py", "line": 628, "function": "run"}, {"path": "/harness/test_reproduction.py", "line": 35, "function": "test_reproduction"}, {"path": "/usr/local/lib/python3.7/unittest/case.py", "line": 1257, "function": "assertGreaterEqual"}, {"path": "/usr/local/lib/python3.7/unittest/case.py", "line": 693, "function": "fail"}]}], "target_lines": [], "target_calls": [], "target_trace_scope": "test_execution"}

```

## 覆盖范围

| 文件 | 静态检查 | 语义审查 | 完成分块 |
|---|---|---|---|

## 失败记录

```json
[]
```

## 驳回的问题（0）


## 跳过文件

{}

逐文件跳过原因、模型调用用量和复核轨迹见 report.json / run.json。
