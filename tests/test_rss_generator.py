import os
import unittest
from xml.etree import ElementTree as ET

# Set test mode before importing the module
os.environ['RSS_GENERATOR_TEST_MODE'] = 'true'

from rss_generator import (convert_iso_to_rfc2822, generate_rss, get_file_info,
                           read_podcast_config)

CONFIG_FILE = "podcast_config.example.yaml"


class TestRSSGenerator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Read the configuration and generate the RSS feed once for all tests
        cls.config = read_podcast_config(CONFIG_FILE)
        generate_rss(cls.config, "test_podcast_feed.xml")
        cls.tree = ET.parse("test_podcast_feed.xml")
        cls.root = cls.tree.getroot()
        cls.channel = cls.root.find("channel")
        cls.ns = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}

    def test_config_structure(self):
        self.assertIn("metadata", self.config)
        self.assertIn("episodes", self.config)

    def test_rss_structure(self):
        self.assertEqual(self.root.tag, "rss")
        self.assertIsNotNone(self.channel)

    def test_channel_structure(self):
        required_tags = ["title", "description", "language", "link"]
        for tag in required_tags:
            self.assertIsNotNone(self.channel.find(tag), f"Missing tag: {tag}")

    def test_itunes_tags_in_channel(self):
        itunes_tags = [
            "itunes:explicit",
            "itunes:owner",
            "itunes:author",
            "itunes:image",
            "itunes:category",
        ]
        for tag in itunes_tags:
            self.assertIsNotNone(
                self.channel.find(tag, self.ns), f"Missing iTunes tag in channel: {tag}"
            )

    def test_episode_structure(self):
        for episode in self.config["episodes"]:
            title = episode["title"]
            item = self.channel.find(f"item[title='{title}']")
            self.assertIsNotNone(item, f"Missing item for episode: {title}")
            self.assertIsNotNone(
                item.find("enclosure"), f"Missing enclosure tag for episode: {title}"
            )

    def test_episode_itunes_tags(self):
        for item in self.channel.findall("item"):
            itunes_episode = item.find("itunes:episode", self.ns)
            self.assertIsNotNone(
                itunes_episode, "Missing iTunes tag in episode: itunes:episode"
            )

            itunes_season = item.find("itunes:season", self.ns)
            self.assertIsNotNone(
                itunes_season, "Missing iTunes tag in episode: itunes:season"
            )

            # Check for itunes:episodeType tag if it is supposed to be present in each episode
            itunes_episode_type = item.find("itunes:episodeType", self.ns)
            if (
                "episodeType" in self.config["episodes"]
            ):  # Assuming 'episodeType' field is in your config for each episode
                self.assertIsNotNone(
                    itunes_episode_type,
                    "Missing iTunes tag in episode: itunes:episodeType",
                )

    def test_date_conversion(self):
        test_date = "2023-02-01T10:00:00"
        rfc_date = convert_iso_to_rfc2822(test_date)
        self.assertTrue(rfc_date.startswith("Wed, 01 Feb 2023 10:00:00"))

    def test_file_info_retrieval(self):
        for episode in self.config["episodes"]:
            file_info = get_file_info(episode["asset_url"])
            self.assertIsInstance(file_info["content-length"], str)
            self.assertIsInstance(file_info["content-type"], str)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists("test_podcast_feed.xml"):
            os.remove("test_podcast_feed.xml")


if __name__ == "__main__":
    unittest.main()
