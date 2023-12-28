import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import format_datetime

import requests
import yaml
import markdown

def read_podcast_config(yaml_file_path):
    with open(yaml_file_path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def convert_iso_to_rfc2822(iso_date):
    date_obj = datetime.fromisoformat(iso_date)
    return format_datetime(date_obj)


def get_file_info(url):
    response = requests.head(url, allow_redirects=True)
    return {
        "content-length": response.headers.get("content-length"),
        "content-type": response.headers.get("content-type"),
    }

def format_description(description):
    # Convert Markdown description to HTML for the channel
    html_description = markdown.markdown(description)
    wrapped_description = f"<![CDATA[{html_description}]]>"

    # Ensure byte limit for the channel description
    byte_limit = 4000
    if len(wrapped_description.encode('utf-8')) > byte_limit:
        # Truncate the description if it exceeds the limit
        # Note: Truncation logic might need to be more sophisticated to handle HTML correctly
        wrapped_description = wrapped_description[:byte_limit]

    return wrapped_description

def generate_rss(config, output_file_path):
    ET.register_namespace("itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    ET.register_namespace("atom", "http://www.w3.org/2005/Atom")

    # Global itunes:explicit setting
    global_explicit = (
        "yes" if config["metadata"].get("itunes_explicit", False) else "no"
    )

    rss = ET.Element(
        "rss",
        version="2.0",
        attrib={
            "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
            "xmlns:atom": "http://www.w3.org/2005/Atom",
        },
    )
    # Metadata
    channel = ET.SubElement(rss, "channel")
    metadata = config["metadata"]
    ET.SubElement(channel, "title").text = metadata["title"]
    ET.SubElement(channel, "description").text = format_description(metadata["description"])
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
        href=output_file_path,
        rel="self",
        type="application/rss+xml",
    )

    # Adds explicit tag
    itunes_explicit = ET.SubElement(channel, "itunes:explicit")
    itunes_explicit.text = global_explicit

    # Add itunes:owner and itunes:email tags
    itunes_owner = ET.SubElement(channel, "itunes:owner")
    ET.SubElement(itunes_owner, "itunes:email").text = metadata["itunes_email"]

    # Add itunes:author tag
    itunes_author = ET.SubElement(channel, "itunes:author")
    itunes_author.text = metadata["itunes_author"]

    # Duplicate descrion to itunes summary
    itunes_summary = ET.SubElement(channel, "itunes:summary")
    itunes_summary.text = metadata["description"]

    # Add itunes:category tag
    if "itunes_category" in metadata:
        ET.SubElement(channel, "itunes:category", text=metadata["itunes_category"])

    if "itunes_image" in metadata:
        itunes_image = ET.SubElement(channel, "itunes:image")
        itunes_image.set("href", metadata["itunes_image"])

    # Episodes
    for episode in config["episodes"]:
        print(f"Processing episode {episode['title']}...")

        # Don't pre-publish episodes
        if not datetime.fromisoformat(episode["publication_date"]) < datetime.utcnow():
            print(f"Skipping episode {episode['title']} as it's not scheduled to be released until {episode['publication_date']}.")
            continue

        file_info = get_file_info(episode["link"])
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "pubDate").text = convert_iso_to_rfc2822(
            episode["publication_date"]
        )
        ET.SubElement(item, "title").text = episode["title"]
        ET.SubElement(item, "description").text = format_description(episode["description"])
        ET.SubElement(item, "guid").text = episode["link"]
        ET.SubElement(
            item,
            "enclosure",
            url=episode["link"],
            type=file_info["content-type"],
            length=str(file_info["content-length"]),
        )

        # Apply global itunes:explicit setting to each episode
        itunes_explicit = ET.SubElement(item, "itunes:explicit")
        itunes_explicit.text = global_explicit

        # New iTunes-specific tags
        if "episode" in episode:
            itunes_episode = ET.SubElement(item, "itunes:episode")
            itunes_episode.text = str(episode["episode"])

        if "season" in episode:
            itunes_season = ET.SubElement(item, "itunes:season")
            itunes_season.text = str(episode["season"])

        if "episode_type" in episode:
            itunes_episode_type = ET.SubElement(item, "itunes:episodeType")
            itunes_episode_type.text = episode["episode_type"]

    tree = ET.ElementTree(rss)
    tree.write(output_file_path, encoding="UTF-8", xml_declaration=True)


def main():
    config = read_podcast_config("podcast_config.yaml")
    generate_rss(config, "podcast_feed.xml")


if __name__ == "__main__":
    main()
