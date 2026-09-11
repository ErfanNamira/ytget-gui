"""Thread-safe bounded log buffering with predictable per-flush work."""
from __future__ import annotations
from collections import deque
from threading import RLock
from typing import Sequence
Entry = tuple[str, str]

class LogBuffer:
    def __init__(self, *, max_entries=1500, trim_to=800, max_flush_entries=200,
                 max_flush_bytes=100 * 1024):
        self._entries = deque()
        self._lock = RLock()
        self._max_entries = max(1, int(max_entries))
        self._trim_to = max(1, min(self._max_entries, int(trim_to)))
        self._max_flush_entries = max(1, int(max_flush_entries))
        self._max_flush_bytes = max(16, int(max_flush_bytes))

    def __len__(self):
        with self._lock:
            return len(self._entries)

    def __bool__(self):
        return len(self) > 0

    @property
    def flush_threshold(self) -> int:
        """Entry count above which a producer should flush early.

        Matches the per-flush cap, so the buffer never accumulates a backlog
        that a single drain cannot clear.
        """
        return self._max_flush_entries

    def add(self, text, colour):
        if not text:
            return
        text = str(text)
        # UTF-8 encoding was previously done here *and* again for every entry
        # in drain(), making it the dominant per-log-line cost. Measure once,
        # store the size, and skip encoding entirely for lines that cannot
        # reach the cap (UTF-8 uses at most 4 bytes per character).
        if len(text) * 4 > self._max_flush_bytes:
            raw = text.encode("utf-8", errors="replace")
            size = len(raw)
            if size > self._max_flush_bytes:
                text = raw[:self._max_flush_bytes - 4].decode("utf-8", errors="ignore") + "…"
                size = len(text.encode("utf-8", errors="replace"))
        else:
            size = len(text)
        with self._lock:
            self._entries.append((text, colour, size))
            if len(self._entries) > self._max_entries:
                while len(self._entries) > self._trim_to:
                    self._entries.popleft()

    def clear(self):
        with self._lock:
            self._entries.clear()

    def drain(self):
        batch, size = [], 0
        with self._lock:
            while self._entries and len(batch) < self._max_flush_entries:
                cost = self._entries[0][2] + (1 if batch else 0)
                if batch and size + cost > self._max_flush_bytes:
                    break
                text, colour, _cost = self._entries.popleft()
                batch.append((text, colour))
                size += cost
        return coalesce(batch)

def coalesce(entries: Sequence[Entry]) -> list[Entry]:
    out = []
    colour, parts = None, []
    for text, current in entries:
        if parts and current != colour:
            out.append(("\n".join(parts), colour))
            parts = []
        colour = current
        parts.append(text)
    if parts:
        out.append(("\n".join(parts), colour))
    return out
