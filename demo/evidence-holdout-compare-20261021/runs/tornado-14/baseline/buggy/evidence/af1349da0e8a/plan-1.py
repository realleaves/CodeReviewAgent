import unittest
from tornado.ioloop import IOLoop


class ReproductionTest(unittest.TestCase):
    def test_reproduction(self):
        IOLoop.clear_current()
        loop = IOLoop()
        IOLoop.clear_current()
        try:
            loop.initialize(make_current=True)
        finally:
            pass
        self.assertIs(IOLoop.current(instance=False), loop)
        IOLoop.clear_current()
