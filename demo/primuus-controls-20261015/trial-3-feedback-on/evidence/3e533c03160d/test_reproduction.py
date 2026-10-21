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
