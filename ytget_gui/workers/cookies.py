# File: ytget_gui/workers/cookies.py
"""Browser cookie export to Netscape format.

Cookies are pruned aggressively: a full Google cookie jar produces a request
header large enough for YouTube to answer HTTP 413, so only auth-relevant
names within relevant domains survive, under both a count and a byte budget.
"""

from __future__ import annotations

import http.cookiejar as cookiejar
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence, Tuple

log = logging.getLogger(__name__)

DEFAULT_DOMAINS: Tuple[str, ...] = (
    ".youtube.com",
    "youtube.com",
    ".google.com",
    "google.com",
    "music.youtube.com",
    "youtube-nocookie.com",
)

DEFAULT_WHITELIST_NAMES = frozenset(
    {
        "SID", "HSID", "SSID", "APISID", "SAPISID",
        "__Secure-1PSID", "__Secure-3PSID",
        "__Secure-1PAPISID", "__Secure-3PAPISID",
        "__Secure-3PSIDCC", "SIDCC",
        "LOGIN_INFO", "PREF", "VISITOR_INFO1_LIVE",
        "VISITOR_PRIVACY_METADATA", "YSC", "CONSENT",
    }
)

YOUTUBE_DOMAINS: Tuple[str, ...] = (".youtube.com", "youtube.com", "music.youtube.com")

MAX_COOKIE_VALUE = 2000
MAX_TOTAL_COOKIES = 40
MAX_HEADER_BYTES = 40 * 1024

_ACCESSORS = {
    "firefox": "firefox",
    "ff": "firefox",
    "edge": "edge",
    "msedge": "edge",
    "safari": "safari",
    "opera": "opera",
    "brave": "brave",
    "vivaldi": "vivaldi",
    "chromium": "chromium",
    "chrome": "chrome",
    "whale": "chrome",
}


def _load_browser_cookie3():
    try:
        import browser_cookie3

        return browser_cookie3
    except ImportError:
        return None


def _cookie_bytes(cookies: Sequence[Any]) -> int:
    total = 0
    for c in cookies:
        total += len((getattr(c, "name", "") or "").encode("utf-8"))
        total += len((getattr(c, "value", "") or "").encode("utf-8"))
    return total


def _to_mozilla_jar(cookies: Sequence[Any]) -> cookiejar.MozillaCookieJar:
    jar = cookiejar.MozillaCookieJar()
    for c in cookies:
        try:
            expires = int(c.expires) if getattr(c, "expires", None) else None
        except (TypeError, ValueError):
            expires = None
        domain = getattr(c, "domain", "") or ""
        jar.set_cookie(
            cookiejar.Cookie(
                version=0,
                name=c.name,
                value=c.value,
                port=None,
                port_specified=False,
                domain=domain,
                domain_specified=bool(domain),
                domain_initial_dot=domain.startswith("."),
                path=getattr(c, "path", "/") or "/",
                path_specified=True,
                secure=bool(getattr(c, "secure", False)),
                expires=expires,
                discard=False,
                comment=None,
                comment_url=None,
                rest={"HttpOnly": getattr(c, "httponly", False)},
                rfc2109=False,
            )
        )
    return jar


def _restrict_permissions(path: Path) -> None:
    """Cookies are session credentials; keep them owner-readable only."""
    if os.name == "nt":
        return
    try:
        os.chmod(path, 0o600)
    except OSError as exc:
        log.debug("Could not chmod %s: %s", path, exc)


