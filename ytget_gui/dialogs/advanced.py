# File: ytget_gui/dialogs/advanced.py
"""Clip extraction and per-run playlist controls."""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ytget_gui.dialogs import common as ui
from ytget_gui.settings import AppSettings
from ytget_gui.utils.validators import (
    is_valid_playlist_items,
    is_valid_timecode,
    timecode_to_seconds,
)

_TIME_HINT = "Seconds or [H:]MM:SS \u2014 e.g. 75, 01:15, 1:02:45"
_ITEMS_HINT = "Indices and ranges, e.g. 1, 3-5, 10"


class AdvancedOptionsDialog(QDialog):
    """Esc cancels, Ctrl+Enter saves, Alt+R resets."""

    def __init__(self, parent: Optional[QWidget], settings: AppSettings) -> None:
        super().__init__(parent)
        self.settings = settings

        self.setWindowTitle("Advanced")
        self.setModal(True)
        self.setMinimumSize(580, 360)
        self.setStyleSheet(ui.dialog_qss())

        self._labels: List[QLabel] = []
        self._build()
        self._load()
        self._validate()

    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        title = QLabel("Advanced options")
        title.setObjectName("dlgTitle")
        subtitle = QLabel("Clip extraction and playlist selection for the next run")
        subtitle.setObjectName("dlgSubtitle")
        root.addWidget(title)
        root.addWidget(subtitle)
        root.addWidget(ui.divider())

        self.clip_start = ui.line_edit("HH:MM:SS or seconds", _TIME_HINT, "Clip start")
        self.clip_end = ui.line_edit("HH:MM:SS or seconds", _TIME_HINT, "Clip end")

        clip_note = QLabel(
            "Cuts are made at exact timestamps by re-encoding around the "
            "boundaries, so a clip may take longer than a full download."
        )
        clip_note.setObjectName("formDescription")
        clip_note.setWordWrap(True)

        clip_body = QWidget()
        clip_layout = QVBoxLayout(clip_body)
        clip_layout.setContentsMargins(0, 0, 0, 0)
        clip_layout.setSpacing(6)
        clip_layout.addWidget(ui.form_row("Start time", self.clip_start, label_registry=self._labels))
        clip_layout.addWidget(ui.form_row("End time", self.clip_end, label_registry=self._labels))
        clip_layout.addWidget(clip_note)

        root.addWidget(
            ui.card(
                clip_body,
                title="Clip extraction",
                subtitle="Leave both empty to download the whole item.",
            )
        )

        self.playlist_items = ui.line_edit("e.g. 1, 3-5, 10", _ITEMS_HINT, "Playlist items")
        self.playlist_reverse = ui.switch("Reverse playlist order")

        playlist_body = QWidget()
        playlist_layout = QVBoxLayout(playlist_body)
        playlist_layout.setContentsMargins(0, 0, 0, 0)
        playlist_layout.setSpacing(6)
        playlist_layout.addWidget(
            ui.form_row("Items", self.playlist_items, label_registry=self._labels)
        )
        playlist_layout.addWidget(
            ui.form_row(
                "Order",
                self.playlist_reverse,
                "Download items from last to first",
                label_registry=self._labels,
            )
        )

        root.addWidget(
            ui.card(
                playlist_body,
                title="Playlist",
                subtitle="Applies to every playlist URL in the queue.",
            )
        )

        root.addStretch(1)
        root.addWidget(ui.divider())

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        self.reset_button = self.buttons.addButton("Reset", QDialogButtonBox.ResetRole)
        self.reset_button.setShortcut(QKeySequence("Alt+R"))
        root.addWidget(self.buttons)

        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        self.reset_button.clicked.connect(self._reset)

        for field in (self.clip_start, self.clip_end, self.playlist_items):
            field.textChanged.connect(self._validate)

        self.setTabOrder(self.clip_start, self.clip_end)
        self.setTabOrder(self.clip_end, self.playlist_items)
        self.setTabOrder(self.playlist_items, self.playlist_reverse)

        width = max(
            (self.fontMetrics().horizontalAdvance(l.text()) for l in self._labels),
            default=0,
        )
        for label in self._labels:
            label.setMinimumWidth(width + 8)

    # ------------------------------------------------------------------

    def _load(self) -> None:
        self.clip_start.setText(str(getattr(self.settings, "CLIP_START", "") or ""))
        self.clip_end.setText(str(getattr(self.settings, "CLIP_END", "") or ""))
        self.playlist_items.setText(str(getattr(self.settings, "PLAYLIST_ITEMS", "") or ""))
        self.playlist_reverse.setChecked(bool(getattr(self.settings, "PLAYLIST_REVERSE", False)))

    def _reset(self) -> None:
        self.clip_start.clear()
        self.clip_end.clear()
        self.playlist_items.clear()
        self.playlist_reverse.setChecked(False)
        self._validate()

    def get_options(self) -> Dict[str, object]:
        return {
            "CLIP_START": self.clip_start.text().strip(),
            "CLIP_END": self.clip_end.text().strip(),
            "PLAYLIST_ITEMS": self.playlist_items.text().strip(),
            "PLAYLIST_REVERSE": self.playlist_reverse.isChecked(),
        }

    # ------------------------------------------------------------------

    def _validate(self) -> None:
        start = self.clip_start.text().strip()
        end = self.clip_end.text().strip()
        items = self.playlist_items.text().strip()

        start_ok = is_valid_timecode(start)
        end_ok = is_valid_timecode(end)
        items_ok = is_valid_playlist_items(items)

        ordering_error = ""
        if start_ok and end_ok and start and end:
            a = timecode_to_seconds(start)
            b = timecode_to_seconds(end)
            if a is None or b is None or b <= a:
                ordering_error = "The end time must be later than the start time."

        # Both fields or neither: a start with no end silently downloads
        # everything after that point, which is rarely what was meant.
        pairing_error = ""
        if bool(start) != bool(end):
            pairing_error = "Set both a start and an end time, or leave both empty."

        ui.set_error(
            self.clip_start,
            (not start_ok and bool(start)) or bool(pairing_error and not start),
            pairing_error or _TIME_HINT,
        )
        ui.set_error(
            self.clip_end,
            (not end_ok and bool(end)) or bool(ordering_error) or bool(pairing_error and not end),
            ordering_error or pairing_error or _TIME_HINT,
        )
        ui.set_error(self.playlist_items, not items_ok, _ITEMS_HINT)

        valid = (
            start_ok and end_ok and items_ok and not ordering_error and not pairing_error
        )
        save = self.buttons.button(QDialogButtonBox.Save)
        if save is not None:
            save.setEnabled(valid)
            save.setDefault(valid)
            save.setToolTip(
                "Save changes" if valid else "Fix the highlighted fields to save"
            )

    def _first_invalid(self) -> Optional[QWidget]:
        for widget in (self.clip_start, self.clip_end, self.playlist_items):
            if (widget.property("state") or "") == "error":
                return widget
        return None

    def _accept(self) -> None:
        self._validate()
        save = self.buttons.button(QDialogButtonBox.Save)
        if save is not None and not save.isEnabled():
            invalid = self._first_invalid()
            if invalid is not None:
                invalid.setFocus(Qt.OtherFocusReason)
                QToolTip.showText(
                    invalid.mapToGlobal(invalid.rect().bottomLeft()),
                    invalid.toolTip(),
                    invalid,
                )
            return
        self.accept()

    def keyPressEvent(self, event) -> None:
        modifiers = event.modifiers()
        if (modifiers & (Qt.ControlModifier | Qt.MetaModifier)) and event.key() in (
            Qt.Key_Return,
            Qt.Key_Enter,
        ):
            self._accept()
            return
        super().keyPressEvent(event)
