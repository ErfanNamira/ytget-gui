# File: ytget_gui/utils/validators.py

from __future__ import annotations
import re

# Accept any HTTP or HTTPS URL
_ANY_HTTP_URL_RE = re.compile(
    r'^(?:https?://)'          # require scheme http or https
    r'[^ \t\r\n]+'             # rest of URL (no whitespace)
    , re.IGNORECASE
)

# YouTube-only matcher for backward compatibility
_YOUTUBE_URL_RE = re.compile(
    r'^(?:https?://)?'                                 # optional scheme
    r'(?:www\.|m\.)?'                                  # optional subdomain
    r'(?:youtube\.com|youtu\.be|music\.youtube\.com|youtube-nocookie\.com)'
    r'/.*',                                            # rest of path
    re.IGNORECASE
)

def is_supported_url(text: str) -> bool:
    """
    Return True if the given text is a supported URL.
    This implementation accepts any http(s) URL.
    """
    if not text:
        return False
    candidate = text.strip()
    return bool(_ANY_HTTP_URL_RE.match(candidate))

def is_youtube_url(text: str) -> bool:
    """
    Backwards-compatible: returns True only for YouTube-style URLs.
    """
    if not text:
        return False
    candidate = text.strip().rstrip("/")
    return bool(_YOUTUBE_URL_RE.match(candidate))
