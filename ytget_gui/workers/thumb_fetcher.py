# File: ytget_gui/workers/thumb_fetcher.py

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException

try:
    from urllib3.util.retry import Retry
except ImportError:  # pragma: no cover - very old urllib3
    Retry = None  # type: ignore

from PySide6.QtCore import QObject, Signal

from ytget_gui.settings import AppSettings
from ytget_gui.workers import cookies as CookieManager
from ytget_gui.workers import ssl_utils


# --------------------------------------------------------------------------
# Shared, connection-pooled HTTP session. Safe to use from multiple threads:
# the underlying urllib3 connection pools are thread-safe, and we never
# mutate session-level state (headers, cookies, etc.) after construction.
# --------------------------------------------------------------------------
def _build_session() -> requests.Session:
    session = requests.Session()
    if Retry is not None:
        retry = Retry(total=2, backoff_factor=0.3, status_forcelist=(500, 502, 503, 504))
        adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=retry)
    else:
        adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


_SESSION = _build_session()

# Resolutions to try, best first, when guessing a thumbnail URL directly.
_YTIMG_CANDIDATES: Tuple[str, ...] = ("maxresdefault", "sddefault", "hqdefault", "mqdefault", "default")

# Known byte sizes of YouTube's generic grey "no thumbnail" placeholder
# image, which is served with HTTP 200 even when a resolution doesn't
# actually exist for a given video.
_PLACEHOLDER_BYTE_SIZES = {1120, 2088}

# Cookie export (browser -> cookies.txt) is comparatively expensive and does
# not need to happen more than once every few minutes.
_COOKIE_REFRESH_MIN_INTERVAL = 300.0  # seconds
_cookie_refresh_lock = threading.Lock()
_last_cookie_refresh_ts = 0.0


def _safe_name(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "unknown"
    s = re.sub(r"[^A-Za-z0-9._-]", "_", s)
    if len(s) > 120:
        h = hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]
        s = s[:100] + "_" + h
    return s


def _ext_from_url_or_ct(url: str, content_type: Optional[str]) -> str:
    url = url or ""
    m = re.search(r"\.([a-zA-Z0-9]{2,6})(?:[?#]|$)", url)
    if m:
        ext = m.group(1).lower()
        if ext in {"jpg", "jpeg", "png", "webp", "gif", "bmp", "avif"}:
            return "." + ("jpg" if ext == "jpeg" else ext)
    if content_type:
        ct = content_type.lower()
        if "jpeg" in ct:
            return ".jpg"
        if "png" in ct:
            return ".png"
        if "webp" in ct:
            return ".webp"
        if "gif" in ct:
            return ".gif"
        if "avif" in ct:
            return ".avif"
    return ".jpg"


