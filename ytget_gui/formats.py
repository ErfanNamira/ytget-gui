# File: ytget_gui/formats.py
"""yt-dlp format-selector construction.

Extracted from AppSettings so the chain logic is testable without
instantiating settings (which touches the filesystem).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Iterable, List

# Audio-only pseudo-codes used by the UI; resolved by the download worker.
AUDIO_FORMAT_CODES = frozenset(
    {"bestaudio", "playlist_mp3", "audio_flac", "audio_opus", "playlist_opus"}
)
PLAYLIST_FORMAT_CODES = frozenset({"playlist_mp3", "playlist_opus"})
SPOTIFY_FORMAT_CODE = "spotify"

_NO_HLS = "[protocol!*=m3u8]"


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
    if parts[-1] != "best":
        parts.append("best")
    return dedupe_chain("/".join(parts))


@lru_cache(maxsize=128)
def video_chain(height: int, width: int | None = None, audio: str = "bestaudio") -> str:
    """Build a codec- and protocol-aware selector chain for a height cap.

    Ordering, best to worst:
      1. AV1 under the cap, DASH/HTTP only
      2. VP9 under the cap, DASH/HTTP only
      3. Any video under the cap, DASH/HTTP only
      4. Any video under the cap, HLS now permitted
      5. bestvideo+audio with no cap (odd/missing height metadata)
      6. best

    Tiers 1-3 exclude HLS so a same-or-lower DASH stream always wins over an
    HLS one. Codec filters use `^=` / `~=` because yt-dlp reports
    "av01.0.05M.08" and "vp09.00.50.08", never the bare "av01"/"vp9" that an
    `=` filter would demand -- with `=` those tiers match nothing and are
    dead weight.
    """
    wf = f"[width<={width}]" if width else ""
    hf = f"[height<={height}]"

    return dedupe_chain(
        "/".join(
            (
                f"bestvideo{hf}{wf}[vcodec^=av01]{_NO_HLS}+{audio}",
                f"bestvideo{hf}{wf}[vcodec~='^vp0?9']{_NO_HLS}+{audio}",
                f"bestvideo{hf}{wf}{_NO_HLS}+{audio}",
                f"bestvideo{hf}{wf}+{audio}",
                f"bestvideo+{audio}",
                "best",
            )
        )
    )


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
            f"best[protocol^=m3u8][height<={height}]/best[protocol^=m3u8]/best"
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
    import re

    return [int(h) for h in re.findall(r"height(?:<=|=)(\d+)", selector or "")]


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


def is_audio_code(code: str | None) -> bool:
    return str(code or "") in AUDIO_FORMAT_CODES


def is_spotify_code(code: str | None) -> bool:
    return str(code or "") == SPOTIFY_FORMAT_CODE
