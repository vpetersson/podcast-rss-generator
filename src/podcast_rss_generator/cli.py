"""The command line entry point."""

import argparse
import os
import sys

import yaml

from podcast_rss_generator import __version__
from podcast_rss_generator.assets import FileInfo
from podcast_rss_generator.config import read_podcast_config
from podcast_rss_generator.enrich import resolve_episodes
from podcast_rss_generator.feed import generate_rss
from podcast_rss_generator.validation import validate_asset_references, validate_config


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
        "--read-asset-metadata",
        action="store_true",
        help=(
            "Fill in episode title, description, episode and season from the "
            "asset's own ID3/container tags when the config omits them. The "
            "config always wins where both are present. Off by default."
        ),
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

    if os.environ.get("INPUT_READ_ASSET_METADATA", "").lower() == "true":
        args.read_asset_metadata = True

    # Reading tags means probing the assets, which is the one thing
    # --skip-asset-verification exists to avoid. Refusing here is clearer than
    # silently ignoring one of the two flags and reporting every title as
    # missing.
    if args.read_asset_metadata and args.skip_asset_verification:
        print(
            "Error: --read-asset-metadata cannot be combined with "
            "--skip-asset-verification; reading tags requires probing the assets."
        )
        sys.exit(1)

    print(f"Input file: {args.input_file}")
    if not args.dry_run:
        print(f"Output file: {args.output_file}")
    if args.skip_asset_verification:
        print("Skipping asset verification.")
    if args.read_asset_metadata:
        print("Reading episode metadata from asset tags where the config omits it.")
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

    # Read metadata off the assets before validating, so that the fields it
    # supplies are not reported as missing. The probe results are carried
    # forward so each asset is fetched once rather than once per stage.
    #
    # This probes under --dry-run too: a dry run that skipped it would report
    # failures for every field the real run resolves, which is precisely the
    # config it is being asked to check.
    asset_info: dict[str, FileInfo] = {}
    if args.read_asset_metadata:
        references_ok, reference_errors = validate_asset_references(config)
        if not references_ok:
            print("✗ Config validation failed:")
            for error in reference_errors:
                print(f"  - {error}")
            sys.exit(1)

        config, asset_info = resolve_episodes(config)

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
        config,
        args.output_file,
        skip_asset_verification=args.skip_asset_verification,
        asset_info=asset_info,
    )
