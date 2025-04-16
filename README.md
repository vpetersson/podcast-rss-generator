# Podcast RSS Generator

[![Python Unit Tests and Linting](https://github.com/vpetersson/podcast-rss-generator/actions/workflows/python-tests.yml/badge.svg)](https://github.com/vpetersson/podcast-rss-generator/actions/workflows/python-tests.yml)

## Description

This an RSS Feed Generator is designed to generate an RSS feed for audio/video podcasts, reading metadata and episode data from a YAML file.

It assumes that you self-host your video episodes somewhere (e.g. S3/GCS/R2) as well as the output of this script. You can then point YouTube/Spotify/Apple Podcast to this path.

This tool was written for my podcast [Nerding Out with Viktor](https://vpetersson.com/podcast/) to solve for the fact that Apple's [Podcast Connect](https://podcastsconnect.apple.com) require you to self-host videos in order to publish.

I also wrote an article on how you can use this tool to automatically turn a video podcast into audio in [this article](https://vpetersson.com/2024/06/27/video-to-audio-podcast.html).

## Features

- Generates RSS feed for audio/video podcasts
- Reads podcast metadata and episode data from a YAML file
- Converts ISO format dates to RFC 2822 format
- Attempts to follow [The Podcast RSS Standard](https://github.com/Podcast-Standards-Project/PSP-1-Podcast-RSS-Specification)

## Known Issues

- Videos uploaded to YouTube [via RSS](https://support.google.com/youtube/answer/13525207?hl=en#zippy=%2Ccan-i-deliver-an-rss-feed-if-i-already-have-a-podcast-on-youtube) will be uploaded as audio.
- Spotify can't handle videos via RSS yet. You will be able to see the episodes in Podcaster, but they will not be processed and sent to Spotify properly. This is apparently a known issue that they are working on resolving.

The workaround for the above issues is to manually upload the episodes.

## Installation

### Prerequisites

- Python 3.8 or higher
- pip (Python package installer)
- ffmpeg

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

**Optional:** Install `yamllint`, `xq` and `flake8`.

## Usage

```bash
$ python rss_generator.py --help
usage: rss_generator.py [-h] [--input-file INPUT_FILE] [--output-file OUTPUT_FILE] [--skip-asset-verification]

Process some parameters.

options:
  -h, --help            show this help message and exit
  --input-file INPUT_FILE
                        Input YAML file
  --output-file OUTPUT_FILE
                        Output XML file
  --skip-asset-verification
                        Skip HTTP HEAD and ffprobe checks for asset URLs (use for testing/fake URLs)
```

1. **Prepare Your Data Files**

Copy `podcast_config.example.yaml` to `podcast_config.yaml` and fill out your podcast metadata and eepisodes.

The `podcast_config.yaml` file contains two main sections: `metadata` and `episodes`.

### Metadata Section

This section contains general information about your podcast:

- `title`: The title of your podcast.
- `description`: A description of your podcast. Markdown is supported.
- `link`: The URL of the main website for your podcast. This is also the default link for episodes if an episode-specific link is not provided.
- `rss_feed_url`: The public URL where your generated `podcast_feed.xml` will be hosted. (Required)
- `language`: The language of the podcast (e.g., `en-us`). Default: `en-us`.
- `email`: The contact email for the podcast owner (Required). The old key `itunes_email` is supported for backward compatibility.
- `author`: The author name(s) (Required). The old key `itunes_author` is supported for backward compatibility.
- `category`: The primary category for iTunes. The old key `itunes_category` is supported for backward compatibility.
- `image`: The URL for the main podcast cover art (JPEG or PNG, 1400x1400 to 3000x3000 pixels). This is also the default image for episodes if an episode-specific image is not provided.
- `explicit`: Set to `true` or `false` to indicate if the podcast contains explicit content. Default: `false`. The old key `itunes_explicit` is supported for backward compatibility.
- `use_asset_hash_as_guid` (optional): Set to `true` to use a content hash or ETag from the asset file's headers as the episode's `<guid>`. Defaults to `false`, which uses the `asset_url` as the GUID. The script prioritizes headers in this order: `x-amz-checksum-sha256` (as `sha256:<hash>`), `x-goog-hash` (extracting `md5:<base64_hash>`), then the full `ETag` value (as `etag:<value>`, including multipart suffixes). If none of these are found, it falls back to `asset_url`. **Warning:** Setting this to `true` means any change to the asset file (re-encoding, editing, or re-uploading even with identical content but different parameters) will likely change the hash/ETag and thus the GUID, causing subscribers to re-download the episode. This deviates from the standard expectation of GUID permanence.
- `copyright` (optional): A string containing the copyright notice for the podcast.

### Episodes Section

This section is a list of your podcast episodes. Each episode is an object with the following fields:

- `title`: The title of the episode.
- `description`: A description of the episode. Markdown is supported.
- `publication_date`: The date and time the episode was published, in ISO 8601 format (e.g., `2023-01-15T10:00:00Z`). Episodes with future dates will not be included in the feed.
- `asset_url`: The direct URL to the audio or video file for the episode.
- `link` (optional): The URL for a webpage specific to this episode. If omitted, the global `link` from the `metadata` section is used.
- `image` (optional): The URL for artwork specific to this episode (same format requirements as the main podcast image). If omitted, the global `image` from the `metadata` section is used.
- `episode` (optional): The episode number (integer).
- `season` (optional): The season number (integer).
- `episode_type` (optional): Can be `full` (default), `trailer`, or `bonus`.
- `transcripts` (optional): A list of transcript files associated with the episode. Each item in the list is an object with:
  - `url`: (Required) The direct URL to the transcript file.
  - `type`: (Required) The MIME type of the transcript file (e.g., `application/x-subrip`, `text/vtt`, `application/json`, `text/plain`, `text/html`).
  - `language` (optional): The language code (e.g., `en`, `es`) for the transcript.
  - `rel` (optional): The relationship of the transcript file (e.g., `captions`).

2. **Generate the RSS Feed**

Make sure your YAML is valid:

```bash
$ yamllint podcast_config.yaml
```

Generate your `podcast_feed.xml` file:

```bash
$ python rss_generator.py
```

Now copy your `podcast_feed.xml` to S3/GCS/R2 using a tool like `s3cmd`, `aws` or `mc` (from Minio).

You can verify your RSS feed using a tool like [Podbase](https://podba.se/validate/).

## **Optional:** Optimize video

If you're dealing with video podcasts, the file size matters for obvious reasons. What I do is to export the video as h624 from my video editor (which I upload to YouTube and Spotify).

I then re-encode the h264 video to h265 for other platforms using `ffmpeg` with the following command (on macOS):

```bash
$ ffmpeg -i input.mp4 \
    -tag:v hvc1 \
    -c:v hevc_videotoolbox \
    -crf 28 \
    -preset slowest \
    -c:a aac \
    -b:a 128k \
    -movflags faststart \
    output.mp4
```

## Usage with GitHub Actions

To incorporate this action into your workflow, follow these steps:

1. **Create a Workflow File**:
   - In your repository, create a new file under `.github/workflows`, for example, `rss_workflow.yml`.

2. **Set Up the Workflow**:
   - Use the following configuration as a starting point:

```yaml
name: Generate Podcast RSS Feed

on: [push, pull_request]

env:
  R2_BUCKET: 'foobar'
jobs:
  generate-rss:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v2

      - name: Install yamllint
        run: |
          sudo apt-get update
          sudo apt-get install yamllint

      - name: Lint YAML file
        run: yamllint podcast_config.yaml

      - name: Run Podcast RSS Generator
        uses: vpetersson/podcast-rss-generator@master
        with:
          input_file: 'podcast_config.yaml'
          output_file: 'podcast_feed.xml'

      - name: Validate output with xq
        run: |
          wget -q https://github.com/sibprogrammer/xq/releases/download/v1.2.3/xq_1.2.3_linux_amd64.tar.gz
          tar xfz xq_1.2.3_linux_amd64.tar.gz
          cat podcast_feed.xml | ./xq

      - uses: actions/upload-artifact@v2
        with:
          name: podcast_feed.xml
          path: podcast_feed.xml

  deploy:
    runs-on: ubuntu-latest
    needs: generate-rss
    if: github.ref == 'refs/heads/master'
    steps:
      - uses: actions/download-artifact@v2
        with:
          name: podcast_feed.xml

      - name: Install mc
        run: |
          wget -q https://dl.min.io/client/mc/release/linux-amd64/mc
          chmod +x mc

      - name: Set up mc
        env:
          R2_ENDPOINT: ${{ secrets.R2_ENDPOINT }}
          R2_KEY_ID: ${{ secrets.R2_KEY_ID }}
          R2_KEY_SECRET: ${{ secrets.R2_KEY_SECRET }}
        run: ./mc alias set r2-storage ${R2_ENDPOINT} ${R2_KEY_ID} ${R2_KEY_SECRET}

      - name: Copy file
        run: ./mc cp podcast_feed.xml r2-storage/${R2_BUCKET}/
```

3. **Customize Your Workflow**:
   - Adjust paths to the YAML configuration and the output XML files as per your repository structure.
   - Ensure the `uses` field points to `vpetersson/podcast-rss-generator@master` (or specify a specific release tag/version instead of `master`).

4. **Commit and Push Your Workflow**:
   - Once you commit this workflow file to your repository, the action will be triggered based on the defined events (e.g., on push or pull request).

### Inputs

- `input_file`: Path to the input YAML file. Default: `podcast_config.yaml`.
- `output_file`: Path for the generated RSS feed XML file. Default: `podcast_feed.xml`.

## Running Tests

To run unit tests, use:

```bash
$ python -m unittest discover tests
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
