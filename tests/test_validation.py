"""Tests for the field validators and for ``validate_config``."""

from typing import Any

import pytest

from rss_generator import (
    is_valid_email,
    is_valid_iso_date,
    is_valid_url,
    validate_config,
)


@pytest.fixture
def valid_config() -> dict[str, Any]:
    """The smallest configuration that validates; tests break it as needed."""
    return {
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


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://example.com/path",
        "https://subdomain.example.com/path?param=value",
    ],
)
def test_is_valid_url_accepts(url: str) -> None:
    assert is_valid_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "not-a-url",
        "",
        "example.com",  # missing scheme
        "://example.com",  # missing scheme
        # A non-string reaches these validators whenever YAML infers a type,
        # e.g. `link: 123`. It must be reported, not raise.
        123,
        None,
    ],
)
def test_is_valid_url_rejects(url: object) -> None:
    assert not is_valid_url(url)


@pytest.mark.parametrize(
    "email",
    ["test@example.com", "user.name@domain.co.uk", "test+tag@example.org"],
)
def test_is_valid_email_accepts(email: str) -> None:
    assert is_valid_email(email)


@pytest.mark.parametrize(
    "email", ["invalid-email", "@example.com", "test@", "", 123, None]
)
def test_is_valid_email_rejects(email: object) -> None:
    assert not is_valid_email(email)


@pytest.mark.parametrize(
    "date_string",
    [
        "2023-01-15T10:00:00Z",
        "2023-01-15T10:00:00+00:00",
        "2023-12-31T23:59:59Z",
    ],
)
def test_is_valid_iso_date_accepts(date_string: str) -> None:
    assert is_valid_iso_date(date_string)


@pytest.mark.parametrize(
    "date_string",
    [
        "invalid-date",
        "2023-13-01T10:00:00Z",  # month 13
        "2023-01-32T10:00:00Z",  # day 32
        "",
        123,
        None,
    ],
)
def test_is_valid_iso_date_rejects(date_string: object) -> None:
    assert not is_valid_iso_date(date_string)


def test_valid_config_passes(valid_config: dict[str, Any]) -> None:
    is_valid, errors = validate_config(valid_config)
    assert is_valid
    assert errors == []


def test_missing_metadata_is_reported() -> None:
    is_valid, errors = validate_config({"episodes": []})
    assert not is_valid
    assert "Missing required 'metadata' section" in errors


def test_missing_episodes_is_reported(valid_config: dict[str, Any]) -> None:
    del valid_config["episodes"]

    is_valid, errors = validate_config(valid_config)

    assert not is_valid
    assert "Missing required 'episodes' section" in errors


def test_invalid_email_is_reported(valid_config: dict[str, Any]) -> None:
    valid_config["metadata"]["email"] = "invalid-email"

    is_valid, errors = validate_config(valid_config)

    assert not is_valid
    assert any("Invalid email format" in error for error in errors)


def test_invalid_urls_are_reported(valid_config: dict[str, Any]) -> None:
    valid_config["metadata"]["link"] = "not-a-url"
    valid_config["episodes"][0]["asset_url"] = "not-a-url"

    is_valid, errors = validate_config(valid_config)

    assert not is_valid
    assert any("Invalid URL format" in error for error in errors)


def test_invalid_publication_date_is_reported(valid_config: dict[str, Any]) -> None:
    valid_config["episodes"][0]["publication_date"] = "invalid-date"

    is_valid, errors = validate_config(valid_config)

    assert not is_valid
    assert any("Invalid publication_date format" in error for error in errors)


def test_legacy_metadata_keys_still_validate(valid_config: dict[str, Any]) -> None:
    metadata = valid_config["metadata"]
    metadata["itunes_email"] = metadata.pop("email")
    metadata["itunes_author"] = metadata.pop("author")
    metadata["itunes_category"] = "Technology"

    is_valid, errors = validate_config(valid_config)

    assert is_valid
    assert errors == []


def test_transcript_urls_are_validated(valid_config: dict[str, Any]) -> None:
    valid_config["episodes"][0]["transcripts"] = [
        {"url": "https://example.com/transcript1.srt", "type": "application/x-subrip"},
        {"url": "invalid-url", "type": "text/vtt"},
    ]

    is_valid, errors = validate_config(valid_config)

    assert not is_valid
    assert any("Transcript 2 has invalid URL format" in error for error in errors)


def test_non_string_fields_are_reported_not_raised(
    valid_config: dict[str, Any],
) -> None:
    """A YAML config yielding `email: 123` must fail validation, not crash."""
    valid_config["metadata"]["email"] = 123
    valid_config["episodes"][0]["publication_date"] = 20230115

    is_valid, errors = validate_config(valid_config)

    assert not is_valid
    assert any("email" in error for error in errors)
