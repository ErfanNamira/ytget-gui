# File: ytget_gui/workers/fetch_core.py
"""Shared metadata fetching via yt-dlp.

TitleFetcher (one-shot) and TitleFetchQueue (serial) both delegate here so
command construction, cookie refresh and JSON parsing exist once.
"""

from __future__ import annotations

import json
import logging
from ytget_gui.utils.cli_args import split_arguments, parse_ytdlp_args
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ytget_gui.utils.paths import is_usable_file
from ytget_gui.utils.validators import is_spotify_url, is_youtube_url
from ytget_gui.workers import cookies as cookie_manager
from ytget_gui.workers import proc, ssl_utils

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECS = 120
SOCKET_TIMEOUT_SECS = 15

CANCELLED = "Cancelled"


class MetadataError(Exception):
    """yt-dlp output could not be turned into usable metadata."""


@dataclass(frozen=True)
class Metadata:
    title: str
    video_id: str
    thumb_url: str
    is_playlist: bool
    duration: Optional[float] = None
    uploader: str = ""
    entry_count: Optional[int] = None
    # Largest advertised size per video height, plus the best audio-only
    # size, taken from the same --dump-single-json output. The selected
    # format is only known to the queue, so the raw numbers are carried
    # here and combined by formats.estimate_download_size().
    video_sizes: Optional[Dict[int, int]] = None
    audio_size: Optional[int] = None


@dataclass(frozen=True)
class FetchResult:
    metadata: Optional[Metadata]
    error: Optional[str]
    cookies_path: Optional[Path]
    warning: Optional[str]

    @property
    def ok(self) -> bool:
        return self.metadata is not None and self.error is None

    @property
    def cancelled(self) -> bool:
        return self.error == CANCELLED


# --------------------------------------------------------------------------
# Spotify short-circuit. yt-dlp cannot extract open.spotify.com; SpotDLWorker
# handles those, so callers show a placeholder title instead of a hard error.
# --------------------------------------------------------------------------

_SPOTIFY_KINDS = ("track", "album", "playlist", "artist", "show", "episode")
_SPOTIFY_MULTI = ("/playlist/", "/album/", "/artist/", "/show/")


def spotify_placeholder_title(url: str) -> str:
    lowered = (url or "").lower()
    for kind in _SPOTIFY_KINDS:
        if f"/{kind}/" in lowered:
            return f"Spotify {kind.capitalize()}"
    return "Spotify Link"


# --------------------------------------------------------------------------
# Cookie refresh
# --------------------------------------------------------------------------


def _refresh_needed(settings) -> bool:
    return bool(
        settings is not None
        and getattr(settings, "COOKIES_AUTO_REFRESH", False)
        and getattr(settings, "COOKIES_FROM_BROWSER", "")
    )


def maybe_refresh_cookies(
    settings, cookies_path: Optional[Path]
) -> Tuple[Optional[Path], Optional[str]]:
    """Best-effort refresh. Never raises; a warning is non-fatal."""
    if not _refresh_needed(settings):
        return cookies_path, None

    try:
        ok, message = cookie_manager.refresh_before_download(settings)
    except Exception as exc:  # noqa: BLE001
        return cookies_path, f"Cookies refresh: {exc}"

    if not ok:
        return cookies_path, f"Cookies refresh: {message}"

    exported = getattr(settings, "COOKIES_PATH", None)
    if not exported or str(exported) in ("", "."):
        exported = Path(getattr(settings, "DATA_DIR", Path("."))) / "cookies.txt"

    cookie_manager.record_refresh(settings)
    return Path(exported), None


def maybe_refresh_cookies_interruptible(
    settings,
    cookies_path: Optional[Path],
    cancel_event: Optional[threading.Event] = None,
    poll_interval: float = 0.2,
) -> Tuple[Optional[Path], Optional[str], bool]:
    """As maybe_refresh_cookies, but stops *waiting* when cancelled.

    browser_cookie3 reads OS keychains in-process, so there is no subprocess to
    kill and a stuck native call cannot be aborted. What this does guarantee is
    that a stop()/cancel() returns promptly instead of blocking for however
    long that call takes: the work runs on a daemon thread whose result is
    discarded if it arrives late.

    Returns (cookies_path, warning, was_cancelled).
    """
    if not _refresh_needed(settings):
        return cookies_path, None, False

    holder: Dict[str, Any] = {}

    def worker() -> None:
        try:
            holder["result"] = maybe_refresh_cookies(settings, cookies_path)
        except Exception as exc:  # noqa: BLE001
            holder["error"] = exc

    thread = threading.Thread(target=worker, daemon=True, name="cookie-refresh")
    thread.start()

    while thread.is_alive():
        if cancel_event is not None and cancel_event.is_set():
            return cookies_path, None, True
        thread.join(timeout=poll_interval)

    if "error" in holder:
        return cookies_path, f"Cookies refresh: {holder['error']}", False

    result = holder.get("result")
    if result is None:
        return cookies_path, None, False
    return result[0], result[1], False


