"""
Tests for reading episode fields off the asset's own container tags.

The behaviour this guards is that the feature is invisible unless asked for,
and that when it is asked for the config still wins over anything the asset
claims.
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml
from helpers import CONFIG_FILE, make_response, probe_output

from podcast_rss_generator import get_file_info
from podcast_rss_generator.assets import FileInfo, _parse_probe
from podcast_rss_generator.cli import main
from podcast_rss_generator.enrich import resolve_episodes
from podcast_rss_generator.validation import validate_asset_references


def file_info(**tags: str) -> FileInfo:
    """A probe result carrying ``tags`` and nothing else of interest."""
    return {
        "content-length": "12345678",
        "content-type": "audio/mpeg",
        "duration": 3541,
        "content_hash": None,
        "tags": dict(tags),
    }


def episode(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "asset_url": "https://example.com/ep1.mp3",
        "publication_date": "2023-01-15T10:00:00Z",
    }
    base.update(overrides)
    return base


# --- the probe layer ---------------------------------------------------


def test_probe_reads_tags_and_duration() -> None:
    duration, tags = _parse_probe(probe_output(title="Ep 1", comment="Notes"))

    assert duration == 3541
    assert tags == {"title": "Ep 1", "comment": "Notes"}


def test_probe_survives_values_that_flat_output_would_mangle() -> None:
    """The reason the probe asks for JSON: flat output escapes these."""
    _, tags = _parse_probe(probe_output(title='He said "hi" = ok', artist="Ünïcode ☕"))

    assert tags["title"] == 'He said "hi" = ok'
    assert tags["artist"] == "Ünïcode ☕"


@pytest.mark.parametrize(
    "probe", ["", "not json at all", "[]"], ids=["empty", "garbage", "not-an-object"]
)
def test_probe_falls_back_when_output_is_unusable(probe: str) -> None:
    assert _parse_probe(probe) == (None, {})


def test_probe_falls_back_to_the_container_duration() -> None:
    """A video's first stream can be cover art, which has no duration."""
    parsed = json.loads(probe_output())
    del parsed["streams"][0]["duration"]

    duration, _ = _parse_probe(json.dumps(parsed))

    assert duration == 3541


def test_get_file_info_carries_the_tags_through() -> None:
    with (
        patch(
            "podcast_rss_generator.assets._make_http_request",
            return_value=make_response(),
        ),
        patch(
            "podcast_rss_generator.assets._run_ffprobe_with_retry",
            return_value=probe_output(title="Tagged"),
        ),
    ):
        info = get_file_info("https://example.com/a.mp3")

    assert info["tags"] == {"title": "Tagged"}


# --- the merge ---------------------------------------------------------


def test_tags_fill_the_fields_the_config_omits() -> None:
    config = {"episodes": [episode()]}

    resolved, _ = resolve_episodes(
        config,
        probe=lambda _url: file_info(
            title="Episode 42", comment="Show notes", track="42", disc="2"
        ),
    )

    filled = resolved["episodes"][0]
    assert filled["title"] == "Episode 42"
    assert filled["description"] == "Show notes"
    assert filled["episode"] == 42
    assert filled["season"] == 2


def test_the_config_always_wins() -> None:
    config = {
        "episodes": [episode(title="From the config", description="Also the config")]
    }

    resolved, _ = resolve_episodes(
        config, probe=lambda _url: file_info(title="From the tag", comment="Tag notes")
    )

    filled = resolved["episodes"][0]
    assert filled["title"] == "From the config"
    assert filled["description"] == "Also the config"


def test_a_fully_specified_episode_is_never_probed() -> None:
    """Nothing to fill means no reason to reach for the asset here."""
    config = {
        "episodes": [
            episode(title="T", description="D", episode=1, season=1),
        ]
    }

    def explode(_url: str) -> FileInfo:
        raise AssertionError("probed an episode that needed nothing")

    resolved, probed = resolve_episodes(config, probe=explode)

    assert probed == {}
    assert resolved["episodes"][0]["title"] == "T"


def test_one_probe_per_asset() -> None:
    """Two episodes may point at one file; it is fetched once."""
    calls: list[str] = []

    def counting_probe(url: str) -> FileInfo:
        calls.append(url)
        return file_info(title="Shared")

    config = {"episodes": [episode(), episode()]}
    _, probed = resolve_episodes(config, probe=counting_probe)

    assert calls == ["https://example.com/ep1.mp3"]
    assert set(probed) == {"https://example.com/ep1.mp3"}


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ({"description": "Preferred"}, "Preferred"),
        ({"TDES": "Podcast frame", "comment": "Comment"}, "Podcast frame"),
        ({"comment": "Comment only"}, "Comment only"),
    ],
    ids=["description", "raw-TDES-frame", "comment"],
)
def test_description_sources_are_tried_in_order(
    tags: dict[str, str], expected: str
) -> None:
    config = {"episodes": [episode()]}

    resolved, _ = resolve_episodes(config, probe=lambda _url: file_info(**tags))

    assert resolved["episodes"][0]["description"] == expected


@pytest.mark.parametrize(
    ("track", "expected"),
    [("7", 7), ("7/12", 7), ("0", None), ("not a number", None), ("", None)],
    ids=["bare", "of-total", "zero", "text", "blank"],
)
def test_track_tags_become_episode_numbers(track: str, expected: int | None) -> None:
    config = {"episodes": [episode()]}

    resolved, _ = resolve_episodes(config, probe=lambda _url: file_info(track=track))

    assert resolved["episodes"][0].get("episode") == expected


