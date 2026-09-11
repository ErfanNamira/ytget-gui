# File: ytget_gui/utils/text.py
"""Small text helpers shared by the UI and workers."""

from __future__ import annotations

import hashlib
import re

_WS_RE = re.compile(r"\s+")
_UNSAFE_CACHE_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def short(text: str, n: int = 50, suffix: str = "...") -> str:
    """Truncate for log lines."""
    text = text or ""
    return text if len(text) <= n else text[:n] + suffix


def clamp(text: str, n: int) -> str:
    """Truncate for UI labels, using a single-character ellipsis."""
    text = text or ""
    return text if len(text) <= n else text[:n] + "\u2026"


def collapse_whitespace(text: str) -> str:
    return _WS_RE.sub(" ", text or "").strip()


def cache_key(value: str, max_len: int = 120) -> str:
    """Filesystem-safe cache filename stem derived from an arbitrary string.

    Long values are truncated and suffixed with a hash so two different long
    inputs can never collide on the same cache file.
    """
    s = (value or "").strip()
    if not s:
        return "unknown"
    s = _UNSAFE_CACHE_CHARS.sub("_", s)
    if len(s) > max_len:
        digest = hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]
        s = f"{s[: max_len - 11]}_{digest}"
    return s


def url_digest(url: str) -> str:
    return hashlib.sha1((url or "").encode("utf-8")).hexdigest()


def repair_mojibake(text: str) -> str:
    """Recover text that was UTF-8 decoded as cp1252 and re-encoded.

    Several source files in the previous revision carried literals like
    "\u00e2\u0153\u2026 Download Finished" (a mangled "\u2705"). This reverses that
    specific round-trip; it returns the input unchanged when the reversal
    isn't applicable, so it is safe to apply blindly.
    """
    if not text:
        return text
    try:
        repaired = text.encode("cp1252", errors="strict").decode("utf-8", errors="strict")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    return repaired


def human_bytes(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(n) < 1024.0:
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024.0
    return f"{n:.1f} PiB"
