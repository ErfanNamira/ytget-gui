# File: ytget_gui/main_window.py

from __future__ import annotations

import os
import sys
import json
import re
import hashlib
import webbrowser
import platform
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from shutil import which

import requests
from PySide6.QtCore import Qt, QThread, QTimer, QSettings, QSize, Signal, Slot
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QIcon,
    QPalette,
    QGuiApplication,
    QTextCursor,
    QColor,
    QFont,
    QPixmap,
)
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QSplitter,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QComboBox,
    QPushButton,
    QTextEdit,
    QFileDialog,
    QMenuBar,
    QMessageBox,
    QFrame,
    QLabel,
    QProgressBar,
)

from ytget_gui.settings import AppSettings
from ytget_gui.styles import AppStyles
from ytget_gui.utils.validators import is_supported_url, is_youtube_url
from ytget_gui.dialogs.preferences import PreferencesDialog
from ytget_gui.dialogs.advanced import AdvancedOptionsDialog
from ytget_gui.dialogs.update_manager import UpdateManager
from ytget_gui.workers.download_worker import DownloadWorker
from ytget_gui.workers.cover_crop_worker import CoverCropWorker
from ytget_gui.widgets.queue_card import QueueCard
from ytget_gui.workers.title_fetch_manager import TitleFetchQueue
from ytget_gui.workers.thumb_fetcher import ThumbManager

def short(text: str, n: int = 50) -> str:
    return text[:n] + "..." if len(text) > n else text

QSS_THEME = """
/* Window */
QMainWindow {
  background: #0F1115;
  color: #E6EAF2;
  font-size: 14px;
}

/* Header (Top Bar) - High Saturation, Low Luminance Gradient */
#TopBar {
  /* Transition from Deep Azure to Deep Royal Purple */
  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #131C2E, stop:1 #1C132E);
  border: 1px solid #263042;
  border-radius: 12px;
}

/* Bottom Bar */
#BottomBar {
  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #131C2E, stop:1 #1C132E);
  border: 1px solid #263042;
  border-radius: 12px;
}

#Pane {
  background: #161A22;
  border: 1px solid #263042;
  border-radius: 12px;
}

/* Header Text - High Contrast White [cite: 110] */
#Brand {
  font-size: 20px;
  font-weight: 600;
  color: #FFFFFF;
}

/* Version Chip - No background or shadow box [cite: 111] */
#VersionChip {
  background: transparent;
  border: none;
  color: #8A95A8; 
  font-weight: 400;
  margin-left: 2px;
}

/* URL pill - Explicitly dark for depth [cite: 112] */
#UrlPillWrap {
  background: #0D1117;
  border: 1px solid #263042;
  border-radius: 22px;
}
#UrlPillWrap:hover { border-color: #3A77FF; }

#UrlPillWrap QLineEdit {
  background: transparent;
  border: none;
  color: #E6EAF2;
  padding: 10px 12px;
  font-size: 15px;
}

/* Buttons and Controls [cite: 113, 114, 115] */
#PillBtn {
  background: #2A3550;
  color: #E6EAF2;
  border: none;
  padding: 8px 12px;
  border-radius: 16px;
}
#PillBtn:hover { background: #36436A; }

#PillIconBtn {
  background: transparent;
  border: none;
  padding: 6px 10px;
  color: #A7B0C0;
}
#PillIconBtn:hover { color: #E6EAF2; }

#Chip, #ChipCombo {
  background: #1D2533;
  border: 1px solid #263042;
  color: #E6EAF2;
  border-radius: 16px;
  padding: 6px 10px;
}
#Chip:hover, #ChipCombo:hover { background: #2A3550; }

#ChipGhost, #Ghost {
  background: transparent;
  border: 1px solid #263042;
  color: #A7B0C0;
  border-radius: 12px;
  padding: 6px 10px;
}
#Ghost:hover { color: #E6EAF2; border-color: #2F3B55; }

/* Primary Button [cite: 118] */
#Primary {
  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6EA8FE, stop:1 #5476F0);
  color: #0F1115;
  border: none;
  padding: 10px 16px;
  border-radius: 10px;
  font-weight: 600;
}
#Primary:hover { background: #6A9CF6; }

#Secondary {
  background: #2A3550;
  color: #E6EAF2;
  border: none;
  padding: 10px 14px;
  border-radius: 10px;
}

/* Queue and Console Elements [cite: 120, 121, 122, 123] */
#PaneTitle {
  font-weight: 600;
  font-size: 16px;
  color: #E6EAF2;
}

#EmptyState {
  color: #8A95A8;
  background: #10141C;
  border: 1px dashed #263042;
  border-radius: 12px;
  padding: 28px;
}

#QueueHeader {
  background: #161A22;
  border: 1px solid #263042;
  border-radius: 12px;
  padding: 10px 12px;
}

#QueueTitle {
  font-size: 15px;
  font-weight: 600;
  color: #E6EAF2;
}

#CountChip {
  background: #1D2533;
  color: #A7B0C0;
  border: 1px solid #263042;
  border-radius: 999px;
  padding: 2px 8px;
}

#Search {
  background: #121620;
  border: 1px solid #263042;
  border-radius: 10px;
  padding: 6px 10px;
  color: #E6EAF2;
}
#Search:focus { border-color: #2F3B55; }

#SortCombo {
  background: #1D2533;
  border: 1px solid #263042;
  color: #E6EAF2;
  border-radius: 0;
  padding: 6px 10px;
}

/* Queue List [cite: 127] */
#QueueList {
  background: transparent;
  border: none;
}
QListWidget::item {
  background: transparent;
  border: none;
}

#QueueCard {
  background: #161A22;
  border: 1px solid #263042;
  border-radius: 12px;
}
#QueueCard:hover { border-color: #2F3B55; }

#CardTitle { font-weight: 600; color: #E6EAF2; }
#CardMeta { color: #8591A3; font-size: 12px; }

#Thumb {
  background: #0F141C;
  border: 1px solid #263042;
  border-radius: 8px;
}

#StatusChip {
  background: #1D2533;
  color: #E6EAF2;
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 12px;
  border: 1px solid #263042;
}

#DragHandle { color: #6A7487; }

#IconBtn {
  background: transparent;
  border: 1px solid #263042;
  color: #A7B0C0;
  border-radius: 8px;
  padding: 2px 8px;
}

/* Global Progress [cite: 133, 134] */
#Progress {
  background: #202839;
  border: 1px solid #263042;
  border-radius: 999px;
}
#Progress::chunk {
  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6EA8FE, stop:1 #5476F0);
  border-radius: 999px;
}

/* Console [cite: 135] */
#Console {
  background: #10141C;
  color: #E6EAF2;
  border: 1px solid #263042;
  border-radius: 10px;
  padding: 8px;
}

/* Scrollbar [cite: 137, 138] */
QScrollBar:vertical, QScrollBar:horizontal {
  background: transparent; border: none;
}
QScrollBar::handle {
  background: #2A3550; border-radius: 6px;
}
QScrollBar::handle:hover { background: #36436A; }

/* Bulk bar [cite: 139] */
#BulkBar {
  background: #121620;
  border: 1px solid #263042;
  border-radius: 10px;
  padding: 6px 10px;
  color: #E6EAF2;
}
"""

MAX_LOG_LINES = 200

