# File: ytget_gui/utils/firewall_manager.py
from __future__ import annotations

import os
import subprocess
from typing import Optional, Dict

import requests
from PySide6.QtWidgets import QWidget, QMessageBox

from ytget_gui.settings import AppSettings

def _gather_proxies(settings: AppSettings) -> Dict[str, str]:
    """
    Return a proxies dict for requests, preferring:
      1) settings.PROXY_URL
      2) environment HTTP_PROXY / HTTPS_PROXY
    """
    props = {}
    # 1) User‐configured proxy in AppSettings
    if getattr(settings, "PROXY_URL", None):
        props["http"] = settings.PROXY_URL
        props["https"] = settings.PROXY_URL
        return props

    # 2) Fallback to environment variables
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        val = os.environ.get(key)
        if val:
            scheme = "https" if "https" in key.lower() else "http"
            props[scheme] = val
    return props


def check_network_firewall(parent: Optional[QWidget] = None):
    """
    Every launch:
      • Attempt HTTPS HEAD to YouTube directly.
      • If that fails and a proxy is configured, attempt via proxy.
      • If both fail, warn the user about firewall/proxy settings.
      • Then verify yt-dlp simulate using the same proxy.
    """
    settings = AppSettings()
    proxies = _gather_proxies(settings)

    def _head(url: str, via: bool) -> bool:
        try:
            requests.head(
                url,
                timeout=5,
                proxies=proxies if via else {},
                allow_redirects=True,
            ).raise_for_status()
            return True
        except Exception:
            return False

    # 1) Check direct HTTPS
    direct_ok = _head("https://www.youtube.com", via=False)

    # 2) If direct failed and we have a proxy, try via proxy
    proxied_ok = False
    if not direct_ok and proxies:
        proxied_ok = _head("https://www.youtube.com", via=True)

    # 3) If neither succeeded, warn once per run
    if not direct_ok and not proxied_ok:
        msg = (
            "YTGet cannot reach https://www.youtube.com.\n\n"
            "If your network blocks YouTube, configure a system or app proxy:\n"
            "  • Windows: Settings → Network & Internet → Proxy\n"
            "  • macOS: System Preferences → Network → Proxies\n"
            "  • Linux: your distro’s network settings or env vars\n\n"
            "Then restart YTGet."
        )
        QMessageBox.warning(parent, "Network/Firewall Warning", msg)
        # skip yt-dlp test if no connectivity at all
        return

    # 4) Finally, verify yt-dlp itself can fetch via same proxy
    cmd = [
        "yt-dlp",
        "--quiet",
        "--simulate",
        "--force-ipv4",
        "https://www.youtube.com/watch?v=BaW_jenozKc",
    ]
    env = os.environ.copy()
    # Pass HTTP(S)_PROXY for subprocess if set
    for key in ("HTTP_PROXY", "HTTPS_PROXY"):
        if proxies.get(key.lower()):
            env[key] = proxies[key.lower()]

    try:
        subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            timeout=10,
            check=True,
        )
    except FileNotFoundError:
        QMessageBox.warning(
            parent,
            "yt-dlp Not Found",
            "Could not locate `yt-dlp` on your PATH.\n"
            "Please install yt-dlp or place it alongside the YTGet binary."
        )
    except subprocess.CalledProcessError:
        QMessageBox.warning(
            parent,
            "yt-dlp Blocked",
            "yt-dlp failed to contact YouTube.\n"
            "Ensure your firewall or proxy allows yt-dlp outbound HTTPS."
        )
    except Exception as exc:
        QMessageBox.warning(
            parent,
            "yt-dlp Check Error",
            f"An unexpected error occurred while testing yt-dlp:\n{exc}"
        )