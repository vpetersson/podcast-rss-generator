"""Tests for the command line entry point.

Where the version comes from is tested in test_packaging.py; here it is only
the flag's behaviour that matters.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from helpers import CONFIG_FILE

import podcast_rss_generator
from podcast_rss_generator.cli import main


def test_version_flag_prints_version(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.argv", ["podcast-rss-generator", "--version"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    assert podcast_rss_generator.__version__ in capsys.readouterr().out


def test_dry_run_validates_the_example_config(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        ["podcast-rss-generator", "--input-file", str(CONFIG_FILE), "--dry-run"],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    assert "Config validation passed" in capsys.readouterr().out
    # --dry-run must not write a feed.
    assert list(tmp_path.iterdir()) == []


def test_missing_config_file_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "podcast-rss-generator",
            "--input-file",
            str(tmp_path / "nope.yaml"),
            "--dry-run",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1


def test_invalid_config_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    broken = tmp_path / "broken.yaml"
    broken.write_text("metadata: {title: Only a title}\n", encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv", ["podcast-rss-generator", "--input-file", str(broken), "--dry-run"]
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1


def test_generates_a_feed_end_to_end(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "feed.xml"
    monkeypatch.setattr(
        "sys.argv",
        [
            "podcast-rss-generator",
            "--input-file",
            str(CONFIG_FILE),
            "--output-file",
            str(output),
            "--skip-asset-verification",
        ],
    )

    main()

    assert output.read_text(encoding="utf-8").startswith("<?xml version=")


def test_input_dry_run_env_var_overrides_the_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The Docker action passes its inputs as environment variables."""
    output = tmp_path / "feed.xml"
    monkeypatch.setenv("INPUT_DRY_RUN", "true")
    monkeypatch.setattr(
        "sys.argv",
        [
            "podcast-rss-generator",
            "--input-file",
            str(CONFIG_FILE),
            "--output-file",
            str(output),
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    assert not output.exists()


def test_input_skip_asset_verification_env_var_overrides_the_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "feed.xml"
    monkeypatch.setenv("INPUT_SKIP_ASSET_VERIFICATION", "true")
    monkeypatch.setattr(
        "sys.argv",
        [
            "podcast-rss-generator",
            "--input-file",
            str(CONFIG_FILE),
            "--output-file",
            str(output),
        ],
    )
    # Nothing should reach the network: the example config points at URLs that
    # do not exist.
    probe = MagicMock()
    monkeypatch.setattr("podcast_rss_generator.assets._make_http_request", probe)

    main()

    assert output.exists()
    probe.assert_not_called()
