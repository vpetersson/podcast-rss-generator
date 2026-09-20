"""Constants and helpers shared by the test modules.

Kept out of ``conftest.py`` so the test modules can import them explicitly;
``conftest.py`` holds fixtures only.
"""

import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NamedTuple
from unittest.mock import MagicMock, patch

from rss_generator import generate_rss

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = REPO_ROOT / "podcast_config.example.yaml"

#: Namespaces used by the feed, for ``Element.find``.
NS = {
    "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
    "podcast": "https://podcastindex.org/namespace/1.0",
}

#: Metadata keys that were renamed; the old spelling is still accepted.
RENAMED_METADATA_KEYS = ("email", "author", "category", "explicit")

#: Trimmed ffprobe output. Only the duration is ever read back out of it.
MOCK_FFPROBE_OUTPUT = """streams.stream.0.index=0
streams.stream.0.codec_name="aac"
streams.stream.0.codec_type="audio"
streams.stream.0.sample_rate="44100"
streams.stream.0.channels=2
streams.stream.0.duration_ts=156170240
streams.stream.0.duration="3541.275283"
streams.stream.0.bit_rate="107301"
streams.stream.0.disposition.default=1"""

DEFAULT_ASSET_HEADERS = {
    "content-length": "12345678",
    "content-type": "audio/mpeg",
    # An MD5-shaped ETag, which the hash-as-GUID path recognises.
    "ETag": '"d41d8cd98f00b204e9800998ecf8427e"',
}


def make_response(
    url: str = "http://example.com/test.mp3",
    headers: Mapping[str, str] | None = None,
) -> MagicMock:
    """A stand-in for the ``requests`` response that ``get_file_info`` reads."""
    response = MagicMock()
    response.url = url
    response.headers = dict(DEFAULT_ASSET_HEADERS if headers is None else headers)
    return response


class Feed(NamedTuple):
    """A generated feed: the config it came from, parsed, and as written."""

    config: dict[str, Any]
    path: Path
    root: ET.Element
    channel: ET.Element
    raw: str


def element(parent: ET.Element, path: str) -> ET.Element:
    """Return ``path`` under ``parent``, failing the test if it is absent.

    ``Element.find`` returns ``Element | None``, so asserting on
    ``parent.find(path).text`` needs a guard at every call site. Funnelling
    the lookups through here keeps the assertions readable and lets the test
    suite type-check as strictly as the module under test.
    """
    found = parent.find(path, NS)
    assert found is not None, f"missing element: {path}"
    return found


def use_legacy_metadata_keys(config: dict[str, Any]) -> dict[str, Any]:
    """Rewrite the renamed metadata keys back to their ``itunes_*`` spelling."""
    metadata = config["metadata"]
    for key in RENAMED_METADATA_KEYS:
        metadata[f"itunes_{key}"] = metadata.pop(key)
    return config


def meta(feed: Feed, key: str) -> Any:
    """Read a metadata value under either the current or the legacy key name."""
    metadata = feed.config["metadata"]
    if key in metadata:
        return metadata[key]
    return metadata[f"itunes_{key}"]


def build_feed(
    config: dict[str, Any],
    path: Path,
    *,
    headers: Mapping[str, str] | None = None,
    ffprobe_output: str = MOCK_FFPROBE_OUTPUT,
    skip_asset_verification: bool = False,
) -> Feed:
    """Generate a feed with the network and ffprobe calls stubbed out."""
    response = make_response(headers=headers)
    with (
        patch("rss_generator._make_http_request", return_value=response),
        patch("rss_generator._run_ffprobe_with_retry", return_value=ffprobe_output),
    ):
        generate_rss(config, str(path), skip_asset_verification=skip_asset_verification)

    root = ET.parse(path).getroot()
    channel = root.find("channel")
    assert channel is not None, "feed has no <channel>"
    return Feed(
        config=config,
        path=path,
        root=root,
        channel=channel,
        raw=path.read_text(encoding="utf-8"),
    )
