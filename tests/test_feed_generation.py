"""End-to-end tests for the generated feed.

Anything structural runs through the ``feed`` fixture, which yields the feed
twice: once built from the documented metadata keys, and once from the legacy
``itunes_*`` spellings. Backward compatibility is therefore covered by the
same assertions as the current behaviour rather than by a parallel copy of
them.
"""

import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from helpers import (
    MOCK_FFPROBE_OUTPUT,
    NS,
    Feed,
    build_feed,
    element,
    make_response,
    meta,
)

from rss_generator import convert_iso_to_rfc2822, generate_rss, get_file_info

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


@pytest.mark.parametrize("key", ["image", "email", "author", "category", "explicit"])
def test_example_config_has_metadata_key(config: dict[str, Any], key: str) -> None:
    assert key in config["metadata"]


def test_example_config_has_episodes(config: dict[str, Any]) -> None:
    assert config["episodes"]


def test_rss_structure(feed: Feed) -> None:
    assert feed.root.tag == "rss"
    assert feed.channel.tag == "channel"


@pytest.mark.parametrize("tag", ["title", "description", "language", "link"])
def test_required_channel_tags(feed: Feed, tag: str) -> None:
    assert element(feed.channel, tag) is not None


def test_copyright_is_emitted_when_configured(feed: Feed) -> None:
    if "copyright" not in feed.config["metadata"]:
        pytest.skip("example config has no copyright")
    assert element(feed.channel, "copyright").text


@pytest.mark.parametrize(
    "tag",
    [
        "itunes:explicit",
        "itunes:owner",  # contains itunes:email
        "itunes:author",
        "itunes:image",
        "itunes:category",
    ],
)
def test_itunes_tags_in_channel(feed: Feed, tag: str) -> None:
    assert element(feed.channel, tag) is not None


def test_channel_author_matches_config(feed: Feed) -> None:
    assert element(feed.channel, "itunes:author").text == meta(feed, "author")


def test_channel_owner_email_matches_config(feed: Feed) -> None:
    owner_email = element(feed.channel, "itunes:owner/itunes:email")
    assert owner_email.text == meta(feed, "email")


def test_channel_explicit_matches_config(feed: Feed) -> None:
    expected = "yes" if meta(feed, "explicit") else "no"
    assert element(feed.channel, "itunes:explicit").text == expected


def test_every_episode_becomes_an_item(feed: Feed) -> None:
    for episode in feed.config["episodes"]:
        item = element(feed.channel, f"item[title='{episode['title']}']")
        assert element(item, "enclosure") is not None


def test_transcripts_are_emitted_verbatim(feed: Feed) -> None:
    for episode in feed.config["episodes"]:
        transcripts = episode.get("transcripts")
        if not isinstance(transcripts, list):
            continue

        item = element(feed.channel, f"item[title='{episode['title']}']")
        tags = item.findall("podcast:transcript", NS)
        assert len(tags) == len(transcripts)

        for tag, expected in zip(tags, transcripts, strict=True):
            assert tag.get("url") == expected["url"]
            assert tag.get("type") == expected["type"]
            # The attribute is omitted rather than emitted empty when the
            # episode does not declare a language.
            assert tag.get("language") == expected.get("language")


@pytest.mark.parametrize(
    ("config_key", "tag"),
    [
        ("episode", "itunes:episode"),
        ("season", "itunes:season"),
        ("episode_type", "itunes:episodeType"),
    ],
)
def test_optional_episode_itunes_tags(
    feed_new: Feed, config_key: str, tag: str
) -> None:
    items = feed_new.channel.findall("item")
    episodes = feed_new.config["episodes"]
    assert len(items) == len(episodes)

    for item, episode in zip(items, episodes, strict=True):
        if config_key not in episode:
            continue
        assert element(item, tag).text == str(episode[config_key])


def test_every_episode_has_an_image(feed: Feed) -> None:
    """Episodes without their own image inherit the channel image."""
    channel_image = feed.config["metadata"]["image"]
    items = feed.channel.findall("item")

    for item, episode in zip(items, feed.config["episodes"], strict=True):
        href = element(item, "itunes:image").get("href")
        assert href == episode.get("image", channel_image)


def test_date_conversion(config: dict[str, Any]) -> None:
    rfc_date = convert_iso_to_rfc2822(config["episodes"][0]["publication_date"])
    assert rfc_date.startswith("Sun, 15 Jan 2023 10:00:00")


