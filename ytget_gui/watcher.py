# File: ytget_gui/watcher.py
"""Clipboard watcher: turns copied links into queue items.

Design notes
------------
* Both `QClipboard.dataChanged` *and* a poll timer are used. The signal alone
  is unreliable: on Windows it can be missed while another process holds the
  clipboard open, and on X11 it does not fire for some applications at all.
  The poll is the safety net, the signal is what makes it feel instant.
* Every pass is compared against the previous clipboard *text*, so re-copying
  the same link intentionally still works after the seen-list is cleared,
  while a clipboard that merely reports a change does not re-enqueue.
* Classification is host-based (via validators/sites), never substring-based,
  so `https://evil.example/?x=youtube.com` cannot pick up the YouTube format
  preference.
"""

from __future__ import annotations

import logging
import re
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QGuiApplication

from ytget_gui.settings import AppSettings
from ytget_gui.sites import is_site_enabled, site_key_for
from ytget_gui.utils.validators import (
    is_playlist_url,
    is_spotify_url,
    is_supported_url,
    is_youtube_music_url,
    is_youtube_url,
)

log = logging.getLogger(__name__)

# Categories, in the order they are tested.
CATEGORY_YTMUSIC = "ytmusic"
CATEGORY_YOUTUBE = "youtube"
CATEGORY_SPOTIFY = "spotify"
CATEGORY_OTHER = "other"

CATEGORY_LABELS: Dict[str, str] = {
    CATEGORY_YOUTUBE: "YouTube",
    CATEGORY_YTMUSIC: "YouTube Music",
    CATEGORY_SPOTIFY: "Spotify",
    CATEGORY_OTHER: "other sites",
}

# Settings key holding the preferred format label per category.
CATEGORY_SETTING_KEYS: Dict[str, str] = {
    CATEGORY_YOUTUBE: "WATCHER_FORMAT_YOUTUBE",
    CATEGORY_YTMUSIC: "WATCHER_FORMAT_YTMUSIC",
    CATEGORY_SPOTIFY: "WATCHER_FORMAT_SPOTIFY",
    CATEGORY_OTHER: "WATCHER_FORMAT_OTHER",
}

_URL_RE = re.compile(r"https?://[^\s<>\"'\\|]+", re.IGNORECASE)
# Punctuation that is almost always sentence/markup noise rather than URL.
_TRAILING_NOISE = ".,;:!?'\"\u2026\u201d\u2019)]}>"

# Hard cap per clipboard change, so copying a whole page of links cannot
# enqueue hundreds of items (and fire hundreds of metadata fetches) at once.
MAX_URLS_PER_PASS = 25
# Bound on the de-duplication memory.
_MAX_SEEN = 500


def extract_urls(text: str) -> List[str]:
    """Pull every plausible http(s) URL out of arbitrary clipboard text."""
    if not text:
        return []
    found: List[str] = []
    seen: set[str] = set()
    for raw in _URL_RE.findall(text):
        candidate = raw.rstrip(_TRAILING_NOISE)
        # Keep a balanced trailing paren (common in wiki-style links).
        if candidate.count("(") > candidate.count(")") and raw.endswith(")"):
            candidate = f"{candidate})"
        if not is_supported_url(candidate) or candidate in seen:
            continue
        seen.add(candidate)
        found.append(candidate)
    return found


def classify(url: str) -> str:
    if is_youtube_music_url(url):
        return CATEGORY_YTMUSIC
    if is_youtube_url(url):
        return CATEGORY_YOUTUBE
    if is_spotify_url(url):
        return CATEGORY_SPOTIFY
    return CATEGORY_OTHER


