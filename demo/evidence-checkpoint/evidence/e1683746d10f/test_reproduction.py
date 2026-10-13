import unittest

from buggy import average


class ReproductionTest(unittest.TestCase):
    def test_reproduction(self):
        self.assertEqual(average([]), 0.0)
