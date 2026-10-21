import os
import tempfile
import unittest

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
            # 按 RFC 7233，后缀长度超过文件大小时应返回整个文件（start 夹紧到 0），
            # 而不是产生负的 seek 偏移。
            start = -100
            end = None
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

            # 若 start 为负，get_content 会执行 file.seek(负数) 抛 OSError
            with open(path, "rb") as f:
                with self.assertRaises(OSError):
                    f.seek(start)
        finally:
            os.unlink(path)
