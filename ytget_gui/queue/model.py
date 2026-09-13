# File: ytget_gui/queue/model.py
"""Queue data model with atomic persistence."""

from __future__ import annotations

import json
import logging
import math
import os
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

from ytget_gui.utils.validators import is_supported_url

log = logging.getLogger(__name__)

# Settings keys an individual queue item may override. Everything else is
# global by design; these are the "for this download only" options.
ITEM_OPTION_KEYS = frozenset(
    {"CLIP_START", "CLIP_END", "PLAYLIST_ITEMS", "PLAYLIST_REVERSE"}
)


class Status(str, Enum):
    PENDING = "Pending"
    DOWNLOADING = "Downloading"
    COMPLETED = "Completed"
    ERROR = "Error"
    CANCELLED = "Cancelled"

    @classmethod
    def parse(cls, value: Any) -> "Status":
        if isinstance(value, cls):
            return value
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
    # Approximate download size in bytes (video + merged audio), or None
    # when the site does not advertise one. Never set for playlists.
    filesize: Optional[int] = None
    queue_attempts: int = 0
    last_error: str = ""
    added_at: float = field(default_factory=time.time)
    output_path: str = ""
    output_count: int = 0
    # Quality tag appended to the output filename when another item for
    # the same URL already targets the same container, e.g. "QHD".
    # Empty for the first item of a URL, which keeps the default naming.
    name_suffix: str = ""
    # Per-item settings overrides captured when the item was added (clip
    # range, playlist selection). Applied on top of the settings snapshot
    # handed to the worker, so changing Advanced later -- or adding a
    # second item -- cannot retroactively re-cut an item already queued.
    options: Dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        """Queue identity: the same URL may be queued in several formats.

        Everything that used to be keyed by URL (the model index, the card
        map, the list rows, the controller signals) is keyed by this, so
        adding 1080p and MP3 of one video gives two independent rows.
        """
        return f"{self.url}\n{self.format_code}"

    @property
    def display_title(self) -> str:
        return self.title or self.url

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @property
    def is_runnable(self) -> bool:
        return self.status is Status.PENDING

    @property
    def has_output(self) -> bool:
        """True when a recorded output file still exists on disk.

        Checked live rather than cached: the file may have been moved or
        deleted at any point since the download finished.
        """
        if not self.output_path:
            return False
        try:
            return Path(self.output_path).exists()
        except OSError:
            return False

    @property
    def output_missing(self) -> bool:
        """A path was recorded, but the file is no longer there."""
        return bool(self.output_path) and not self.has_output

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
            "output_path": self.output_path,
            "output_count": self.output_count,
            "filesize": self.filesize,
            "name_suffix": self.name_suffix,
            "options": dict(self.options),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional["QueueItem"]:
        url = str(data.get("url") or "").strip()
        if not is_supported_url(url):
            return None

        status = Status.parse(data.get("status", Status.PENDING))
        # A DOWNLOADING item in a persisted queue means the app exited mid-job.
        # It must come back runnable, not stuck showing a frozen progress bar.
        if status is Status.DOWNLOADING:
            status = Status.PENDING

        def as_int(value: Any, default: int = 0) -> int:
            try:
                return int(value)
            except (TypeError, ValueError, OverflowError):
                return default

        def as_float(value, default=None):
            try:
                n = float(value)
                return n if math.isfinite(n) and n >= 0 else default
            except (TypeError, ValueError, OverflowError):
                return default
        duration = as_float(data.get("duration"))
        playlist = data.get("is_playlist", False)
        return cls(
            url=url,
            title=str(data.get("title") or ""),
            format_code=str(data.get("format_code") or ""),
            format_label=str(data.get("format_label") or ""),
            status=status,
            progress=0 if status is Status.PENDING else max(0, min(100, as_int(data.get("progress")))),
            video_id=str(data.get("video_id") or ""),
            thumbnail_url=str(data.get("thumbnail_url") or ""),
            thumb_path=str(data.get("thumb_path") or ""),
            is_playlist=playlist is True or str(playlist).lower() in ("true", "1"),
            duration=duration,
            uploader=str(data.get("uploader") or ""),
            queue_attempts=max(0, as_int(data.get("queue_attempts"))),
            last_error=str(data.get("last_error") or ""),
            added_at=as_float(data.get("added_at"), time.time()),
            output_path=str(data.get("output_path") or ""),
            output_count=max(0, as_int(data.get("output_count"))),
            filesize=cls._parse_size(data.get("filesize")),
            name_suffix=str(data.get("name_suffix") or "")[:40].strip(),
            options=cls._parse_options(data.get("options")),
        )

    @staticmethod
    def _parse_size(raw: Any) -> Optional[int]:
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return None
        return int(raw) if raw > 0 else None

    @staticmethod
    def _parse_options(raw: Any) -> Dict[str, Any]:
        """Only known override keys with scalar values are accepted.

        queue.json is user-editable and survives upgrades, so an arbitrary
        dict here would be setattr'd straight onto the settings snapshot.
        """
        if not isinstance(raw, dict):
            return {}
        return {
            key: value
            for key, value in raw.items()
            if key in ITEM_OPTION_KEYS and isinstance(value, (str, int, float, bool))
        }


