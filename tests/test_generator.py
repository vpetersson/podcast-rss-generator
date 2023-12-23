import unittest
from generator import iso_to_rfc2822, read_metadata, read_video_data, generate_rss
from xml.etree import ElementTree as ET
import os


class TestRSSGenerator(unittest.TestCase):

    def test_read_metadata(self):
        metadata = read_metadata('metadata.yaml.example')
        self.assertEqual(metadata['title'], 'My Video Podcast')
        self.assertEqual(metadata['author'], 'Viktor Petersson')

    def test_read_video_data(self):
        video_data = read_video_data('videos.csv.example')

        # Assuming there are 2 entries in the test CSV
        self.assertEqual(len(video_data), 2)
        self.assertEqual(video_data[0]['title'], 'Video Podcast Episode 1')

    def test_date_conversion(self):
        rfc_date = iso_to_rfc2822('2023-12-20T10:00:00')
        self.assertEqual(rfc_date, 'Wed, 20 Dec 2023 10:00:00 -0000')

    def test_rss_generation(self):
        metadata = read_metadata('metadata.yaml.example')
        video_data = read_video_data('videos.csv.example')
        generate_rss(metadata, video_data)
        self.assertTrue(os.path.exists('podcast_feed.xml'))
        tree = ET.parse('podcast_feed.xml')
        root = tree.getroot()
        self.assertEqual(root.tag, 'rss')
        self.assertEqual(root.find('./channel/title').text, 'My Video Podcast')

    def tearDown(self):
        if os.path.exists('podcast_feed.xml'):
            os.remove('podcast_feed.xml')


if __name__ == '__main__':
    unittest.main()
