# Podcast RSS Generator

[![Python Unit Tests and Linting](https://github.com/vpetersson/podcast-rss-generator/actions/workflows/python-tests.yml/badge.svg)](https://github.com/vpetersson/podcast-rss-generator/actions/workflows/python-tests.yml)

## Description

This an RSS Feed Generator is designed to generate an RSS feed for audio/video podcasts, reading metadata and episode data from a YAML file.

It assumes that you self-host your video episodes somewhere (e.g. S3/GCS/R2) as well as the output of this script. You can then point YouTube/Spotify/Apple Podcast to this path.

This tool was written for my podcast [Nerding Out with Viktor](https://blog.viktorpetersson.com/nerding-out-with-viktor/) to solve for the fact that Apple's [Podcast Connect](https://podcastsconnect.apple.com) require you to self-host videos in order to publish.

## Features

- Generates RSS feed for audio/video podcasts
- Reads podcast metadata and episode data from a YAML file
- Converts ISO format dates to RFC 2822 format
- Attempts to follow [The Podcast RSS Standard](https://github.com/Podcast-Standards-Project/PSP-1-Podcast-RSS-Specification)

## Known Issues

* Videos uploaded to YouTube [via RSS](https://support.google.com/youtube/answer/13525207?hl=en#zippy=%2Ccan-i-deliver-an-rss-feed-if-i-already-have-a-podcast-on-youtube) will be uploaded as audio.
* Spotify can't handle videos via RSS yet. You will be able to see the episodes in Podcaster, but they will not be processed and sent to Spotify properly. This is apparently a known issue that they are working on resolving.

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

1. **Prepare Your Data Files**

Copy `podcast_config.example.yaml` to `podcast_config.yaml` and fill out your podcast metadata and eepisodes.

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

If you're dealing with video podcasts, the file size matters for obvious reasons. Here's what I'm using for re-encoding my videos (on macOS):

```bash
$ ffmpeg -i input.mp4 \
    -tag:v hvc1 \
    -c:v hevc_videotoolbox \
    -crf 26 \
    -preset slowest \
    -c:a aac \
    -b:a 128k \
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
        run: ./mc cp podcast_feed.xml r2-storage/my-bucket/
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