class QueueModel:
    """Ordered collection of QueueItems with an O(1) URL index.

    MainWindow previously linear-scanned the list on every progress tick and
    thumbnail callback, which is O(n) per event and O(n^2) across a full queue
    -- the main source of UI stutter on long queues.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._items: List[QueueItem] = []
        # Keyed by QueueItem.key (url + format), not by URL.
        self._index: Dict[str, QueueItem] = {}
        # Secondary index: metadata and thumbnail fetches are per URL and
        # have to fan out to every format queued for that URL.
        self._by_url: Dict[str, List[QueueItem]] = {}
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

    def get(self, token: str) -> Optional[QueueItem]:
        """Look up by item key, falling back to a bare URL.

        The URL fallback keeps older callers (and a queue.json written by a
        previous build) working; it resolves to the first format queued
        for that URL.
        """
        item = self._index.get(token)
        if item is not None:
            return item
        bucket = self._by_url.get(token)
        return bucket[0] if bucket else None

    def items_for_url(self, url: str) -> List[QueueItem]:
        """Every queued format of one URL, in queue order."""
        return list(self._by_url.get(url, ()))

    def contains(self, token: str) -> bool:
        return token in self._index or token in self._by_url

    def contains_url(self, url: str) -> bool:
        return url in self._by_url

    def index_of(self, item: QueueItem) -> int:
        # Identity, not equality. QueueItem is a mutable dataclass, so two
        # distinct rows that happen to hold the same field values compare
        # equal and list.index() would resolve to the wrong row.
        for position, existing in enumerate(self._items):
            if existing is item:
                return position
        return -1

    # -- mutation ------------------------------------------------------

    def add(self, item: QueueItem) -> bool:
        # Same URL *and* same format is a duplicate; same URL in a
        # different format is a separate download.
        if item.key in self._index:
            return False
        self._items.append(item)
        self._index[item.key] = item
        self._by_url.setdefault(item.url, []).append(item)
        return True

    def remove(self, token: str) -> Optional[QueueItem]:
        item = self.get(token)
        if item is None:
            return None
        self._index.pop(item.key, None)
        bucket = self._by_url.get(item.url)
        if bucket is not None:
            self._by_url[item.url] = [i for i in bucket if i is not item]
            if not self._by_url[item.url]:
                del self._by_url[item.url]
        position = self.index_of(item)
        if position >= 0:
            del self._items[position]
        return item

    def clear(self) -> None:
        self._items.clear()
        self._index.clear()
        self._by_url.clear()

    def replace_all(self, items: Iterable[QueueItem]) -> None:
        self.clear()
        for item in items:
            self.add(item)

    def move_to_end(self, item: QueueItem) -> None:
        position = self.index_of(item)
        if position < 0:
            return
        del self._items[position]
        self._items.append(item)

    def move_many(self, keys: Sequence[str], *, to_top: bool, after: int = 0) -> None:
        """Move the given item keys as a block.

        `after` reserves leading slots (used to keep the in-progress item at the
        head when the user sends a selection to the top).
        """
        resolved = (self.get(k) for k in dict.fromkeys(keys))
        wanted = [item for item in resolved if item is not None]
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

    def reorder_by_keys(self, keys: Sequence[str]) -> None:
        """Apply a visual order. Items missing from `keys` keep relative order
        at the end, so a filtered view can never silently drop entries."""
        seen: set[int] = set()
        ordered: List[QueueItem] = []
        for key in keys:
            item = self.get(key)
            if item is not None and id(item) not in seen:
                ordered.append(item)
                seen.add(id(item))
        ordered.extend(i for i in self._items if id(i) not in seen)
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
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
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
        return len(self._items), None
