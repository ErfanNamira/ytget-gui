from __future__ import annotations

import os
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from PySide6.QtCore import Qt, QThread, QTimer, QSettings, QUrl
from PySide6.QtGui import QAction, QActionGroup, QIcon, QPalette, QGuiApplication, QTextCursor, QColor
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QListWidget,
    QListWidgetItem, QLineEdit, QComboBox, QPushButton, QTextEdit, QFileDialog,
    QMenuBar, QMessageBox, QStyle
)

from ytget.settings import AppSettings
from ytget.styles import AppStyles
from ytget.utils.validators import is_youtube_url
from ytget.dialogs.preferences import PreferencesDialog
from ytget.dialogs.advanced import AdvancedOptionsDialog
from ytget.widgets.queue_item import QueueItemWidget
from ytget.workers.title_fetcher import TitleFetcher
from ytget.workers.download_worker import DownloadWorker
from ytget.workers.cover_crop_worker import CoverCropWorker


def short(title: str, n: int = 35) -> str:
    return title[:n] + "..." if len(title) > n else title


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = AppSettings()
        self.styles = AppStyles()

        self.queue: List[Dict[str, Any]] = []
        self.current_download_item: Optional[Dict[str, Any]] = None
        self.is_downloading = False
        self.queue_paused = True
        self.post_queue_action = "Keep"  # Keep | Shutdown | Sleep | Restart | Close

        # Threads
        self.download_thread: Optional[QThread] = None
        self.download_worker: Optional[DownloadWorker] = None
        self.title_fetch_thread: Optional[QThread] = None
        self.title_fetcher: Optional[TitleFetcher] = None
        self.cover_thread: Optional[QThread] = None
        self.cover_worker: Optional[CoverCropWorker] = None

        self._setup_ui()
        self._setup_connections()
        self._setup_menu()
        self._restore_window()
        self._log_startup()

    # ---------- UI ----------

    def _setup_ui(self):
        self.setWindowTitle(f"{self.settings.APP_NAME} {self.settings.VERSION}")
        icon_candidates = [
            self.settings.BASE_DIR / "icon.ico",
            self.settings.INTERNAL_DIR / "icon.ico",
            self.settings.BASE_DIR / "icon.png",
            self.settings.INTERNAL_DIR / "icon.png",
        ]
        for p in icon_candidates:
            if p.exists():
                self.setWindowIcon(QIcon(str(p)))
                break

        self.resize(980, 680)
        self.setStyleSheet(self.styles.MAIN)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(5, 5, 5, 5)

        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # Left: Queue
        queue_container = QWidget()
        queue_layout = QVBoxLayout(queue_container)
        queue_layout.setContentsMargins(0, 0, 0, 0)
        self.queue_list = QListWidget()
        self.queue_list.setStyleSheet(self.styles.QUEUE)
        queue_layout.addWidget(self.queue_list)
        splitter.addWidget(queue_container)
        splitter.setStretchFactor(0, 1)

        # Right: Controls
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(10, 0, 0, 0)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 2)

        # URL input
        self.url_input = QLineEdit(placeholderText="🔎 Paste YouTube URL and press Enter")
        self.url_input.setStyleSheet("padding: 8px; font-size: 16px;")
        right_layout.addWidget(self.url_input)

        # Format row
        format_row = QHBoxLayout()
        self.format_box = QComboBox()
        self.format_box.addItems(self.settings.RESOLUTIONS.keys())
        self.format_box.setStyleSheet("padding: 8px; font-size: 15px;")
        format_row.addWidget(self.format_box, 3)

        self.btn_advanced = QPushButton("⚙️ Advanced")
        self.btn_advanced.setStyleSheet(AppStyles.BUTTON.format(
            bg_color=AppStyles.INFO_COLOR, text_color="white", hover_color="#81d4fa"
        ))
        format_row.addWidget(self.btn_advanced, 1)
        right_layout.addLayout(format_row)

        # Buttons
        btn_row = QHBoxLayout()
        self.btn_add_queue = QPushButton("➕ Add to Queue", enabled=False)
        self.btn_start_queue = QPushButton("▶️ Start Queue")
        self.btn_pause_queue = QPushButton("⏸️ Pause Queue", enabled=False)

        self.btn_add_queue.setStyleSheet(self.styles.BUTTON.format(
            bg_color=AppStyles.INFO_COLOR, text_color="white", hover_color="#81d4fa"
        ))
        self.btn_start_queue.setStyleSheet(self.styles.BUTTON.format(
            bg_color=AppStyles.SUCCESS_COLOR, text_color="black", hover_color="#69f0ae"
        ))
        self.btn_pause_queue.setStyleSheet(self.styles.BUTTON.format(
            bg_color=AppStyles.WARNING_COLOR, text_color="black", hover_color="#ffd54f"
        ))
        btn_row.addWidget(self.btn_add_queue)
        btn_row.addWidget(self.btn_start_queue)
        btn_row.addWidget(self.btn_pause_queue)
        right_layout.addLayout(btn_row)

        # Log
        self.log_output = QTextEdit(readOnly=True)
        self.log_output.setStyleSheet(self.styles.LOG)
        right_layout.addWidget(self.log_output)

        # Initial splitter sizes after show
        QTimer.singleShot(100, lambda: splitter.setSizes([self.width() // 3, self.width() * 2 // 3]))

        # DnD
        self.setAcceptDrops(True)

    def _setup_connections(self):
        self.url_input.textChanged.connect(self._on_url_text_changed)
        self.url_input.returnPressed.connect(self._add_to_queue)
        self.btn_add_queue.clicked.connect(self._add_to_queue)
        self.btn_start_queue.clicked.connect(self._start_queue)
        self.btn_pause_queue.clicked.connect(self._pause_queue)
        self.btn_advanced.clicked.connect(self._show_advanced_options)

    def _setup_menu(self):
        menubar: QMenuBar = self.menuBar()
        menubar.setStyleSheet("QMenuBar { background-color: #333; } QMenu::item:selected { background-color: #555; }")

        # File
        m_file = menubar.addMenu("File")
        m_file.addAction("Save Queue", self._save_queue_to_disk, "Ctrl+S")
        m_file.addAction("Load Queue", self._load_queue_from_disk, "Ctrl+O")
        m_file.addSeparator()
        m_file.addAction("Exit", self.close, "Ctrl+Q")

        # Settings
        m_settings = menubar.addMenu("Settings")
        m_settings.addAction("Set Download Folder...", self._set_download_path)
        m_settings.addAction("Set Cookies File...", self._set_cookies_path)
        m_settings.addAction("Preferences...", self._show_preferences, "Ctrl+P")
        m_settings.addSeparator()

        # Post-queue
        post_menu = m_settings.addMenu("When Queue Finishes...")
        action_group = QActionGroup(self)
        action_group.setExclusive(True)
        actions = {
            "Keep Running": "Keep", "Shutdown PC": "Shutdown",
            "Sleep PC": "Sleep", "Restart PC": "Restart", "Close YTGet": "Close"
        }
        for text, value in actions.items():
            act = QAction(text, self, checkable=True)
            if value == self.post_queue_action:
                act.setChecked(True)
            act.triggered.connect(lambda checked, v=value: self._set_post_queue_action(v))
            action_group.addAction(act)
            post_menu.addAction(act)

        # Help
        m_help = menubar.addMenu("Help")
        m_help.addAction("Check for Updates", self._check_for_updates)
        m_help.addAction("Open Download Folder", lambda: webbrowser.open(self.settings.DOWNLOADS_DIR.as_uri()))
        m_help.addAction("About", self._show_about)

    # ---------- Startup / Logging ----------

    def _log_startup(self):
        self.log("💡 Welcome to YTGet! Paste a URL to Begin.\n", AppStyles.INFO_COLOR)
        self.log(f"📂 Download Folder: {self.settings.DOWNLOADS_DIR}\n", AppStyles.INFO_COLOR)
        self.log(f"🔧 Using binaries from: {self.settings.FFMPEG_PATH.parent}\n", AppStyles.INFO_COLOR)

        # Sanity hints (no hard failure to keep cross-platform friendly)
        if not self.settings.YT_DLP_PATH.exists():
            self.log("⚠️ yt-dlp not found in app folder or PATH. Set it in Preferences or install system-wide.\n", AppStyles.WARNING_COLOR)
        if not self.settings.FFMPEG_PATH.exists() or not self.settings.FFPROBE_PATH.exists():
            self.log("⚠️ ffmpeg/ffprobe not found in app folder or PATH. Set in Preferences or install system-wide.\n", AppStyles.WARNING_COLOR)

        # Log relevant toggles
        if self.settings.PROXY_URL:
            self.log(f"🌐 Proxy: {self.settings.PROXY_URL}\n", AppStyles.INFO_COLOR)
        if self.settings.SPONSORBLOCK_CATEGORIES:
            self.log(f"⏩ SponsorBlock: {', '.join(self.settings.SPONSORBLOCK_CATEGORIES)}\n", AppStyles.INFO_COLOR)
        if self.settings.CHAPTERS_MODE != "none":
            self.log(f"📖 Chapters: {self.settings.CHAPTERS_MODE}\n", AppStyles.INFO_COLOR)
        if self.settings.WRITE_SUBS:
            self.log(f"📝 Subtitles: {self.settings.SUB_LANGS}\n", AppStyles.INFO_COLOR)
        if self.settings.ENABLE_ARCHIVE:
            self.log(f"📚 Archive: {self.settings.ARCHIVE_PATH}\n", AppStyles.INFO_COLOR)
        if self.settings.PLAYLIST_REVERSE:
            self.log("↩️ Playlist Reverse: On\n", AppStyles.INFO_COLOR)
        if self.settings.AUDIO_NORMALIZE:
            self.log("🔊 Audio Normalize: On\n", AppStyles.INFO_COLOR)
        if self.settings.LIMIT_RATE:
            self.log(f"📉 Rate Limit: {self.settings.LIMIT_RATE}\n", AppStyles.INFO_COLOR)
        if self.settings.ORGANIZE_BY_UPLOADER:
            self.log("🗂️ Organize by Uploader: On\n", AppStyles.INFO_COLOR)
        if self.settings.DATEAFTER:
            self.log(f"📅 Only After: {self.settings.DATEAFTER}\n", AppStyles.INFO_COLOR)
        if self.settings.LIVE_FROM_START:
            self.log("🔴 Live from Start: On\n", AppStyles.INFO_COLOR)
        if self.settings.YT_MUSIC_METADATA:
            self.log("🎵 Enhanced YouTube Music Metadata: On\n", AppStyles.INFO_COLOR)
        if self.settings.CROP_AUDIO_COVERS:
            self.log("🖼️ Will crop audio covers to 1:1 after queue.\n", AppStyles.INFO_COLOR)
        if self.settings.CLIP_START and self.settings.CLIP_END:
            self.log(f"⏱️ Clip: {self.settings.CLIP_START}-{self.settings.CLIP_END}\n", AppStyles.INFO_COLOR)

    # ---------- Drag and drop ----------

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            text = ""
            if event.mimeData().hasUrls():
                urls = [u.toString() for u in event.mimeData().urls()]
                text = " ".join(urls)
            else:
                text = event.mimeData().text()
            if any("youtu" in t for t in text.split()):
                event.acceptProposedAction()
                return
        super().dragEnterEvent(event)

    def dropEvent(self, event):
        urls: List[str] = []
        if event.mimeData().hasUrls():
            urls = [u.toString() for u in event.mimeData().urls()]
        elif event.mimeData().hasText():
            urls = [t for t in event.mimeData().text().split()]
        added = 0
        for u in urls:
            if is_youtube_url(u):
                self._fetch_title(u)
                added += 1
        if added == 0:
            self.log("⚠️ No valid YouTube URLs detected in drop.\n", AppStyles.WARNING_COLOR)
        event.acceptProposedAction()

    # ---------- Queue / Title ----------

    def _on_url_text_changed(self, text: str):
        self.btn_add_queue.setEnabled(is_youtube_url(text))

    def _add_to_queue(self):
        url = self.url_input.text().strip()
        if not is_youtube_url(url):
            self.log("⚠️ Invalid YouTube URL format.\n", AppStyles.WARNING_COLOR)
            return
        self.url_input.clear()
        self.btn_add_queue.setEnabled(False)
        self._fetch_title(url)

    def _fetch_title(self, url: str):
        self.log(f"🔎 Fetching title for: {url[:60]}...\n", AppStyles.INFO_COLOR)
        # Clean up existing title thread if needed
        try:
            if self.title_fetch_thread and self.title_fetch_thread.isRunning():
                self.title_fetch_thread.quit()
                self.title_fetch_thread.wait()
        except RuntimeError:
            pass

        self.title_fetch_thread = QThread()
        self.title_fetcher = TitleFetcher(
            url=url,
            yt_dlp_path=self.settings.YT_DLP_PATH,
            ffmpeg_dir=self.settings.FFMPEG_PATH.parent,
            cookies_path=self.settings.COOKIES_PATH,
            proxy_url=self.settings.PROXY_URL,
        )
        self.title_fetcher.moveToThread(self.title_fetch_thread)
        self.title_fetch_thread.started.connect(self.title_fetcher.run)
        self.title_fetcher.title_fetched.connect(self._on_title_fetched)
        self.title_fetcher.error.connect(self._on_title_error)
        self.title_fetcher.finished.connect(self.title_fetch_thread.quit)
        self.title_fetch_thread.finished.connect(self.title_fetcher.deleteLater)
        self.title_fetch_thread.finished.connect(self.title_fetch_thread.deleteLater)
        self.title_fetch_thread.start()

    def _on_title_fetched(self, url: str, title: str):
        fmt_text = self.format_box.currentText()
        item = {"url": url, "title": title, "format_code": self.settings.RESOLUTIONS[fmt_text]}
        self.queue.append(item)
        self.log(f"✅ Added to queue: {short(title)}\n", AppStyles.SUCCESS_COLOR)
        self._refresh_queue_list()
        self._update_button_states()

    def _on_title_error(self, url: str, msg: str):
        self.log(f"❌ Error fetching title for {url[:60]}: {msg}\n", AppStyles.ERROR_COLOR)
        self.btn_add_queue.setEnabled(True)

    # ---------- Queue control ----------

    def _start_queue(self):
        if self.is_downloading and not self.queue_paused:
            self.log("ℹ️ Queue is already running.\n", AppStyles.INFO_COLOR)
            return
        if not self.queue:
            self.log("⚠️ Queue is empty. Add items to start.\n", AppStyles.WARNING_COLOR)
            return

        self.queue_paused = False
        self.log(("▶️ Resuming" if self.is_downloading else "▶️ Starting") + " queue processing...\n", AppStyles.SUCCESS_COLOR)
        self._download_next()
        self._update_button_states()

    def _pause_queue(self):
        if not self.is_downloading:
            self.log("ℹ️ Queue is not running.\n", AppStyles.INFO_COLOR)
            return
        self.queue_paused = True
        if self.download_worker:
            self.download_worker.cancel()
        self._update_button_states()

    def _download_next(self):
        if self.queue_paused or self.is_downloading or not self.queue:
            if not self.queue and not self.is_downloading:
                self._on_queue_finished()
            return

        self.is_downloading = True
        self.current_download_item = self.queue[0]
        self._refresh_queue_list()
        self._update_button_states()

        # Clean up previous download thread
        try:
            if self.download_thread and self.download_thread.isRunning():
                self.download_thread.quit()
                self.download_thread.wait()
        except RuntimeError:
            pass

        self.download_thread = QThread()
        self.download_worker = DownloadWorker(self.current_download_item, self.settings)
        self.download_worker.moveToThread(self.download_thread)
        self.download_thread.started.connect(self.download_worker.run)
        self.download_worker.log.connect(self.log)
        self.download_worker.error.connect(lambda m: self.log(f"❌ {m}\n", AppStyles.ERROR_COLOR))
        self.download_worker.finished.connect(self._on_download_finished)
        self.download_worker.finished.connect(self.download_thread.quit)
        self.download_thread.finished.connect(self.download_worker.deleteLater)
        self.download_thread.finished.connect(self.download_thread.deleteLater)
        self.download_thread.start()

    def _on_download_finished(self, exit_code: int):
        self.is_downloading = False
        self.current_download_item = None
        if exit_code == 0 and self.queue:
            self.queue.pop(0)
        self._refresh_queue_list()
        self._update_button_states()

        if not self.queue_paused and self.queue:
            self._download_next()
        elif not self.queue:
            self._on_queue_finished()

    def _on_queue_finished(self):
        self.log(f"🏁 Queue complete! Action: {self.post_queue_action}.\n", AppStyles.SUCCESS_COLOR)

        if getattr(self.settings, "CROP_AUDIO_COVERS", False):
            self.log("🖼️ Cropping audio covers to 1:1. This may take a moment...\n", AppStyles.INFO_COLOR)
            # Clean cover thread if needed
            try:
                if self.cover_thread and self.cover_thread.isRunning():
                    self.cover_thread.quit()
                    self.cover_thread.wait()
            except RuntimeError:
                pass

            self.cover_thread = QThread()
            self.cover_worker = CoverCropWorker(self.settings.DOWNLOADS_DIR)
            self.cover_worker.moveToThread(self.cover_thread)
            self.cover_thread.started.connect(self.cover_worker.run)
            self.cover_worker.log.connect(self.log)
            self.cover_worker.finished.connect(self.cover_thread.quit)
            self.cover_worker.finished.connect(lambda: self._perform_post_queue_action(self.post_queue_action))
            self.cover_thread.finished.connect(self.cover_worker.deleteLater)
            self.cover_thread.finished.connect(self.cover_thread.deleteLater)
            self.cover_thread.start()
        else:
            self._perform_post_queue_action(self.post_queue_action)

    def _perform_post_queue_action(self, action: str):
        if action == "Close":
            self.close()
            return

        if sys.platform != "win32":
            self.log(f"⚠️ '{action}' is only supported on Windows.\n", AppStyles.WARNING_COLOR)
            return

        if action == "Shutdown":
            os.system("shutdown /s /t 60")
        elif action == "Sleep":
            os.system('timeout /t 60 && powershell -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Application]::SetSuspendState(\'Suspend\', $false, $false)"')
        elif action == "Restart":
            os.system("shutdown /r /t 60")

    # ---------- UI helpers ----------

    def _refresh_queue_list(self):
        self.queue_list.clear()
        for i, item in enumerate(self.queue):
            widget = QueueItemWidget(item["title"], item["url"])
            list_item = QListWidgetItem()
            list_item.setSizeHint(widget.sizeHint())
            widget.btn_delete.clicked.connect(lambda checked=False, idx=i: self._remove_queue_item(idx))
            widget.btn_up.clicked.connect(lambda checked=False, idx=i: self._move_queue_item(idx, -1))
            widget.btn_down.clicked.connect(lambda checked=False, idx=i: self._move_queue_item(idx, 1))
            if item == self.current_download_item:
                widget.set_active(True)
            self.queue_list.addItem(list_item)
            self.queue_list.setItemWidget(list_item, widget)

    def _remove_queue_item(self, index: int):
        if not (0 <= index < len(self.queue)):
            return
        if self.is_downloading and self.queue[index] == self.current_download_item:
            self.log("⚠️ Cannot remove an active download. Pause the queue first.\n", AppStyles.WARNING_COLOR)
            return
        item = self.queue.pop(index)
        self.log(f"🗑️ Removed from queue: {short(item['title'])}\n", AppStyles.INFO_COLOR)
        self._refresh_queue_list()
        self._update_button_states()

    def _move_queue_item(self, index: int, step: int):
        new_index = index + step
        if not (0 <= index < len(self.queue) and 0 <= new_index < len(self.queue)):
            return
        if self.is_downloading and (self.queue[index] == self.current_download_item or self.queue[new_index] == self.current_download_item):
            self.log("⚠️ Cannot move an active download.\n", AppStyles.WARNING_COLOR)
            return
        self.queue.insert(new_index, self.queue.pop(index))
        self._refresh_queue_list()

    def _update_button_states(self):
        has_items = bool(self.queue)
        self.btn_start_queue.setEnabled(has_items and (self.queue_paused or not self.is_downloading))
        self.btn_pause_queue.setEnabled(self.is_downloading and not self.queue_paused)
        self.btn_add_queue.setEnabled(not self.is_downloading or self.queue_paused)

    def log(self, text: str, color: str = AppStyles.TEXT_COLOR):
        self.log_output.setTextColor(QPalette().color(QPalette.Text))  # reset
        cursor = self.log_output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = self.log_output.currentCharFormat()
        fmt.setForeground(QColor(color))
        self.log_output.setCurrentCharFormat(fmt)
        cursor.insertText(text)
        self.log_output.ensureCursorVisible()

    # ---------- Menu actions ----------

    def _save_queue_to_disk(self):
        if not self.queue:
            self.log("⚠️ Queue is empty, nothing to save.\n", AppStyles.WARNING_COLOR)
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Queue", str(self.settings.BASE_DIR / "queue.json"), "JSON Files (*.json)")
        if path:
            try:
                import json
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self.queue, f, indent=2)
                self.log(f"💾 Queue saved to {path}\n", AppStyles.SUCCESS_COLOR)
                self._refresh_queue_list()
            except Exception as e:
                self.log(f"❌ Failed to save queue: {e}\n", AppStyles.ERROR_COLOR)

    def _load_queue_from_disk(self):
        if self.is_downloading:
            self.log("⚠️ Cannot load a new queue while a download is active.\n", AppStyles.WARNING_COLOR)
            return
        path, _ = QFileDialog.getOpenFileName(self, "Load Queue", str(self.settings.BASE_DIR), "JSON Files (*.json)")
        if path:
            try:
                import json
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if not isinstance(loaded, list):
                    raise ValueError("Invalid queue file format.")
                self.queue = loaded
                self._refresh_queue_list()
                self._update_button_states()
                self.log(f"📂 Queue loaded from {path}\n", AppStyles.SUCCESS_COLOR)
            except Exception as e:
                self.log(f"❌ Failed to load queue: {e}\n", AppStyles.ERROR_COLOR)

    def _set_download_path(self):
        path_str = QFileDialog.getExistingDirectory(self, "Select Download Folder", str(self.settings.DOWNLOADS_DIR))
        if path_str:
            self.settings.set_download_path(Path(path_str))
            self.log(f"📥 Download folder set to: {path_str}\n", AppStyles.INFO_COLOR)

    def _set_cookies_path(self):
        path_str, _ = QFileDialog.getOpenFileName(self, "Select Cookies File", str(self.settings.BASE_DIR), "Text Files (*.txt);;All Files (*)")
        if path_str:
            self.settings.COOKIES_PATH = Path(path_str)
            self.settings.save_config()
            self.log(f"🍪 Cookies path set to: {path_str}\n", AppStyles.INFO_COLOR)

    def _set_post_queue_action(self, action: str):
        self.post_queue_action = action
        self.log(f"⚙️ Post-queue action set to: {action}\n", AppStyles.INFO_COLOR)

    def _show_preferences(self):
        dlg = PreferencesDialog(self, self.settings)
        if dlg.exec():
            new = dlg.get_settings()
            self.settings.PROXY_URL = new["PROXY_URL"]
            self.settings.COOKIES_PATH = new["COOKIES_PATH"]
            self.settings.COOKIES_FROM_BROWSER = new["COOKIES_FROM_BROWSER"]
            self.settings.SPONSORBLOCK_CATEGORIES = new["SPONSORBLOCK_CATEGORIES"]
            self.settings.CHAPTERS_MODE = new["CHAPTERS_MODE"]
            self.settings.WRITE_SUBS = new["WRITE_SUBS"]
            self.settings.SUB_LANGS = new["SUB_LANGS"]
            self.settings.WRITE_AUTO_SUBS = new["WRITE_AUTO_SUBS"]
            self.settings.CONVERT_SUBS_TO_SRT = new["CONVERT_SUBS_TO_SRT"]
            self.settings.ENABLE_ARCHIVE = new["ENABLE_ARCHIVE"]
            self.settings.ARCHIVE_PATH = new["ARCHIVE_PATH"]
            self.settings.PLAYLIST_REVERSE = new["PLAYLIST_REVERSE"]
            self.settings.PLAYLIST_ITEMS = new["PLAYLIST_ITEMS"]
            self.settings.AUDIO_NORMALIZE = new["AUDIO_NORMALIZE"]
            self.settings.ADD_METADATA = new["ADD_METADATA"]
            self.settings.CROP_AUDIO_COVERS = new["CROP_AUDIO_COVERS"]
            self.settings.CUSTOM_FFMPEG_ARGS = new["CUSTOM_FFMPEG_ARGS"]
            self.settings.ORGANIZE_BY_UPLOADER = new["ORGANIZE_BY_UPLOADER"]
            self.settings.DATEAFTER = new["DATEAFTER"]
            self.settings.LIVE_FROM_START = new["LIVE_FROM_START"]
            self.settings.YT_MUSIC_METADATA = new["YT_MUSIC_METADATA"]
            self.settings.LIMIT_RATE = new["LIMIT_RATE"]
            self.settings.RETRIES = new["RETRIES"]
            self.settings.save_config()
            self.log("⚙️ Settings Updated and Saved.\n", AppStyles.INFO_COLOR)
            self._log_startup()

    def _show_advanced_options(self):
        dlg = AdvancedOptionsDialog(self, self.settings)
        if dlg.exec():
            o = dlg.get_options()
            self.settings.CLIP_START = o["CLIP_START"]
            self.settings.CLIP_END = o["CLIP_END"]
            self.settings.PLAYLIST_ITEMS = o["PLAYLIST_ITEMS"]
            self.settings.PLAYLIST_REVERSE = o["PLAYLIST_REVERSE"]
            self.settings.save_config()
            self.log("⚙️ Advanced Options Updated.\n", AppStyles.INFO_COLOR)
            if self.settings.CLIP_START and self.settings.CLIP_END:
                self.log(f"⏱️ Clip Extraction Set: {self.settings.CLIP_START}-{self.settings.CLIP_END}\n", AppStyles.INFO_COLOR)
            if self.settings.PLAYLIST_ITEMS:
                self.log(f"🎬 Playlist Items Set: {self.settings.PLAYLIST_ITEMS}\n", AppStyles.INFO_COLOR)
            if self.settings.PLAYLIST_REVERSE:
                self.log("↩️ Playlist Reverse Order Enabled.\n", AppStyles.INFO_COLOR)

    def _check_for_updates(self):
        self.log("🌐 Checking for Updates...\n", AppStyles.INFO_COLOR)
        try:
            r = requests.head(f"{self.settings.GITHUB_URL}/releases/latest", allow_redirects=True, timeout=6)
            r.raise_for_status()
            latest_tag = r.url.rstrip("/").split("/")[-1].lstrip("v")
            if latest_tag > self.settings.VERSION:
                reply = QMessageBox.information(
                    self, "Update Available",
                    f"A New Version ({latest_tag}) is Available!\n"
                    f"You are Using Version {self.settings.VERSION}.\n\n"
                    "Open the Releases Page?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    webbrowser.open(f"{self.settings.GITHUB_URL}/releases")
            else:
                QMessageBox.information(self, "Up to Date", "You are Using the Latest Version.")
        except requests.RequestException as e:
            QMessageBox.warning(self, "Update Check Failed", f"Could Not Check For Updates: {e}")

    def _show_about(self):
        QMessageBox.about(self, "About YTGet",
                          f"<h2>{self.settings.APP_NAME} {self.settings.VERSION}</h2>"
                          "<p>A Simple Yet Powerful GUI For yt-dlp.</p>"
                          "<p>Built with Python and PySide6.</p>"
                          f"<p><a href='{self.settings.GITHUB_URL}'>Visit on GitHub</a></p>")

    # ---------- Window state ----------

    def _restore_window(self):
        qs = QSettings("YTGet", "YTGet")
        geom = qs.value("geometry")
        state = qs.value("windowState")
        if geom:
            self.restoreGeometry(geom)
        if state:
            self.restoreState(state)

    def _save_window(self):
        qs = QSettings("YTGet", "YTGet")
        qs.setValue("geometry", self.saveGeometry())
        qs.setValue("windowState", self.saveState())

    def closeEvent(self, event):
        # Stop threads
        try:
            if self.download_thread and self.download_thread.isRunning():
                if self.download_worker:
                    self.download_worker.cancel()
                self.download_thread.quit()
                self.download_thread.wait()
        except RuntimeError:
            pass

        try:
            if self.title_fetch_thread and self.title_fetch_thread.isRunning():
                self.title_fetch_thread.quit()
                self.title_fetch_thread.wait()
        except RuntimeError:
            pass

        try:
            if self.cover_thread and self.cover_thread.isRunning():
                self.cover_thread.quit()
                self.cover_thread.wait()
        except RuntimeError:
            pass

        # Ask to save queue if not empty
        if self.queue:
            reply = QMessageBox.question(
                self, "Exit Confirmation",
                "You have Items in your Queue. Do you Want to Save the Queue Before Exiting?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
            )
            if reply == QMessageBox.Save:
                self._save_queue_to_disk()
                self._save_window()
                event.accept()
            elif reply == QMessageBox.Discard:
                self._save_window()
                event.accept()
            else:
                event.ignore()
        else:
            self._save_window()
            event.accept()