# File: ytget_gui/workers/fetch_core.py
"""
Shared implementation for title/metadata fetching via yt-dlp.

TitleFetcher (single-shot QObject) and TitleFetchQueue (serial queue) both
delegate to the functions in this module so the subprocess-building,
cookie-refresh, and JSON-parsing logic exists in exactly one place.
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ytget_gui.settings import AppSettings
from ytget_gui.workers import cookies as CookieManager
from ytget_gui.workers import ssl_utils

_SPOTIFY_RE = re.compile(r"https?://(open\.)?spotify\.com/", re.IGNORECASE)
_SPOTIFY_KIND_RE = re.compile(r"spotify\.com/(?:[a-z-]+/)?([a-z]+)/", re.IGNORECASE)

DEFAULT_TIMEOUT_SECS = 120
SOCKET_TIMEOUT_SECS = 15


class MetadataError(Exception):
    """Raised when yt-dlp output can't be turned into usable metadata."""


@dataclass
class Metadata:
    title: str
    video_id: str
    thumb_url: str
    is_playlist: bool


# ── Spotify short-circuit ────────────────────────────────────────────────
# yt-dlp cannot handle open.spotify.com URLs and will be blocked. Callers
# should check this first and emit a placeholder title; SpotDLWorker
# handles the actual download/metadata later.

def is_spotify_url(url: str) -> bool:
    return bool(_SPOTIFY_RE.search(url))


def spotify_placeholder_title(url: str) -> str:
    m = _SPOTIFY_KIND_RE.search(url)
    kind = m.group(1).capitalize() if m else "Link"
    return f"Spotify {kind}"


# ── Cookies ───────────────────────────────────────────────────────────────

def maybe_refresh_cookies(settings: Optional[AppSettings], cookies_path: Optional[Path]) -> Tuple[Optional[Path], Optional[str]]:
    """
    Best-effort cookie refresh. Returns (possibly-updated cookies_path, warning_message).
    Never raises - callers should proceed with metadata fetching regardless.
    """
    if settings is None:
        return cookies_path, None
    if not getattr(settings, "COOKIES_AUTO_REFRESH", False):
        return cookies_path, None
    if not getattr(settings, "COOKIES_FROM_BROWSER", ""):
        return cookies_path, None

    try:
        ok, msg = CookieManager.refresh_before_download(settings)
    except Exception as e:
        return cookies_path, f"Cookies refresh: {e}"

    if not ok:
        return cookies_path, f"Cookies refresh: {msg}"

    try:
        exported_path = getattr(settings, "COOKIES_PATH", None)
        if not exported_path or str(exported_path) == "":
            exported_path = Path(getattr(settings, "BASE_DIR", Path("."))) / "cookies.txt"
        exported_path = Path(exported_path)

        settings.COOKIES_PATH = exported_path
        settings.COOKIES_LAST_IMPORTED = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        if hasattr(settings, "save_config"):
            settings.save_config()
        return exported_path, None
    except Exception:
        # Refresh itself succeeded; persisting the timestamp/path did not.
        # Fall back to whatever settings currently reports.
        return getattr(settings, "COOKIES_PATH", cookies_path), None


# ── Command / environment ────────────────────────────────────────────────

def build_command(
    url: str,
    yt_dlp_path: Path,
    ffmpeg_dir: Path,
    cookies_path: Optional[Path],
    proxy_url: str,
    settings: Optional[AppSettings],
    cookies_from_browser: str = "",
    cookies_profile: str = "",
) -> List[str]:
    cmd: List[str] = [
        str(yt_dlp_path),
        "--ffmpeg-location", str(ffmpeg_dir),
        "--skip-download",
        "--print-json",
        "--ignore-errors",
        "--no-warnings",
        "--flat-playlist",
        "--socket-timeout", str(SOCKET_TIMEOUT_SECS),
    ]

    _verify, ytdlp_ssl_args, _ssl_env = ssl_utils.resolve_ssl_config(settings)
    cmd.extend(ytdlp_ssl_args)

    cmd.append(url)

    cfb = cookies_from_browser or (getattr(settings, "COOKIES_FROM_BROWSER", "") if settings is not None else "")
    if cfb:
        if cookies_profile:
            cmd.extend(["--cookies-from-browser", f"{cfb}:{cookies_profile}"])
        else:
            cmd.extend(["--cookies-from-browser", cfb])
    elif cookies_path and Path(cookies_path).exists() and Path(cookies_path).stat().st_size > 0:
        cmd.extend(["--cookies", str(cookies_path)])

    if proxy_url:
        cmd.extend(["--proxy", proxy_url])

    return cmd


def build_env(settings: Optional[AppSettings]) -> Dict[str, str]:
    env = os.environ.copy()

    try:
        if settings is not None:
            extra_paths = [str(settings.INTERNAL_DIR), str(settings.BASE_DIR)]
            ph = getattr(settings, "PHANTOMJS_PATH", None)
            if ph and Path(ph).exists():
                extra_paths.append(str(Path(ph).parent))

            cur_path = env.get("PATH", "")
            existing = set(cur_path.split(os.pathsep)) if cur_path else set()
            prefix_parts = []
            for p in reversed(extra_paths):
                if p and p not in existing:
                    prefix_parts.append(p)
                    existing.add(p)
            if prefix_parts:
                env["PATH"] = os.pathsep.join(prefix_parts) + (os.pathsep + cur_path if cur_path else "")

            if os.name == "nt" and not env.get("PATHEXT"):
                env["PATHEXT"] = ".COM;.EXE;.BAT;.CMD"
    except Exception:
        pass

    try:
        _verify, _ssl_args, ssl_env = ssl_utils.resolve_ssl_config(settings)
        env.update(ssl_env)
    except Exception:
        pass

    return env


