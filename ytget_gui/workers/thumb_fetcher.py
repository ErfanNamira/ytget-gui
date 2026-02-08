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

    def run(self):
        self.started.emit(self.url)
        try:
            # Optional cookie refresh
            try:
                if getattr(self.settings, "COOKIES_AUTO_REFRESH", False) and getattr(self.settings, "COOKIES_FROM_BROWSER", ""):
                    ok, msg = CookieManager.refresh_before_download(self.settings)
                    if ok:
                        exported_path = getattr(self.settings, "COOKIES_PATH", None)
                        if not exported_path or str(exported_path) == "":
                            exported_path = Path(getattr(self.settings, "BASE_DIR", Path("."))) / "cookies.txt"
                        self.settings.COOKIES_PATH = Path(exported_path)
                        from datetime import datetime
                        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
                        self.settings.COOKIES_LAST_IMPORTED = ts
                        if hasattr(self.settings, "save_config"):
                            try:
                                self.settings.save_config()
                            except Exception:
                                pass
                    else:
                        self.error.emit(self.url, f"Cookies refresh failed: {msg}")
            except Exception as e:
                self.error.emit(self.url, f"Cookies refresh exception: {e}")

            thumb_url, video_id, is_playlist = self._extract_thumbnail_url()
            if not thumb_url:
                if video_id:
                    thumb_url = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
                else:
                    self.error.emit(self.url, "No thumbnail URL discovered")
                    self.finished.emit(self.url, "")
                    return

            base_name = video_id or hashlib.sha1(self.url.encode("utf-8")).hexdigest()
            safe = _safe_name(base_name)
            ext_guess = ".jpg"
            m = re.search(r"\.([a-zA-Z0-9]{2,6})(?:[?#]|$)", thumb_url)
            if m:
                ext_guess = "." + m.group(1).lower()
            target = self.cache_dir / f"{safe}{ext_guess}"

            try:
                if target.exists() and target.stat().st_size > 0:
                    self.finished.emit(self.url, str(target))
                    return
            except Exception:
                pass

            # Try requests first
            try:
                saved = self._download_with_requests(thumb_url, target)
                if saved:
                    self.finished.emit(self.url, str(saved))
                    return
            except Exception as e:
                self.error.emit(self.url, f"requests download exception: {e}")

            # Fallback to yt-dlp approach
            try:
                saved = self._download_with_ytdlp(thumb_url, target)
                if saved:
                    self.finished.emit(self.url, str(saved))
                    return
            except Exception as e:
                self.error.emit(self.url, f"yt-dlp fallback exception: {e}")
                self.finished.emit(self.url, "")
                return

            self.error.emit(self.url, "Failed to download thumbnail")
            self.finished.emit(self.url, "")
        except Exception as e:
            self.error.emit(self.url, f"Unexpected error: {e}")
            self.finished.emit(self.url, "")

    def _canonical_watch_url(self, url: str) -> str:
        """
        If the URL contains a 'v' query parameter, return a canonical watch URL
        (https://www.youtube.com/watch?v=<id>) to avoid yt-dlp confusion with extra params.
        Otherwise return the original URL.
        """
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

    def _extract_thumbnail_url(self) -> Tuple[Optional[str], Optional[str], bool]:
        """
        Run yt-dlp to print JSON metadata and extract a thumbnail URL.
        Handles both 'thumbnail' (string) and 'thumbnails' (list) fields.
        Returns (thumbnail_url or None, video_id or None, is_playlist_flag)
        """
        try:
            # Prefer a canonical watch URL when possible to avoid playlist/watch param issues
            url_for_metadata = self._canonical_watch_url(self.url)

            cmd: List[str] = [
                str(self.settings.YT_DLP_PATH),
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

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=False,
                check=False,
                timeout=30,
                startupinfo=startupinfo,
                env=env,
            )

            stdout = (proc.stdout or b"").decode("utf-8", errors="replace")
            stderr = (proc.stderr or b"").decode("utf-8", errors="replace")

            if proc.returncode != 0 and not stdout:
                stderr_msg = stderr.strip()
                raise RuntimeError(stderr_msg or "yt-dlp failed to extract metadata")

            output = stdout.strip()
            if not output:
                return None, None, False

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

            return thumbnail, video_id, is_playlist
        except subprocess.TimeoutExpired:
            self.error.emit(self.url, "yt-dlp metadata extraction timed out")
            return None, None, False
        except Exception as e:
            try:
                self.error.emit(self.url, f"yt-dlp metadata extraction error: {e}")
            except Exception:
                pass
            return None, None, False

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
                    self.error.emit(self.url, f"HTTP error {getattr(r, 'status_code', '')}: {e}")
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
                            self.error.emit(self.url, f"Failed to move temp thumbnail file: {e}")
                            return None
                        try:
                            tmp_path.unlink()
                        except Exception:
                            pass

                if final.exists() and final.stat().st_size > 0:
                    return final
                else:
                    self.error.emit(self.url, f"Downloaded thumbnail file missing or empty: {final}")
                    return None
        except RequestException as e:
            self.error.emit(self.url, f"requests exception: {e}")
            return None
        except Exception as e:
            self.error.emit(self.url, f"unexpected error during requests download: {e}")
            return None

    def _download_with_ytdlp(self, thumb_url: str, target: Path) -> Optional[Path]:
        try:
            out_dir = str(target.parent)
            base = target.stem
            out_template = str(Path(out_dir) / (base + "%(ext)s"))

            # Prefer canonical watch URL when invoking yt-dlp to write thumbnail
            url_for_metadata = self._canonical_watch_url(self.url)

            cmd: List[str] = [
                str(self.settings.YT_DLP_PATH),
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

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=False,
                check=False,
                timeout=60,
                startupinfo=startupinfo,
                env=env,
            )

            _out = (proc.stdout or b"").decode("utf-8", errors="replace")
            _err = (proc.stderr or b"").decode("utf-8", errors="replace")
            if proc.returncode != 0:
                self.error.emit(self.url, f"yt-dlp returned code {proc.returncode}: {_err.strip()}")

            candidates = list(Path(out_dir).glob(base + ".*"))
            for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"):
                for c in candidates:
                    if c.suffix.lower() == ext:
                        try:
                            final = target.with_suffix(ext)
                            try:
                                c.replace(final)
                                return final
                            except Exception:
                                return c
                        except Exception:
                            return c
            if candidates:
                return candidates[0]
            return None
        except subprocess.TimeoutExpired:
            self.error.emit(self.url, "yt-dlp thumbnail write timed out")
            return None
        except Exception as e:
            self.error.emit(self.url, f"yt-dlp thumbnail write error: {e}")
            return None

    def _derive_referer(self, url: str) -> str:
        try:
            if not url:
                return ""
            parts = url.split("/")
            if len(parts) >= 3:
                host = parts[0] + "//" + parts[2]
                return host
        except Exception:
            pass
        return ""


def fetch_thumbnail_sync(url: str, cache_dir: Path, settings: AppSettings, timeout: int = 20) -> Tuple[Optional[str], Optional[str]]:
    worker = ThumbFetcher(url, cache_dir, settings, timeout)
    thumb_url, video_id, is_playlist = worker._extract_thumbnail_url()
    if not thumb_url and not video_id:
        return None, "No thumbnail metadata found"
    if not thumb_url and video_id:
        thumb_url = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
    base_name = video_id or hashlib.sha1(url.encode("utf-8")).hexdigest()
    safe = _safe_name(base_name)
    ext_guess = ".jpg"
    m = re.search(r"\.([a-zA-Z0-9]{2,6})(?:[?#]|$)", thumb_url or "")
    if m:
        ext_guess = "." + m.group(1).lower()
    target = Path(cache_dir) / f"{safe}{ext_guess}"
    saved = worker._download_with_requests(thumb_url, target)
    if saved:
        return str(saved), None
    saved = worker._download_with_ytdlp(thumb_url, target)
    if saved:
        return str(saved), None
    return None, "Failed to download thumbnail"
