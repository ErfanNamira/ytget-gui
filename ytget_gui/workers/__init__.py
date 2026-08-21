# File: ytget_gui/workers/__init__.py
"""Background workers.

Every worker exposes the interface declared in `base.WorkerSignals` so the
queue controller can drive yt-dlp and spotdl jobs without special-casing.
"""

from __future__ import annotations

__all__ = [
    "base",
    "cookies",
    "cover_crop_worker",
    "download_worker",
    "fetch_core",
    "log_buffer",
    "proc",
    "spotdl_worker",
    "ssl_utils",
    "thumb_fetcher",
    "title_fetch_manager",
    "title_fetcher",
]
