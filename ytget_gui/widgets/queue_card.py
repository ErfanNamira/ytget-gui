# File: ytget_gui/widgets/queue_card.py
from __future__ import annotations

from typing import Optional, Callable, List, Tuple

from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QFrame,
    QMenu,
)


def _clamp(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + "…"


STATUS_COLORS = {
    "Pending": "#4B5565",
    "Queued": "#4B5565",
    "Downloading": "#6EA8FE",
    "Completed": "#55D187",
    "Error": "#FF6B6B",
    "Skipped": "#D1A85F",
}


class QueueCard(QFrame):
    """
    Modern queue item card:
    - Drag handle
    - Optional thumbnail
    - Title, URL/meta
    - Status chip
    - Micro progress + percent
    - Overflow menu with pluggable actions

    Signals:
      - removed: emitted when the delete/remove is triggered
      - movedUp: emitted when move-up is triggered
      - movedDown: emitted when move-down is triggered
    """

    removed = Signal()
    movedUp = Signal()
    movedDown = Signal()

    def __init__(
        self,
        title: str,
        url: str,
        status: str = "Pending",
        progress: Optional[int] = 0,
        show_thumbnail: bool = True,
    ):
        super().__init__()
        self.setObjectName("QueueCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.setProperty("elevated", False)

        self._context_actions: List[Tuple[str, Callable[[], None]]] = []

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # Drag handle
        self.handle = QLabel("⠿")
        self.handle.setObjectName("DragHandle")
        self.handle.setFixedWidth(16)
        self.handle.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.handle.setToolTip("Drag to reorder")
        root.addWidget(self.handle)

        # Thumbnail
        if show_thumbnail:
            self.thumb = QLabel()
            self.thumb.setFixedSize(120, 68)  # matches fallback card size in main_window
            self.thumb.setObjectName("Thumb")
            self.thumb.setScaledContents(True)
            root.addWidget(self.thumb)
        else:
            self.thumb = None

        # Center block (title, meta, progress)
        center = QVBoxLayout()
        center.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)

        self.title_lbl = QLabel(_clamp(title, 90))
        self.title_lbl.setObjectName("CardTitle")
        self.title_lbl.setWordWrap(True)
        title_row.addWidget(self.title_lbl, 1)

        self.status_chip = QLabel(status)
        self.status_chip.setObjectName("StatusChip")
        self.status_chip.setAlignment(Qt.AlignCenter)
        self.status_chip.setFixedHeight(20)
        title_row.addWidget(self.status_chip, 0, Qt.AlignRight)

        center.addLayout(title_row)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)
        self.meta_lbl = QLabel(_clamp(url, 64))
        self.meta_lbl.setObjectName("CardMeta")
        self.meta_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        meta_row.addWidget(self.meta_lbl, 1)
        center.addLayout(meta_row)

        progress_row = QHBoxLayout()
        progress_row.setSpacing(8)

        self.progress = QProgressBar()
        self.progress.setObjectName("Progress")
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.setRange(0, 100)
        self.progress.setValue(int(progress or 0))
        progress_row.addWidget(self.progress, 1)

        self.percent_lbl = QLabel(f"{int(progress or 0)}%")
        self.percent_lbl.setObjectName("Percent")
        self.percent_lbl.setFixedWidth(38)
        self.percent_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        progress_row.addWidget(self.percent_lbl, 0)

        center.addLayout(progress_row)

        root.addLayout(center, 1)

        # Right side: overflow + hidden compat controls
        right = QVBoxLayout()
        right.setSpacing(6)

        self.more_btn = QPushButton("⋯")
        self.more_btn.setObjectName("IconBtn")
        self.more_btn.setFixedWidth(28)
        self.more_btn.setToolTip("More actions")
        self.more_btn.setCursor(Qt.PointingHandCursor)
        right.addWidget(self.more_btn, 0, Qt.AlignRight)

        compat = QHBoxLayout()
        compat.setSpacing(6)
        self.btn_up = QPushButton("▲")
        self.btn_up.setObjectName("IconBtn")
        self.btn_down = QPushButton("▼")
        self.btn_down.setObjectName("IconBtn")
        self.btn_delete = QPushButton("✕")
        self.btn_delete.setObjectName("IconBtn")
        for b in (self.btn_up, self.btn_down, self.btn_delete):
            b.setVisible(False)
        compat.addWidget(self.btn_up)
        compat.addWidget(self.btn_down)
        compat.addWidget(self.btn_delete)
        right.addLayout(compat)

        right.addStretch(1)
        root.addLayout(right)

        # Wire signals
        self.more_btn.clicked.connect(self._open_context_menu)
        self.btn_delete.clicked.connect(self.removed.emit)
        self.btn_up.clicked.connect(self.movedUp.emit)
        self.btn_down.clicked.connect(self.movedDown.emit)

        # Accessibility
        self.setAccessibleName("QueueCard")
        self.more_btn.setAccessibleName("MoreMenu")
        if self.thumb:
            self.thumb.setAccessibleName("Thumbnail")
        self.progress.setAccessibleName("ProgressBar")
        self.status_chip.setAccessibleName("StatusChip")

        # Hover elevation polish
        self.setMouseTracking(True)
        self.installEventFilter(self)

        # Initial style
        self._apply_status_style(status)

    # ----- Public API -----

    def set_status(self, status: str):
        self._apply_status_style(status)

    def set_progress(self, value: int):
        v = max(0, min(100, int(value)))
        self.progress.setValue(v)
        self.percent_lbl.setText(f"{v}%")

    def set_context_actions(self, items: List[Tuple[str, Callable[[], None]]]):
        """
        Provide context menu actions, e.g.
        [("Open in browser", fn), ("Copy URL", fn2)]
        """
        self._context_actions = items

    def set_thumbnail_pixmap(self, pix: QPixmap):
        """Optionally set the thumbnail pixmap directly."""
        if self.thumb is None or pix is None or pix.isNull():
            return
        size = self.thumb.size()
        scaled = pix.scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        self.thumb.setPixmap(scaled)

    def set_thumbnail_path(self, path: str):
        """Load a pixmap from path and set as thumbnail."""
        if not path or self.thumb is None:
            return
        pix = QPixmap(path)
        self.set_thumbnail_pixmap(pix)

    # ----- Internal helpers -----

    def _apply_status_style(self, status: str):
        self.status_chip.setText(status)
        # Expose a color hint via dynamic property; QSS can read it indirectly
        color = STATUS_COLORS.get(status, "#4B5565")
        self.setProperty("statusColor", color)
        self._repolish()

    def _open_context_menu(self):
        menu = QMenu(self)
        if self._context_actions:
            for label, fn in self._context_actions:
                act = menu.addAction(label)
                if callable(fn):
                    act.triggered.connect(fn)
        else:
            menu.addAction("Remove").triggered.connect(self.removed.emit)
            menu.addAction("Move up").triggered.connect(self.movedUp.emit)
            menu.addAction("Move down").triggered.connect(self.movedDown.emit)
        menu.exec(self.more_btn.mapToGlobal(self.more_btn.rect().bottomLeft()))

    def _repolish(self):
        self.style().unpolish(self)
        self.style().polish(self)

    # ----- Hover/elevation -----

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Enter:
            self.setProperty("elevated", True)
            self._repolish()
        elif event.type() == QEvent.Leave:
            self.setProperty("elevated", False)
            self._repolish()
        return super().eventFilter(obj, event)
