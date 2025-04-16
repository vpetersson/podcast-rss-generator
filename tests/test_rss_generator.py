import os
import unittest
from xml.etree import ElementTree as ET
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

# Set test mode before importing the module
os.environ["RSS_GENERATOR_TEST_MODE"] = "true"

from rss_generator import (
    convert_iso_to_rfc2822,
    generate_rss,
    get_file_info,
    read_podcast_config,
)

CONFIG_FILE = "podcast_config.example.yaml"


class TestRSSGenerator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Read the configuration and generate the RSS feed once for all tests
        # Use the updated example config with non-prefixed keys
        cls.config = read_podcast_config(CONFIG_FILE)

        # --- Generate feed based on the example config (using new keys) ---
        generate_rss(cls.config, "test_podcast_feed_new_keys.xml")
        cls.tree_new = ET.parse("test_podcast_feed_new_keys.xml")
        cls.root_new = cls.tree_new.getroot()
        cls.channel_new = cls.root_new.find("channel")

        # --- Generate feed using old keys for backward compatibility testing ---
        cls.config_old = read_podcast_config(CONFIG_FILE)  # Read again
        # Rename keys back to old format for this test config
        metadata_old = cls.config_old["metadata"]
        metadata_old["itunes_email"] = metadata_old.pop("email")
        metadata_old["itunes_author"] = metadata_old.pop("author")
        metadata_old["itunes_category"] = metadata_old.pop("category")
        metadata_old["itunes_explicit"] = metadata_old.pop("explicit")
        # image key remains 'image'
        generate_rss(cls.config_old, "test_podcast_feed_old_keys.xml")
        cls.tree_old = ET.parse("test_podcast_feed_old_keys.xml")
        cls.root_old = cls.tree_old.getroot()
        cls.channel_old = cls.root_old.find("channel")

        # Add podcast namespace for transcript testing
        cls.ns = {
            "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
            "podcast": "https://podcastindex.org/namespace/1.0",
            }

    def test_config_structure(self):
        # Test structure based on the primary config (new keys)
        self.assertIn("metadata", self.config)
        self.assertIn("episodes", self.config)
        self.assertIn("image", self.config["metadata"])
        self.assertIn("email", self.config["metadata"])  # Check new key presence
        self.assertIn("author", self.config["metadata"])  # Check new key presence
        self.assertIn("category", self.config["metadata"])  # Check new key presence
        self.assertIn("explicit", self.config["metadata"])  # Check new key presence

    def test_rss_structure(self):
        # Test general structure on both generated feeds
        self.assertEqual(self.root_new.tag, "rss")
        self.assertIsNotNone(self.channel_new)
        self.assertEqual(self.root_old.tag, "rss")
        self.assertIsNotNone(self.channel_old)

    def test_channel_structure(self):
        # Test basic channel tags on both feeds
        required_tags = ["title", "description", "language", "link"]
        # Check for optional copyright tag if present in config
        if "copyright" in self.config["metadata"]:
             required_tags.append("copyright")

        for tag in required_tags:
            self.assertIsNotNone(self.channel_new.find(tag), f"[New Keys] Missing tag: {tag}")
            self.assertIsNotNone(self.channel_old.find(tag), f"[Old Keys] Missing tag: {tag}")

    def test_itunes_tags_in_channel(self):
        # Test iTunes tags presence in channel for both feeds
        itunes_tags = [
            "itunes:explicit",
            "itunes:owner",  # Contains itunes:email
            "itunes:author",
            "itunes:image",
            "itunes:category",
        ]
        for tag in itunes_tags:
            self.assertIsNotNone(
                self.channel_new.find(tag, self.ns),
                f"[New Keys] Missing iTunes tag in channel: {tag}",
            )
            self.assertIsNotNone(
                self.channel_old.find(tag, self.ns),
                f"[Old Keys] Missing iTunes tag in channel: {tag}",
            )

        # Check specific values to ensure correctness
        self.assertEqual(
            self.channel_new.find("itunes:author", self.ns).text,
            self.config["metadata"]["author"],
        )
        self.assertEqual(
            self.channel_old.find("itunes:author", self.ns).text,
            self.config_old["metadata"]["itunes_author"],
        )

        self.assertEqual(
            self.channel_new.find("itunes:owner/itunes:email", self.ns).text,
            self.config["metadata"]["email"],
        )
        self.assertEqual(
            self.channel_old.find("itunes:owner/itunes:email", self.ns).text,
            self.config_old["metadata"]["itunes_email"],
        )

        explicit_new = self.channel_new.find("itunes:explicit", self.ns).text
        explicit_old = self.channel_old.find("itunes:explicit", self.ns).text
        self.assertEqual(
            explicit_new, "no" if not self.config["metadata"]["explicit"] else "yes"
        )
        self.assertEqual(
            explicit_old,
            "no" if not self.config_old["metadata"]["itunes_explicit"] else "yes",
        )

    def test_episode_structure(self):
        # Check episode structure based on new keys config (should be same for old)
        for episode in self.config["episodes"]:
            title = episode["title"]
            item_new = self.channel_new.find(f"item[title='{title}']")
            self.assertIsNotNone(
                item_new, f"[New Keys] Missing item for episode: {title}"
            )
            self.assertIsNotNone(
                item_new.find("enclosure"),
                f"[New Keys] Missing enclosure tag for episode: {title}",
            )
            # Optionally check on old keys feed too, assuming structure is identical
            item_old = self.channel_old.find(f"item[title='{title}']")
            self.assertIsNotNone(
                item_old, f"[Old Keys] Missing item for episode: {title}"
            )
            self.assertIsNotNone(
                item_old.find("enclosure"),
                f"[Old Keys] Missing enclosure tag for episode: {title}",
            )

            # Check for transcript tags if present in episode config
            if "transcripts" in episode and isinstance(episode["transcripts"], list):
                transcript_tags_new = item_new.findall("podcast:transcript", self.ns)
                transcript_tags_old = item_old.findall("podcast:transcript", self.ns)
                self.assertEqual(len(transcript_tags_new), len(episode["transcripts"]),
                                 f"[New Keys] Episode '{title}' transcript tag count mismatch")
                self.assertEqual(len(transcript_tags_old), len(episode["transcripts"]),
                                 f"[Old Keys] Episode '{title}' transcript tag count mismatch")

                # Verify attributes of the first transcript for simplicity
                first_transcript_config = episode["transcripts"][0]
                first_tag_new = transcript_tags_new[0]
                self.assertEqual(first_tag_new.get("url"), first_transcript_config["url"])
                self.assertEqual(first_tag_new.get("type"), first_transcript_config["type"])
                if "language" in first_transcript_config:
                     self.assertEqual(first_tag_new.get("language"), first_transcript_config["language"])
                else:
                    self.assertIsNone(first_tag_new.get("language"))

    def test_episode_itunes_tags(self):
        # Check episode tags based on new keys config
        for i, item in enumerate(self.channel_new.findall("item")):
            episode_config = self.config["episodes"][i]
            # Check for optional tags only if they exist in the config
            if "episode" in episode_config:
                itunes_episode = item.find("itunes:episode", self.ns)
                self.assertIsNotNone(
                    itunes_episode,
                    f"[New Keys] Missing itunes:episode tag in episode {i+1} when config has 'episode' key",
                )
                self.assertEqual(str(episode_config["episode"]), itunes_episode.text)

            if "season" in episode_config:
                itunes_season = item.find("itunes:season", self.ns)
                self.assertIsNotNone(
                    itunes_season,
                    f"[New Keys] Missing itunes:season tag in episode {i+1} when config has 'season' key",
                )
                self.assertEqual(str(episode_config["season"]), itunes_season.text)

            if "episode_type" in episode_config:
                itunes_episode_type = item.find("itunes:episodeType", self.ns)
                self.assertIsNotNone(
                    itunes_episode_type,
                    f"[New Keys] Missing itunes:episodeType tag in episode {i+1} when config has 'episode_type' key",
                )
                self.assertEqual(
                    episode_config["episode_type"], itunes_episode_type.text
                )

            # Test for episode-specific itunes:image tag (this should always exist due to fallback)
            itunes_image_tag = item.find("itunes:image", self.ns)
            self.assertIsNotNone(
                itunes_image_tag, "[New Keys] Missing itunes:image tag in episode"
            )
        # Could add similar loop for self.channel_old if needed, but logic is channel-level

    def test_episode_image_fallback(self):
        """Test image fallback on both new and old key feeds."""
        # Test with New Keys feed
        channel_image_url_new = self.config["metadata"]["image"]
        for i, item in enumerate(self.channel_new.findall("item")):
            episode_config = self.config["episodes"][i]
            item_image = item.find("itunes:image", self.ns)
            self.assertIsNotNone(
                item_image, f"[New Keys] Episode {i+1} missing itunes:image tag"
            )
            item_image_url = item_image.get("href")
            if "image" in episode_config:
                self.assertEqual(
                    item_image_url,
                    episode_config["image"],
                    f"[New Keys] Episode {i+1} specific image URL mismatch",
                )
            else:
                self.assertEqual(
                    item_image_url,
                    channel_image_url_new,
                    f"[New Keys] Episode {i+1} fallback image URL mismatch",
                )

        # Test with Old Keys feed
        channel_image_url_old = self.config_old["metadata"][
            "image"
        ]  # Still 'image' key here
        for i, item in enumerate(self.channel_old.findall("item")):
            episode_config = self.config_old["episodes"][
                i
            ]  # Use old config for checking episode key
            item_image = item.find("itunes:image", self.ns)
            self.assertIsNotNone(
                item_image, f"[Old Keys] Episode {i+1} missing itunes:image tag"
            )
            item_image_url = item_image.get("href")
            if (
                "image" in episode_config
            ):  # Episode image key is 'image' in both configs
                self.assertEqual(
                    item_image_url,
                    episode_config["image"],
                    f"[Old Keys] Episode {i+1} specific image URL mismatch",
                )
            else:
                self.assertEqual(
                    item_image_url,
                    channel_image_url_old,
                    f"[Old Keys] Episode {i+1} fallback image URL mismatch",
                )

    def test_date_conversion(self):
        # Use a date from the example config for a more reliable test
        test_date = self.config["episodes"][0]["publication_date"]
        rfc_date = convert_iso_to_rfc2822(test_date)
        # Expected format based on "2023-01-15T10:00:00Z"
        self.assertTrue(rfc_date.startswith("Sun, 15 Jan 2023 10:00:00"))

    def test_file_info_retrieval(self):
        # Test on new keys config (should be same for old)
        for episode in self.config["episodes"]:
            file_info = get_file_info(episode["asset_url"])
            self.assertIsInstance(file_info["content-length"], str)
            self.assertIsInstance(file_info["content-type"], str)

    def test_guid_logic(self):
        """Test GUID generation with and without use_asset_hash_as_guid flag."""

        base_config = read_podcast_config(CONFIG_FILE)
        test_url = base_config["episodes"][0]["asset_url"]
        expected_sha256_guid = "sha256:test-sha256-hash"
        expected_gcs_md5_guid = "md5:test-gcs-md5-base64"
        expected_etag_guid_md5 = "etag:d41d8cd98f00b204e9800998ecf8427e"
        expected_etag_guid_multi = "etag:multipart-etag-abc-1"

        scenarios = [
            # Default behavior (flag false or missing)
            ({"use_asset_hash_as_guid": False}, {}, test_url, "Default (flag false)"),
            ({}, {}, test_url, "Default (flag missing)"),
            # Flag true, testing header priority and fallback
            (
                {"use_asset_hash_as_guid": True},
                {"x-amz-checksum-sha256": "test-sha256-hash"},
                expected_sha256_guid,
                "Flag true, SHA256 header",
            ),
            ({"use_asset_hash_as_guid": True}, {"x-goog-hash": "crc32c=AAA,md5=test-gcs-md5-base64"}, expected_gcs_md5_guid, "Flag true, GCS MD5 header"),
            # ETag scenarios (now prefixed with etag:)
            ({"use_asset_hash_as_guid": True}, {"ETag": '"d41d8cd98f00b204e9800998ecf8427e"'}, expected_etag_guid_md5, "Flag true, ETag (MD5-like)"),
            ({"use_asset_hash_as_guid": True}, {"ETag": '"multipart-etag-abc-1"'}, expected_etag_guid_multi, "Flag true, ETag (Multipart)"),
            # Priority: SHA256 > GCS MD5 > ETag
            ({"use_asset_hash_as_guid": True}, {"x-amz-checksum-sha256": "test-sha256-hash", "ETag": '"any-etag"'}, expected_sha256_guid, "Flag true, SHA256 takes priority over ETag"),
            ({"use_asset_hash_as_guid": True}, {"x-goog-hash": "crc32c=AAA,md5=test-gcs-md5-base64", "ETag": '"any-etag"'}, expected_gcs_md5_guid, "Flag true, GCS MD5 takes priority over ETag"),
            # Fallback if no headers found
            ({"use_asset_hash_as_guid": True}, {}, test_url, "Flag true, No hash headers fallback"),
        ]

        for meta_override, mock_headers, expected_guid, description in scenarios:
            with self.subTest(description=description):
                test_config = read_podcast_config(CONFIG_FILE)  # Reset config
                test_config["metadata"].update(meta_override)

                # Mock the requests.head call within the _make_http_request scope
                mock_response = MagicMock()
                mock_response.headers = {
                    "content-length": "1000",  # Need basic headers for get_file_info
                    "content-type": "audio/mpeg",
                    **mock_headers,  # Add scenario-specific headers
                }
                mock_response.url = test_url  # Needed for ffprobe call

                # We patch _make_http_request which is called by get_file_info
                # We also need to patch _run_ffprobe_with_retry to avoid external calls
                with patch(
                    "rss_generator._make_http_request", return_value=mock_response
                ), patch(
                    "rss_generator._run_ffprobe_with_retry",
                    return_value='streams.stream.0.duration="123"',
                ):
                    output_filename = f"test_guid_{description.replace(' ', '_')}.xml"
                    generate_rss(test_config, output_filename)

                    tree = ET.parse(output_filename)
                    root = tree.getroot()
                    channel = root.find("channel")
                    # Check the GUID of the first item
                    item = channel.find("item")
                    self.assertIsNotNone(item)
                    guid_tag = item.find("guid")
                    self.assertIsNotNone(guid_tag)
                    self.assertEqual(guid_tag.text, expected_guid)

                    if os.path.exists(output_filename):
                        os.remove(output_filename)

    def test_date_comparison_with_naive_datetime(self):
        """Test that future-dated episodes with naive datetime strings are skipped."""
        # Create a config with a future date without timezone info
        future_naive_date = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        test_config = {
            "metadata": self.config["metadata"].copy(), # Use existing valid metadata
            "episodes": [
                {
                    "title": "Future Episode (Naive)",
                    "description": "Test description",
                    "publication_date": future_naive_date,
                    "asset_url": "http://example.com/future_naive.mp3",
                }
            ]
        }
        # Mock get_file_info to avoid network calls
        mock_file_info = {
            "content-length": "1000",
            "content-type": "audio/mpeg",
            "duration": 120,
            "content_hash": None,
        }
        with patch("rss_generator.get_file_info", return_value=mock_file_info):
            generate_rss(test_config, "test_naive_date_feed.xml")

        # Assert the feed was generated but contains no items (because the episode was skipped)
        tree = ET.parse("test_naive_date_feed.xml")
        root = tree.getroot()
        channel = root.find("channel")
        items = channel.findall("item")
        self.assertEqual(len(items), 0, "Future episode with naive datetime should have been skipped")

        if os.path.exists("test_naive_date_feed.xml"):
            os.remove("test_naive_date_feed.xml")

    @classmethod
    def tearDownClass(cls):
        # Clean up both generated files
        if os.path.exists("test_podcast_feed_new_keys.xml"):
            os.remove("test_podcast_feed_new_keys.xml")
        if os.path.exists("test_podcast_feed_old_keys.xml"):
            os.remove("test_podcast_feed_old_keys.xml")


if __name__ == "__main__":
    unittest.main()
