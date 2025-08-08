# File: ytget/utils/validators.py
from __future__ import annotations
import re

YOUTUBE_URL_RE = re.compile(
    r"^(https?://)?(www\.|m\.)?(youtube\.com|youtu\.be|music\.youtube\.com)/.+",
    re.IGNORECASE,
)

def is_youtube_url(text: str) -> bool:
    return bool(YOUTUBE_URL_RE.match(text.strip()))