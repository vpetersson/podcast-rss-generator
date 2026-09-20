"""One test per bug found in the audit. Each of these failed before its fix."""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from helpers import NS, Feed, build_feed, element

import rss_generator
from rss_generator import format_description


def test_special_characters_in_title_stay_escaped(
    config: dict[str, Any], tmp_path: Path
) -> None:
    """A "<" in a title used to produce malformed XML.

    The module monkeypatched ``ET._escape_cdata`` to stop escaping "<" and ">"
    so that CDATA delimiters survived serialization. That applied to every
    text node, not just CDATA, so a title containing "<" was written verbatim
    and the feed no longer parsed.
    """
    config["episodes"] = [config["episodes"][0]]
    config["episodes"][0]["title"] = "Tips & Tricks <not-a-tag> for you"

    feed = build_feed(
        config, tmp_path / "special_chars.xml", skip_asset_verification=True
    )

    title = element(element(feed.channel, "item"), "title")
    assert title.text == "Tips & Tricks <not-a-tag> for you"


def test_cdata_survives_and_keeps_html_escaping(
    config: dict[str, Any], tmp_path: Path
) -> None:
    """CDATA delimiters must be literal, and the HTML inside stays escaped."""
    config["episodes"] = [config["episodes"][0]]
    config["episodes"][0]["description"] = "Rock & roll <em>bold</em> text"

    feed = build_feed(config, tmp_path / "cdata.xml", skip_asset_verification=True)

    assert "<![CDATA[" in feed.raw
    assert "]]>" in feed.raw
    # HTML inside CDATA is parsed as HTML by clients, so "&" belongs escaped.
    # A raw "&" here would be invalid HTML.
    assert "Rock &amp; roll" in feed.raw
    # And the document as a whole still parses.
    ET.parse(feed.path)


def test_description_truncation_respects_byte_limit() -> None:
    """Truncation applied the byte budget as a character index, so any
    multi-byte text overshot: 3,000 accented characters produced 6,019 bytes
    against a 4,000-byte limit.
    """
    # format_description returns the sentinel form; what ships is the restored
    # CDATA, so measure that.
    result = format_description("é" * 3000)
    shipped = result.replace(rss_generator._CDATA_OPEN, "<![CDATA[").replace(
        rss_generator._CDATA_CLOSE, "]]>"
    )

    assert len(shipped.encode("utf-8")) <= rss_generator.DESCRIPTION_BYTE_LIMIT
    # And the trim landed on a character boundary, not mid-sequence.
    assert "�" not in shipped


def test_enclosure_defaults_when_headers_missing(
    config: dict[str, Any], tmp_path: Path
) -> None:
    """``get_file_info`` always sets these keys, so ``.get(key, default)``
    returned None rather than the default, and the enclosure was written with
    length="None" and a type of None.
    """
    config["episodes"] = [config["episodes"][0]]

    feed = build_feed(
        config,
        tmp_path / "enclosure.xml",
        headers={},  # server sent neither content-length nor content-type
        ffprobe_output="",
    )

    enclosure = element(element(feed.channel, "item"), "enclosure")
    assert enclosure.get("length") == "0"
    assert enclosure.get("type") == "application/octet-stream"


def test_global_explicit_honours_new_key(
    config: dict[str, Any], tmp_path: Path
) -> None:
    """The per-episode explicit fallback read only the legacy itunes_explicit
    key, so a config using the documented `explicit:` key marked every episode
    "no".
    """
    config["metadata"].pop("itunes_explicit", None)
    config["metadata"]["explicit"] = True
    # Strip per-episode overrides so the global value is what is tested.
    for episode in config["episodes"]:
        episode.pop("explicit", None)
        episode.pop("itunes_explicit", None)

    feed = build_feed(config, tmp_path / "explicit.xml", skip_asset_verification=True)

    items = feed.channel.findall("item")
    assert items
    for item in items:
        assert element(item, "itunes:explicit").text == "yes"


def test_feed_declares_the_podcast_namespace(feed_new: Feed) -> None:
    """Transcript tags are namespaced; without the declaration they parse as
    an unknown namespace and no client reads them.
    """
    assert NS["podcast"] in feed_new.raw
