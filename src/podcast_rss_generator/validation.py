"""Validating a parsed configuration before a feed is built from it."""

import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse


def is_valid_url(url: object) -> bool:
    """Check if a URL is valid"""
    if not isinstance(url, str):
        return False
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def is_valid_email(email: object) -> bool:
    """
    Basic email validation.

    Guards on type first: YAML happily yields an int for `email: 123`, which
    used to raise TypeError out of re.match and abort validation instead of
    reporting the field as invalid.
    """
    if not isinstance(email, str):
        return False
    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(email_pattern, email) is not None


def is_valid_iso_date(date_string: object) -> bool:
    """
    Check if a date string is valid ISO format.

    Guards on type first: a non-string publication_date used to raise
    AttributeError rather than being reported as an invalid date.
    """
    if not isinstance(date_string, str):
        return False
    try:
        # Handle both 'Z' and timezone offset formats
        compatible_date = date_string.replace("Z", "+00:00")
        datetime.fromisoformat(compatible_date)
        return True
    except ValueError:
        return False


def validate_asset_references(config: Any) -> tuple[bool, list[str]]:
    """
    Check only what has to hold before the assets can be probed.

    ``validate_config`` requires a title, a description and a publication date
    on every episode, so it cannot run before metadata is read off the assets
    — the whole point of that pass is to supply some of those fields. This is
    the subset that reading them depends on: a list of episodes, each with a
    usable asset URL. Everything else is still reported by the full pass once
    the episodes have been resolved.
    """
    errors = []

    if not isinstance(config, dict):
        return False, ["Config must be a dictionary"]

    episodes = config.get("episodes")
    if episodes is None:
        return False, ["Missing required 'episodes' section"]

    if not isinstance(episodes, list):
        return False, ["Episodes section must be a list"]

    for i, episode in enumerate(episodes):
        if not isinstance(episode, dict):
            errors.append(f"Episode {i + 1} must be a dictionary")
        elif "asset_url" not in episode:
            errors.append(f"Episode {i + 1}: Missing required field 'asset_url'")
        elif not is_valid_url(episode["asset_url"]):
            errors.append(
                f"Episode {i + 1}: Invalid asset_url format '{episode['asset_url']}'"
            )

    return len(errors) == 0, errors


