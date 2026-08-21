# File: ytget_gui/workers/log_buffer.py
"""Coalescing log buffer for worker output.

Workers can emit thousands of lines per second. Emitting a Qt signal per line
floods the GUI thread's event queue. This batches entries, merges consecutive
runs of the same colour into one signal, and caps how much is released per
flush so a burst cannot stall the UI -- the remainder is requeued in order.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

Entry = Tuple[str, str]  # (text, colour)


class LogBuffer:
    def __init__(
        self,
        *,
        max_entries: int = 1500,
        trim_to: int = 800,
        max_flush_entries: int = 200,
        max_flush_bytes: int = 100 * 1024,
    ) -> None:
        self._entries: List[Entry] = []
        self._max_entries = max_entries
        self._trim_to = trim_to
        self._max_flush_entries = max_flush_entries
        self._max_flush_bytes = max_flush_bytes

    def __len__(self) -> int:
        return len(self._entries)

    def __bool__(self) -> bool:
        return bool(self._entries)

    def add(self, text: str, colour: str) -> None:
        if not text:
            return
        self._entries.append((text, colour))
        if len(self._entries) > self._max_entries:
            # Drop the oldest: under a flood the tail is what matters, and an
            # unbounded buffer is a slow memory leak on long playlists.
            del self._entries[: len(self._entries) - self._trim_to]

    def clear(self) -> None:
        self._entries.clear()

    def drain(self) -> List[Entry]:
        """Return coalesced entries to emit, requeuing anything over the cap."""
        if not self._entries:
            return []

        pending = self._entries
        self._entries = []

        out: List[Entry] = []
        run_colour: Optional[str] = None
        run_parts: List[str] = []
        emitted_bytes = 0
        cutoff: Optional[int] = None

        def flush_run() -> int:
            if run_colour is None or not run_parts:
                return 0
            merged = "\n".join(run_parts)
            out.append((merged, run_colour))
            return len(merged.encode("utf-8", errors="replace"))

        for index, (text, colour) in enumerate(pending):
            if len(out) >= self._max_flush_entries or emitted_bytes > self._max_flush_bytes:
                cutoff = index
                break
            if run_colour is None:
                run_colour, run_parts = colour, [text]
            elif colour == run_colour:
                run_parts.append(text)
            else:
                emitted_bytes += flush_run()
                run_colour, run_parts = colour, [text]

        emitted_bytes += flush_run()

        if cutoff is not None:
            # Requeue by index, not by value: a value-based search could match
            # an earlier identical (text, colour) pair and duplicate or drop
            # output.
            remainder = pending[cutoff:]
            if remainder:
                self._entries[0:0] = remainder

        return out


def coalesce(entries: Sequence[Entry]) -> List[Entry]:
    """Merge consecutive same-colour entries. Used for one-shot flushes."""
    out: List[Entry] = []
    for text, colour in entries:
        if out and out[-1][1] == colour:
            out[-1] = (out[-1][0] + "\n" + text, colour)
        else:
            out.append((text, colour))
    return out
