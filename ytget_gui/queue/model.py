# File: ytget_gui/queue/model.py
"""Queue data model with atomic persistence."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

log = logging.getLogger(__name__)


class Status(str, Enum):
    PENDING = "Pending"
    DOWNLOADING = "Downloading"
    COMPLETED = "Completed"
    ERROR = "Error"
    CANCELLED = "Cancelled"

    @classmethod
    def parse(cls, value: Any) -> "Status":
        try:
            return cls(str(value))
        except ValueError:
            # Legacy queue files used "Queued"/"Skipped"; treat anything
            # unrecognised as runnable rather than dropping the item.
            return cls.PENDING


# An item in a terminal state is never auto-scheduled. CANCELLED belongs here:
# omitting it meant skipping the only item in the queue re-selected that same
# item immediately and re-ran it forever.
TERMINAL_STATUSES = frozenset({Status.COMPLETED, Status.ERROR, Status.CANCELLED})

# Statuses that count as "done" for overall progress.
FINISHED_STATUSES = frozenset({Status.COMPLETED, Status.ERROR, Status.CANCELLED})


@dataclass
class QueueItem:
    url: str
    title: str = ""
    format_code: str = ""
    format_label: str = ""
    status: Status = Status.PENDING
    progress: int = 0
    stage: str = ""
    video_id: str = ""
    thumbnail_url: str = ""
    thumb_path: str = ""
    is_playlist: bool = False
    duration: Optional[float] = None
    uploader: str = ""
    queue_attempts: int = 0
    last_error: str = ""
    added_at: float = field(default_factory=time.time)

    @property
    def display_title(self) -> str:
        return self.title or self.url

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @property
    def is_runnable(self) -> bool:
        return not self.is_terminal

    def reset_for_retry(self) -> None:
        self.status = Status.PENDING
        self.progress = 0
        self.stage = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "format_code": self.format_code,
            "format_label": self.format_label,
            "status": self.status.value,
            "progress": self.progress,
            "video_id": self.video_id,
            "thumbnail_url": self.thumbnail_url,
            "thumb_path": self.thumb_path,
            "is_playlist": self.is_playlist,
            "duration": self.duration,
            "uploader": self.uploader,
            "queue_attempts": self.queue_attempts,
            "last_error": self.last_error,
            "added_at": self.added_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional["QueueItem"]:
        url = str(data.get("url") or "").strip()
        if not url:
            return None

        status = Status.parse(data.get("status", Status.PENDING))
        # A DOWNLOADING item in a persisted queue means the app exited mid-job.
        # It must come back runnable, not stuck showing a frozen progress bar.
        if status is Status.DOWNLOADING:
            status = Status.PENDING

        def as_int(value: Any, default: int = 0) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        duration = data.get("duration")
        return cls(
            url=url,
            title=str(data.get("title") or ""),
            format_code=str(data.get("format_code") or ""),
            format_label=str(data.get("format_label") or ""),
            status=status,
            progress=0 if status is Status.PENDING else as_int(data.get("progress")),
            video_id=str(data.get("video_id") or ""),
            thumbnail_url=str(data.get("thumbnail_url") or ""),
            thumb_path=str(data.get("thumb_path") or ""),
            is_playlist=bool(data.get("is_playlist", False)),
            duration=float(duration) if isinstance(duration, (int, float)) else None,
            uploader=str(data.get("uploader") or ""),
            queue_attempts=as_int(data.get("queue_attempts")),
            last_error=str(data.get("last_error") or ""),
            added_at=float(data.get("added_at") or time.time()),
        )


class QueueModel:
    """Ordered collection of QueueItems with an O(1) URL index.

    MainWindow previously linear-scanned the list on every progress tick and
    thumbnail callback, which is O(n) per event and O(n^2) across a full queue
    -- the main source of UI stutter on long queues.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._items: List[QueueItem] = []
        self._index: Dict[str, QueueItem] = {}
        self.path = Path(path) if path else None

    # -- container protocol -------------------------------------------

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[QueueItem]:
        return iter(self._items)

    def __bool__(self) -> bool:
        return bool(self._items)

    @property
    def items(self) -> Sequence[QueueItem]:
        return tuple(self._items)

    # -- lookup --------------------------------------------------------

    def get(self, url: str) -> Optional[QueueItem]:
        return self._index.get(url)

    def contains(self, url: str) -> bool:
        return url in self._index

    def index_of(self, item: QueueItem) -> int:
        try:
            return self._items.index(item)
        except ValueError:
            return -1

    # -- mutation ------------------------------------------------------

    def add(self, item: QueueItem) -> bool:
        if item.url in self._index:
            return False
        self._items.append(item)
        self._index[item.url] = item
        return True

    def remove(self, url: str) -> Optional[QueueItem]:
        item = self._index.pop(url, None)
        if item is None:
            return None
        try:
            self._items.remove(item)
        except ValueError:
            pass
        return item

    def clear(self) -> None:
        self._items.clear()
        self._index.clear()

    def replace_all(self, items: Iterable[QueueItem]) -> None:
        self.clear()
        for item in items:
            self.add(item)

    def move_to_end(self, item: QueueItem) -> None:
        if self.index_of(item) < 0:
            return
        self._items.remove(item)
        self._items.append(item)

    def move_many(self, urls: Sequence[str], *, to_top: bool, after: int = 0) -> None:
        """Move the given URLs as a block.

        `after` reserves leading slots (used to keep the in-progress item at the
        head when the user sends a selection to the top).
        """
        wanted = [self._index[u] for u in urls if u in self._index]
        if not wanted:
            return
        keys = {id(i) for i in wanted}
        rest = [i for i in self._items if id(i) not in keys]
        if to_top:
            head = rest[:after]
            tail = rest[after:]
            self._items = head + wanted + tail
        else:
            self._items = rest + wanted

    def reorder_by_urls(self, urls: Sequence[str]) -> None:
        """Apply a visual order. Items missing from `urls` keep relative order
        at the end, so a filtered view can never silently drop entries."""
        seen: set[str] = set()
        ordered: List[QueueItem] = []
        for url in urls:
            item = self._index.get(url)
            if item is not None and url not in seen:
                ordered.append(item)
                seen.add(url)
        ordered.extend(i for i in self._items if i.url not in seen)
        self._items = ordered

    def sort_by(self, key: str) -> None:
        if key == "Title":
            self._items.sort(key=lambda i: i.display_title.lower())
        elif key == "Status":
            order = {
                Status.DOWNLOADING: 0,
                Status.PENDING: 1,
                Status.CANCELLED: 2,
                Status.COMPLETED: 3,
                Status.ERROR: 4,
            }
            self._items.sort(key=lambda i: order.get(i.status, 99))
        else:
            self._items.sort(key=lambda i: i.added_at)

    def remove_completed(self) -> List[QueueItem]:
        removed = [i for i in self._items if i.status is Status.COMPLETED]
        for item in removed:
            self.remove(item.url)
        return removed

    # -- scheduling ----------------------------------------------------

    def next_runnable(self) -> Optional[QueueItem]:
        return next((i for i in self._items if i.is_runnable), None)

    def rearm_cancelled(self) -> int:
        """Make previously skipped/stopped items runnable again.

        Called on an explicit Start so the user's own cancellation is respected
        until they ask for the queue to run again.
        """
        count = 0
        for item in self._items:
            if item.status is Status.CANCELLED:
                item.reset_for_retry()
                count += 1
        return count

    def counts(self) -> Dict[str, int]:
        result = {status.value: 0 for status in Status}
        for item in self._items:
            result[item.status.value] += 1
        return result

    def overall_progress(self, current: Optional[QueueItem] = None) -> int:
        """Fractional completion across the queue.

        Counts the in-progress item's own percentage rather than treating each
        item as all-or-nothing, so a single large download still shows movement.
        """
        total = len(self._items)
        if total == 0:
            return 0
        done = sum(1 for i in self._items if i.status in FINISHED_STATUSES)
        fraction = 0.0
        if current is not None and current.status is Status.DOWNLOADING:
            fraction = max(0, min(100, current.progress)) / 100.0
        return int(round(min(1.0, (done + fraction) / total) * 100))

    # -- persistence ---------------------------------------------------

    def save(self, path: Optional[Path] = None) -> bool:
        target = Path(path) if path else self.path
        if target is None:
            return False

        payload = json.dumps(
            [i.to_dict() for i in self._items], indent=2, ensure_ascii=False
        )
        tmp_path: Optional[str] = None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(target.parent), prefix=".queue-", suffix=".tmp"
            )
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            # Atomic: the queue is written after every state change, so a crash
            # mid-write previously produced an unparseable queue.json and the
            # entire queue was lost on next launch.
            os.replace(tmp_path, target)
            tmp_path = None
            return True
        except OSError as exc:
            log.error("Could not save queue: %s", exc)
            return False
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def load(self, path: Optional[Path] = None) -> tuple[int, Optional[str]]:
        """Load from disk. Returns (loaded_count, error_message)."""
        target = Path(path) if path else self.path
        if target is None or not target.is_file():
            return 0, None

        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return 0, f"Could not read {target.name}: {exc}"

        if not isinstance(data, list):
            return 0, f"{target.name} is not a queue list"

        items: List[QueueItem] = []
        for raw in data:
            if not isinstance(raw, dict):
                continue
            item = QueueItem.from_dict(raw)
            if item is not None:
                items.append(item)

        self.replace_all(items)
        return len(items), None
