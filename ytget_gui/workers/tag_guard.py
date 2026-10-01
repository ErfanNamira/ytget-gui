# File: ytget_gui/workers/tag_guard.py
"""Protect an existing file's tags while yt-dlp "re-processes" it.

When two different uploads in one run resolve to the same filename (a single
and the album version on a YouTube Music "Topic" channel share a title),
yt-dlp treats the second as "already downloaded" and runs its metadata and
thumbnail post-processors on the *first* upload's file. For Opus that fails
("Postprocessing: Conversion failed!"); for MP3, M4A and FLAC it succeeds and
silently overwrites the first track's title, source URL and cover with the
second track's.

yt-dlp has no switch to skip post-processing of existing files, so the worker
takes an in-memory snapshot of the tags the moment yt-dlp announces the
existing file, and puts them back after the run if they were changed.
Snapshots are tag-only (the cover is part of the tags), never the audio data.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

log = logging.getLogger(__name__)

# Tag keys in which yt-dlp's --add-metadata stores the source page URL.
_SOURCE_TAG_HINTS = ("purl", "comment", "cmt", "comm", "website", "wxxx")

# Containers whose tags mutagen can both read and write in place. Video
# containers are deliberately excluded: Matroska is not supported by mutagen,
# and re-writing a multi-GB MP4's moov atom is not a "cheap" operation.
SNAPSHOT_EXTENSIONS = frozenset({".mp3", ".m4a", ".flac", ".opus", ".ogg"})


@dataclass
class TagSnapshot:
    kind: str                    # "id3" | "vcomment" | "mp4"
    tags: Any
    pictures: Optional[List[Any]]
    source_text: str             # source-URL tags when the snapshot was taken


@dataclass
class Probe:
    """What was known about an existing file before yt-dlp touched it."""
    source_text: Optional[str]   # None = unreadable, "" = no source tags
    snapshot: Optional[TagSnapshot]


def _open(path: Path):
    import mutagen

    return mutagen.File(path)


def source_text(audio: Any) -> str:
    """Concatenated source-URL-ish tag values of an opened mutagen file."""
    tags = getattr(audio, "tags", None)
    if audio is None or not tags:
        return ""
    try:
        items = list(tags.items())
    except Exception:  # noqa: BLE001 - some tag types are not mappings
        return ""
    parts: List[str] = []
    for key, value in items:
        if not any(h in str(key).lower() for h in _SOURCE_TAG_HINTS):
            continue
        values = value if isinstance(value, (list, tuple)) else [value]
        for entry in values:
            text = getattr(entry, "text", None) or getattr(entry, "url", None) or entry
            if isinstance(text, (list, tuple)):
                text = " ".join(str(t) for t in text)
            text = str(text)
            if len(text) < 4096:
                parts.append(text)
    return "\n".join(parts)


def _take_snapshot(audio: Any, text: str) -> Optional[TagSnapshot]:
    tags = getattr(audio, "tags", None)
    if tags is None:
        return None
    try:
        from mutagen.id3 import ID3
        from mutagen.mp4 import MP4Tags

        pictures = None
        if hasattr(audio, "pictures"):
            pictures = copy.deepcopy(list(audio.pictures))
        if isinstance(tags, ID3):
            return TagSnapshot("id3", copy.deepcopy(list(tags.values())), pictures, text)
        if isinstance(tags, MP4Tags):
            return TagSnapshot("mp4", copy.deepcopy(dict(tags)), pictures, text)
        if isinstance(tags, list):  # VComment family: Ogg Opus/Vorbis, FLAC
            return TagSnapshot("vcomment", copy.deepcopy(list(tags)), pictures, text)
    except Exception as exc:  # noqa: BLE001 - protection is best-effort
        log.debug("Tag snapshot failed: %s", exc)
    return None


def probe(path: Path, *, with_snapshot: bool = True) -> Probe:
    """Read an existing file's source tags (and optionally snapshot all tags)."""
    try:
        audio = _open(path)
    except Exception as exc:  # noqa: BLE001 - probing is best-effort
        log.debug("Could not read tags of %s: %s", path, exc)
        return Probe(None, None)
    if audio is None:
        return Probe("", None)
    text = source_text(audio)
    snapshot = None
    if with_snapshot and path.suffix.lower() in SNAPSHOT_EXTENSIONS:
        snapshot = _take_snapshot(audio, text)
    return Probe(text, snapshot)


def changed_since(path: Path, snapshot: TagSnapshot) -> bool:
    """True when the file's source tags no longer match the snapshot.

    Size and mtime cannot be used: yt-dlp's ffmpeg post-processors restore
    the original mtime, and a rewritten tag block often keeps the same size.
    A re-tag for another upload always rewrites the source URL, though.
    """
    current = probe(path, with_snapshot=False).source_text
    return current is not None and current != snapshot.source_text


def restore(path: Path, snapshot: TagSnapshot) -> bool:
    """Put a snapshot's tags back on `path`. Returns True on success."""
    try:
        if snapshot.kind == "id3":
            from mutagen.id3 import ID3

            tags = ID3()
            for frame in snapshot.tags:
                tags.add(frame)
            tags.save(path)
            return True

        audio = _open(path)
        if audio is None:
            return False
        if audio.tags is None:
            audio.add_tags()
        if snapshot.kind == "mp4":
            audio.tags.clear()
            audio.tags.update(snapshot.tags)
        else:
            del audio.tags[:]
            audio.tags.extend(snapshot.tags)
        if snapshot.pictures is not None and hasattr(audio, "clear_pictures"):
            audio.clear_pictures()
            for picture in snapshot.pictures:
                audio.add_picture(picture)
        audio.save()
        return True
    except Exception as exc:  # noqa: BLE001 - restoration is best-effort
        log.debug("Could not restore tags of %s: %s", path, exc)
        return False
