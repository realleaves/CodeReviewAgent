import os
import tempfile
import unittest

import pysnooper


class ReproductionTest(unittest.TestCase):
    def test_reproduction(self):
        fd, path = tempfile.mkstemp()
        os.close(fd)
        try:
            @pysnooper.snoop(path)
            def f():
                x = 1
                return x

            f()
            with open(path, 'r') as fh:
                content = fh.read()
            self.assertIn('x', content)
        finally:
            if os.path.exists(path):
                os.remove(path)
