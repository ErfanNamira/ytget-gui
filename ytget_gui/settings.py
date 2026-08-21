# File: ytget_gui/settings.py
"""Application settings with declarative, atomic persistence.

The previous revision maintained `save_config()` and `load_config()` as two
parallel hand-written key lists. Every new setting had to be added in three
places (the dataclass, the saver, the loader) and omitting one produced a
setting that silently reverted on restart. Persistence is now driven by
`_PLAIN_KEYS` / `_PATH_KEYS` plus a per-key validator table, so a field can
only be forgotten in one place instead of three.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping

from ytget_gui import _version
from ytget_gui.formats import (
    build_resolution_presets,
    ensure_best_fallback,
    video_chain,
)
from ytget_gui.spotdl_settings import SpotDLSettings
from ytget_gui.utils.paths import (
    default_downloads_dir,
    ensure_dir,
    executable_name,
    get_base_path,
    is_usable_file,
    resolve_tool,
)

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Enumerated choices
# --------------------------------------------------------------------------

YOUTUBE_PLAYER_CLIENTS: Dict[str, str] = {
    "Auto (yt-dlp default)": "auto",
    "default,web_embedded (cookies-safe fallback)": "default,web_embedded",
    "default": "default",
    "web": "web",
    "web_embedded": "web_embedded",
    "web_safari": "web_safari",
    "tv": "tv",
    "tv_embedded": "tv_embedded",
    "mweb": "mweb",
    "ios": "ios",
    "android": "android",
}

FILENAME_FORMAT_PRESETS: Dict[str, str] = {
    "title_only": "%(title)s",
    "artist_title": "%(artist)s - %(title)s",
    "title_artist": "%(title)s - %(artist)s",
    "artist_album_title": "%(artist)s - %(album)s - %(title)s",
    "track_title": "%(track_number)s - %(title)s",
    "album_track_title": "%(album)s - %(track_number)s - %(title)s",
    "playlist_index_title": "%(playlist_index)s - %(title)s",
    "uploader_title": "%(uploader)s - %(title)s",
    "channel_title": "%(channel)s - %(title)s",
    "date_title": "%(upload_date)s - %(title)s",
    "id_title": "%(id)s - %(title)s",
}

CHAPTERS_MODES = ("none", "embed", "split")
VIDEO_CONTAINERS = (".mkv", ".mp4", ".webm")
THUMBNAIL_FORMATS = ("png", "jpg", "webp")
BROWSERS = (
    "", "chrome", "chromium", "edge", "firefox",
    "opera", "brave", "vivaldi", "safari", "whale",
)

DEFAULT_TITLE_TEMPLATE = "%(title)s.%(ext)s"
DEFAULT_PLAYLIST_TEMPLATE = "%(playlist_index)s - %(title)s.%(ext)s"

MAX_LOG_LINES = 1000

# Keys serialised as JSON natives. Coerced on load to the type of the
# in-memory default, so a hand-edited config cannot inject a wrong type.
_PLAIN_KEYS: tuple[str, ...] = (
    "PROXY_URL",
    "IGNORE_SSL_ERRORS",
    "CUSTOM_CA_CERT",
    "SPONSORBLOCK_CATEGORIES",
    "CHAPTERS_MODE",
    "WRITE_SUBS",
    "SUB_LANGS",
    "WRITE_AUTO_SUBS",
    "CONVERT_SUBS_TO_SRT",
    "ENABLE_ARCHIVE",
    "PLAYLIST_REVERSE",
    "PLAYLIST_ITEMS",
    "AUDIO_NORMALIZE",
    "ADD_METADATA",
    "LIMIT_RATE",
    "RETRIES",
    "AUTO_RETRY_COUNT",
    "QUEUE_ERROR_RETRIES",
    "ORGANIZE_BY_UPLOADER",
    "FILENAME_FORMAT",
    "CUSTOM_FILENAME_TEMPLATE",
    "DATEAFTER",
    "COOKIES_FROM_BROWSER",
    "COOKIES_AUTO_REFRESH",
    "COOKIES_LAST_IMPORTED",
    "LIVE_FROM_START",
    "YT_MUSIC_METADATA",
    "CLIP_START",
    "CLIP_END",
    "CUSTOM_FFMPEG_ARGS",
    "EXTRA_YTDLP_ARGS",
    "YOUTUBE_PLAYER_CLIENT",
    "CROP_AUDIO_COVERS",
    "VIDEO_FORMAT",
    "WRITE_THUMBNAIL",
    "CONVERT_THUMBNAILS",
    "THUMBNAIL_FORMAT",
    "EMBED_THUMBNAIL",
    "PREFER_HLS",
    "HLS_PREFERRED_DOMAINS",
    "LOG_THUMBNAILS",
    "MAX_LOG_LINES",
    "CONFIRM_ON_QUIT",
)

# Keys stored as strings but held as Path. Restored only when still valid.
_PATH_KEYS: tuple[str, ...] = (
    "DOWNLOADS_DIR",
    "YT_DLP_PATH",
    "FFMPEG_PATH",
    "FFPROBE_PATH",
    "PHANTOMJS_PATH",
    "DENO_PATH",
    "COOKIES_PATH",
    "ARCHIVE_PATH",
)

# Per-key sanitisers applied after load, so an out-of-range or stale value
# from a downgraded/hand-edited config can never reach a CLI invocation.
_VALIDATORS: Dict[str, Callable[[Any], Any]] = {
    "CHAPTERS_MODE": lambda v: v if v in CHAPTERS_MODES else "embed",
    "VIDEO_FORMAT": lambda v: v if v in VIDEO_CONTAINERS else ".mkv",
    "THUMBNAIL_FORMAT": lambda v: v if v in THUMBNAIL_FORMATS else "png",
    "YOUTUBE_PLAYER_CLIENT": (
        lambda v: v if v in YOUTUBE_PLAYER_CLIENTS.values() else "auto"
    ),
    "FILENAME_FORMAT": (
        lambda v: v
        if v in ("default", "custom") or v in FILENAME_FORMAT_PRESETS
        else "default"
    ),
    "COOKIES_FROM_BROWSER": lambda v: v if v in BROWSERS else "",
    "RETRIES": lambda v: max(1, min(100, int(v))),
    "AUTO_RETRY_COUNT": lambda v: max(0, min(20, int(v))),
    "QUEUE_ERROR_RETRIES": lambda v: max(0, min(20, int(v))),
    "MAX_LOG_LINES": lambda v: max(100, min(50_000, int(v))),
    "SPONSORBLOCK_CATEGORIES": lambda v: [str(x) for x in v if str(x).strip()],
    "HLS_PREFERRED_DOMAINS": lambda v: [
        str(x).strip().lower() for x in v if str(x).strip()
    ],
}


@dataclass
class AppSettings:
    # --- Identity (never persisted) ---
    VERSION: str = _version.__version__
    APP_NAME: str = _version.APP_NAME
    GITHUB_URL: str = _version.GITHUB_URL

    # --- Locations ---
    BASE_DIR: Path = field(default_factory=get_base_path)
    DOWNLOADS_DIR: Path = field(default_factory=default_downloads_dir)
    INTERNAL_DIR: Path = field(init=False)
    CACHE_DIR: Path = field(init=False)
    CONFIG_PATH: Path = field(init=False)
    QUEUE_PATH: Path = field(init=False)
    COOKIES_PATH: Path = field(init=False)
    ARCHIVE_PATH: Path = field(init=False)

    # --- External binaries ---
    YT_DLP_PATH: Path = field(init=False)
    FFMPEG_PATH: Path = field(init=False)
    FFPROBE_PATH: Path = field(init=False)
    PHANTOMJS_PATH: Path = field(init=False)
    DENO_PATH: Path = field(init=False)

    # --- Output templates (derived from DOWNLOADS_DIR) ---
    OUTPUT_TEMPLATE: str = field(init=False, default="")
    PLAYLIST_TEMPLATE: str = field(init=False, default="")

    # --- Format presets ---
    RESOLUTIONS: Dict[str, str] = field(default_factory=build_resolution_presets)

    # --- Network ---
    PROXY_URL: str = ""
    IGNORE_SSL_ERRORS: bool = False
    # Path to a self-signed CA to trust explicitly (e.g. for a local
    # MITM/domain-fronting proxy). Takes precedence over IGNORE_SSL_ERRORS:
    # validation stays on, it just also trusts this one certificate rather
    # than trusting nothing.
    CUSTOM_CA_CERT: str = ""
    LIMIT_RATE: str = ""
    RETRIES: int = 10
    # In-process re-runs of the whole yt-dlp command after a known-transient
    # failure (expired signed URL/403, momentarily missing format, dropped
    # connection). 0 disables.
    AUTO_RETRY_COUNT: int = 3
    # Times a failed item is moved to the back of the queue for a later
    # attempt, after AUTO_RETRY_COUNT in-process retries are exhausted.
    QUEUE_ERROR_RETRIES: int = 2

    # --- Cookies ---
    COOKIES_FROM_BROWSER: str = ""
    COOKIES_AUTO_REFRESH: bool = False
    COOKIES_LAST_IMPORTED: str = ""

    # --- Content selection ---
    SPONSORBLOCK_CATEGORIES: List[str] = field(default_factory=list)
    CHAPTERS_MODE: str = "embed"
    WRITE_SUBS: bool = False
    SUB_LANGS: str = "en"
    WRITE_AUTO_SUBS: bool = False
    CONVERT_SUBS_TO_SRT: bool = False
    PLAYLIST_REVERSE: bool = False
    PLAYLIST_ITEMS: str = ""
    DATEAFTER: str = ""
    CLIP_START: str = ""
    CLIP_END: str = ""
    LIVE_FROM_START: bool = False

    # --- Output ---
    ENABLE_ARCHIVE: bool = False
    ORGANIZE_BY_UPLOADER: bool = False
    FILENAME_FORMAT: str = "default"
    CUSTOM_FILENAME_TEMPLATE: str = ""
    VIDEO_FORMAT: str = ".mkv"

    # --- Post-processing ---
    AUDIO_NORMALIZE: bool = False
    ADD_METADATA: bool = True
    CROP_AUDIO_COVERS: bool = True
    CUSTOM_FFMPEG_ARGS: str = ""
    YT_MUSIC_METADATA: bool = False

    # --- Thumbnails ---
    WRITE_THUMBNAIL: bool = False
    CONVERT_THUMBNAILS: bool = True
    THUMBNAIL_FORMAT: str = "png"
    EMBED_THUMBNAIL: bool = True

    # --- yt-dlp passthrough ---
    # Parsed with shlex and appended after all built-in flags, so a user can
    # override any default.
    EXTRA_YTDLP_ARGS: str = "--sleep-interval 15 --max-sleep-interval 20"
    # yt-dlp periodically has to deprecate individual player clients faster
    # than app releases can track, so this is a preference, not a constant.
    YOUTUBE_PLAYER_CLIENT: str = "auto"

    # --- HLS ---
    # Off by default: forcing HLS caps quality wherever DASH offers a taller
    # ladder. Opt in per-domain for sites that only serve usable HLS.
    PREFER_HLS: bool = False
    HLS_PREFERRED_DOMAINS: List[str] = field(default_factory=list)

    # --- Diagnostics / UX ---
    LOG_THUMBNAILS: bool = False
    MAX_LOG_LINES: int = MAX_LOG_LINES
    CONFIRM_ON_QUIT: bool = True

    # --- Nested ---
    SPOTDL: SpotDLSettings = field(default_factory=SpotDLSettings)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __post_init__(self) -> None:
        self.BASE_DIR = Path(self.BASE_DIR).resolve()
        self.INTERNAL_DIR = (self.BASE_DIR / "_internal").resolve()
        self.CACHE_DIR = (self.BASE_DIR / "cache").resolve()
        self.CONFIG_PATH = (self.BASE_DIR / "config.json").resolve()
        self.QUEUE_PATH = (self.BASE_DIR / "queue.json").resolve()
        self.COOKIES_PATH = (self.BASE_DIR / "cookies.txt").resolve()
        self.ARCHIVE_PATH = (self.BASE_DIR / "archive.txt").resolve()

        for d in (self.DOWNLOADS_DIR, self.INTERNAL_DIR, self.CACHE_DIR):
            try:
                ensure_dir(d)
            except OSError as exc:
                log.warning("Could not create %s: %s", d, exc)

        self._resolve_binaries()
        self._refresh_templates()
        self.load_config()

    def _resolve_binaries(self) -> None:
        """Resolve helper binaries: env override, then PATH, then bundled.

        Env overrides exist so a packaged build can be pointed at
        system/toolbox binaries without editing config.json.
        """
        self.YT_DLP_PATH = resolve_tool(
            "YTGET_YT_DLP_PATH",
            self.BASE_DIR / executable_name("yt-dlp"),
            executable_name("yt-dlp"),
        )
        self.FFMPEG_PATH = resolve_tool(
            "YTGET_FFMPEG_PATH",
            self.BASE_DIR / executable_name("ffmpeg"),
            executable_name("ffmpeg"),
        )
        self.FFPROBE_PATH = resolve_tool(
            "YTGET_FFPROBE_PATH",
            self.BASE_DIR / executable_name("ffprobe"),
            executable_name("ffprobe"),
        )
        self.PHANTOMJS_PATH = resolve_tool(
            "YTGET_PHANTOMJS_PATH",
            self.BASE_DIR / executable_name("phantomjs"),
            executable_name("phantomjs"),
        )
        self.DENO_PATH = resolve_tool(
            "YTGET_DENO_PATH",
            self.BASE_DIR / executable_name("deno"),
            executable_name("deno"),
        )

    def _refresh_templates(self) -> None:
        self.OUTPUT_TEMPLATE = str(self.DOWNLOADS_DIR / DEFAULT_TITLE_TEMPLATE)
        self.PLAYLIST_TEMPLATE = str(self.DOWNLOADS_DIR / DEFAULT_PLAYLIST_TEMPLATE)

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------

    @property
    def thumb_cache_dir(self) -> Path:
        return self.CACHE_DIR / "thumbs"

    def has_cookies_file(self) -> bool:
        return is_usable_file(self.COOKIES_PATH)

    def has_custom_ca(self) -> bool:
        return is_usable_file(self.CUSTOM_CA_CERT)

    def archive_target(self) -> Path | None:
        """Archive path, or None when it is unusable.

        Returning None (rather than a bare Path) is what stops an empty
        setting from becoming `--download-archive .`.
        """
        if not self.ENABLE_ARCHIVE:
            return None
        p = Path(self.ARCHIVE_PATH)
        if str(p) in ("", "."):
            return None
        try:
            if not p.exists():
                p.parent.mkdir(parents=True, exist_ok=True)
                p.touch()
        except OSError as exc:
            log.warning("Archive file unusable (%s): %s", p, exc)
            return None
        return p

    def get_format_for_resolution(self, height: int, audio: str = "bestaudio") -> str:
        return video_chain(height, audio=audio)

    @staticmethod
    def ensure_format_fallback(fmt: str) -> str:
        return ensure_best_fallback(fmt)

    def resolve_format_code(self, code: str) -> str:
        """Normalise whatever the UI handed us into a real yt-dlp selector.

        Accepts a preset label, a bare "1080p" token, or an already-valid
        selector string.
        """
        import re

        code = str(code or "")
        if code in self.RESOLUTIONS:
            return self.RESOLUTIONS[code]
        m = re.fullmatch(r"(\d{3,4})p", code.strip())
        if m:
            return self.get_format_for_resolution(int(m.group(1)))
        return code

    def set_download_path(self, path: Path) -> None:
        """The only correct way to change the download folder.

        Assigning DOWNLOADS_DIR directly leaves OUTPUT_TEMPLATE and
        PLAYLIST_TEMPLATE pointing at the previous folder and skips the mkdir.
        """
        self.DOWNLOADS_DIR = Path(path).expanduser().resolve()
        ensure_dir(self.DOWNLOADS_DIR)
        self._refresh_templates()
        self.save_config()

    def apply(self, values: Mapping[str, Any]) -> None:
        """Bulk-apply a dict of settings (used by the dialogs).

        DOWNLOADS_DIR is routed through set_download_path so templates stay
        consistent no matter which path the value arrives by.
        """
        download_dir = values.get("DOWNLOADS_DIR")

        for key, value in values.items():
            if key in ("DOWNLOADS_DIR", "SPOTDL"):
                continue
            if not hasattr(self, key):
                log.debug("Ignoring unknown setting %r", key)
                continue
            setattr(self, key, value)

        spotdl = values.get("SPOTDL")
        if isinstance(spotdl, SpotDLSettings):
            self.SPOTDL = spotdl
        elif isinstance(spotdl, dict):
            self.SPOTDL = SpotDLSettings.from_dict(spotdl)

        self._sanitise()

        if download_dir:
            self.set_download_path(Path(download_dir))
        else:
            self._refresh_templates()

    def _sanitise(self) -> None:
        for key, validator in _VALIDATORS.items():
            try:
                setattr(self, key, validator(getattr(self, key)))
            except (TypeError, ValueError):
                pass
        self.SPOTDL.normalise()

        # An empty cookies/archive field must fall back to the canonical
        # location rather than becoming Path(".").
        if str(self.COOKIES_PATH) in ("", "."):
            self.COOKIES_PATH = self.BASE_DIR / "cookies.txt"
        if str(self.ARCHIVE_PATH) in ("", "."):
            self.ARCHIVE_PATH = self.BASE_DIR / "archive.txt"

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {k: getattr(self, k) for k in _PLAIN_KEYS}
        data.update({k: str(getattr(self, k)) for k in _PATH_KEYS})
        data["SPOTDL"] = self.SPOTDL.to_dict()
        data["_schema"] = self.VERSION
        return data

    def save_config(self) -> bool:
        """Write config.json atomically.

        A plain `open(..., "w")` truncates first, so a crash or full disk
        mid-write left a zero-length or half-written config that failed to
        parse on next launch and silently reset every preference. Writing to a
        temp file in the same directory and then `os.replace` makes the
        swap atomic on both POSIX and Windows.
        """
        payload = json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
        tmp_path: str | None = None
        try:
            self.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self.CONFIG_PATH.parent),
                prefix=".config-",
                suffix=".tmp",
            )
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, self.CONFIG_PATH)
            tmp_path = None
            return True
        except OSError as exc:
            log.error("Failed to save config: %s", exc)
            return False
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    # Backwards-compatible alias; MainWindow previously probed for `save`.
    save = save_config

    def load_config(self) -> None:
        if not self.CONFIG_PATH.is_file():
            self._sanitise()
            return

        try:
            raw = self.CONFIG_PATH.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            log.error("Config unreadable, keeping defaults: %s", exc)
            self._quarantine_config()
            self._sanitise()
            return

        if not isinstance(data, dict):
            log.error("Config root is %s, expected object", type(data).__name__)
            self._sanitise()
            return

        for key in _PLAIN_KEYS:
            if key in data:
                setattr(self, key, _coerce(data[key], getattr(self, key)))

        spotdl = data.get("SPOTDL")
        if isinstance(spotdl, dict):
            self.SPOTDL = SpotDLSettings.from_dict(spotdl)

        # Download dir first: templates depend on it.
        dl = data.get("DOWNLOADS_DIR")
        if dl:
            candidate = Path(str(dl)).expanduser()
            try:
                ensure_dir(candidate)
                self.DOWNLOADS_DIR = candidate.resolve()
            except OSError as exc:
                log.warning(
                    "Saved download dir %s unusable (%s); keeping %s",
                    candidate, exc, self.DOWNLOADS_DIR,
                )

        # Binaries: only honour a saved path that still resolves, so a
        # relocated/uninstalled tool falls back to PATH discovery instead of
        # pinning a dead path forever.
        for key in ("YT_DLP_PATH", "FFMPEG_PATH", "FFPROBE_PATH",
                    "PHANTOMJS_PATH", "DENO_PATH"):
            value = data.get(key)
            if value and Path(str(value)).is_file():
                setattr(self, key, Path(str(value)))

        # Cookies/archive may legitimately not exist yet (archive is created
        # on demand), so only the obviously-bogus values are rejected.
        for key in ("COOKIES_PATH", "ARCHIVE_PATH"):
            value = str(data.get(key) or "").strip()
            if value and value != ".":
                setattr(self, key, Path(value))

        self._sanitise()
        self._refresh_templates()

    def _quarantine_config(self) -> None:
        """Move a corrupt config aside so the user can inspect it."""
        try:
            backup = self.CONFIG_PATH.with_suffix(".json.corrupt")
            os.replace(self.CONFIG_PATH, backup)
            log.warning("Corrupt config moved to %s", backup)
        except OSError:
            pass


def _coerce(value: Any, current: Any) -> Any:
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
        return list(value) if isinstance(value, list) else ([value] if value else [])
    if isinstance(current, str):
        return "" if value is None else str(value)
    return value