class ClipboardWatcher(QObject):
    """Watches the clipboard and reports URLs with a per-category format.

    Emits `urls_ready` with a list of `(url, format_label)` pairs. An empty
    format label means "whatever the main window's format box is set to",
    which keeps the watcher from overriding a deliberate manual choice.
    """

    urls_ready = Signal(list)          # [(url, format_label), ...]
    unlisted_ready = Signal(list)      # [(url, format_label), ...] needing consent
    message = Signal(str, str)         # text, level ("Info"/"Warning")
    running_changed = Signal(bool)

    def __init__(self, settings: AppSettings, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self._running = False
        self._last_text: str = ""
        # deque, not list: _remember() evicts from the front, and list.pop(0)
        # is O(n) in the number of remembered URLs.
        self._seen: Deque[str] = deque()
        self._seen_set: set[str] = set()

        self._timer = QTimer(self)
        self._timer.setSingleShot(False)
        self._timer.timeout.connect(self._check)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    def _clipboard(self):
        return QGuiApplication.clipboard()

    def _interval_ms(self) -> int:
        seconds = max(1, min(60, int(getattr(self.settings, "WATCHER_POLL_SECONDS", 2))))
        return seconds * 1000

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, *, announce: bool = True) -> bool:
        clipboard = self._clipboard()
        if clipboard is None:
            self.message.emit("No clipboard is available on this system.", "Warning")
            return False
        if self._running:
            self._timer.setInterval(self._interval_ms())
            return True

        # Adopt the current clipboard contents as the baseline instead of
        # enqueuing whatever happened to be copied before the watcher was
        # switched on.
        self._last_text = self._safe_text()
        try:
            clipboard.dataChanged.connect(self._check)
        except (RuntimeError, TypeError):
            log.debug("Clipboard dataChanged unavailable; polling only", exc_info=True)
        self._timer.start(self._interval_ms())
        self._running = True
        self.running_changed.emit(True)
        if announce:
            self.message.emit(
                "\U0001f4cb Clipboard watcher is on. Copy a link to queue it.", "Info"
            )
        return True

    def stop(self, *, announce: bool = True) -> None:
        if not self._running:
            return
        self._timer.stop()
        clipboard = self._clipboard()
        if clipboard is not None:
            try:
                clipboard.dataChanged.disconnect(self._check)
            except (RuntimeError, TypeError):
                pass
        self._running = False
        self.running_changed.emit(False)
        if announce:
            self.message.emit("\U0001f4cb Clipboard watcher is off.", "Info")

    def set_enabled(self, enabled: bool, *, announce: bool = True) -> bool:
        """Single entry point used by the tray, the menu and Preferences."""
        if enabled:
            started = self.start(announce=announce)
            self.settings.CLIPBOARD_WATCHER_ENABLED = bool(started)
            return started
        self.stop(announce=announce)
        self.settings.CLIPBOARD_WATCHER_ENABLED = False
        return False

    def apply_settings(self) -> None:
        """Re-sync with settings after Preferences is saved."""
        if self._running:
            self._timer.setInterval(self._interval_ms())
        wanted = bool(getattr(self.settings, "CLIPBOARD_WATCHER_ENABLED", False))
        if wanted != self._running:
            self.set_enabled(wanted)

    def forget_history(self) -> None:
        self._seen.clear()
        self._seen_set.clear()
        self._last_text = self._safe_text()

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def _safe_text(self) -> str:
        clipboard = self._clipboard()
        if clipboard is None:
            return ""
        try:
            return clipboard.text() or ""
        except RuntimeError:
            return ""

    def _remember(self, url: str) -> None:
        self._seen.append(url)
        self._seen_set.add(url)
        while len(self._seen) > _MAX_SEEN:
            self._seen_set.discard(self._seen.popleft())

    def _format_label_for(self, category: str) -> str:
        key = CATEGORY_SETTING_KEYS.get(category, "")
        label = str(getattr(self.settings, key, "") or "")
        # A label saved by an older build (or a renamed preset) must not be
        # handed to the queue as a bogus format code.
        if label and label not in self.settings.RESOLUTIONS:
            log.debug("Watcher format %r for %s no longer exists", label, category)
            return ""
        return label

    def _unlisted_policy(self) -> str:
        """Policy for sites outside the curated list.

        The pre-policy builds only had a boolean allowlist switch, so a
        config carrying WATCHER_ONLY_KNOWN_SITES=True is honoured as
        "block" rather than silently loosening to the new default.
        """
        policy = str(getattr(self.settings, "WATCHER_UNLISTED_POLICY", "allow") or "allow")
        if policy not in ("allow", "ask", "block"):
            policy = "allow"
        if policy == "allow" and bool(
            getattr(self.settings, "WATCHER_ONLY_KNOWN_SITES", False)
        ):
            return "block"
        return policy

    def accept_unlisted(self, urls: List[str]) -> None:
        """Mark consented links as seen so they are not offered again."""
        for url in urls:
            self._remember(url)

    def note_urls(self, urls: List[str]) -> None:
        """Record links queued outside the watcher (paste and queue).

        The clipboard baseline is re-synced as well, so the next poll
        does not treat the text that was just handled as a new change.
        """
        for url in urls:
            self._remember(url)
        self._last_text = self._safe_text()

    def _check(self) -> None:
        if not self._running:
            return

        text = self._safe_text()
        if not text or text == self._last_text:
            return
        self._last_text = text

        urls = extract_urls(text)
        if not urls:
            return

        policy = self._unlisted_policy()
        skip_playlists = bool(getattr(self.settings, "WATCHER_SKIP_PLAYLISTS", False))
        ignore_dupes = bool(getattr(self.settings, "WATCHER_IGNORE_DUPLICATES", True))
        enabled_sites = list(getattr(self.settings, "WATCHER_ENABLED_SITES", []) or [])

        batch: List[Tuple[str, str]] = []
        needs_consent: List[Tuple[str, str]] = []
        rejected_site = 0
        for url in urls[:MAX_URLS_PER_PASS]:
            if ignore_dupes and url in self._seen_set:
                continue
            if skip_playlists and is_playlist_url(url):
                continue
            category = classify(url)
            label = self._format_label_for(category)
            if policy != "allow" and not is_site_enabled(url, enabled_sites):
                if policy == "block":
                    rejected_site += 1
                    continue
                # "ask": the window prompts once per batch. Not remembered
                # here, so declining and re-copying asks again.
                needs_consent.append((url, label))
                continue
            batch.append((url, label))
            self._remember(url)

        if len(urls) > MAX_URLS_PER_PASS:
            self.message.emit(
                f"Clipboard held {len(urls)} links; only the first "
                f"{MAX_URLS_PER_PASS} were queued.",
                "Warning",
            )
        if rejected_site:
            self.message.emit(
                f"Watcher ignored {rejected_site} link(s) from sites that are not "
                "enabled in Preferences \u203a Watcher.",
                "Info",
            )
        if batch:
            self.urls_ready.emit(batch)
        if needs_consent:
            self.unlisted_ready.emit(needs_consent)
