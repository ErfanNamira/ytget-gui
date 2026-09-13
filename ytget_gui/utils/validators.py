# File: ytget_gui/utils/validators.py

from __future__ import annotations

import re
from urllib.parse import urlparse, parse_qs, urlsplit

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

_DATE_RE = re.compile(r"^\d{8}$")

# Pre-compiled because these run per keystroke in the Preferences dialogs and
# per URL when a queue is imported. `re.fullmatch` re-parses the pattern text
# on every call once the internal cache is evicted by other call sites.
_ITEM_SINGLE_RE = re.compile(r"[1-9]\d*")
_ITEM_RANGE_RE = re.compile(r"[1-9]\d*\s*-\s*[1-9]\d*")
# Open-ended forms yt-dlp accepts: "5-" (from 5 to the end) and "-4"
# (from the start to 4).
_ITEM_RANGE_OPEN_RE = re.compile(r"(?:[1-9]\d*\s*-)|(?:-\s*[1-9]\d*)")
_ITEM_SLICE_RE = re.compile(r"-?\d*:-?\d*(?::-?\d*)?")
_RATE_LIMIT_RE = re.compile(r"\d+(?:\.\d+)?[KkMmGgTtPpEeZzYy]?")
_RATE_SUFFIX_RE = re.compile(r"[A-Za-z]$")


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
    text = text.strip()
    if any(ch.isspace() or ord(ch) < 32 for ch in text):
        return False
    try:
        parsed = urlsplit(text)
        _ = parsed.port
        return (parsed.scheme.lower() in ("http", "https") and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None
                and not any(c in parsed.netloc for c in "\\{}<>"))
    except ValueError:
        return False


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
    text = (text or "").strip()
    return is_youtube_url(text) and urlparse(text).path.startswith("/shorts/")


def is_playlist_url(text: str) -> bool:
    return bool(parse_qs(urlparse(text or "").query).get("list"))


def is_valid_timecode(text: str) -> bool:
    t = (text or "").strip()
    return t == "" or timecode_to_seconds(t) is not None


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
    for part in t.split(","):
        part = part.strip()
        if _ITEM_SINGLE_RE.fullmatch(part):
            continue
        if _ITEM_RANGE_RE.fullmatch(part):
            a, b = map(int, part.split("-"))
            if b < a:
                return False
            continue
        if _ITEM_RANGE_OPEN_RE.fullmatch(part):
            continue
        if not _ITEM_SLICE_RE.fullmatch(part):
            return False
        bits = part.split(":")
        if any(v in ("-", "0") for v in bits[:2]):
            return False
        if len(bits) == 3 and bits[2] in ("-", "0"):
            return False
    return True


def is_valid_rate_limit(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if not _RATE_LIMIT_RE.fullmatch(t):
        return False
    # A bare unit suffix ("K") leaves an empty numeric part, which float()
    # raises on -- that surfaced as a crash in the Preferences validator
    # rather than an inline "invalid" hint.
    number = _RATE_SUFFIX_RE.sub("", t)
    try:
        return float(number) > 0
    except ValueError:
        return False


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
    # yt-dlp accepts language tags and regular expressions, including exclusions.
    if not t:
        return True
    try:
        for token in t.split(","):
            token = token.strip().removeprefix("-")
            if not token or any(ord(c) < 32 for c in token):
                return False
            re.compile(token)
    except re.error:
        return False
    return True


def is_valid_proxy(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    try:
        parsed = urlsplit(t)
        _ = parsed.port
        return (parsed.scheme in ("http", "https", "socks4", "socks5", "socks5h")
                and bool(parsed.hostname) and not any(c.isspace() for c in t))
    except ValueError:
        return False
