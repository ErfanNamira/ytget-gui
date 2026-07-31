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
from collections import deque
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
    QGraphicsDropShadowEffect,
)

from ytget_gui.settings import AppSettings
from ytget_gui.styles import AppStyles
from ytget_gui.utils.validators import is_supported_url, is_youtube_url
from ytget_gui.dialogs.preferences import PreferencesDialog
from ytget_gui.dialogs.advanced import AdvancedOptionsDialog
from ytget_gui.dialogs.update_manager import UpdateManager
from ytget_gui.dialogs.about_dialog import AboutDialog
from ytget_gui.workers.download_worker import DownloadWorker
from ytget_gui.workers.cover_crop_worker import CoverCropWorker
from ytget_gui.widgets.queue_card import QueueCard
from ytget_gui.workers.title_fetch_manager import TitleFetchQueue
from ytget_gui.workers.thumb_fetcher import ThumbManager
from ytget_gui.spotdl_settings import SpotDLSettings
from ytget_gui.workers.spotdl_worker import SpotDLWorker

def short(text: str, n: int = 50) -> str:
    return text[:n] + "..." if len(text) > n else text


# ─────────────────────────────────────────────────────────────────────────────
#  THEME — Glassmorphism: frosted glass panels over deep space gradient
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
#  THEME — Glassmorphism: frosted glass panels over deep space gradient
# ─────────────────────────────────────────────────────────────────────────────
QSS_THEME = """
/* ── Root: deep space gradient backdrop (matches Advanced dialog) ── */
QMainWindow {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #0a0e1a,
        stop:0.3 #15102e,
        stop:0.6 #1e1b4b,
        stop:1 #0c1733);
    color: #F4F4F8;
    font-family: "Inter", "SF Pro Display", "Segoe UI", sans-serif;
    font-size: 13px;
}

/* Central widget must be transparent so the gradient shows through */
#CentralWidget {
    background: transparent;
}

/* ── Top Bar — transparent to show gradient ── */
#TopBar {
    background: transparent;
    border-bottom: 1px solid rgba(255, 255, 255, 20);
}

/* ── Brand ── */
#Brand {
    font-size: 16px;
    font-weight: 800;
    letter-spacing: 1.5px;
    color: #00E5FF;
}

#BrandDot {
    color: #FF3B6B;
    font-size: 22px;
    font-weight: 900;
}

#VersionChip {
    background: rgba(255, 255, 255, 25);
    border: 1px solid rgba(255, 255, 255, 40);
    color: rgba(255, 255, 255, 180);
    font-size: 10px;
    border-radius: 6px;
    padding: 2px 8px;
}

/* ── URL Input Area — glass ── */
#UrlWrap {
    background: rgba(255, 255, 255, 15);
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 10px;
}
#UrlWrap:hover {
    background: rgba(255, 255, 255, 20);
    border: 1px solid rgba(255, 255, 255, 50);
}
#UrlWrap:focus-within {
    border: 1px solid rgba(0, 229, 255, 150);
    background: rgba(0, 229, 255, 15);
}
#UrlWrap QLineEdit {
    background: transparent;
    border: none;
    color: #F4F4F8;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 13px;
    padding: 9px 12px;
    selection-background-color: #00E5FF;
    selection-color: #0a0e1a;
}

/* ── Format Combo — glass ── */
#FormatBox {
    background: rgba(255, 255, 255, 15);
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 8px;
    color: rgba(255, 255, 255, 200);
    font-size: 12px;
    padding: 7px 12px;
    min-width: 130px;
}
#FormatBox:hover {
    background: rgba(255, 255, 255, 25);
    border: 1px solid rgba(255, 255, 255, 50);
}
#FormatBox::drop-down {
    border: none;
    width: 22px;
}
#FormatBox::down-arrow {
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid rgba(255, 255, 255, 150);
    margin-right: 8px;
}
#FormatBox QAbstractItemView {
    background: rgba(20, 20, 40, 240);
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 8px;
    color: #F4F4F8;
    selection-background-color: rgba(0, 229, 255, 80);
    selection-color: #ffffff;
    padding: 4px;
    outline: none;
}

/* ── Generic Buttons ── */
QPushButton {
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 12px;
}

#BtnAdd {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #00E5FF, stop:1 #00B8FF);
    color: #0a0e1a;
    border: 1px solid rgba(0, 229, 255, 100);
    border-radius: 8px;
    padding: 8px 18px;
    font-weight: 700;
    font-size: 12px;
    letter-spacing: 0.5px;
}
#BtnAdd:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #33EEFF, stop:1 #33CCFF);
}
#BtnAdd:disabled {
    background: rgba(255, 255, 255, 10);
    color: rgba(255, 255, 255, 80);
    border: 1px solid rgba(255, 255, 255, 20);
}

#BtnPaste {
    background: rgba(255, 255, 255, 15);
    color: rgba(255, 255, 255, 180);
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 8px;
    padding: 8px 14px;
}
#BtnPaste:hover {
    background: rgba(255, 255, 255, 25);
    color: #F4F4F8;
    border: 1px solid rgba(255, 255, 255, 50);
}

#BtnClear {
    background: transparent;
    color: rgba(255, 255, 255, 100);
    border: none;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 14px;
}
#BtnClear:hover {
    color: rgba(255, 255, 255, 200);
    background: rgba(255, 255, 255, 15);
}

#BtnTopbar {
    background: rgba(255, 255, 255, 15);
    color: rgba(255, 255, 255, 180);
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 8px;
    padding: 7px 13px;
}
#BtnTopbar:hover {
    color: #F4F4F8;
    border: 1px solid rgba(255, 255, 255, 50);
    background: rgba(255, 255, 255, 25);
}

/* ── Splitter ── */
QSplitter::handle {
    background: rgba(255, 255, 255, 15);
    width: 1px;
}
QSplitter::handle:hover {
    background: rgba(0, 229, 255, 100);
}

/* ── Queue Pane — transparent to show gradient ── */
#QueuePane {
    background: transparent;
    border-right: 1px solid rgba(255, 255, 255, 20);
}

#QueueHeader {
    background: transparent;
    border-bottom: 1px solid rgba(255, 255, 255, 15);
}

#PaneLabel {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
    color: rgba(255, 255, 255, 120);
}

#CountBadge {
    background: rgba(0, 229, 255, 30);
    color: #00E5FF;
    border: 1px solid rgba(0, 229, 255, 60);
    border-radius: 6px;
    font-size: 10px;
    padding: 1px 7px;
}

#SearchBox {
    background: rgba(255, 255, 255, 15);
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 8px;
    color: rgba(255, 255, 255, 200);
    font-size: 12px;
    padding: 6px 10px;
}
#SearchBox:focus {
    border: 1px solid rgba(0, 229, 255, 120);
    background: rgba(0, 229, 255, 10);
    color: #F4F4F8;
}

#SortBox {
    background: rgba(255, 255, 255, 15);
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 8px;
    color: rgba(255, 255, 255, 150);
    font-size: 11px;
    padding: 5px 8px;
}
#SortBox::drop-down { border: none; width: 18px; }
#SortBox::down-arrow {
    width: 0; height: 0;
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-top: 4px solid rgba(255, 255, 255, 120);
    margin-right: 6px;
}
#SortBox QAbstractItemView {
    background: rgba(20, 20, 40, 240);
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 8px;
    color: #F4F4F8;
    selection-background-color: rgba(0, 229, 255, 80);
    padding: 4px;
    outline: none;
}

/* ── Queue List ── */
#QueueList {
    background: transparent;
    border: none;
}
#QueueList::item {
    background: transparent;
    border: none;
    padding: 0px;
    border-radius: 12px;
}
#QueueList::item:selected {
    background: rgba(0, 229, 255, 20);
    border-radius: 12px;
}

/* ── Empty State ── */
#EmptyState {
    color: rgba(255, 255, 255, 80);
    background: transparent;
    font-size: 12px;
}

/* ── Bulk Bar — glass ── */
#BulkBar {
    background: rgba(0, 229, 255, 15);
    border-top: 1px solid rgba(0, 229, 255, 40);
}
#BulkLabel {
    color: #00E5FF;
    font-size: 11px;
}
#BulkBtn {
    background: rgba(255, 255, 255, 15);
    color: rgba(255, 255, 255, 150);
    border: 1px solid rgba(255, 255, 255, 25);
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 11px;
}
#BulkBtn:hover {
    color: #F4F4F8;
    border: 1px solid rgba(255, 255, 255, 50);
    background: rgba(255, 255, 255, 25);
}

/* ── Console Pane — dark frosted glass (log part) ── */
#ConsolePane {
    background: rgba(5, 5, 15, 220);
    border-left: 1px solid rgba(255, 255, 255, 20);
}

#ConsolePaneLabel {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
    color: rgba(255, 255, 255, 120);
}

#FilterBox {
    background: rgba(255, 255, 255, 15);
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 8px;
    color: rgba(255, 255, 255, 150);
    font-size: 11px;
    padding: 5px 8px;
    min-width: 80px;
}
#FilterBox::drop-down { border: none; width: 18px; }
#FilterBox::down-arrow {
    width: 0; height: 0;
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-top: 4px solid rgba(255, 255, 255, 120);
    margin-right: 6px;
}
#FilterBox QAbstractItemView {
    background: rgba(20, 20, 40, 240);
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 8px;
    color: #F4F4F8;
    selection-background-color: rgba(0, 229, 255, 80);
    padding: 4px;
    outline: none;
}

#ConsoleTool {
    background: rgba(255, 255, 255, 15);
    color: rgba(255, 255, 255, 120);
    border: 1px solid rgba(255, 255, 255, 25);
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 11px;
}
#ConsoleTool:hover {
    color: rgba(255, 255, 255, 200);
    border: 1px solid rgba(255, 255, 255, 45);
    background: rgba(255, 255, 255, 25);
}

#Console {
    background: transparent;
    color: rgba(255, 255, 255, 160);
    border: none;
    border-top: 1px solid rgba(255, 255, 255, 15);
    font-family: "JetBrains Mono", "Fira Code", Consolas, monospace;
    font-size: 12px;
    padding: 14px;
    line-height: 1.7;
}

/* ── Bottom Bar — transparent to show gradient ── */
#BottomBar {
    background: transparent;
    border-top: 1px solid rgba(255, 255, 255, 20);
}

#BtnStart {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #00E5FF, stop:1 #00B8FF);
    color: #0a0e1a;
    border: 1px solid rgba(0, 229, 255, 100);
    border-radius: 8px;
    padding: 9px 22px;
    font-weight: 700;
    font-size: 13px;
    letter-spacing: 0.5px;
    min-width: 90px;
}
#BtnStart:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #33EEFF, stop:1 #33CCFF);
}
#BtnStart:disabled {
    background: rgba(255, 255, 255, 10);
    color: rgba(255, 255, 255, 60);
    border: 1px solid rgba(255, 255, 255, 15);
}

#BtnPause {
    background: rgba(255, 255, 255, 15);
    color: rgba(255, 255, 255, 120);
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 8px;
    padding: 9px 18px;
    font-size: 12px;
}
#BtnPause:enabled {
    color: rgba(255, 255, 255, 200);
    border: 1px solid rgba(255, 255, 255, 45);
}
#BtnPause:hover:enabled {
    color: #F4F4F8;
    background: rgba(255, 255, 255, 25);
    border: 1px solid rgba(255, 255, 255, 60);
}
#BtnPause:disabled {
    color: rgba(255, 255, 255, 50);
    border: 1px solid rgba(255, 255, 255, 15);
}

#BtnSkip {
    background: rgba(255, 255, 255, 15);
    color: rgba(255, 255, 255, 100);
    border: 1px solid rgba(255, 255, 255, 25);
    border-radius: 8px;
    padding: 9px 14px;
    font-size: 12px;
}
#BtnSkip:enabled {
    color: rgba(255, 255, 255, 180);
    border: 1px solid rgba(255, 255, 255, 45);
}
#BtnSkip:hover:enabled {
    color: #F4F4F8;
    border: 1px solid rgba(255, 255, 255, 60);
    background: rgba(255, 255, 255, 25);
}
#BtnSkip:disabled {
    color: rgba(255, 255, 255, 40);
    border: 1px solid rgba(255, 255, 255, 15);
}

#BtnStop {
    background: rgba(248, 113, 113, 15);
    color: rgba(248, 113, 113, 120);
    border: 1px solid rgba(248, 113, 113, 30);
    border-radius: 8px;
    padding: 9px 14px;
    font-size: 12px;
}
#BtnStop:enabled {
    color: #F87171;
    border: 1px solid rgba(248, 113, 113, 50);
}
#BtnStop:hover:enabled {
    color: #FECACA;
    background: rgba(248, 113, 113, 30);
    border: 1px solid rgba(248, 113, 113, 80);
}
#BtnStop:disabled {
    color: rgba(255, 255, 255, 40);
    border: 1px solid rgba(255, 255, 255, 15);
    background: rgba(255, 255, 255, 10);
}

/* ── Progress Bar ── */
#GlobalProgress {
    background: rgba(255, 255, 255, 15);
    border: none;
    border-radius: 2px;
    max-height: 3px;
}
#GlobalProgress::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #00E5FF, stop:0.5 #7C4DFF, stop:1 #00B8FF);
    border-radius: 2px;
}

/* ── Post Action / Path ── */
#PostActionBox {
    background: rgba(255, 255, 255, 15);
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 8px;
    color: rgba(255, 255, 255, 150);
    font-size: 11px;
    padding: 5px 8px;
    min-width: 95px;
}
#PostActionBox::drop-down { border: none; width: 18px; }
#PostActionBox::down-arrow {
    width: 0; height: 0;
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-top: 4px solid rgba(255, 255, 255, 120);
    margin-right: 6px;
}
#PostActionBox QAbstractItemView {
    background: rgba(20, 20, 40, 240);
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 8px;
    color: #F4F4F8;
    selection-background-color: rgba(0, 229, 255, 80);
    padding: 4px;
    outline: none;
}
#AfterLabel {
    color: rgba(255, 255, 255, 120);
    font-size: 11px;
}
#PathBtn {
    background: rgba(255, 255, 255, 15);
    color: rgba(255, 255, 255, 120);
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 8px;
    padding: 5px 10px;
    font-size: 11px;
    max-width: 260px;
}
#PathBtn:hover {
    color: rgba(255, 255, 255, 200);
    border: 1px solid rgba(255, 255, 255, 50);
    background: rgba(255, 255, 255, 25);
}

/* ── Scrollbars ── */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
    border: none;
}
QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 40);
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(255, 255, 255, 70);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 0;
    border: none;
}
QScrollBar::handle:horizontal {
    background: rgba(255, 255, 255, 40);
    border-radius: 4px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover {
    background: rgba(255, 255, 255, 70);
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

/* ── Menu Bar — frosted glass ── */
QMenuBar {
    background: transparent;
    color: rgba(255, 255, 255, 150);
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 12px;
    border-bottom: 1px solid rgba(255, 255, 255, 20);
    padding: 2px 4px;
}
QMenuBar::item:selected {
    background: rgba(255, 255, 255, 25);
    color: #F4F4F8;
    border-radius: 6px;
}
QMenu {
    background: rgba(20, 20, 40, 240);
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 10px;
    color: rgba(255, 255, 255, 200);
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 12px;
    padding: 6px;
}
QMenu::item {
    padding: 6px 24px 6px 14px;
    border-radius: 6px;
}
QMenu::item:selected {
    background: rgba(0, 229, 255, 40);
    color: #F4F4F8;
}
QMenu::separator {
    height: 1px;
    background: rgba(255, 255, 255, 20);
    margin: 4px 8px;
}

/* ── Queue Card — glass ── */
QFrame#QueueCard {
    background: rgba(255, 255, 255, 18);
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 12px;
}
QFrame#QueueCard[elevated="true"] {
    background: rgba(255, 255, 255, 30);
    border: 1px solid rgba(255, 255, 255, 50);
}
QFrame#QueueCard #DragHandle {
    color: rgba(255, 255, 255, 60);
    font-size: 14px;
}
QFrame#QueueCard #Thumb {
    background: rgba(0, 0, 0, 100);
    border: 1px solid rgba(255, 255, 255, 20);
    border-radius: 8px;
}
QFrame#QueueCard #CardTitle {
    color: #F4F4F8;
    font-size: 13px;
    font-weight: 600;
}
QFrame#QueueCard #CardMeta {
    color: rgba(255, 255, 255, 120);
    font-size: 11px;
}
QFrame#QueueCard #StatusChip {
    border-radius: 6px;
    padding: 1px 8px;
    font-size: 10px;
    font-weight: 600;
}
QFrame#QueueCard #Progress {
    background: rgba(255, 255, 255, 20);
    border: none;
    border-radius: 3px;
}
QFrame#QueueCard #Progress::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #00E5FF, stop:1 #7C4DFF);
    border-radius: 3px;
}
QFrame#QueueCard #Percent {
    color: rgba(255, 255, 255, 150);
    font-size: 10px;
}
QFrame#QueueCard #IconBtn {
    background: rgba(255, 255, 255, 15);
    color: rgba(255, 255, 255, 120);
    border: 1px solid rgba(255, 255, 255, 25);
    border-radius: 6px;
    font-size: 11px;
}
QFrame#QueueCard #IconBtn:hover {
    background: rgba(255, 255, 255, 25);
    color: #F4F4F8;
}

/* ── Tooltip ── */
QToolTip {
    background: rgba(20, 20, 40, 240);
    color: #F4F4F8;
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 6px;
    padding: 5px 8px;
    font-size: 11px;
}

/* ── Drop active state ── */
#QueuePane[dropActive="true"] {
    background: rgba(0, 229, 255, 30);
    border-right: 2px solid rgba(0, 229, 255, 120);
}
"""

