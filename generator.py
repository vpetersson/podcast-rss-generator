import csv
import yaml
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import format_datetime

def iso_to_rfc2822(iso_date):
    """Convert ISO format date to RFC 2822 format."""
    date_obj = datetime.fromisoformat(iso_date)
    return format_datetime(date_obj)

def read_metadata(yaml_file):
    """Read podcast metadata from a YAML file."""
    with open(yaml_file, 'r', encoding='utf-8') as file:
        return yaml.safe_load(file)

def read_video_data(csv_file):
    """Read video data from a CSV file."""
    videos = []
    with open(csv_file, newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            row['pubDate'] = iso_to_rfc2822(row['pubDate'])
            videos.append(row)
    return videos

def generate_rss(metadata, video_data):
    """Generate RSS feed from metadata and video data."""
    rss = ET.Element("rss", version="2.0", attrib={"xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = metadata['title']
    ET.SubElement(channel, "description").text = metadata['description']
    ET.SubElement(channel, "language").text = metadata.get('language', 'en-us')
    ET.SubElement(channel, "generator").text = "Python RSS Generator Script"
    ET.SubElement(channel, "itunes:author").text = metadata['author']
    ET.SubElement(channel, "itunes:explicit").text = metadata.get('itunes_explicit', 'no')

    if 'image' in metadata:
        image = ET.SubElement(channel, "image")
        ET.SubElement(image, "url").text = metadata['image']
        ET.SubElement(image, "title").text = metadata['title']

    if 'itunes_category' in metadata:
        ET.SubElement(channel, "itunes:category", attrib={"text": metadata['itunes_category']})

    for video in video_data:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = video["title"]
        ET.SubElement(item, "link").text = video["link"]
        ET.SubElement(item, "description").text = video["description"]
        ET.SubElement(item, "pubDate").text = video["pubDate"]
        ET.SubElement(item, "itunes:author").text = metadata['author']

    tree = ET.ElementTree(rss)
    tree.write("podcast_feed.xml", encoding="UTF-8", xml_declaration=True)
    print("Podcast feed generated: podcast_feed.xml")

def main():
    metadata = read_metadata('metadata.yaml')
    video_data = read_video_data('videos.csv')
    generate_rss(metadata, video_data)

if __name__ == "__main__":
    main()

