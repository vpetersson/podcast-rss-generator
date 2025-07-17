import os
import re
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from xml.etree import ElementTree as ET

from rss_generator import (
    convert_iso_to_rfc2822,
    generate_rss,
    get_file_info,
    read_podcast_config,
    validate_config,
    is_valid_url,
    is_valid_email,
    is_valid_iso_date,
)

CONFIG_FILE = "podcast_config.example.yaml"


# Mock HTTP response for testing
class MockResponse:
    def __init__(self, url):
        self.url = url
        self.headers = {
            "content-length": "12345678",
            "content-type": "audio/mpeg",
            # Example headers for testing hash extraction
            "ETag": '"d41d8cd98f00b204e9800998ecf8427e"',  # MD5 hash
        }


# Mock ffprobe output for testing
MOCK_FFPROBE_OUTPUT = """streams.stream.0.index=0
streams.stream.0.codec_name="aac"
streams.stream.0.codec_long_name="AAC (Advanced Audio Coding)"
streams.stream.0.profile="LC"
streams.stream.0.codec_type="audio"
streams.stream.0.codec_tag_string="mp4a"
streams.stream.0.codec_tag="0x6134706d"
streams.stream.0.sample_fmt="fltp"
streams.stream.0.sample_rate="44100"
streams.stream.0.channels=2
streams.stream.0.channel_layout="stereo"
streams.stream.0.bits_per_sample=0
streams.stream.0.initial_padding=0
streams.stream.0.id="0x1"
streams.stream.0.r_frame_rate="0/0"
streams.stream.0.avg_frame_rate="0/0"
streams.stream.0.time_base="1/44100"
streams.stream.0.start_pts=0
streams.stream.0.start_time="0.000000"
streams.stream.0.duration_ts=156170240
streams.stream.0.duration="3541.275283"
streams.stream.0.bit_rate="107301"
streams.stream.0.max_bit_rate="N/A"
streams.stream.0.bits_per_raw_sample="N/A"
streams.stream.0.nb_frames="152510"
streams.stream.0.nb_read_frames="N/A"
streams.stream.0.nb_read_packets="N/A"
streams.stream.0.extradata_size=2
streams.stream.0.disposition.default=1"""