class ThumbFetcher(QObject):
    """
    Fetch a thumbnail for a given URL and cache it.

    Signals:
      - started(url)
      - finished(url, path)  -> path is empty string on failure
      - error(url, message)
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
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.url = url
        self.cache_dir = Path(cache_dir)
        self.settings = settings
        self.timeout = int(timeout)
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        self._target_path: Optional[Path] = None

    # ------------------------------------------------------------------
    # Small helpers to cut down on repetitive try/except boilerplate.
    # ------------------------------------------------------------------
    def _safe_emit(self, signal: Signal, *args) -> None:
        try:
            signal.emit(*args)
        except Exception:
            pass

    def _log(self, message: str) -> None:
        if getattr(self.settings, "LOG_THUMBNAILS", False):
            self._safe_emit(self.error, self.url, message)

    def _finish(self, path: str) -> None:
        self._safe_emit(self.finished, self.url, path)

    # Public synchronous run method (intended to be called from a worker thread)
    def run(self):
        self._safe_emit(self.started, self.url)

        try:
            if getattr(self.settings, "COOKIES_AUTO_REFRESH", False) and getattr(self.settings, "COOKIES_FROM_BROWSER", ""):
                self._maybe_refresh_cookies()

            video_id = self._extract_video_id_from_url(self.url)

            # Fast path: guess the CDN URL directly and confirm it with a
            # pooled HEAD request. This skips the yt-dlp subprocess
            # entirely for the common case of a normal watch URL.
            thumb_url: Optional[str] = self._probe_ytimg_thumbnail(video_id) if video_id else None
            is_playlist = False

            if not thumb_url:
                # Slow path: ask yt-dlp for metadata. Needed for playlist
                # entries, non-standard URLs, or when the fast probe above
                # found nothing.
                extracted_url, extracted_id, is_playlist = self._extract_thumbnail_url()
                video_id = video_id or extracted_id
                thumb_url = extracted_url
                if not thumb_url and video_id:
                    thumb_url = self._probe_ytimg_thumbnail(video_id) or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

            if not thumb_url:
                self._log("No thumbnail URL discovered")
                self._finish("")
                return

            base_name = video_id or hashlib.sha1(self.url.encode("utf-8")).hexdigest()
            safe = _safe_name(base_name)
            ext_guess = ".jpg"
            m = re.search(r"\.([a-zA-Z0-9]{2,6})(?:[?#]|$)", thumb_url)
            if m:
                ext_guess = "." + m.group(1).lower()
            target = self.cache_dir / f"{safe}{ext_guess}"
            self._target_path = target

            # If the file already exists and is non-empty, reuse it
            # (converting avif -> jpg if needed).
            try:
                if target.exists() and target.stat().st_size > 0:
                    if target.suffix.lower() == ".avif":
                        converted = self._convert_avif_to_jpg(target)
                        if converted:
                            self._finish(str(converted))
                            return
                    else:
                        self._finish(str(target))
                        return
            except Exception:
                pass

            # Try requests first (fast, pooled connection).
            saved = None
            try:
                saved = self._download_with_requests(thumb_url, target)
            except Exception as e:
                self._log(f"requests download exception: {e}")

            if saved:
                self._finish(str(saved))
                return

            # Fallback to yt-dlp's own thumbnail writer.
            try:
                saved = self._download_with_ytdlp(thumb_url, target)
            except Exception as e:
                self._log(f"yt-dlp fallback exception: {e}")

            if saved:
                self._finish(str(saved))
                return

            self._log("Failed to download thumbnail")
            self._finish("")
        except Exception as e:
            self._log(f"Unexpected error: {e}")
            self._finish("")

    # ------------------------------------------------------------------
    # Cookie refresh (throttled process-wide)
    # ------------------------------------------------------------------
    def _maybe_refresh_cookies(self) -> None:
        global _last_cookie_refresh_ts
        now = time.monotonic()
        with _cookie_refresh_lock:
            if now - _last_cookie_refresh_ts < _COOKIE_REFRESH_MIN_INTERVAL:
                return
            _last_cookie_refresh_ts = now

        try:
            ok, msg = CookieManager.refresh_before_download(self.settings)
        except Exception as e:
            self._log(f"Cookies refresh exception: {e}")
            return

        if not ok:
            self._log(f"Cookies refresh failed: {msg}")
            return

        try:
            exported_path = getattr(self.settings, "COOKIES_PATH", None)
            if not exported_path or str(exported_path) == "":
                exported_path = Path(getattr(self.settings, "BASE_DIR", Path("."))) / "cookies.txt"
            self.settings.COOKIES_PATH = Path(exported_path)
            self.settings.COOKIES_LAST_IMPORTED = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            if hasattr(self.settings, "save_config"):
                try:
                    self.settings.save_config()
                except Exception:
                    pass
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Fast-path thumbnail resolution (no subprocess)
    # ------------------------------------------------------------------
    def _probe_ytimg_thumbnail(self, video_id: Optional[str]) -> Optional[str]:
        if not video_id:
            return None
        try:
            verify, _args, _env = ssl_utils.resolve_ssl_config(self.settings)
        except Exception:
            verify = True

        proxies = None
        proxy = getattr(self.settings, "PROXY_URL", "") or ""
        if proxy:
            proxies = {"http": proxy, "https": proxy}

        probe_timeout = min(self.timeout, 6) or 6

        for name in _YTIMG_CANDIDATES:
            candidate = f"https://i.ytimg.com/vi/{video_id}/{name}.jpg"
            try:
                r = _SESSION.head(candidate, timeout=probe_timeout, allow_redirects=True, proxies=proxies, verify=verify)
            except Exception:
                continue
            if r.status_code != 200:
                continue
            length = r.headers.get("Content-Length")
            if length:
                try:
                    if int(length) in _PLACEHOLDER_BYTE_SIZES:
                        continue
                except ValueError:
                    pass
            return candidate
        return None

    def _canonical_watch_url(self, url: str) -> str:
        try:
            if not url:
                return url or ""
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            if "v" in qs and qs["v"]:
                vid = qs["v"][0]
                return f"https://www.youtube.com/watch?v={vid}"
        except Exception:
            pass
        return url or ""

    def _extract_video_id_from_url(self, url: str) -> Optional[str]:
        try:
            if not url:
                return None
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            if "v" in qs and qs["v"]:
                return qs["v"][0]
            m = re.search(r"(?:youtu\.be/|youtube\.com/(?:embed/|v/|shorts/))([A-Za-z0-9_-]{6,})", url)
            if m:
                return m.group(1)
            m2 = re.search(r"[?&]v=([A-Za-z0-9_-]{6,})", url)
            if m2:
                return m2.group(1)
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Slow path: yt-dlp subprocess helpers
    # ------------------------------------------------------------------
    def _ytdlp_common_args(self) -> List[str]:
        args: List[str] = []
        cookies_from = getattr(self.settings, "COOKIES_FROM_BROWSER", "") or ""
        if cookies_from:
            profile = getattr(self.settings, "COOKIES_PROFILE", None)
            args.extend(["--cookies-from-browser", f"{cookies_from}:{profile}" if profile else cookies_from])
        else:
            cookies_path = getattr(self.settings, "COOKIES_PATH", None)
            if cookies_path and Path(cookies_path).exists():
                args.extend(["--cookies", str(cookies_path)])

        proxy = getattr(self.settings, "PROXY_URL", "") or ""
        if proxy:
            args.extend(["--proxy", proxy])

        try:
            ffmpeg_dir = str(self.settings.FFMPEG_PATH.parent)
            args.extend(["--ffmpeg-location", ffmpeg_dir])
        except Exception:
            pass
        return args

    def _build_subprocess_env(self, ssl_env: dict) -> dict:
        env = os.environ.copy()
        try:
            extra_paths = [str(self.settings.INTERNAL_DIR), str(self.settings.BASE_DIR)]
            ph = getattr(self.settings, "PHANTOMJS_PATH", None)
            if ph and getattr(ph, "exists", None) and ph.exists():
                extra_paths.append(str(ph.parent))
            cur_path = env.get("PATH", "")
            for p in reversed(extra_paths):
                if p and p not in cur_path:
                    cur_path = f"{p}{os.pathsep}{cur_path}"
            env["PATH"] = cur_path
            if os.name == "nt" and not env.get("PATHEXT"):
                env["PATHEXT"] = ".COM;.EXE;.BAT;.CMD"
        except Exception:
            pass
        try:
            env.update(ssl_env)
        except Exception:
            pass
        return env

    @staticmethod
    def _win_startupinfo():
        if platform.system().lower().startswith("win"):
            try:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                return si
            except Exception:
                return None
        return None

    def _extract_thumbnail_url(self) -> Tuple[Optional[str], Optional[str], bool]:
        try:
            url_for_metadata = self._canonical_watch_url(self.url)

            ytdlp_path = getattr(self.settings, "YT_DLP_PATH", None)
            if not ytdlp_path:
                return None, self._extract_video_id_from_url(self.url), False
            try:
                ytdlp_path = Path(ytdlp_path)
                if not ytdlp_path.exists():
                    return None, self._extract_video_id_from_url(self.url), False
            except Exception:
                return None, self._extract_video_id_from_url(self.url), False

            cmd: List[str] = [
                str(ytdlp_path),
                "--no-warnings",
                "--skip-download",
                "--print-json",
                "--ignore-errors",
                "--flat-playlist",
            ]

            _verify, ytdlp_ssl_args, ssl_env = ssl_utils.resolve_ssl_config(self.settings)
            cmd.extend(ytdlp_ssl_args)
            cmd.append(url_for_metadata)
            cmd.extend(self._ytdlp_common_args())

            env = self._build_subprocess_env(ssl_env)
            startupinfo = self._win_startupinfo()

            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=False,
                    check=False,
                    timeout=30,
                    startupinfo=startupinfo,
                    env=env,
                )
            except FileNotFoundError:
                return None, self._extract_video_id_from_url(self.url), False
            except subprocess.TimeoutExpired:
                self._log("yt-dlp metadata extraction timed out")
                return None, None, False
            except Exception as e:
                self._log(f"yt-dlp metadata extraction error: {e}")
                return None, self._extract_video_id_from_url(self.url), False

            stdout = (proc.stdout or b"").decode("utf-8", errors="replace")
            stderr = (proc.stderr or b"").decode("utf-8", errors="replace")

            if proc.returncode != 0 and not stdout:
                self._log(f"yt-dlp failed to extract metadata: {stderr.strip()}")
                return None, self._extract_video_id_from_url(self.url), False

            output = stdout.strip()
            if not output:
                return None, self._extract_video_id_from_url(self.url), False

            thumbnail: Optional[str] = None
            video_id: Optional[str] = None
            is_playlist = False

            def pick_best_from_thumbnails(thumbs: List[Any]) -> Optional[str]:
                if not thumbs:
                    return None
                try:
                    best = max(
                        (t for t in thumbs if isinstance(t, dict)),
                        key=lambda t: (t.get("preference", 0), t.get("width", 0), t.get("height", 0)),
                    )
                    return best.get("url") or None
                except Exception:
                    for t in reversed(thumbs):
                        if isinstance(t, dict) and t.get("url"):
                            return t.get("url")
                    return None

            for line in (l for l in output.splitlines() if l.strip()):
                try:
                    info = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if "entries" in info or "playlist_index" in info or "playlist_title" in info:
                    is_playlist = True

                if not thumbnail and info.get("thumbnail"):
                    thumbnail = info.get("thumbnail")

                if not thumbnail and isinstance(info.get("thumbnails"), list):
                    candidate = pick_best_from_thumbnails(info.get("thumbnails"))
                    if candidate:
                        thumbnail = candidate

                if not video_id and info.get("id"):
                    video_id = info.get("id")

                if thumbnail and video_id:
                    break

            if not video_id:
                video_id = self._extract_video_id_from_url(self.url)

            return thumbnail, video_id, is_playlist
        except subprocess.TimeoutExpired:
            self._log("yt-dlp metadata extraction timed out")
            return None, None, False
        except Exception as e:
            self._log(f"yt-dlp metadata extraction error: {e}")
            return None, self._extract_video_id_from_url(self.url), False

    def _convert_avif_to_jpg(self, avif_path: Path) -> Optional[Path]:
        try:
            from PIL import Image  # type: ignore

            with Image.open(avif_path) as im:
                rgb = im.convert("RGB")
                jpg_path = avif_path.with_suffix(".jpg")
                rgb.save(jpg_path, format="JPEG", quality=95)
            try:
                avif_path.unlink()
            except Exception:
                pass
            return jpg_path
        except Exception:
            pass

        # Fallback: use ffmpeg to do the conversion.
        try:
            jpg_path = avif_path.with_suffix(".jpg")
            ffmpeg_cmd = ["ffmpeg", "-y", "-i", str(avif_path), str(jpg_path)]
            try:
                ffmpeg_path = getattr(self.settings, "FFMPEG_PATH", None)
                if ffmpeg_path:
                    ffmpeg_path = Path(ffmpeg_path)
                    if ffmpeg_path.exists():
                        ffmpeg_cmd[0] = str(ffmpeg_path)
            except Exception:
                pass
            subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)
            try:
                avif_path.unlink()
            except Exception:
                pass
            return jpg_path
        except Exception:
            return None

    def _derive_referer(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            if parsed.scheme and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}/"
        except Exception:
            pass
        return "https://www.youtube.com/"

    @staticmethod
    def _atomic_move(tmp_path: Path, final: Path) -> None:
        """Move tmp_path to final, falling back to copy+delete if a plain
        rename isn't possible (e.g. across filesystems)."""
        try:
            tmp_path.replace(final)
            return
        except Exception:
            pass
        try:
            tmp_path.rename(final)
            return
        except Exception:
            pass
        with open(tmp_path, "rb") as src, open(final, "wb") as dst:
            dst.write(src.read())
        try:
            tmp_path.unlink()
        except Exception:
            pass

    def _download_with_requests(self, thumb_url: str, target: Path) -> Optional[Path]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Referer": self._derive_referer(thumb_url),
        }

        proxies = None
        proxy = getattr(self.settings, "PROXY_URL", "") or ""
        if proxy:
            proxies = {"http": proxy, "https": proxy}

        requests_verify, _ytdlp_args, _env = ssl_utils.resolve_ssl_config(self.settings)
        ssl_utils.maybe_suppress_insecure_warning(requests_verify)

        try:
            with _SESSION.get(
                thumb_url,
                headers=headers,
                stream=True,
                timeout=self.timeout,
                proxies=proxies,
                allow_redirects=True,
                verify=requests_verify,
            ) as r:
                try:
                    r.raise_for_status()
                except RequestException as e:
                    self._log(f"HTTP error {getattr(r, 'status_code', '')}: {e}")
                    return None

                content_type = r.headers.get("Content-Type", "")
                ext = _ext_from_url_or_ct(thumb_url, content_type)
                final = target.with_suffix(ext)

                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=ext, dir=str(target.parent)) as tf:
                        for chunk in r.iter_content(chunk_size=65536):
                            if chunk:
                                tf.write(chunk)
                        tmp_path = Path(tf.name)
                except Exception as e:
                    self._log(f"Failed to write temp thumbnail file: {e}")
                    return None

                try:
                    self._atomic_move(tmp_path, final)
                except Exception as e:
                    try:
                        tmp_path.unlink()
                    except Exception:
                        pass
                    self._log(f"Failed to move temp thumbnail file: {e}")
                    return None

                if not (final.exists() and final.stat().st_size > 0):
                    self._log(f"Downloaded thumbnail file missing or empty: {final}")
                    return None

                if final.suffix.lower() == ".avif":
                    converted = self._convert_avif_to_jpg(final)
                    if converted and converted.exists() and converted.stat().st_size > 0:
                        return converted
                    self._log("Failed to convert AVIF thumbnail to JPG")
                    return None

                return final
        except RequestException as e:
            self._log(f"requests exception: {e}")
            return None
        except Exception as e:
            self._log(f"unexpected error during requests download: {e}")
            return None

    def _download_with_ytdlp(self, thumb_url: str, target: Path) -> Optional[Path]:
        try:
            ytdlp_path = getattr(self.settings, "YT_DLP_PATH", None)
            if not ytdlp_path:
                return None
            try:
                ytdlp_path = Path(ytdlp_path)
                if not ytdlp_path.exists():
                    return None
            except Exception:
                return None

            out_dir = str(target.parent)
            base = target.stem
            out_template = str(Path(out_dir) / (base + ".%(ext)s"))

            url_for_metadata = self._canonical_watch_url(self.url)

            cmd: List[str] = [
                str(ytdlp_path),
                "--no-warnings",
                "--skip-download",
                "--write-thumbnail",
                "-o",
                out_template,
            ]

            _verify, ytdlp_ssl_args, ssl_env = ssl_utils.resolve_ssl_config(self.settings)
            cmd.extend(ytdlp_ssl_args)
            cmd.append(url_for_metadata)
            cmd.extend(self._ytdlp_common_args())

            env = self._build_subprocess_env(ssl_env)
            startupinfo = self._win_startupinfo()

            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=False,
                    check=False,
                    timeout=60,
                    startupinfo=startupinfo,
                    env=env,
                )
            except FileNotFoundError:
                return None
            except subprocess.TimeoutExpired:
                self._log("yt-dlp thumbnail write timed out")
                return None
            except Exception as e:
                self._log(f"yt-dlp thumbnail write error: {e}")
                return None

            if proc.returncode != 0:
                stderr = (proc.stderr or b"").decode("utf-8", errors="replace")
                self._log(f"yt-dlp returned code {proc.returncode}: {stderr.strip()}")

            candidates = list(Path(out_dir).glob(base + ".*"))
            ordered: List[Path] = []
            for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"):
                ordered.extend(c for c in candidates if c.suffix.lower() == ext)
            if not ordered:
                ordered = candidates

            for c in ordered:
                final = target.with_suffix(c.suffix.lower())
                try:
                    c.replace(final)
                except Exception:
                    final = c  # couldn't rename; use the file where it landed

                if final.suffix.lower() == ".avif":
                    converted = self._convert_avif_to_jpg(final)
                    if converted and converted.exists() and converted.stat().st_size > 0:
                        return converted
                    return None
                return final

            return None
        except Exception:
            return None


