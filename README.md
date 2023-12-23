# Python RSS Generator

## Description
This Python RSS Feed Generator is designed to generate an RSS feed for video podcasts, reading metadata from a YAML file and video details from a CSV file.

It assumes that you self-host your video episodes somewhere (e.g. S3/GCS) as well as the output of this script. You can then point YouTube/Spotify/Apple Podcast to this path.


## Features

- Generates RSS feed for video podcasts
- Reads podcast metadata from a YAML file
- Extracts video details from a CSV file
- Converts ISO format dates to RFC 2822 format
- Automated unit tests and linting with GitHub Actions

## Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package installer)

### Setup

1. **Clone the Repository**

```bash
$ git clone https://github.com/vpetersson/podcast-rss-generator.git
$ cd podcast-rss-generator
```

2. **Install Dependencies**

```bash
$ pip install -r requirements.txt
```

*Note: Ensure your `requirements.txt` file includes all necessary packages like `pyyaml` and `flake8`.*

## Usage

1. **Prepare Your Data Files**

- Copy `metadata.yaml.example` to `metadata.yaml` and fill out your podcast metadata.
- Copy `videos.csv.example` to `videos.csv` file and popuylate it with your podcast episodes.

2. **Generate the RSS Feed**

```bash
$ python generator.py
```

This command will generate an RSS feed in XML format.

3. **Running Tests**

To run unit tests, use:

```bash
python -m unittest discover tests
```

## Contributing

Contributions to this project are welcome! Please follow these steps:
1. Fork the repository.
2. Create a new branch for your feature.
3. Commit your changes.
4. Push to the branch.
5. Submit a pull request.

## License
[MIT License](LICENSE)
