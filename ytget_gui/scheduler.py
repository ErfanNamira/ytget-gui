# File: ytget_gui/scheduler.py
"""Time-based queue and power scheduling.

The scheduler is deliberately dumb: it only decides *when* something is due
and emits a signal. Starting the queue, stopping it and running a power action
stay in MainWindow, which already owns those paths, so a schedule and a manual
click go through exactly the same code.

Firing rules that matter:

- Events fire at most once per calendar day, tracked per event key. A queue
  that is still running at the stop time is stopped, and the power action runs
  even mid-download; that is the point of the feature.
- A due event is only honoured inside a short catch-up window. Without it,
  launching the app in the evening would immediately trigger a 03:00 shutdown
  that the user was never present for.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time as dtime, timedelta
from typing import Dict, Optional, Sequence, Tuple

from PySide6.QtCore import QObject, QTimer, Signal

log = logging.getLogger(__name__)

# How late an event may still fire after its scheduled minute. Also the reason
# a machine that was asleep at 03:00 does not shut down the moment it wakes.
CATCH_UP_SECONDS = 300

_TICK_MS = 15000

DAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

POWER_ACTIONS = ("Shutdown", "Sleep", "Restart", "Close")


def parse_time(value: str, fallback: str = "00:00") -> dtime:
    """Parse HH:MM, falling back rather than raising."""
    for candidate in (value, fallback):
        text = str(candidate or "").strip()
        try:
            hour, _, minute = text.partition(":")
            return dtime(hour=int(hour), minute=int(minute))
        except (TypeError, ValueError):
            continue
    return dtime(0, 0)


class Scheduler(QObject):
    """Emits queue/power intents when their scheduled time arrives."""

    start_queue = Signal()
    stop_queue = Signal()
    power_action = Signal(str)
    message = Signal(str, str)

    def __init__(self, settings, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self._fired: Dict[str, date] = {}
        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._timer.isActive()

    def apply_settings(self) -> None:
        """Re-read settings; called after Preferences is saved."""
        if self.settings.SCHEDULER_ENABLED:
            if self._timer.isActive():
                # Times may have just been edited. Re-seed so a minute
                # that is already in the past is not fired retroactively
                # merely because Preferences was saved inside the
                # catch-up window.
                self._seed_fired()
            self.start()
        else:
            self.stop()

    def start(self) -> None:
        if self._timer.isActive():
            return
        # Anything already past when the scheduler starts is treated as
        # handled, so enabling the scheduler never fires a stale event.
        self._seed_fired()
        self._timer.start()
        self.message.emit(f"Scheduler active - {self.describe()}", "Info")

    def stop(self) -> None:
        if not self._timer.isActive():
            return
        self._timer.stop()
        self.message.emit("Scheduler stopped.", "Info")

    # ------------------------------------------------------------------
    # Description
    # ------------------------------------------------------------------

    def active_days(self) -> Sequence[int]:
        days = [int(d) for d in (self.settings.SCHEDULE_DAYS or []) if 0 <= int(d) <= 6]
        return sorted(set(days)) if days else list(range(7))

    def describe(self) -> str:
        days = self.active_days()
        when = "daily" if len(days) == 7 else ", ".join(DAY_LABELS[d] for d in days)
        parts = []
        if self.settings.SCHEDULE_START_ENABLED:
            parts.append(f"start {self.settings.SCHEDULE_START_TIME}")
        if self.settings.SCHEDULE_STOP_ENABLED:
            parts.append(f"stop {self.settings.SCHEDULE_STOP_TIME}")
        if self.settings.SCHEDULE_POWER_ENABLED:
            action = str(self.settings.SCHEDULE_POWER_ACTION).lower()
            parts.append(f"{action} {self.settings.SCHEDULE_POWER_TIME}")
        return f"{', '.join(parts) or 'nothing scheduled'} ({when})"

    def next_event(self, now: Optional[datetime] = None) -> Optional[str]:
        """Human-readable next due event, for the tray tooltip."""
        now = now or datetime.now()
        best: Optional[Tuple[datetime, str]] = None
        for key, label in (
            ("start", "start queue"),
            ("stop", "stop queue"),
            ("power", str(self.settings.SCHEDULE_POWER_ACTION).lower()),
        ):
            moment = self._next_occurrence(key, now)
            if moment is None:
                continue
            if best is None or moment < best[0]:
                best = (moment, label)
        if best is None:
            return None
        moment, label = best
        return f"{label} at {moment.strftime('%a %H:%M')}"

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def _enabled_for(self, key: str) -> bool:
        if not self.settings.SCHEDULER_ENABLED:
            return False
        return {
            "start": bool(self.settings.SCHEDULE_START_ENABLED),
            "stop": bool(self.settings.SCHEDULE_STOP_ENABLED),
            "power": bool(self.settings.SCHEDULE_POWER_ENABLED),
        }.get(key, False)

    def _time_for(self, key: str) -> dtime:
        raw = {
            "start": self.settings.SCHEDULE_START_TIME,
            "stop": self.settings.SCHEDULE_STOP_TIME,
            "power": self.settings.SCHEDULE_POWER_TIME,
        }.get(key, "00:00")
        return parse_time(raw)

    def _next_occurrence(self, key: str, now: datetime) -> Optional[datetime]:
        if not self._enabled_for(key):
            return None
        days = self.active_days()
        target = self._time_for(key)
        for offset in range(8):
            day = now.date() + timedelta(days=offset)
            if day.weekday() not in days:
                continue
            moment = datetime.combine(day, target)
            if moment > now:
                return moment
        return None

    def _seed_fired(self, now: Optional[datetime] = None) -> None:
        now = now or datetime.now()
        for key in ("start", "stop", "power"):
            if datetime.combine(now.date(), self._time_for(key)) <= now:
                self._fired[key] = now.date()

    def _due(self, key: str, now: datetime) -> bool:
        if not self._enabled_for(key):
            return False
        if now.weekday() not in self.active_days():
            return False
        if self._fired.get(key) == now.date():
            return False
        scheduled = datetime.combine(now.date(), self._time_for(key))
        delta = (now - scheduled).total_seconds()
        return 0 <= delta <= CATCH_UP_SECONDS

    def _tick(self) -> None:
        now = datetime.now()

        # Order matters: a power action in the same minute as a stop should
        # see the queue already stopped.
        if self._due("start", now):
            self._fired["start"] = now.date()
            self.message.emit("Scheduled start reached.", "Info")
            self.start_queue.emit()

        if self._due("stop", now):
            self._fired["stop"] = now.date()
            self.message.emit("Scheduled stop reached.", "Info")
            self.stop_queue.emit()

        if self._due("power", now):
            self._fired["power"] = now.date()
            action = str(self.settings.SCHEDULE_POWER_ACTION)
            if action not in POWER_ACTIONS:
                self.message.emit(f"Unknown scheduled power action: {action}", "Warning")
                return
            self.message.emit(
                f"Scheduled {action.lower()} reached - running now, even if the "
                "queue is unfinished.",
                "Warning",
            )
            self.power_action.emit(action)
