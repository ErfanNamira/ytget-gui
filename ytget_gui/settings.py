# File: ytget_gui/settings.py

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Pattern

from ytget_gui.utils.paths import (
    get_base_path,
    executable_name,
    which_or_path,
    default_downloads_dir,
)

from ytget_gui.spotdl_settings import SpotDLSettings

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

@dataclass
class AppSettings:
    VERSION: str = "2.7.9"
    APP_NAME: str = "YTGet"
    GITHUB_URL: str = "https://github.com/ErfanNamira/ytget-gui"

    BASE_DIR: Path = field(default_factory=get_base_path)
    INTERNAL_DIR: Path = field(init=False)
    DOWNLOADS_DIR: Path = field(default_factory=default_downloads_dir)
    CONFIG_PATH: Path = field(init=False)
    COOKIES_PATH: Path = field(init=False)
    ARCHIVE_PATH: Path = field(init=False)

    YT_DLP_PATH: Path = field(init=False)
    FFMPEG_PATH: Path = field(init=False)
    FFPROBE_PATH: Path = field(init=False)
    PHANTOMJS_PATH: Path = field(init=False)
    DENO_PATH: Path = field(init=False)

    OUTPUT_TEMPLATE: str = field(init=False)
    PLAYLIST_TEMPLATE: str = field(init=False)

    YOUTUBE_URL_PATTERN: Pattern = field(
        default_factory=lambda: re.compile(
            r"^(https?://)?(www\.|m\.)?(youtube\.com|youtu\.be|music\.youtube\.com)/.+",
            re.IGNORECASE,
        )
    )

    RESOLUTIONS: Dict[str, str] = field(
        default_factory=lambda: {
            # --- YouTube-optimized presets ---
            # Built via AppSettings._video_format_chain() -- see that method
            # for why this replaced the old hard-coded itag pairs (251+271
            # etc): those itags don't exist on every video, and the fallback
            # they had ("bestvideo[height<=N]+bestaudio") carried no codec
            # or protocol preference, so it could -- and did -- resolve to
            # an HLS stream capped below the requested height.
            "🎬 YouTube 4320p (8K)": AppSettings._video_format_chain(4320),
            "🎬 YouTube 2160p (4K)": AppSettings._video_format_chain(2160),
            "🎥 YouTube 1440p (QHD)": AppSettings._video_format_chain(1440),
            "🎥 YouTube 1080p (FHD)": AppSettings._video_format_chain(1080),
            "📱 YouTube 720p (HD)":  AppSettings._video_format_chain(720),
            "📱 YouTube 480p (SD)":  AppSettings._video_format_chain(480),

            # --- Universal presets (stricter, work across any site supported by yt-dlp) ---
            # Same codec/protocol-aware chain as above, with an added width
            # cap so oddly-cropped/anamorphic sources don't sneak past the
            # intended resolution tier on non-YouTube sites.
            "🌐 Universal 4320p (8K)": AppSettings._video_format_chain(4320, width=7680),
            "🌐 Universal 2160p (4K)": AppSettings._video_format_chain(2160, width=3840),
            "🌐 Universal 1440p (QHD)": AppSettings._video_format_chain(1440, width=2560),
            "🌐 Universal 1080p (FHD)": AppSettings._video_format_chain(1080, width=1920),
            "🌐 Universal 720p (HD)":   AppSettings._video_format_chain(720, width=1280),
            "🌐 Universal 480p (SD)":   AppSettings._video_format_chain(480, width=854),

            # --- Audio / playlist presets (unchanged) ---
            "🎵 Single Audio (MP3)": "bestaudio",
            "🎧 Single Audio (FLAC)": "audio_flac",
            "🎧 Single Audio (Opus)": "audio_opus",
            "🎶 Audio Playlist (MP3 – YouTube/Music)": "playlist_mp3",
            "🎶 Audio Playlist (Opus – YouTube/Music)": "playlist_opus",

            # --- Spotify via SpotDL ---
            "🎸 Spotify (via SpotDL)": "spotify",
        }
    )

    PROXY_URL: str = ""
    IGNORE_SSL_ERRORS: bool = False
    # Path to a self-signed CA certificate to trust explicitly (e.g. the
    # mycert.crt you generate yourself for a local MITM/domain-fronting proxy
    # such as https://github.com/patterniha/MITM-DomainFronting). When set,
    # this takes precedence over IGNORE_SSL_ERRORS: TLS validation stays on,
    # it just also trusts this one certificate, instead of trusting nothing.
    CUSTOM_CA_CERT: str = ""
    SPONSORBLOCK_CATEGORIES: List[str] = field(default_factory=list)
    CHAPTERS_MODE: str = "embed"       # none|embed|split
    WRITE_SUBS: bool = False
    SUB_LANGS: str = "en"
    WRITE_AUTO_SUBS: bool = False
    CONVERT_SUBS_TO_SRT: bool = False
    ENABLE_ARCHIVE: bool = False
    PLAYLIST_REVERSE: bool = False
    AUDIO_NORMALIZE: bool = False
    ADD_METADATA: bool = True
    LIMIT_RATE: str = ""
    RETRIES: int = 10
    # How many times DownloadWorker will silently re-run the *entire*
    # yt-dlp command after a known-transient failure (expired signed URL /
    # 403, momentarily unavailable format, dropped connection, etc) before
    # giving up on the item. Set to 0 to disable auto-retry entirely.
    AUTO_RETRY_COUNT: int = 3
    # How many times the queue will move a failed item to the back of the
    # queue (instead of dropping it) to try again later, after
    # AUTO_RETRY_COUNT in-process retries have already been exhausted.
    QUEUE_ERROR_RETRIES: int = 2
    ORGANIZE_BY_UPLOADER: bool = False
    FILENAME_FORMAT: str = "default"
    CUSTOM_FILENAME_TEMPLATE: str = ""
    DATEAFTER: str = ""
    COOKIES_FROM_BROWSER: str = ""
    COOKIES_AUTO_REFRESH: bool = False
    COOKIES_LAST_IMPORTED: str = ""
    LIVE_FROM_START: bool = False
    YT_MUSIC_METADATA: bool = False
    PLAYLIST_ITEMS: str = ""
    CLIP_START: str = ""
    CLIP_END: str = ""
    CUSTOM_FFMPEG_ARGS: str = ""
    CROP_AUDIO_COVERS: bool = True
    VIDEO_FORMAT: str = ".mkv"
    # Thumbnail embedding
    WRITE_THUMBNAIL: bool = False
    CONVERT_THUMBNAILS: bool = True
    THUMBNAIL_FORMAT: str = "png"
    EMBED_THUMBNAIL: bool = True
    # HLS preference controls
    PREFER_HLS: bool = True
    HLS_PREFERRED_DOMAINS: List[str] = field(default_factory=list)
    SPOTDL: SpotDLSettings = field(default_factory=SpotDLSettings)    

    def __post_init__(self):
        # Prepare paths
        self.INTERNAL_DIR = (self.BASE_DIR / "_internal").resolve()
        self.CONFIG_PATH = (self.BASE_DIR / "config.json").resolve()
        self.COOKIES_PATH = (self.BASE_DIR / "cookies.txt").resolve()
        self.ARCHIVE_PATH = (self.BASE_DIR / "archive.txt").resolve()

        # Ensure directories exist
        self.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        self.INTERNAL_DIR.mkdir(parents=True, exist_ok=True)

        # Touch files if missing
        if not self.COOKIES_PATH.exists():
            self.COOKIES_PATH.touch()
        if self.ENABLE_ARCHIVE and not self.ARCHIVE_PATH.exists():
            self.ARCHIVE_PATH.touch()

        # Define bundled candidates
        yt_dlp_candidate = self.BASE_DIR / executable_name("yt-dlp")
        ffmpeg_candidate = self.BASE_DIR / executable_name("ffmpeg")
        ffprobe_candidate = self.BASE_DIR / executable_name("ffprobe")
        phantom_candidate = self.BASE_DIR / executable_name("phantomjs")
        deno_candidate = self.BASE_DIR / executable_name("deno")

        # Resolve via ENV override, then system PATH, then bundled
        yt_env = os.getenv("YTGET_YT_DLP_PATH")
        self.YT_DLP_PATH = Path(yt_env) if yt_env and Path(yt_env).exists() \
            else which_or_path(yt_dlp_candidate, executable_name("yt-dlp"))

        ff_env = os.getenv("YTGET_FFMPEG_PATH")
        self.FFMPEG_PATH = Path(ff_env) if ff_env and Path(ff_env).exists() \
            else which_or_path(ffmpeg_candidate, executable_name("ffmpeg"))

        fp_env = os.getenv("YTGET_FFPROBE_PATH")
        self.FFPROBE_PATH = Path(fp_env) if fp_env and Path(fp_env).exists() \
            else which_or_path(ffprobe_candidate, executable_name("ffprobe"))

        ph_env = os.getenv("YTGET_PHANTOMJS_PATH")
        self.PHANTOMJS_PATH = Path(ph_env) if ph_env and Path(ph_env).exists() \
            else which_or_path(phantom_candidate, executable_name("phantomjs"))

        deno_env = os.getenv("YTGET_DENO_PATH")
        self.DENO_PATH = Path(deno_env) if deno_env and Path(deno_env).exists() \
            else which_or_path(deno_candidate, executable_name("deno"))
            
        # Output templates
        self.OUTPUT_TEMPLATE = str((self.DOWNLOADS_DIR / "%(title)s.%(ext)s").resolve())
        self.PLAYLIST_TEMPLATE = str((self.DOWNLOADS_DIR / "%(playlist_index)s - %(title)s.%(ext)s").resolve())

        # Load persisted config last
        self.load_config()

    # -------- Format selection (AV1 -> VP9 -> best, HLS as last resort) --------

    def get_format_for_resolution(self, height: int, audio: str = "bestaudio") -> str:
        """
        Build a yt-dlp format string for an arbitrary height, using the
        exact same chain as the RESOLUTIONS presets (see
        _video_format_chain for the ordering and the reasoning behind it).
        """
        return self._video_format_chain(height, audio=audio)

    @staticmethod
    @lru_cache(maxsize=64)
    def _video_format_chain(
        height: int, width: int | None = None, audio: str = "bestaudio"
    ) -> str:
        """
        Build a yt-dlp format-selector chain, in this order:

          1) AV1 video at or below the target height, DASH/HTTP only.
          2) VP9 video (matches both legacy "vp9" and "vp09.xx" codec
             strings) at or below the target height, DASH/HTTP only.
          3) Best video at or below the target height, still excluding HLS.
          4) Best video at or below the target height, HLS now allowed --
             this only fires when nothing better exists under the cap
             (e.g. the DASH ladder for that video/session is incomplete).
          5) Generic bestvideo+bestaudio with no height cap, in case even
             the height filter can't be satisfied (missing/odd metadata).
          6) "best" -- absolute last resort, whatever yt-dlp can get.

        Every tier before (4) uses "[protocol!*=m3u8]" so a same-or-lower
        DASH/HTTP stream is always tried before an HLS one is ever
        considered. Codec filters use "^=" (starts-with) or "~=" (regex)
        rather than "=" (exact match) because yt-dlp reports codecs like
        "av01.0.05M.08" or "vp09.00.50.08", not the bare "av01"/"vp9" an
        exact-match filter would require -- with "=", these tiers silently
        never match anything and are effectively dead code.

        Cached because the UI can re-request the same (height, width,
        audio) combination many times (e.g. re-opening a dropdown).
        """
        no_hls = "[protocol!*=m3u8]"
        width_filter = f"[width<={width}]" if width else ""

        av1 = f"bestvideo[height<={height}]{width_filter}[vcodec^=av01]{no_hls}+{audio}"
        vp9 = f"bestvideo[height<={height}]{width_filter}[vcodec~='^vp0?9']{no_hls}+{audio}"
        best_no_hls = f"bestvideo[height<={height}]{width_filter}{no_hls}+{audio}"
        best_any_proto = f"bestvideo[height<={height}]{width_filter}+{audio}"
        generic_best = f"bestvideo+{audio}"
        ultimate = "best"

        chain = "/".join([av1, vp9, best_no_hls, best_any_proto, generic_best, ultimate])
        return AppSettings._dedupe_format_chain(chain)

    @staticmethod
    def _dedupe_format_chain(chain: str) -> str:
        seen = set()
        parts: List[str] = []
        for seg in (s.strip() for s in chain.split("/") if s.strip()):
            if seg not in seen:
                parts.append(seg)
                seen.add(seg)
        return "/".join(parts)

    # ---------------------- Persistence ----------------------

    def set_download_path(self, path: Path):
        self.DOWNLOADS_DIR = path.resolve()
        self.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        self.OUTPUT_TEMPLATE = str(self.DOWNLOADS_DIR / "%(title)s.%(ext)s")
        self.PLAYLIST_TEMPLATE = str(self.DOWNLOADS_DIR / "%(playlist_index)s - %(title)s.%(ext)s")
        self.save_config()

    def save_config(self):
        config = {
            "PROXY_URL": self.PROXY_URL,
            "IGNORE_SSL_ERRORS": self.IGNORE_SSL_ERRORS,
            "CUSTOM_CA_CERT": self.CUSTOM_CA_CERT,
            "SPONSORBLOCK_CATEGORIES": self.SPONSORBLOCK_CATEGORIES,
            "CHAPTERS_MODE": self.CHAPTERS_MODE,
            "WRITE_SUBS": self.WRITE_SUBS,
            "SUB_LANGS": self.SUB_LANGS,
            "WRITE_AUTO_SUBS": self.WRITE_AUTO_SUBS,
            "CONVERT_SUBS_TO_SRT": self.CONVERT_SUBS_TO_SRT,
            "ENABLE_ARCHIVE": self.ENABLE_ARCHIVE,
            "PLAYLIST_REVERSE": self.PLAYLIST_REVERSE,
            "AUDIO_NORMALIZE": self.AUDIO_NORMALIZE,
            "ADD_METADATA": self.ADD_METADATA,
            "LIMIT_RATE": self.LIMIT_RATE,
            "RETRIES": self.RETRIES,
            "AUTO_RETRY_COUNT": self.AUTO_RETRY_COUNT,
            "QUEUE_ERROR_RETRIES": self.QUEUE_ERROR_RETRIES,
            "ORGANIZE_BY_UPLOADER": self.ORGANIZE_BY_UPLOADER,
            "FILENAME_FORMAT": self.FILENAME_FORMAT,
            "CUSTOM_FILENAME_TEMPLATE": self.CUSTOM_FILENAME_TEMPLATE,
            "DATEAFTER": self.DATEAFTER,
            "COOKIES_FROM_BROWSER": self.COOKIES_FROM_BROWSER,
            "COOKIES_AUTO_REFRESH": self.COOKIES_AUTO_REFRESH,
            "COOKIES_LAST_IMPORTED": self.COOKIES_LAST_IMPORTED,
            "LIVE_FROM_START": self.LIVE_FROM_START,
            "YT_MUSIC_METADATA": self.YT_MUSIC_METADATA,
            "PLAYLIST_ITEMS": self.PLAYLIST_ITEMS,
            "CLIP_START": self.CLIP_START,
            "CLIP_END": self.CLIP_END,
            "CUSTOM_FFMPEG_ARGS": self.CUSTOM_FFMPEG_ARGS,
            "CROP_AUDIO_COVERS": self.CROP_AUDIO_COVERS,
            "VIDEO_FORMAT": self.VIDEO_FORMAT,
            "WRITE_THUMBNAIL": self.WRITE_THUMBNAIL,
            "CONVERT_THUMBNAILS": self.CONVERT_THUMBNAILS,
            "THUMBNAIL_FORMAT": self.THUMBNAIL_FORMAT,
            "EMBED_THUMBNAIL": self.EMBED_THUMBNAIL,
            "DOWNLOADS_DIR": str(self.DOWNLOADS_DIR),
            "YT_DLP_PATH": str(self.YT_DLP_PATH),
            "FFMPEG_PATH": str(self.FFMPEG_PATH),
            "FFPROBE_PATH": str(self.FFPROBE_PATH),
            "PHANTOMJS_PATH": str(self.PHANTOMJS_PATH),   
            "DENO_PATH": str(self.DENO_PATH),            
            "COOKIES_PATH": str(self.COOKIES_PATH),
            "ARCHIVE_PATH": str(self.ARCHIVE_PATH),
            "PREFER_HLS": self.PREFER_HLS,
            "HLS_PREFERRED_DOMAINS": self.HLS_PREFERRED_DOMAINS,
            "SPOTDL": self.SPOTDL.to_dict(),
        }
        with open(self.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

    def load_config(self):
        if not self.CONFIG_PATH.exists():
            return
        try:
            config = json.loads(self.CONFIG_PATH.read_text(encoding="utf-8"))

            # Basic flags
            self.PROXY_URL = config.get("PROXY_URL", self.PROXY_URL)
            self.IGNORE_SSL_ERRORS = config.get("IGNORE_SSL_ERRORS", self.IGNORE_SSL_ERRORS)
            self.CUSTOM_CA_CERT = config.get("CUSTOM_CA_CERT", self.CUSTOM_CA_CERT)
            self.SPONSORBLOCK_CATEGORIES = config.get("SPONSORBLOCK_CATEGORIES", self.SPONSORBLOCK_CATEGORIES)
            self.CHAPTERS_MODE = config.get("CHAPTERS_MODE", self.CHAPTERS_MODE)
            self.WRITE_SUBS = config.get("WRITE_SUBS", self.WRITE_SUBS)
            self.SUB_LANGS = config.get("SUB_LANGS", self.SUB_LANGS)
            self.WRITE_AUTO_SUBS = config.get("WRITE_AUTO_SUBS", self.WRITE_AUTO_SUBS)
            self.CONVERT_SUBS_TO_SRT = config.get("CONVERT_SUBS_TO_SRT", self.CONVERT_SUBS_TO_SRT)
            self.ENABLE_ARCHIVE = config.get("ENABLE_ARCHIVE", self.ENABLE_ARCHIVE)
            self.PLAYLIST_REVERSE = config.get("PLAYLIST_REVERSE", self.PLAYLIST_REVERSE)
            self.AUDIO_NORMALIZE = config.get("AUDIO_NORMALIZE", self.AUDIO_NORMALIZE)
            self.ADD_METADATA = config.get("ADD_METADATA", self.ADD_METADATA)
            self.LIMIT_RATE = config.get("LIMIT_RATE", self.LIMIT_RATE)
            self.RETRIES = config.get("RETRIES", self.RETRIES)
            self.AUTO_RETRY_COUNT = config.get("AUTO_RETRY_COUNT", self.AUTO_RETRY_COUNT)
            self.QUEUE_ERROR_RETRIES = config.get("QUEUE_ERROR_RETRIES", self.QUEUE_ERROR_RETRIES)
            self.ORGANIZE_BY_UPLOADER = config.get("ORGANIZE_BY_UPLOADER", self.ORGANIZE_BY_UPLOADER)
            self.FILENAME_FORMAT = config.get("FILENAME_FORMAT", self.FILENAME_FORMAT)
            if self.FILENAME_FORMAT not in ("default", "custom", *FILENAME_FORMAT_PRESETS.keys()):
                self.FILENAME_FORMAT = "default"
            self.CUSTOM_FILENAME_TEMPLATE = config.get("CUSTOM_FILENAME_TEMPLATE", self.CUSTOM_FILENAME_TEMPLATE)
            self.DATEAFTER = config.get("DATEAFTER", self.DATEAFTER)
            self.COOKIES_FROM_BROWSER = config.get("COOKIES_FROM_BROWSER", self.COOKIES_FROM_BROWSER)
            self.COOKIES_AUTO_REFRESH = config.get("COOKIES_AUTO_REFRESH", self.COOKIES_AUTO_REFRESH)
            self.COOKIES_LAST_IMPORTED = config.get("COOKIES_LAST_IMPORTED", self.COOKIES_LAST_IMPORTED)
            self.LIVE_FROM_START = config.get("LIVE_FROM_START", self.LIVE_FROM_START)
            self.YT_MUSIC_METADATA = config.get("YT_MUSIC_METADATA", self.YT_MUSIC_METADATA)
            self.PLAYLIST_ITEMS = config.get("PLAYLIST_ITEMS", self.PLAYLIST_ITEMS)
            self.CLIP_START = config.get("CLIP_START", self.CLIP_START)
            self.CLIP_END = config.get("CLIP_END", self.CLIP_END)
            self.CUSTOM_FFMPEG_ARGS = config.get("CUSTOM_FFMPEG_ARGS", self.CUSTOM_FFMPEG_ARGS)
            self.CROP_AUDIO_COVERS = config.get("CROP_AUDIO_COVERS", self.CROP_AUDIO_COVERS)
            self.VIDEO_FORMAT = config.get("VIDEO_FORMAT", self.VIDEO_FORMAT)
            # Thumbnail options
            self.WRITE_THUMBNAIL      = config.get("WRITE_THUMBNAIL", self.WRITE_THUMBNAIL)
            self.CONVERT_THUMBNAILS   = config.get("CONVERT_THUMBNAILS", self.CONVERT_THUMBNAILS)
            self.THUMBNAIL_FORMAT     = config.get("THUMBNAIL_FORMAT", self.THUMBNAIL_FORMAT)
            self.EMBED_THUMBNAIL      = config.get("EMBED_THUMBNAIL", self.EMBED_THUMBNAIL)
            self.PREFER_HLS = config.get("PREFER_HLS", self.PREFER_HLS)
            self.HLS_PREFERRED_DOMAINS = config.get("HLS_PREFERRED_DOMAINS", self.HLS_PREFERRED_DOMAINS)

            spotdl_data = config.get("SPOTDL")
            if isinstance(spotdl_data, dict):
                self.SPOTDL = SpotDLSettings.from_dict(spotdl_data)

            # Override download dir if set
            dl_dir = config.get("DOWNLOADS_DIR")
            if dl_dir:
                self.DOWNLOADS_DIR = Path(dl_dir).resolve()
                self.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
                self.OUTPUT_TEMPLATE = str(self.DOWNLOADS_DIR / "%(title)s.%(ext)s")
                self.PLAYLIST_TEMPLATE = str(self.DOWNLOADS_DIR / "%(playlist_index)s - %(title)s.%(ext)s")

            # Override binary paths if valid
            for key, attr in (
                ("YT_DLP_PATH", "YT_DLP_PATH"),
                ("FFMPEG_PATH", "FFMPEG_PATH"),
                ("FFPROBE_PATH", "FFPROBE_PATH"),
                ("PHANTOMJS_PATH", "PHANTOMJS_PATH"),   
                ("DENO_PATH", "DENO_PATH"),                
                ("COOKIES_PATH", "COOKIES_PATH"),
                ("ARCHIVE_PATH", "ARCHIVE_PATH"),
            ):
                val = config.get(key)
                if val and Path(val).exists():
                    setattr(self, attr, Path(val))

        except Exception as e:
            print(f"Error loading config: {e}")