def test_a_blank_config_value_counts_as_absent() -> None:
    config = {"episodes": [episode(title="   ")]}

    resolved, _ = resolve_episodes(config, probe=lambda _url: file_info(title="Tagged"))

    assert resolved["episodes"][0]["title"] == "Tagged"


def test_an_untagged_asset_leaves_the_fields_alone() -> None:
    """The normal validation pass then reports them, as it would anyway."""
    config = {"episodes": [episode()]}

    resolved, _ = resolve_episodes(config, probe=lambda _url: file_info())

    assert "title" not in resolved["episodes"][0]


def test_resolving_does_not_mutate_the_config_it_was_given() -> None:
    original = episode()
    config = {"episodes": [original]}

    resolve_episodes(config, probe=lambda _url: file_info(title="Tagged"))

    assert original == episode()


# --- pre-enrichment validation ----------------------------------------


def test_asset_references_accept_the_example_config() -> None:
    with CONFIG_FILE.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    assert validate_asset_references(config) == (True, [])


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ("not a mapping", "Config must be a dictionary"),
        ({}, "Missing required 'episodes' section"),
        ({"episodes": "nope"}, "Episodes section must be a list"),
        ({"episodes": ["nope"]}, "Episode 1 must be a dictionary"),
        ({"episodes": [{}]}, "Episode 1: Missing required field 'asset_url'"),
        (
            {"episodes": [{"asset_url": "not-a-url"}]},
            "Episode 1: Invalid asset_url format 'not-a-url'",
        ),
    ],
    ids=["scalar", "no-episodes", "not-a-list", "not-a-dict", "no-url", "bad-url"],
)
def test_asset_references_report_what_probing_depends_on(
    config: Any, expected: str
) -> None:
    is_valid, errors = validate_asset_references(config)

    assert not is_valid
    assert expected in errors


# --- the flag ----------------------------------------------------------


def _write_config(path: Path, episodes: list[dict[str, Any]]) -> Path:
    config = {
        "metadata": {
            "title": "Show",
            "description": "About things",
            "link": "https://example.com",
            "rss_feed_url": "https://example.com/feed.xml",
            "language": "en-us",
            "email": "host@example.com",
            "author": "Host",
        },
        "episodes": episodes,
    }
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def test_the_flag_is_off_by_default(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Without it, an episode relying on its tags fails as it always has."""
    config = _write_config(tmp_path / "config.yaml", [episode()])
    monkeypatch.setattr(
        "sys.argv",
        ["podcast-rss-generator", "--input-file", str(config), "--dry-run"],
    )

    with (
        patch("podcast_rss_generator.cli.resolve_episodes") as resolve,
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    resolve.assert_not_called()
    assert "Missing required field 'title'" in capsys.readouterr().out


def test_the_flag_resolves_the_missing_fields(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _write_config(tmp_path / "config.yaml", [episode()])
    monkeypatch.setattr(
        "sys.argv",
        [
            "podcast-rss-generator",
            "--input-file",
            str(config),
            "--read-asset-metadata",
            "--dry-run",
        ],
    )

    with (
        patch(
            "podcast_rss_generator.assets._make_http_request",
            return_value=make_response(),
        ),
        patch(
            "podcast_rss_generator.assets._run_ffprobe_with_retry",
            return_value=probe_output(title="From the asset", comment="Notes"),
        ),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 0
    assert "Config validation passed" in capsys.readouterr().out


def test_the_flag_refuses_to_skip_the_verification_it_depends_on(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "podcast-rss-generator",
            "--input-file",
            str(CONFIG_FILE),
            "--read-asset-metadata",
            "--skip-asset-verification",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    assert "cannot be combined" in capsys.readouterr().out


def test_the_action_input_turns_the_flag_on(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The Docker action passes its inputs as environment variables."""
    config = _write_config(tmp_path / "config.yaml", [episode()])
    monkeypatch.setenv("INPUT_READ_ASSET_METADATA", "true")
    monkeypatch.setattr(
        "sys.argv",
        ["podcast-rss-generator", "--input-file", str(config), "--dry-run"],
    )

    with (
        patch(
            "podcast_rss_generator.cli.resolve_episodes",
            return_value=({"metadata": {}, "episodes": []}, {}),
        ) as resolve,
        pytest.raises(SystemExit),
    ):
        main()

    resolve.assert_called_once()


def test_the_feed_reuses_the_probe_the_merge_already_paid_for(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One probe per asset across both stages, not one per stage."""
    config = _write_config(tmp_path / "config.yaml", [episode()])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "podcast-rss-generator",
            "--input-file",
            str(config),
            "--read-asset-metadata",
            "--output-file",
            str(tmp_path / "feed.xml"),
        ],
    )

    with (
        patch(
            "podcast_rss_generator.assets._make_http_request",
            return_value=make_response(),
        ) as head,
        patch(
            "podcast_rss_generator.assets._run_ffprobe_with_retry",
            return_value=probe_output(title="From the asset", comment="Notes"),
        ) as ffprobe,
    ):
        main()

    assert head.call_count == 1
    assert ffprobe.call_count == 1
    assert "From the asset" in (tmp_path / "feed.xml").read_text(encoding="utf-8")
