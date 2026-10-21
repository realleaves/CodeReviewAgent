import json
import unittest

from youtube_dl.extractor.youtube import YoutubeIE


class ReproductionTest(unittest.TestCase):
    def test_reproduction(self):
        def chapter(ms, title):
            return {'chapterRenderer': {'timeRangeStartMillis': ms, 'title': {'simpleText': title}}}

        chapters = [chapter(0, 'a'), chapter(10000, 'b'), chapter(20000, 'c')]
        response = {
            'playerOverlays': {
                'playerOverlayRenderer': {
                    'decoratedPlayerBarRenderer': {
                        'decoratedPlayerBarRenderer': {
                            'playerBar': {
                                'chapteredPlayerBarRenderer': {
                                    'chapters': chapters,
                                }
                            }
                        }
                    }
                }
            }
        }
        player = {'watch_next_response': json.dumps(response)}
        webpage = 'RELATED_PLAYER_ARGS": ' + json.dumps(player) + ',\n'

        ie = YoutubeIE()
        result = ie._extract_chapters_from_json(webpage, 'vid', 30)
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['start_time'], 0)
        self.assertEqual(result[0]['end_time'], 10)
        self.assertEqual(result[1]['end_time'], 20)
        self.assertEqual(result[2]['end_time'], 30)
