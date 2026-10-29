# File: ytget_gui/formats.py
"""yt-dlp format-selector construction.

Extracted from AppSettings so the chain logic is testable without
instantiating settings (which touches the filesystem).
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import List, Mapping, Optional

# Audio-only pseudo-codes used by the UI; resolved by the download worker.
AUDIO_FORMAT_CODES = frozenset(
    {"bestaudio", "playlist_mp3", "audio_flac", "audio_opus", "playlist_opus"}
)
PLAYLIST_FORMAT_CODES = frozenset({"playlist_mp3", "playlist_opus"})
SPOTIFY_FORMAT_CODE = "spotify"

# Resolution and frame rate take priority over codec/protocol/extractor tiers.
# vbr (not br) leaves yt-dlp's normal audio/language ranking intact.
VIDEO_FORMAT_SORT = "res,fps,vbr"

VIDEO_CODEC_CHOICES = (
    ("Auto (any codec)", "auto"),
    ("AV1", "av1"),
    ("VP9", "vp9"),
    ("H.264 / AVC", "h264"),
)
VIDEO_PRIORITY_CHOICES = (
    ("Balanced (frame rate, then bitrate)", "balanced"),
    ("Highest video bitrate", "bitrate"),
    ("Preferred codec first", "codec"),
)
_CODEC_SORT = {"av1": "vcodec:av01", "vp9": "vcodec:vp9.2", "h264": "vcodec:avc"}


def video_format_sort(codec: str = "auto", priority: str = "balanced",
                      container: str = "mkv") -> str:
    """Soft preferences *within* the best resolution, never codec filters.

    Highest-bitrate mode puts vbr ahead of FPS. Balanced retains 2.8.4's
    FPS-first policy. Codec-first puts the preferred codec ahead of both.
    Audio's codec/language ordering is unaffected (all video fields tie).
    """
    if container.lstrip(".") == "webm" and codec == "h264":
        codec = "auto"  # AVC cannot be stream-copied into WebM.
    codec_sort = _CODEC_SORT.get(codec, "vcodec")
    if priority == "bitrate":
        return f"res,vbr,fps,{codec_sort}"
    if priority == "codec":
        return f"res,{codec_sort},fps,vbr"
    # Keep the existing default's tie-breaking exactly as before.
    return VIDEO_FORMAT_SORT if codec not in _CODEC_SORT else f"res,fps,vbr,{codec_sort}"


# Module level: these were compiled inside the functions below, which run for
# every preset build and every format resolution.
_HEIGHT_CAP_RE = re.compile(r"\[height<=(\d+)\]")
_WIDTH_CAP_RE = re.compile(r"\[width<=(\d+)\]")
_HEIGHT_ANY_RE = re.compile(r"height(?:<=|=)(\d+)")


def dedupe_chain(chain: str) -> str:
    seen: set[str] = set()
    parts: List[str] = []
    for seg in (s.strip() for s in chain.split("/")):
        if seg and seg not in seen:
            parts.append(seg)
            seen.add(seg)
    return "/".join(parts)


def ensure_best_fallback(fmt: str) -> str:
    """Guarantee a selector degrades to `best` instead of hard-failing with
    "Requested format is not available"."""
    if not fmt:
        return "best"
    parts = [p.strip() for p in fmt.split("/") if p.strip()]
    if not parts:
        return "best"
    caps = _HEIGHT_CAP_RE.findall(fmt)
    widths = _WIDTH_CAP_RE.findall(fmt)
    cap = f"[height<={min(map(int, caps))}]" if caps else ""
    cap += f"[width<={min(map(int, widths))}]" if widths else ""
    fallback = "best" + cap
    if parts[-1] != fallback:
        parts.append(fallback)
    return dedupe_chain("/".join(parts))


@lru_cache(maxsize=128)
def video_chain(height: int, width: int | None = None, audio: str = "bestaudio") -> str:
    """Best video within the cap, without codec or protocol downgrade tiers.

    yt-dlp's slash operator is a *fallback*, not a comparison: a 360p VP9
    match in an earlier branch prevented a later 1080p AVC match entirely.
    Rank all candidates together; the worker supplies VIDEO_FORMAT_SORT.
    bestvideo* includes progressive streams so a lower separate-video stream
    cannot mask a higher-quality already-muxed stream.
    """
    wf = f"[width<={width}]" if width else ""
    hf = f"[height<={height}]"
    return f"bestvideo*{hf}{wf}+{audio}/best{hf}{wf}"


@lru_cache(maxsize=1)
def _legacy_video_presets() -> dict[str, str]:
    """Exact 2.8.3 built-ins only; never rewrite custom selectors/format IDs."""
    mapping = {}
    for height, width in ((4320, 7680), (2160, 3840), (1440, 2560),
                          (1080, 1920), (720, 1280), (480, 854)):
        for w in (None, width):
            cap = f"[height<={height}]" + (f"[width<={w}]" if w else "")
            old = "/".join((
                f"bestvideo{cap}[vcodec^=av01][protocol!*=m3u8]+bestaudio",
                f"bestvideo{cap}[vcodec~='^vp0?9'][protocol!*=m3u8]+bestaudio",
                f"bestvideo{cap}[protocol!*=m3u8]+bestaudio",
                f"bestvideo{cap}+bestaudio",
                f"best{cap}",
            ))
            mapping[old] = video_chain(height, width=w)
    return mapping


def normalise_video_selector(code: str) -> str:
    """Upgrade persisted built-ins, leaving explicit user selectors intact."""
    return _legacy_video_presets().get(code, code)


def webm_compatible_selector(selector: str) -> str:
    """Constrain built-ins to codecs ffmpeg can stream-copy into WebM.

    Removing the old VP9-first tier otherwise makes a valid AVC selection
    fail at the WebM merger. Explicit custom selectors remain user-owned.
    """
    height = max_height_in(selector)
    widths = _WIDTH_CAP_RE.findall(selector)
    width = int(widths[0]) if widths else None
    if not height or selector != video_chain(height, width):
        return selector
    video_filter = "[vcodec~='^(av01|vp0?[89])']"
    audio_filter = "[acodec~='^(opus|vorbis)']"
    return (selector.replace("bestvideo*", "bestvideo*" + video_filter)
            .replace("+bestaudio", "+bestaudio" + audio_filter)
            .replace("/best[", "/best" + video_filter + audio_filter + "["))


@lru_cache(maxsize=32)
def hls_chain(height: int | None = None) -> str:
    """Selector for sites that genuinely only serve usable streams over HLS.

    A normal (non-HLS) merge at the requested height is attempted first;
    muxed HLS is the fallback. Preferring muxed HLS outright caps quality at
    whatever single pre-muxed rendition the site publishes.
    """
    if height:
        return (
            f"bestvideo[protocol^=m3u8][height<={height}]+bestaudio/"
            f"bestvideo[height<={height}]+bestaudio/"
            f"best[protocol^=m3u8][height<={height}]/best[height<={height}]"
        )
    return (
        "bestvideo[protocol^=m3u8]+bestaudio/"
        "bestvideo+bestaudio/"
        "best[protocol^=m3u8]/best"
    )


def audio_chain(base: str = "bestaudio") -> str:
    """`bestaudio` alone has no fallback: some player clients expose no format
    literally satisfying it, which hard-failed the whole item."""
    return ensure_best_fallback(f"{base}/bestaudio*")


def heights_in(selector: str) -> List[int]:
    """Extract every height cap present in a resolved selector chain."""
    return [int(h) for h in _HEIGHT_ANY_RE.findall(selector or "")]


def max_height_in(selector: str) -> int | None:
    heights = heights_in(selector)
    return max(heights) if heights else None


def build_resolution_presets() -> dict[str, str]:
    """Labelled presets shown in the main window's format combo."""
    presets: dict[str, str] = {}

    for label, h in (
        ("4320p (8K)", 4320),
        ("2160p (4K)", 2160),
        ("1440p (QHD)", 1440),
        ("1080p (FHD)", 1080),
        ("720p (HD)", 720),
        ("480p (SD)", 480),
    ):
        icon = "\U0001F3AC" if h >= 2160 else ("\U0001F3A5" if h >= 1080 else "\U0001F4F1")
        presets[f"{icon} YouTube {label}"] = video_chain(h)

    # Universal presets add a width cap so anamorphic/cropped sources on
    # non-YouTube sites cannot slip past the intended tier.
    for label, h, w in (
        ("4320p (8K)", 4320, 7680),
        ("2160p (4K)", 2160, 3840),
        ("1440p (QHD)", 1440, 2560),
        ("1080p (FHD)", 1080, 1920),
        ("720p (HD)", 720, 1280),
        ("480p (SD)", 480, 854),
    ):
        presets[f"\U0001F310 Universal {label}"] = video_chain(h, width=w)

    presets["\U0001F3B5 Single Audio (MP3)"] = "bestaudio"
    presets["\U0001F3A7 Single Audio (FLAC)"] = "audio_flac"
    presets["\U0001F3A7 Single Audio (Opus)"] = "audio_opus"
    presets["\U0001F3B6 Audio Playlist (MP3)"] = "playlist_mp3"
    presets["\U0001F3B6 Audio Playlist (Opus)"] = "playlist_opus"
    presets["\U0001F3B8 Spotify (via SpotDL)"] = SPOTIFY_FORMAT_CODE

    return presets


def estimate_download_size(
    video_sizes: Optional[Mapping[int, int]],
    audio_size: Optional[int],
    format_code: str,
) -> Optional[int]:
    """Approximate bytes for `format_code`, or None when unknown.

    Audio-only presets return the audio stream alone; video presets return
    the best height within the preset's cap plus the audio track that gets
    merged with it. Sites that only publish progressive streams report no
    audio-only format, and those sizes already include the audio.
    """
    if is_audio_code(format_code):
        return audio_size
    if not video_sizes:
        return None
    cap = max_height_in(format_code)
    heights = [h for h in video_sizes if cap is None or h <= cap]
    if not heights:
        # Every selector branch is capped: no playable match, not the
        # smallest above-cap video. Do not advertise an impossible estimate.
        return None
    total = video_sizes[max(heights)]
    if audio_size:
        total += audio_size
    return total or None


def is_audio_code(code: str | None) -> bool:
    return str(code or "") in AUDIO_FORMAT_CODES


def is_spotify_code(code: str | None) -> bool:
    return str(code or "") == SPOTIFY_FORMAT_CODE
