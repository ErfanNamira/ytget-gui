# File: ytget_gui/widgets/queue_card.py

from __future__ import annotations

from typing import Optional, Callable, List, Tuple

from PySide6.QtCore import Qt, Signal, QEvent, QSize
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
    QSizePolicy,
)

__all__ = ["QueueCard"]


def _clamp(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + "…"


STATUS_COLORS = {
    "Pending": "#4B5565",
    "Queued": "#4B5565",
    "Downloading": "#6EA8FE",
    "Completed": "#55D187",
    "Error": "#FF6B6B",
    "Skipped": "#D1A85F",
    "Cancelled": "#8A8FA3",
}
_DEFAULT_STATUS_COLOR = "#4B5565"


class QueueCard(QFrame):
    """
    Queue item card:
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

    THUMB_SIZE = QSize(120, 68)  # matches fallback card size in main_window

    def __init__(
        self,
        title: str,
        url: str,
        status: str = "Pending",
        progress: Optional[int] = 0,
        show_thumbnail: bool = True,
    ):
        super().__init__()
        self.url = url
        self.setObjectName("QueueCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.setProperty("elevated", False)

        self._context_actions: List[Tuple[str, Callable[[], None]]] = []
        self._last_meta_width: int = -1
        self._last_progress_value: int = -1
        self._last_thumb_path: Optional[str] = None
        self._last_thumb_pixmap_key: Optional[int] = None  # cacheKey() of last source pixmap

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
            self.thumb.setFixedSize(self.THUMB_SIZE)
            self.thumb.setObjectName("Thumb")
            # NOTE: scaledContents deliberately left False. We pre-scale and
            # center-crop pixmaps ourselves in _make_thumbnail_pixmap so the
            # aspect ratio is preserved; letting Qt additionally stretch the
            # result via scaledContents would re-distort it.
            self.thumb.setScaledContents(False)
            self.thumb.setAlignment(Qt.AlignCenter)
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

        # meta row (elide long URLs to avoid scrollbars)
        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)

        self._full_meta_text = url or ""
        self.meta_lbl = QLabel()
        self.meta_lbl.setObjectName("CardMeta")
        self.meta_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.meta_lbl.setWordWrap(False)
        # allow the label to shrink instead of forcing scrollbars
        self.meta_lbl.setMinimumWidth(0)
        self.meta_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        meta_row.addWidget(self.meta_lbl, 1)
        center.addLayout(meta_row)

        # set initial elided text and tooltip
        self._set_elided_meta(self._full_meta_text, max_width=220, force=True)

        progress_row = QHBoxLayout()
        progress_row.setSpacing(8)

        self.progress = QProgressBar()
        self.progress.setObjectName("Progress")
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.setRange(0, 100)
        progress_row.addWidget(self.progress, 1)

        self.percent_lbl = QLabel()
        self.percent_lbl.setObjectName("Percent")
        self.percent_lbl.setFixedWidth(38)
        self.percent_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        progress_row.addWidget(self.percent_lbl, 0)

        center.addLayout(progress_row)
        self.set_progress(progress or 0)

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

        # Initial style (also ensures dynamic properties set above are
        # actually applied by the style engine before first paint)
        self._apply_status_style(status)

    # ----- Public API -----

    def set_status(self, status: str) -> None:
        self._apply_status_style(status)

    def set_progress(self, value: int) -> None:
        v = max(0, min(100, int(value)))
        if v == self._last_progress_value:
            return  # avoid redundant repaint/relayout work
        self._last_progress_value = v
        self.progress.setValue(v)
        self.percent_lbl.setText(f"{v}%")

    def set_context_actions(self, items: List[Tuple[str, Callable[[], None]]]) -> None:
        """
        Provide context menu actions, e.g.
        [("Open in browser", fn), ("Copy URL", fn2)]
        """
        self._context_actions = items

    def set_thumbnail_pixmap(self, pix: Optional[QPixmap]) -> None:
        """Optionally set the thumbnail pixmap directly."""
        if self.thumb is None or pix is None or pix.isNull():
            return

        # Skip re-scaling work if this is literally the same source pixmap
        # we already rendered (common when refreshing/re-adding cards).
        key = pix.cacheKey()
        if key == self._last_thumb_pixmap_key:
            return
        self._last_thumb_pixmap_key = key
        self._last_thumb_path = None  # pixmap set directly, not via path cache

        self.thumb.setPixmap(self._make_thumbnail_pixmap(pix))

    def set_thumbnail_path(self, path: str) -> None:
        """Load a pixmap from path and set as thumbnail."""
        if not path or self.thumb is None:
            return
        if path == self._last_thumb_path:
            return  # already showing this exact file
        pix = QPixmap(path)
        if pix.isNull():
            return
        self._last_thumb_path = path
        self._last_thumb_pixmap_key = pix.cacheKey()
        self.thumb.setPixmap(self._make_thumbnail_pixmap(pix))

    # ----- Internal helpers -----

    def _make_thumbnail_pixmap(self, pix: QPixmap) -> QPixmap:
        """
        Scale to fill THUMB_SIZE while preserving aspect ratio, then center
        crop to exactly THUMB_SIZE. Avoids both letterboxing and the
        distortion that setScaledContents(True) would otherwise introduce
        on top of an already-aspect-scaled pixmap.
        """
        size = self.THUMB_SIZE
        scaled = pix.scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        if scaled.size() == size:
            return scaled
        x = max(0, (scaled.width() - size.width()) // 2)
        y = max(0, (scaled.height() - size.height()) // 2)
        return scaled.copy(x, y, size.width(), size.height())

    def _apply_status_style(self, status: str) -> None:
        self.status_chip.setText(status)
        # Expose a color hint via dynamic property; QSS can read it indirectly
        color = STATUS_COLORS.get(status, _DEFAULT_STATUS_COLOR)
        self.setProperty("statusColor", color)
        self._repolish()

    def _open_context_menu(self) -> None:
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

    def _repolish(self) -> None:
        style = self.style()
        style.unpolish(self)
        style.polish(self)

    def _set_elided_meta(self, text: str, max_width: int = 220, force: bool = False) -> None:
        """
        Elide the meta text (URL) to avoid scrollbars.
        max_width is the pixel width available for the label.
        """
        self._full_meta_text = text or ""
        if not force and max_width == self._last_meta_width:
            return  # nothing changed since last elide pass
        self._last_meta_width = max_width
        try:
            fm = self.meta_lbl.fontMetrics()
            elided = fm.elidedText(self._full_meta_text, Qt.ElideMiddle, max_width)
            self.meta_lbl.setText(elided)
            self.meta_lbl.setToolTip(self._full_meta_text)
        except Exception:
            # fallback to raw truncated text
            self.meta_lbl.setText(_clamp(self._full_meta_text, 64))
            self.meta_lbl.setToolTip(self._full_meta_text)

    # ----- Hover/elevation -----

    def eventFilter(self, obj, event):
        et = event.type()
        if et == QEvent.Enter:
            self.setProperty("elevated", True)
            self._repolish()
        elif et == QEvent.Leave:
            self.setProperty("elevated", False)
            self._repolish()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        # Re-elide against the label's *actual* current width rather than
        # a fixed guess, so the URL doesn't stay over-truncated on wide
        # windows or under-truncated (causing wrapping/scrollbars) on
        # narrow ones. _set_elided_meta short-circuits if width is
        # unchanged, so this is cheap on no-op resizes (e.g. vertical-only).
        super().resizeEvent(event)
        width = self.meta_lbl.width()
        if width > 0:
            self._set_elided_meta(self._full_meta_text, max_width=width)
