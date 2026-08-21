# File: ytget_gui/queue/__init__.py
"""Queue model and controller.

Extracted from MainWindow, which previously held the queue list, its
persistence, the worker lifecycle and the scheduling state machine inline
across ~1,200 lines. The scheduling bugs (skip looping forever on the last
item, the post-queue action firing twice) were direct consequences of that
state being spread across a dozen methods.
"""

from __future__ import annotations

from ytget_gui.queue.model import QueueItem, QueueModel, Status
from ytget_gui.queue.controller import QueueController

__all__ = ["QueueItem", "QueueModel", "Status", "QueueController"]
