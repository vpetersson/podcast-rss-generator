"""Generate a podcast RSS feed from a YAML configuration file.

The public surface is re-exported here, so callers write

    from podcast_rss_generator import generate_rss, read_podcast_config

without depending on which module a function currently lives in.
"""

from importlib.metadata import version

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

# The version is declared in pyproject.toml and nowhere else. Reading it back
# from the installed distribution's metadata means there is no second copy to
# bump, and `--version` reports what was actually installed rather than what
# the working tree happens to say.
#
# This raises PackageNotFoundError if the package is not installed, which is
# the honest answer: under the src layout, an import that resolves at all came
# from an installed distribution.
__version__ = version("podcast-rss-generator")

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
