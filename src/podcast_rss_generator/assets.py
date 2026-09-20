"""Probing a published episode asset over HTTP and with ffprobe."""

import json
import re
import subprocess
import time
from typing import Any, TypedDict

import requests

# How long to wait on the HEAD request for an asset. Without this, a hung
# server stalls the whole feed build indefinitely.
HTTP_TIMEOUT_SECONDS = 30

# ffprobe has to download enough of a remote file to read its stream headers,
# so this is more generous than the HEAD timeout, but still bounded.
FFPROBE_TIMEOUT_SECONDS = 120


# Declared functionally because two of the keys are the hyphenated header
# names this module has always used; renaming them would be a breaking change
# for anyone importing get_file_info. Every value can legitimately be None: a
# server need not send Content-Length or Content-Type, and ffprobe may fail.
FileInfo = TypedDict(
    "FileInfo",
    {
        "content-length": str | None,
        "content-type": str | None,
        "duration": int | None,
        "content_hash": str | None,
        "tags": dict[str, str],
    },
)


def _make_http_request(
    url: str, max_retries: int = 5, delay: int = 2
) -> requests.Response:
    """
    HEAD the URL, retrying with exponential backoff.

    Written out rather than pulled from the `retry` package: that package was
    last released in 2016 and brings in `decorator` and `py`, the latter being
    pytest's retired legacy library. Three dependencies for one decorator, on
    a module that already hand-rolls the same loop for ffprobe.
    """
    for attempt in range(1, max_retries + 1):
        try:
            return requests.head(
                url, allow_redirects=True, timeout=HTTP_TIMEOUT_SECONDS
            )
        except requests.RequestException:
            if attempt >= max_retries:
                raise
            print(
                f"HTTP request failed (attempt {attempt}/{max_retries}), "
                f"retrying in {delay} seconds..."
            )
            time.sleep(delay)
            delay *= 2
    # Unreachable: the final attempt either returns or re-raises.
    raise AssertionError("unreachable")


def _run_ffprobe_with_retry(url: str, max_retries: int = 5, delay: int = 2) -> str:
    """
    Run ffprobe with manual retry logic to handle ErrorReturnCode exceptions.

    Returns the probe output, or an empty string if every attempt failed.

    Uses subprocess from the standard library. This previously went through
    the `sh` package, which resolves the binary at import time — so the module
    would not even load without ffmpeg installed, including for --dry-run,
    which never probes anything.
    """
    command = [
        "ffprobe",
        "-hide_banner",
        "-v",
        "quiet",
        "-show_streams",
        # Container-level metadata, which is where ID3 tags surface. ffprobe
        # reads it from the same header fetch the stream info already needs,
        # so asking for it costs no extra network: probing a 28 MB remote MP3
        # transfers ~48 KB either way.
        "-show_format",
        "-print_format",
        # JSON rather than flat: tag values are arbitrary text, and flat
        # output escapes them ('format.tags.title="He said \\"hi\\" = ok"').
        # Splitting that on "=" mangles any title containing one.
        "json",
        url,
    ]

    for attempt in range(1, max_retries + 1):
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
                timeout=FFPROBE_TIMEOUT_SECONDS,
            )
            return completed.stdout
        except FileNotFoundError:
            # ffmpeg is not installed. Retrying will not help.
            print(
                "ffprobe not found. Install ffmpeg, or pass "
                "--skip-asset-verification to omit duration metadata."
            )
            return ""
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            if attempt >= max_retries:
                print(
                    f"Failed to run ffprobe after {max_retries} attempts for URL: {url}"
                )
                return ""
            print(
                f"ffprobe failed (attempt {attempt}/{max_retries}), "
                f"retrying in {delay} seconds..."
            )
            time.sleep(delay)
            delay *= 2  # Exponential backoff
    return ""


def _parse_probe(probe: str) -> tuple[int | None, dict[str, str]]:
    """
    Pull the duration and the container tags out of ffprobe's JSON.

    Returns ``(None, {})`` for output that is empty or not JSON at all, which
    is what an ffprobe that never ran leaves behind.
    """
    if not probe:
        return None, {}

    try:
        parsed: Any = json.loads(probe)
    except json.JSONDecodeError:
        print("ffprobe returned output that is not valid JSON; ignoring it.")
        return None, {}

    if not isinstance(parsed, dict):
        return None, {}

    container: Any = parsed.get("format")
    container = container if isinstance(container, dict) else {}

    streams: Any = parsed.get("streams")
    first_stream: Any = streams[0] if isinstance(streams, list) and streams else {}
    first_stream = first_stream if isinstance(first_stream, dict) else {}

    # The first stream, as before, falling back to the container. They agree
    # for audio; a container-level duration is the more reliable of the two
    # for video, where the first stream may be a cover-art image.
    duration = None
    for source in (first_stream, container):
        raw = source.get("duration")
        if raw is not None:
            try:
                duration = int(float(raw))
            except (TypeError, ValueError):
                continue
            break

    # Tag values are strings in practice, but ffprobe is not contractually
    # bound to that, and a tag coerced to str is more useful than a crash.
    raw_tags: Any = container.get("tags")
    tags = (
        {str(key): str(value) for key, value in raw_tags.items()}
        if isinstance(raw_tags, dict)
        else {}
    )

    return duration, tags


def get_file_info(url: str) -> FileInfo:
    # Make HTTP request with retry logic
    response = _make_http_request(url)

    # Get duration of audio/video file
    # We're using the response.url here in order to
    # follow redirects and get the actual file

    # Run ffprobe with retry logic
    probe = _run_ffprobe_with_retry(response.url)
    duration, tags = _parse_probe(probe)

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
        "tags": tags,
    }
