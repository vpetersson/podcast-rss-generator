"""Tests for the network and ffprobe layer: retries, timeouts, fallbacks.

These paths are the ones a broken asset host exercises in production, and
they were the least covered part of the module.
"""

import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests
from helpers import MOCK_FFPROBE_OUTPUT, make_response

from podcast_rss_generator import assets, get_file_info
from podcast_rss_generator.assets import (
    _make_http_request,
    _run_ffprobe_with_retry,
)


@pytest.fixture(autouse=True)
def _no_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Backoff is real seconds; the tests only care that it was attempted."""
    monkeypatch.setattr(
        "podcast_rss_generator.assets.time.sleep", lambda _seconds: None
    )


def test_http_request_passes_a_timeout() -> None:
    """Without a timeout a hung host stalls the whole feed build."""
    with patch("podcast_rss_generator.assets.requests.head") as head:
        _make_http_request("https://example.com/a.mp3")

    assert head.call_args.kwargs["timeout"] == assets.HTTP_TIMEOUT_SECONDS
    assert head.call_args.kwargs["allow_redirects"] is True


def test_http_request_retries_then_succeeds() -> None:
    response = make_response()
    with patch(
        "podcast_rss_generator.assets.requests.head",
        side_effect=[requests.ConnectionError("boom"), response],
    ) as head:
        assert _make_http_request("https://example.com/a.mp3") is response

    assert head.call_count == 2


def test_http_request_reraises_after_the_last_attempt() -> None:
    with (
        patch(
            "podcast_rss_generator.assets.requests.head",
            side_effect=requests.ConnectionError("boom"),
        ) as head,
        pytest.raises(requests.ConnectionError),
    ):
        _make_http_request("https://example.com/a.mp3", max_retries=3)

    assert head.call_count == 3


def test_ffprobe_returns_its_output() -> None:
    completed = MagicMock(stdout=MOCK_FFPROBE_OUTPUT)
    with patch(
        "podcast_rss_generator.assets.subprocess.run", return_value=completed
    ) as run:
        assert _run_ffprobe_with_retry("https://example.com/a.mp3") == (
            MOCK_FFPROBE_OUTPUT
        )

    assert run.call_args.kwargs["timeout"] == assets.FFPROBE_TIMEOUT_SECONDS
    # Tags live in the container metadata, and JSON is what makes a tag value
    # containing "=" or a quote readable.
    command = run.call_args.args[0]
    assert "-show_format" in command
    assert command[command.index("-print_format") + 1] == "json"


def test_ffprobe_missing_binary_gives_up_immediately() -> None:
    """ffmpeg not being installed is not a transient failure."""
    with patch(
        "podcast_rss_generator.assets.subprocess.run", side_effect=FileNotFoundError
    ) as run:
        assert _run_ffprobe_with_retry("https://example.com/a.mp3") == ""

    assert run.call_count == 1


@pytest.mark.parametrize(
    "error",
    [
        subprocess.CalledProcessError(1, "ffprobe"),
        subprocess.TimeoutExpired("ffprobe", 1),
    ],
    ids=["exit-code", "timeout"],
)
def test_ffprobe_retries_then_returns_empty(error: Exception) -> None:
    with patch("podcast_rss_generator.assets.subprocess.run", side_effect=error) as run:
        assert _run_ffprobe_with_retry("https://example.com/a.mp3", max_retries=3) == ""

    assert run.call_count == 3


def test_ffprobe_retry_then_success() -> None:
    completed = MagicMock(stdout=MOCK_FFPROBE_OUTPUT)
    with patch(
        "podcast_rss_generator.assets.subprocess.run",
        side_effect=[subprocess.CalledProcessError(1, "ffprobe"), completed],
    ):
        assert _run_ffprobe_with_retry("https://example.com/a.mp3") == (
            MOCK_FFPROBE_OUTPUT
        )


def test_get_file_info_reads_headers_and_duration() -> None:
    with (
        patch(
            "podcast_rss_generator.assets._make_http_request",
            return_value=make_response(),
        ),
        patch(
            "podcast_rss_generator.assets._run_ffprobe_with_retry",
            return_value=MOCK_FFPROBE_OUTPUT,
        ),
    ):
        info = get_file_info("https://example.com/a.mp3")

    assert info["content-length"] == "12345678"
    assert info["content-type"] == "audio/mpeg"
    # 3541.275283 seconds, rounded to whole seconds.
    assert info["duration"] == 3541


def test_get_file_info_survives_an_unusable_probe() -> None:
    """Every key is still present, so callers can rely on the shape."""
    with (
        patch(
            "podcast_rss_generator.assets._make_http_request",
            return_value=make_response(headers={}),
        ),
        patch("podcast_rss_generator.assets._run_ffprobe_with_retry", return_value=""),
    ):
        info: dict[str, Any] = dict(get_file_info("https://example.com/a.mp3"))

    assert set(info) == {
        "content-length",
        "content-type",
        "duration",
        "content_hash",
        "tags",
    }
    assert info["duration"] is None
    assert info["tags"] == {}
