import unittest
from unittest.mock import patch
from rss_generator import read_metadata, read_video_data, convert_iso_to_rfc2822, generate_rss
import os


class TestRSSGenerator(unittest.TestCase):

    def test_read_metadata(self):
        metadata = read_metadata('metadata.yaml.example')
        self.assertEqual(metadata['title'], 'My Video Podcast')

    def test_read_video_data(self):
        video_data = read_video_data('videos.csv.example')
        self.assertEqual(len(video_data), 2)
        self.assertEqual(video_data[0]['title'], 'Episode 1')

    def test_date_conversion(self):
        rfc_date = convert_iso_to_rfc2822('2023-02-01T10:00:00')
        self.assertTrue(rfc_date.startswith('Wed, 01 Feb 2023 10:00:00'))

    def test_rss_generation(self):
        metadata = read_metadata('metadata.yaml.example')
        video_data = read_video_data('videos.csv.example')
        generate_rss(metadata, video_data, 'test_podcast_feed.xml')
        self.assertTrue(os.path.exists('test_podcast_feed.xml'))
        # Additional tests can be added here to check the structure and content of the generated RSS feed

    def tearDown(self):
        if os.path.exists('test_podcast_feed.xml'):
            os.remove('test_podcast_feed.xml')


if __name__ == '__main__':
    unittest.main()
