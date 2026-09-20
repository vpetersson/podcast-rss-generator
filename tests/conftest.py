"""Fixtures for the test suite.

Two things here are deliberate:

* every path is derived from this file's location, so the suite passes
  regardless of the directory pytest is invoked from;
* every feed is written under ``tmp_path``. The suite used to write XML into
  the repository root and delete it in ``finally`` blocks, which left debris
  behind whenever a test failed early.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from helpers import (
    CONFIG_FILE,
    MOCK_FFPROBE_OUTPUT,
    Feed,
    build_feed,
    make_response,
    use_legacy_metadata_keys,
)

from rss_generator import read_podcast_config


def _example_config() -> dict[str, Any]:
    parsed: dict[str, Any] = read_podcast_config(str(CONFIG_FILE))
    return parsed


@pytest.fixture
def config() -> dict[str, Any]:
    """The example configuration, read fresh so tests may mutate it."""
    return _example_config()


@pytest.fixture(scope="session")
def _feed_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("feeds")


@pytest.fixture(scope="session")
def feed_new(_feed_dir: Path) -> Feed:
    """The example config rendered once, for the read-only structural tests."""
    return build_feed(_example_config(), _feed_dir / "feed_new_keys.xml")


@pytest.fixture(scope="session")
def feed_old(_feed_dir: Path) -> Feed:
    """The same, via the legacy ``itunes_*`` metadata keys."""
    config = use_legacy_metadata_keys(_example_config())
    return build_feed(config, _feed_dir / "feed_old_keys.xml")


@pytest.fixture(params=["new-keys", "old-keys"])
def feed(request: pytest.FixtureRequest) -> Feed:
    """Both renderings, so each structural test runs against either spelling."""
    fixture_name = "feed_new" if request.param == "new-keys" else "feed_old"
    feed: Feed = request.getfixturevalue(fixture_name)
    return feed


@pytest.fixture
def no_network() -> Iterator[None]:
    """Stub the HEAD request and ffprobe for tests that call into them."""
    with (
        patch("rss_generator._make_http_request", return_value=make_response()),
        patch(
            "rss_generator._run_ffprobe_with_retry", return_value=MOCK_FFPROBE_OUTPUT
        ),
    ):
        yield
