import os
import tempfile
import unittest

import pysnooper


class ReproductionTest(unittest.TestCase):
    def test_reproduction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, 'log.txt')

            @pysnooper.snoop(log_path)
            def target(x):
                y = x + 1
                return y

            result = target(1)
            self.assertEqual(result, 2)
            self.assertTrue(os.path.exists(log_path))
            with open(log_path, 'r') as f:
                content = f.read()
            self.assertIn('y', content)