@pytest.mark.usefixtures("no_network")
def test_file_info_retrieval(config: dict[str, Any]) -> None:
    for episode in config["episodes"]:
        file_info = get_file_info(episode["asset_url"])
        assert isinstance(file_info["content-length"], str)
        assert isinstance(file_info["content-type"], str)


GUID_SCENARIOS = [
    pytest.param(False, {}, None, id="flag-off"),
    pytest.param(None, {}, None, id="flag-absent"),
    pytest.param(
        True,
        {"x-amz-checksum-sha256": "test-sha256-hash"},
        "sha256:test-sha256-hash",
        id="sha256-header",
    ),
    pytest.param(
        True,
        {"x-goog-hash": "crc32c=AAA,md5=test-gcs-md5-base64"},
        "md5:test-gcs-md5-base64",
        id="gcs-md5-header",
    ),
    pytest.param(
        True,
        {"ETag": '"d41d8cd98f00b204e9800998ecf8427e"'},
        "etag:d41d8cd98f00b204e9800998ecf8427e",
        id="etag-md5-shaped",
    ),
    pytest.param(
        True,
        {"ETag": '"multipart-etag-abc-1"'},
        "etag:multipart-etag-abc-1",
        id="etag-multipart",
    ),
    pytest.param(
        True,
        {"x-amz-checksum-sha256": "test-sha256-hash", "ETag": '"any-etag"'},
        "sha256:test-sha256-hash",
        id="sha256-beats-etag",
    ),
    pytest.param(
        True,
        {"x-goog-hash": "crc32c=AAA,md5=test-gcs-md5-base64", "ETag": '"any-etag"'},
        "md5:test-gcs-md5-base64",
        id="gcs-md5-beats-etag",
    ),
    pytest.param(True, {}, None, id="no-hash-headers-falls-back-to-url"),
]


@pytest.mark.parametrize(("flag", "headers", "expected_guid"), GUID_SCENARIOS)
def test_guid_selection(
    config: dict[str, Any],
    tmp_path: Path,
    flag: bool | None,
    headers: dict[str, str],
    expected_guid: str | None,
) -> None:
    """``expected_guid`` of ``None`` means "falls back to the asset URL"."""
    if flag is not None:
        config["metadata"]["use_asset_hash_as_guid"] = flag
    asset_url = config["episodes"][0]["asset_url"]

    feed = build_feed(
        config,
        tmp_path / "guid.xml",
        headers={"content-length": "1000", "content-type": "audio/mpeg", **headers},
        ffprobe_output='streams.stream.0.duration="123"',
    )

    guid = element(element(feed.channel, "item"), "guid")
    assert guid.text == (expected_guid if expected_guid is not None else asset_url)


def test_future_episode_with_naive_datetime_is_skipped(
    config: dict[str, Any], tmp_path: Path
) -> None:
    future_naive = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    config["episodes"] = [
        {
            "title": "Future Episode (Naive)",
            "description": "Test description",
            "publication_date": future_naive,
            "asset_url": "http://example.com/future_naive.mp3",
        }
    ]

    feed = build_feed(config, tmp_path / "naive_date.xml")

    assert feed.channel.findall("item") == []


def test_descriptions_are_wrapped_in_cdata(feed_new: Feed) -> None:
    descriptions = re.findall(r"<description>(.*?)</description>", feed_new.raw)
    assert descriptions[0] == (
        "<![CDATA[<p>A podcast about technology &amp; programming.</p>]]>"
    )
    assert descriptions[1] == "<![CDATA[<p>Introduction to the podcast.</p>]]>"


def test_podcast_guid_is_generated_when_absent(feed_new: Feed) -> None:
    guid = element(feed_new.channel, "podcast:guid")
    assert guid.text is not None
    assert UUID_PATTERN.match(guid.text)


def test_generate_rss_writes_utf8(config: dict[str, Any], tmp_path: Path) -> None:
    """A non-ASCII title must survive the round trip through the file."""
    config["episodes"] = [config["episodes"][0]]
    config["episodes"][0]["title"] = "Épisode spécial — ☕"

    with (
        patch("rss_generator._make_http_request", return_value=make_response()),
        patch(
            "rss_generator._run_ffprobe_with_retry", return_value=MOCK_FFPROBE_OUTPUT
        ),
    ):
        output = tmp_path / "utf8.xml"
        generate_rss(config, str(output))

    channel = ET.parse(output).getroot().find("channel")
    assert channel is not None
    assert element(element(channel, "item"), "title").text == "Épisode spécial — ☕"
