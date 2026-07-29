# File: ytget_gui/workers/ssl_utils.py
"""
Centralized SSL/proxy resolution for MITM-style local proxies
(e.g. https://github.com/patterniha/MITM-DomainFronting via v2rayN).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple, Union

RequestsVerify = Union[bool, str]


def resolve_ssl_config(settings) -> Tuple[RequestsVerify, List[str], Dict[str, str]]:
    """
    Returns:
      requests_verify: value to pass as `verify=` to requests.get/Session
                        (True, False, or a path string to a CA bundle/cert)
      ytdlp_extra_args: list of extra CLI args to extend a yt-dlp command with
      env_overrides:    dict of env vars to merge into a subprocess's env so
                        that yt-dlp/ffmpeg's own TLS stacks (and any nested
                        Python/OpenSSL/libcurl trust store lookups) also trust
                        the custom CA, instead of only the `requests` calls
                        made directly in this process.
    """
    raw_ca = str(getattr(settings, "CUSTOM_CA_CERT", "") or "").strip()
    ignore_ssl = bool(getattr(settings, "IGNORE_SSL_ERRORS", False))

    ca_path = None
    if raw_ca:
        try:
            p = Path(raw_ca).expanduser()
            if p.is_file():
                ca_path = str(p)
        except Exception:
            ca_path = None

    if ca_path:
        requests_verify: RequestsVerify = ca_path
    elif ignore_ssl:
        requests_verify = False
    else:
        requests_verify = True

    ytdlp_extra_args: List[str] = []
    if ca_path or ignore_ssl:
        ytdlp_extra_args.append("--no-check-certificates")

    env_overrides: Dict[str, str] = {}
    if ca_path:
        # Covers Python's ssl module, requests/urllib3, and libcurl-based
        # tools that yt-dlp/ffmpeg may shell out to or link against.
        env_overrides["SSL_CERT_FILE"] = ca_path
        env_overrides["REQUESTS_CA_BUNDLE"] = ca_path
        env_overrides["CURL_CA_BUNDLE"] = ca_path

    return requests_verify, ytdlp_extra_args, env_overrides


_warned_insecure = False


def maybe_suppress_insecure_warning(requests_verify: RequestsVerify) -> None:
    """
    Call once before doing a requests.get(..., verify=requests_verify) when
    requests_verify may be False, to avoid spamming InsecureRequestWarning
    on every single request.
    """
    global _warned_insecure
    if requests_verify is False and not _warned_insecure:
        try:
            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass
        _warned_insecure = True