# --------------------------------------------------------------------------
# Command construction
# --------------------------------------------------------------------------


def build_command(
    url: str,
    yt_dlp_path: Path,
    ffmpeg_dir: Path,
    cookies_path: Optional[Path],
    proxy_url: str,
    settings,
    *,
    cookies_from_browser: str = "",
    cookies_profile: str = "",
    flat_playlist: bool = True,
) -> List[str]:
    cmd: List[str] = [
        str(yt_dlp_path),
        "--ignore-config",
        "--ffmpeg-location", str(ffmpeg_dir),
        "--skip-download",
        "--dump-single-json",
        "--ignore-errors",
        "--no-warnings",
        "--no-progress",
        "--socket-timeout", str(SOCKET_TIMEOUT_SECS),
    ]
    if flat_playlist:
        # Without this, fetching a 500-item playlist title extracts every
        # entry, taking minutes for a single queue card.
        cmd.append("--flat-playlist")

    _verify, ssl_args, _env = ssl_utils.resolve_ssl_config(settings)
    cmd.extend(ssl_args)

    browser = cookies_from_browser or str(
        getattr(settings, "COOKIES_FROM_BROWSER", "") or ""
    )
    if browser:
        spec = f"{browser}:{cookies_profile}" if cookies_profile else browser
        cmd.extend(["--cookies-from-browser", spec])
    elif is_usable_file(cookies_path):
        # is_usable_file rejects Path(".") -- an empty cookies setting used to
        # serialise to "." and produce `--cookies .`, which yt-dlp rejects
        # outright, breaking every metadata fetch.
        cmd.extend(["--cookies", str(cookies_path)])

    if proxy_url:
        cmd.extend(["--proxy", proxy_url])

    player_client = str(getattr(settings, "YOUTUBE_PLAYER_CLIENT", "auto") or "auto")
    if player_client and player_client != "auto" and is_youtube_url(url):
        cmd.extend(["--extractor-args", f"youtube:player_client={player_client}"])

    # Download-only passthrough flags must never execute while merely adding a URL.
    # Network/auth/client options above are shared explicitly.

    # URL last: yt-dlp treats a bare token after the URL as another URL, and
    # the previous build appended flags after it, so extra args were parsed as
    # additional download targets.
    cmd.extend(["--", url])
    return cmd


def parse_extra_args(raw: str) -> List[str]:
    """Compatibility wrapper for ffmpeg argument lists."""
    return split_arguments(raw)


def build_env(settings) -> Dict[str, str]:
    return proc.tool_env(settings)


# --------------------------------------------------------------------------
# Execution
# --------------------------------------------------------------------------


def run_yt_dlp(
    cmd: List[str],
    env: Dict[str, str],
    timeout: int = DEFAULT_TIMEOUT_SECS,
    on_process_started: Optional[Callable[[subprocess.Popen], None]] = None,
) -> Tuple[int, str, str]:
    """Run yt-dlp, returning (returncode, stdout, stderr).

    Uses Popen rather than subprocess.run so the live process is handed to the
    caller *before* we block on it. subprocess.run exposes no handle, so a
    stuck fetch could not be interrupted and a "stopped" queue (or app
    shutdown) hung for the full timeout.

    Raises subprocess.TimeoutExpired on timeout.
    """
    process = proc.spawn(cmd, env=env, merge_stderr=False)

    if on_process_started is not None:
        try:
            on_process_started(process)
        except Exception as exc:  # noqa: BLE001
            log.debug("on_process_started callback failed: %s", exc)

    try:
        stdout_raw, stderr_raw = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.terminate_tree(process)
        raise

    return (
        process.returncode,
        (stdout_raw or b"").decode("utf-8", errors="replace"),
        (stderr_raw or b"").decode("utf-8", errors="replace"),
    )


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def _looks_like_playlist(info: Dict[str, Any]) -> bool:
    """Decide whether one yt-dlp info dict describes a playlist.

    Every test is on truthiness, never key presence. yt-dlp sets `playlist`,
    `playlist_index`, `playlist_title` and friends to None on a standalone
    video, so `"playlist_index" in info` is True for every ordinary watch URL
    -- which is why single videos were being labelled as playlists.
    """
    if str(info.get("_type") or "") in ("playlist", "multi_video"):
        return True
    if info.get("entries"):
        return True
    if info.get("n_entries"):
        return True
    return bool(info.get("playlist_index")) or bool(info.get("playlist_title"))