def _prune(
    cookies: Sequence[Any],
    whitelist: frozenset[str],
) -> List[Any]:
    def keep(c: Any) -> bool:
        name = getattr(c, "name", "") or ""
        value = getattr(c, "value", "") or ""
        domain = getattr(c, "domain", "") or ""
        if len(value) > MAX_COOKIE_VALUE:
            return False
        if name in whitelist:
            return True
        return any(d in domain for d in YOUTUBE_DOMAINS)

    pruned = [c for c in cookies if keep(c)]
    # Whitelisted names first so a count cap never evicts a critical cookie.
    pruned.sort(key=lambda c: 0 if (getattr(c, "name", "") or "") in whitelist else 1)

    if len(pruned) > MAX_TOTAL_COOKIES:
        pruned = pruned[:MAX_TOTAL_COOKIES]

    if _cookie_bytes(pruned) <= MAX_HEADER_BYTES:
        return pruned

    keepers = [c for c in pruned if (getattr(c, "name", "") or "") in whitelist]
    budget = _cookie_bytes(keepers)
    for c in (c for c in pruned if (getattr(c, "name", "") or "") not in whitelist):
        size = len((getattr(c, "name", "") or "").encode("utf-8")) + len(
            (getattr(c, "value", "") or "").encode("utf-8")
        )
        if budget + size > MAX_HEADER_BYTES:
            break
        keepers.append(c)
        budget += size
    return keepers


def export_for_browser(
    browser: str,
    out_path: Path,
    domains: Optional[Iterable[str]] = None,
    *,
    whitelist_names: Optional[Iterable[str]] = None,
) -> Tuple[bool, str]:
    """Export cookies for `browser` into `out_path` (Netscape format)."""
    bc3 = _load_browser_cookie3()
    if bc3 is None:
        return False, "Missing dependency: browser_cookie3 (pip install browser-cookie3)"

    key = (browser or "").strip().lower()
    accessor_name = _ACCESSORS.get(key)
    if accessor_name is None:
        return False, f"Unsupported browser: {browser}"

    accessor = getattr(bc3, accessor_name, None)
    if accessor is None:
        return False, f"browser_cookie3 has no reader for {accessor_name}"

    try:
        jar = accessor()
    except Exception as exc:  # noqa: BLE001 - bc3 raises many browser-specific types
        return False, f"Failed to read {browser} cookies: {exc}"

    wanted = tuple(domains) if domains else DEFAULT_DOMAINS
    filtered = [
        c for c in jar if any(d in (getattr(c, "domain", "") or "") for d in wanted)
    ]
    if not filtered:
        return False, f"No YouTube-related cookies found in {browser}"

    whitelist = frozenset(whitelist_names) if whitelist_names else DEFAULT_WHITELIST_NAMES
    pruned = _prune(filtered, whitelist)
    if not pruned:
        return False, "No usable cookies remained after pruning"

    out_path = Path(out_path)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, f"Cannot create {out_path.parent}: {exc}"

    # Write to a sibling temp file and swap: overwriting cookies.txt in place
    # means a failure mid-write leaves a truncated jar, which yt-dlp reads as
    # "logged out" on the very next download.
    tmp_path: Optional[Path] = None
    try:
        fd, tmp_name = tempfile.mkstemp(dir=str(out_path.parent), prefix=".cookies-")
        os.close(fd)
        tmp_path = Path(tmp_name)
        _to_mozilla_jar(pruned).save(
            str(tmp_path), ignore_discard=True, ignore_expires=True
        )
        _restrict_permissions(tmp_path)
        os.replace(tmp_path, out_path)
        tmp_path = None
    except Exception as exc:  # noqa: BLE001
        return False, f"Failed to save cookies file: {exc}"
    finally:
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

    try:
        size = out_path.stat().st_size
    except OSError:
        size = 0
    return True, f"Wrote {len(pruned)} cookie(s) ({size} bytes) to {out_path}"


def refresh_before_download(settings) -> Tuple[bool, str]:
    """Re-export cookies from the configured browser before a download."""
    browser = str(getattr(settings, "COOKIES_FROM_BROWSER", "") or "").strip()
    if not browser:
        return False, "No browser configured for cookie import"

    target = getattr(settings, "COOKIES_PATH", None)
    if not target or str(target) in ("", "."):
        base = getattr(settings, "BASE_DIR", None) or Path(".")
        target = Path(base) / "cookies.txt"

    return export_for_browser(browser, Path(target))


def record_refresh(settings) -> None:
    """Persist the import timestamp after a successful refresh."""
    try:
        settings.COOKIES_LAST_IMPORTED = datetime.now(timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
        if hasattr(settings, "save_config"):
            settings.save_config()
    except Exception as exc:  # noqa: BLE001 - bookkeeping only
        log.debug("Could not record cookie refresh: %s", exc)