def validate_config(config: Any) -> tuple[bool, list[str]]:
    """
    Validate the podcast configuration file.
    Returns a tuple (is_valid, errors) where errors is a list of error messages.
    """
    errors = []

    # Check top-level structure
    if not isinstance(config, dict):
        errors.append("Config must be a dictionary")
        return False, errors

    if "metadata" not in config:
        errors.append("Missing required 'metadata' section")
        return False, errors

    if "episodes" not in config:
        errors.append("Missing required 'episodes' section")
        return False, errors

    metadata = config["metadata"]
    episodes = config["episodes"]

    # Validate metadata section
    required_metadata_fields = [
        "title",
        "description",
        "link",
        "rss_feed_url",
        "language",
    ]
    for field in required_metadata_fields:
        if field not in metadata:
            errors.append(f"Missing required metadata field: '{field}'")
        elif not isinstance(metadata[field], str) or not metadata[field].strip():
            errors.append(f"Metadata field '{field}' must be a non-empty string")

    # Validate email field (supports both new and old format)
    email_field = metadata.get("email") or metadata.get("itunes_email")
    if not email_field:
        errors.append("Missing required metadata field: 'email' (or 'itunes_email')")
    elif not is_valid_email(email_field):
        errors.append(f"Invalid email format: '{email_field}'")

    # Validate author field (supports both new and old format)
    author_field = metadata.get("author") or metadata.get("itunes_author")
    if not author_field:
        errors.append("Missing required metadata field: 'author' (or 'itunes_author')")
    elif not isinstance(author_field, str) or not author_field.strip():
        errors.append("Author field must be a non-empty string")

    # Validate category field (supports both new and old format)
    category_field = metadata.get("category") or metadata.get("itunes_category")
    if category_field and (
        not isinstance(category_field, str) or not category_field.strip()
    ):
        errors.append("Category field must be a non-empty string")

    # Validate URLs
    url_fields = ["link", "rss_feed_url", "image"]
    for field in url_fields:
        if metadata.get(field) and not is_valid_url(metadata[field]):
            errors.append(
                f"Invalid URL format in metadata field '{field}': '{metadata[field]}'"
            )

    # Validate boolean fields
    boolean_fields = ["explicit", "itunes_explicit", "use_asset_hash_as_guid"]
    for field in boolean_fields:
        if field in metadata and not isinstance(metadata[field], bool):
            errors.append(f"Metadata field '{field}' must be a boolean (true/false)")

    # Validate podcast_locked field
    if "podcast_locked" in metadata:
        locked_val = metadata["podcast_locked"]
        if locked_val not in ["yes", "no", True, False]:
            errors.append(
                "Metadata field 'podcast_locked' must be 'yes', 'no', true, or false"
            )

    # Validate episodes section
    if not isinstance(episodes, list):
        errors.append("Episodes section must be a list")
        return False, errors

    if len(episodes) == 0:
        errors.append("At least one episode is required")

    # Validate each episode
    required_episode_fields = ["title", "description", "publication_date", "asset_url"]
    valid_episode_types = ["full", "trailer", "bonus"]

    for i, episode in enumerate(episodes):
        if not isinstance(episode, dict):
            errors.append(f"Episode {i + 1} must be a dictionary")
            continue

        # Check required fields
        for field in required_episode_fields:
            if field not in episode:
                errors.append(f"Episode {i + 1}: Missing required field '{field}'")
            elif not isinstance(episode[field], str) or not episode[field].strip():
                errors.append(
                    f"Episode {i + 1}: Field '{field}' must be a non-empty string"
                )

        # Validate publication date
        if "publication_date" in episode and not is_valid_iso_date(
            episode["publication_date"]
        ):
            errors.append(
                f"Episode {i + 1}: Invalid publication_date format '{episode['publication_date']}' (must be ISO format like '2023-01-15T10:00:00Z')"
            )

        # Validate asset_url
        if "asset_url" in episode and not is_valid_url(episode["asset_url"]):
            errors.append(
                f"Episode {i + 1}: Invalid asset_url format '{episode['asset_url']}'"
            )

        # Validate optional URL fields
        episode_url_fields = ["link", "image"]
        for field in episode_url_fields:
            if episode.get(field) and not is_valid_url(episode[field]):
                errors.append(
                    f"Episode {i + 1}: Invalid URL format in field '{field}': '{episode[field]}'"
                )

        # Validate episode number
        if "episode" in episode and (
            not isinstance(episode["episode"], int) or episode["episode"] < 1
        ):
            errors.append(
                f"Episode {i + 1}: Field 'episode' must be a positive integer"
            )

        # Validate season number
        if "season" in episode and (
            not isinstance(episode["season"], int) or episode["season"] < 1
        ):
            errors.append(f"Episode {i + 1}: Field 'season' must be a positive integer")

        # Validate episode type
        if (
            "episode_type" in episode
            and episode["episode_type"] not in valid_episode_types
        ):
            errors.append(
                f"Episode {i + 1}: Invalid episode_type '{episode['episode_type']}' (must be one of: {', '.join(valid_episode_types)})"
            )

        # Validate boolean fields
        episode_boolean_fields = ["explicit", "itunes_explicit"]
        for field in episode_boolean_fields:
            if field in episode and not isinstance(episode[field], bool):
                errors.append(
                    f"Episode {i + 1}: Field '{field}' must be a boolean (true/false)"
                )

        # Validate transcripts
        if "transcripts" in episode:
            if not isinstance(episode["transcripts"], list):
                errors.append(f"Episode {i + 1}: Field 'transcripts' must be a list")
            else:
                for j, transcript in enumerate(episode["transcripts"]):
                    if not isinstance(transcript, dict):
                        errors.append(
                            f"Episode {i + 1}: Transcript {j + 1} must be a dictionary"
                        )
                        continue

                    # Check required transcript fields
                    if "url" not in transcript:
                        errors.append(
                            f"Episode {i + 1}: Transcript {j + 1} missing required field 'url'"
                        )
                    elif not is_valid_url(transcript["url"]):
                        errors.append(
                            f"Episode {i + 1}: Transcript {j + 1} has invalid URL format: '{transcript['url']}'"
                        )

                    if "type" not in transcript:
                        errors.append(
                            f"Episode {i + 1}: Transcript {j + 1} missing required field 'type'"
                        )
                    elif (
                        not isinstance(transcript["type"], str)
                        or not transcript["type"].strip()
                    ):
                        errors.append(
                            f"Episode {i + 1}: Transcript {j + 1} field 'type' must be a non-empty string"
                        )

    return len(errors) == 0, errors
