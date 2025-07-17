import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
import argparse
import time
import re
import uuid
import sys
import os
from urllib.parse import urlparse

import markdown
import requests
import yaml
import html
from sh import ffprobe, ErrorReturnCode
from retry import retry


# Fix CDATA delimiter escaping
def _escape_cdata(text):
    try:
        if "&" in text:
            text = text.replace("&", "&amp;")
        # Don't escape < and > in CDATA per RSS spec
        return text
    except TypeError:
        raise TypeError("cannot serialize %r (type %s)" % (text, type(text).__name__))


ET._escape_cdata = _escape_cdata


def read_podcast_config(yaml_file_path):
    with open(yaml_file_path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def convert_iso_to_rfc2822(iso_date):
    # Replace 'Z' with '+00:00' for Python < 3.11 compatibility
    compatible_iso_date = iso_date.replace("Z", "+00:00")
    date_obj = datetime.fromisoformat(compatible_iso_date)
    return format_datetime(date_obj)


@retry(tries=5, delay=2, backoff=2, logger=None)
def _make_http_request(url):
    """Make HTTP request with retry logic"""
    return requests.head(url, allow_redirects=True)


def _run_ffprobe_with_retry(url, max_retries=5, delay=2):
    """
    Run ffprobe with manual retry logic to handle ErrorReturnCode exceptions
    """
    retries = 0
    while retries < max_retries:
        try:
            return ffprobe(
                "-hide_banner",
                "-v",
                "quiet",
                "-show_streams",
                "-print_format",
                "flat",
                url,
            )
        except ErrorReturnCode:
            retries += 1
            if retries >= max_retries:
                print(
                    f"Failed to run ffprobe after {max_retries} attempts for URL: {url}"
                )
                # Return empty string if all retries fail
                return ""
            print(
                f"ffprobe failed (attempt {retries}/{max_retries}), retrying in {delay} seconds..."
            )
            time.sleep(delay)
            delay *= 2  # Exponential backoff


def get_file_info(url):
    # Make HTTP request with retry logic
    response = _make_http_request(url)

    # Get duration of audio/video file
    # We're using the response.url here in order to
    # follow redirects and get the actual file

    # Run ffprobe with retry logic
    probe = _run_ffprobe_with_retry(response.url)

    # If probe is empty (all retries failed), set duration to None
    if not probe:
        return {
            "content-length": response.headers.get("content-length"),
            "content-type": response.headers.get("content-type"),
            "duration": None,
        }

    lines = probe.split("\n")

    # Filtering out the line that contains 'streams.stream.0.duration'
    duration_line = next(
        (line for line in lines if line.startswith("streams.stream.0.duration=")), None
    )

    if duration_line:
        # Extracting the numeric value and converting it to an integer
        duration = int(float(duration_line.split("=")[1].strip('"')))
    else:
        duration = None

    # --- Extract content hash from headers ---
    content_hash = None
    headers = response.headers

    # 1. Check for x-amz-checksum-sha256
    sha256_hash = headers.get("x-amz-checksum-sha256")
    if sha256_hash:
        content_hash = f"sha256:{sha256_hash}"

    # 2. Check for GCS MD5 (if SHA256 not found)
    if not content_hash:
        gcs_hash = headers.get("x-goog-hash")
        if gcs_hash:
            # Extract base64 md5 value - look for md5= and capture until next comma or end of string
            match = re.search(r"md5=([^,]+)", gcs_hash)
            if match:
                # Note: GCS MD5 is base64 encoded, needs decoding if we wanted raw bytes,
                # but for a GUID string, the base64 representation is fine and unique.
                content_hash = f"md5:{match.group(1)}"

    # 3. Check ETag (if other hashes not found)
    if not content_hash:
        etag = headers.get("ETag", "").strip('" ')  # Remove quotes and whitespace
        if etag:  # Use any non-empty ETag as a fallback hash
            content_hash = f"etag:{etag}"

    return {
        "content-length": headers.get("content-length"),
        "content-type": headers.get("content-type"),
        "duration": duration,
        "content_hash": content_hash,  # Add the extracted hash to the result
    }


def format_description(description):
    """Convert Markdown to HTML and wrap in CDATA"""
    html_description = markdown.markdown(description)
    # Unescape HTML entities since CDATA should contain literal characters
    unescaped_html = html.unescape(html_description)
    wrapped_description = f"<![CDATA[{unescaped_html}]]>"

    # Handle byte limit
    byte_limit = 4000
    if len(wrapped_description.encode("utf-8")) > byte_limit:
        content_length = byte_limit - len("<![CDATA[]]>".encode("utf-8"))
        if content_length > 0:
            truncated_content = unescaped_html[:content_length]
            # Avoid breaking HTML tags
            if (
                "<" in truncated_content
                and ">" not in truncated_content[truncated_content.rfind("<") :]
            ):
                truncated_content = truncated_content[: truncated_content.rfind("<")]
            wrapped_description = f"<![CDATA[{truncated_content}]]>"

    return wrapped_description


def is_valid_url(url):
    """Check if a URL is valid"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def is_valid_email(email):
    """Basic email validation"""
    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(email_pattern, email) is not None


def is_valid_iso_date(date_string):
    """Check if a date string is valid ISO format"""
    try:
        # Handle both 'Z' and timezone offset formats
        compatible_date = date_string.replace("Z", "+00:00")
        datetime.fromisoformat(compatible_date)
        return True
    except ValueError:
        return False


def validate_config(config):
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
        if field in metadata and metadata[field]:
            if not is_valid_url(metadata[field]):
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
        if "publication_date" in episode:
            if not is_valid_iso_date(episode["publication_date"]):
                errors.append(
                    f"Episode {i + 1}: Invalid publication_date format '{episode['publication_date']}' (must be ISO format like '2023-01-15T10:00:00Z')"
                )

        # Validate asset_url
        if "asset_url" in episode:
            if not is_valid_url(episode["asset_url"]):
                errors.append(
                    f"Episode {i + 1}: Invalid asset_url format '{episode['asset_url']}'"
                )

        # Validate optional URL fields
        episode_url_fields = ["link", "image"]
        for field in episode_url_fields:
            if field in episode and episode[field]:
                if not is_valid_url(episode[field]):
                    errors.append(
                        f"Episode {i + 1}: Invalid URL format in field '{field}': '{episode[field]}'"
                    )

        # Validate episode number
        if "episode" in episode:
            if not isinstance(episode["episode"], int) or episode["episode"] < 1:
                errors.append(
                    f"Episode {i + 1}: Field 'episode' must be a positive integer"
                )

        # Validate season number
        if "season" in episode:
            if not isinstance(episode["season"], int) or episode["season"] < 1:
                errors.append(
                    f"Episode {i + 1}: Field 'season' must be a positive integer"
                )

        # Validate episode type
        if "episode_type" in episode:
            if episode["episode_type"] not in valid_episode_types:
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


def generate_rss(config, output_file_path, skip_asset_verification=False):
    # --- Namespace Registration --- (Ensure podcast namespace is included)
    ET.register_namespace("itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    ET.register_namespace("atom", "http://www.w3.org/2005/Atom")
    ET.register_namespace(
        "podcast", "https://podcastindex.org/namespace/1.0"
    )  # Add podcast namespace

    # --- Root Element Setup --- (Add podcast namespace attribute)
    rss = ET.Element(
        "rss",
        version="2.0",
        attrib={
            "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
            "xmlns:atom": "http://www.w3.org/2005/Atom",
            "xmlns:podcast": "https://podcastindex.org/namespace/1.0",  # Add podcast namespace
        },
    )

    # Global itunes:explicit setting
    global_explicit = (
        "yes" if config["metadata"].get("itunes_explicit", False) else "no"
    )

    # --- Metadata Section --- (Add copyright)
    channel = ET.SubElement(rss, "channel")
    metadata = config["metadata"]

    # Helper function to get metadata with backward compatibility
    def get_meta(key, old_key=None, required=False, default=None):
        # If old_key is not provided, use key itself for checking
        check_keys = [key]
        if old_key:
            check_keys.append(old_key)

        value = None
        for k in check_keys:
            value = metadata.get(k)
            if value is not None:
                break  # Found a value

        if required and value is None:
            key_str = f"'{key}'"
            if old_key:
                key_str += f" or '{old_key}'"
            raise ValueError(f"Missing required metadata key: {key_str}")

        return value if value is not None else default

    ET.SubElement(channel, "title").text = metadata[
        "title"
    ]  # Title is fundamental, no old key needed
    ET.SubElement(channel, "description").text = format_description(
        metadata["description"]
    )
    ET.SubElement(channel, "language").text = metadata.get("language", "en-us")
    ET.SubElement(channel, "link").text = metadata["link"]
    ET.SubElement(
        channel, "generator"
    ).text = (
        "Podcast RSS Generator (https://github.com/vpetersson/podcast-rss-generator)"
    )
    ET.SubElement(
        channel,
        "atom:link",
        href=get_meta(
            "rss_feed_url", "rss_feed_url", required=True
        ),  # Use helper, though no old key needed
        rel="self",
        type="application/rss+xml",
    )

    # Explicit tag (backward compatibility)
    explicit_val = get_meta("explicit", "itunes_explicit", default=False)
    explicit_text = "yes" if explicit_val else "no"
    ET.SubElement(channel, "itunes:explicit").text = explicit_text

    # Owner/Email (backward compatibility)
    email_val = get_meta("email", "itunes_email", required=True)
    itunes_owner = ET.SubElement(channel, "itunes:owner")
    ET.SubElement(itunes_owner, "itunes:email").text = email_val

    # Author (backward compatibility)
    author_val = get_meta("author", "itunes_author", required=True)
    ET.SubElement(channel, "itunes:author").text = author_val

    # Summary (use description)
    itunes_summary = ET.SubElement(channel, "itunes:summary")
    itunes_summary.text = metadata["description"]

    # Category (backward compatibility)
    category_val = get_meta("category", "itunes_category")
    if category_val:
        ET.SubElement(channel, "itunes:category", text=category_val)

    # Image (backward compatibility, already handled)
    image_val = get_meta(
        "image", "image"
    )  # Uses 'image' as both new and old effective key here
    if image_val:
        itunes_image = ET.SubElement(channel, "itunes:image")
        itunes_image.set("href", image_val)

    # Copyright (Optional)
    copyright_val = metadata.get("copyright")
    if copyright_val:
        ET.SubElement(channel, "copyright").text = copyright_val

    # Recommended Channel Elements (Podcast Standards Project)
    # podcast:locked
    locked_val = get_meta("podcast_locked", default="no")  # Default to 'no' (false)
    # Ensure the value is either 'yes' or 'no'
    locked_text = (
        "yes"
        if str(locked_val).lower() == "true" or str(locked_val).lower() == "yes"
        else "no"
    )
    ET.SubElement(
        channel, "podcast:locked", owner=email_val
    ).text = locked_text  # Requires owner email

    # podcast:guid
    # Prefer explicitly defined GUID in config, otherwise generate based on feed URL
    guid_val = get_meta("podcast_guid")
    if not guid_val:
        feed_url_val = get_meta(
            "rss_feed_url", required=True
        )  # Feed URL is required anyway
        # Generate UUID v5 based on the feed URL namespace
        guid_val = str(uuid.uuid5(uuid.NAMESPACE_URL, feed_url_val))
        print(
            f"Warning: podcast_guid not found in metadata. Generated GUID: {guid_val}"
        )
        print("It is recommended to explicitly set podcast_guid in your config file.")
    ET.SubElement(channel, "podcast:guid").text = guid_val

    # --- Episode Processing --- (Add transcript logic)
    use_hash_guid = metadata.get("use_asset_hash_as_guid", False)

    for episode in config["episodes"]:
        print(f"Processing episode {episode['title']}...")

        # Replace \'Z\' with \'+00:00\' for Python < 3.11 compatibility with fromisoformat
        pub_date_str = episode["publication_date"].replace("Z", "+00:00")
        # Parse the date string
        pub_date = datetime.fromisoformat(pub_date_str)
        # If the parsed date is naive (no timezone info), assume it's UTC
        if pub_date.tzinfo is None:
            pub_date = pub_date.replace(tzinfo=timezone.utc)

        # Now compare the timezone-aware publication date with the current UTC time
        if not pub_date < datetime.now(timezone.utc):
            print(
                f"Skipping episode {episode['title']} as it's not scheduled to be released until {episode['publication_date']}."
            )
            continue

        if skip_asset_verification:
            print(f"  Skipping asset verification for {episode['asset_url']}")
            # Provide default/placeholder values
            file_info = {
                "content-length": "0",  # Required by enclosure
                "content-type": "application/octet-stream",  # Generic fallback type
                "duration": None,
                "content_hash": None,
            }
        else:
            file_info = get_file_info(episode["asset_url"])

        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "pubDate").text = convert_iso_to_rfc2822(pub_date_str)
        ET.SubElement(item, "title").text = episode["title"]
        ET.SubElement(item, "description").text = format_description(
            episode["description"]
        )

        # Determine GUID: Use hash if requested and available, else use asset_url
        guid_text = episode["asset_url"]  # Default
        if use_hash_guid and file_info.get("content_hash"):
            guid_text = file_info["content_hash"]
            print(f"  Using content hash for GUID: {guid_text}")
        else:
            print(f"  Using asset URL for GUID: {guid_text}")

        ET.SubElement(item, "guid").text = guid_text
        ET.SubElement(
            item,
            "enclosure",
            url=episode["asset_url"],
            # Use fetched or default values
            type=file_info.get("content-type", "application/octet-stream"),
            length=str(file_info.get("content-length", "0")),
        )

        # Apply itunes:explicit setting (check episode first, then global)
        episode_explicit_val = episode.get("explicit", episode.get("itunes_explicit"))
        if episode_explicit_val is not None:
            # Use episode-specific value if present
            explicit_text_item = "yes" if episode_explicit_val else "no"
        else:
            # Fallback to global setting
            explicit_text_item = global_explicit
        ET.SubElement(item, "itunes:explicit").text = explicit_text_item

        # Add itunes:duration tag if available
        if file_info.get("duration") is not None:
            itunes_duration = ET.SubElement(item, "itunes:duration")
            itunes_duration.text = str(file_info["duration"])

        # iTunes-specific tags
        if episode.get("episode") is not None:
            itunes_episode = ET.SubElement(item, "itunes:episode")
            itunes_episode.text = str(episode["episode"])

        if episode.get("season") is not None:
            itunes_season = ET.SubElement(item, "itunes:season")
            itunes_season.text = str(episode["season"])

        if episode.get("episode_type") is not None:
            itunes_episode_type = ET.SubElement(item, "itunes:episodeType")
            itunes_episode_type.text = episode["episode_type"]

        # Add link if available, if not, use global
        link = ET.SubElement(item, "link")
        link.text = episode.get("link", metadata["link"])

        # Determine the correct image URL (episode-specific or channel default)
        # Use episode specific artwork if available, falling back to channel image
        image_url = episode.get("image", metadata.get("image"))

        # Creating the 'itunes:image' element if an image URL is available
        if image_url:
            itunes_image = ET.SubElement(item, "itunes:image")
            itunes_image.set("href", image_url)

        # Add transcript links if available
        if "transcripts" in episode and isinstance(episode["transcripts"], list):
            for transcript_info in episode["transcripts"]:
                if "url" in transcript_info and "type" in transcript_info:
                    # Basic required attributes
                    transcript_attrs = {
                        "url": transcript_info["url"],
                        "type": transcript_info["type"],
                    }
                    # Add optional attributes if they exist
                    if "language" in transcript_info:
                        transcript_attrs["language"] = transcript_info["language"]
                    if "rel" in transcript_info:
                        transcript_attrs["rel"] = transcript_info["rel"]

                    ET.SubElement(item, "podcast:transcript", attrib=transcript_attrs)
                else:
                    print(
                        f"  Skipping invalid transcript entry for episode {episode['title']}: {transcript_info}"
                    )

    tree = ET.ElementTree(rss)
    tree.write(output_file_path, encoding="UTF-8", xml_declaration=True)


def main():
    parser = argparse.ArgumentParser(description="Process some parameters.")

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


if __name__ == "__main__":
    main()
