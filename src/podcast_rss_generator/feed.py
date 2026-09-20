"""Rendering the RSS document itself."""

import re
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import format_datetime
from typing import Any

import markdown

from podcast_rss_generator.assets import FileInfo, get_file_info

# Apple caps <description> at 4000 bytes.
DESCRIPTION_BYTE_LIMIT = 4000

# CDATA sections are assembled as text, so ElementTree escapes the delimiters
# along with everything else. Rather than disabling escaping globally — which
# is what this module used to do, and which let a "<" in any title emit
# malformed XML — the delimiters are swapped for sentinels that survive
# serialization untouched and are restored afterwards. See _restore_cdata.
# Randomised per run so no description can contain a sentinel by accident.
_CDATA_TOKEN = uuid.uuid4().hex
_CDATA_OPEN = f"@@CDATA-OPEN-{_CDATA_TOKEN}@@"
_CDATA_CLOSE = f"@@CDATA-CLOSE-{_CDATA_TOKEN}@@"


def convert_iso_to_rfc2822(iso_date: str) -> str:
    # Replace 'Z' with '+00:00' for Python < 3.11 compatibility
    compatible_iso_date = iso_date.replace("Z", "+00:00")
    date_obj = datetime.fromisoformat(compatible_iso_date)
    return format_datetime(date_obj)


def _truncate_to_bytes(text: str, byte_limit: int) -> str:
    """
    Trim text so its UTF-8 encoding fits within byte_limit, without splitting a
    character in half.

    The previous implementation used the byte budget as a character index,
    which silently overshot for any non-ASCII text: 3,000 accented characters
    produced 6,019 bytes against a 4,000-byte limit.
    """
    encoded = text.encode("utf-8")
    if len(encoded) <= byte_limit:
        return text
    # errors="ignore" drops a trailing partial multi-byte sequence.
    return encoded[:byte_limit].decode("utf-8", errors="ignore")


def format_description(description: str) -> str:
    """
    Convert Markdown to HTML and wrap it in a CDATA section.

    The delimiters use sentinels rather than literal "<![CDATA[" so that
    ElementTree can escape the document normally; _restore_cdata swaps them
    back after serialization.
    """
    # Markdown already emits correctly escaped HTML ("&" -> "&amp;"). The CDATA
    # section carries HTML for the client to parse, so that escaping has to be
    # preserved. This used to call html.unescape() here and then re-escape at
    # serialization time via a monkeypatch: the two cancelled out, but the
    # monkeypatch also disabled "<" escaping for the entire document.
    rendered_html = markdown.markdown(description)

    # Reserve room for the delimiters, then trim on a character boundary.
    overhead = len(b"<![CDATA[]]>")
    content = _truncate_to_bytes(rendered_html, DESCRIPTION_BYTE_LIMIT - overhead)

    if content != rendered_html:
        # Avoid leaving a half-written HTML tag at the cut point.
        last_open = content.rfind("<")
        if last_open != -1 and ">" not in content[last_open:]:
            content = content[:last_open]

    return f"{_CDATA_OPEN}{content}{_CDATA_CLOSE}"


def _restore_cdata(xml_text: str) -> str:
    """
    Turn the sentinels back into real CDATA delimiters and undo the escaping
    ElementTree applied to the section contents.

    This replaces a module-level monkeypatch of ET._escape_cdata, which
    disabled "<" and ">" escaping for the whole document rather than just for
    CDATA. Any episode title containing "<" was therefore written verbatim and
    produced malformed XML.
    """

    def _unescape(match: re.Match[str]) -> str:
        inner = match.group(1)
        inner = (
            inner.replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&#10;", "\n")
            .replace("&#13;", "\r")
            .replace("&#09;", "\t")
            # &amp; last, so "&amp;lt;" does not become "<".
            .replace("&amp;", "&")
        )
        return f"<![CDATA[{inner}]]>"

    return re.sub(
        re.escape(_CDATA_OPEN) + "(.*?)" + re.escape(_CDATA_CLOSE),
        _unescape,
        xml_text,
        flags=re.DOTALL,
    )


def generate_rss(
    config: Any, output_file_path: str, skip_asset_verification: bool = False
) -> None:
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
    # Honour both the new and legacy keys. This previously read only
    # itunes_explicit, so a config using the documented `explicit:` key had
    # every episode fall back to "no".
    _meta = config["metadata"]
    _global_explicit_val = _meta.get("explicit", _meta.get("itunes_explicit", False))
    global_explicit = "yes" if _global_explicit_val else "no"

    # --- Metadata Section --- (Add copyright)
    channel = ET.SubElement(rss, "channel")
    metadata = config["metadata"]

    # Helper function to get metadata with backward compatibility
    def get_meta(
        key: str,
        old_key: str | None = None,
        required: bool = False,
        default: Any = None,
    ) -> Any:
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
            pub_date = pub_date.replace(tzinfo=UTC)

        # Now compare the timezone-aware publication date with the current UTC time
        if not pub_date < datetime.now(UTC):
            print(
                f"Skipping episode {episode['title']} as it's not scheduled to be released until {episode['publication_date']}."
            )
            continue

        if skip_asset_verification:
            print(f"  Skipping asset verification for {episode['asset_url']}")
            # Provide default/placeholder values
            file_info: FileInfo = {
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
            # `or` rather than .get(..., default): get_file_info always sets
            # these keys, so a missing header left them as None and the
            # enclosure was written with length="None" and type=None.
            type=file_info.get("content-type") or "application/octet-stream",
            length=str(file_info.get("content-length") or "0"),
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

    # Serialize to text so the CDATA sentinels can be restored, then write.
    # Everything outside those sections keeps ElementTree's normal escaping.
    xml_body = ET.tostring(rss, encoding="unicode")
    # Single quotes match what ElementTree.write() emitted, so switching to a
    # manual write does not churn every byte of an existing feed.
    xml_text = "<?xml version='1.0' encoding='UTF-8'?>\n" + _restore_cdata(xml_body)
    with open(output_file_path, "w", encoding="utf-8") as handle:
        handle.write(xml_text)
