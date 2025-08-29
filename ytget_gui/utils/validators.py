# File: ytget_gui/utils/validators.py

from __future__ import annotations
import re

# Matches YouTube watch, share, music, and no-cookie domains:
# - youtube.com
# - youtu.be
# - music.youtube.com
# - youtube-nocookie.com
YOUTUBE_URL_RE = re.compile(
    r'^(?:https?://)?'                                 # optional scheme
    r'(?:www\.|m\.)?'                                  # optional subdomain
    r'(?:youtube\.com|youtu\.be|music\.youtube\.com|'  # standard domains
    r'youtube-nocookie\.com)'                          # YouTube no-cookie
    r'/.*',                                            # rest of path
    re.IGNORECASE
)

def is_youtube_url(text: str) -> bool:
    """
    Return True if the given text is a YouTube URL.

    This strips surrounding whitespace and any trailing slash,
    then tests against a regex that accepts:
      - youtube.com and subpaths
      - youtu.be short links
      - music.youtube.com
      - youtube-nocookie.com
    """
    candidate = text.strip().rstrip('/')
    return bool(YOUTUBE_URL_RE.match(candidate))