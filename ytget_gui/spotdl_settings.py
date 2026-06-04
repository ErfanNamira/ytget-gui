# File: ytget_gui/spotdl_settings.py

"""
SpotDL-specific settings, persisted inside the main config.json
under the key "SPOTDL".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
# Supported choices (kept in sync with spotdl CLI)
# ---------------------------------------------------------------------------
SPOTDL_FORMATS = ["mp3", "flac", "ogg", "opus", "m4a", "wav"]

SPOTDL_LYRICS_PROVIDERS = ["synced", "musixmatch", "genius", "azlyrics"]

SPOTDL_AUDIO_PROVIDERS = [
    "youtube",
    "youtube-music",
    "soundcloud",
    "bandcamp",
    "piped",
]

SPOTDL_BITRATES = [
    "auto", "disable",
    "8k", "16k", "24k", "32k", "40k", "48k",
    "64k", "80k", "96k", "112k", "128k",
    "160k", "192k", "224k", "256k", "320k",
]

SPOTDL_OVERWRITE_MODES = ["skip", "metadata", "force"]

# Common output template tokens (shown as hints in the UI)
SPOTDL_OUTPUT_TOKENS = (
    "{title}", "{artists}", "{artist}", "{album}", "{album-artist}",
    "{genre}", "{disc-number}", "{disc-count}", "{duration}",
    "{year}", "{original-date}", "{track-number}", "{tracks-count}",
    "{isrc}", "{track-id}", "{publisher}", "{list-name}",
    "{list-position}", "{list-length}", "{output-ext}",
)

# ---------------------------------------------------------------------------
# Default output template (mirrors the user's usual command)
# ---------------------------------------------------------------------------
DEFAULT_OUTPUT_TEMPLATE = "{artists} - {title} - {year}.{output-ext}"


@dataclass
class SpotDLSettings:
    # ── Core ────────────────────────────────────────────────────────────────
    SPOTDL_FORMAT: str = "opus"
    SPOTDL_THREADS: int = 6
    SPOTDL_OUTPUT: str = DEFAULT_OUTPUT_TEMPLATE

    # ── Lyrics ──────────────────────────────────────────────────────────────
    SPOTDL_LYRICS: List[str] = field(default_factory=lambda: ["synced"])
    SPOTDL_GENERATE_LRC: bool = True

    # ── Audio source ────────────────────────────────────────────────────────
    SPOTDL_AUDIO_PROVIDERS: List[str] = field(
        default_factory=lambda: ["youtube", "youtube-music"]
    )

    # ── Quality ─────────────────────────────────────────────────────────────
    SPOTDL_BITRATE: str = "auto"

    # ── yt-dlp passthrough ──────────────────────────────────────────────────
    SPOTDL_YT_DLP_ARGS: str = "--sleep-interval 1 --max-sleep-interval 2"

    # ── Extra ffmpeg args ────────────────────────────────────────────────────
    SPOTDL_FFMPEG_ARGS: str = ""

    # ── Behaviour ───────────────────────────────────────────────────────────
    SPOTDL_OVERWRITE: str = "skip"          # skip | metadata | force
    SPOTDL_PLAYLIST_NUMBERING: bool = False
    SPOTDL_SKIP_EXPLICIT: bool = False
    SPOTDL_SPONSOR_BLOCK: bool = False
    SPOTDL_ADD_UNAVAILABLE: bool = False

    # ── Proxy (re-uses main proxy or can override) ───────────────────────────
    SPOTDL_USE_MAIN_PROXY: bool = True
    SPOTDL_PROXY: str = ""

    # ────────────────────────────────────────────────────────────────────────
    #  Serialisation helpers
    # ────────────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "SPOTDL_FORMAT": self.SPOTDL_FORMAT,
            "SPOTDL_THREADS": self.SPOTDL_THREADS,
            "SPOTDL_OUTPUT": self.SPOTDL_OUTPUT,
            "SPOTDL_LYRICS": self.SPOTDL_LYRICS,
            "SPOTDL_GENERATE_LRC": self.SPOTDL_GENERATE_LRC,
            "SPOTDL_AUDIO_PROVIDERS": self.SPOTDL_AUDIO_PROVIDERS,
            "SPOTDL_BITRATE": self.SPOTDL_BITRATE,
            "SPOTDL_YT_DLP_ARGS": self.SPOTDL_YT_DLP_ARGS,
            "SPOTDL_FFMPEG_ARGS": self.SPOTDL_FFMPEG_ARGS,
            "SPOTDL_OVERWRITE": self.SPOTDL_OVERWRITE,
            "SPOTDL_PLAYLIST_NUMBERING": self.SPOTDL_PLAYLIST_NUMBERING,
            "SPOTDL_SKIP_EXPLICIT": self.SPOTDL_SKIP_EXPLICIT,
            "SPOTDL_SPONSOR_BLOCK": self.SPOTDL_SPONSOR_BLOCK,
            "SPOTDL_ADD_UNAVAILABLE": self.SPOTDL_ADD_UNAVAILABLE,
            "SPOTDL_USE_MAIN_PROXY": self.SPOTDL_USE_MAIN_PROXY,
            "SPOTDL_PROXY": self.SPOTDL_PROXY,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SpotDLSettings":
        obj = cls()
        for key, default in obj.to_dict().items():
            val = d.get(key, default)
            # type-coerce lists that might have been stored as something else
            if isinstance(default, list) and not isinstance(val, list):
                val = [val] if val else []
            elif isinstance(default, bool) and not isinstance(val, bool):
                val = bool(val)
            elif isinstance(default, int) and not isinstance(val, int):
                try:
                    val = int(val)
                except Exception:
                    val = default
            setattr(obj, key, val)
        return obj
