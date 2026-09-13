# File: ytget_gui/naming.py
"""Output-name disambiguation for one URL queued in several formats.

The default naming (`%(title)s.%(ext)s`) is deliberately kept: a single
queued item still lands on disk as "Title.mkv". Only when the *same* URL is
queued twice into the *same* container would the second download overwrite
(or be skipped as already-downloaded), so the later item gets a short quality
tag appended: "Title QHD.mkv".

Different containers never collide ("Title.mkv" vs "Title.mp3"), so those get
no suffix at all.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from ytget_gui import formats

# Audio pseudo-codes resolve to a real extension in the download worker; the
# container is what decides whether two outputs can collide.
_AUDIO_CONTAINERS = {
    "bestaudio": "mp3",
    "playlist_mp3": "mp3",
    "audio_flac": "flac",
    "audio_opus": "opus",
    "playlist_opus": "opus",
}

_AUDIO_TAGS = {
    "bestaudio": "MP3",
    "playlist_mp3": "MP3",
    "audio_flac": "FLAC",
    "audio_opus": "Opus",
    "playlist_opus": "Opus",
}

# "\U0001F3AC YouTube 1440p (QHD)" -> "QHD"; the parenthesised tag is what the
# user sees in the format box, so it is the least surprising suffix.
_PAREN_TAG_RE = re.compile(r"\(([^)]{1,12})\)")
_HEIGHT_LABEL_RE = re.compile(r"(\d{3,4})p")
_UNSAFE_RE = re.compile(r"[^0-9A-Za-z]+")


def container_key(format_code: str, settings: Any = None) -> str:
    """The on-disk container two items would have to share to collide."""
    code = str(format_code or "")
    if formats.is_spotify_code(code):
        return "spotify"
    if code in _AUDIO_CONTAINERS:
        return _AUDIO_CONTAINERS[code]
    container = str(getattr(settings, "VIDEO_FORMAT", ".mkv") or ".mkv")
    return container.lstrip(".").lower() or "mkv"


def variant_tag(format_label: str, format_code: str = "") -> str:
    """Short quality tag for a format, e.g. "QHD", "4K", "1080p", "FLAC"."""
    code = str(format_code or "")
    if code in _AUDIO_TAGS:
        return _AUDIO_TAGS[code]

    label = str(format_label or "")
    match = _PAREN_TAG_RE.search(label)
    if match:
        tag = _UNSAFE_RE.sub(" ", match.group(1)).strip()
        if tag:
            return tag

    match = _HEIGHT_LABEL_RE.search(label)
    if match:
        return f"{match.group(1)}p"

    height = formats.max_height_in(code)
    if height:
        return f"{height}p"
    return ""


def suffix_for(
    format_label: str,
    format_code: str,
    taken: Optional[Iterable[str]] = None,
) -> str:
    """A tag that is not already used by a sibling item.

    `taken` holds the suffixes of the URL's existing same-container items, so
    two formats that happen to share a tag (or have none at all) still get
    distinct names instead of overwriting each other.
    """
    used = {str(t) for t in (taken or ()) if t}
    base = variant_tag(format_label, format_code) or "alt"
    if base not in used:
        return base
    for n in range(2, 100):
        candidate = f"{base} {n}"
        if candidate not in used:
            return candidate
    return base
