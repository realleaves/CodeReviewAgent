import unittest
from youtube_dl.YoutubeDL import YoutubeDL


class ReproductionTest(unittest.TestCase):
    def test_reproduction(self):
        ydl = YoutubeDL({'quiet': True})
        f = ydl._build_format_filter('ext!=mp4')
        self.assertFalse(f({'ext': 'mp4'}))
        self.assertTrue(f({'ext': 'webm'}))
