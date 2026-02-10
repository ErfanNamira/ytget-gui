# File: ytget_gui/workers/thumb_fetcher.py
from __future__ import annotations

import json
import subprocess
import platform
import os
import hashlib
import re
import tempfile
from pathlib import Path
from typing import Optional, Tuple, Any, List
import requests
from requests.exceptions import RequestException
from urllib.parse import urlparse, parse_qs
import shutil
import threading
import time
import queue

from PySide6.QtCore import QObject, Signal

from ytget_gui.settings import AppSettings
from ytget_gui.workers import cookies as CookieManager


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

    # Public synchronous run method (intended to be called from a worker thread)
    def run(self):
        try:
            self.started.emit(self.url)
        except Exception:
            pass

        try:
            # Optional cookie refresh (non-fatal)
            try:
                if getattr(self.settings, "COOKIES_AUTO_REFRESH", False) and getattr(self.settings, "COOKIES_FROM_BROWSER", ""):
                    try:
                        ok, msg = CookieManager.refresh_before_download(self.settings)
                    except Exception as e:
                        if getattr(self.settings, "LOG_THUMBNAILS", False):
                            try:
                                self.error.emit(self.url, f"Cookies refresh exception: {e}")
                            except Exception:
                                pass
                        ok = False
                        msg = str(e)
                    if ok:
                        exported_path = getattr(self.settings, "COOKIES_PATH", None)
                        if not exported_path or str(exported_path) == "":
                            exported_path = Path(getattr(self.settings, "BASE_DIR", Path("."))) / "cookies.txt"
                        try:
                            self.settings.COOKIES_PATH = Path(exported_path)
                            from datetime import datetime
                            ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
                            self.settings.COOKIES_LAST_IMPORTED = ts
                            if hasattr(self.settings, "save_config"):
                                try:
                                    self.settings.save_config()
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    else:
                        if getattr(self.settings, "LOG_THUMBNAILS", False):
                            try:
                                self.error.emit(self.url, f"Cookies refresh failed: {msg}")
                            except Exception:
                                pass
            except Exception as e:
                if getattr(self.settings, "LOG_THUMBNAILS", False):
                    try:
                        self.error.emit(self.url, f"Cookies refresh exception: {e}")
                    except Exception:
                        pass

            thumb_url, video_id, is_playlist = self._extract_thumbnail_url()
            if not thumb_url:
                if video_id:
                    thumb_url = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
                else:
                    if getattr(self.settings, "LOG_THUMBNAILS", False):
                        try:
                            self.error.emit(self.url, "No thumbnail URL discovered")
                        except Exception:
                            pass
                    try:
                        self.finished.emit(self.url, "")
                    except Exception:
                        pass
                    return

            base_name = video_id or hashlib.sha1(self.url.encode("utf-8")).hexdigest()
            safe = _safe_name(base_name)
            ext_guess = ".jpg"
            m = re.search(r"\.([a-zA-Z0-9]{2,6})(?:[?#]|$)", thumb_url)
            if m:
                ext_guess = "." + m.group(1).lower()
            target = self.cache_dir / f"{safe}{ext_guess}"
            self._target_path = target

            # If file already exists and non-empty, return it (convert avif if needed)
            try:
                if target.exists() and target.stat().st_size > 0:
                    if target.suffix.lower() == ".avif":
                        converted = self._convert_avif_to_jpg(target)
                        if converted:
                            try:
                                self.finished.emit(self.url, str(converted))
                            except Exception:
                                pass
                            return
                    try:
                        self.finished.emit(self.url, str(target))
                    except Exception:
                        pass
                    return
            except Exception:
                pass

            # Try requests first
            saved = None
            try:
                saved = self._download_with_requests(thumb_url, target)
            except Exception as e:
                if getattr(self.settings, "LOG_THUMBNAILS", False):
                    try:
                        self.error.emit(self.url, f"requests download exception: {e}")
                    except Exception:
                        pass

            if saved:
                try:
                    self.finished.emit(self.url, str(saved))
                except Exception:
                    pass
                return

            # Fallback to yt-dlp approach
            try:
                saved = self._download_with_ytdlp(thumb_url, target)
            except Exception as e:
                if getattr(self.settings, "LOG_THUMBNAILS", False):
                    try:
                        self.error.emit(self.url, f"yt-dlp fallback exception: {e}")
                    except Exception:
                        pass

            if saved:
                try:
                    self.finished.emit(self.url, str(saved))
                except Exception:
                    pass
                return

            # Nothing worked
            if getattr(self.settings, "LOG_THUMBNAILS", False):
                try:
                    self.error.emit(self.url, "Failed to download thumbnail")
                except Exception:
                    pass
            try:
                self.finished.emit(self.url, "")
            except Exception:
                pass
        except Exception as e:
            if getattr(self.settings, "LOG_THUMBNAILS", False):
                try:
                    self.error.emit(self.url, f"Unexpected error: {e}")
                except Exception:
                    pass
            try:
                self.finished.emit(self.url, "")
            except Exception:
                pass

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
            m = re.search(r"(?:youtu\.be/|youtube\.com/(?:embed/|v/))([A-Za-z0-9_-]{6,})", url)
            if m:
                return m.group(1)
            m2 = re.search(r"[?&]v=([A-Za-z0-9_-]{6,})", url)
            if m2:
                return m2.group(1)
        except Exception:
            pass
        return None

    def _extract_thumbnail_url(self) -> Tuple[Optional[str], Optional[str], bool]:
        try:
            url_for_metadata = self._canonical_watch_url(self.url)

            ytdlp_path = getattr(self.settings, "YT_DLP_PATH", None)
            if not ytdlp_path:
                vid = self._extract_video_id_from_url(self.url)
                return None, vid, False
            try:
                ytdlp_path = Path(ytdlp_path)
                if not ytdlp_path.exists():
                    vid = self._extract_video_id_from_url(self.url)
                    return None, vid, False
            except Exception:
                vid = self._extract_video_id_from_url(self.url)
                return None, vid, False

            cmd: List[str] = [
                str(ytdlp_path),
                "--no-warnings",
                "--skip-download",
                "--print-json",
                "--ignore-errors",
                "--flat-playlist",
                url_for_metadata,
            ]

            cookies_from = getattr(self.settings, "COOKIES_FROM_BROWSER", "") or ""
            if cookies_from:
                profile = getattr(self.settings, "COOKIES_PROFILE", None)
                if profile:
                    cmd.extend(["--cookies-from-browser", f"{cookies_from}:{profile}"])
                else:
                    cmd.extend(["--cookies-from-browser", cookies_from])
            else:
                cookies_path = getattr(self.settings, "COOKIES_PATH", None)
                if cookies_path and Path(cookies_path).exists():
                    cmd.extend(["--cookies", str(cookies_path)])

            proxy = getattr(self.settings, "PROXY_URL", "") or ""
            if proxy:
                cmd.extend(["--proxy", proxy])

            try:
                ffmpeg_dir = str(self.settings.FFMPEG_PATH.parent)
                cmd.extend(["--ffmpeg-location", ffmpeg_dir])
            except Exception:
                pass

            env = os.environ.copy()
            try:
                extra_paths = []
                extra_paths.append(str(self.settings.INTERNAL_DIR))
                extra_paths.append(str(self.settings.BASE_DIR))
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

            startupinfo = None
            if platform.system().lower().startswith("win"):
                try:
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo = si
                except Exception:
                    startupinfo = None

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
                vid = self._extract_video_id_from_url(self.url)
                return None, vid, False
            except subprocess.TimeoutExpired:
                if getattr(self.settings, "LOG_THUMBNAILS", False):
                    try:
                        self.error.emit(self.url, "yt-dlp metadata extraction timed out")
                    except Exception:
                        pass
                return None, None, False
            except Exception as e:
                if getattr(self.settings, "LOG_THUMBNAILS", False):
                    try:
                        self.error.emit(self.url, f"yt-dlp metadata extraction error: {e}")
                    except Exception:
                        pass
                vid = self._extract_video_id_from_url(self.url)
                return None, vid, False

            stdout = (proc.stdout or b"").decode("utf-8", errors="replace")
            stderr = (proc.stderr or b"").decode("utf-8", errors="replace")

            if proc.returncode != 0 and not stdout:
                stderr_msg = stderr.strip()
                if getattr(self.settings, "LOG_THUMBNAILS", False):
                    try:
                        self.error.emit(self.url, f"yt-dlp failed to extract metadata: {stderr_msg}")
                    except Exception:
                        pass
                vid = self._extract_video_id_from_url(self.url)
                return None, vid, False

            output = stdout.strip()
            if not output:
                vid = self._extract_video_id_from_url(self.url)
                return None, vid, False

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
                        try:
                            if isinstance(t, dict) and t.get("url"):
                                return t.get("url")
                        except Exception:
                            continue
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

                if not thumbnail and info.get("thumbnails"):
                    t = info.get("thumbnails")
                    if isinstance(t, list):
                        candidate = pick_best_from_thumbnails(t)
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
            if getattr(self.settings, "LOG_THUMBNAILS", False):
                try:
                    self.error.emit(self.url, "yt-dlp metadata extraction timed out")
                except Exception:
                    pass
            return None, None, False
        except Exception as e:
            if getattr(self.settings, "LOG_THUMBNAILS", False):
                try:
                    self.error.emit(self.url, f"yt-dlp metadata extraction error: {e}")
                except Exception:
                    pass
            vid = self._extract_video_id_from_url(self.url)
            return None, vid, False

    def _convert_avif_to_jpg(self, avif_path: Path) -> Optional[Path]:
        try:
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
                jpg_path = avif_path.with_suffix(".jpg")
                try:
                    ffmpeg_cmd = ["ffmpeg", "-y", "-i", str(avif_path), str(jpg_path)]
                    try:
                        ffmpeg_path = getattr(self.settings, "FFMPEG_PATH", None)
                        if ffmpeg_path:
                            ffmpeg_path = Path(ffmpeg_path)
                            if ffmpeg_path.exists():
                                ffmpeg_cmd[0] = str(ffmpeg_path)
                    except Exception:
                        pass
                    subprocess.run(
                        ffmpeg_cmd,
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    try:
                        avif_path.unlink()
                    except Exception:
                        pass
                    return jpg_path
                except Exception:
                    return None
        except Exception:
            return None

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

        try:
            with requests.get(thumb_url, headers=headers, stream=True, timeout=self.timeout, proxies=proxies, allow_redirects=True) as r:
                try:
                    r.raise_for_status()
                except RequestException as e:
                    if getattr(self.settings, "LOG_THUMBNAILS", False):
                        try:
                            self.error.emit(self.url, f"HTTP error {getattr(r, 'status_code', '')}: {e}")
                        except Exception:
                            pass
                    return None

                content_type = r.headers.get("Content-Type", "")
                ext = _ext_from_url_or_ct(thumb_url, content_type)
                final = target.with_suffix(ext)

                with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tf:
                    try:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                tf.write(chunk)
                        tmp_path = Path(tf.name)
                    finally:
                        tf.flush()

                try:
                    tmp_path.replace(final)
                except Exception:
                    try:
                        tmp_path.rename(final)
                    except Exception:
                        try:
                            with open(tmp_path, "rb") as src, open(final, "wb") as dst:
                                dst.write(src.read())
                        except Exception as e:
                            try:
                                tmp_path.unlink()
                            except Exception:
                                pass
                            if getattr(self.settings, "LOG_THUMBNAILS", False):
                                try:
                                    self.error.emit(self.url, f"Failed to move temp thumbnail file: {e}")
                                except Exception:
                                    pass
                            return None
                        try:
                            tmp_path.unlink()
                        except Exception:
                            pass

                if final.exists() and final.stat().st_size > 0:
                    try:
                        if final.suffix.lower() == ".avif":
                            converted = self._convert_avif_to_jpg(final)
                            if converted and converted.exists() and converted.stat().st_size > 0:
                                return converted
                            else:
                                if getattr(self.settings, "LOG_THUMBNAILS", False):
                                    try:
                                        self.error.emit(self.url, "Failed to convert AVIF thumbnail to JPG")
                                    except Exception:
                                        pass
                                return None
                        return final
                    except Exception as e:
                        if getattr(self.settings, "LOG_THUMBNAILS", False):
                            try:
                                self.error.emit(self.url, f"Error handling downloaded file: {e}")
                            except Exception:
                                pass
                        return None
                else:
                    if getattr(self.settings, "LOG_THUMBNAILS", False):
                        try:
                            self.error.emit(self.url, f"Downloaded thumbnail file missing or empty: {final}")
                        except Exception:
                            pass
                    return None
        except RequestException as e:
            if getattr(self.settings, "LOG_THUMBNAILS", False):
                try:
                    self.error.emit(self.url, f"requests exception: {e}")
                except Exception:
                    pass
            return None
        except Exception as e:
            if getattr(self.settings, "LOG_THUMBNAILS", False):
                try:
                    self.error.emit(self.url, f"unexpected error during requests download: {e}")
                except Exception:
                    pass
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
            out_template = str(Path(out_dir) / (base + "%(ext)s"))

            url_for_metadata = self._canonical_watch_url(self.url)

            cmd: List[str] = [
                str(ytdlp_path),
                "--no-warnings",
                "--skip-download",
                "--write-thumbnail",
                "-o",
                out_template,
                url_for_metadata,
            ]

            cookies_from = getattr(self.settings, "COOKIES_FROM_BROWSER", "") or ""
            if cookies_from:
                profile = getattr(self.settings, "COOKIES_PROFILE", None)
                if profile:
                    cmd.extend(["--cookies-from-browser", f"{cookies_from}:{profile}"])
                else:
                    cmd.extend(["--cookies-from-browser", cookies_from])
            else:
                cookies_path = getattr(self.settings, "COOKIES_PATH", None)
                if cookies_path and Path(cookies_path).exists():
                    cmd.extend(["--cookies", str(cookies_path)])

            proxy = getattr(self.settings, "PROXY_URL", "") or ""
            if proxy:
                cmd.extend(["--proxy", proxy])

            try:
                ffmpeg_dir = str(self.settings.FFMPEG_PATH.parent)
                cmd.extend(["--ffmpeg-location", ffmpeg_dir])
            except Exception:
                pass

            env = os.environ.copy()
            try:
                extra_paths = []
                extra_paths.append(str(self.settings.INTERNAL_DIR))
                extra_paths.append(str(self.settings.BASE_DIR))
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

            startupinfo = None
            if platform.system().lower().startswith("win"):
                try:
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo = si
                except Exception:
                    startupinfo = None

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
                if getattr(self.settings, "LOG_THUMBNAILS", False):
                    try:
                        self.error.emit(self.url, "yt-dlp thumbnail write timed out")
                    except Exception:
                        pass
                return None
            except Exception as e:
                if getattr(self.settings, "LOG_THUMBNAILS", False):
                    try:
                        self.error.emit(self.url, f"yt-dlp thumbnail write error: {e}")
                    except Exception:
                        pass
                return None

            _out = (proc.stdout or b"").decode("utf-8", errors="replace")
            _err = (proc.stderr or b"").decode("utf-8", errors="replace")
            if proc.returncode != 0:
                if getattr(self.settings, "LOG_THUMBNAILS", False):
                    try:
                        self.error.emit(self.url, f"yt-dlp returned code {proc.returncode}: {_err.strip()}")
                    except Exception:
                        pass

            candidates = list(Path(out_dir).glob(base + ".*"))
            for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"):
                for c in candidates:
                    if c.suffix.lower() == ext:
                        try:
                            final = target.with_suffix(ext)
                            try:
                                c.replace(final)
                                if final.suffix.lower() == ".avif":
                                    converted = self._convert_avif_to_jpg(final)
                                    if converted and converted.exists() and converted.stat().st_size > 0:
                                        return converted
                                    else:
                                        return None
                                return final
                            except Exception:
                                if c.suffix.lower() == ".avif":
                                    converted = self._convert_avif_to_jpg(c)
                                    if converted and converted.exists() and converted.stat().st_size > 0:
                                        return converted
                                    else:
                                        return c
                                return c
                        except Exception:
                            return c
            if candidates:
                first = candidates[0]
                if first.suffix.lower() == ".avif":
                    converted = self._convert_avif_to_jpg(first)
                    if converted and converted.exists() and converted.stat().st_size > 0:
                        return converted
                    else:
                        return None
            return None
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


# -------------------------
# ThumbManager: serializes thumbnail fetches (safe, single worker by default)
# -------------------------
class ThumbManager(QObject):
    """
    ThumbManager serializes thumbnail fetches to avoid UI crashes and resource contention.

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
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(target=self._worker_loop, name="ThumbManagerWorker", daemon=True)
        self._worker_thread.start()

    def enqueue(self, url: str):
        if not url:
            return
        self._queue.put(url)

    def stop(self, wait: bool = True):
        self._stop_event.set()
        # put a sentinel to wake the queue
        self._queue.put(None)
        if wait and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5)

    def _worker_loop(self):
        """
        Single-threaded loop that processes thumbnail requests sequentially.
        This avoids concurrent conversions and race conditions that crash the UI.
        """
        while not self._stop_event.is_set():
            try:
                item = self._queue.get()
                if item is None:
                    # sentinel for shutdown
                    break
                url = item
                # Create a ThumbFetcher and run it synchronously in this worker thread
                fetcher = ThumbFetcher(url, self.cache_dir, self.settings)
                # Forward signals from fetcher to manager signals
                fetcher.started.connect(lambda u, _u=url: self._emit_started(_u))
                fetcher.finished.connect(lambda u, p, _u=url: self._emit_finished(_u, p))
                fetcher.error.connect(lambda u, m, _u=url: self._emit_error(_u, m))
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
                    # small delay to avoid hammering remote servers when many items queued
                    time.sleep(0.05)
            except Exception:
                # swallow to keep loop alive
                time.sleep(0.1)
                continue

    # Internal emit helpers (emit from worker thread; Qt will queue to GUI)
    def _emit_started(self, url: str):
        try:
            self.started.emit(url)
        except Exception:
            pass

    def _emit_finished(self, url: str, path: str):
        try:
            self.finished.emit(url, path)
        except Exception:
            pass

    def _emit_error(self, url: str, msg: str):
        try:
            self.error.emit(url, msg)
        except Exception:
            pass
