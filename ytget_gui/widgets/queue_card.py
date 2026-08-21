# File: ytget_gui/widgets/queue_card.py
"""Queue item card.

Takes a QueueItem and renders it. The previous revision passed five loose
positional arguments and then required the caller to keep the card, the
QListWidgetItem's UserRole dict and the backing queue entry manually in sync --
three copies of the same state that regularly disagreed.

Performance characteristics that matter in a long, scrolling list:
  * The drop shadow is attached only while hovered. QGraphicsDropShadowEffect
    forces an offscreen compositing pass; keeping one live on every row is the
    single largest cause of scroll lag.
  * Hover uses enterEvent/leaveEvent rather than an installed event filter, so
    mouse traffic is not routed through Python for a type check per event.
  * unpolish/polish runs only when a style property actually changes.
  * Repeated identical updates are no-ops, so a backend re-emitting the same
    value costs nothing.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from ytget_gui.queue.model import QueueItem, Status
from ytget_gui.utils.text import clamp

__all__ = ["QueueCard"]

_CHIP_STYLES = {
    Status.PENDING: (
        "background: rgba(107, 114, 128, 40); color: #9CA3AF; "
        "border: 1px solid rgba(107, 114, 128, 60);"
    ),
    Status.DOWNLOADING: (
        "background: rgba(0, 229, 255, 30); color: #00E5FF; "
        "border: 1px solid rgba(0, 229, 255, 80);"
    ),
    Status.COMPLETED: (
        "background: rgba(34, 211, 165, 30); color: #22D3A5; "
        "border: 1px solid rgba(34, 211, 165, 80);"
    ),
    Status.ERROR: (
        "background: rgba(248, 113, 113, 30); color: #F87171; "
        "border: 1px solid rgba(248, 113, 113, 80);"
    ),
    Status.CANCELLED: (
        "background: rgba(251, 191, 36, 28); color: #FBBF24; "
        "border: 1px solid rgba(251, 191, 36, 70);"
    ),
}
_DEFAULT_CHIP = _CHIP_STYLES[Status.PENDING]


def _format_duration(seconds: Optional[float]) -> str:
    if not seconds or seconds <= 0:
        return ""
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


class QueueCard(QFrame):
    removed = Signal(str)
    retry_requested = Signal(str)

    THUMB_SIZE = QSize(120, 68)

    def __init__(self, item: QueueItem, parent=None) -> None:
        super().__init__(parent)
        self.url = item.url

        self.setObjectName("QueueCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.setProperty("elevated", False)
        self.setProperty("active", False)

        # A fresh effect is built on each attach: Qt deletes the previously
        # installed QGraphicsEffect whenever setGraphicsEffect() is called
        # again (even with None), so reusing one instance leaves a Python
        # wrapper around a destroyed C++ object.
        self._shadow: Optional[QGraphicsDropShadowEffect] = None
        self._elevated = False
        self._active = False

        self._context_actions: List[Tuple[str, Callable[[], None]]] = []
        self._last_status: Optional[Status] = None
        self._last_percent = -1
        self._last_title = ""
        self._last_meta = ""
        self._meta_text = ""
        self._meta_width = -1
        self._thumb_path: Optional[str] = None

        self._build_ui()
        self.update_from(item)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        self.handle = QLabel("\u283f")
        self.handle.setObjectName("DragHandle")
        self.handle.setFixedWidth(16)
        self.handle.setAlignment(Qt.AlignCenter)
        self.handle.setToolTip("Drag to reorder")
        root.addWidget(self.handle)

        self.thumb = QLabel()
        self.thumb.setObjectName("Thumb")
        self.thumb.setFixedSize(self.THUMB_SIZE)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setAccessibleName("Thumbnail")
        root.addWidget(self.thumb)

        centre = QVBoxLayout()
        centre.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self.title_lbl = QLabel()
        self.title_lbl.setObjectName("CardTitle")
        self.title_lbl.setWordWrap(True)
        title_row.addWidget(self.title_lbl, 1)

        self.status_chip = QLabel()
        self.status_chip.setObjectName("StatusChip")
        self.status_chip.setAlignment(Qt.AlignCenter)
        self.status_chip.setFixedHeight(20)
        self.status_chip.setAccessibleName("Status")
        title_row.addWidget(self.status_chip, 0, Qt.AlignRight)
        centre.addLayout(title_row)

        self.meta_lbl = QLabel()
        self.meta_lbl.setObjectName("CardMeta")
        self.meta_lbl.setWordWrap(False)
        self.meta_lbl.setMinimumWidth(0)
        self.meta_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.meta_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        centre.addWidget(self.meta_lbl)

        progress_row = QHBoxLayout()
        progress_row.setSpacing(8)
        self.progress = QProgressBar()
        self.progress.setObjectName("Progress")
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.setRange(0, 100)
        self.progress.setAccessibleName("Download progress")
        progress_row.addWidget(self.progress, 1)

        self.percent_lbl = QLabel()
        self.percent_lbl.setObjectName("Percent")
        self.percent_lbl.setFixedWidth(38)
        self.percent_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        progress_row.addWidget(self.percent_lbl, 0)
        centre.addLayout(progress_row)

        root.addLayout(centre, 1)

        right = QVBoxLayout()
        right.setSpacing(6)

        self.more_btn = QPushButton("\u22ef")
        self.more_btn.setObjectName("IconBtn")
        self.more_btn.setFixedSize(28, 22)
        self.more_btn.setCursor(Qt.PointingHandCursor)
        self.more_btn.setToolTip("More actions")
        self.more_btn.setAccessibleName("More actions")
        right.addWidget(self.more_btn, 0, Qt.AlignRight)

        self.btn_delete = QPushButton("\u2715")
        self.btn_delete.setObjectName("IconBtn")
        self.btn_delete.setFixedSize(28, 22)
        self.btn_delete.setCursor(Qt.PointingHandCursor)
        self.btn_delete.setToolTip("Remove from queue")
        self.btn_delete.setAccessibleName("Remove from queue")
        right.addWidget(self.btn_delete, 0, Qt.AlignRight)

        right.addStretch(1)
        root.addLayout(right)

        self.more_btn.clicked.connect(self._open_menu_at_button)
        # The delete button previously only emitted a signal nothing was
        # connected to, so clicking it did nothing at all.
        self.btn_delete.clicked.connect(lambda: self.removed.emit(self.url))

        # Right-click anywhere works even when the window is narrow enough that
        # the icon buttons get squeezed out of the layout.
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._open_menu_at_point)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_from(self, item: QueueItem) -> None:
        """Refresh every field from the model. Cheap when nothing changed."""
        self.url = item.url
        self._set_title(item.display_title)
        self._set_status(item.status)
        self._set_progress(item.progress)
        self._set_meta(self._compose_meta(item))
        self._set_active(item.status is Status.DOWNLOADING)
        if item.thumb_path:
            self.set_thumbnail_path(item.thumb_path)

    def set_context_actions(
        self, actions: Sequence[Tuple[str, Callable[[], None]]]
    ) -> None:
        self._context_actions = list(actions)

    def set_thumbnail_path(self, path: str) -> None:
        if not path or path == self._thumb_path:
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return
        self._thumb_path = path
        self.thumb.setPixmap(self._fit(pixmap))

    # ------------------------------------------------------------------
    # Field updates
    # ------------------------------------------------------------------

    def _set_title(self, title: str) -> None:
        if title == self._last_title:
            return
        self._last_title = title
        self.title_lbl.setText(clamp(title, 90))
        self.title_lbl.setToolTip(title)

    def _set_status(self, status: Status) -> None:
        if status is self._last_status:
            return
        self._last_status = status
        self.status_chip.setText(status.value)
        self.status_chip.setStyleSheet(_CHIP_STYLES.get(status, _DEFAULT_CHIP))
        # A finished item's progress bar is noise; hide it so the card reads as
        # "done" rather than "stalled at 100%".
        show_progress = status in (Status.DOWNLOADING, Status.CANCELLED)
        self.progress.setVisible(show_progress)
        self.percent_lbl.setVisible(show_progress)

    def _set_progress(self, percent: int) -> None:
        value = max(0, min(100, int(percent)))
        if value == self._last_percent:
            return
        self._last_percent = value
        self.progress.setValue(value)
        self.percent_lbl.setText(f"{value}%")

    @staticmethod
    def _compose_meta(item: QueueItem) -> str:
        parts: List[str] = []
        if item.stage:
            parts.append(item.stage)
        if item.format_label:
            parts.append(item.format_label)
        duration = _format_duration(item.duration)
        if duration:
            parts.append(duration)
        if item.is_playlist:
            parts.append("playlist")
        if item.uploader:
            parts.append(item.uploader)
        if item.last_error and item.status is Status.ERROR:
            parts.append(clamp(item.last_error, 70))
        if not parts:
            parts.append(item.url)
        return "  \u00b7  ".join(parts)

    def _set_meta(self, text: str) -> None:
        if text == self._meta_text:
            return
        self._meta_text = text
        self._apply_elided_meta(force=True)

    def _apply_elided_meta(self, *, force: bool = False) -> None:
        width = self.meta_lbl.width()
        if width <= 0:
            width = 240
        if not force and width == self._meta_width:
            return
        self._meta_width = width
        metrics = self.meta_lbl.fontMetrics()
        self.meta_lbl.setText(
            metrics.elidedText(self._meta_text, Qt.ElideRight, width)
        )
        self.meta_lbl.setToolTip(self._meta_text)

    def _fit(self, pixmap: QPixmap) -> QPixmap:
        size = self.THUMB_SIZE
        scaled = pixmap.scaled(
            size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        )
        if scaled.size() == size:
            return scaled
        x = max(0, (scaled.width() - size.width()) // 2)
        y = max(0, (scaled.height() - size.height()) // 2)
        return scaled.copy(x, y, size.width(), size.height())

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _build_menu(self) -> QMenu:
        menu = QMenu(self)
        if self._context_actions:
            for label, callback in self._context_actions:
                menu.addAction(label).triggered.connect(callback)
        else:
            menu.addAction("Remove").triggered.connect(
                lambda: self.removed.emit(self.url)
            )
        return menu

    def _open_menu_at_button(self) -> None:
        menu = self._build_menu()
        menu.exec(self.more_btn.mapToGlobal(self.more_btn.rect().bottomLeft()))

    def _open_menu_at_point(self, pos) -> None:
        self._build_menu().exec(self.mapToGlobal(pos))

    # ------------------------------------------------------------------
    # Hover / state styling
    # ------------------------------------------------------------------

    def _set_elevated(self, on: bool) -> None:
        if on == self._elevated:
            return
        self._elevated = on
        if on:
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(16)
            shadow.setColor(QColor(0, 0, 0, 60))
            shadow.setOffset(0, 2)
            self._shadow = shadow
            self.setGraphicsEffect(shadow)
        else:
            self.setGraphicsEffect(None)
            self._shadow = None
        self._repolish("elevated", on)

    def _set_active(self, on: bool) -> None:
        if on == self._active:
            return
        self._active = on
        self._repolish("active", on)

    def _repolish(self, prop: str, value: bool) -> None:
        self.setProperty(prop, value)
        style = self.style()
        style.unpolish(self)
        style.polish(self)

    def enterEvent(self, event) -> None:
        self._set_elevated(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._set_elevated(False)
        super().leaveEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_elided_meta()
