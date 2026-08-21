# File: ytget_gui/spotdl_settings.py
"""SpotDL settings, persisted inside config.json under the "SPOTDL" key."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List

SPOTDL_FORMATS: tuple[str, ...] = ("mp3", "flac", "ogg", "opus", "m4a", "wav")

SPOTDL_LYRICS_PROVIDERS: tuple[str, ...] = ("synced", "musixmatch", "genius", "azlyrics")

SPOTDL_AUDIO_PROVIDERS: tuple[str, ...] = (
    "youtube-music",
    "youtube",
    "soundcloud",
    "bandcamp",
    "piped",
)

SPOTDL_BITRATES: tuple[str, ...] = (
    "auto", "disable",
    "8k", "16k", "24k", "32k", "40k", "48k",
    "64k", "80k", "96k", "112k", "128k",
    "160k", "192k", "224k", "256k", "320k",
)

SPOTDL_OVERWRITE_MODES: tuple[str, ...] = ("skip", "metadata", "force")

SPOTDL_OUTPUT_TOKENS: tuple[str, ...] = (
    "{title}", "{artists}", "{artist}", "{album}", "{album-artist}",
    "{genre}", "{disc-number}", "{disc-count}", "{duration}",
    "{year}", "{original-date}", "{track-number}", "{tracks-count}",
    "{isrc}", "{track-id}", "{publisher}", "{list-name}",
    "{list-position}", "{list-length}", "{output-ext}",
)

DEFAULT_OUTPUT_TEMPLATE = "{artists} - {title} - {year}.{output-ext}"

DEFAULT_AUDIO_PROVIDERS: tuple[str, ...] = ("youtube-music", "youtube")

MAX_THREADS = 32


@dataclass
class SpotDLSettings:
    # Core
    SPOTDL_FORMAT: str = "opus"
    SPOTDL_THREADS: int = 12
    SPOTDL_OUTPUT: str = DEFAULT_OUTPUT_TEMPLATE

    # Lyrics
    SPOTDL_LYRICS: List[str] = field(default_factory=lambda: ["synced"])
    SPOTDL_GENERATE_LRC: bool = True

    # Audio source. youtube-music first (fastest, best metadata match) with
    # youtube as a safety net so one provider hiccup (bot-check, region lock,
    # missing format) does not silently drop a track.
    SPOTDL_AUDIO_PROVIDERS: List[str] = field(
        default_factory=lambda: list(DEFAULT_AUDIO_PROVIDERS)
    )

    # Quality
    SPOTDL_BITRATE: str = "auto"

    # Passthrough
    SPOTDL_YT_DLP_ARGS: str = "--sleep-interval 1 --max-sleep-interval 2"
    SPOTDL_FFMPEG_ARGS: str = ""

    # Behaviour
    SPOTDL_OVERWRITE: str = "skip"
    SPOTDL_PLAYLIST_NUMBERING: bool = False
    SPOTDL_SKIP_EXPLICIT: bool = False
    SPOTDL_SPONSOR_BLOCK: bool = False
    SPOTDL_ADD_UNAVAILABLE: bool = False

    # Proxy
    SPOTDL_USE_MAIN_PROXY: bool = True
    SPOTDL_PROXY: str = ""

    # ------------------------------------------------------------------
    # Serialisation. Driven by dataclass introspection rather than a
    # hand-maintained to_dict() -- the old version listed every key twice,
    # so adding a field without touching to_dict() made it silently
    # non-persistent and simultaneously invisible to from_dict().
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any] | None) -> "SpotDLSettings":
        obj = cls()
        if not isinstance(data, dict):
            return obj

        for f in fields(cls):
            if f.name not in data:
                continue
            current = getattr(obj, f.name)
            setattr(obj, f.name, _coerce(data[f.name], current))

        obj.normalise()
        return obj

    def normalise(self) -> None:
        """Clamp/validate every field to a value the spotdl CLI accepts.

        Config files are user-editable and survive downgrades, so a stale or
        hand-edited value must never reach the command line.
        """
        if self.SPOTDL_FORMAT not in SPOTDL_FORMATS:
            self.SPOTDL_FORMAT = "opus"

        self.SPOTDL_THREADS = max(1, min(MAX_THREADS, int(self.SPOTDL_THREADS or 1)))

        if not (self.SPOTDL_OUTPUT or "").strip():
            self.SPOTDL_OUTPUT = DEFAULT_OUTPUT_TEMPLATE

        self.SPOTDL_LYRICS = [p for p in self.SPOTDL_LYRICS if p in SPOTDL_LYRICS_PROVIDERS]

        providers = [p for p in self.SPOTDL_AUDIO_PROVIDERS if p in SPOTDL_AUDIO_PROVIDERS]
        self.SPOTDL_AUDIO_PROVIDERS = providers or list(DEFAULT_AUDIO_PROVIDERS)

        if self.SPOTDL_BITRATE not in SPOTDL_BITRATES:
            self.SPOTDL_BITRATE = "auto"

        if self.SPOTDL_OVERWRITE not in SPOTDL_OVERWRITE_MODES:
            self.SPOTDL_OVERWRITE = "skip"

    def uses_default_providers(self) -> bool:
        return tuple(self.SPOTDL_AUDIO_PROVIDERS) == DEFAULT_AUDIO_PROVIDERS


def _coerce(value: Any, current: Any) -> Any:
    """Best-effort coercion of a persisted value to the field's type."""
    if isinstance(current, bool):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)

    if isinstance(current, int):
        try:
            return int(value)
        except (TypeError, ValueError):
            return current

    if isinstance(current, list):
        if isinstance(value, list):
            return [str(v) for v in value]
        return [str(value)] if value else []

    if isinstance(current, str):
        return "" if value is None else str(value)

    return value
