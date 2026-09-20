"""Tests that the distribution is assembled the way the Dockerfile expects.

The Docker image installs the package and invokes the console script, so a
missing module or a renamed entry point breaks the published action even
though every other test still passes against the source tree.
"""

import subprocess
import sys
from importlib.metadata import distribution, entry_points, metadata
from pathlib import Path

import pytest
from helpers import REPO_ROOT

import podcast_rss_generator

EXPECTED_MODULES = [
    "podcast_rss_generator.assets",
    "podcast_rss_generator.cli",
    "podcast_rss_generator.config",
    "podcast_rss_generator.feed",
    "podcast_rss_generator.validation",
]


def test_the_distribution_is_installed() -> None:
    """The tests import the package they installed, not a stray directory."""
    assert distribution("podcast-rss-generator").name == "podcast-rss-generator"


def test_nothing_importable_sits_at_the_repository_root() -> None:
    """The src layout is what makes the test above meaningful: with a flat
    layout, `import podcast_rss_generator` would find the working tree even if
    the wheel were missing half its modules.
    """
    assert not (REPO_ROOT / "podcast_rss_generator").exists()
    assert not (REPO_ROOT / "rss_generator.py").exists()
    assert (REPO_ROOT / "src" / "podcast_rss_generator" / "__init__.py").is_file()


@pytest.mark.parametrize("module", EXPECTED_MODULES)
def test_module_ships_in_the_distribution(module: str) -> None:
    __import__(module)


def test_the_package_ships_its_typing_marker() -> None:
    """PEP 561: without py.typed in the wheel, a consumer running mypy sees
    the package as untyped no matter how strictly it is checked here."""
    location = podcast_rss_generator.__file__
    assert location is not None
    assert (Path(location).parent / "py.typed").is_file()


def test_public_api_is_re_exported() -> None:
    for name in podcast_rss_generator.__all__:
        assert hasattr(podcast_rss_generator, name), name


def test_console_script_is_declared() -> None:
    scripts = entry_points(group="console_scripts")
    entry = next(ep for ep in scripts if ep.name == "podcast-rss-generator")
    assert entry.value == "podcast_rss_generator.cli:main"


def test_distribution_metadata_is_complete() -> None:
    fields = metadata("podcast-rss-generator")
    assert fields["Name"] == "podcast-rss-generator"
    assert fields["Version"] == podcast_rss_generator.__version__
    assert fields["Requires-Python"] == ">=3.11"


def test_module_invocation_reports_the_version() -> None:
    """`python -m podcast_rss_generator` is the fallback the image does not
    use but users reach for."""
    result = subprocess.run(
        [sys.executable, "-m", "podcast_rss_generator", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == (
        f"podcast-rss-generator {podcast_rss_generator.__version__}"
    )
