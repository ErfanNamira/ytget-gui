# File: ytget/dialogs/advanced.py
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLineEdit, QCheckBox, QDialogButtonBox, QGroupBox

from ytget.styles import AppStyles
from ytget.settings import AppSettings

class AdvancedOptionsDialog(QDialog):
    def __init__(self, parent, settings: AppSettings):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Advanced Options")
        self.setStyleSheet(AppStyles.DIALOG)
        self.setMinimumSize(420, 300)

        v = QVBoxLayout(self)

        clip_group = QGroupBox("Clip Extraction")
        clip_form = QFormLayout(clip_group)
        self.clip_start = QLineEdit(self.settings.CLIP_START, placeholderText="HH:MM:SS or seconds")
        self.clip_end = QLineEdit(self.settings.CLIP_END, placeholderText="HH:MM:SS or seconds")
        clip_form.addRow("Start Time:", self.clip_start)
        clip_form.addRow("End Time:", self.clip_end)
        v.addWidget(clip_group)

        pl_group = QGroupBox("Playlist Options")
        pl_form = QFormLayout(pl_group)
        self.playlist_items = QLineEdit(self.settings.PLAYLIST_ITEMS, placeholderText="e.g., 1,5-10,15")
        self.playlist_reverse = QCheckBox("Reverse playlist order")
        self.playlist_reverse.setChecked(self.settings.PLAYLIST_REVERSE)
        pl_form.addRow("Items to Download:", self.playlist_items)
        pl_form.addRow(self.playlist_reverse)
        v.addWidget(pl_group)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        v.addWidget(bb)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)

    def get_options(self) -> dict:
        return {
            "CLIP_START": self.clip_start.text().strip(),
            "CLIP_END": self.clip_end.text().strip(),
            "PLAYLIST_ITEMS": self.playlist_items.text().strip(),
            "PLAYLIST_REVERSE": self.playlist_reverse.isChecked(),
        }