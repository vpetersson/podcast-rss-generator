# Podcast RSS Generator

[![Tests](https://github.com/vpetersson/podcast-rss-generator/actions/workflows/python-tests.yml/badge.svg)](https://github.com/vpetersson/podcast-rss-generator/actions/workflows/python-tests.yml)

Generates an RSS feed for an audio or video podcast from a YAML file.

It assumes you self-host your episodes somewhere (S3/GCS/R2) along with the
generated feed. You then point YouTube, Spotify and Apple Podcasts at that URL.

Written for [Nerding Out with Viktor](https://vpetersson.com/podcast/), because
Apple's [Podcast Connect](https://podcastsconnect.apple.com) requires you to
self-host video in order to publish. There is also
[an article](https://vpetersson.com/2024/06/27/video-to-audio-podcast.html) on
using this to turn a video podcast into audio automatically.

## What it does

- Reads podcast metadata and episodes from YAML
- Converts ISO 8601 dates to RFC 2822
- Probes each asset for duration, content type and length via HTTP HEAD and
  `ffprobe`
- Follows [The Podcast RSS Standard](https://github.com/Podcast-Standards-Project/PSP-1-Podcast-RSS-Specification),
  including `podcast:guid`, `podcast:locked` and `podcast:transcript`
- Validates the config and reports every problem at once, rather than failing
  on the first

## Known issues

Neither is a bug in this tool:

- Video uploaded to YouTube [via RSS](https://support.google.com/youtube/answer/13525207?hl=en#zippy=%2Ccan-i-deliver-an-rss-feed-if-i-already-have-a-podcast-on-youtube)
  arrives as audio only.
- Spotify does not process video via RSS. Episodes appear in Podcaster but are
  not published.

Upload manually to those two platforms.

## Installation

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). `ffmpeg` is needed
for duration probing.

This is a regular Python package, so the quickest way to get the
`podcast-rss-generator` command without cloning anything is:

```bash
uv tool install git+https://github.com/vpetersson/podcast-rss-generator
# or: pipx install git+https://github.com/vpetersson/podcast-rss-generator
```

To work on it instead:

```bash
git clone https://github.com/vpetersson/podcast-rss-generator.git
cd podcast-rss-generator
uv sync
```

`uv` reads `.python-version` and installs the right interpreter itself, so
there is no virtualenv to create. `uv sync` installs the package in editable
mode plus the dev tools (`pytest`, `ruff`, `mypy`, `yamllint`); use
`uv sync --no-dev` for runtime only.

If `ffmpeg` is missing, the generator says so and omits episode duration rather
than failing. It is not needed at all for `--dry-run` or
`--skip-asset-verification`.

## Usage

```
usage: podcast-rss-generator [-h] [--version] [--input-file INPUT_FILE]
                             [--output-file OUTPUT_FILE]
                             [--skip-asset-verification] [--dry-run]

options:
  -h, --help                 show this help message and exit
  --version                  show the version and exit
  --input-file INPUT_FILE    Input YAML file (default: podcast_config.yaml)
  --output-file OUTPUT_FILE  Output XML file (default: podcast_feed.xml)
  --skip-asset-verification  Skip HTTP HEAD and ffprobe checks for asset URLs
  --dry-run                  Validate the configuration only
```

`python -m podcast_rss_generator` does the same thing, for anyone who prefers
it or whose `PATH` does not include the tool's `bin` directory.

Copy `podcast_config.example.yaml` to `podcast_config.yaml` and fill in your
metadata and episodes, then:

```bash
podcast-rss-generator --dry-run   # validate
podcast-rss-generator             # generate podcast_feed.xml
```

From a clone, prefix those with `uv run` (`uv run podcast-rss-generator
--dry-run`) to use the project's own environment.

`--dry-run` checks YAML syntax, required fields, URL formats, email addresses,
ISO dates and episode structure. It exits 0 when the config is valid and 1 when
it is not:

```
✗ Config validation failed:
  - Invalid email format: 'invalid-email'
  - Episode 1: Invalid publication_date format 'invalid-date'
  - Episode 1: Invalid asset_url format 'not-a-url'
```

Copy the resulting `podcast_feed.xml` to your bucket with `s3cmd`, `aws` or
`mc`. You can check the result with [Podbase](https://podba.se/validate/).

## Configuration

### `metadata`

| Key                      | Description                                                                                                             | Notes                                                                                                                                                          |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `title`                  | Podcast title.                                                                                                          | Required.                                                                                                                                                      |
| `description`            | Podcast description.                                                                                                    | Required. Markdown supported.                                                                                                                                  |
| `link`                   | Main website for the podcast.                                                                                           | Required. Default link for episodes.                                                                                                                           |
| `rss_feed_url`           | Public URL where the generated feed will be hosted.                                                                     | Required.                                                                                                                                                      |
| `language`               | Language code, e.g. `en-us`.                                                                                            | Required.                                                                                                                                                      |
| `email`                  | Contact email for the owner.                                                                                            | Required. Legacy key: `itunes_email`. Used for `podcast:locked`.                                                                                               |
| `author`                 | Author name.                                                                                                            | Required. Legacy key: `itunes_author`.                                                                                                                         |
| `image`                  | Cover art URL (JPEG or PNG, 1400x1400 to 3000x3000).                                                                    | Optional, but every platform wants it. Default image for episodes.                                                                                             |
| `category`               | Primary iTunes category.                                                                                                | Optional. Legacy key: `itunes_category`.                                                                                                                       |
| `explicit`               | Whether the podcast contains explicit content.                                                                          | Optional, `true`/`false`. Default `false`. Legacy key: `itunes_explicit`. Overridable per episode.                                                             |
| `copyright`              | Copyright notice.                                                                                                       | Optional.                                                                                                                                                      |
| `podcast_locked`         | Stops platforms importing the feed without confirming ownership via `email`.                                            | Optional, `yes`/`no`. Default `no`.                                                                                                                            |
| `podcast_guid`           | Permanent identifier for the show, UUID recommended.                                                                    | Optional, but set it. If omitted, a UUIDv5 is derived from `rss_feed_url`, which means changing that URL changes the GUID.                                     |
| `use_asset_hash_as_guid` | Derive each episode's `guid` from the asset's `x-amz-checksum-sha256`, `x-goog-hash` MD5, or `ETag` instead of its URL. | Optional, `true`/`false`. Default `false`. **Re-uploading an asset changes its hash and therefore its GUID, which makes subscribers re-download the episode.** |

### `episodes`

| Key                | Description                                                                    | Notes                                                    |
| ------------------ | ------------------------------------------------------------------------------ | -------------------------------------------------------- |
| `title`            | Episode title.                                                                 | Required.                                                |
| `description`      | Episode description.                                                           | Required. Markdown supported.                            |
| `publication_date` | ISO 8601, e.g. `2023-01-15T10:00:00Z`.                                         | Required. Episodes dated in the future are skipped.      |
| `asset_url`        | Direct URL to the audio or video file.                                         | Required.                                                |
| `link`             | Webpage for this episode.                                                      | Optional. Defaults to `metadata.link`.                   |
| `image`            | Artwork for this episode.                                                      | Optional. Defaults to `metadata.image`.                  |
| `episode`          | Episode number.                                                                | Optional. Positive integer.                              |
| `season`           | Season number.                                                                 | Optional. Positive integer.                              |
| `episode_type`     | `full`, `trailer` or `bonus`.                                                  | Optional. Lowercase; anything else is rejected.          |
| `explicit`         | Overrides the podcast-level setting for this episode.                          | Optional, `true`/`false`. Legacy key: `itunes_explicit`. |
| `transcripts`      | List of `{url, type, language?, rel?}`. `url` and `type` are required on each. | Optional. See the example config.                        |

Episode duration is not configured. It is read from the asset with `ffprobe`.

## GitHub Actions

This repository ships as a Docker action.

```yaml
name: Generate Podcast RSS Feed

on: [push, pull_request]

env:
  R2_BUCKET: 'foobar'

jobs:
  generate-rss:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run Podcast RSS Generator
        uses: vpetersson/podcast-rss-generator@master
        with:
          input_file: 'podcast_config.yaml'
          output_file: 'podcast_feed.xml'

      - uses: actions/upload-artifact@v4
        with:
          name: podcast_feed.xml
          path: podcast_feed.xml

  deploy:
    runs-on: ubuntu-latest
    needs: generate-rss
    if: github.ref == 'refs/heads/master'
    steps:
      - uses: actions/download-artifact@v4
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

Pin to a release tag rather than `master` if you want reproducible runs.

### Action inputs

| Input                     | Description                      | Default               |
| ------------------------- | -------------------------------- | --------------------- |
| `input_file`              | Path to the YAML config.         | `podcast_config.yaml` |
| `output_file`             | Path for the generated feed.     | `podcast_feed.xml`    |
| `skip_asset_verification` | Skip HEAD and `ffprobe` checks.  | `false`               |
| `dry_run`                 | Validate only, generate nothing. | `false`               |

## Docker

```bash
docker build -t podcast-rss-generator:latest .

docker run --rm -v .:/data podcast-rss-generator:latest \
    --input-file podcast_config.yaml \
    --output-file myfeed.xml
```

`-v` shares the working directory with the container so the config can be read
and the feed written back out; `--rm` cleans up the container afterwards. The
image sets its working directory to `/data`, so paths inside the container are
relative to whatever you mounted there.

The image installs the built wheel into a virtualenv and its entry point is
the `podcast-rss-generator` console script — it does not carry a source tree,
so what runs in the container is the same distribution `uv tool install` would
give you.

## Optimising video

File size matters for video podcasts. Export h264 from your editor for YouTube
and Spotify, then re-encode to h265 for everything else. On macOS:

```bash
ffmpeg -i input.mp4 \
    -tag:v hvc1 \
    -c:v hevc_videotoolbox \
    -crf 28 \
    -preset slowest \
    -c:a aac \
    -b:a 128k \
    -movflags faststart \
    output.mp4
```

## Development

The checks CI runs:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

Tests use [pytest](https://docs.pytest.org/). A few things worth knowing before
adding one:

- `uv run pytest --cov` prints a coverage report; CI fails below 85%.
- `uv run pytest -k transcript` runs a subset, `-x` stops at the first failure.
- Fixtures live in `tests/conftest.py`, helpers in `tests/helpers.py`. The
  `feed` fixture yields the example feed twice — once built from the current
  metadata keys and once from the legacy `itunes_*` ones — so a structural
  assertion covers both spellings without being written twice.
- Nothing in the suite touches the network or needs `ffmpeg`; HTTP HEAD and
  `ffprobe` are stubbed. Generated feeds are written to pytest's `tmp_path`,
  never into the working tree.

The package and the test suite are both type-checked under mypy's `strict`
mode, and the package ships a `py.typed` marker so anything importing it gets
the annotations too.

### Project layout

```
src/podcast_rss_generator/
    __init__.py    # __version__ and the public API
    cli.py         # argument parsing, the podcast-rss-generator entry point
    config.py      # reading the YAML file
    validation.py  # --dry-run's checks
    assets.py      # HTTP HEAD and ffprobe probing of episode assets
    feed.py        # building the RSS document
tests/             # pytest suite; helpers.py and conftest.py are shared
```

The `src/` layout is deliberate: nothing is importable from the repository
root, so the tests can only see the package that was actually installed. With
a flat layout, a module accidentally left out of the wheel still passes CI and
fails on the user's machine. `tests/test_packaging.py` covers the rest of the
contract — the console script, the metadata, and `python -m`.

Dependencies are pinned in `uv.lock`. After changing `pyproject.toml`, run
`uv lock` and commit the result — CI installs with `--frozen` and fails if the
lockfile is out of step.

## Versioning

This project uses [CalVer](https://calver.org/), `YYYY.M.PATCH`:

- `YYYY` — four-digit year
- `M` — month, not zero-padded, so the string matches what PEP 440 normalises
  a Python package version to
- `PATCH` — starts at `0` and increments for each further release in the same
  month

There is nothing to infer from a version bump beyond when it shipped; read the
release notes for what changed. Earlier releases used SemVer (`v0.2.1` and
below), so any version from `2026.9.0` onwards is newer than any `0.x` tag.

`podcast_rss_generator.__version__` is the single source of truth.
`pyproject.toml` declares the version dynamic and hatchling reads it from
there, so `podcast-rss-generator --version` and the package metadata cannot
disagree.

To cut a release:

```bash
# 1. bump __version__ in src/podcast_rss_generator/__init__.py
uv lock              # refreshes the version recorded in uv.lock
uv run pytest
git commit -am "Release 2026.9.0"
git tag v2026.9.0
git push --follow-tags
```

## Contributing

Fork, branch, commit, push, open a pull request.

## License

[MIT License](LICENSE)
