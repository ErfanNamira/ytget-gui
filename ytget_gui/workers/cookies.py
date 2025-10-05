# File: ytget_gui/workers/cookies.py

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Tuple, List
import http.cookiejar as cookiejar
import os

# Domains relevant to YouTube/Google sessions
DEFAULT_DOMAINS = (
    ".youtube.com",
    "youtube.com",
    ".google.com",
    "google.com",
    "music.youtube.com",
    "youtube-nocookie.com",
)

# Conservative whitelist of cookie names usually required for YouTube auth/context
DEFAULT_WHITELIST_NAMES = {
    "SID",
    "HSID",
    "SSID",
    "APISID",
    "SAPISID",
    "__Secure-3PAPISID",
    "__Secure-3PSID",
    "SIDCC",
    "LOGIN_INFO",
    "PREF",
    "VISITOR_INFO1_LIVE",
    "YSC",
    "CONSENT",
}


def _filter_cookies(jar: Iterable, domains: Iterable[str] = DEFAULT_DOMAINS) -> List:
    out = []
    for c in jar:
        dom = getattr(c, "domain", "") or ""
        if any(d in dom for d in domains):
            out.append(c)
    return out


def _make_mozilla_cookiejar(cookies) -> cookiejar.MozillaCookieJar:
    mc = cookiejar.MozillaCookieJar()
    for c in cookies:
        try:
            expires = int(c.expires) if getattr(c, "expires", None) else None
        except Exception:
            expires = None
        ck = cookiejar.Cookie(
            version=0,
            name=c.name,
            value=c.value,
            port=None,
            port_specified=False,
            domain=c.domain,
            domain_specified=bool(c.domain),
            domain_initial_dot=str(c.domain).startswith("."),
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
        mc.set_cookie(ck)
    return mc


def _safe_chmod(path: Path) -> None:
    try:
        # Restrict file to user-only read/write on POSIX
        if os.name != "nt":
            os.chmod(str(path), 0o600)
    except Exception:
        pass


def _total_bytes_of_cookies(cookies: List) -> int:
    total = 0
    for c in cookies:
        total += len((getattr(c, "name", "") or "").encode("utf-8"))
        total += len((getattr(c, "value", "") or "").encode("utf-8"))
    return total


def _import_browser_cookie3():
    """
    Lazy import helper for browser_cookie3. Returns module or None.
    """
    try:
        import browser_cookie3  # type: ignore
        return browser_cookie3
    except Exception:
        return None


def export_for_browser(
    browser: str,
    out_path: Path,
    domains: Optional[Iterable[str]] = None,
    *,
    whitelist_names: Optional[Iterable[str]] = None,
    max_cookie_value: int = 2000,
    max_total_cookies: int = 40,
) -> Tuple[bool, str]:
    """
    Export cookies from the chosen browser into a Netscape-format file (out_path).
    Prune aggressively to avoid huge Cookie headers that trigger HTTP 413.

    Returns (success, message). Non-exceptional errors are returned as (False, message).
    """
    browser_cookie3 = _import_browser_cookie3()
    if browser_cookie3 is None:
        return False, "Missing dependency: browser_cookie3 (pip install browser_cookie3)"

    key = (browser or "").lower()
    accessor = None
    try:
        if key in ("firefox", "ff"):
            accessor = browser_cookie3.firefox
        elif key in ("edge", "msedge"):
            accessor = browser_cookie3.edge
        elif key in ("safari",):
            accessor = browser_cookie3.safari
        else:
            # default covers chrome and many chromium-based browsers
            accessor = browser_cookie3.chrome
    except Exception:
        accessor = None

    if accessor is None:
        return False, f"Unsupported browser: {browser}"

    try:
        jar = accessor()
    except Exception as e:
        return False, f"Failed to read browser cookies: {e}"

    domains_filter = tuple(domains) if domains else DEFAULT_DOMAINS

    # First pass: domain-based filtering
    filtered = [c for c in jar if any(d in (getattr(c, "domain", "") or "") for d in domains_filter)]
    if not filtered:
        return False, "No YouTube-related cookies found in selected browser"

    # Prune using whitelist and size caps
    wl = set(whitelist_names) if whitelist_names else DEFAULT_WHITELIST_NAMES
    MAX_VAL = int(max_cookie_value) if max_cookie_value and max_cookie_value > 0 else 2000
    MAX_TOTAL = int(max_total_cookies) if max_total_cookies and max_total_cookies > 0 else 40

    def _keep(c) -> bool:
        name = getattr(c, "name", "") or ""
        val = getattr(c, "value", "") or ""
        domain = getattr(c, "domain", "") or ""
        # Drop enormous cookie values outright
        if len(val) > MAX_VAL:
            return False
        # Keep if cookie name is whitelisted
        if name in wl:
            return True
        # Keep if domain is explicitly youtube/google (coverage for unusual names)
        if any(d in domain for d in (".youtube.com", "youtube.com", "music.youtube.com")):
            return True
        return False

    pruned = [c for c in filtered if _keep(c)]
    if not pruned:
        return False, "No usable YouTube cookies after pruning; export would be empty"

    # Prioritize whitelist cookies so critical items appear first
    pruned.sort(key=lambda c: 0 if (getattr(c, "name", "") or "") in wl else 1)

    # Enforce total cookie cap
    if len(pruned) > MAX_TOTAL:
        pruned = pruned[:MAX_TOTAL]

    # Safety: if total header would still be huge, reduce further
    total_bytes = _total_bytes_of_cookies(pruned)
    # If over ~40KB, trim until under the threshold (conservative)
    MAX_HEADER_BYTES = 40 * 1024
    if total_bytes > MAX_HEADER_BYTES:
        # remove non-whitelist cookies from the end until under threshold
        keepers = [c for c in pruned if (getattr(c, "name", "") or "") in wl]
        others = [c for c in pruned if (getattr(c, "name", "") or "") not in wl]
        # gradually append from others until threshold reached
        cur = keepers[:]
        cur_bytes = _total_bytes_of_cookies(cur)
        for c in others:
            cur_bytes += len((getattr(c, "name", "") or "").encode("utf-8"))
            cur_bytes += len((getattr(c, "value", "") or "").encode("utf-8"))
            if cur_bytes > MAX_HEADER_BYTES:
                break
            cur.append(c)
        pruned = cur
        if not pruned:
            return False, "Pruning removed all cookies to keep header size safe"

    mc = _make_mozilla_cookiejar(pruned)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mc.save(str(out_path), ignore_discard=True, ignore_expires=True)
        try:
            _safe_chmod(out_path)
        except Exception:
            pass
    except Exception as e:
        return False, f"Failed to save cookies file: {e}"

    # Report summary
    try:
        size = out_path.stat().st_size
    except Exception:
        size = 0
    return True, f"Wrote {len(pruned)} cookie(s) ({size} bytes) to {out_path}"


def refresh_before_download(settings) -> Tuple[bool, str]:
    """
    Convenience helper called by workers before launching yt-dlp.
    Behavior:
      - If settings.COOKIES_FROM_BROWSER exists and is non-empty, try to export into settings.COOKIES_PATH
        (if provided) or to BASE_DIR/cookies.txt.
    Returns (success, message).
    """
    browser = getattr(settings, "COOKIES_FROM_BROWSER", "") or ""
    if not browser:
        return False, "No browser configured for cookies-from-browser"

    out = getattr(settings, "COOKIES_PATH", None)
    if not out or str(out) == "":
        base = getattr(settings, "BASE_DIR", None) or Path(".")
        out = Path(base) / "cookies.txt"
    else:
        out = Path(out)

    return export_for_browser(browser, out)
