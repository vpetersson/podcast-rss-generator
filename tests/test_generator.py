import os
import unittest
from xml.etree import ElementTree as ET

from rss_generator import (convert_iso_to_rfc2822, generate_rss,
                           read_podcast_config)

CONFIG_FILE = "podcast_config.example.yaml"


class TestRSSGenerator(unittest.TestCase):
    def test_read_podcast_config(self):
        config = read_podcast_config(CONFIG_FILE)
        self.assertIn("metadata", config)
        self.assertIn("episodes", config)
        self.assertEqual(config["metadata"]["title"], "My Video Podcast")

    def test_date_conversion(self):
        rfc_date = convert_iso_to_rfc2822("2023-02-01T10:00:00")
        self.assertTrue(rfc_date.startswith("Wed, 01 Feb 2023 10:00:00"))

    def test_rss_generation(self):
        config = read_podcast_config(CONFIG_FILE)
        generate_rss(config, "test_podcast_feed.xml")
        self.assertTrue(os.path.exists("test_podcast_feed.xml"))
        tree = ET.parse("test_podcast_feed.xml")
        root = tree.getroot()
        self.assertEqual(root.tag, "rss")
        self.assertEqual(root.find("./channel/title").text, config["metadata"]["title"])

    def tearDown(self):
        if os.path.exists("test_podcast_feed.xml"):
            os.remove("test_podcast_feed.xml")


if __name__ == "__main__":
    unittest.main()