# -------------------------
# ThumbManager: runs thumbnail fetches on a small bounded thread pool
# -------------------------
class ThumbManager(QObject):
    """
    ThumbManager fetches thumbnails on a bounded thread pool so the GUI
    thread never blocks, while `max_workers` limits how many fetches
    (subprocess calls / downloads) run at once.

    Usage:
      manager = ThumbManager(cache_dir, settings, max_workers=1)
      manager.started.connect(...)
      manager.finished.connect(...)
      manager.error.connect(...)
      manager.enqueue(url)
      manager.stop()  # on shutdown
    """

    started = Signal(str)
    finished = Signal(str, str)
    error = Signal(str, str)

    def __init__(self, cache_dir: Path, settings: AppSettings, max_workers: int = 1):
        super().__init__()
        self.cache_dir = Path(cache_dir)
        self.settings = settings
        self.max_workers = max(1, int(max_workers))
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="ThumbFetch")
        self._lock = threading.Lock()
        self._pending: set = set()
        self._stopped = False

    def enqueue(self, url: str, force: bool = False) -> None:
        """Queue a thumbnail fetch.

        URLs already queued or in-flight are skipped by default so the same
        thumbnail is never fetched twice concurrently (common when a GUI
        list re-renders). Pass force=True to fetch anyway, e.g. to retry
        after a failure.
        """
        if not url or self._stopped:
            return
        with self._lock:
            if not force and url in self._pending:
                return
            self._pending.add(url)
        try:
            self._executor.submit(self._run_one, url)
        except RuntimeError:
            # Executor already shut down; drop silently.
            with self._lock:
                self._pending.discard(url)

    def stop(self, wait: bool = True) -> None:
        self._stopped = True
        try:
            self._executor.shutdown(wait=wait, cancel_futures=not wait)
        except TypeError:
            # cancel_futures was added in Python 3.9; degrade gracefully.
            self._executor.shutdown(wait=wait)

    def _run_one(self, url: str) -> None:
        try:
            fetcher = ThumbFetcher(url, self.cache_dir, self.settings)
            fetcher.started.connect(self.started.emit)
            fetcher.finished.connect(self.finished.emit)
            fetcher.error.connect(self.error.emit)
            try:
                fetcher.run()
            except Exception as e:
                if getattr(self.settings, "LOG_THUMBNAILS", False):
                    try:
                        self.error.emit(url, f"Fetcher run exception: {e}")
                    except Exception:
                        pass
                try:
                    self.finished.emit(url, "")
                except Exception:
                    pass
        finally:
            with self._lock:
                self._pending.discard(url)
