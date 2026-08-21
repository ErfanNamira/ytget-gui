# File: ytget_gui/widgets/ui_switch.py
"""Animated toggle switch.

Lived in dialogs/advanced.py, which meant preferences.py imported a *dialog*
module purely to get a widget. Moved here so the dependency runs one way.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QCheckBox, QSizePolicy

from ytget_gui.styles import Palette

__all__ = ["UISwitch"]

_TRACK_W = 46.0
_TRACK_H = 26.0
_MARGIN = 2.0


class UISwitch(QCheckBox):
    """A QCheckBox that paints as a switch.

    Subclassing QCheckBox rather than QAbstractButton keeps `toggled`,
    `setChecked`, keyboard activation (Space/Enter) and accessibility for free.
    """

    offsetChanged = Signal(float)

    def __init__(self, text: str = "", parent: Optional[QCheckBox] = None) -> None:
        super().__init__(text, parent)
        self._offset = 1.0 if self.isChecked() else 0.0

        self._animation = QPropertyAnimation(self, b"offset", self)
        self._animation.setDuration(150)
        self._animation.setEasingCurve(QEasingCurve.InOutCubic)

        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.toggled.connect(self._animate_to)

    # ------------------------------------------------------------------

    def sizeHint(self) -> QSize:
        text_width = (
            self.fontMetrics().horizontalAdvance(self.text()) if self.text() else 0
        )
        padding = 10 if text_width else 0
        return QSize(int(_TRACK_W + 8) + text_width + padding, int(_TRACK_H + 6))

    @Property(float)
    def offset(self) -> float:
        return self._offset

    @offset.setter
    def offset(self, value: float) -> None:
        clamped = max(0.0, min(1.0, float(value)))
        if clamped == self._offset:
            return
        self._offset = clamped
        self.offsetChanged.emit(clamped)
        self.update()

    def _animate_to(self, checked: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._offset)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def setChecked(self, checked: bool) -> None:
        """Snap without animating when the value is set programmatically.

        Loading settings would otherwise run an animation per switch, which
        reads as the dialog flickering on open.
        """
        animating = self.isChecked() != bool(checked)
        super().setChecked(checked)
        if animating:
            self._animation.stop()
            self.offset = 1.0 if checked else 0.0

    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        track = QRectF(0, 0, _TRACK_W, _TRACK_H)
        track.moveTop((self.height() - _TRACK_H) / 2.0)

        enabled = self.isEnabled()
        if self.isChecked() and enabled:
            track_colour = QColor(Palette.ACCENT)
        elif enabled:
            track_colour = QColor(58, 58, 78)
        else:
            track_colour = QColor(40, 40, 54)

        painter.setPen(Qt.NoPen)
        painter.setBrush(track_colour)
        painter.drawRoundedRect(track, _TRACK_H / 2, _TRACK_H / 2)

        if self.hasFocus():
            pen = QPen(QColor(Palette.ACCENT))
            pen.setWidthF(2.0)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            inner = track.adjusted(1, 1, -1, -1)
            painter.drawRoundedRect(inner, inner.height() / 2, inner.height() / 2)

        diameter = _TRACK_H - _MARGIN * 2
        x = track.left() + _MARGIN + self._offset * (_TRACK_W - 2 * _MARGIN - diameter)
        thumb = QRectF(x, track.top() + _MARGIN, diameter, diameter)

        if enabled:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 90))
            painter.drawEllipse(thumb.adjusted(0.5, 1.2, 0.5, 1.2))

        painter.setPen(QPen(QColor(255, 255, 255, 60), 1.0))
        painter.setBrush(QColor(244, 244, 248) if enabled else QColor(150, 150, 160))
        painter.drawEllipse(thumb)

        if self.text():
            painter.setPen(QColor(Palette.TEXT if enabled else Palette.TEXT_FAINT))
            text_rect = QRectF(
                track.right() + 8, 0, self.width() - track.right() - 8, self.height()
            )
            painter.drawText(
                text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.text()
            )