def _best_thumbnail(info: Dict[str, Any]) -> str:
    direct = info.get("thumbnail")
    if direct:
        return str(direct)

    thumbs = info.get("thumbnails")
    if not isinstance(thumbs, list):
        return ""

    def rank(t: Dict[str, Any]) -> tuple:
        return (
            t.get("preference") or 0,
            t.get("width") or 0,
            t.get("height") or 0,
        )

    candidates = [t for t in thumbs if isinstance(t, dict) and t.get("url")]
    if not candidates:
        return ""
    return str(max(candidates, key=rank).get("url", ""))


def metadata_payload(md: "Metadata") -> Dict[str, Any]:
    """Serialise Metadata for the Qt signal.

    A dict rather than a widening positional signature: the previous
    five-argument signal had nowhere to put duration or uploader, so both
    were parsed and then dropped before the card could show them.
    """
    return {
        "title": md.title,
        "video_id": md.video_id,
        "thumb_url": md.thumb_url,
        "is_playlist": md.is_playlist,
        "duration": md.duration,
        "uploader": md.uploader,
        "entry_count": md.entry_count,
        "video_sizes": dict(md.video_sizes or {}),
        "audio_size": md.audio_size,
    }


def _size_of(fmt: Dict[str, Any]) -> Optional[int]:
    """Exact size when yt-dlp knows it, otherwise its own estimate."""
    for key in ("filesize", "filesize_approx"):
        value = fmt.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
    # Some extractors only report a bitrate; tbr is in kbit/s.
    tbr = fmt.get("tbr")
    duration = fmt.get("_duration")
    if isinstance(tbr, (int, float)) and isinstance(duration, (int, float)):
        if tbr > 0 and duration > 0:
            return int(tbr * 125 * duration)
    return None


def parse_sizes(info: Dict[str, Any]) -> Tuple[Dict[int, int], Optional[int]]:
    """Map video height -> bytes, and the best audio-only size.

    Progressive formats (audio muxed into the video stream) are recorded
    with an audio size of None so the caller does not double-count them.
    """
    formats = info.get("formats")
    if not isinstance(formats, list):
        return {}, None
    duration = info.get("duration")

    video_sizes: Dict[int, int] = {}
    audio_size: Optional[int] = None
    for fmt in formats:
        if not isinstance(fmt, dict):
            continue
        if isinstance(duration, (int, float)):
            fmt = {**fmt, "_duration": duration}
        size = _size_of(fmt)
        if size is None:
            continue
        has_video = str(fmt.get("vcodec") or "none") != "none"
        has_audio = str(fmt.get("acodec") or "none") != "none"
        height = fmt.get("height")
        if has_video and isinstance(height, (int, float)) and height > 0:
            key = int(height)
            # yt-dlp picks the highest-bitrate stream for a height, which
            # is the largest one.
            if size > video_sizes.get(key, 0):
                video_sizes[key] = size
        elif has_audio and not has_video:
            if audio_size is None or size > audio_size:
                audio_size = size
    return video_sizes, audio_size