class TestRSSGenerator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Read the configuration and generate the RSS feed once for all tests
        # Use the updated example config with non-prefixed keys
        cls.config = read_podcast_config(CONFIG_FILE)

        # --- Generate feed based on the example config (using new keys) ---
        with (
            patch("rss_generator._make_http_request") as mock_http,
            patch("rss_generator._run_ffprobe_with_retry") as mock_ffprobe,
        ):
            mock_http.return_value = MockResponse("http://example.com/test.mp3")
            mock_ffprobe.return_value = MOCK_FFPROBE_OUTPUT

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

        with (
            patch("rss_generator._make_http_request") as mock_http,
            patch("rss_generator._run_ffprobe_with_retry") as mock_ffprobe,
        ):
            mock_http.return_value = MockResponse("http://example.com/test.mp3")
            mock_ffprobe.return_value = MOCK_FFPROBE_OUTPUT

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
            self.assertIsNotNone(
                self.channel_new.find(tag), f"[New Keys] Missing tag: {tag}"
            )
            self.assertIsNotNone(
                self.channel_old.find(tag), f"[Old Keys] Missing tag: {tag}"
            )

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
                self.assertEqual(
                    len(transcript_tags_new),
                    len(episode["transcripts"]),
                    f"[New Keys] Episode '{title}' transcript tag count mismatch",
                )
                self.assertEqual(
                    len(transcript_tags_old),
                    len(episode["transcripts"]),
                    f"[Old Keys] Episode '{title}' transcript tag count mismatch",
                )

                # Verify attributes for *all* transcripts
                for i, transcript_config in enumerate(episode["transcripts"]):
                    tag_new = transcript_tags_new[i]
                    tag_old = transcript_tags_old[i]  # Assuming order is preserved

                    # Check New Keys Feed
                    self.assertEqual(
                        tag_new.get("url"),
                        transcript_config["url"],
                        f"[New Keys] Episode '{title}' transcript {i + 1} URL mismatch",
                    )
                    self.assertEqual(
                        tag_new.get("type"),
                        transcript_config["type"],
                        f"[New Keys] Episode '{title}' transcript {i + 1} type mismatch",
                    )
                    if "language" in transcript_config:
                        self.assertEqual(
                            tag_new.get("language"),
                            transcript_config["language"],
                            f"[New Keys] Episode '{title}' transcript {i + 1} language mismatch",
                        )
                    else:
                        self.assertIsNone(
                            tag_new.get("language"),
                            f"[New Keys] Episode '{title}' transcript {i + 1} should not have language",
                        )

                    # Check Old Keys Feed (assuming transcript logic remains the same)
                    self.assertEqual(
                        tag_old.get("url"),
                        transcript_config["url"],
                        f"[Old Keys] Episode '{title}' transcript {i + 1} URL mismatch",
                    )
                    self.assertEqual(
                        tag_old.get("type"),
                        transcript_config["type"],
                        f"[Old Keys] Episode '{title}' transcript {i + 1} type mismatch",
                    )
                    if "language" in transcript_config:
                        self.assertEqual(
                            tag_old.get("language"),
                            transcript_config["language"],
                            f"[Old Keys] Episode '{title}' transcript {i + 1} language mismatch",
                        )
                    else:
                        self.assertIsNone(
                            tag_old.get("language"),
                            f"[Old Keys] Episode '{title}' transcript {i + 1} should not have language",
                        )

    def test_episode_itunes_tags(self):
        # Check episode tags based on new keys config
        for i, item in enumerate(self.channel_new.findall("item")):
            episode_config = self.config["episodes"][i]
            # Check for optional tags only if they exist in the config
            if "episode" in episode_config:
                itunes_episode = item.find("itunes:episode", self.ns)
                self.assertIsNotNone(
                    itunes_episode,
                    f"[New Keys] Missing itunes:episode tag in episode {i + 1} when config has 'episode' key",
                )
                self.assertEqual(str(episode_config["episode"]), itunes_episode.text)

            if "season" in episode_config:
                itunes_season = item.find("itunes:season", self.ns)
                self.assertIsNotNone(
                    itunes_season,
                    f"[New Keys] Missing itunes:season tag in episode {i + 1} when config has 'season' key",
                )
                self.assertEqual(str(episode_config["season"]), itunes_season.text)

            if "episode_type" in episode_config:
                itunes_episode_type = item.find("itunes:episodeType", self.ns)
                self.assertIsNotNone(
                    itunes_episode_type,
                    f"[New Keys] Missing itunes:episodeType tag in episode {i + 1} when config has 'episode_type' key",
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
                item_image, f"[New Keys] Episode {i + 1} missing itunes:image tag"
            )
            item_image_url = item_image.get("href")
            if "image" in episode_config:
                self.assertEqual(
                    item_image_url,
                    episode_config["image"],
                    f"[New Keys] Episode {i + 1} specific image URL mismatch",
                )
            else:
                self.assertEqual(
                    item_image_url,
                    channel_image_url_new,
                    f"[New Keys] Episode {i + 1} fallback image URL mismatch",
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
                item_image, f"[Old Keys] Episode {i + 1} missing itunes:image tag"
            )
            item_image_url = item_image.get("href")
            if (
                "image" in episode_config
            ):  # Episode image key is 'image' in both configs
                self.assertEqual(
                    item_image_url,
                    episode_config["image"],
                    f"[Old Keys] Episode {i + 1} specific image URL mismatch",
                )
            else:
                self.assertEqual(
                    item_image_url,
                    channel_image_url_old,
                    f"[Old Keys] Episode {i + 1} fallback image URL mismatch",
                )

    def test_date_conversion(self):
        # Use a date from the example config for a more reliable test
        test_date = self.config["episodes"][0]["publication_date"]
        rfc_date = convert_iso_to_rfc2822(test_date)
        # Expected format based on "2023-01-15T10:00:00Z"
        self.assertTrue(rfc_date.startswith("Sun, 15 Jan 2023 10:00:00"))

    def test_file_info_retrieval(self):
        # Test on new keys config (should be same for old)
        with (
            patch("rss_generator._make_http_request") as mock_http,
            patch("rss_generator._run_ffprobe_with_retry") as mock_ffprobe,
        ):
            mock_http.return_value = MockResponse("http://example.com/test.mp3")
            mock_ffprobe.return_value = MOCK_FFPROBE_OUTPUT

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
            (
                {"use_asset_hash_as_guid": True},
                {"x-goog-hash": "crc32c=AAA,md5=test-gcs-md5-base64"},
                expected_gcs_md5_guid,
                "Flag true, GCS MD5 header",
            ),
            # ETag scenarios (now prefixed with etag:)
            (
                {"use_asset_hash_as_guid": True},
                {"ETag": '"d41d8cd98f00b204e9800998ecf8427e"'},
                expected_etag_guid_md5,
                "Flag true, ETag (MD5-like)",
            ),
            (
                {"use_asset_hash_as_guid": True},
                {"ETag": '"multipart-etag-abc-1"'},
                expected_etag_guid_multi,
                "Flag true, ETag (Multipart)",
            ),
            # Priority: SHA256 > GCS MD5 > ETag
            (
                {"use_asset_hash_as_guid": True},
                {"x-amz-checksum-sha256": "test-sha256-hash", "ETag": '"any-etag"'},
                expected_sha256_guid,
                "Flag true, SHA256 takes priority over ETag",
            ),
            (
                {"use_asset_hash_as_guid": True},
                {
                    "x-goog-hash": "crc32c=AAA,md5=test-gcs-md5-base64",
                    "ETag": '"any-etag"',
                },
                expected_gcs_md5_guid,
                "Flag true, GCS MD5 takes priority over ETag",
            ),
            # Fallback if no headers found
            (
                {"use_asset_hash_as_guid": True},
                {},
                test_url,
                "Flag true, No hash headers fallback",
            ),
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
                with (
                    patch(
                        "rss_generator._make_http_request", return_value=mock_response
                    ),
                    patch(
                        "rss_generator._run_ffprobe_with_retry",
                        return_value='streams.stream.0.duration="123"',
                    ),
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
        future_naive_date = (datetime.now(timezone.utc) + timedelta(days=1)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        test_config = {
            "metadata": self.config["metadata"].copy(),  # Use existing valid metadata
            "episodes": [
                {
                    "title": "Future Episode (Naive)",
                    "description": "Test description",
                    "publication_date": future_naive_date,
                    "asset_url": "http://example.com/future_naive.mp3",
                }
            ],
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
        self.assertEqual(
            len(items), 0, "Future episode with naive datetime should have been skipped"
        )

        if os.path.exists("test_naive_date_feed.xml"):
            os.remove("test_naive_date_feed.xml")

    def test_description_escaping(self):
        with open("test_podcast_feed_new_keys.xml", "r") as f:
            xml_feed = f.read()
        # check for correct CDATA escaping
        description_tag_pattern = re.compile(r"<description>(.*?)</description>")
        items = description_tag_pattern.findall(xml_feed)
        self.assertEqual(
            items[0], "<![CDATA[<p>A podcast about technology &amp; programming.</p>]]>"
        )
        self.assertEqual(items[1], "<![CDATA[<p>Introduction to the podcast.</p>]]>")

    def test_podcast_guid_generation(self):
        """Test automatic podcast GUID generation when not specified"""
        # Check if GUID was generated and is in UUID format
        guid_element = self.channel_new.find("podcast:guid", self.ns)
        self.assertIsNotNone(guid_element)

        # Should be a valid UUID format
        uuid_pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        self.assertIsNotNone(re.match(uuid_pattern, guid_element.text))


class TestValidationFunctions(unittest.TestCase):
    """Test the new validation functions"""

    def test_is_valid_url(self):
        """Test URL validation"""
        # Valid URLs
        self.assertTrue(is_valid_url("https://example.com"))
        self.assertTrue(is_valid_url("http://example.com/path"))
        self.assertTrue(is_valid_url("https://subdomain.example.com/path?param=value"))

        # Invalid URLs
        self.assertFalse(is_valid_url("not-a-url"))
        self.assertFalse(is_valid_url(""))
        self.assertFalse(is_valid_url("example.com"))  # Missing scheme
        self.assertFalse(is_valid_url("://example.com"))  # Missing scheme

    def test_is_valid_email(self):
        """Test email validation"""
        # Valid emails
        self.assertTrue(is_valid_email("test@example.com"))
        self.assertTrue(is_valid_email("user.name@domain.co.uk"))
        self.assertTrue(is_valid_email("test+tag@example.org"))

        # Invalid emails
        self.assertFalse(is_valid_email("invalid-email"))
        self.assertFalse(is_valid_email("@example.com"))
        self.assertFalse(is_valid_email("test@"))
        self.assertFalse(is_valid_email(""))

    def test_is_valid_iso_date(self):
        """Test ISO date validation"""
        # Valid ISO dates
        self.assertTrue(is_valid_iso_date("2023-01-15T10:00:00Z"))
        self.assertTrue(is_valid_iso_date("2023-01-15T10:00:00+00:00"))
        self.assertTrue(is_valid_iso_date("2023-12-31T23:59:59Z"))

        # Invalid ISO dates
        self.assertFalse(is_valid_iso_date("invalid-date"))
        self.assertFalse(is_valid_iso_date("2023-13-01T10:00:00Z"))  # Invalid month
        self.assertFalse(is_valid_iso_date("2023-01-32T10:00:00Z"))  # Invalid day
        self.assertFalse(is_valid_iso_date(""))

    def test_validate_config_valid(self):
        """Test validation with valid config"""
        valid_config = {
            "metadata": {
                "title": "Test Podcast",
                "description": "Test description",
                "link": "https://example.com",
                "rss_feed_url": "https://example.com/feed.xml",
                "language": "en-us",
                "email": "test@example.com",
                "author": "Test Author",
            },
            "episodes": [
                {
                    "title": "Episode 1",
                    "description": "Test episode",
                    "publication_date": "2023-01-15T10:00:00Z",
                    "asset_url": "https://example.com/episode1.mp3",
                }
            ],
        }

        is_valid, errors = validate_config(valid_config)
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)

    def test_validate_config_missing_metadata(self):
        """Test validation with missing metadata"""
        invalid_config = {"episodes": []}

        is_valid, errors = validate_config(invalid_config)
        self.assertFalse(is_valid)
        self.assertIn("Missing required 'metadata' section", errors)

    def test_validate_config_missing_episodes(self):
        """Test validation with missing episodes"""
        invalid_config = {
            "metadata": {
                "title": "Test Podcast",
                "description": "Test description",
                "link": "https://example.com",
                "rss_feed_url": "https://example.com/feed.xml",
                "language": "en-us",
                "email": "test@example.com",
                "author": "Test Author",
            }
        }

        is_valid, errors = validate_config(invalid_config)
        self.assertFalse(is_valid)
        self.assertIn("Missing required 'episodes' section", errors)

    def test_validate_config_invalid_email(self):
        """Test validation with invalid email"""
        invalid_config = {
            "metadata": {
                "title": "Test Podcast",
                "description": "Test description",
                "link": "https://example.com",
                "rss_feed_url": "https://example.com/feed.xml",
                "language": "en-us",
                "email": "invalid-email",
                "author": "Test Author",
            },
            "episodes": [
                {
                    "title": "Episode 1",
                    "description": "Test episode",
                    "publication_date": "2023-01-15T10:00:00Z",
                    "asset_url": "https://example.com/episode1.mp3",
                }
            ],
        }

        is_valid, errors = validate_config(invalid_config)
        self.assertFalse(is_valid)
        self.assertTrue(any("Invalid email format" in error for error in errors))

    def test_validate_config_invalid_url(self):
        """Test validation with invalid URLs"""
        invalid_config = {
            "metadata": {
                "title": "Test Podcast",
                "description": "Test description",
                "link": "not-a-url",
                "rss_feed_url": "https://example.com/feed.xml",
                "language": "en-us",
                "email": "test@example.com",
                "author": "Test Author",
            },
            "episodes": [
                {
                    "title": "Episode 1",
                    "description": "Test episode",
                    "publication_date": "2023-01-15T10:00:00Z",
                    "asset_url": "not-a-url",
                }
            ],
        }

        is_valid, errors = validate_config(invalid_config)
        self.assertFalse(is_valid)
        self.assertTrue(any("Invalid URL format" in error for error in errors))

    def test_validate_config_invalid_episode_date(self):
        """Test validation with invalid episode date"""
        invalid_config = {
            "metadata": {
                "title": "Test Podcast",
                "description": "Test description",
                "link": "https://example.com",
                "rss_feed_url": "https://example.com/feed.xml",
                "language": "en-us",
                "email": "test@example.com",
                "author": "Test Author",
            },
            "episodes": [
                {
                    "title": "Episode 1",
                    "description": "Test episode",
                    "publication_date": "invalid-date",
                    "asset_url": "https://example.com/episode1.mp3",
                }
            ],
        }

        is_valid, errors = validate_config(invalid_config)
        self.assertFalse(is_valid)
        self.assertTrue(
            any("Invalid publication_date format" in error for error in errors)
        )

    def test_validate_config_backward_compatibility(self):
        """Test validation with old-style metadata keys"""
        old_style_config = {
            "metadata": {
                "title": "Test Podcast",
                "description": "Test description",
                "link": "https://example.com",
                "rss_feed_url": "https://example.com/feed.xml",
                "language": "en-us",
                "itunes_email": "test@example.com",  # Old key
                "itunes_author": "Test Author",  # Old key
                "itunes_category": "Technology",  # Old key
            },
            "episodes": [
                {
                    "title": "Episode 1",
                    "description": "Test episode",
                    "publication_date": "2023-01-15T10:00:00Z",
                    "asset_url": "https://example.com/episode1.mp3",
                }
            ],
        }

        is_valid, errors = validate_config(old_style_config)
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)

    def test_validate_config_transcripts(self):
        """Test validation of episode transcripts"""
        config_with_transcripts = {
            "metadata": {
                "title": "Test Podcast",
                "description": "Test description",
                "link": "https://example.com",
                "rss_feed_url": "https://example.com/feed.xml",
                "language": "en-us",
                "email": "test@example.com",
                "author": "Test Author",
            },
            "episodes": [
                {
                    "title": "Episode 1",
                    "description": "Test episode",
                    "publication_date": "2023-01-15T10:00:00Z",
                    "asset_url": "https://example.com/episode1.mp3",
                    "transcripts": [
                        {
                            "url": "https://example.com/transcript1.srt",
                            "type": "application/x-subrip",
                        },
                        {
                            "url": "invalid-url",  # Invalid URL
                            "type": "text/vtt",
                        },
                    ],
                }
            ],
        }

        is_valid, errors = validate_config(config_with_transcripts)
        self.assertFalse(is_valid)
        self.assertTrue(
            any("Transcript 2 has invalid URL format" in error for error in errors)
        )

    @classmethod
    def tearDownClass(cls):
        # Clean up both generated files
        if os.path.exists("test_podcast_feed_new_keys.xml"):
            os.remove("test_podcast_feed_new_keys.xml")
        if os.path.exists("test_podcast_feed_old_keys.xml"):
            os.remove("test_podcast_feed_old_keys.xml")


if __name__ == "__main__":
    unittest.main()