MAX_LOG_LINES = 200


class MainWindow(QMainWindow):
    # ── Signals ──────────────────────────────────────────────────
    enqueue_title = Signal(str)
    enqueue_titles = Signal(list)
    post_queue_action_signal = Signal(str)

    # ════════════════════════════════════════════════════════════════════════
    def __init__(self):
        super().__init__()
        self.settings = AppSettings()
        self.styles = AppStyles()

        self.post_queue_action_signal.connect(self._perform_post_queue_action, Qt.QueuedConnection)

        # Thumbnail cache
        self.thumb_cache_dir: Path = self.settings.BASE_DIR / "cache" / "thumbs"
        self.thumb_cache_dir.mkdir(parents=True, exist_ok=True)

        self.thumb_manager = ThumbManager(self.thumb_cache_dir, self.settings, max_workers=1)
        self.thumb_manager.started.connect(self._on_thumb_started, Qt.QueuedConnection)
        self.thumb_manager.finished.connect(self._on_thumb_finished, Qt.QueuedConnection)
        self.thumb_manager.error.connect(self._on_thumb_error, Qt.QueuedConnection)
        self._pending_thumb_urls = set()
        self._thumb_jobs: Dict[str, Tuple[QThread, object]] = {}

        self.queue: List[Dict[str, Any]] = []
        self.current_download_item: Optional[Dict[str, Any]] = None
        self.is_downloading = False
        self.queue_paused = True
        self._stop_all_requested: bool = False
        self.post_queue_action = "Keep"
        self._initial_queue_len: int = 0

        self.download_thread: Optional[QThread] = None
        self.download_worker: Optional[DownloadWorker] = None
        self.spotdl_thread: Optional[QThread] = None
        self.spotdl_worker: Optional[SpotDLWorker] = None
        self.cover_thread: Optional[QThread] = None
        self.cover_worker: Optional[CoverCropWorker] = None
        self._cover_crop_running: bool = False
        self.title_queue_thread: Optional[QThread] = None
        self.title_queue: Optional[TitleFetchQueue] = None

        self._log_entries: List[Tuple[str, str, str]] = []

        self.queue_file_path: Path = self.settings.BASE_DIR / "queue.json"

        # UI refs
        self.queue_list: QListWidget
        self.queue_empty_state: QLabel
        self.log_output: QTextEdit
        self.url_input: QLineEdit
        self.format_box: QComboBox
        self.btn_add_inline: QPushButton
        self.btn_start_queue: QPushButton
        self.btn_pause_queue: QPushButton
        self.btn_stop_all: QPushButton
        self.btn_skip: QPushButton
        self.global_progress: QProgressBar
        self.post_action: QComboBox
        self.download_path_btn: QPushButton
        self.queue_pane: QWidget
        self.filter_combo: QComboBox
        self.queue_title: QLabel
        self.count_chip: QLabel
        self.search_box: QLineEdit
        self.sort_combo: QComboBox
        self.bulk_bar: QFrame
        self.bulk_label: QLabel

        self._app_icon: Optional[QIcon] = None

        self._setup_ui()
        self.btn_skip.hide()
        self._setup_connections()
        self._setup_menu()
        self._setup_title_fetch_queue()
        self._load_permanent_queue()
        self._restore_window()
        self._log_startup()

    # ════════════════════════════════════════════════════════════════════════
    #  LOGGING
    # ════════════════════════════════════════════════════════════════════════

    def log(self, text: str, color: str = AppStyles.INFO_COLOR, level: str = "Info"):
        if text is None:
            return
        raw_lines = str(text).splitlines()
        for raw_line in raw_lines:
            s = " ".join(raw_line.split()).strip()
            if not s:
                continue
            prefix = ""
            clean_check = s.replace("🚀", "").strip()
            if clean_check.startswith("Starting Download for:"):
                prefix = "🚀 "
            elif level and str(level).lower() == "warning":
                prefix = "⚠️ "
            elif level and str(level).lower() == "error":
                prefix = "❌ "
            elif level and str(level).lower() in ["success", "process"]:
                prefix = "✅ "
            elif "merger" in s.lower() or "merging" in s.lower():
                prefix = "📦 "
            elif "deleting" in s.lower():
                prefix = "🧹 "
            final_content = s.replace("🚀", "").strip()
            final_text = f"{prefix}{final_content}".strip()
            final_color = color if color else AppStyles.INFO_COLOR
            _level_norm = str(level).strip().capitalize() if level else "Info"
            _level_map = {"Success": "Info", "Process": "Info", "Warn": "Warning"}
            final_level = _level_map.get(_level_norm, _level_norm)
            if not hasattr(self, "_log_entries"):
                self._log_entries = []
            self._log_entries.append((final_text, final_color, final_level))
            max_lines = getattr(self.settings, "MAX_LOG_LINES", MAX_LOG_LINES)
            if len(self._log_entries) > max_lines:
                self._log_entries = self._log_entries[-max_lines:]
            filt_text = self.filter_combo.currentText() if hasattr(self, "filter_combo") else "All"
            if filt_text == "All" or filt_text == final_level:
                self._append_to_console(final_text, final_color)

    def _render_log(self):
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
        try:
            if not self.log_output:
                return
            self.log_output.moveCursor(QTextCursor.End)
            self.log_output.setTextColor(QColor(color))
            self.log_output.append(text)
            self.log_output.setTextColor(QColor(AppStyles.INFO_COLOR))
            self.log_output.ensureCursorVisible()
        except Exception:
            pass

    # ════════════════════════════════════════════════════════════════════════
    #  UI SCAFFOLD
    # ════════════════════════════════════════════════════════════════════════

    def _setup_ui(self):
        self.setWindowTitle(f"{self.settings.APP_NAME}  ·  {self.settings.VERSION}")
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

        self.resize(1280, 820)
        self.setMinimumSize(900, 600)

        # Font — modern sans-serif for glassmorphism
        f = QFont("Inter", 10)
        self.setFont(f)
        self.setStyleSheet(QSS_THEME)

        central = QWidget()
        central.setObjectName("CentralWidget")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar
        self.top_bar = self._build_top_bar()
        root.addWidget(self.top_bar)

        # Progress bar — flush under the top bar, 3 px line
        self.global_progress = QProgressBar()
        self.global_progress.setObjectName("GlobalProgress")
        self.global_progress.setTextVisible(False)
        self.global_progress.setMaximumHeight(3)
        self.global_progress.setRange(0, 100)
        self.global_progress.setValue(0)
        root.addWidget(self.global_progress)

        # Main body — queue | console
        self.main_split = QSplitter(Qt.Horizontal)
        self.main_split.setChildrenCollapsible(False)
        self.main_split.setHandleWidth(1)
        root.addWidget(self.main_split, 1)

        self.queue_pane = self._build_queue_pane()
        self.console_pane = self._build_console_pane()

        self.main_split.addWidget(self.queue_pane)
        self.main_split.addWidget(self.console_pane)
        self.main_split.setStretchFactor(0, 2)
        self.main_split.setStretchFactor(1, 3)
        QTimer.singleShot(120, lambda: self.main_split.setSizes([
            int(self.width() * 0.40),
            int(self.width() * 0.60),
        ]))

        # Bottom bar
        self.bottom_bar = self._build_bottom_bar()
        root.addWidget(self.bottom_bar)

        self.setAcceptDrops(True)

    # ── Helper: add glass shadow to a widget ────────────────────────────────
    @staticmethod
    def _add_glass_shadow(widget: QWidget, blur: int = 20, alpha: int = 80, y: int = 4) -> None:
        eff = QGraphicsDropShadowEffect(widget)
        eff.setBlurRadius(blur)
        eff.setColor(QColor(0, 0, 0, alpha))
        eff.setOffset(0, y)
        widget.setGraphicsEffect(eff)

    # ── Top Bar ─────────────────────────────────────────────────────────────
    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(56)

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 16, 0)
        lay.setSpacing(14)

        # Brand
        brand_wrap = QHBoxLayout()
        brand_wrap.setSpacing(0)
        lbl_brand = QLabel(self.settings.APP_NAME.upper())
        lbl_brand.setObjectName("Brand")
        lbl_dot = QLabel("·")
        lbl_dot.setObjectName("BrandDot")
        lbl_dot.setContentsMargins(5, 0, 5, 0)
        lbl_version = QLabel(f"v{self.settings.VERSION}")
        lbl_version.setObjectName("VersionChip")
        brand_wrap.addWidget(lbl_brand)
        brand_wrap.addWidget(lbl_dot)
        brand_wrap.addWidget(lbl_version)
        brand_wrap.addSpacing(4)
        brand_w = QWidget()
        brand_w.setLayout(brand_wrap)
        lay.addWidget(brand_w)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color: rgba(255, 255, 255, 30);")
        sep.setFixedHeight(24)
        lay.addWidget(sep)

        # URL input
        url_wrap = QFrame()
        url_wrap.setObjectName("UrlWrap")
        url_lay = QHBoxLayout(url_wrap)
        url_lay.setContentsMargins(0, 0, 4, 0)
        url_lay.setSpacing(4)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Paste or type a video / playlist URL …")
        self.url_input.setClearButtonEnabled(False)

        self.btn_add_inline = QPushButton("ADD")
        self.btn_add_inline.setObjectName("BtnAdd")
        self.btn_add_inline.setCursor(Qt.PointingHandCursor)
        self.btn_add_inline.setEnabled(False)
        self.btn_add_inline.setFixedHeight(34)

        btn_paste = QPushButton("PASTE")
        btn_paste.setObjectName("BtnPaste")
        btn_paste.setCursor(Qt.PointingHandCursor)
        btn_paste.setFixedHeight(34)

        btn_clear = QPushButton("✕")
        btn_clear.setObjectName("BtnClear")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.setFixedSize(28, 34)

        url_lay.addWidget(self.url_input, 1)
        url_lay.addWidget(btn_paste)
        url_lay.addWidget(self.btn_add_inline)
        url_lay.addWidget(btn_clear)
        lay.addWidget(url_wrap, 1)

        # Format selector
        self.format_box = QComboBox()
        self.format_box.setObjectName("FormatBox")
        for k in self.settings.RESOLUTIONS.keys():
            self.format_box.addItem(k)
        lay.addWidget(self.format_box)

        # Action buttons
        self.btn_advanced = QPushButton("ADVANCED")
        self.btn_advanced.setObjectName("BtnTopbar")
        self.btn_advanced.setCursor(Qt.PointingHandCursor)

        btn_settings = QPushButton("SETTINGS")
        btn_settings.setObjectName("BtnTopbar")
        btn_settings.setCursor(Qt.PointingHandCursor)

        btn_help = QPushButton()
        btn_help.setObjectName("BtnTopbar")
        btn_help.setCursor(Qt.PointingHandCursor)
        btn_help.setToolTip("About")
        if self._app_icon:
            btn_help.setIcon(self._app_icon)
            btn_help.setIconSize(QSize(16, 16))
        else:
            btn_help.setText("?")

        lay.addWidget(self.btn_advanced)
        lay.addWidget(btn_settings)
        lay.addWidget(btn_help)

        # Wire
        btn_paste.clicked.connect(self._paste_into_url)
        btn_clear.clicked.connect(self.url_input.clear)
        btn_settings.clicked.connect(self._show_preferences)
        btn_help.clicked.connect(self._show_about)

        return bar

    # ── Queue Pane ───────────────────────────────────────────────────────────
    def _build_queue_pane(self) -> QWidget:
        pane = QWidget()
        pane.setObjectName("QueuePane")
        lay = QVBoxLayout(pane)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("QueueHeader")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(16, 10, 12, 10)
        h_lay.setSpacing(8)

        lbl_queue = QLabel("QUEUE")
        lbl_queue.setObjectName("PaneLabel")
        self.count_chip = QLabel("0")
        self.count_chip.setObjectName("CountBadge")

        self.search_box = QLineEdit()
        self.search_box.setObjectName("SearchBox")
        self.search_box.setPlaceholderText("search…")
        self.search_box.setClearButtonEnabled(True)

        self.sort_combo = QComboBox()
        self.sort_combo.setObjectName("SortBox")
        self.sort_combo.addItems(["Added", "Title", "Status"])
        self.sort_combo.setFixedWidth(80)

        h_lay.addWidget(lbl_queue)
        h_lay.addWidget(self.count_chip)
        h_lay.addStretch(1)
        h_lay.addWidget(self.search_box, 2)
        h_lay.addWidget(self.sort_combo)
        lay.addWidget(header)

        # Empty state
        self.queue_empty_state = QLabel(
            "NO ITEMS IN QUEUE\n\nDrop URLs here or paste above."
        )
        self.queue_empty_state.setObjectName("EmptyState")
        self.queue_empty_state.setAlignment(Qt.AlignCenter)
        self.queue_empty_state.setContentsMargins(24, 32, 24, 32)
        lay.addWidget(self.queue_empty_state)

        # List
        self.queue_list = QListWidget()
        self.queue_list.setObjectName("QueueList")
        self.queue_list.setSpacing(4)
        self.queue_list.setFrameShape(QFrame.NoFrame)
        self.queue_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.queue_list.setUniformItemSizes(False)
        self.queue_list.setDragEnabled(True)
        self.queue_list.setAcceptDrops(True)
        self.queue_list.setDragDropMode(QListWidget.InternalMove)
        self.queue_list.setDefaultDropAction(Qt.MoveAction)
        self.queue_list.setContentsMargins(8, 4, 8, 4)
        lay.addWidget(self.queue_list, 1)

        # Bulk bar
        self.bulk_bar = QFrame()
        self.bulk_bar.setObjectName("BulkBar")
        self.bulk_bar.setFixedHeight(42)
        self.bulk_bar.setVisible(False)
        b_lay = QHBoxLayout(self.bulk_bar)
        b_lay.setContentsMargins(14, 0, 10, 0)
        b_lay.setSpacing(6)

        self.bulk_label = QLabel("0 selected")
        self.bulk_label.setObjectName("BulkLabel")

        btn_rm = QPushButton("REMOVE")
        btn_top = QPushButton("TOP")
        btn_bot = QPushButton("BOTTOM")
        btn_clear_done = QPushButton("CLEAR DONE")
        for b in (btn_rm, btn_top, btn_bot, btn_clear_done):
            b.setObjectName("BulkBtn")
            b.setCursor(Qt.PointingHandCursor)

        b_lay.addWidget(self.bulk_label)
        b_lay.addStretch(1)
        b_lay.addWidget(btn_rm)
        b_lay.addWidget(btn_top)
        b_lay.addWidget(btn_bot)
        b_lay.addWidget(btn_clear_done)
        lay.addWidget(self.bulk_bar)

        # Wire
        self.queue_list.model().rowsMoved.connect(self._on_rows_moved)
        self.queue_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.search_box.textChanged.connect(self._apply_queue_filter)
        self.sort_combo.currentTextChanged.connect(self._apply_queue_sort)
        btn_rm.clicked.connect(self._bulk_remove_selected)
        btn_top.clicked.connect(lambda: self._bulk_move_selected(top=True))
        btn_bot.clicked.connect(lambda: self._bulk_move_selected(bottom=True))
        btn_clear_done.clicked.connect(self._bulk_clear_completed)

        return pane

    # ── Console Pane ─────────────────────────────────────────────────────────
    def _build_console_pane(self) -> QWidget:
        pane = QFrame()
        pane.setObjectName("ConsolePane")
        v = QVBoxLayout(pane)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # Console toolbar
        toolbar = QFrame()
        toolbar.setStyleSheet("background: transparent; border-bottom: 1px solid rgba(255, 255, 255, 15);")
        toolbar.setFixedHeight(42)
        t_lay = QHBoxLayout(toolbar)
        t_lay.setContentsMargins(16, 0, 12, 0)
        t_lay.setSpacing(8)

        lbl_console = QLabel("OUTPUT")
        lbl_console.setObjectName("ConsolePaneLabel")

        self.filter_combo = QComboBox()
        self.filter_combo.setObjectName("FilterBox")
        self.filter_combo.addItems(["All", "Info", "Warning", "Error"])

        btn_copy = QPushButton("COPY")
        btn_copy.setObjectName("ConsoleTool")
        btn_copy.setCursor(Qt.PointingHandCursor)

        btn_clear = QPushButton("CLEAR")
        btn_clear.setObjectName("ConsoleTool")
        btn_clear.setCursor(Qt.PointingHandCursor)

        t_lay.addWidget(lbl_console)
        t_lay.addSpacing(8)
        t_lay.addWidget(self.filter_combo)
        t_lay.addStretch(1)
        t_lay.addWidget(btn_copy)
        t_lay.addWidget(btn_clear)
        v.addWidget(toolbar)

        # Log output
        self.log_output = QTextEdit(readOnly=True)
        self.log_output.setObjectName("Console")
        self.log_output.setUndoRedoEnabled(False)
        self.log_output.document().setMaximumBlockCount(max(1, getattr(self.settings, "MAX_LOG_LINES", MAX_LOG_LINES)))
        self.log_output.setStyleSheet(
            "QTextEdit#Console { background: rgba(5, 5, 15, 200); color: rgba(255, 255, 255, 160); "
            "border: none; border-top: 1px solid rgba(255, 255, 255, 15); "
            "font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace; "
            "font-size: 12px; padding: 16px; }"
        )
        v.addWidget(self.log_output, 1)

        btn_copy.clicked.connect(self._copy_console)
        btn_clear.clicked.connect(self._clear_console)
        self.filter_combo.currentTextChanged.connect(self._render_log)

        return pane

    # ── Bottom Bar ───────────────────────────────────────────────────────────
    def _build_bottom_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("BottomBar")
        bar.setFixedHeight(54)

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 16, 0)
        lay.setSpacing(8)

        # Playback controls
        self.btn_start_queue = QPushButton("▶  START")
        self.btn_start_queue.setObjectName("BtnStart")
        self.btn_start_queue.setCursor(Qt.PointingHandCursor)
        self.btn_start_queue.setFixedHeight(36)

        self.btn_pause_queue = QPushButton("⏸  PAUSE")
        self.btn_pause_queue.setObjectName("BtnPause")
        self.btn_pause_queue.setCursor(Qt.PointingHandCursor)
        self.btn_pause_queue.setEnabled(False)
        self.btn_pause_queue.setFixedHeight(36)

        self.btn_skip = QPushButton("⏭")
        self.btn_skip.setObjectName("BtnSkip")
        self.btn_skip.setCursor(Qt.PointingHandCursor)
        self.btn_skip.setEnabled(False)
        self.btn_skip.setFixedHeight(36)
        self.btn_skip.setToolTip("Skip current item")

        self.btn_stop_all = QPushButton("⏹  STOP")
        self.btn_stop_all.setObjectName("BtnStop")
        self.btn_stop_all.setCursor(Qt.PointingHandCursor)
        self.btn_stop_all.setEnabled(False)
        self.btn_stop_all.setFixedHeight(36)
        self.btn_stop_all.setToolTip("Stop the current download.")

        lay.addWidget(self.btn_start_queue)
        lay.addWidget(self.btn_pause_queue)
        lay.addWidget(self.btn_skip)
        lay.addWidget(self.btn_stop_all)
        lay.addStretch(1)

        # Right cluster
        lbl_after = QLabel("AFTER")
        lbl_after.setObjectName("AfterLabel")

        self.post_action = QComboBox()
        self.post_action.setObjectName("PostActionBox")
        self.post_action.addItems(["Keep", "Shutdown", "Sleep", "Restart", "Close"])
        self.post_action.setCurrentText(self.post_queue_action)

        self.download_path_btn = QPushButton(str(self.settings.DOWNLOADS_DIR))
        self.download_path_btn.setObjectName("PathBtn")
        self.download_path_btn.setCursor(Qt.PointingHandCursor)
        self.download_path_btn.setToolTip("Open download folder")

        lay.addWidget(lbl_after)
        lay.addWidget(self.post_action)
        lay.addSpacing(8)
        lay.addWidget(self.download_path_btn)

        self.post_action.currentTextChanged.connect(self._set_post_queue_action)
        self.download_path_btn.clicked.connect(
            lambda: webbrowser.open(self.settings.DOWNLOADS_DIR.as_uri())
        )

        return bar

    # ════════════════════════════════════════════════════════════════════════
    #  CONNECTIONS / MENU / TITLE FETCH
    # ════════════════════════════════════════════════════════════════════════

    def _setup_connections(self):
        self.url_input.textChanged.connect(self._on_url_text_changed)
        self.url_input.returnPressed.connect(self._add_to_queue)
        self.btn_add_inline.clicked.connect(self._add_to_queue)
        self.btn_start_queue.clicked.connect(self._start_queue)
        self.btn_pause_queue.clicked.connect(self._pause_queue)
        self.btn_advanced.clicked.connect(self._show_advanced_options)
        self.btn_skip.clicked.connect(self._skip_current)
        self.btn_stop_all.clicked.connect(self._stop_all)

    def _setup_menu(self):
        menubar: QMenuBar = self.menuBar()

        m_file = menubar.addMenu("File")
        m_file.addAction("Save Queue As...", self._save_queue_to_disk, "Ctrl+S")
        m_file.addAction("Load Queue...", self._load_queue_from_disk, "Ctrl+O")
        m_file.addSeparator()
        m_file.addAction("Open Download Folder", lambda: webbrowser.open(self.settings.DOWNLOADS_DIR.as_uri()))
        m_file.addSeparator()
        m_file.addAction("Exit", self.close, "Ctrl+Q")

        m_settings = menubar.addMenu("Settings")
        m_settings.addAction("Set Download Folder...", self._set_download_path)
        m_settings.addAction("Set Cookies File...", self._set_cookies_path)
        m_settings.addAction("Preferences...", self._show_preferences, "Ctrl+P")
        m_settings.addSeparator()

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

        m_tools = menubar.addMenu("Tools")
        self.action_crop_covers = m_tools.addAction("Crop Audio Covers Now", self._run_cover_crop_manual)

        m_help = menubar.addMenu("Help")
        m_help.addAction("Check for Updates", self._show_update_manager)
        m_help.addAction("About", self._show_about)

    def _setup_title_fetch_queue(self):
        self.title_queue_thread = QThread(self)
        self.title_queue = TitleFetchQueue(self.settings)
        self.title_queue.moveToThread(self.title_queue_thread)
        self.enqueue_title.connect(self.title_queue.enqueue, Qt.QueuedConnection)
        self.enqueue_titles.connect(self.title_queue.enqueue_many, Qt.QueuedConnection)
        self.title_queue.metadata_fetched.connect(self._on_metadata_fetched, Qt.QueuedConnection)
        self.title_queue.error.connect(self._on_title_error)
        self.title_queue.started_one.connect(self._on_title_started)
        self.title_queue_thread.start()

    # ════════════════════════════════════════════════════════════════════════
    #  THUMBNAIL HELPERS
    # ════════════════════════════════════════════════════════════════════════

    def _thumb_safe_name(self, base_name: str) -> str:
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
        pass

    @Slot(str, str)
    def _on_thumb_finished(self, url: str, path: str):
        try:
            try:
                if url in self._pending_thumb_urls:
                    self._pending_thumb_urls.discard(url)
            except Exception:
                pass
            for i in range(self.queue_list.count()):
                item = self.queue_list.item(i)
                widget = self.queue_list.itemWidget(item)
                if not widget:
                    continue
                w_url = getattr(widget, "url", None) or getattr(widget, "_full_meta_text", None)
                if not w_url:
                    continue
                if w_url == url:
                    if path:
                        try:
                            widget.set_thumbnail_path(path)
                        except Exception:
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

    # ════════════════════════════════════════════════════════════════════════
    #  QUEUE CARD HELPERS
    # ════════════════════════════════════════════════════════════════════════

    def _add_queue_card_to_list(self, url: str, title: str = "", video_id: Optional[str] = None, show_thumbnail: bool = True, status: str = "Pending"):
        try:
            card = QueueCard(title=title or short(url, 80), url=url, status=status, progress=0, show_thumbnail=show_thumbnail)
            try:
                setattr(card, "url", url)
            except Exception:
                pass

            # Add glass shadow to the card
            self._add_glass_shadow(card, blur=16, alpha=60, y=2)

            def _open_in_browser():
                webbrowser.open(url)

            def _copy_url():
                QGuiApplication.clipboard().setText(url)

            def _remove_item():
                for item in self.queue:
                    if item.get("url") == url:
                        self._remove_item_by_id(item)
                        break

            card.set_context_actions([
                ("Open in browser", _open_in_browser),
                ("Copy URL", _copy_url),
                ("Remove", _remove_item),
            ])

            item = QListWidgetItem()
            item.setSizeHint(card.sizeHint())
            item.setData(Qt.UserRole, {"url": url, "title": title or short(url, 80), "status": status})
            self.queue_list.addItem(item)
            self.queue_list.setItemWidget(item, card)

            base_name = video_id or hashlib.sha1(url.encode("utf-8")).hexdigest()
            safe = self._thumb_safe_name(base_name)

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
        try:
            key = url or ""
        except Exception:
            key = url or ""

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

        current_label = self.format_box.currentText()
        chosen_format = self.settings.RESOLUTIONS.get(current_label, "best")

        already_in_queue = any(q.get("url") == key for q in self.queue)

        if not already_in_queue:
            try:
                qitem = {
                    "url": key,
                    "title": title,
                    "video_id": video_id,
                    "thumbnail_url": thumb_url,
                    "format_code": chosen_format,
                    "status": "Pending",
                    "progress": 0,
                    "thumb_path": "",
                    "is_playlist": bool(is_playlist),
                }
                self.queue.append(qitem)
                if list_item is None:
                    self._add_queue_card_to_list(url=key, title=title, video_id=video_id, show_thumbnail=True)
                try:
                    self.count_chip.setText(str(self.queue_list.count()))
                    self.queue_empty_state.setVisible(self.queue_list.count() == 0)
                except Exception:
                    pass
                self.log(f"✅ Added to queue: {short(title, 60)}", AppStyles.INFO_COLOR, "Info")
                try:
                    self._save_queue_permanent()
                except Exception:
                    pass
            except Exception as e:
                self.log(f"Failed to create queue card for {key}: {e}", AppStyles.WARNING_COLOR, "Warning")
                return

        try:
            if list_item is not None:
                data = list_item.data(Qt.UserRole) or {}
                if isinstance(data, dict):
                    data.update({"title": title, "video_id": video_id, "thumbnail_url": thumb_url})
                    list_item.setData(Qt.UserRole, data)
                    widget = self.queue_list.itemWidget(list_item)
                    if widget and hasattr(widget, "set_title"):
                        try:
                            widget.set_title(title)
                        except Exception:
                            pass
                for q in self.queue:
                    if q.get("url") == key:
                        q.update({"title": title, "video_id": video_id, "thumbnail_url": thumb_url})
                        break
        except Exception:
            pass

        try:
            self.count_chip.setText(str(self.queue_list.count()))
            self.queue_empty_state.setVisible(self.queue_list.count() == 0)
            self._apply_queue_filter(self.search_box.text())
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

    # ════════════════════════════════════════════════════════════════════════
    #  STARTUP / LOG HELPERS
    # ════════════════════════════════════════════════════════════════════════

    def _log_startup(self):
        self.log("💡 Welcome to YTGet! Paste a URL to Begin.\n", AppStyles.INFO_COLOR, "Info")
        self.log(f"📂 Download Folder: {self.settings.DOWNLOADS_DIR}\n", AppStyles.INFO_COLOR, "Info")
        self.log(f"🔧 Using FFMPEG from: {self.settings.FFMPEG_PATH.parent}\n", AppStyles.INFO_COLOR, "Info")
        if not self.settings.YT_DLP_PATH.exists():
            self.log("yt-dlp not found in app folder or PATH. Download it via Menu Bar → Help → Check yt-dlp Update.\n", AppStyles.WARNING_COLOR, "Warning")
        if not self.settings.FFMPEG_PATH.exists() or not self.settings.FFPROBE_PATH.exists():
            self.log("ffmpeg/ffprobe not found in app folder or PATH.\n", AppStyles.WARNING_COLOR, "Warning")
        if hasattr(self.settings, "PHANTOMJS_PATH") and self.settings.PHANTOMJS_PATH.exists():
            self.log(f"🔧 PhantomJS available: {self.settings.PHANTOMJS_PATH}\n", AppStyles.INFO_COLOR, "Info")
        else:
            self.log("PhantomJS not found in app folder or PATH.\n", AppStyles.WARNING_COLOR, "Warning")
        try:
            deno_attr = getattr(self.settings, "DENO_PATH", None)
            if deno_attr:
                deno_path = Path(deno_attr)
                if deno_path.exists():
                    self.log(f"🔧 Using Deno from: {deno_path}\n", AppStyles.INFO_COLOR, "Info")
                else:
                    self.log("Deno not found in app folder or PATH.\n", AppStyles.WARNING_COLOR, "Warning")
            else:
                bundled = Path(self.settings.BASE_DIR) / ("deno.exe" if os.name == "nt" else "deno")
                if bundled.exists():
                    self.log(f"🔧 Deno available (bundled): {bundled}\n", AppStyles.INFO_COLOR, "Info")
                else:
                    self.log("Deno not found in app folder or PATH.\n", AppStyles.WARNING_COLOR, "Warning")
        except Exception:
            pass
        try:
            from ytget_gui.workers.spotdl_worker import _find_spotdl
            spotdl_bin = _find_spotdl(self.settings)
            if spotdl_bin is not None:
                self.log(f"🔧 SpotDL available: {spotdl_bin}\n", AppStyles.INFO_COLOR, "Info")
            else:
                self.log(
                    "SpotDL not found in app folder or PATH. "
                    "Spotify downloads will fail. Install with: pip install spotdl\n",
                    AppStyles.WARNING_COLOR, "Warning"
                )
        except Exception:
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

    # ════════════════════════════════════════════════════════════════════════
    #  DRAG & DROP
    # ════════════════════════════════════════════════════════════════════════

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
                self.enqueue_titles.emit(valid)
            event.acceptProposedAction()
        else:
            self.log("⚠️ No valid YouTube URLs detected in drop.\n", AppStyles.WARNING_COLOR, "Warning")
            event.ignore()

    # ════════════════════════════════════════════════════════════════════════
    #  QUEUE / TITLE / THUMBNAILS
    # ════════════════════════════════════════════════════════════════════════

    def _on_url_text_changed(self, text: str):
        self.btn_add_inline.setEnabled(is_supported_url(text))

    def _add_to_queue(self):
        url = self.url_input.text().strip()
        if not is_supported_url(url):
            self.log("⚠️ Invalid or unsupported URL format.\n", AppStyles.WARNING_COLOR, "Warning")
            return
        if any(it.get("url") == url for it in self.queue):
            self.log("ℹ️ Already in queue.\n", AppStyles.INFO_COLOR, "Info")
            self.url_input.clear()
            self.btn_add_inline.setEnabled(False)
            return
        self.url_input.clear()
        self.btn_add_inline.setEnabled(False)
        self._add_queue_card_to_list(url=url, title=short(url, 80), show_thumbnail=True)
        if self.title_queue:
            self.enqueue_title.emit(url)

    @Slot(str)
    def _on_title_started(self, url: str):
        self.log(f"🔎 Fetching title for: {url[:60]}...\n", AppStyles.INFO_COLOR, "Info")

    def _on_title_fetched(self, url: str, title: str):
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
        vid = (it or {}).get("video_id") or ""
        if not vid:
            key = (it.get("url", "").split("v=")[-1].split("&")[0]) or ""
            if not key:
                import hashlib
                key = hashlib.sha1(it.get("url", "").encode("utf-8")).hexdigest()
            return self.thumb_cache_dir / f"{key}.jpg"
        return self.thumb_cache_dir / f"{vid}.jpg"

    # ════════════════════════════════════════════════════════════════════════
    #  QUEUE CONTROL
    # ════════════════════════════════════════════════════════════════════════

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
        self.log("⏸️ Queue paused. Current download will keep running and the next item will wait.\n", AppStyles.INFO_COLOR, "Info")
        self._update_button_states()

    def _skip_current(self):
        if self.is_downloading and self.download_worker:
            self.log("⏭️ Skipping current item...\n", AppStyles.INFO_COLOR, "Info")
            self.download_worker.cancel()

    def _stop_all(self):
        if not self.is_downloading and not self.queue_paused:
            self.log("ℹ️ Nothing to stop.\n", AppStyles.INFO_COLOR, "Info")
            return

        self.log("⏹️ Stopping current download...\n", AppStyles.WARNING_COLOR, "Warning")
        self._stop_all_requested = True
        self.queue_paused = True

        if self.is_downloading and self.download_worker:
            self.download_worker.cancel()
        else:
            self._stop_all_requested = False
            self._update_button_states()

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

        url = self.current_download_item.get("url", "")
        is_spotify = "open.spotify.com" in url

        self.download_thread = QThread()
        if is_spotify:
            self.download_worker = SpotDLWorker(
                self.current_download_item,
                self.settings,
                self.settings.SPOTDL,
            )
        else:
            self.download_worker = DownloadWorker(self.current_download_item, self.settings)

        self.download_worker.moveToThread(self.download_thread)
        self.download_thread.started.connect(self.download_worker.run)
        self.download_worker.log.connect(self.log, Qt.QueuedConnection)
        self.download_worker.error.connect(lambda m: self.log(f"❌ {m}\n", AppStyles.ERROR_COLOR, "Error"))
        if hasattr(self.download_worker, "status"):
            try:
                self.download_worker.status.connect(self._on_download_status)
            except Exception:
                pass
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
        target_url = self.current_download_item.get("url", "")
        for i in range(self.queue_list.count()):
            lw_item = self.queue_list.item(i)
            data = lw_item.data(Qt.UserRole) or {}
            if data.get("url") == target_url:
                data["status"] = status
                lw_item.setData(Qt.UserRole, data)
                w = self.queue_list.itemWidget(lw_item)
                if isinstance(w, QueueCard):
                    w.set_status(status)
                break

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

        if self._stop_all_requested:
            self._stop_all_requested = False
            self._refresh_queue_list()
            self._update_button_states()
            self._update_global_progress_bar()
            self.log("⏹️ Stopped. Queue is paused; remaining items are untouched.\n", AppStyles.WARNING_COLOR, "Info")
            return

        self._refresh_queue_list()
        self._update_button_states()
        self._update_global_progress_bar()
        if not self.queue_paused and self.queue:
            self._download_next()
        elif not self.queue:
            self._on_queue_finished()

    def _update_global_progress_bar(self):
        total = max(1, self._initial_queue_len if self._initial_queue_len else len(self.queue))
        done = (self._initial_queue_len - len(self.queue)) if self._initial_queue_len else 0
        percent = int((done / total) * 100) if total else 0
        self.global_progress.setRange(0, 100)
        self.global_progress.setValue(percent)

    def _on_queue_finished(self):
        self.log(f"🏁 Queue complete! Action: {self.post_queue_action}.\n", AppStyles.SUCCESS_COLOR, "Info")
        self._initial_queue_len = 0
        self._update_global_progress_bar()
        if getattr(self.settings, "CROP_AUDIO_COVERS", False):
            started = self._start_cover_crop_worker(
                on_finished=lambda action=self.post_queue_action: self.post_queue_action_signal.emit(action)
            )
            if not started:
                self.post_queue_action_signal.emit(self.post_queue_action)
        else:
            self.post_queue_action_signal.emit(self.post_queue_action)

    def _run_cover_crop_manual(self):
        self._start_cover_crop_worker()

    def _start_cover_crop_worker(self, on_finished=None) -> bool:
        if self._cover_crop_running:
            self.log("ℹ️ Cover cropping is already running.\n", AppStyles.INFO_COLOR, "Info")
            return False

        self._cover_crop_running = True
        if hasattr(self, "action_crop_covers"):
            self.action_crop_covers.setEnabled(False)

        self.log("🖼️ Cropping audio covers to 1:1. This may take a moment...\n", AppStyles.INFO_COLOR, "Info")
        self.cover_thread = QThread()
        self.cover_worker = CoverCropWorker(self.settings.DOWNLOADS_DIR)
        self.cover_worker.moveToThread(self.cover_thread)
        self.cover_thread.started.connect(self.cover_worker.run)
        self.cover_worker.log.connect(self.log, Qt.QueuedConnection)
        self.cover_worker.finished.connect(self.cover_thread.quit)
        if on_finished is not None:
            self.cover_worker.finished.connect(on_finished, Qt.QueuedConnection)
        self.cover_thread.finished.connect(self.cover_worker.deleteLater)
        self.cover_thread.finished.connect(self.cover_thread.deleteLater)
        self.cover_thread.finished.connect(self._on_cover_crop_thread_finished, Qt.QueuedConnection)
        self.cover_thread.start()
        return True

    def _on_cover_crop_thread_finished(self):
        self.cover_thread = None
        self.cover_worker = None
        self._cover_crop_running = False
        if hasattr(self, "action_crop_covers"):
            self.action_crop_covers.setEnabled(True)

    def _perform_post_queue_action(self, action: str):
        if action == "Keep":
            return
        if action == "Close":
            self.close()
            return
        sysname = platform.system().lower()
        if sysname.startswith("win"):
            plat = "win"
        elif sysname == "darwin":
            plat = "mac"
        else:
            plat = "linux"
        ACTION_COMMANDS: dict[str, dict[str, list[str]]] = {
            "Shutdown": {
                "win": ["shutdown", "/s", "/t", "60"],
                "mac": ["osascript", "-e", 'tell app "System Events" to shut down'],
                "linux": [which("systemctl") or "shutdown", which("systemctl") and "poweroff" or "now"],
            },
            "Sleep": {
                "win": ["powershell", "-Command", "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)"],
                "mac": ["pmset", "sleepnow"],
                "linux": [which("systemctl") or "pm-suspend", which("systemctl") and "suspend" or ""],
            },
            "Restart": {
                "win": ["shutdown", "/r", "/t", "60"],
                "mac": ["osascript", "-e", 'tell app "System Events" to restart'],
                "linux": [which("systemctl") or "shutdown", which("systemctl") and "reboot" or "now"],
            },
        }
        cmds_for_action = ACTION_COMMANDS.get(action)
        if not cmds_for_action:
            self.log(f"⚠️ Unknown post-queue action: {action}\n", AppStyles.WARNING_COLOR, "Warning")
            return
        cmd = cmds_for_action.get(plat)
        if not cmd or not cmd[0]:
            self.log(f"⚠️ Cannot perform '{action}' on this platform ({sysname}).\n", AppStyles.WARNING_COLOR, "Warning")
            return
        try:
            subprocess.run(cmd if isinstance(cmd, list) else [cmd], check=False)
        except Exception as exc:
            self.log(f"❌ Failed to {action.lower()}: {exc}\n", AppStyles.ERROR_COLOR, "Error")

    # ════════════════════════════════════════════════════════════════════════
    #  QUEUE PANE HELPERS
    # ════════════════════════════════════════════════════════════════════════

    def _sync_queue_from_visual(self) -> None:
        pools: Dict[str, "deque[Dict[str, Any]]"] = {}
        for it in self.queue:
            url = it.get("url", "")
            pools.setdefault(url, deque()).append(it)

        new_queue: List[Dict[str, Any]] = []
        for i in range(self.queue_list.count()):
            lw_item = self.queue_list.item(i)
            data = lw_item.data(Qt.UserRole) or {}
            url = data.get("url", "") if isinstance(data, dict) else ""
            pool = pools.get(url)
            if pool:
                new_queue.append(pool.popleft())

        for pool in pools.values():
            while pool:
                new_queue.append(pool.popleft())

        self.queue = new_queue

    def _on_rows_moved(self, src_parent, src_start, src_end, dst_parent, dst_row):
        self._sync_queue_from_visual()

        needs_refresh = False

        if self.is_downloading and self.current_download_item is not None:
            try:
                idx = self.queue.index(self.current_download_item)
            except ValueError:
                idx = -1
            if idx > 0:
                item = self.queue.pop(idx)
                self.queue.insert(0, item)
                needs_refresh = True

        if self.is_downloading and self.queue and self.queue[0] is not self.current_download_item:
            item = self.queue[0]
            if item.get("progress") or item.get("status") not in ("Pending", "Completed", "Error"):
                item["progress"] = 0
                if item.get("status") not in ("Completed", "Error"):
                    item["status"] = "Pending"
                needs_refresh = True

        if needs_refresh:
            self._refresh_queue_list()

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
        count = len(self.queue)
        self.count_chip.setText(str(count))
        self.queue_empty_state.setVisible(count == 0)
        for it in self.queue:
            self._add_queue_card_to_list(
                url=it.get("url", ""),
                title=it.get("title", "(title pending)"),
                video_id=it.get("video_id"),
                show_thumbnail=True,
                status=it.get("status", "Pending"),
            )
        self._apply_queue_filter(self.search_box.text())

    def _make_queue_card_widget(self, item: Dict[str, Any]) -> QWidget:
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
            self._add_glass_shadow(card, blur=16, alpha=60, y=2)
            try:
                card.progress.setVisible(False)
                card.percent_lbl.setVisible(False)
            except Exception:
                pass

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

        frame = QFrame()
        frame.setObjectName("QueueCard")
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)
        thumb = QFrame()
        thumb.setObjectName("Thumb")
        thumb.setFixedSize(120, 68)
        lay.addWidget(thumb)
        mid = QVBoxLayout()
        title_lbl = QLabel(item.get("title", "(title pending)"))
        title_lbl.setObjectName("CardTitle")
        meta_lbl = QLabel(f"{item.get('status','Pending')} · {item.get('format_code','')}")
        meta_lbl.setObjectName("CardMeta")
        mid.addWidget(title_lbl)
        mid.addWidget(meta_lbl)
        mid.addStretch(1)
        lay.addLayout(mid, 1)
        btn_del = QPushButton("Remove")
        btn_del.setObjectName("BulkBtn")
        btn_del.setCursor(Qt.PointingHandCursor)
        btn_del.clicked.connect(lambda: self._remove_item_by_id(item))
        lay.addWidget(btn_del)
        frame.title_lbl = title_lbl
        frame.meta_lbl = meta_lbl
        return frame

    def _remove_item_by_id(self, it: Dict[str, Any]):
        try:
            idx = self.queue.index(it)
        except ValueError:
            return
        if self.is_downloading and self.current_download_item is it and self.download_worker:
            self.download_worker.cancel()
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
        self._sync_queue_from_visual()
        rows = sorted({i.row() for i in self.queue_list.selectedIndexes()}, reverse=True)
        rows = [r for r in rows if 0 <= r < len(self.queue)]
        if not rows:
            return
        if self.is_downloading and rows and 0 in rows and self.download_worker:
            self.download_worker.cancel()
        for r in rows:
            if 0 <= r < len(self.queue):
                it = self.queue[r]
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
        self._sync_queue_from_visual()
        rows = sorted({i.row() for i in self.queue_list.selectedIndexes()})
        rows = [r for r in rows if 0 <= r < len(self.queue)]
        if not rows:
            return
        if self.is_downloading and 0 in rows:
            rows = [r for r in rows if r != 0]
            if not rows:
                return
        items = [self.queue[r] for r in rows]
        for r in reversed(rows):
            self.queue.pop(r)
        if top:
            if self.is_downloading and self.queue:
                for i, it in enumerate(items):
                    it["progress"] = 0
                    if it.get("status") not in ("Completed", "Error"):
                        it["status"] = "Pending"
                self.queue[1:1] = items
            else:
                self.queue = items + self.queue
        elif bottom:
            self.queue.extend(items)
        self._save_queue_permanent()
        self._refresh_queue_list()
        self.queue_list.clearSelection()
        if top:
            if self.is_downloading and len(self.queue) > 1:
                tgt_rows = list(range(1, 1 + len(items)))
            else:
                tgt_rows = list(range(len(items)))
        elif bottom:
            base = len(self.queue) - len(items)
            tgt_rows = list(range(base, base + len(items)))
        else:
            tgt_rows = []
        for r in tgt_rows:
            it = self.queue_list.item(r)
            if it:
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

    # ════════════════════════════════════════════════════════════════════════
    #  UPDATER UI HANDLERS
    # ════════════════════════════════════════════════════════════════════════

    def _show_update_manager(self):
        dlg = UpdateManager(self.settings, self)
        dlg.exec()

    # ════════════════════════════════════════════════════════════════════════
    #  SETTINGS / DIALOGS
    # ════════════════════════════════════════════════════════════════════════

    def _refresh_format_box(self):
        current = self.format_box.currentText() if self.format_box.count() else None
        self.format_box.blockSignals(True)
        self.format_box.clear()
        for k in self.settings.RESOLUTIONS.keys():
            self.format_box.addItem(k)
        if current and current in self.settings.RESOLUTIONS:
            self.format_box.setCurrentText(current)
        elif self.format_box.count():
            self.format_box.setCurrentIndex(0)
        self.format_box.blockSignals(False)

    def _apply_settings_dict(self, cfg: Dict[str, Any]):
        for k, v in (cfg or {}).items():
            if hasattr(self.settings, k):
                try:
                    setattr(self.settings, k, v)
                except Exception:
                    pass

    def _persist_settings(self):
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
            dlg = PreferencesDialog(self, self.settings)
            if dlg.exec():
                if hasattr(dlg, "apply") and callable(getattr(dlg, "apply")):
                    try:
                        dlg.apply()
                    except Exception:
                        pass
                elif hasattr(dlg, "get_settings") and callable(getattr(dlg, "get_settings")):
                    try:
                        new_cfg = dlg.get_settings()
                        self._apply_settings_dict(new_cfg)
                    except Exception:
                        pass
                self._persist_settings()
                self.download_path_btn.setText(str(self.settings.DOWNLOADS_DIR))
                self._refresh_format_box()
                self.log("✅ Preferences saved.\n", AppStyles.SUCCESS_COLOR, "Info")
                self._log_startup()
        except Exception as e:
            QMessageBox.warning(self, "Preferences", f"Couldn't open Preferences:\n{e}")

    def _show_advanced_options(self):
        try:
            dlg = AdvancedOptionsDialog(self, self.settings)
            if dlg.exec():
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
                self._persist_settings()
                self.log("✅ Advanced options applied.\n", AppStyles.SUCCESS_COLOR, "Info")
                if self.settings.CLIP_START and self.settings.CLIP_END:
                    self.log(f"⏱️ Clip: {self.settings.CLIP_START}-{self.settings.CLIP_END}\n", AppStyles.INFO_COLOR, "Info")
                if getattr(self.settings, "PLAYLIST_ITEMS", ""):
                    self.log(f"🎬 Playlist Items: {self.settings.PLAYLIST_ITEMS}\n", AppStyles.INFO_COLOR, "Info")
                if getattr(self.settings, "PLAYLIST_REVERSE", False):
                    self.log("↩️ Playlist Reverse: On\n", AppStyles.INFO_COLOR, "Info")
        except Exception as e:
            QMessageBox.warning(self, "Advanced Options", f"Couldn't open Advanced Options:\n{e}")

    def _show_about(self):        
        dialog = AboutDialog(self.settings, self._app_icon, self)
        dialog.exec()

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
        if self.post_action.currentText() != value:
            self.post_action.setCurrentText(value)
        for k, act in self.post_actions_map.items():
            act.setChecked(k == value)

    def _update_button_states(self):
        has_items = len(self.queue) > 0
        self.btn_start_queue.setEnabled(has_items and (self.queue_paused or not self.is_downloading))
        self.btn_pause_queue.setEnabled(self.is_downloading and not self.queue_paused)
        self.btn_skip.setEnabled(self.is_downloading)
        self.btn_stop_all.setEnabled(self.is_downloading)

    # ════════════════════════════════════════════════════════════════════════
    #  PERSISTENT QUEUE
    # ════════════════════════════════════════════════════════════════════════

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
                self._save_queue_permanent()
            self._refresh_queue_list()
            for it in self.queue:
                tp = it.get("thumb_path")
                if tp and Path(tp).exists():
                    try:
                        url = it.get("url", "")
                        if url:
                            self._pending_thumb_urls.add(url)
                    except Exception:
                        pass
                else:
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
                    for it in self.queue:
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

    # ════════════════════════════════════════════════════════════════════════
    #  WINDOW STATE
    # ════════════════════════════════════════════════════════════════════════

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
        try:
            try:
                if hasattr(self, "thumb_manager") and self.thumb_manager is not None:
                    self.thumb_manager.stop(wait=True)
            except Exception:
                pass
            try:
                if hasattr(self, "_pending_thumb_urls"):
                    self._pending_thumb_urls.clear()
            except Exception:
                pass
            settings = QSettings(self.settings.APP_NAME, self.settings.APP_NAME)
            settings.setValue("main/geometry", self.saveGeometry())
            settings.setValue("main/windowState", self.saveState())
            settings.setValue("main/splitSizes", self.main_split.sizes())
            try:
                settings.sync()
            except Exception:
                pass
            self._save_queue_permanent()
            try:
                if self.download_worker:
                    self.download_worker.cancel()
            except Exception:
                pass
            try:
                if self.spotdl_worker:
                    self.spotdl_worker.cancel()
            except Exception:
                pass                
            try:
                if self.title_queue:
                    self.title_queue.stop()
                if self.title_queue_thread:
                    self.title_queue_thread.quit()
                    self.title_queue_thread.wait(2000)
            except Exception:
                pass
            try:
                if self.cover_thread and self.cover_thread.isRunning():
                    self.cover_thread.quit()
                    self.cover_thread.wait(2000)
            except Exception:
                pass
        except Exception:
            pass
        super().closeEvent(event)
