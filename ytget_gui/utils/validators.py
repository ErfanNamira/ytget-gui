# File: ytget_gui/utils/validators.py

from __future__ import annotations

import re
from urllib.parse import urlparse

_ANY_HTTP_URL_RE = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)

_YOUTUBE_HOSTS = (
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
)

_SPOTIFY_HOSTS = ("open.spotify.com", "spotify.com", "www.spotify.com")

_TIME_RE = re.compile(r"^(?:\d+|(?:\d{1,3}:)?[0-5]?\d:[0-5]\d)$")
_PLAYLIST_ITEMS_RE = re.compile(
    r"^\s*\d+\s*(?:-\s*\d+\s*)?(?:\s*,\s*\d+\s*(?:-\s*\d+\s*)?)*\s*$"
)
_RATE_RE = re.compile(r"^\d+(?:\.\d+)?[KkMmGg]$")
_DATE_RE = re.compile(r"^\d{8}$")
_SUB_LANGS_RE = re.compile(r"^[A-Za-z]{2,3}(?:\s*,\s*[A-Za-z]{2,3})*$")


def _host(text: str) -> str:
    try:
        netloc = urlparse(text if "://" in text else f"https://{text}").netloc
    except ValueError:
        return ""
    return netloc.split("@")[-1].split(":")[0].lower()


def is_supported_url(text: str) -> bool:
    """Any http(s) URL. yt-dlp supports well over a thousand sites, so the
    app deliberately does not gatekeep on host."""
    if not text:
        return False
    return bool(_ANY_HTTP_URL_RE.match(text.strip()))


def is_youtube_url(text: str) -> bool:
    """Host-based rather than substring-based.

    A substring check matched hostile inputs such as
    `https://evil.example/?x=youtube.com`, which then had YouTube-specific
    flags (player_client, cookies) applied to an unrelated host.
    """
    if not text:
        return False
    return _host(text.strip()) in _YOUTUBE_HOSTS


def is_youtube_music_url(text: str) -> bool:
    if not text:
        return False
    return _host(text.strip()) == "music.youtube.com"


def is_spotify_url(text: str) -> bool:
    if not text:
        return False
    return _host(text.strip()) in _SPOTIFY_HOSTS


def is_short_video_url(text: str) -> bool:
    return "/shorts/" in (text or "")


def is_playlist_url(text: str) -> bool:
    return "list=" in (text or "")


def is_valid_timecode(text: str) -> bool:
    t = (text or "").strip()
    return t == "" or bool(_TIME_RE.match(t))


def timecode_to_seconds(text: str) -> int | None:
    t = (text or "").strip()
    if not t:
        return None
    if t.isdigit():
        return int(t)
    parts = t.split(":")
    try:
        if len(parts) == 2:
            m, s = int(parts[0]), int(parts[1])
            return m * 60 + s if 0 <= s <= 59 and m >= 0 else None
        if len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            if h >= 0 and 0 <= m <= 59 and 0 <= s <= 59:
                return h * 3600 + m * 60 + s
    except ValueError:
        return None
    return None


def is_valid_playlist_items(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if not _PLAYLIST_ITEMS_RE.match(t):
        return False
    for part in (p.strip() for p in t.split(",")):
        if "-" in part:
            a, b = (x.strip() for x in part.split("-", 1))
            if not (a.isdigit() and b.isdigit()):
                return False
            if int(a) <= 0 or int(b) <= 0 or int(b) < int(a):
                return False
        elif not part.isdigit() or int(part) <= 0:
            return False
    return True


def is_valid_rate_limit(text: str) -> bool:
    t = (text or "").strip()
    return t == "" or bool(_RATE_RE.match(t))


def is_valid_dateafter(text: str) -> bool:
    from datetime import datetime

    t = (text or "").strip()
    if not t:
        return True
    if not _DATE_RE.match(t):
        return False
    try:
        datetime.strptime(t, "%Y%m%d")
    except ValueError:
        return False
    return True


def is_valid_sub_langs(text: str) -> bool:
    t = (text or "").strip()
    return t == "" or bool(_SUB_LANGS_RE.match(t))


def is_valid_proxy(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    return t.startswith(("http://", "https://", "socks4://", "socks5://", "socks5h://"))
