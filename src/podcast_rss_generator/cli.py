"""The command line entry point."""

import argparse
import os
import sys

import yaml

from podcast_rss_generator import __version__
from podcast_rss_generator.config import read_podcast_config
from podcast_rss_generator.feed import generate_rss
from podcast_rss_generator.validation import validate_config


def main() -> None:
    parser = argparse.ArgumentParser(
        # Pinned so `python -m podcast_rss_generator` does not announce itself
        # as "__main__.py" in usage and --version output.
        prog="podcast-rss-generator",
        description="Generate a podcast RSS feed from a YAML configuration file.",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--input-file", type=str, default="podcast_config.yaml", help="Input YAML file"
    )
    parser.add_argument(
        "--output-file", type=str, default="podcast_feed.xml", help="Output XML file"
    )
    parser.add_argument(
        "--skip-asset-verification",
        action="store_true",  # Makes it a boolean flag
        help="Skip HTTP HEAD and ffprobe checks for asset URLs (use for testing/fake URLs)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration file only, do not generate RSS feed",
    )

    # Parse arguments from the command line
    args = parser.parse_args()

    # Check for GitHub Actions environment variables and override if present
    if os.environ.get("INPUT_SKIP_ASSET_VERIFICATION", "").lower() == "true":
        args.skip_asset_verification = True

    if os.environ.get("INPUT_DRY_RUN", "").lower() == "true":
        args.dry_run = True

    print(f"Input file: {args.input_file}")
    if not args.dry_run:
        print(f"Output file: {args.output_file}")
    if args.skip_asset_verification:
        print("Skipping asset verification.")
    if args.dry_run:
        print("Dry-run mode: validating configuration only.")

    # Read and validate config
    try:
        config = read_podcast_config(args.input_file)
    except FileNotFoundError:
        print(f"Error: Config file '{args.input_file}' not found.")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error: Invalid YAML syntax in '{args.input_file}':")
        print(f"  {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading config file '{args.input_file}': {e}")
        sys.exit(1)

    # Validate configuration
    is_valid, errors = validate_config(config)
    if not is_valid:
        print("✗ Config validation failed:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)

    print("✓ Config validation passed!")

    # If dry-run, stop here
    if args.dry_run:
        print("✓ Dry-run completed successfully.")
        sys.exit(0)

    # Generate RSS feed
    generate_rss(
        config, args.output_file, skip_asset_verification=args.skip_asset_verification
    )
