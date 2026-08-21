# File: ytget_gui/workers/ssl_utils.py
"""Centralised TLS trust resolution.

Supports local MITM/domain-fronting proxies by trusting one user-supplied CA
certificate instead of disabling verification wholesale.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Dict, List, Tuple, Union

log = logging.getLogger(__name__)

RequestsVerify = Union[bool, str]

_warn_lock = threading.Lock()
_warned_insecure = False


def resolve_ssl_config(settings) -> Tuple[RequestsVerify, List[str], Dict[str, str]]:
    """Return (requests `verify=` value, yt-dlp CLI args, env overrides).

    A configured, existing CUSTOM_CA_CERT wins over IGNORE_SSL_ERRORS:
    verification stays on and that one certificate is added to the trust set.
    The env overrides matter because yt-dlp, ffmpeg and any nested
    Python/OpenSSL/libcurl consumer each consult their own trust store -- only
    setting `verify=` would fix the in-process `requests` calls and leave every
    subprocess failing its handshake.
    """
    raw_ca = str(getattr(settings, "CUSTOM_CA_CERT", "") or "").strip()
    ignore_ssl = bool(getattr(settings, "IGNORE_SSL_ERRORS", False))

    ca_path: str | None = None
    if raw_ca:
        try:
            candidate = Path(raw_ca).expanduser()
            if candidate.is_file():
                ca_path = str(candidate)
            else:
                log.warning("CUSTOM_CA_CERT does not exist: %s", candidate)
        except OSError as exc:
            log.warning("CUSTOM_CA_CERT unusable: %s", exc)

    if ca_path:
        verify: RequestsVerify = ca_path
    elif ignore_ssl:
        verify = False
    else:
        verify = True

    ytdlp_args: List[str] = []
    if ca_path or ignore_ssl:
        # yt-dlp has no "extra CA" switch, so a custom CA still requires
        # relaxing its own check; the env vars below restore real trust for
        # everything that honours them.
        ytdlp_args.append("--no-check-certificates")

    env: Dict[str, str] = {}
    if ca_path:
        env["SSL_CERT_FILE"] = ca_path
        env["REQUESTS_CA_BUNDLE"] = ca_path
        env["CURL_CA_BUNDLE"] = ca_path

    return verify, ytdlp_args, env


def maybe_suppress_insecure_warning(verify: RequestsVerify) -> None:
    """Silence urllib3's InsecureRequestWarning once, not per request."""
    global _warned_insecure
    if verify is not False:
        return
    with _warn_lock:
        if _warned_insecure:
            return
        _warned_insecure = True
    try:
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception as exc:  # noqa: BLE001
        log.debug("Could not disable urllib3 warnings: %s", exc)
