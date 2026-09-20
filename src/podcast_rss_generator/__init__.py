"""Generate a podcast RSS feed from a YAML configuration file.

The public surface is re-exported here, so callers write

    from podcast_rss_generator import generate_rss, read_podcast_config

without depending on which module a function currently lives in.
"""

from podcast_rss_generator.assets import FileInfo, get_file_info
from podcast_rss_generator.config import read_podcast_config
from podcast_rss_generator.feed import (
    convert_iso_to_rfc2822,
    format_description,
    generate_rss,
)
from podcast_rss_generator.validation import (
    is_valid_email,
    is_valid_iso_date,
    is_valid_url,
    validate_config,
)

# CalVer, YYYY.M.PATCH. This is the single source of truth for the version:
# hatchling reads it from here (see [tool.hatch.version] in pyproject.toml),
# so the package metadata and `--version` can never disagree.
__version__ = "2026.9.0"

__all__ = [
    "FileInfo",
    "__version__",
    "convert_iso_to_rfc2822",
    "format_description",
    "generate_rss",
    "get_file_info",
    "is_valid_email",
    "is_valid_iso_date",
    "is_valid_url",
    "read_podcast_config",
    "validate_config",
]
