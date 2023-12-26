import xml.etree.ElementTree as ET
import yaml
import csv
import requests
from datetime import datetime
from email.utils import format_datetime


def read_podcast_config(yaml_file_path):
    with open(yaml_file_path, 'r', encoding='utf-8') as file:
        return yaml.safe_load(file)


def convert_iso_to_rfc2822(iso_date):
    date_obj = datetime.fromisoformat(iso_date)
    return format_datetime(date_obj)


def get_file_size(url):
    response = requests.head(url, allow_redirects=True)
    return response.headers.get('content-length', 0)


def generate_rss(config, output_file_path):
    ET.register_namespace('itunes', "http://www.itunes.com/dtds/podcast-1.0.dtd")
    ET.register_namespace('atom', "http://www.w3.org/2005/Atom")

    rss = ET.Element("rss", version="2.0", attrib={"xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
                                                   "xmlns:atom": "http://www.w3.org/2005/Atom"})
    # Metadata
    channel = ET.SubElement(rss, "channel")
    metadata = config['metadata']
    ET.SubElement(channel, "title").text = metadata['title']
    ET.SubElement(channel, "description").text = metadata['description']
    ET.SubElement(channel, "language").text = metadata.get('language', 'en-us')
    ET.SubElement(channel, "link").text = metadata['link']
    ET.SubElement(channel, "generator").text = "Podcast RSS Generator (https://github.com/vpetersson/podcast-rss-generator)"
    ET.SubElement(channel, "atom:link", href=output_file_path, rel="self", type="application/rss+xml")

    # Adds explicit tag
    itunes_explicit = ET.SubElement(channel, "itunes:explicit")
    itunes_explicit.text = 'yes' if metadata.get('itunes_explicit') else 'no'

    # Add itunes:owner and itunes:email tags
    itunes_owner = ET.SubElement(channel, "itunes:owner")
    ET.SubElement(itunes_owner, "itunes:email").text = metadata['itunes_email']

    # Add itunes:author tag
    itunes_author = ET.SubElement(channel, "itunes:author")
    itunes_author.text = metadata['itunes_author']

    # Duplicate descrion to itunes summary
    itunes_summary = ET.SubElement(channel, "itunes:summary")
    itunes_summary.text = metadata['description']

    # Add itunes:category tag
    if 'itunes_category' in metadata:
        ET.SubElement(channel, "itunes:category", text=metadata['itunes_category'])

    if 'itunes_image' in metadata:
        itunes_image = ET.SubElement(channel, "itunes:image")
        itunes_image.set('href', metadata['itunes_image'])

    # Episodes
    for episode in config['episodes']:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = episode["title"]
        ET.SubElement(item, "description").text = episode["description"]
        ET.SubElement(item, "pubDate").text = episode["pubDate"]

        # The 'enclosure' element has been intentionally removed as
        # it requires more work to support both video and audio.
        # ET.SubElement(item, "enclosure", url=episode["link"], type="audio/mpeg", length=str(video["file_size"]))

    tree = ET.ElementTree(rss)
    tree.write(output_file_path, encoding="UTF-8", xml_declaration=True)


def main():
    config = read_podcast_config('podcast_config.yaml')
    generate_rss(config, 'podcast_feed.xml')


if __name__ == "__main__":
    main()
