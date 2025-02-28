"""Command-line interface for the podcast RSS generator."""

import argparse
import sys

from podcast_rss_generator.generator import generate_rss, read_podcast_config


def main():
    """Entry point for the podcast-rss-generator command."""
    parser = argparse.ArgumentParser(
        description="Generate an RSS feed for audio/video podcasts."
    )

    parser.add_argument(
        "--input-file",
        type=str,
        default="podcast_config.yaml",
        help="Input YAML file (default: podcast_config.yaml)"
    )
    parser.add_argument(
        "--output-file",
        type=str,
        default="podcast_feed.xml",
        help="Output XML file (default: podcast_feed.xml)"
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show version information and exit"
    )

    # Parse arguments from the command line
    args = parser.parse_args()

    if args.version:
        from podcast_rss_generator import __version__
        print(f"podcast-rss-generator version {__version__}")
        sys.exit(0)

    print(f"Input file: {args.input_file}, Output file: {args.output_file}")

    try:
        config = read_podcast_config(args.input_file)
        generate_rss(config, args.output_file)
        print(f"RSS feed successfully generated at {args.output_file}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()