def get_startupinfo():
    if not platform.system().lower().startswith("win"):
        return None
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return si
    except Exception:
        return None


# ── Subprocess execution ─────────────────────────────────────────────────

def run_yt_dlp(
    cmd: List[str],
    env: Dict[str, str],
    timeout: int = DEFAULT_TIMEOUT_SECS,
    on_process_started: Optional[Callable[[subprocess.Popen], None]] = None,
) -> Tuple[int, str, str]:
    """
    Runs yt-dlp and returns (returncode, stdout_text, stderr_text).
    Always reads raw bytes and decodes with 'replace' so odd terminal
    encodings (esp. on Windows) never raise UnicodeDecodeError.

    Unlike a plain subprocess.run(), this uses Popen so the live process
    object can be handed back to the caller *before* we block on it (via
    on_process_started). That's what lets an external stop()/cancel() call
    actually kill the process instead of only being able to wait out the
    full timeout - subprocess.run() blocks with no handle exposed at all,
    which previously meant a stuck/slow fetch could not be interrupted and
    would keep a "stopped" queue (and app shutdown) hanging for up to
    `timeout` seconds.

    Raises subprocess.TimeoutExpired on timeout - caller handles it.
    Raises FetchCancelled if on_process_started's caller kills the process
    out from under us before it exits naturally.
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        startupinfo=get_startupinfo(),
        env=env,
    )

    if on_process_started is not None:
        try:
            on_process_started(proc)
        except Exception:
            pass

    try:
        stdout_b, stderr_b = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass
        raise

    stdout = (stdout_b or b"").decode("utf-8", errors="replace")
    stderr = (stderr_b or b"").decode("utf-8", errors="replace")
    return proc.returncode, stdout, stderr


# ── Output parsing ───────────────────────────────────────────────────────

def parse_metadata(stdout_text: str) -> Metadata:
    output = (stdout_text or "").strip()
    if not output:
        raise MetadataError("No metadata received from yt-dlp")

    infos: List[Dict[str, Any]] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            infos.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not infos:
        raise MetadataError("Failed to parse metadata: no valid JSON objects")

    is_playlist = any(
        ("entries" in info) or ("playlist_index" in info) or ("playlist_title" in info)
        for info in infos
    )

    playlist_title = next((info.get("playlist_title") for info in infos if info.get("playlist_title")), None)

    representative = infos[0]
    video_id = representative.get("id") or ""
    thumb_url = representative.get("thumbnail") or ""
    title = playlist_title if (is_playlist and playlist_title) else (representative.get("title") or "Unknown Title")

    return Metadata(title=title, video_id=video_id, thumb_url=thumb_url, is_playlist=is_playlist)


# ── High-level entry point ───────────────────────────────────────────────

def fetch_metadata(
    url: str,
    yt_dlp_path: Path,
    ffmpeg_dir: Path,
    cookies_path: Optional[Path],
    proxy_url: str,
    settings: Optional[AppSettings] = None,
    cookies_from_browser: str = "",
    cookies_profile: str = "",
    timeout: int = DEFAULT_TIMEOUT_SECS,
    on_process_started: Optional[Callable[[subprocess.Popen], None]] = None,
) -> Tuple[Optional[Metadata], Optional[str], Optional[Path], Optional[str]]:
    """
    One-stop synchronous fetch. Returns:
        (metadata_or_None, error_message_or_None, updated_cookies_path, cookie_refresh_warning_or_None)

    A cookie-refresh warning is non-fatal - metadata fetching still proceeds
    and may succeed even if `cookie_refresh_warning` is set.

    `on_process_started`, if given, is called with the live subprocess.Popen
    as soon as it launches (before we block on it) so a caller running this
    on a background thread can stash the handle and kill() it from another
    thread to cancel a stuck/slow fetch on demand, instead of only being
    able to wait out the full `timeout`.

    Does NOT touch Qt signals - callers emit based on the returned tuple.
    Spotify URLs are NOT handled here; check is_spotify_url() first.
    """
    updated_cookies_path, refresh_warning = maybe_refresh_cookies(settings, cookies_path)
    if updated_cookies_path is not None:
        cookies_path = updated_cookies_path

    cmd = build_command(
        url, yt_dlp_path, ffmpeg_dir, cookies_path, proxy_url, settings,
        cookies_from_browser=cookies_from_browser, cookies_profile=cookies_profile,
    )
    env = build_env(settings)

    try:
        returncode, stdout, stderr = run_yt_dlp(cmd, env, timeout=timeout, on_process_started=on_process_started)
    except subprocess.TimeoutExpired:
        return None, f"Timeout while fetching metadata ({timeout} seconds)", cookies_path, refresh_warning
    except Exception as e:
        return None, f"Unexpected error: {e}", cookies_path, refresh_warning

    if returncode != 0:
        if returncode is not None and returncode < 0:
            return None, "Cancelled", cookies_path, refresh_warning
        return None, (stderr or "yt-dlp returned an error").strip(), cookies_path, refresh_warning

    try:
        metadata = parse_metadata(stdout)
    except MetadataError as e:
        return None, str(e), cookies_path, refresh_warning

    return metadata, None, cookies_path, refresh_warning
