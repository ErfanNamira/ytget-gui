# File: ytget/dialogs/preferences.py
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Dict, List

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTabWidget, QWidget, QGroupBox, QFormLayout,
    QLineEdit, QCheckBox, QComboBox, QPushButton, QGridLayout, QLabel,
    QSpinBox, QFileDialog, QDialogButtonBox, QCalendarWidget, QMessageBox
)
from PySide6.QtCore import QDate

from ytget.styles import AppStyles
from ytget.settings import AppSettings

_SPONSORBLOCK_CATEGORIES = {
    "Sponsor": "sponsor",
    "Intro": "intro",
    "Outro": "outro",
    "Self Promotion": "selfpromo",
    "Interaction Reminder": "interaction",
    "Music Non-Music": "music_offtopic",
    "Preview/Recap": "preview",
    "Filler": "filler",
}

class PreferencesDialog(QDialog):
    def __init__(self, parent, settings: AppSettings):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Preferences")
        self.setMinimumSize(820, 680)
        self.setStyleSheet(AppStyles.DIALOG)

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # Network
        network = QWidget()
        nlayout = QVBoxLayout(network)

        proxy_group = QGroupBox("Proxy")
        proxy_form = QFormLayout(proxy_group)
        self.proxy_input = QLineEdit(self.settings.PROXY_URL, placeholderText="http://proxy:port or socks5://proxy:port")
        proxy_form.addRow("Proxy URL:", self.proxy_input)
        nlayout.addWidget(proxy_group)

        cookies_group = QGroupBox("Cookies")
        cookies_form = QFormLayout(cookies_group)
        self.cookies_path_input = QLineEdit(str(self.settings.COOKIES_PATH))
        self.cookies_path_input.setReadOnly(True)
        self.btn_browse_cookies = QPushButton("Browse...")
        self.cookies_browser_combo = QComboBox()
        self.cookies_browser_combo.addItems(["", "chrome", "firefox", "edge", "opera", "vivaldi"])
        if self.settings.COOKIES_FROM_BROWSER:
            self.cookies_browser_combo.setCurrentText(self.settings.COOKIES_FROM_BROWSER)

        cookies_form.addRow("Cookies File:", self.cookies_path_input)
        cookies_form.addRow(self.btn_browse_cookies)
        cookies_form.addRow("Import from Browser:", self.cookies_browser_combo)
        nlayout.addWidget(cookies_group)

        perf_group = QGroupBox("Performance")
        perf_grid = QGridLayout(perf_group)
        self.limit_rate_input = QLineEdit(self.settings.LIMIT_RATE, placeholderText="e.g., 5M or 500K")
        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(1, 100)
        self.retries_spin.setValue(self.settings.RETRIES)
        perf_grid.addWidget(QLabel("Max Download Speed:"), 0, 0)
        perf_grid.addWidget(self.limit_rate_input, 0, 1)
        perf_grid.addWidget(QLabel("Retry Attempts:"), 1, 0)
        perf_grid.addWidget(self.retries_spin, 1, 1)
        nlayout.addWidget(perf_group)
        nlayout.addStretch()

        tabs.addTab(network, "Network")

        # SponsorBlock
        sponsor = QWidget()
        s_layout = QVBoxLayout(sponsor)
        sb_group = QGroupBox("Skip Segments")
        sb_v = QVBoxLayout(sb_group)
        self.category_cb = {}
        for label, code in _SPONSORBLOCK_CATEGORIES.items():
            cb = QCheckBox(label)
            cb.setChecked(code in self.settings.SPONSORBLOCK_CATEGORIES)
            self.category_cb[code] = cb
            sb_v.addWidget(cb)
        sb_v.addStretch()
        s_layout.addWidget(sb_group)
        s_layout.addStretch()
        tabs.addTab(sponsor, "SponsorBlock")

        # Chapters
        ch = QWidget()
        ch_layout = QFormLayout(ch)
        self.chapters_embed = QCheckBox("Embed chapters in file")
        self.chapters_split = QCheckBox("Split by chapters")
        self.chapters_embed.setChecked(self.settings.CHAPTERS_MODE == "embed")
        self.chapters_split.setChecked(self.settings.CHAPTERS_MODE == "split")
        ch_layout.addRow(self.chapters_embed)
        ch_layout.addRow(self.chapters_split)
        tabs.addTab(ch, "Chapters")

        # Subtitles
        subs = QWidget()
        subs_form = QFormLayout(subs)
        self.subtitles_enabled = QCheckBox("Download subtitles")
        self.subtitles_enabled.setChecked(self.settings.WRITE_SUBS)
        self.languages_input = QLineEdit(self.settings.SUB_LANGS, placeholderText="en,es,fr")
        self.auto_subs = QCheckBox("Include auto-generated subtitles")
        self.auto_subs.setChecked(self.settings.WRITE_AUTO_SUBS)
        self.convert_subs = QCheckBox("Convert subtitles to SRT")
        self.convert_subs.setChecked(self.settings.CONVERT_SUBS_TO_SRT)
        subs_form.addRow(self.subtitles_enabled)
        subs_form.addRow("Languages:", self.languages_input)
        subs_form.addRow(self.auto_subs)
        subs_form.addRow(self.convert_subs)
        tabs.addTab(subs, "Subtitles")

        # Playlist
        pl = QWidget()
        pl_form = QFormLayout(pl)
        self.enable_archive = QCheckBox("Enable download archive")
        self.enable_archive.setChecked(self.settings.ENABLE_ARCHIVE)
        self.archive_path_input = QLineEdit(str(self.settings.ARCHIVE_PATH))
        self.archive_path_input.setReadOnly(True)
        self.btn_browse_archive = QPushButton("Browse...")
        self.playlist_reverse = QCheckBox("Reverse playlist order")
        self.playlist_reverse.setChecked(self.settings.PLAYLIST_REVERSE)
        self.playlist_items = QLineEdit(self.settings.PLAYLIST_ITEMS, placeholderText="e.g., 1,5-10,15")
        pl_form.addRow(self.enable_archive)
        pl_form.addRow("Archive File:", self.archive_path_input)
        pl_form.addRow(self.btn_browse_archive)
        pl_form.addRow(self.playlist_reverse)
        pl_form.addRow("Playlist Items:", self.playlist_items)
        tabs.addTab(pl, "Playlist")

        # Post Processing
        post = QWidget()
        post_form = QFormLayout(post)
        self.audio_normalize = QCheckBox("Normalize audio volume")
        self.audio_normalize.setChecked(self.settings.AUDIO_NORMALIZE)
        self.add_metadata = QCheckBox("Add metadata to files")
        self.add_metadata.setChecked(self.settings.ADD_METADATA)
        self.crop_covers = QCheckBox("Crop audio covers to 1:1 after queue")
        self.crop_covers.setChecked(self.settings.CROP_AUDIO_COVERS)
        self.custom_ffmpeg = QLineEdit(self.settings.CUSTOM_FFMPEG_ARGS, placeholderText="-c:v libx265 -crf 23")
        post_form.addRow(self.audio_normalize)
        post_form.addRow(self.add_metadata)
        post_form.addRow(self.crop_covers)
        post_form.addRow("Custom FFmpeg Args:", self.custom_ffmpeg)
        tabs.addTab(post, "Post-Processing")

        # Output
        out = QWidget()
        out_form = QFormLayout(out)
        self.organize_uploader = QCheckBox("Organize by uploader (create folders)")
        self.organize_uploader.setChecked(self.settings.ORGANIZE_BY_UPLOADER)
        self.date_after = QLineEdit(self.settings.DATEAFTER, placeholderText="YYYYMMDD")
        self.btn_date_picker = QPushButton("Select Date...")
        out_form.addRow(self.organize_uploader)
        out_form.addRow("Only Download After:", self.date_after)
        out_form.addRow(self.btn_date_picker)
        tabs.addTab(out, "Output")

        # Experimental
        exp = QWidget()
        exp_form = QFormLayout(exp)
        self.live_stream = QCheckBox("Record live streams from start")
        self.live_stream.setChecked(self.settings.LIVE_FROM_START)
        self.yt_music = QCheckBox("Enhanced YouTube Music metadata")
        self.yt_music.setChecked(self.settings.YT_MUSIC_METADATA)
        exp_form.addRow(self.live_stream)
        exp_form.addRow(self.yt_music)
        tabs.addTab(exp, "Experimental")

        # Behavior
        self.subtitles_enabled.toggled.connect(self._update_sub_controls)
        self.enable_archive.toggled.connect(self._update_archive_controls)
        self._update_sub_controls(self.settings.WRITE_SUBS)
        self._update_archive_controls(self.settings.ENABLE_ARCHIVE)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)

        # Connections
        self.btn_browse_cookies.clicked.connect(self._browse_cookies)
        self.btn_browse_archive.clicked.connect(self._browse_archive)
        self.btn_date_picker.clicked.connect(self._pick_date)

    def _browse_cookies(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Cookies File", str(self.settings.BASE_DIR), "Text Files (*.txt);;All Files (*)")
        if path:
            self.cookies_path_input.setText(path)

    def _browse_archive(self):
        path, _ = QFileDialog.getSaveFileName(self, "Select Archive File", str(self.settings.BASE_DIR), "Text Files (*.txt);;All Files (*)")
        if path:
            self.archive_path_input.setText(path)

    def _pick_date(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Select Date")
        dlg.setStyleSheet(AppStyles.DIALOG)
        v = QVBoxLayout(dlg)
        cal = QCalendarWidget()
        cal.setGridVisible(True)
        v.addWidget(cal)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        v.addWidget(bb)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        if dlg.exec():
            qd = cal.selectedDate()
            self.date_after.setText(qd.toString("yyyyMMdd"))

    def _update_sub_controls(self, enabled: bool):
        self.languages_input.setEnabled(enabled)
        self.auto_subs.setEnabled(enabled)
        self.convert_subs.setEnabled(enabled)

    def _update_archive_controls(self, enabled: bool):
        self.archive_path_input.setEnabled(enabled)
        self.btn_browse_archive.setEnabled(enabled)

    def _validate_and_accept(self):
        proxy_url = self.proxy_input.text().strip()
        if proxy_url and not (proxy_url.startswith("http://") or proxy_url.startswith("socks5://")):
            QMessageBox.warning(self, "Invalid Proxy", "Proxy URL must start with http:// or socks5://")
            return

        if self.subtitles_enabled.isChecked():
            langs = self.languages_input.text().strip()
            if not langs:
                QMessageBox.warning(self, "Missing Languages", "Please specify at least one language code")
                return
            if not all(2 <= len(x.strip()) <= 3 for x in langs.split(",")):
                QMessageBox.warning(self, "Invalid Languages", "Language codes should be 2-3 letters (e.g., en, es, fra)")
                return

        date_str = self.date_after.text().strip()
        if date_str:
            try:
                datetime.datetime.strptime(date_str, "%Y%m%d")
            except ValueError:
                QMessageBox.warning(self, "Invalid Date", "Date must be in YYYYMMDD format (e.g., 20240101)")
                return

        self.accept()

    def get_settings(self) -> dict:
        sb = [code for code, cb in self.category_cb.items() if cb.isChecked()]
        ch_mode = "none"
        if self.chapters_embed.isChecked():
            ch_mode = "embed"
        if self.chapters_split.isChecked():
            ch_mode = "split"

        return {
            "PROXY_URL": self.proxy_input.text().strip(),
            "COOKIES_PATH": Path(self.cookies_path_input.text().strip()),
            "COOKIES_FROM_BROWSER": self.cookies_browser_combo.currentText().strip(),
            "SPONSORBLOCK_CATEGORIES": sb,
            "CHAPTERS_MODE": ch_mode,
            "WRITE_SUBS": self.subtitles_enabled.isChecked(),
            "SUB_LANGS": self.languages_input.text().strip(),
            "WRITE_AUTO_SUBS": self.auto_subs.isChecked(),
            "CONVERT_SUBS_TO_SRT": self.convert_subs.isChecked(),
            "ENABLE_ARCHIVE": self.enable_archive.isChecked(),
            "ARCHIVE_PATH": Path(self.archive_path_input.text().strip()),
            "PLAYLIST_REVERSE": self.playlist_reverse.isChecked(),
            "PLAYLIST_ITEMS": self.playlist_items.text().strip(),
            "AUDIO_NORMALIZE": self.audio_normalize.isChecked(),
            "ADD_METADATA": self.add_metadata.isChecked(),
            "CROP_AUDIO_COVERS": self.crop_covers.isChecked(),
            "CUSTOM_FFMPEG_ARGS": self.custom_ffmpeg.text().strip(),
            "ORGANIZE_BY_UPLOADER": self.organize_uploader.isChecked(),
            "DATEAFTER": self.date_after.text().strip(),
            "LIVE_FROM_START": self.live_stream.isChecked(),
            "YT_MUSIC_METADATA": self.yt_music.isChecked(),
            "LIMIT_RATE": self.limit_rate_input.text().strip(),
            "RETRIES": self.retries_spin.value(),
        }