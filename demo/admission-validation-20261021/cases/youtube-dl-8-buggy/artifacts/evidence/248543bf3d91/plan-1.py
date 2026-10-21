import unittest
from youtube_dl import YoutubeDL


class ReproductionTest(unittest.TestCase):
    def test_reproduction(self):
        ydl = YoutubeDL({'quiet': True})
        for spec in (',best', 'best,,worst'):
            with self.assertRaises(SyntaxError):
                ydl.build_format_selector(spec)
