"""Tests that the distribution is assembled the way the Dockerfile expects.

The Docker image installs the package and invokes the console script, so a
missing module or a renamed entry point breaks the published action even
though every other test still passes against the source tree.
"""

import re
import subprocess
import sys
import tomllib
from importlib.metadata import distribution, entry_points, metadata
from pathlib import Path

import pytest
from helpers import REPO_ROOT

import podcast_rss_generator

# CalVer: YYYY.M.PATCH, with the month unpadded so the string matches what
# PEP 440 normalises the package version to.
CALVER_PATTERN = re.compile(r"^\d{4}\.(1[0-2]|[1-9])\.\d+$")

EXPECTED_MODULES = [
    "podcast_rss_generator.assets",
    "podcast_rss_generator.cli",
    "podcast_rss_generator.config",
    "podcast_rss_generator.enrich",
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
    assert fields["Requires-Python"] == ">=3.11"


def declared_version() -> str:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        project_version: str = tomllib.load(handle)["project"]["version"]
    return project_version


def test_pyproject_declares_a_calver_version() -> None:
    assert CALVER_PATTERN.match(declared_version())


def test_the_installed_version_matches_pyproject() -> None:
    """pyproject.toml is the only place the version is written; everything
    else reads it back. `uv run` re-syncs before it runs, so this mostly
    guards the environments that do not — the wheel CI job and the Docker
    image, where a stale install would otherwise report the wrong version.
    """
    assert metadata("podcast-rss-generator")["Version"] == declared_version()
    assert podcast_rss_generator.__version__ == declared_version()


def test_the_version_is_not_duplicated_in_the_source() -> None:
    """The package reads its version from the installed metadata. A literal
    reintroduced anywhere under src/ is a second copy to forget to bump.
    """
    literal = re.compile(r"""__version__\s*=\s*['"]\d""")
    offenders = [
        path.relative_to(REPO_ROOT)
        for path in (REPO_ROOT / "src").rglob("*.py")
        if literal.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


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
