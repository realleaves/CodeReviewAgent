import asyncio
import os
import tempfile
import unittest

from tornado.httpserver import HTTPRequest
from tornado.httputil import HTTPHeaders
from tornado.web import Application, StaticFileHandler


class ReproductionTest(unittest.TestCase):
    def test_reproduction(self):
        fd, path = tempfile.mkstemp()
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(b"0123456789")
            size = os.path.getsize(path)
            self.assertEqual(size, 10)

            root, filename = os.path.split(path)
            app = Application()
            handler = StaticFileHandler(app, HTTPRequest(
                method="GET",
                uri="/" + filename,
                headers=HTTPHeaders({"Range": "bytes=-100"}),
            ))
            handler.root = root

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(handler.get("/" + filename))
            finally:
                loop.close()

            # 后缀长度超过文件大小时，start 修正后不应为负，
            # 否则 get_content 中 file.seek(负数) 会抛 OSError。
            self.assertGreaterEqual(
                handler._status_code,
                200,
                "请求处理未正常完成，状态码: %r" % (handler._status_code,),
            )
        finally:
            os.unlink(path)
