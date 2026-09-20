"""
Filling absent episode fields from the asset's own container tags.

The tool already runs ffprobe against every asset to read its duration, and
the same invocation returns the container's metadata — ID3 frames for MP3,
the iTunes-style atoms for MP4/M4A. This module maps those tags onto the
episode keys the config would otherwise have to spell out by hand.

Two rules govern the merge:

* the config always wins. A tag only ever fills a key that is absent or
  blank, so adding this to an existing config cannot change the feed it
  produces;
* nothing is guessed. A field with no dependable tag behind it — see
  ``publication_date`` below — is left for the config to supply and reported
  as missing by the normal validation pass.
"""

from collections.abc import Callable, Mapping
from typing import Any

from podcast_rss_generator.assets import FileInfo, get_file_info

#: Episode key -> the tag names that can fill it, in order of preference.
#:
#: ffprobe normalises the frames it recognises to lowercase names ("title"
#: from TIT2) and passes the rest through under their raw frame ID, which is
#: why TDES — the podcast description frame, which ffprobe has no friendly
#: name for — appears in both spellings.
TAG_SOURCES: Mapping[str, tuple[str, ...]] = {
    "title": ("title",),
    # TDES is the frame a podcast host writes the show notes to; "comment" is
    # where most encoders put them instead.
    "description": ("description", "TDES", "synopsis", "comment"),
    "episode": ("track",),
    "season": ("disc",),
}

#: Fields parsed as a positive integer rather than taken as text. ID3 writes
#: these as "3" or as "3/10" (position within a total), and MP4 carries the
#: same convention.
NUMERIC_FIELDS = frozenset({"episode", "season"})

#: Deliberately absent from TAG_SOURCES:
#:
#: publication_date — ID3 dates are lossy. A tag written as
#:   "2025-06-19T10:00:00Z" reads back as "2025-06-19T10:00", and in the wild
#:   TDRC is routinely just a year. Deriving publication order from that would
#:   silently misorder a feed, so the config keeps supplying it.
#: image — the feed needs a URL. Cover art embedded in an APIC frame would
#:   have to be extracted and hosted somewhere first.
UNDERIVABLE_FIELDS = ("publication_date", "image")


def _is_blank(value: Any) -> bool:
    """A key counts as unfilled when it is absent, null, or empty text."""
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


def _coerce_number(raw: str) -> int | None:
    """
    Read a track or disc tag as a positive integer.

    Accepts the bare "3" and the "3/10" form; returns None for anything that
    is not a usable number, leaving the field for the config to supply.
    """
    candidate = raw.split("/", 1)[0].strip()
    try:
        number = int(candidate)
    except ValueError:
        return None
    return number if number > 0 else None


def _fill_from_tags(
    episode: Mapping[str, Any], tags: Mapping[str, str]
) -> dict[str, Any]:
    """Return ``episode`` with its blank keys filled from ``tags``."""
    resolved = dict(episode)

    for field, sources in TAG_SOURCES.items():
        if not _is_blank(resolved.get(field)):
            continue

        for source in sources:
            raw = tags.get(source)
            if raw is None or not raw.strip():
                continue

            if field in NUMERIC_FIELDS:
                number = _coerce_number(raw)
                if number is None:
                    continue
                resolved[field] = number
            else:
                resolved[field] = raw.strip()
            break

    return resolved


def _missing_fields(episode: Mapping[str, Any]) -> list[str]:
    """Which fillable keys this episode has left for the asset to supply."""
    return [field for field in TAG_SOURCES if _is_blank(episode.get(field))]


def resolve_episodes(
    config: Mapping[str, Any],
    probe: Callable[[str], FileInfo] = get_file_info,
) -> tuple[dict[str, Any], dict[str, FileInfo]]:
    """
    Fill each episode's blank fields from its asset's tags.

    Returns the resolved config and the probe results, keyed by asset URL.
    Handing that cache to ``generate_rss`` is what keeps this to one probe per
    asset rather than two: the feed needs the same duration and headers back.

    An episode that already spells out every fillable field is not probed here
    at all — ``generate_rss`` will probe it as it always has.
    """
    resolved_config = dict(config)
    probed: dict[str, FileInfo] = {}
    resolved_episodes: list[Any] = []

    for episode in config["episodes"]:
        missing = _missing_fields(episode)
        if not missing:
            resolved_episodes.append(episode)
            continue

        url = episode["asset_url"]
        print(f"Reading metadata from {url} for: {', '.join(missing)}")

        # Two episodes may legitimately point at one asset, and a probe is a
        # network round trip plus an ffprobe process.
        if url not in probed:
            probed[url] = probe(url)

        resolved = _fill_from_tags(episode, probed[url]["tags"])

        filled = [field for field in missing if not _is_blank(resolved.get(field))]
        if filled:
            print(f"  Filled from asset metadata: {', '.join(filled)}")
        unfilled = [field for field in missing if field not in filled]
        if unfilled:
            print(f"  No usable tag for: {', '.join(unfilled)}")

        resolved_episodes.append(resolved)

    resolved_config["episodes"] = resolved_episodes
    return resolved_config, probed
