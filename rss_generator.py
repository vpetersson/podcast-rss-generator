import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
import argparse
import time
import os
import re

import markdown
import requests
import yaml
from sh import ffprobe, ErrorReturnCode
from retry import retry

# Flag to indicate if we're in test mode
TEST_MODE = os.environ.get("RSS_GENERATOR_TEST_MODE", "false").lower() == "true"

# Mock ffprobe output for testing
MOCK_FFPROBE_OUTPUT = """streams.stream.0.index=0
streams.stream.0.codec_name="aac"
streams.stream.0.codec_long_name="AAC (Advanced Audio Coding)"
streams.stream.0.profile="LC"
streams.stream.0.codec_type="audio"
streams.stream.0.codec_tag_string="mp4a"
streams.stream.0.codec_tag="0x6134706d"
streams.stream.0.sample_fmt="fltp"
streams.stream.0.sample_rate="44100"
streams.stream.0.channels=2
streams.stream.0.channel_layout="stereo"
streams.stream.0.bits_per_sample=0
streams.stream.0.initial_padding=0
streams.stream.0.id="0x1"
streams.stream.0.r_frame_rate="0/0"
streams.stream.0.avg_frame_rate="0/0"
streams.stream.0.time_base="1/44100"
streams.stream.0.start_pts=0
streams.stream.0.start_time="0.000000"
streams.stream.0.duration_ts=156170240
streams.stream.0.duration="3541.275283"
streams.stream.0.bit_rate="107301"
streams.stream.0.max_bit_rate="N/A"
streams.stream.0.bits_per_raw_sample="N/A"
streams.stream.0.nb_frames="152510"
streams.stream.0.nb_read_frames="N/A"
streams.stream.0.nb_read_packets="N/A"
streams.stream.0.extradata_size=2
streams.stream.0.disposition.default=1"""


# Mock HTTP response for testing
class MockResponse:
    def __init__(self, url):
        self.url = url
        self.headers = {
            "content-length": "12345678",
            "content-type": "audio/mpeg",
            # Example headers for testing hash extraction
            "ETag": '"d41d8cd98f00b204e9800998ecf8427e"',  # MD5 hash
            # 'ETag': '"abc-1"', # Multipart ETag
            # 'x-amz-checksum-sha256': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
            # 'x-goog-hash': 'crc32c=AAAAAA==,md5=1B2M2Y8AsgTpgAmY7PhCfg==' # Base64 MD5
        }


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
    if TEST_MODE:
        return MockResponse(url)
    return requests.head(url, allow_redirects=True)


def _run_ffprobe_with_retry(url, max_retries=5, delay=2):
    """
    Run ffprobe with manual retry logic to handle ErrorReturnCode exceptions
    """
    if TEST_MODE:
        return MOCK_FFPROBE_OUTPUT

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
        etag = headers.get("ETag", "").strip('" ') # Remove quotes and whitespace
        if etag: # Use any non-empty ETag as a fallback hash
            content_hash = f"etag:{etag}"

    return {
        "content-length": headers.get("content-length"),
        "content-type": headers.get("content-type"),
        "duration": duration,
        "content_hash": content_hash,  # Add the extracted hash to the result
    }


def format_description(description):
    """
    Convert Markdown description to HTML
    """
    html_description = markdown.markdown(description)
    wrapped_description = f"<![CDATA[{html_description}]]>"

    # Ensure byte limit for the channel description
    byte_limit = 4000
    if len(wrapped_description.encode("utf-8")) > byte_limit:
        # Truncate the description if it exceeds the limit
        # Note: Truncation logic might need to be more sophisticated to handle HTML correctly
        wrapped_description = wrapped_description[:byte_limit]

    return wrapped_description


def generate_rss(config, output_file_path, skip_asset_verification=False):
    # --- Namespace Registration --- (Ensure podcast namespace is included)
    ET.register_namespace("itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    ET.register_namespace("atom", "http://www.w3.org/2005/Atom")
    ET.register_namespace("podcast", "https://podcastindex.org/namespace/1.0") # Add podcast namespace

    # --- Root Element Setup --- (Add podcast namespace attribute)
    rss = ET.Element(
        "rss",
        version="2.0",
        attrib={
            "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
            "xmlns:atom": "http://www.w3.org/2005/Atom",
            "xmlns:podcast": "https://podcastindex.org/namespace/1.0" # Add podcast namespace
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
    def get_meta(key, old_key, required=False, default=None):
        value = metadata.get(key, metadata.get(old_key))
        if required and value is None:
            raise ValueError(f"Missing required metadata key: '{key}' or '{old_key}'")
        return value if value is not None else default

    ET.SubElement(channel, "title").text = metadata[
        "title"
    ]  # Title is fundamental, no old key
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

    # --- Episode Processing --- (Add transcript logic)
    use_hash_guid = metadata.get("use_asset_hash_as_guid", False)

    for episode in config["episodes"]:
        print(f"Processing episode {episode['title']}...")

        # Don't pre-publish episodes
        # Replace 'Z' with '+00:00' for Python < 3.11 compatibility with fromisoformat
        pub_date_str = episode["publication_date"].replace("Z", "+00:00")
        if not datetime.fromisoformat(pub_date_str) < datetime.now(timezone.utc):
            print(
                f"Skipping episode {episode['title']} as it's not scheduled to be released until {episode['publication_date']}."
            )
            continue

        if skip_asset_verification:
            print(f"  Skipping asset verification for {episode['asset_url']}")
            # Provide default/placeholder values
            file_info = {
                "content-length": "0", # Required by enclosure
                "content-type": "application/octet-stream", # Generic fallback type
                "duration": None,
                "content_hash": None,
            }
        else:
            file_info = get_file_info(episode["asset_url"])

        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "pubDate").text = convert_iso_to_rfc2822(
            pub_date_str
        )
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

        # Apply global itunes:explicit setting to each episode
        itunes_explicit = ET.SubElement(item, "itunes:explicit")
        itunes_explicit.text = global_explicit

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
                    print(f"  Skipping invalid transcript entry for episode {episode['title']}: {transcript_info}")

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
        action="store_true", # Makes it a boolean flag
        help="Skip HTTP HEAD and ffprobe checks for asset URLs (use for testing/fake URLs)"
    )

    # Parse arguments from the command line
    args = parser.parse_args()

    print(f"Input file: {args.input_file}, Output file: {args.output_file}")
    if args.skip_asset_verification:
        print("Skipping asset verification.")

    config = read_podcast_config(args.input_file)
    generate_rss(config, args.output_file, skip_asset_verification=args.skip_asset_verification)


if __name__ == "__main__":
    main()