def parse_metadata(stdout_text: str) -> Metadata:
    output = (stdout_text or "").strip()
    if not output:
        raise MetadataError("No metadata received from yt-dlp")

    infos: List[Dict[str, Any]] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            infos.append(parsed)

    if not infos:
        raise MetadataError("Could not parse yt-dlp metadata (no JSON objects)")

    is_playlist = any(_looks_like_playlist(info) for info in infos)

    playlist_title = next(
        (str(info["playlist_title"]) for info in infos if info.get("playlist_title")),
        None,
    )

    head = infos[0]
    title = (
        playlist_title
        if (is_playlist and playlist_title)
        else str(head.get("title") or "Unknown Title")
    )

    entry_count: Optional[int] = None
    entries = head.get("entries")
    if isinstance(entries, list):
        entry_count = len(entries)
    elif head.get("n_entries"):
        try:
            entry_count = int(head["n_entries"])
        except (TypeError, ValueError):
            entry_count = None
    elif is_playlist and len(infos) > 1:
        # --flat-playlist prints one JSON object per entry, so the object count
        # is the entry count when no explicit total was given.
        entry_count = len(infos)

    duration = head.get("duration")
    # Playlists are deliberately skipped: --flat-playlist carries no
    # per-entry formats, and summing a whole playlist would need one
    # yt-dlp call per entry.
    video_sizes, audio_size = ({}, None) if is_playlist else parse_sizes(head)
    return Metadata(
        title=title,
        video_id=str(head.get("id") or ""),
        thumb_url=_best_thumbnail(head),
        is_playlist=is_playlist,
        duration=float(duration) if isinstance(duration, (int, float)) else None,
        uploader=str(head.get("uploader") or head.get("channel") or ""),
        entry_count=entry_count,
        video_sizes=video_sizes or None,
        audio_size=audio_size,
    )


# --------------------------------------------------------------------------
# High-level entry point
# --------------------------------------------------------------------------


def fetch_metadata(
    url: str,
    yt_dlp_path: Path,
    ffmpeg_dir: Path,
    cookies_path: Optional[Path],
    proxy_url: str,
    settings=None,
    *,
    cookies_from_browser: str = "",
    cookies_profile: str = "",
    timeout: int = DEFAULT_TIMEOUT_SECS,
    on_process_started: Optional[Callable[[subprocess.Popen], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> FetchResult:
    """Synchronous metadata fetch. Emits no Qt signals."""
    if is_spotify_url(url):
        lowered = (url or "").lower()
        return FetchResult(
            metadata=Metadata(
                title=spotify_placeholder_title(url),
                video_id="",
                thumb_url="",
                is_playlist=any(kind in lowered for kind in _SPOTIFY_MULTI),
            ),
            error=None,
            cookies_path=cookies_path,
            warning=None,
        )

    updated_path, warning, was_cancelled = maybe_refresh_cookies_interruptible(
        settings, cookies_path, cancel_event=cancel_event
    )
    if updated_path is not None:
        cookies_path = updated_path

    if was_cancelled or (cancel_event is not None and cancel_event.is_set()):
        return FetchResult(None, CANCELLED, cookies_path, warning)

    if not Path(yt_dlp_path).is_file():
        return FetchResult(
            None,
            f"yt-dlp not found at {yt_dlp_path}. "
            "Install it via Help \u203a Check for Updates.",
            cookies_path,
            warning,
        )

    cmd = build_command(
        url,
        yt_dlp_path,
        ffmpeg_dir,
        cookies_path,
        proxy_url,
        settings,
        cookies_from_browser=cookies_from_browser,
        cookies_profile=cookies_profile,
    )

    try:
        returncode, stdout, stderr = run_yt_dlp(
            cmd,
            build_env(settings),
            timeout=timeout,
            on_process_started=on_process_started,
        )
    except subprocess.TimeoutExpired:
        return FetchResult(
            None, f"Timed out after {timeout}s fetching metadata", cookies_path, warning
        )
    except FileNotFoundError:
        return FetchResult(
            None, f"yt-dlp not found at {yt_dlp_path}", cookies_path, warning
        )
    except OSError as exc:
        return FetchResult(None, f"Could not run yt-dlp: {exc}", cookies_path, warning)

    if cancel_event is not None and cancel_event.is_set():
        return FetchResult(None, CANCELLED, cookies_path, warning)

    # A negative code means killed by signal, i.e. our own cancellation.
    if returncode is not None and returncode < 0:
        return FetchResult(None, CANCELLED, cookies_path, warning)

    # --ignore-errors makes yt-dlp exit non-zero for a partially-extracted
    # playlist while still printing usable JSON, so parse before judging.
    if stdout.strip():
        try:
            return FetchResult(parse_metadata(stdout), None, cookies_path, warning)
        except MetadataError as exc:
            if returncode == 0:
                return FetchResult(None, str(exc), cookies_path, warning)

    message = (stderr or "").strip() or f"yt-dlp exited with code {returncode}"
    return FetchResult(None, _condense_error(message), cookies_path, warning)


def _condense_error(text: str) -> str:
    """Reduce a multi-line yt-dlp stderr dump to the useful line."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in lines:
        if "ERROR:" in line:
            return line.split("ERROR:", 1)[1].strip() or line
    return lines[-1] if lines else text
