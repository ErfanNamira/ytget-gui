# File: ytget_gui/workers/thumb_fetcher.py
"""Thumbnail fetching and caching.

Two paths: guess the ytimg CDN URL and confirm with a pooled HEAD request
(no subprocess, milliseconds), falling back to yt-dlp metadata extraction only
when that fails.
"""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, wait as futures_wait
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import parse_qs, urlparse

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException

try:
    from urllib3.util.retry import Retry
except ImportError:  # pragma: no cover
    Retry = None  # type: ignore[assignment]

from PySide6.QtCore import QObject, Signal

from ytget_gui.settings import AppSettings
from ytget_gui.utils.text import cache_key, url_digest
from ytget_gui.workers import cookies as cookie_manager
from ytget_gui.workers import proc, ssl_utils

log = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

# Best-first. maxres/sd do not exist for every video, hence the probe.
_YTIMG_CANDIDATES: Tuple[str, ...] = (
    "maxresdefault", "sddefault", "hqdefault", "mqdefault", "default",
)

# YouTube serves its grey "no thumbnail" placeholder with HTTP 200, so a 200 is
# not proof the resolution exists -- these exact byte lengths identify it.
_PLACEHOLDER_SIZES = frozenset({1097, 1120, 2088})

_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif")

_COOKIE_REFRESH_INTERVAL = 300.0
_cookie_lock = threading.Lock()
_last_cookie_refresh = 0.0


def _build_session() -> requests.Session:
    """Shared connection-pooled session.

    Thread-safe: urllib3's pools are, and nothing mutates session state after
    construction.
    """
    session = requests.Session()
    session.headers.update({"User-Agent": _USER_AGENT})
    if Retry is not None:
        retry = Retry(
            total=2, backoff_factor=0.3,
            status_forcelist=(500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "HEAD"}),
        )
        adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=retry)
    else:
        adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


_SESSION = _build_session()


def _extension_for(url: str, content_type: Optional[str]) -> str:
    match = re.search(r"\.([a-zA-Z0-9]{2,6})(?:[?#]|$)", url or "")
    if match:
        ext = match.group(1).lower()
        if ext in {"jpg", "jpeg", "png", "webp", "gif", "bmp", "avif"}:
            return ".jpg" if ext == "jpeg" else f".{ext}"
    ct = (content_type or "").lower()
    for needle, ext in (
        ("jpeg", ".jpg"), ("png", ".png"), ("webp", ".webp"),
        ("gif", ".gif"), ("avif", ".avif"),
    ):
        if needle in ct:
            return ext
    return ".jpg"


def extract_video_id(url: str) -> Optional[str]:
    try:
        parsed = urlparse(url or "")
    except ValueError:
        return None
    query = parse_qs(parsed.query)
    if query.get("v"):
        return query["v"][0]
    match = re.search(
        r"(?:youtu\.be/|youtube\.com/(?:embed/|v/|shorts/|live/))([A-Za-z0-9_-]{6,})",
        url or "",
    )
    return match.group(1) if match else None


def canonical_watch_url(url: str) -> str:
    """Strip playlist/index parameters so metadata extraction targets one video."""
    video_id = extract_video_id(url)
    if video_id and "youtu" in (url or ""):
        return f"https://www.youtube.com/watch?v={video_id}"
    return url or ""


