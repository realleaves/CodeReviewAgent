import unittest
from tornado.ioloop import IOLoop


class ReproductionTest(unittest.TestCase):
    def test_reproduction(self):
        IOLoop.clear_current()
        self.assertIsNone(IOLoop.current(instance=False))
        loop = IOLoop(make_current=True)
        try:
            self.assertIs(IOLoop.current(instance=False), loop)
        finally:
            IOLoop.clear_current()
            loop.close(all_fds=True)