class MainWindow(QMainWindow):
    # Signals to marshal work into the title-fetch worker thread
    enqueue_title = Signal(str)
    enqueue_titles = Signal(list)
    
    # Signals to marshal update checks into updater thread
    request_check_ytget_gui = Signal()
    request_check_ytdlp = Signal()
    request_download_ytdlp = Signal(str)    

    # Signal to marshal post‐queue actions back to GUI thread
    post_queue_action_signal = Signal(str)

    def __init__(self):
        super().__init__()
        self.settings = AppSettings()
        self.styles = AppStyles()

        # Update Manager
        self.updater = UpdateManager(self.settings, log_callback=None, parent=None)
        self.update_thread = QThread(self)
        self.updater.moveToThread(self.update_thread)

        # Requests routed into updater thread
        self.request_check_ytget_gui.connect(self.updater.check_ytget_gui_update, Qt.QueuedConnection)
        self.request_check_ytdlp.connect(self.updater.check_ytdlp_update, Qt.QueuedConnection)
        self.request_download_ytdlp.connect(self.updater.download_ytdlp, Qt.QueuedConnection)

        # Logs from updater to console (executed in GUI thread)
        self.updater.log_signal.connect(self.log)

        # ytget_gui update results
        self.updater.ytget_gui_ready.connect(self._on_ytget_gui_ready)
        self.updater.ytget_gui_uptodate.connect(self._on_ytget_gui_uptodate)
        self.updater.ytget_gui_error.connect(self._on_ytget_gui_error)

        # yt-dlp update results
        self.updater.ytdlp_ready.connect(self._on_ytdlp_ready)
        self.updater.ytdlp_uptodate.connect(self._on_ytdlp_uptodate)
        self.updater.ytdlp_error.connect(self._on_ytdlp_error)

        # yt-dlp download outcome
        self.updater.ytdlp_download_success.connect(self._on_ytdlp_download_success)
        self.updater.ytdlp_download_failed.connect(self._on_ytdlp_download_failed)

        self.update_thread.start()
        # ensure post‐queue actions run in GUI thread
        self.post_queue_action_signal.connect(
            self._perform_post_queue_action,
            Qt.QueuedConnection
        )

        # Thumbnail cache folder and async jobs
        self.thumb_cache_dir: Path = self.settings.BASE_DIR / "cache" / "thumbs"
        self.thumb_cache_dir.mkdir(parents=True, exist_ok=True)

        # Thumb manager (serializes thumbnail fetches)
        # Use a single worker by default to avoid race conditions and UI crashes
        self.thumb_manager = ThumbManager(self.thumb_cache_dir, self.settings, max_workers=1)
        self.thumb_manager.started.connect(self._on_thumb_started, Qt.QueuedConnection)
        self.thumb_manager.finished.connect(self._on_thumb_finished, Qt.QueuedConnection)
        self.thumb_manager.error.connect(self._on_thumb_error, Qt.QueuedConnection)

        # Optional dedupe set to avoid enqueueing same URL repeatedly
        self._pending_thumb_urls = set()

        # legacy per-job map (no longer used)
        self._thumb_jobs: Dict[str, Tuple[QThread, object]] = {}

        self.queue: List[Dict[str, Any]] = []
        self.current_download_item: Optional[Dict[str, Any]] = None
        self.is_downloading = False
        self.queue_paused = True
        self.post_queue_action = "Keep"  # Keep | Shutdown | Sleep | Restart | Close

        # For global progress
        self._initial_queue_len: int = 0

        # Threads
        self.download_thread: Optional[QThread] = None
        self.download_worker: Optional[DownloadWorker] = None
        self.cover_thread: Optional[QThread] = None
        self.cover_worker: Optional[CoverCropWorker] = None

        # Title fetch queue manager (single worker thread)
        self.title_queue_thread: Optional[QThread] = None
        self.title_queue: Optional[TitleFetchQueue] = None

        # Logging store for filter
        self._log_entries: List[Tuple[str, str, str]] = []  # (text, color, level)

        # Permanent queue file
        self.queue_file_path: Path = self.settings.BASE_DIR / "queue.json"

        # UI refs created in builders
        self.queue_list: QListWidget
        self.queue_empty_state: QLabel
        self.log_output: QTextEdit
        self.url_input: QLineEdit
        self.format_box: QComboBox
        self.btn_add_inline: QPushButton
        self.btn_start_queue: QPushButton
        self.btn_pause_queue: QPushButton
        self.btn_skip: QPushButton
        self.global_progress: QProgressBar
        self.post_action: QComboBox
        self.download_path_btn: QPushButton
        self.queue_pane: QWidget
        self.filter_combo: QComboBox

        # Queue header/bulk UI refs
        self.queue_title: QLabel
        self.count_chip: QLabel
        self.search_box: QLineEdit
        self.sort_combo: QComboBox
        self.bulk_bar: QFrame
        self.bulk_label: QLabel

        # App icon cache for reuse (e.g., Help button)
        self._app_icon: Optional[QIcon] = None

        self._setup_ui()
        self._setup_connections()
        self._setup_menu()

        # Start the title-fetch worker thread
        self._setup_title_fetch_queue()

        self._load_permanent_queue()
        self._restore_window()
        self._log_startup()

    def log(self, text: str, color: str = AppStyles.INFO_COLOR, level: str = "Info"):
        """
        Normalize and store log entries. 
        """
        if text is None:
            return

        # 1. Split by actual newlines to handle multi-line messages
        raw_lines = str(text).splitlines()
        
        for raw_line in raw_lines:
            # Clean up whitespace
            s = " ".join(raw_line.split()).strip()
            if not s:
                continue

            # 2. Icon Logic - MORE SPECIFIC CHECKS
            prefix = ""
            
            # CHECK 1: The Rocket - Only for the main start line
            clean_check = s.replace("🚀", "").strip()
            if clean_check.startswith("Starting Download for:"):
                prefix = "🚀 "
            
            # CHECK 2: Standard Status Icons
            elif level and str(level).lower() == "warning":
                prefix = "⚠️ "
            elif level and str(level).lower() == "error":
                prefix = "❌ "
            elif level and str(level).lower() in ["success", "process"]:
                # Only add checkmark if it's not already the "Starting Download" line
                prefix = "✅ "

            # CHECK 3: Action Icons (Merging/Deleting)
            elif "merger" in s.lower() or "merging" in s.lower():
                prefix = "📦 "
            elif "deleting" in s.lower():
                prefix = "🧹 "

            # 3. Construct Final String
            # Remove any existing rocket from 's' so we don't double it up
            final_content = s.replace("🚀", "").strip()
            final_text = f"{prefix}{final_content}".strip()
            
            final_color = color if color else AppStyles.INFO_COLOR
            final_level = level if level else "Info"

            # 4. Store in buffer
            if not hasattr(self, "_log_entries"):
                self._log_entries = []
            self._log_entries.append((final_text, final_color, final_level))

            # Buffer limit
            max_lines = getattr(self.settings, "MAX_LOG_LINES", 500)
            if len(self._log_entries) > max_lines:
                self._log_entries = self._log_entries[-max_lines:]

            # 5. UI Render
            filt_text = self.filter_combo.currentText() if hasattr(self, "filter_combo") else "All"
            if filt_text == "All":
                self._append_to_console(final_text, final_color)
            else:
                self._render_log()

    def _render_log(self):
        """Full buffer re-render (used for filtering)."""
        try:
            if not hasattr(self, "_log_entries") or not self.log_output:
                return
            filt_text = self.filter_combo.currentText() if hasattr(self, "filter_combo") else "All"
            
            self.log_output.blockSignals(True)
            self.log_output.clear()
            for text, color, level in self._log_entries:
                if filt_text != "All" and level != filt_text:
                    continue
                self._append_to_console(text, color)
            self.log_output.blockSignals(False)
            self.log_output.moveCursor(QTextCursor.End)
        except Exception:
            pass

    def _append_to_console(self, text: str, color: str = AppStyles.INFO_COLOR):
        """Appends exactly one line safely."""
        try:
            if not self.log_output: return
            self.log_output.moveCursor(QTextCursor.End)
            self.log_output.setTextColor(QColor(color))

            self.log_output.append(text)
            self.log_output.setTextColor(QColor(AppStyles.INFO_COLOR)) # Reset
            self.log_output.ensureCursorVisible()
        except Exception:
            pass

    # ---------- UI scaffold

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
                self._app_icon = QIcon(str(p))
                self.setWindowIcon(self._app_icon)
                break

        self.resize(1200, 780)

        # Font
        f = QFont("Inter", 10)
        self.setFont(f)

        # Apply dark theme
        self.setStyleSheet(QSS_THEME)

        # Root container
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(12)

        # Top bar
        self.top_bar = self._build_top_bar()
        outer.addWidget(self.top_bar)

        # Main split: Queue (1/3) | Console (2/3)
        self.main_split = QSplitter(Qt.Horizontal)
        self.main_split.setChildrenCollapsible(False)
        outer.addWidget(self.main_split, 1)

        self.queue_pane = self._build_queue_pane()
        self.console_pane = self._build_console_pane()

        self.main_split.addWidget(self.queue_pane)
        self.main_split.addWidget(self.console_pane)
        self.main_split.setStretchFactor(0, 1)
        self.main_split.setStretchFactor(1, 2)
        QTimer.singleShot(100, lambda: self.main_split.setSizes([int(self.width() * 0.38), int(self.width() * 0.62)]))

        # Bottom control bar
        self.bottom_bar = self._build_bottom_bar()
        outer.addWidget(self.bottom_bar)

        # Drag-and-drop
        self.setAcceptDrops(True)

    def _build_top_bar(self) -> QWidget:
        w = QFrame()
        w.setObjectName("TopBar")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(12)

        brand = QLabel(self.settings.APP_NAME)
        brand.setObjectName("Brand")
        version = QLabel(f"v{self.settings.VERSION}")
        version.setObjectName("VersionChip")

        # URL pill
        pillw = QFrame()
        pillw.setObjectName("UrlPillWrap")
        pill = QHBoxLayout(pillw)
        pill.setContentsMargins(10, 2, 6, 2)
        pill.setSpacing(6)
        self.url_input = QLineEdit(placeholderText="Paste a URL and press Enter")
        self.url_input.setClearButtonEnabled(False)
        self.btn_add_inline = QPushButton("Add")
        self.btn_add_inline.setObjectName("PillBtn")
        self.btn_add_inline.setCursor(Qt.PointingHandCursor)
        btn_paste = QPushButton("Paste")
        btn_paste.setObjectName("PillBtn")
        btn_paste.setCursor(Qt.PointingHandCursor)
        btn_clear = QPushButton("✕")
        btn_clear.setObjectName("PillIconBtn")
        btn_clear.setCursor(Qt.PointingHandCursor)
        pill.addWidget(self.url_input, 1)
        pill.addWidget(self.btn_add_inline)
        pill.addWidget(btn_paste)
        pill.addWidget(btn_clear)

        # Quick chips
        self.format_box = QComboBox()
        self.format_box.setObjectName("ChipCombo")
        for k in self.settings.RESOLUTIONS.keys():
            self.format_box.addItem(k)

        self.btn_advanced = QPushButton("Advanced")
        self.btn_advanced.setObjectName("Chip")
        self.btn_advanced.setCursor(Qt.PointingHandCursor)
        btn_settings = QPushButton("Settings")
        btn_settings.setObjectName("Chip")
        btn_settings.setCursor(Qt.PointingHandCursor)

        # Help uses app icon
        btn_help = QPushButton()
        btn_help.setObjectName("ChipGhost")
        btn_help.setCursor(Qt.PointingHandCursor)
        btn_help.setToolTip("Help")
        if self._app_icon:
            btn_help.setIcon(self._app_icon)
        else:
            btn_help.setText("Help")

        lay.addWidget(brand)
        lay.addWidget(version)
        lay.addWidget(pillw, 1)
        lay.addWidget(self.format_box)
        lay.addWidget(self.btn_advanced)
        lay.addWidget(btn_settings)
        lay.addWidget(btn_help)

        # Wire helpers
        btn_paste.clicked.connect(self._paste_into_url)
        btn_clear.clicked.connect(self.url_input.clear)
        btn_settings.clicked.connect(self._show_preferences)
        btn_help.clicked.connect(self._show_about)

        # Start with Add disabled until URL looks valid
        self.btn_add_inline.setEnabled(False)

        return w

    def _build_queue_pane(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Header row
        header = QFrame()
        header.setObjectName("QueueHeader")
        h = QHBoxLayout(header)
        h.setContentsMargins(10, 8, 10, 8)
        h.setSpacing(8)

        self.queue_title = QLabel("Queue")
        self.queue_title.setObjectName("QueueTitle")
        self.count_chip = QLabel("0")
        self.count_chip.setObjectName("CountChip")

        self.search_box = QLineEdit()
        self.search_box.setObjectName("Search")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setPlaceholderText("Search queue…")
        self.search_box.setMinimumWidth(320)

        self.sort_combo = QComboBox()
        self.sort_combo.setObjectName("SortCombo")
        self.sort_combo.addItems(["Added", "Title", "Status"])

        h.addWidget(self.queue_title)
        h.addWidget(self.count_chip)
        h.addStretch(1)
        h.addWidget(self.search_box, 2)
        h.addWidget(self.sort_combo, 0)
        layout.addWidget(header)

        # Empty state
        self.queue_empty_state = QLabel("Add links to build your queue.\nDrag to reorder.")
        self.queue_empty_state.setObjectName("EmptyState")
        self.queue_empty_state.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.queue_empty_state)

        # List
        self.queue_list = QListWidget()
        self.queue_list.setObjectName("QueueList")
        self.queue_list.setSpacing(8)
        self.queue_list.setFrameShape(QFrame.NoFrame)
        self.queue_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.queue_list.setUniformItemSizes(False)
        # Native drag reorder
        self.queue_list.setDragEnabled(True)
        self.queue_list.setAcceptDrops(True)
        self.queue_list.setDragDropMode(QListWidget.InternalMove)
        self.queue_list.setDefaultDropAction(Qt.MoveAction)

        layout.addWidget(self.queue_list, 1)

        # Bulk bar (appears when items selected)
        self.bulk_bar = QFrame()
        self.bulk_bar.setObjectName("BulkBar")
        self.bulk_bar.setVisible(False)
        bh = QHBoxLayout(self.bulk_bar)
        bh.setContentsMargins(10, 6, 10, 6)
        bh.setSpacing(8)
        self.bulk_label = QLabel("0 selected")
        btn_rm = QPushButton("Remove")
        btn_top = QPushButton("Move to top")
        btn_bot = QPushButton("Move to bottom")
        btn_clear_done = QPushButton("Clear completed")
        for b in (btn_rm, btn_top, btn_bot, btn_clear_done):
            b.setObjectName("Ghost")
            b.setCursor(Qt.PointingHandCursor)
        bh.addWidget(self.bulk_label)
        bh.addStretch(1)
        bh.addWidget(btn_rm)
        bh.addWidget(btn_top)
        bh.addWidget(btn_bot)
        bh.addWidget(btn_clear_done)
        layout.addWidget(self.bulk_bar)

        # Connections
        self.queue_list.model().rowsMoved.connect(self._on_rows_moved)
        self.queue_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.search_box.textChanged.connect(self._apply_queue_filter)
        self.sort_combo.currentTextChanged.connect(self._apply_queue_sort)

        btn_rm.clicked.connect(self._bulk_remove_selected)
        btn_top.clicked.connect(lambda: self._bulk_move_selected(top=True))
        btn_bot.clicked.connect(lambda: self._bulk_move_selected(bottom=True))
        btn_clear_done.clicked.connect(self._bulk_clear_completed)

        return container

    def _build_console_pane(self) -> QWidget:
        w = QFrame()
        w.setObjectName("Pane")
        v = QVBoxLayout(w)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)

        title = QLabel("Console")
        title.setObjectName("PaneTitle")
        v.addWidget(title)

        tools_row = QHBoxLayout()
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Info", "Warning", "Error"])
        btn_copy = QPushButton("Copy all")
        btn_copy.setObjectName("Ghost")
        btn_clear = QPushButton("Clear")
        btn_clear.setObjectName("Ghost")
        tools_row.addWidget(self.filter_combo)
        tools_row.addStretch(1)
        tools_row.addWidget(btn_copy)
        tools_row.addWidget(btn_clear)
        roww = QWidget()
        roww.setLayout(tools_row)
        v.addWidget(roww)

        self.log_output = QTextEdit(readOnly=True)
        self.log_output.setObjectName("Console")
        # Explicitly enforce dark console
        self.log_output.setStyleSheet("background:#10141C; color:#E6EAF2; border:1px solid #263042; border-radius:10px;")
        v.addWidget(self.log_output, 1)

        btn_copy.clicked.connect(self._copy_console)
        btn_clear.clicked.connect(self._clear_console)

        # Filter changes re-render the log
        self.filter_combo.currentTextChanged.connect(self._render_log)

        return w

    def _build_bottom_bar(self) -> QWidget:
        w = QFrame()
        w.setObjectName("BottomBar")
        h = QHBoxLayout(w)
        h.setContentsMargins(16, 10, 16, 10)
        h.setSpacing(12)

        self.btn_start_queue = QPushButton("Start")
        self.btn_start_queue.setObjectName("Primary")
        self.btn_start_queue.setCursor(Qt.PointingHandCursor)

        self.btn_pause_queue = QPushButton("Pause")
        self.btn_pause_queue.setObjectName("Secondary")
        self.btn_pause_queue.setCursor(Qt.PointingHandCursor)
        self.btn_pause_queue.setEnabled(False)

        self.btn_skip = QPushButton("Skip")
        self.btn_skip.setObjectName("Ghost")
        self.btn_skip.setCursor(Qt.PointingHandCursor)
        self.btn_skip.setEnabled(False)

        left = QHBoxLayout()
        left.addWidget(self.btn_start_queue)
        left.addWidget(self.btn_pause_queue)
        left.addWidget(self.btn_skip)

        self.global_progress = QProgressBar()
        self.global_progress.setObjectName("Progress")
        self.global_progress.setTextVisible(False)
        self.global_progress.setMaximumHeight(6)
        # Determinate by default
        self.global_progress.setRange(0, 100)
        self.global_progress.setValue(0)

        # Right side: post-action + path
        right = QHBoxLayout()
        right.addWidget(QLabel("After:"))
        self.post_action = QComboBox()
        self.post_action.setObjectName("ChipCombo")
        self.post_action.addItems(["Keep", "Shutdown", "Sleep", "Restart", "Close"])
        self.post_action.setCurrentText(self.post_queue_action)
        self.download_path_btn = QPushButton(str(self.settings.DOWNLOADS_DIR))
        self.download_path_btn.setObjectName("Ghost")
        self.download_path_btn.setCursor(Qt.PointingHandCursor)

        right.addWidget(self.post_action)
        right.addWidget(self.download_path_btn)

        h.addLayout(left)
        h.addStretch(1)
        h.addWidget(self.global_progress, 1)
        h.addLayout(right)

        self.post_action.currentTextChanged.connect(self._set_post_queue_action)
        self.download_path_btn.clicked.connect(lambda: webbrowser.open(self.settings.DOWNLOADS_DIR.as_uri()))

        return w

    def _setup_connections(self):
        self.url_input.textChanged.connect(self._on_url_text_changed)
        self.url_input.returnPressed.connect(self._add_to_queue)
        self.btn_add_inline.clicked.connect(self._add_to_queue)
        self.btn_start_queue.clicked.connect(self._start_queue)
        self.btn_pause_queue.clicked.connect(self._pause_queue)
        self.btn_advanced.clicked.connect(self._show_advanced_options)
        self.btn_skip.clicked.connect(self._skip_current)

    def _setup_menu(self):
        menubar: QMenuBar = self.menuBar()
        menubar.setStyleSheet(
            "QMenuBar { background-color: #1C2230; color: #E6EAF2; } "
            "QMenu::item:selected { background-color: #2A3550; }"
        )

        # File
        m_file = menubar.addMenu("File")
        m_file.addAction("Save Queue As...", self._save_queue_to_disk, "Ctrl+S")
        m_file.addAction("Load Queue...", self._load_queue_from_disk, "Ctrl+O")
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
            "Keep Running": "Keep",
            "Shutdown PC": "Shutdown",
            "Sleep PC": "Sleep",
            "Restart PC": "Restart",
            "Close YTGet": "Close",
        }
        self.post_actions_map = {}
        for text, value in actions.items():
            act = QAction(text, self, checkable=True)
            if value == self.post_queue_action:
                act.setChecked(True)
            act.triggered.connect(lambda checked, v=value: self._set_post_queue_action(v))
            action_group.addAction(act)
            post_menu.addAction(act)
            self.post_actions_map[value] = act

        # Help
        m_help = menubar.addMenu("Help")
        m_help.addAction("Check YTGet Update", lambda: self.request_check_ytget_gui.emit())
        m_help.addAction("Check yt-dlp Update", lambda: self.request_check_ytdlp.emit())
        m_help.addAction("Open Download Folder", lambda: webbrowser.open(self.settings.DOWNLOADS_DIR.as_uri()))
        m_help.addAction("About", self._show_about)

    def _setup_title_fetch_queue(self):
        # Create a single worker thread that serializes title fetches
        self.title_queue_thread = QThread(self)
        self.title_queue = TitleFetchQueue(self.settings)
        self.title_queue.moveToThread(self.title_queue_thread)

        # Inputs into worker (queued)
        self.enqueue_title.connect(self.title_queue.enqueue, Qt.QueuedConnection)
        self.enqueue_titles.connect(self.title_queue.enqueue_many, Qt.QueuedConnection)

        # Results to UI (run in GUI thread)
        self.title_queue.metadata_fetched.connect(self._on_metadata_fetched, Qt.QueuedConnection)
        self.title_queue.error.connect(self._on_title_error)
        self.title_queue.started_one.connect(self._on_title_started)

        self.title_queue_thread.start()

    def _thumb_safe_name(self, base_name: str) -> str:
        """Match thumb_fetcher._safe_name behavior for cache lookup."""
        s = (base_name or "").strip()
        if not s:
            return "unknown"
        s = re.sub(r"[^A-Za-z0-9._-]", "_", s)
        if len(s) > 120:
            h = hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]
            s = s[:100] + "_" + h
        return s

    @Slot(str)
    def _on_thumb_started(self, url: str):
        # Minimal UI reaction; reserved for future UI polish
        pass

    @Slot(str, str)
    def _on_thumb_finished(self, url: str, path: str):
        """
        Called when ThumbManager finishes fetching a thumbnail.
        `path` is empty string on failure.
        """
        try:
            # Remove from pending set
            try:
                if url in self._pending_thumb_urls:
                    self._pending_thumb_urls.discard(url)
            except Exception:
                pass

            # Find matching QueueCard widgets and set thumbnail
            for i in range(self.queue_list.count()):
                item = self.queue_list.item(i)
                widget = self.queue_list.itemWidget(item)
                if not widget:
                    continue
                # Prefer widget.url if set; fallback to widget._full_meta_text
                w_url = getattr(widget, "url", None) or getattr(widget, "_full_meta_text", None)
                if not w_url:
                    continue
                if w_url == url:
                    if path:
                        try:
                            widget.set_thumbnail_path(path)
                        except Exception:
                            pass
                    else:
                        # optional: set placeholder or leave as-is
                        pass
        except Exception:
            pass

    @Slot(str, str)
    def _on_thumb_error(self, url: str, message: str):
        try:
            if getattr(self.settings, "LOG_THUMBNAILS", False):
                self.log(f"Thumbnail error for {short(url, 80)}: {message}", AppStyles.WARNING_COLOR, "Warning")
        except Exception:
            pass

    def _add_queue_card_to_list(self, url: str, title: str = "", video_id: Optional[str] = None, show_thumbnail: bool = True):
        """
        Create a QueueCard, add it to the QListWidget, and set thumbnail from cache or enqueue fetch.
        """
        try:
            # Create card
            card = QueueCard(title=title or short(url, 80), url=url, status="Pending", progress=0, show_thumbnail=show_thumbnail)
            # store url on widget for lookup
            try:
                setattr(card, "url", url)
            except Exception:
                pass

            # Set up context menu
            def _open_in_browser():
                webbrowser.open(url)
        
            def _copy_url():
                QGuiApplication.clipboard().setText(url)
        
            def _remove_item():
                # Find the item by URL and remove it
                for item in self.queue:
                    if item.get("url") == url:
                        self._remove_item_by_id(item)
                        break
        
            card.set_context_actions([
                ("Open in browser", _open_in_browser),
                ("Copy URL", _copy_url),
                ("Remove", _remove_item),
            ])

            # Create list item and attach widget
            item = QListWidgetItem()
            item.setSizeHint(card.sizeHint())
            self.queue_list.addItem(item)
            self.queue_list.setItemWidget(item, card)

            # Compute safe base name
            base_name = video_id or hashlib.sha1(url.encode("utf-8")).hexdigest()
            safe = self._thumb_safe_name(base_name)

            # Look for cached thumbnail
            found_path = None
            for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"):
                p = self.thumb_cache_dir / f"{safe}{ext}"
                try:
                    if p.exists() and p.stat().st_size > 0:
                        found_path = str(p)
                        break
                except Exception:
                    continue

            if found_path:
                try:
                    card.set_thumbnail_path(found_path)
                except Exception:
                    pass
            else:
                # Enqueue fetch if not already pending
                if url not in self._pending_thumb_urls:
                    try:
                        self._pending_thumb_urls.add(url)
                        self.thumb_manager.enqueue(url)
                    except Exception:
                        try:
                            self._pending_thumb_urls.discard(url)
                        except Exception:
                            pass
        except Exception:
            pass

    @Slot(str, str, str, str, bool)
    def _on_metadata_fetched(self, url: str, title: str, video_id: str, thumb_url: str, is_playlist: bool):
        """
        Called from the TitleFetchQueue worker thread (signal marshalled to GUI thread).
        Ensure a QueueCard exists for this URL, persist metadata, and only then start thumbnail fetch.
        """
        try:
            key = url or ""
        except Exception:
            key = url or ""

        # Find existing list item for this URL (if added earlier)
        list_item = None
        try:
            for i in range(self.queue_list.count()):
                it = self.queue_list.item(i)
                data = it.data(Qt.UserRole)
                if data and isinstance(data, dict) and data.get("url") == key:
                    list_item = it
                    break
        except Exception:
            list_item = None
        
        # Get the readable label (e.g. "YouTube 1080p")
        current_label = self.format_box.currentText()
        # Translate it to the yt-dlp format string using settings (default to 'best' if not found)
        chosen_format = self.settings.RESOLUTIONS.get(current_label, "best")
        # --------------------------------------------------

        # If no list item exists, create one and append to queue_list and in-memory queue
        if list_item is None:
            try:
                qitem = {
                    "url": key,
                    "title": title,
                    "video_id": video_id,
                    "thumbnail_url": thumb_url,
                    # --- FIX: Save the format code here ---
                    "format_code": chosen_format, 
                    "status": "Pending",
                    "progress": 0,
                    "thumb_path": "",
                    "is_playlist": bool(is_playlist),
                }
                self.queue.append(qitem)

                # Use new helper method to add card
                self._add_queue_card_to_list(url=key, title=title, video_id=video_id, show_thumbnail=True)

                try:
                    self.count_chip.setText(str(self.queue_list.count()))
                    self.queue_empty_state.setVisible(self.queue_list.count() == 0)
                except Exception:
                    pass

                # Keep the user-facing confirmation that an item was added
                self.log(f"✅ Added to queue: {short(title, 60)}", AppStyles.INFO_COLOR, "Info")
                try:
                    self._save_queue_permanent()
                except Exception:
                    pass
            except Exception as e:
                # Surface only a warning if card creation fails
                self.log(f"Failed to create queue card for {key}: {e}", AppStyles.WARNING_COLOR, "Warning")
                return

        # Update stored metadata on the list item and in-memory queue
        try:
            data = list_item.data(Qt.UserRole) or {}
            if isinstance(data, dict):
                data.update({"title": title, "video_id": video_id, "thumbnail_url": thumb_url})
                list_item.setData(Qt.UserRole, data)
                
                for q in self.queue:
                    if q.get("url") == key:
                        q.update({"title": title, "video_id": video_id, "thumbnail_url": thumb_url})
                        break
        except Exception:
            pass

        # Refresh UI and state (preserve original behavior)
        try:
            self._refresh_queue_list()
        except Exception:
            pass
        try:
            self._update_button_states()
        except Exception:
            pass
        try:
            self._update_global_progress_bar()
        except Exception:
            pass

    # ---------- Startup / Logging with filter ----------

    def _log_startup(self):
        self.log("💡 Welcome to YTGet! Paste a URL to Begin.\n", AppStyles.INFO_COLOR, "Info")
        self.log(f"📂 Download Folder: {self.settings.DOWNLOADS_DIR}\n", AppStyles.INFO_COLOR, "Info")
        self.log(f"🔧 Using binaries from: {self.settings.FFMPEG_PATH.parent}\n", AppStyles.INFO_COLOR, "Info")       
	    
        if not self.settings.YT_DLP_PATH.exists():
            self.log("⚠️ yt-dlp not found in app folder or PATH. Download it via Menu Bar → Help → Check yt-dlp Update.\n", AppStyles.WARNING_COLOR, "Warning")
        if not self.settings.FFMPEG_PATH.exists() or not self.settings.FFPROBE_PATH.exists():
            self.log("⚠️ ffmpeg/ffprobe not found in app folder or PATH. Download and place it in the _internal directory or install it system-wide.\n", AppStyles.WARNING_COLOR, "Warning")
        if hasattr(self.settings, "PHANTOMJS_PATH") and self.settings.PHANTOMJS_PATH.exists():
            self.log(f"🔧 PhantomJS available: {self.settings.PHANTOMJS_PATH}\n", AppStyles.INFO_COLOR, "Info")
        else:
            self.log("⚠️ PhantomJS not found in app folder or PATH. If a site requires it, place PhantomJS in the app folder.\n", AppStyles.WARNING_COLOR, "Warning")
            
        # Deno availability
        try:
            deno_attr = getattr(self.settings, "DENO_PATH", None)
            if deno_attr:
                deno_path = Path(deno_attr)
                if deno_path.exists():
                    self.log(f"🔧 Deno available: {deno_path}\n", AppStyles.INFO_COLOR, "Info")
                else:
                    self.log(
                        "⚠️ Deno not found at configured path. Install Deno: https://docs.deno.com/runtime/getting_started/installation/ "
                        "or set the YTGET_DENO_PATH environment variable to the full path to the deno binary.\n",
                        AppStyles.WARNING_COLOR,
                        "Warning",
                    )
            else:
                # Try bundled candidate beside BASE_DIR (deno.exe on Windows)
                bundled = Path(self.settings.BASE_DIR) / ("deno.exe" if os.name == "nt" else "deno")
                if bundled.exists():
                    self.log(f"🔧 Deno available (bundled): {bundled}\n", AppStyles.INFO_COLOR, "Info")
                else:
                    # Not found on bundled path; try to detect via settings resolution (best-effort)
                    # If AppSettings.load_config / __post_init__ sets DENO_PATH, it would have been used above.
                    self.log(
                        "⚠️ Deno not found in app folder or PATH. Some sites may require a JS runtime. "
                        "Install Deno: https://docs.deno.com/runtime/getting_started/installation/ or set YTGET_DENO_PATH.\n",
                        AppStyles.WARNING_COLOR,
                        "Warning",
                    )
        except Exception:
            # best-effort only; do not interrupt startup
            pass            
		
        if self.settings.PROXY_URL:
            self.log(f"🌐 Proxy: {self.settings.PROXY_URL}\n", AppStyles.INFO_COLOR, "Info")
        if self.settings.SPONSORBLOCK_CATEGORIES:
            self.log(f"⏩ SponsorBlock: {', '.join(self.settings.SPONSORBLOCK_CATEGORIES)}\n", AppStyles.INFO_COLOR, "Info")
        if self.settings.CHAPTERS_MODE != "none":
            self.log(f"📖 Chapters: {self.settings.CHAPTERS_MODE}\n", AppStyles.INFO_COLOR, "Info")
        if self.settings.WRITE_SUBS:
            self.log(f"📝 Subtitles: {self.settings.SUB_LANGS}\n", AppStyles.INFO_COLOR, "Info")
        if self.settings.ENABLE_ARCHIVE:
            self.log(f"📚 Archive: {self.settings.ARCHIVE_PATH}\n", AppStyles.INFO_COLOR, "Info")
        if self.settings.PLAYLIST_REVERSE:
            self.log("↩️ Playlist Reverse: On\n", AppStyles.INFO_COLOR, "Info")
        if self.settings.AUDIO_NORMALIZE:
            self.log("🔊 Audio Normalize: On\n", AppStyles.INFO_COLOR, "Info")
        if self.settings.LIMIT_RATE:
            self.log(f"📉 Rate Limit: {self.settings.LIMIT_RATE}\n", AppStyles.INFO_COLOR, "Info")
        if self.settings.ORGANIZE_BY_UPLOADER:
            self.log("🗂️ Organize by Uploader: On\n", AppStyles.INFO_COLOR, "Info")
        if self.settings.DATEAFTER:
            self.log(f"📅 Only After: {self.settings.DATEAFTER}\n", AppStyles.INFO_COLOR, "Info")
        if self.settings.LIVE_FROM_START:
            self.log("🔴 Live from Start: On\n", AppStyles.INFO_COLOR, "Info")
        if self.settings.YT_MUSIC_METADATA:
            self.log("🎵 Enhanced YouTube Music Metadata: On\n", AppStyles.INFO_COLOR, "Info")
        if self.settings.CROP_AUDIO_COVERS:
            self.log("🖼️ Will Crop Audio Covers to 1:1 After Queue.\n", AppStyles.INFO_COLOR, "Info")
        if self.settings.CLIP_START and self.settings.CLIP_END:
            self.log(f"⏱️ Clip: {self.settings.CLIP_START}-{self.settings.CLIP_END}\n", AppStyles.INFO_COLOR, "Info")

    def _copy_console(self):
        QGuiApplication.clipboard().setText(self.log_output.toPlainText())

    def _clear_console(self):
        self._log_entries.clear()
        self._render_log()

    def _paste_into_url(self):
        text = QGuiApplication.clipboard().text()
        if text:
            self.url_input.setText(text)
            self.url_input.setCursorPosition(len(text))

    # ---------- Drag and drop ----------

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            text = ""
            if event.mimeData().hasUrls():
                urls = [u.toString() for u in event.mimeData().urls()]
                text = " ".join(urls)
            else:
                text = event.mimeData().text()
            tokens = text.split()
            if any(is_supported_url(t) for t in tokens):
                event.acceptProposedAction()
                self.queue_pane.setProperty("dropActive", True)
                self.queue_pane.style().unpolish(self.queue_pane)
                self.queue_pane.style().polish(self.queue_pane)
                return              
        super().dragEnterEvent(event)

    def dragLeaveEvent(self, event):
        self.queue_pane.setProperty("dropActive", False)
        self.queue_pane.style().unpolish(self.queue_pane)
        self.queue_pane.style().polish(self.queue_pane)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.queue_pane.setProperty("dropActive", False)
        self.queue_pane.style().unpolish(self.queue_pane)
        self.queue_pane.style().polish(self.queue_pane)

        urls: List[str] = []
        if event.mimeData().hasUrls():
            urls = [u.toString() for u in event.mimeData().urls()]
        elif event.mimeData().hasText():
            urls = [t for t in event.mimeData().text().split()]

        valid = [u for u in urls if is_supported_url(u)]
        if valid:
            for u in valid:
                self.log(f"🧾 Queued for fetch: {u[:60]}...\n", AppStyles.INFO_COLOR, "Info")
            if self.title_queue:
                self.enqueue_titles.emit(valid)  # queued call
            event.acceptProposedAction()
        else:
            self.log("⚠️ No valid YouTube URLs detected in drop.\n", AppStyles.WARNING_COLOR, "Warning")
            event.ignore()

    # ---------- Queue / Title / Thumbnails ----------

    def _on_url_text_changed(self, text: str):
        self.btn_add_inline.setEnabled(is_supported_url(text))

    def _add_to_queue(self):
        url = self.url_input.text().strip()
        if not is_supported_url(url):
            self.log("⚠️ Invalid or unsupported URL format.\n", AppStyles.WARNING_COLOR, "Warning")
            return

        # Prevent duplicates already in download queue
        if any(it.get("url") == url for it in self.queue):
            self.log("ℹ️ Already in queue.\n", AppStyles.INFO_COLOR, "Info")
            self.url_input.clear()
            self.btn_add_inline.setEnabled(False)
            return

        self.url_input.clear()
        self.btn_add_inline.setEnabled(False)
        
        # Add card immediately with placeholder title
        self._add_queue_card_to_list(url=url, title=short(url, 80), show_thumbnail=True)
        
        # Enqueue title fetch
        if self.title_queue:
            self.enqueue_title.emit(url)

    @Slot(str)
    def _on_title_started(self, url: str):
        self.log(f"🔎 Fetching title for: {url[:60]}...\n", AppStyles.INFO_COLOR, "Info")
        
    def _on_title_fetched(self, url: str, title: str):
        # Legacy path (no id/thumbnail)
        fmt_text = self.format_box.currentText()
        item = {
            "url": url,
            "title": title,
            "format_code": self.settings.RESOLUTIONS[fmt_text],
            "status": "Pending",
            "progress": 0,
            "video_id": "",
            "thumbnail_url": "",
            "thumb_path": "",
            "is_playlist": False,
        }
        self.queue.append(item)
        self._save_queue_permanent()
        self.log(f"✅ Added to queue: {short(title)}\n", AppStyles.SUCCESS_COLOR, "Info")

        self._refresh_queue_list()
        self._update_button_states()
        self._update_global_progress_bar()

    def _on_title_error(self, url: str, msg: str):
        self.log(f"Error fetching title for {url[:60]}: {msg}\n", AppStyles.ERROR_COLOR, "Error")
        self.btn_add_inline.setEnabled(True)

    def _thumb_path_for_item(self, it: Dict[str, Any]) -> Path:
        """
        Return a conservative expected cache path for quick existence checks.
        The ThumbFetcher may write different extensions; this function is used
        only to detect an existing cached file quickly (prefers .jpg).
        """
        vid = (it or {}).get("video_id") or ""
        if not vid:
            # fallback name derived from URL to still benefit from cache
            key = (it.get("url", "").split("v=")[-1].split("&")[0]) or ""
            if not key:
                # hashed fallback
                import hashlib
                key = hashlib.sha1(it.get("url", "").encode("utf-8")).hexdigest()
            return self.thumb_cache_dir / f"{key}.jpg"
        return self.thumb_cache_dir / f"{vid}.jpg"

    # ---------- Queue control ----------

    def _start_queue(self):
        if self.is_downloading and not self.queue_paused:
            self.log("ℹ️ Queue is already running.\n", AppStyles.INFO_COLOR, "Info")
            return
        if not self.queue:
            self.log("⚠️ Queue is empty. Add items to start.\n", AppStyles.WARNING_COLOR, "Warning")
            return

        self.queue_paused = False
        if not self.is_downloading:
            self._initial_queue_len = len(self.queue)
        self.log(("▶️ Resuming" if self.is_downloading else "▶️ Starting") + " queue processing...\n", AppStyles.SUCCESS_COLOR, "Info")
        # Mark first item as downloading (and persist)
        if self.queue and (self.current_download_item is None):
            self.queue[0]["status"] = "Downloading"
            self._save_queue_permanent()
        self._update_global_progress_bar()
        self._download_next()
        self._update_button_states()

    def _pause_queue(self):
        if not self.is_downloading:
            self.log("ℹ️ Queue is not running.\n", AppStyles.INFO_COLOR, "Info")
            return
        self.queue_paused = True
        if self.download_worker:
            self.download_worker.cancel()
        self._update_button_states()

    def _skip_current(self):
        if self.is_downloading and self.download_worker:
            self.log("⏭️ Skipping current item...\n", AppStyles.INFO_COLOR, "Info")
            self.download_worker.cancel()

    def _download_next(self):
        if self.queue_paused or self.is_downloading or not self.queue:
            if not self.queue and not self.is_downloading:
                self._on_queue_finished()
            return

        self.is_downloading = True
        self.current_download_item = self.queue[0]
        self.current_download_item["status"] = "Downloading"
        self.current_download_item["progress"] = 0
        self._save_queue_permanent()
        self._refresh_queue_list()
        self._update_button_states()

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

        # Logs and errors
        self.download_worker.log.connect(self.log, Qt.QueuedConnection)
        self.download_worker.error.connect(lambda m: self.log(f"❌ {m}\n", AppStyles.ERROR_COLOR, "Error"))

        if hasattr(self.download_worker, "status"):
            try:
                self.download_worker.status.connect(self._on_download_status)
            except Exception:
                pass

        # Finish
        self.download_worker.finished.connect(self._on_download_finished)
        self.download_worker.finished.connect(self.download_thread.quit)
        self.download_thread.finished.connect(self.download_worker.deleteLater)
        self.download_thread.finished.connect(self.download_thread.deleteLater)
        self.download_thread.start()

    def _on_download_status(self, status: str):
        if self.current_download_item is None:
            return
        self.current_download_item["status"] = status
        self._save_queue_permanent()
        if self.queue_list.count() > 0:
            w = self.queue_list.itemWidget(self.queue_list.item(0))
            if isinstance(w, QueueCard):
                w.set_status(status)

    def _on_download_finished(self, exit_code: int):
        self.is_downloading = False
        if self.current_download_item is not None:
            self.current_download_item["status"] = "Completed" if exit_code == 0 else "Error"
            self.current_download_item["progress"] = 100 if exit_code == 0 else 0
            self._save_queue_permanent()
        if exit_code == 0 and self.queue:
            self.queue.pop(0)
            self._save_queue_permanent()
        self.current_download_item = None

        self._refresh_queue_list()
        self._update_button_states()
        self._update_global_progress_bar()

        if not self.queue_paused and self.queue:
            self._download_next()
        elif not self.queue:
            self._on_queue_finished()

    def _update_global_progress_bar(self):
        # Determinate, based on items completed
        total = max(1, self._initial_queue_len if self._initial_queue_len else len(self.queue))
        done = (self._initial_queue_len - len(self.queue)) if self._initial_queue_len else 0
        percent = int((done / total) * 100) if total else 0
        self.global_progress.setRange(0, 100)
        self.global_progress.setValue(percent)

    def _on_queue_finished(self):
        # Notify that the queue is complete
        self.log(
            f"🏁 Queue complete! Action: {self.post_queue_action}.\n",
            AppStyles.SUCCESS_COLOR,
            "Info"
        )
        self._initial_queue_len = 0
        self._update_global_progress_bar()

        # If we need to crop audio covers, do so asynchronously
        if getattr(self.settings, "CROP_AUDIO_COVERS", False):
            self.log(
                "🖼️ Cropping audio covers to 1:1. This may take a moment...\n",
                AppStyles.INFO_COLOR,
                "Info"
            )

            # If a previous cover thread is running, stop it first
            try:
                if self.cover_thread and self.cover_thread.isRunning():
                    self.cover_thread.quit()
                    self.cover_thread.wait()
            except RuntimeError:
                pass

            # Set up a new thread + worker for cover cropping
            self.cover_thread = QThread()
            self.cover_worker = CoverCropWorker(self.settings.DOWNLOADS_DIR)
            self.cover_worker.moveToThread(self.cover_thread)

            # When the thread starts, run the worker
            self.cover_thread.started.connect(self.cover_worker.run)

            # Marshal logs onto the GUI thread
            self.cover_worker.log.connect(self.log, Qt.QueuedConnection)

            # Quit thread when done
            self.cover_worker.finished.connect(self.cover_thread.quit)

            # Instead of calling the action directly (wrong thread), emit our queued signal
            self.cover_worker.finished.connect(
                lambda action=self.post_queue_action: self.post_queue_action_signal.emit(action),
                Qt.QueuedConnection
            )

            # Clean up when thread finishes
            self.cover_thread.finished.connect(self.cover_worker.deleteLater)
            self.cover_thread.finished.connect(self.cover_thread.deleteLater)

            # Start cropping
            self.cover_thread.start()

        else:
            # No cropping needed—emit signal so the action runs on the GUI thread
            self.post_queue_action_signal.emit(self.post_queue_action)
           
    def _perform_post_queue_action(self, action: str):
        """
        Cross-platform implementations for Keep | Shutdown | Sleep | Restart | Close.
        - "Keep": do nothing
        - "Close": quit the app
        - All other actions are dispatched via subprocess.run()
        """
        # 1) Silent no-op
        if action == "Keep":
            return

        # 2) Close the window immediately
        if action == "Close":
            self.close()
            return

        # 3) Normalize platform key
        sysname = platform.system().lower()
        if sysname.startswith("win"):
            plat = "win"
        elif sysname == "darwin":
            plat = "mac"
        else:
            plat = "linux"

        # 4) Define action → command mapping
        ACTION_COMMANDS: dict[str, dict[str, list[str]]] = {
            "Shutdown": {
                "win": ["shutdown", "/s", "/t", "60"],
                "mac": [
                    "osascript", "-e",
                    'tell app "System Events" to shut down'
                ],
                "linux": [
                    which("systemctl") or "shutdown",
                    which("systemctl") and "poweroff" or "now"
                ],
            },
            "Sleep": {
                "win": [
                    "powershell", "-Command",
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    "[System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)"
                ],
                "mac": ["pmset", "sleepnow"],
                "linux": [
                    which("systemctl") or "pm-suspend",
                    which("systemctl") and "suspend" or ""
                ],
            },
            "Restart": {
                "win": ["shutdown", "/r", "/t", "60"],
                "mac": [
                    "osascript", "-e",
                    'tell app "System Events" to restart'
                ],
                "linux": [
                    which("systemctl") or "shutdown",
                    which("systemctl") and "reboot" or "now"
                ],
            },
        }

        # 5) Lookup and run
        cmds_for_action = ACTION_COMMANDS.get(action)
        if not cmds_for_action:
            self.log(
                f"⚠️ Unknown post-queue action: {action}\n",
                AppStyles.WARNING_COLOR, "Warning"
            )
            return

        cmd = cmds_for_action.get(plat)
        if not cmd or not cmd[0]:
            self.log(
                f"⚠️ Cannot perform '{action}' on this platform ({sysname}).\n",
                AppStyles.WARNING_COLOR, "Warning"
            )
            return

        try:
            # Some commands (esp. on Linux fallbacks) are single-item strings
            # so ensure we pass a list to subprocess.run
            subprocess.run(cmd if isinstance(cmd, list) else [cmd], check=False)
        except Exception as exc:
            self.log(
                f"❌ Failed to {action.lower()}: {exc}\n",
                AppStyles.ERROR_COLOR, "Error"
            )

    # ---------- Queue pane helpers (sort, filter, drag-reorder, bulk) ----------

    def _on_rows_moved(self, src_parent, src_start, src_end, dst_parent, dst_row):
        # Keep self.queue in sync with visual reorder (single-row move)
        if src_end != src_start:
            return
        if not (0 <= src_start < len(self.queue)):
            return
        item = self.queue.pop(src_start)
        insert_at = dst_row if dst_row <= len(self.queue) else len(self.queue)
        self.queue.insert(insert_at, item)
        self._save_queue_permanent()
        self._update_button_states()

    def _on_selection_changed(self):
        count = len(self.queue_list.selectedIndexes())
        self.bulk_bar.setVisible(count > 0)
        self.bulk_label.setText(f"{count} selected")

    def _apply_queue_sort(self, key: str):
        if not self.queue:
            return
        if key == "Title":
            self.queue.sort(key=lambda x: x.get("title", "").lower())
        elif key == "Status":
            order = {"Downloading": 0, "Pending": 1, "Queued": 2, "Completed": 3, "Error": 4}
            self.queue.sort(key=lambda x: order.get(x.get("status", "Pending"), 99))
        else:
            # "Added" keeps current order
            pass
        self._save_queue_permanent()
        self._refresh_queue_list()

    def _apply_queue_filter(self, text: str):
        t = (text or "").strip().lower()
        for i in range(self.queue_list.count()):
            lw_item = self.queue_list.item(i)
            data = lw_item.data(Qt.UserRole) or {}
            title = str(data.get("title", "")).lower()
            meta = f"{data.get('status','')}".lower()
            visible = True
            if t:
                visible = (t in title) or (t in meta)
            lw_item.setHidden(not visible)

    def _refresh_queue_list(self):
        self.queue_list.clear()

        # Update header chip and empty state
        count = len(self.queue)
        self.count_chip.setText(str(count))
        self.queue_empty_state.setVisible(count == 0)

        for it in self.queue:
            # Use helper method to add card with context menu
            self._add_queue_card_to_list(
                url=it.get("url", ""),
                title=it.get("title", "(title pending)"),
                video_id=it.get("video_id"),
                show_thumbnail=True
            )
    
        # Apply current filter after rebuilding the list
        self._apply_queue_filter(self.search_box.text())

    def _make_queue_card_widget(self, item: Dict[str, Any]) -> QWidget:
        # Prefer external QueueCard with correct signature
        try:
            card = QueueCard(
                item.get("title", "(title pending)"),
                item.get("url", ""),
                item.get("status", "Pending"),
                int(item.get("progress", 0)),
                show_thumbnail=True,
            )
        except Exception:
            card = None

        if card:
            card.setObjectName("QueueCard")

            # Hide micro progress (we use global progress)
            try:
                card.progress.setVisible(False)
                card.percent_lbl.setVisible(False)
            except Exception:
                pass

            # Context actions
            def _open_in_browser():
                webbrowser.open(item.get("url", ""))
            def _copy_url():
                QGuiApplication.clipboard().setText(item.get("url", ""))

            try:
                card.set_context_actions([
                    ("Open in browser", _open_in_browser),
                    ("Copy URL", _copy_url),
                    ("Remove", lambda: self._remove_item_by_id(item)),
                ])
            except Exception:
                pass

            return card

        # Fallback simple, progress-free card
        frame = QFrame()
        frame.setObjectName("QueueCard")
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)

        # Left: thumbnail placeholder
        thumb = QFrame()
        thumb.setObjectName("Thumb")
        thumb.setFixedSize(120, 68)
        lay.addWidget(thumb)

        # Middle: title + meta
        mid = QVBoxLayout()
        title_lbl = QLabel(item.get("title", "(title pending)"))
        title_lbl.setObjectName("CardTitle")
        meta_lbl = QLabel(f"{item.get('status','Pending')} • {item.get('format_code','')}")
        meta_lbl.setObjectName("CardMeta")
        mid.addWidget(title_lbl)
        mid.addWidget(meta_lbl)
        mid.addStretch(1)
        lay.addLayout(mid, 1)

        # Right: actions (no per-item progress)
        btn_del = QPushButton("Remove")
        btn_del.setObjectName("IconBtn")
        btn_del.setCursor(Qt.PointingHandCursor)
        btn_del.clicked.connect(lambda: self._remove_item_by_id(item))
        lay.addWidget(btn_del)

        # expose for filter
        frame.title_lbl = title_lbl
        frame.meta_lbl = meta_lbl
        return frame

    def _remove_item_by_id(self, it: Dict[str, Any]):
        try:
            idx = self.queue.index(it)
        except ValueError:
            return
        # If removing current downloading item, cancel worker
        if self.is_downloading and self.current_download_item is it and self.download_worker:
            self.download_worker.cancel()

        # Delete cached thumbnail
        try:
            url = it.get("url", "")
            if url in self._pending_thumb_urls:
                self._pending_thumb_urls.discard(url)
            
            # Try to find and delete cached thumbnail files
            video_id = it.get("video_id")
            if video_id:
                safe_name = self._thumb_safe_name(video_id)
                for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"):
                    p = self.thumb_cache_dir / f"{safe_name}{ext}"
                    try:
                        if p.exists():
                            p.unlink()
                    except Exception:
                        pass
        except Exception:
            pass

        self.queue.pop(idx)
        self._save_queue_permanent()
        self._refresh_queue_list()
        self._update_button_states()
        self._update_global_progress_bar()

    def _update_item_status(self, it: Dict[str, Any], status: str):
        it["status"] = status
        self._save_queue_permanent()
        self._refresh_queue_list()

    def _bulk_remove_selected(self):
        rows = sorted({i.row() for i in self.queue_list.selectedIndexes()}, reverse=True)
        if not rows:
            return
        # Cancel if current is being removed
        if self.is_downloading and rows and 0 in rows and self.download_worker:
            self.download_worker.cancel()

        for r in rows:
            if 0 <= r < len(self.queue):
                it = self.queue[r]
                # Remove from pending thumb set and delete cached thumbnails
                try:
                    url = it.get("url", "")
                    if url in self._pending_thumb_urls:
                        self._pending_thumb_urls.discard(url)
                    
                    video_id = it.get("video_id")
                    if video_id:
                        safe_name = self._thumb_safe_name(video_id)
                        for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"):
                            p = self.thumb_cache_dir / f"{safe_name}{ext}"
                            try:
                                if p.exists():
                                    p.unlink()
                            except Exception:
                                pass
                except Exception:
                    pass
                
                self.queue.pop(r)

        self._save_queue_permanent()
        self._refresh_queue_list()
        self._update_button_states()
        self._update_global_progress_bar()

    def _bulk_move_selected(self, top: bool = False, bottom: bool = False):
        rows = sorted({i.row() for i in self.queue_list.selectedIndexes()})
        if not rows:
            return
        items = [self.queue[r] for r in rows]
        # Remove from end to preserve indices
        for r in reversed(rows):
            self.queue.pop(r)
        if top:
            self.queue = items + self.queue
        elif bottom:
            self.queue.extend(items)
        self._save_queue_permanent()
        self._refresh_queue_list()
        # Reselect moved
        self.queue_list.clearSelection()
        if top:
            tgt_rows = list(range(len(items)))
        elif bottom:
            base = len(self.queue) - len(items)
            tgt_rows = list(range(base, base + len(items)))
        else:
            tgt_rows = []
        for r in tgt_rows:
            it = self.queue_list.item(r)
            it.setSelected(True)

    def _bulk_clear_completed(self):
        before = len(self.queue)
        keep = []
        for it in self.queue:
            if it.get("status") == "Completed":
                try:
                    url = it.get("url", "")
                    if url in self._pending_thumb_urls:
                        self._pending_thumb_urls.discard(url)
                    
                    video_id = it.get("video_id")
                    if video_id:
                        safe_name = self._thumb_safe_name(video_id)
                        for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"):
                            p = self.thumb_cache_dir / f"{safe_name}{ext}"
                            try:
                                if p.exists():
                                    p.unlink()
                            except Exception:
                                pass
                except Exception:
                    pass
            else:
                keep.append(it)
        self.queue = keep
        if len(self.queue) != before:
            self._save_queue_permanent()
            self._refresh_queue_list()
            self._update_button_states()
            self._update_global_progress_bar()
            
    # ----- Updater UI handlers (GUI thread) -----

    def _on_ytget_gui_ready(self, latest: str):
        reply = QMessageBox.information(
            self,
            f"{self.settings.APP_NAME} Update Available",
            f"A new version ({latest}) is available.\n"
            f"You are using {self.settings.VERSION}.\n\n"
            "Open the releases page?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            webbrowser.open(f"{self.settings.GITHUB_URL}/releases/latest")

    def _on_ytget_gui_uptodate(self):
        QMessageBox.information(self, "Up to Date", f"{self.settings.APP_NAME} is up to date.")

    def _on_ytget_gui_error(self, msg: str):
        QMessageBox.warning(self, "Update Check Failed", f"Could not check {self.settings.APP_NAME} updates:\n{msg}")

    def _on_ytdlp_ready(self, latest: str, current: str, asset_url: str):
        reply = QMessageBox.question(
            self,
            "yt-dlp Update Available",
            f"A new yt-dlp version ({latest}) is available.\n"
            f"Current version: {current}\n\n"
            "Download and replace it now?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.request_download_ytdlp.emit(asset_url)

    def _on_ytdlp_uptodate(self, current: str):
        QMessageBox.information(self, "Up to Date", f"yt-dlp is up to date (current: {current}).")

    def _on_ytdlp_error(self, msg: str):
        QMessageBox.warning(self, "yt-dlp Update Check Failed", f"Could not check yt-dlp updates:\n{msg}")

    def _on_ytdlp_download_success(self):
        QMessageBox.information(self, "yt-dlp Updated", "yt-dlp has been updated successfully.")

    def _on_ytdlp_download_failed(self, msg: str):
        QMessageBox.critical(self, "yt-dlp Update Failed", f"Could not update yt-dlp:\n{msg}")

    # ---------- Settings, dialogs, and helpers ----------

    def _refresh_format_box(self):
        # Safely rebuild resolutions combo in case settings changed
        current = self.format_box.currentText() if self.format_box.count() else None
        self.format_box.blockSignals(True)
        self.format_box.clear()
        for k in self.settings.RESOLUTIONS.keys():
            self.format_box.addItem(k)
        # try restore previous selection
        if current and current in self.settings.RESOLUTIONS:
            self.format_box.setCurrentText(current)
        elif self.format_box.count():
            self.format_box.setCurrentIndex(0)
        self.format_box.blockSignals(False)

    def _apply_settings_dict(self, cfg: Dict[str, Any]):
        # Apply keys from dialog dict onto settings if they exist
        for k, v in (cfg or {}).items():
            if hasattr(self.settings, k):
                try:
                    setattr(self.settings, k, v)
                except Exception:
                    pass

    def _persist_settings(self):
        # Support both new and old settings APIs
        if hasattr(self.settings, "save") and callable(getattr(self.settings, "save")):
            try:
                self.settings.save()
                return
            except Exception:
                pass
        if hasattr(self.settings, "save_config") and callable(getattr(self.settings, "save_config")):
            try:
                self.settings.save_config()
            except Exception:
                pass

    def _show_preferences(self):
        try:
            dlg = PreferencesDialog(self, self.settings)  # parent first
            if dlg.exec():
                # 1) If dialog exposes apply(), use it (preferred modern flow)
                if hasattr(dlg, "apply") and callable(getattr(dlg, "apply")):
                    try:
                        dlg.apply()
                    except Exception:
                        pass
                # 2) Else, if dialog exposes get_settings(), merge into AppSettings
                elif hasattr(dlg, "get_settings") and callable(getattr(dlg, "get_settings")):
                    try:
                        new_cfg = dlg.get_settings()
                        self._apply_settings_dict(new_cfg)
                    except Exception:
                        pass
                # 3) Else assume dialog mutated self.settings directly

                # Persist and refresh UI
                self._persist_settings()
                self.download_path_btn.setText(str(self.settings.DOWNLOADS_DIR))
                self._refresh_format_box()
                self.log("✅ Preferences saved.\n", AppStyles.SUCCESS_COLOR, "Info")

                # Re-log toggles so user sees active config
                self._log_startup()
        except Exception as e:
            QMessageBox.warning(self, "Preferences", f"Couldn't open Preferences:\n{e}")

    def _show_advanced_options(self):
        try:
            dlg = AdvancedOptionsDialog(self, self.settings)  # parent first
            if dlg.exec():
                # Similar compatibility handling
                if hasattr(dlg, "apply") and callable(getattr(dlg, "apply")):
                    try:
                        dlg.apply()
                    except Exception:
                        pass
                elif hasattr(dlg, "get_options") and callable(getattr(dlg, "get_options")):
                    try:
                        o = dlg.get_options()
                        self._apply_settings_dict(o)
                    except Exception:
                        pass
                # Persist and reflect
                self._persist_settings()
                self.log("✅ Advanced options applied.\n", AppStyles.SUCCESS_COLOR, "Info")
                # Re-log a few fields that commonly change
                if self.settings.CLIP_START and self.settings.CLIP_END:
                    self.log(f"⏱️ Clip: {self.settings.CLIP_START}-{self.settings.CLIP_END}\n", AppStyles.INFO_COLOR, "Info")
                if getattr(self.settings, "PLAYLIST_ITEMS", ""):
                    self.log(f"🎬 Playlist Items: {self.settings.PLAYLIST_ITEMS}\n", AppStyles.INFO_COLOR, "Info")
                if getattr(self.settings, "PLAYLIST_REVERSE", False):
                    self.log("↩️ Playlist Reverse: On\n", AppStyles.INFO_COLOR, "Info")
        except Exception as e:
            QMessageBox.warning(self, "Advanced Options", f"Couldn't open Advanced Options:\n{e}")

    def _show_about(self):
        box = QMessageBox(self)
        box.setWindowTitle("About")

        text = (
            f"<h2>{self.settings.APP_NAME} {self.settings.VERSION}</h2>"
            "A Simple Yet Powerful GUI For yt-dlp.\n\n"
        )
        box.setText(text)

        if self._app_icon:
            box.setIconPixmap(self._app_icon.pixmap(64, 64))  # show .ico in dialog
        else:
            box.setIcon(QMessageBox.Information)

        box.setStandardButtons(QMessageBox.Ok)
        box.exec()

    def _set_download_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Download Folder", str(self.settings.DOWNLOADS_DIR))
        if path:
            try:
                self.settings.DOWNLOADS_DIR = Path(path)
                self.download_path_btn.setText(str(self.settings.DOWNLOADS_DIR))
                self.log(f"📂 Download folder set to: {path}\n", AppStyles.INFO_COLOR, "Info")
            finally:
                self._persist_settings()

    def _set_cookies_path(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select Cookies File", str(self.settings.BASE_DIR), "Cookies (*.txt *.json);;All Files (*)")
        if file:
            self.settings.COOKIES_PATH = Path(file)
            self.log(f"🍪 Cookies file set to: {file}\n", AppStyles.INFO_COLOR, "Info")
            self._persist_settings()

    def _set_post_queue_action(self, value: str):
        self.post_queue_action = value
        self.post_action.setCurrentText(value)

        # Sync the ComboBox
        if self.post_action.currentText() != value:
            self.post_action.setCurrentText(value)

        # Sync the menu actions
        for k, act in self.post_actions_map.items():
            act.setChecked(k == value)

    def _update_button_states(self):
        has_items = len(self.queue) > 0
        self.btn_start_queue.setEnabled(has_items and (self.queue_paused or not self.is_downloading))
        self.btn_pause_queue.setEnabled(self.is_downloading and not self.queue_paused)
        self.btn_skip.setEnabled(self.is_downloading)

    # ---------- Persistent queue (auto-save to queue.json) ----------

    def _save_queue_permanent(self):
        try:
            self.queue_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.queue_file_path, "w", encoding="utf-8") as f:
                json.dump(self.queue, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log(f"❌ Failed to save queue.json: {e}\n", AppStyles.ERROR_COLOR, "Error")

    def _load_permanent_queue(self):
        try:
            if self.queue_file_path.exists():
                with open(self.queue_file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        cleaned = []
                        for it in data:
                            if not isinstance(it, dict):
                                continue
                            cleaned.append({
                                "url": it.get("url", ""),
                                "title": it.get("title", ""),
                                "format_code": it.get("format_code", self.settings.RESOLUTIONS.get(self.format_box.currentText(), "")),
                                "status": it.get("status", "Pending"),
                                "progress": 0,
                                "video_id": it.get("video_id", ""),
                                "thumbnail_url": it.get("thumbnail_url", ""),
                                "thumb_path": it.get("thumb_path", ""),
                                "is_playlist": bool(it.get("is_playlist", False)),
                            })
                        self.queue = cleaned
                    else:
                        self.queue = []
            else:
                self.queue = []
                # Create an empty file to make it "permanent"
                self._save_queue_permanent()

            self._refresh_queue_list()
            # Re-ensure thumbnails for items loaded from disk
            for it in self.queue:
                # If thumb_path exists and file is valid, enqueue it for potential refresh
                tp = it.get("thumb_path")
                if tp and Path(tp).exists():
                    try:
                        # Add to pending set to prevent duplicate fetches
                        url = it.get("url", "")
                        if url:
                            self._pending_thumb_urls.add(url)
                    except Exception:
                        pass
                else:
                    # Try to fetch
                    url = it.get("url", "")
                    if url and url not in self._pending_thumb_urls:
                        try:
                            self._pending_thumb_urls.add(url)
                            self.thumb_manager.enqueue(url)
                        except Exception:
                            pass

            self._update_button_states()
            self._update_global_progress_bar()
        except Exception as e:
            self.queue = []
            self.log(f"❌ Failed to load queue.json: {e}\n", AppStyles.ERROR_COLOR, "Error")

    def _save_queue_to_disk(self):
        file, _ = QFileDialog.getSaveFileName(self, "Save Queue As", str(self.queue_file_path), "JSON (*.json)")
        if not file:
            return
        try:
            with open(file, "w", encoding="utf-8") as f:
                json.dump(self.queue, f, indent=2, ensure_ascii=False)
            self.log(f"💾 Queue saved to {file}\n", AppStyles.SUCCESS_COLOR, "Info")
        except Exception as e:
            self.log(f"❌ Couldn't save queue: {e}\n", AppStyles.ERROR_COLOR, "Error")

    def _load_queue_from_disk(self):
        file, _ = QFileDialog.getOpenFileName(self, "Load Queue", str(self.queue_file_path.parent), "JSON (*.json)")
        if not file:
            return
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    self.queue = data
                    self._save_queue_permanent()
                    self._refresh_queue_list()
                    # Re-ensure thumbs
                    for it in self.queue:
                        tp = it.get("thumb_path")
                        url = it.get("url", "")
                        if url and url not in self._pending_thumb_urls:
                            try:
                                self._pending_thumb_urls.add(url)
                                self.thumb_manager.enqueue(url)
                            except Exception:
                                pass
                    self._update_button_states()
                    self._update_global_progress_bar()
                    self.log(f"📥 Queue loaded from {file}\n", AppStyles.SUCCESS_COLOR, "Info")
                else:
                    raise ValueError("Invalid queue file format.")
        except Exception as e:
            self.log(f"❌ Couldn't load queue: {e}\n", AppStyles.ERROR_COLOR, "Error")

    # ---------- Window state ----------

    def _restore_window(self):
        settings = QSettings(self.settings.APP_NAME, self.settings.APP_NAME)
        geo = settings.value("main/geometry")
        state = settings.value("main/windowState")
        if geo:
            self.restoreGeometry(geo)
        if state:
            self.restoreState(state)
        sizes = settings.value("main/splitSizes")
        if sizes:
            try:
                self.main_split.setSizes([int(s) for s in sizes])
            except Exception:
                pass

    def closeEvent(self, event):
        """
        Ensure the thumb manager and other worker threads are stopped cleanly
        so no background thread tries to touch GUI objects after the window closes.
        """
        try:
            # Stop thumb manager and wait for its worker to finish
            try:
                if hasattr(self, "thumb_manager") and self.thumb_manager is not None:
                    self.thumb_manager.stop(wait=True)
            except Exception:
                pass

            # Clear pending set to avoid memory retention
            try:
                if hasattr(self, "_pending_thumb_urls"):
                    self._pending_thumb_urls.clear()
            except Exception:
                pass

            # Save window state and queue
            settings = QSettings(self.settings.APP_NAME, self.settings.APP_NAME)
            settings.setValue("main/geometry", self.saveGeometry())
            settings.setValue("main/windowState", self.saveState())
            settings.setValue("main/splitSizes", self.main_split.sizes())
            try:
                settings.sync()
            except Exception:
                pass

            # Persist queue one last time
            self._save_queue_permanent()

            # Cancel download worker gracefully
            try:
                if self.download_worker:
                    self.download_worker.cancel()
            except Exception:
                pass

            # Stop title-fetch queue thread cleanly
            try:
                if self.title_queue:
                    self.title_queue.stop()
                if self.title_queue_thread:
                    self.title_queue_thread.quit()
                    self.title_queue_thread.wait(2000)
            except Exception:
                pass

            # Stop cover worker if running
            try:
                if self.cover_thread and self.cover_thread.isRunning():
                    self.cover_thread.quit()
                    self.cover_thread.wait(2000)
            except Exception:
                pass

            # Stop updater thread
            try:
                if hasattr(self, "update_thread") and self.update_thread and self.update_thread.isRunning():
                    self.update_thread.quit()
                    self.update_thread.wait(2000)
            except Exception:
                pass

        except Exception:
            pass

        super().closeEvent(event)