class ThumbFetcher(QObject):
    """Fetch and cache one thumbnail.

    finished(url, path) reports an empty path on failure so callers can always
    clear their pending state on a single signal.
    """

    started = Signal(str)
    finished = Signal(str, str)
    error = Signal(str, str)

    def __init__(
        self,
        url: str,
        cache_dir: Path,
        settings: AppSettings,
        timeout: int = 20,
        cancel_event: Optional[threading.Event] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.url = url
        self.cache_dir = Path(cache_dir)
        self.settings = settings
        self.timeout = int(timeout)

        self._cancel = cancel_event or threading.Event()
        self._proc_lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None

    # ------------------------------------------------------------------
    # Cancellation
    # ------------------------------------------------------------------

    def request_cancel(self) -> None:
        """Stop as soon as possible. Safe from any thread.

        Kills the current yt-dlp subprocess if one is running. requests calls
        cannot be aborted mid-socket, but each is timeout-bounded.
        """
        self._cancel.set()
        with self._proc_lock:
            process = self._process
        proc.terminate_tree(process)

    def _cancelled(self) -> bool:
        return self._cancel.is_set()

    def _register_proc(self, process: subprocess.Popen) -> None:
        with self._proc_lock:
            self._process = process
        if self._cancelled():
            proc.terminate_tree(process)

    def _clear_proc(self) -> None:
        with self._proc_lock:
            self._process = None

    def _log(self, message: str) -> None:
        if getattr(self.settings, "LOG_THUMBNAILS", False):
            self.error.emit(self.url, message)
        else:
            log.debug("thumb %s: %s", self.url, message)

    # ------------------------------------------------------------------
    # Main flow
    # ------------------------------------------------------------------

    def run(self) -> None:
        self.started.emit(self.url)
        try:
            self.finished.emit(self.url, self._fetch() or "")
        except Exception as exc:  # noqa: BLE001 - a pool worker must not die
            log.exception("Thumbnail fetch crashed")
            self._log(f"Unexpected error: {exc}")
            self.finished.emit(self.url, "")

    def _fetch(self) -> Optional[str]:
        if self._cancelled():
            return None

        self._maybe_refresh_cookies()
        if self._cancelled():
            return None

        video_id = extract_video_id(self.url)
        thumb_url = self._probe_ytimg(video_id) if video_id else None

        if not thumb_url and not self._cancelled():
            extracted_url, extracted_id = self._extract_via_ytdlp()
            video_id = video_id or extracted_id
            thumb_url = extracted_url or (
                self._probe_ytimg(video_id) if video_id else None
            )
            if not thumb_url and video_id:
                thumb_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

        if self._cancelled():
            return None
        if not thumb_url:
            self._log("No thumbnail URL discovered")
            return None

        stem = cache_key(video_id or url_digest(self.url))
        target = self.cache_dir / f"{stem}{_extension_for(thumb_url, None)}"

        cached = self._existing_cache_entry(stem)
        if cached is not None:
            return str(cached)

        saved = self._download_via_requests(thumb_url, target)
        if saved is None and not self._cancelled():
            saved = self._download_via_ytdlp(target)

        if saved is None:
            self._log("Failed to download thumbnail")
            return None
        return str(saved)

    def _existing_cache_entry(self, stem: str) -> Optional[Path]:
        for ext in _IMAGE_EXTENSIONS:
            candidate = self.cache_dir / f"{stem}{ext}"
            try:
                if not (candidate.is_file() and candidate.stat().st_size > 0):
                    continue
            except OSError:
                continue
            if ext == ".avif":
                converted = self._convert_avif(candidate)
                return converted
            return candidate
        return None

    # ------------------------------------------------------------------
    # Cookie refresh (throttled process-wide)
    # ------------------------------------------------------------------

    def _maybe_refresh_cookies(self) -> None:
        s = self.settings
        if not (
            getattr(s, "COOKIES_AUTO_REFRESH", False)
            and getattr(s, "COOKIES_FROM_BROWSER", "")
        ):
            return

        # Exporting a browser cookie jar takes seconds and hits the OS keychain.
        # Doing it per thumbnail made a 20-item queue unusable.
        global _last_cookie_refresh
        now = time.monotonic()
        with _cookie_lock:
            if now - _last_cookie_refresh < _COOKIE_REFRESH_INTERVAL:
                return
            _last_cookie_refresh = now

        try:
            ok, message = cookie_manager.refresh_before_download(s)
        except Exception as exc:  # noqa: BLE001
            self._log(f"Cookie refresh error: {exc}")
            return
        if ok:
            cookie_manager.record_refresh(s)
        else:
            self._log(f"Cookie refresh failed: {message}")

    # ------------------------------------------------------------------
    # Fast path
    # ------------------------------------------------------------------

    def _request_kwargs(self) -> Dict[str, object]:
        verify, _args, _env = ssl_utils.resolve_ssl_config(self.settings)
        ssl_utils.maybe_suppress_insecure_warning(verify)
        kwargs: Dict[str, object] = {"verify": verify}
        proxy = (getattr(self.settings, "PROXY_URL", "") or "").strip()
        if proxy:
            kwargs["proxies"] = {"http": proxy, "https": proxy}
        return kwargs

    def _probe_ytimg(self, video_id: Optional[str]) -> Optional[str]:
        if not video_id:
            return None
        kwargs = self._request_kwargs()
        # (connect, read): a tight connect bound means an unreachable network
        # fails fast instead of burning the full read timeout per candidate.
        timeout = (3, min(self.timeout, 6) or 6)

        for name in _YTIMG_CANDIDATES:
            if self._cancelled():
                return None
            candidate = f"https://i.ytimg.com/vi/{video_id}/{name}.jpg"
            try:
                response = _SESSION.head(
                    candidate, timeout=timeout, allow_redirects=True, **kwargs
                )
            except RequestException:
                continue
            if response.status_code != 200:
                continue
            length = response.headers.get("Content-Length")
            if length:
                try:
                    if int(length) in _PLACEHOLDER_SIZES:
                        continue
                except ValueError:
                    pass
            return candidate
        return None

    # ------------------------------------------------------------------
    # Slow path
    # ------------------------------------------------------------------

    def _ytdlp_auth_args(self) -> List[str]:
        s = self.settings
        args: List[str] = []
        browser = getattr(s, "COOKIES_FROM_BROWSER", "") or ""
        if browser:
            args += ["--cookies-from-browser", browser]
        elif is_usable_file_safe(s.COOKIES_PATH):
            args += ["--cookies", str(s.COOKIES_PATH)]
        proxy = (getattr(s, "PROXY_URL", "") or "").strip()
        if proxy:
            args += ["--proxy", proxy]
        ffmpeg = Path(getattr(s, "FFMPEG_PATH", ""))
        if ffmpeg.is_file():
            args += ["--ffmpeg-location", str(ffmpeg.parent)]
        return args

    def _run_ytdlp(self, extra: Sequence[str], timeout: int) -> Optional[str]:
        binary = Path(getattr(self.settings, "YT_DLP_PATH", ""))
        if not binary.is_file():
            return None

        _verify, ssl_args, _env = ssl_utils.resolve_ssl_config(self.settings)
        cmd = [
            str(binary),
            "--no-warnings",
            "--skip-download",
            "--ignore-errors",
            *ssl_args,
            *self._ytdlp_auth_args(),
            *extra,
            # URL last: flags placed after it are parsed as extra download
            # targets, which is how the previous revision silently fetched
            # metadata for the wrong thing.
            canonical_watch_url(self.url),
        ]

        try:
            process = proc.spawn(cmd, env=proc.tool_env(self.settings), merge_stderr=False)
        except (OSError, subprocess.SubprocessError) as exc:
            self._log(f"Could not run yt-dlp: {exc}")
            return None

        self._register_proc(process)
        try:
            stdout_raw, stderr_raw = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.terminate_tree(process)
            self._log("yt-dlp timed out")
            return None
        finally:
            self._clear_proc()

        if self._cancelled():
            return None

        stdout = (stdout_raw or b"").decode("utf-8", errors="replace")
        if process.returncode != 0 and not stdout.strip():
            stderr = (stderr_raw or b"").decode("utf-8", errors="replace")
            self._log(f"yt-dlp exited {process.returncode}: {stderr.strip()[:200]}")
            return None
        return stdout

    def _extract_via_ytdlp(self) -> Tuple[Optional[str], Optional[str]]:
        stdout = self._run_ytdlp(["--print-json", "--flat-playlist"], timeout=30)
        if not stdout:
            return None, None
        try:
            metadata = __import__(
                "ytget_gui.workers.fetch_core", fromlist=["parse_metadata"]
            ).parse_metadata(stdout)
        except Exception:  # noqa: BLE001 - parse failures are non-fatal here
            return None, None
        return metadata.thumb_url or None, metadata.video_id or None

    def _download_via_ytdlp(self, target: Path) -> Optional[Path]:
        stem = target.stem
        stdout = self._run_ytdlp(
            [
                "--write-thumbnail",
                "-o", str(self.cache_dir / f"{stem}.%(ext)s"),
            ],
            timeout=60,
        )
        if stdout is None:
            return None
        return self._existing_cache_entry(stem)

    # ------------------------------------------------------------------
    # Download / conversion
    # ------------------------------------------------------------------

    def _download_via_requests(self, thumb_url: str, target: Path) -> Optional[Path]:
        headers = {
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Referer": self._referer(thumb_url),
        }
        try:
            with _SESSION.get(
                thumb_url,
                headers=headers,
                stream=True,
                timeout=(5, self.timeout),
                allow_redirects=True,
                **self._request_kwargs(),
            ) as response:
                response.raise_for_status()
                final = target.with_suffix(
                    _extension_for(thumb_url, response.headers.get("Content-Type"))
                )
                written = self._stream_to_file(response, final)
        except RequestException as exc:
            self._log(f"HTTP error: {exc}")
            return None

        if written is None:
            return None
        if written.suffix.lower() == ".avif":
            return self._convert_avif(written)
        return written

    def _stream_to_file(self, response: requests.Response, final: Path) -> Optional[Path]:
        tmp_path: Optional[Path] = None
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                delete=False, dir=str(self.cache_dir), suffix=final.suffix
            ) as handle:
                tmp_path = Path(handle.name)
                for chunk in response.iter_content(chunk_size=65536):
                    if self._cancelled():
                        return None
                    if chunk:
                        handle.write(chunk)

            if tmp_path.stat().st_size == 0:
                return None
            # Atomic swap: a half-written cache file would be re-served forever
            # as a valid entry on the next launch.
            tmp_path.replace(final)
            tmp_path = None
            return final
        except OSError as exc:
            self._log(f"Could not write thumbnail: {exc}")
            return None
        finally:
            if tmp_path is not None and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def _convert_avif(self, path: Path) -> Optional[Path]:
        """Qt has no built-in AVIF reader, so convert or the card shows blank."""
        jpg = path.with_suffix(".jpg")
        try:
            from PIL import Image

            with Image.open(path) as image:
                image.convert("RGB").save(jpg, format="JPEG", quality=95)
            path.unlink(missing_ok=True)
            return jpg
        except Exception as exc:  # noqa: BLE001 - Pillow may lack AVIF support
            log.debug("Pillow AVIF conversion failed: %s", exc)

        ffmpeg = Path(getattr(self.settings, "FFMPEG_PATH", "ffmpeg"))
        binary = str(ffmpeg) if ffmpeg.is_file() else "ffmpeg"
        try:
            # proc.run keeps the console window hidden; the previous revision
            # called subprocess.run directly here and flashed a window per
            # thumbnail on Windows.
            result = proc.run([binary, "-y", "-i", str(path), str(jpg)], timeout=30)
        except (OSError, subprocess.SubprocessError) as exc:
            self._log(f"AVIF conversion failed: {exc}")
            return None
        if result.returncode != 0 or not jpg.is_file():
            return None
        path.unlink(missing_ok=True)
        return jpg

    @staticmethod
    def _referer(url: str) -> str:
        try:
            parsed = urlparse(url)
            if parsed.scheme and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}/"
        except ValueError:
            pass
        return "https://www.youtube.com/"


def is_usable_file_safe(path) -> bool:
    from ytget_gui.utils.paths import is_usable_file

    return is_usable_file(path)


class ThumbManager(QObject):
    """Runs thumbnail fetches on a bounded pool so the GUI never blocks."""

    started = Signal(str)
    finished = Signal(str, str)
    error = Signal(str, str)

    def __init__(
        self,
        cache_dir: Path,
        settings: AppSettings,
        max_workers: int = 2,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.cache_dir = Path(cache_dir)
        self.settings = settings
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._executor = ThreadPoolExecutor(
            max_workers=max(1, int(max_workers)), thread_name_prefix="ThumbFetch"
        )
        self._lock = threading.Lock()
        self._pending: Set[str] = set()
        self._active: Dict[str, ThumbFetcher] = {}
        self._futures: Dict[str, Future] = {}
        self._stopped = False

    def enqueue(self, url: str, *, force: bool = False) -> None:
        """Queue a fetch, skipping URLs already queued or in flight."""
        if not url or self._stopped:
            return
        with self._lock:
            if not force and url in self._pending:
                return
            self._pending.add(url)
        try:
            future = self._executor.submit(self._run_one, url)
        except RuntimeError:
            with self._lock:
                self._pending.discard(url)
            return
        with self._lock:
            self._futures[url] = future

    def cancel(self, url: str) -> None:
        with self._lock:
            fetcher = self._active.get(url)
            future = self._futures.get(url)
            self._pending.discard(url)
        if future is not None:
            future.cancel()
        if fetcher is not None:
            fetcher.request_cancel()

    def stop(self, wait: bool = True) -> None:
        """Cancel everything in flight and return promptly.

        The previous implementation called shutdown(wait=True), which blocked
        until whatever was running finished on its own -- with the network down
        that meant waiting out full subprocess timeouts back to back, freezing
        the window on close for a minute or more.
        """
        self._stopped = True
        with self._lock:
            fetchers = list(self._active.values())
            futures = list(self._futures.values())
            self._pending.clear()

        for fetcher in fetchers:
            try:
                fetcher.request_cancel()
            except Exception:  # noqa: BLE001
                pass

        if wait and futures:
            # Grace period only. In-flight requests calls cannot be force-aborted,
            # so this gives them a moment to observe cancellation; callers bound
            # their own shutdown budget and these must not stack.
            try:
                futures_wait(futures, timeout=0.3)
            except Exception:  # noqa: BLE001
                pass

        try:
            self._executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:  # pragma: no cover - Python < 3.9
            self._executor.shutdown(wait=False)

    def _run_one(self, url: str) -> None:
        fetcher = ThumbFetcher(url, self.cache_dir, self.settings)
        with self._lock:
            self._active[url] = fetcher
        try:
            fetcher.started.connect(self.started.emit)
            fetcher.finished.connect(self.finished.emit)
            fetcher.error.connect(self.error.emit)
            fetcher.run()
        except Exception as exc:  # noqa: BLE001
            log.debug("Thumb worker failed for %s: %s", url, exc)
            self.finished.emit(url, "")
        finally:
            with self._lock:
                self._pending.discard(url)
                self._active.pop(url, None)
                self._futures.pop(url, None)
