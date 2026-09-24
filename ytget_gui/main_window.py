# File: ytget_gui/main_window.py
"""Main window: a view over QueueController.

All scheduling, retry policy and worker lifecycle now live in
ytget_gui.queue.controller. This file builds widgets, forwards user intent to
the controller, and renders controller signals.
"""

from __future__ import annotations

import datetime
import logging
import platform
import shutil
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import (
    QRect,
    QSettings,
    QSize,
    Qt,
    QThread,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QGuiApplication,
    QIcon,
    QPixmap,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ytget_gui import _version, formats, naming
from ytget_gui.queue.controller import QueueController
from ytget_gui.queue.model import QueueItem, QueueModel, Status
from ytget_gui.settings import AppSettings
from ytget_gui.styles import AppStyles, Palette
from ytget_gui import autostart
from ytget_gui.scheduler import Scheduler
from ytget_gui.tray import TrayController
from ytget_gui.sites import host_of
from ytget_gui.watcher import ClipboardWatcher
from ytget_gui.theme import main_window_qss
from ytget_gui.utils import opener
from ytget_gui.utils.text import short
from ytget_gui.utils.validators import is_supported_url
from ytget_gui.widgets.queue_card import QueueCard

if TYPE_CHECKING:  # imported lazily at runtime, see _start_cover_crop
    from ytget_gui.workers.cover_crop_worker import CoverCropWorker
from ytget_gui.workers.thumb_fetcher import ThumbManager
from ytget_gui.workers.title_fetch_manager import TitleFetchQueue

log = logging.getLogger(__name__)

_LOG_LEVELS = ("All", "Info", "Warning", "Error")

_POST_ACTIONS = ("Keep", "Shutdown", "Sleep", "Restart", "Close")

# Total budget for closeEvent. Each shutdown step draws from the same deadline
# instead of having its own timeout: the previous revision gave the thumbnail
# manager, the title queue and the cover-crop thread ~2s each, which stacked
# into a window frozen for four or more seconds on exit.
_SHUTDOWN_BUDGET_S = 2.0

# How often the queue is scanned for items still missing their details.
_METADATA_RETRY_TICK_MS = 60_000

# Backoff between metadata retries: 1, 5, 15, 30 minutes, then hourly. A
# rate-limited host stays rate-limited for a while, so retrying tightly only
# extends the block.
_METADATA_BACKOFF_S = (60, 300, 900, 1800, 3600)

# Items retried per tick, so a queue of hundreds cannot fire hundreds of
# yt-dlp calls at once after a long offline spell.
_METADATA_RETRY_BATCH = 5


class MainWindow(QMainWindow):
    # Cross-thread requests into the title-fetch queue, which lives in its own
    # QThread. Direct calls would run the slot on the GUI thread.
    request_fetch = Signal(list)
    request_fetch_cancel = Signal(str)

    def __init__(self, app_icon: Optional[QIcon] = None) -> None:
        super().__init__()
        self.settings = AppSettings()
        self._app_icon = app_icon or self._discover_icon()

        self.model = QueueModel(self.settings.QUEUE_PATH)
        self.controller = QueueController(self.model, self.settings, parent=self)

        self._cards: Dict[str, QListWidgetItem] = {}
        # Lower-cased search text per URL. Rebuilding it for every row on
        # every keystroke made filtering a long queue quadratic.
        self._search_index: Dict[str, str] = {}
        self._pending_fetch: set[str] = set()
        # Retries metadata for items whose fetch failed (typically a
        # rate-limit). Without it a throttled item kept showing its bare URL
        # forever: nothing ever asked for its details again, not even after a
        # restart.
        self._metadata_retry_timer = QTimer(self)
        self._metadata_retry_timer.setInterval(_METADATA_RETRY_TICK_MS)
        self._metadata_retry_timer.timeout.connect(self._retry_missing_metadata)
        # Advanced options waiting to be stamped onto the next items added.
        # They are never written to the shared settings, which is what used
        # to make a clip range apply to every item in the queue.
        self._pending_options: Dict[str, object] = {}
        self._log_entries: List[Tuple[str, str, str]] = []
        self._console_pending: List[Tuple[str, str]] = []

        # Restored from config, so an unattended queue keeps the power action
        # that was chosen last session.
        self._post_queue_action = (
            self.settings.POST_QUEUE_ACTION
            if self.settings.POST_QUEUE_ACTION in _POST_ACTIONS
            else "Keep"
        )
        self._post_action_items: Dict[str, QAction] = {}

        # Set by the tray's Exit action (and by any other deliberate quit) so
        # closeEvent can tell "user wants out" from "user clicked the X while
        # close-to-tray is on".
        self._force_quit = False
        self.tray: Optional[TrayController] = None
        # Guards the modal unlisted-site prompt against re-entry.
        self._unlisted_prompt_open = False
        self.watcher: Optional[ClipboardWatcher] = None

        self._title_thread: Optional[QThread] = None
        self._title_queue: Optional[TitleFetchQueue] = None
        self._cover_thread: Optional[QThread] = None
        self._cover_worker: Optional["CoverCropWorker"] = None
        # Files waiting to be cropped because a crop pass is already busy.
        self._crop_backlog: List[Path] = []
        self._cover_running = False
        self._pending_post_action: Optional[str] = None
        self._normal_geometry: Optional[QRect] = None
        self._was_maximized = False

        self._build_ui()
        self._build_menu()
        self._connect_controller()
        self._start_thumb_manager()
        self._start_title_queue()
        self._restore_geometry()
        self._load_queue()
        # Deferred to the first idle tick: none of this is needed to paint
        # the window, and _log_environment alone shells out to yt-dlp and
        # ffmpeg, which cost most of the old start-up delay.
        QTimer.singleShot(0, self._deferred_startup)

    def _deferred_startup(self) -> None:
        self._start_watcher()
        self._start_scheduler()
        self._apply_tray_settings()
        self._log_environment()

    # ==================================================================
    # Construction
    # ==================================================================

    def _discover_icon(self) -> Optional[QIcon]:
        for root in (self.settings.BASE_DIR, self.settings.INTERNAL_DIR):
            for name in ("icon.ico", "icon.png"):
                candidate = root / name
                if candidate.is_file():
                    return QIcon(str(candidate))
        return None

    def _build_ui(self) -> None:
        self.setWindowTitle(f"{_version.APP_NAME}  \u00b7  {_version.__version__}")
        if self._app_icon is not None:
            self.setWindowIcon(self._app_icon)
        self.resize(1280, 820)
        self.setMinimumSize(940, 620)
        self.setStyleSheet(main_window_qss())
        self.setAcceptDrops(True)

        central = QWidget()
        central.setObjectName("CentralWidget")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_top_bar())

        self.global_progress = QProgressBar()
        self.global_progress.setObjectName("GlobalProgress")
        self.global_progress.setTextVisible(False)
        self.global_progress.setRange(0, 100)
        self.global_progress.setMaximumHeight(3)
        root.addWidget(self.global_progress)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(1)
        self.queue_pane = self._build_queue_pane()
        self.console_pane = self._build_console_pane()
        self.splitter.addWidget(self.queue_pane)
        self.splitter.addWidget(self.console_pane)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 3)
        root.addWidget(self.splitter, 1)

        root.addWidget(self._build_bottom_bar())

        self._console_timer = QTimer(self)
        self._console_timer.setSingleShot(True)
        self._console_timer.setInterval(40)
        self._console_timer.timeout.connect(self._flush_console)

        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(150)
        self._filter_timer.timeout.connect(
            lambda: self._apply_filter(self.search_box.text())
        )

        self._update_buttons()

    # -- top bar -------------------------------------------------------

    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(56)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 16, 0)
        layout.setSpacing(14)

        brand = QWidget()
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(0)
        name = QLabel(_version.APP_NAME.upper())
        name.setObjectName("Brand")
        dot = QLabel("\u00b7")
        dot.setObjectName("BrandDot")
        dot.setContentsMargins(5, 0, 5, 0)
        version = QLabel(f"v{_version.__version__}")
        version.setObjectName("VersionChip")
        brand_layout.addWidget(name, 0, Qt.AlignVCenter)
        brand_layout.addWidget(dot, 0, Qt.AlignVCenter)
        brand_layout.addWidget(version, 0, Qt.AlignVCenter)
        layout.addWidget(brand)

        separator = QFrame()
        separator.setObjectName("Separator")
        separator.setFrameShape(QFrame.VLine)
        separator.setFixedHeight(24)
        layout.addWidget(separator)

        self.url_wrap = QFrame()
        self.url_wrap.setObjectName("UrlWrap")
        url_layout = QHBoxLayout(self.url_wrap)
        url_layout.setContentsMargins(0, 0, 4, 0)
        url_layout.setSpacing(4)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Paste a video, playlist or Spotify URL\u2026")
        self.url_input.setAccessibleName("URL to download")
        self.url_input.textChanged.connect(self._on_url_changed)
        self.url_input.returnPressed.connect(self._add_from_input)

        btn_paste = QPushButton("PASTE")
        btn_paste.setObjectName("BtnPaste")
        btn_paste.setFixedHeight(34)
        btn_paste.setCursor(Qt.PointingHandCursor)
        btn_paste.clicked.connect(self._paste_url)

        self.btn_add = QPushButton("ADD")
        self.btn_add.setObjectName("BtnAdd")
        self.btn_add.setFixedHeight(34)
        self.btn_add.setEnabled(False)
        self.btn_add.setCursor(Qt.PointingHandCursor)
        self.btn_add.clicked.connect(self._add_from_input)

        btn_clear = QPushButton("\u2715")
        btn_clear.setObjectName("BtnClear")
        btn_clear.setFixedSize(28, 34)
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.clicked.connect(self.url_input.clear)

        url_layout.addWidget(self.url_input, 1)
        url_layout.addWidget(btn_paste)
        url_layout.addWidget(self.btn_add)
        url_layout.addWidget(btn_clear)
        layout.addWidget(self.url_wrap, 1)

        self.format_box = QComboBox()
        self.format_box.setObjectName("FormatBox")
        self.format_box.setAccessibleName("Download format")
        self._refresh_format_box()
        layout.addWidget(self.format_box)

        self.btn_advanced = QPushButton("ADVANCED")
        self.btn_advanced.setObjectName("BtnTopbar")
        self.btn_advanced.setCursor(Qt.PointingHandCursor)
        self.btn_advanced.clicked.connect(self._show_advanced)
        self._refresh_advanced_button()

        btn_settings = QPushButton("SETTINGS")
        btn_settings.setObjectName("BtnTopbar")
        btn_settings.setCursor(Qt.PointingHandCursor)
        btn_settings.clicked.connect(self._show_preferences)

        btn_about = QPushButton()
        btn_about.setObjectName("BtnTopbar")
        btn_about.setCursor(Qt.PointingHandCursor)
        btn_about.setToolTip("About")
        btn_about.setAccessibleName("About")
        if self._app_icon is not None:
            btn_about.setIcon(self._app_icon)
            btn_about.setIconSize(QSize(16, 16))
        else:
            btn_about.setText("?")
        btn_about.clicked.connect(self._show_about)

        layout.addWidget(self.btn_advanced)
        layout.addWidget(btn_settings)
        layout.addWidget(btn_about)
        return bar

    # -- queue pane ----------------------------------------------------

    def _build_queue_pane(self) -> QWidget:
        pane = QWidget()
        pane.setObjectName("QueuePane")
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("QueueHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 10, 12, 10)
        header_layout.setSpacing(8)

        label = QLabel("QUEUE")
        label.setObjectName("PaneLabel")
        self.count_badge = QLabel("0")
        self.count_badge.setObjectName("CountBadge")

        self.search_box = QLineEdit()
        self.search_box.setObjectName("SearchBox")
        self.search_box.setPlaceholderText("search\u2026")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setAccessibleName("Filter queue")
        self.search_box.textChanged.connect(lambda _: self._filter_timer.start())

        self.sort_box = QComboBox()
        self.sort_box.setObjectName("SortBox")
        self.sort_box.addItems(["Added", "Title", "Status"])
        self.sort_box.setAccessibleName("Sort queue")
        self.sort_box.currentTextChanged.connect(self.controller.sort_by)

        header_layout.addWidget(label, 0, Qt.AlignVCenter)
        header_layout.addWidget(self.count_badge, 0, Qt.AlignVCenter)
        header_layout.addStretch(1)
        header_layout.addWidget(self.search_box, 2)
        header_layout.addWidget(self.sort_box)
        layout.addWidget(header)

        self.empty_state = QLabel(
            "NOTHING QUEUED\n\nDrop URLs here, or paste one above."
        )
        self.empty_state.setObjectName("EmptyState")
        self.empty_state.setAlignment(Qt.AlignCenter)
        self.empty_state.setContentsMargins(24, 40, 24, 40)
        layout.addWidget(self.empty_state)

        self.queue_list = QListWidget()
        self.queue_list.setObjectName("QueueList")
        self.queue_list.setSpacing(4)
        self.queue_list.setFrameShape(QFrame.NoFrame)
        self.queue_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.queue_list.setUniformItemSizes(False)
        self.queue_list.setDragDropMode(QListWidget.InternalMove)
        self.queue_list.setDefaultDropAction(Qt.MoveAction)
        self.queue_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.queue_list.setAccessibleName("Download queue")
        self.queue_list.model().rowsMoved.connect(self._on_rows_moved)
        self.queue_list.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.queue_list, 1)

        self.bulk_bar = QFrame()
        self.bulk_bar.setObjectName("BulkBar")
        self.bulk_bar.setFixedHeight(42)
        self.bulk_bar.setVisible(False)
        bulk_layout = QHBoxLayout(self.bulk_bar)
        bulk_layout.setContentsMargins(14, 0, 10, 0)
        bulk_layout.setSpacing(6)

        self.bulk_label = QLabel("0 selected")
        self.bulk_label.setObjectName("BulkLabel")
        bulk_layout.addWidget(self.bulk_label)
        bulk_layout.addStretch(1)

        for text, handler in (
            ("REMOVE", self._remove_selected),
            ("TOP", lambda: self._move_selected(to_top=True)),
            ("BOTTOM", lambda: self._move_selected(to_top=False)),
            ("CLEAR DONE", self._clear_completed),
        ):
            button = QPushButton(text)
            button.setObjectName("BulkBtn")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(handler)
            bulk_layout.addWidget(button)

        layout.addWidget(self.bulk_bar)
        return pane

    # -- console -------------------------------------------------------

    def _build_console_pane(self) -> QWidget:
        pane = QFrame()
        pane.setObjectName("ConsolePane")
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QFrame()
        toolbar.setObjectName("ConsoleToolbar")
        toolbar.setFixedHeight(42)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 0, 12, 0)
        toolbar_layout.setSpacing(8)

        label = QLabel("OUTPUT")
        label.setObjectName("ConsolePaneLabel")
        self.filter_box = QComboBox()
        self.filter_box.setObjectName("FilterBox")
        self.filter_box.addItems(_LOG_LEVELS)
        self.filter_box.setAccessibleName("Filter log level")
        self.filter_box.currentTextChanged.connect(lambda _: self._rerender_console())

        btn_copy = QPushButton("COPY")
        btn_copy.setObjectName("ConsoleTool")
        btn_copy.setCursor(Qt.PointingHandCursor)
        btn_copy.clicked.connect(self._copy_console)

        btn_clear = QPushButton("CLEAR")
        btn_clear.setObjectName("ConsoleTool")
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.clicked.connect(self._clear_console)

        toolbar_layout.addWidget(label)
        toolbar_layout.addSpacing(8)
        toolbar_layout.addWidget(self.filter_box)
        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(btn_copy)
        toolbar_layout.addWidget(btn_clear)
        layout.addWidget(toolbar)

        self.console = QTextEdit(readOnly=True)
        self.console.setObjectName("Console")
        self.console.setUndoRedoEnabled(False)
        self.console.setAccessibleName("Output log")
        # Hard cap in the document itself, so even a runaway worker cannot grow
        # the QTextDocument without bound.
        self.console.document().setMaximumBlockCount(
            max(100, int(self.settings.MAX_LOG_LINES))
        )
        layout.addWidget(self.console, 1)
        return pane

    # -- bottom bar ----------------------------------------------------

    def _build_bottom_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("BottomBar")
        bar.setFixedHeight(54)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 16, 0)
        layout.setSpacing(8)

        self.btn_start = QPushButton("\u25b6  START")
        self.btn_start.setObjectName("BtnStart")
        self.btn_start.setFixedHeight(36)
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.clicked.connect(self.controller.start)

        self.btn_pause = QPushButton("\u23f8  PAUSE")
        self.btn_pause.setObjectName("BtnPause")
        self.btn_pause.setFixedHeight(36)
        self.btn_pause.setCursor(Qt.PointingHandCursor)
        self.btn_pause.clicked.connect(self.controller.pause)

        self.btn_skip = QPushButton("\u23ed")
        self.btn_skip.setObjectName("BtnSkip")
        self.btn_skip.setFixedHeight(36)
        self.btn_skip.setToolTip("Skip the current item")
        self.btn_skip.setAccessibleName("Skip current item")
        self.btn_skip.setCursor(Qt.PointingHandCursor)
        self.btn_skip.clicked.connect(self.controller.skip_current)

        self.btn_stop = QPushButton("\u23f9  STOP")
        self.btn_stop.setObjectName("BtnStop")
        self.btn_stop.setFixedHeight(36)
        self.btn_stop.setToolTip("Stop the current download and pause the queue")
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.clicked.connect(self.controller.stop_all)

        for button in (self.btn_start, self.btn_pause, self.btn_skip, self.btn_stop):
            layout.addWidget(button)
        layout.addStretch(1)

        after_label = QLabel("AFTER")
        after_label.setObjectName("AfterLabel")
        self.post_action_box = QComboBox()
        self.post_action_box.setObjectName("PostActionBox")
        self.post_action_box.addItems(_POST_ACTIONS)
        self.post_action_box.setAccessibleName("Action when the queue finishes")
        self.post_action_box.currentTextChanged.connect(self._set_post_action)

        self.path_button = QPushButton(str(self.settings.DOWNLOADS_DIR))
        self.path_button.setObjectName("PathBtn")
        self.path_button.setCursor(Qt.PointingHandCursor)
        self.path_button.setToolTip("Open the download folder")
        self.path_button.clicked.connect(self._open_downloads)

        layout.addWidget(after_label)
        layout.addWidget(self.post_action_box)
        layout.addSpacing(8)
        layout.addWidget(self.path_button)
        return bar

    # -- menu ----------------------------------------------------------

    def _build_menu(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")
        file_menu.addAction("Save Queue As\u2026", self._export_queue, "Ctrl+S")
        file_menu.addAction("Load Queue\u2026", self._import_queue, "Ctrl+O")
        file_menu.addSeparator()
        file_menu.addAction(
            "Import Links from Text File\u2026", self._import_links, "Ctrl+I"
        )
        file_menu.addAction(
            "Export Links to Text File\u2026", self._export_links, "Ctrl+E"
        )
        file_menu.addSeparator()
        file_menu.addAction("Open Download Folder", self._open_downloads)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close, "Ctrl+Q")

        settings_menu = menubar.addMenu("Settings")
        settings_menu.addAction("Set Download Folder\u2026", self._choose_download_dir)
        settings_menu.addAction("Set Cookies File\u2026", self._choose_cookies_file)
        settings_menu.addAction("Preferences\u2026", self._show_preferences, "Ctrl+P")
        settings_menu.addSeparator()

        post_menu = settings_menu.addMenu("When the Queue Finishes\u2026")
        group = QActionGroup(self)
        group.setExclusive(True)
        for label, value in (
            ("Keep Running", "Keep"),
            ("Shut Down", "Shutdown"),
            ("Sleep", "Sleep"),
            ("Restart", "Restart"),
            (f"Close {_version.APP_NAME}", "Close"),
        ):
            action = QAction(label, self, checkable=True)
            action.setChecked(value == self._post_queue_action)
            action.triggered.connect(lambda _c=False, v=value: self._set_post_action(v))
            group.addAction(action)
            post_menu.addAction(action)
            self._post_action_items[value] = action

        tools_menu = menubar.addMenu("Tools")
        self.action_crop = tools_menu.addAction(
            "Crop Audio Covers Now", self._start_cover_crop
        )
        tools_menu.addSeparator()
        self.action_watcher = QAction("Clipboard Watcher", self, checkable=True)
        self.action_watcher.setShortcut("Ctrl+Shift+V")
        self.action_watcher.setToolTip("Queue supported links automatically as you copy them")
        self.action_watcher.toggled.connect(self.set_clipboard_watcher)
        tools_menu.addAction(self.action_watcher)
        tools_menu.addAction("Queue Clipboard Now", self.queue_clipboard_now)

        help_menu = menubar.addMenu("Help")
        help_menu.addAction("Check for Updates\u2026", self._show_updates)
        help_menu.addAction("About", self._show_about)

    # ==================================================================
    # Wiring
    # ==================================================================

    def _connect_controller(self) -> None:
        self.controller.log_message.connect(self._on_worker_log)
        self.controller.item_changed.connect(self._on_item_changed)
        self.controller.item_completed.connect(self._on_item_completed)
        self.controller.queue_changed.connect(self._rebuild_queue_list)
        self.controller.overall_progress.connect(self.global_progress.setValue)
        self.controller.running_changed.connect(lambda _: self._update_buttons())
        self.controller.queue_finished.connect(self._on_queue_finished)
        self.controller.queue_changed.connect(self._refresh_tray)
        self.controller.running_changed.connect(lambda _: self._refresh_tray())
        self.controller.overall_progress.connect(lambda _: self._refresh_tray())

    def _start_thumb_manager(self) -> None:
        self.thumbs = ThumbManager(
            self.settings.thumb_cache_dir, self.settings, max_workers=2, parent=self
        )
        self.thumbs.finished.connect(self._on_thumb_ready, Qt.QueuedConnection)
        self.thumbs.error.connect(self._on_thumb_error, Qt.QueuedConnection)

    def _start_title_queue(self) -> None:
        thread = QThread(self)
        thread.setObjectName("title-fetch")
        queue = TitleFetchQueue(self.settings)
        queue.moveToThread(thread)

        self.request_fetch.connect(queue.enqueue_many, Qt.QueuedConnection)
        self.request_fetch_cancel.connect(queue.cancel, Qt.QueuedConnection)
        queue.metadata_fetched.connect(self._on_metadata, Qt.QueuedConnection)
        queue.error.connect(self._on_metadata_error, Qt.QueuedConnection)
        queue.started_one.connect(self._on_fetch_started, Qt.QueuedConnection)

        thread.start()
        self._title_thread = thread
        self._title_queue = queue

    # ==================================================================
    # Logging
    # ==================================================================

    def log(self, text: str, colour: str = AppStyles.INFO_COLOR, level: str = "Info") -> None:
        if not text:
            return
        level = {"Success": "Info", "Process": "Info", "Warn": "Warning"}.get(
            str(level).capitalize(), str(level).capitalize()
        )
        if level not in _LOG_LEVELS:
            level = "Info"

        added: List[Tuple[str, str, str]] = []
        for raw in str(text).splitlines():
            line = " ".join(raw.split()).strip()
            if line:
                added.append((line, colour, level))
        self._log_entries.extend(added)

        cap = max(100, int(self.settings.MAX_LOG_LINES))
        if len(self._log_entries) > cap:
            del self._log_entries[: len(self._log_entries) - cap]

        selected = self.filter_box.currentText()
        for line, line_colour, line_level in added:
            if selected in ("All", line_level):
                self._queue_console_line(line, line_colour)

    def _on_worker_log(self, text: str, colour: str) -> None:
        if colour == AppStyles.ERROR_COLOR:
            level = "Error"
        elif colour == AppStyles.WARNING_COLOR:
            level = "Warning"
        else:
            level = "Info"
        self.log(text, colour, level)

    def _queue_console_line(self, text: str, colour: str) -> None:
        # Batched: bursty worker output would otherwise cost several widget
        # operations per line. One document edit and one scroll per tick.
        self._console_pending.append((text, colour))
        if not self._console_timer.isActive():
            self._console_timer.start()

    def _flush_console(self) -> None:
        if not self._console_pending:
            return
        pending, self._console_pending = self._console_pending, []

        scrollbar = self.console.verticalScrollBar()
        at_bottom = scrollbar is None or scrollbar.value() >= scrollbar.maximum() - 4

        cursor = self.console.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.console.setUpdatesEnabled(False)
        try:
            for text, colour in pending:
                if cursor.position() != 0:
                    cursor.insertBlock()
                fmt = cursor.charFormat()
                fmt.setForeground(QColor(colour))
                cursor.setCharFormat(fmt)
                cursor.insertText(text)
        finally:
            self.console.setUpdatesEnabled(True)

        if at_bottom:
            # Only auto-scroll when the user was already at the bottom, so
            # reading back through history is not yanked away mid-download.
            self.console.moveCursor(QTextCursor.End)
            self.console.ensureCursorVisible()

    def _rerender_console(self) -> None:
        self._console_timer.stop()
        self._console_pending.clear()
        selected = self.filter_box.currentText()
        self.console.clear()
        for text, colour, level in self._log_entries:
            if selected in ("All", level):
                self._console_pending.append((text, colour))
        self._flush_console()

    def _copy_console(self) -> None:
        QGuiApplication.clipboard().setText(self.console.toPlainText())

    def _clear_console(self) -> None:
        self._log_entries.clear()
        self._rerender_console()

    def _log_environment(self) -> None:
        s = self.settings
        self.log(f"\U0001f4a1 {_version.APP_NAME} {_version.__version__} ready.")
        self.log(f"\U0001f4c2 Downloads: {s.DOWNLOADS_DIR}")

        for label, path, hint in (
            ("yt-dlp", s.YT_DLP_PATH, "Install it via Help \u203a Check for Updates."),
            ("ffmpeg", s.FFMPEG_PATH, "Downloads will fail without it."),
            ("ffprobe", s.FFPROBE_PATH, "Some post-processing needs it."),
        ):
            if Path(path).is_file():
                self.log(f"\U0001f527 {label}: {path}")
            else:
                self.log(f"{label} not found. {hint}", AppStyles.WARNING_COLOR, "Warning")

        if Path(s.DENO_PATH).is_file():
            self.log(f"\U0001f527 deno: {s.DENO_PATH}")

        from ytget_gui.workers.spotdl_worker import _find_spotdl

        spotdl = _find_spotdl(s)
        if spotdl is not None:
            self.log(f"\U0001f527 spotdl: {spotdl}")
        else:
            self.log(
                "spotdl not found; Spotify links will fail. Install with: pip install spotdl",
                AppStyles.WARNING_COLOR,
                "Warning",
            )

        active = self._active_options_summary()
        if active:
            self.log("\u2699\ufe0f Active: " + ", ".join(active))

    def _active_options_summary(self) -> List[str]:
        """One compact line instead of the fifteen-line banner the previous
        revision re-emitted every single time Preferences was saved."""
        s = self.settings
        parts: List[str] = []
        if s.PROXY_URL:
            parts.append(f"proxy {s.PROXY_URL}")
        if s.SPONSORBLOCK_CATEGORIES:
            parts.append(f"sponsorblock {len(s.SPONSORBLOCK_CATEGORIES)}")
        if s.CHAPTERS_MODE != "none":
            parts.append(f"chapters {s.CHAPTERS_MODE}")
        if s.WRITE_SUBS:
            parts.append(f"subs {s.SUB_LANGS}")
        if s.ENABLE_ARCHIVE:
            parts.append("archive")
        if s.AUDIO_NORMALIZE:
            parts.append("normalize")
        if s.ORGANIZE_BY_UPLOADER:
            parts.append("by uploader")
        if s.LIMIT_RATE:
            parts.append(f"limit {s.LIMIT_RATE}")
        if s.CROP_AUDIO_COVERS:
            parts.append("crop covers")
        if self._pending_options:
            parts.append("next item: " + self._describe_options(self._pending_options))
        if s.FILENAME_FORMAT != "default":
            parts.append(f"naming {s.FILENAME_FORMAT}")
        return parts

    # ==================================================================
    # Adding items
    # ==================================================================

    def _on_url_changed(self, text: str) -> None:
        stripped = text.strip()
        valid = is_supported_url(stripped)
        self.btn_add.setEnabled(valid)
        # Only flag as invalid once there is something to judge, so an empty
        # field does not sit there looking like an error.
        self.url_wrap.setProperty("invalid", bool(stripped) and not valid)
        style = self.url_wrap.style()
        style.unpolish(self.url_wrap)
        style.polish(self.url_wrap)

    def _paste_url(self) -> None:
        text = QGuiApplication.clipboard().text().strip()
        if text:
            urls = [line.strip() for line in text.splitlines() if line.strip()]
            if len(urls) > 1:
                self.enqueue_urls(urls)
                return
            self.url_input.setText(text)
            self.url_input.setCursorPosition(len(text))

    def _add_from_input(self) -> None:
        url = self.url_input.text().strip()
        if not is_supported_url(url):
            self.log("Invalid or unsupported URL.", AppStyles.WARNING_COLOR, "Warning")
            return
        if self.enqueue_urls([url]):
            self.url_input.clear()

    def _name_suffix_for(
        self, url: str, code: str, label: str, pending: Sequence[QueueItem]
    ) -> str:
        """Quality tag for this item, or "" when nothing would collide.

        Two formats of one URL only overwrite each other when they share a
        container, so 1080p + 4K (both .mkv) get disambiguated while
        1080p + MP3 both keep the plain default name.
        """
        container = naming.container_key(code, self.settings)
        siblings = [
            item
            for item in list(self.model.items_for_url(url)) + list(pending)
            if item.url == url
            and naming.container_key(item.format_code, self.settings) == container
        ]
        if not siblings:
            return ""
        return naming.suffix_for(
            label, code, [item.name_suffix for item in siblings]
        )

    def enqueue_urls(
        self, urls: Sequence[str], format_label: Optional[str] = None
    ) -> int:
        """Add URLs and start metadata fetches. Returns the number added.

        `format_label` lets the clipboard watcher apply a per-site preset. When
        it is None or unknown, the main window's format box wins, so manual
        additions always behave exactly as before.
        """
        accepted: List[str] = []
        items = []
        seen: set[str] = set()
        label = format_label or self.format_box.currentText()
        if label not in self.settings.RESOLUTIONS:
            label = self.format_box.currentText()
        code = self.settings.RESOLUTIONS.get(label, "best")

        for raw in urls:
            url = (raw or "").strip()
            if not is_supported_url(url):
                continue
            # Same URL in a different format is a new download; only the
            # exact url+format pair counts as a duplicate.
            key = f"{url}\n{code}"
            if self.model.contains(key) or key in seen:
                self.log(
                    f"Already queued as {label}: {short(url, 50)}",
                    AppStyles.INFO_COLOR,
                )
                continue

            # The item enters the model immediately, with the URL standing in for
            # the title. The previous design created a card *without* a backing
            # entry and only added one when metadata arrived, so a failed or
            # in-flight fetch left a card that no removal path could find --
            # unremovable until restart, and silently re-added on refresh.
            item = QueueItem(
                url=url,
                title="",
                format_code=code,
                format_label=label,
                options=dict(self._pending_options),
                name_suffix=self._name_suffix_for(url, code, label, items),
            )
            # Another format of this URL may already have metadata; reuse
            # it so the new row is not blank while the fetch runs.
            twin = next(iter(self.model.items_for_url(url)), None)
            if twin is not None:
                item.title = twin.title
                item.video_id = twin.video_id
                item.thumbnail_url = twin.thumbnail_url
                item.thumb_path = twin.thumb_path
                item.is_playlist = twin.is_playlist
                item.duration = twin.duration
                item.uploader = twin.uploader
            items.append(item)
            seen.add(key)
            accepted.append(url)

        if not accepted:
            return 0

        self.controller.add_items(items)
        # Metadata and thumbnails are per URL, so fetch each URL once even
        # when several formats of it were just queued.
        unique_urls = list(dict.fromkeys(accepted))
        self._pending_fetch.update(unique_urls)
        self.request_fetch.emit(unique_urls)
        for url in unique_urls:
            self.thumbs.enqueue(url)
        self.log(f"\u2795 Queued {len(accepted)} item(s); fetching details\u2026")
        for item in items:
            if item.name_suffix:
                self.log(
                    "Same link already queued in this container \u2014 this one "
                    f"will be saved with \u201c {item.name_suffix}\u201d appended.",
                    AppStyles.INFO_COLOR,
                )
        return len(accepted)

    # ==================================================================
    # Metadata / thumbnails
    # ==================================================================

    @Slot(str)
    def _on_fetch_started(self, url: str) -> None:
        log.debug("Fetching metadata for %s", url)

    @Slot(str, object)
    def _on_metadata(self, url: str, payload: object) -> None:
        self._pending_fetch.discard(url)
        data = payload if isinstance(payload, dict) else {}
        items = self.model.items_for_url(url)
        if not items:
            # Removed while the fetch was in flight; nothing to update.
            return

        title = str(data.get("title") or "")
        video_sizes = data.get("video_sizes") or {}
        audio_size = data.get("audio_size")
        duration = data.get("duration")
        is_playlist = bool(data.get("is_playlist"))

        # One fetch per URL feeds every queued format of that URL.
        for item in items:
            item.title = title or item.title
            item.video_id = str(data.get("video_id") or "")
            item.thumbnail_url = str(data.get("thumb_url") or "")
            item.is_playlist = is_playlist
            item.uploader = str(data.get("uploader") or "")
            item.duration = duration if isinstance(duration, (int, float)) else None
            item.filesize = (
                None
                if is_playlist
                else formats.estimate_download_size(
                    video_sizes, audio_size, item.format_code
                )
            )
            if title:
                # Resolved for good: no later start re-fetches this item.
                item.metadata_ok = True
                item.metadata_attempts = 0
                item.metadata_retry_at = 0.0
                item.last_error = ""
            self._on_item_changed(item.key)
        self.model.save()
        self.log(f"\u2705 {short(items[0].display_title, 60)}")

    @Slot(str, str)
    def _on_metadata_error(self, url: str, message: str) -> None:
        self._pending_fetch.discard(url)
        delay = 0
        for item in self.model.items_for_url(url):
            item.last_error = message
            item.metadata_attempts += 1
            delay = self._metadata_backoff(item)
            item.metadata_retry_at = time.time() + delay
            self._on_item_changed(item.key)
        self.model.save()
        # Non-fatal: the item stays queued and the download may still succeed,
        # since yt-dlp resolves metadata again at download time. The details
        # are asked for again later -- a rate-limit is temporary.
        retry = f" Retrying in {max(1, delay // 60)} min." if delay else ""
        self.log(
            f"Could not fetch details for {short(url, 50)}: "
            f"{short(message, 90)}.{retry}",
            AppStyles.WARNING_COLOR,
            "Warning",
        )

    @Slot(str, str)
    def _on_thumb_ready(self, url: str, path: str) -> None:
        if not path:
            return
        for item in self.model.items_for_url(url):
            item.thumb_path = path
            card = self._card_for(item.key)
            if card is not None:
                card.set_thumbnail_path(path)

    @Slot(str, str)
    def _on_thumb_error(self, url: str, message: str) -> None:
        if self.settings.LOG_THUMBNAILS:
            self.log(
                f"Thumbnail: {short(url, 50)} \u2014 {message}",
                AppStyles.WARNING_COLOR,
                "Warning",
            )

    # ==================================================================
    # Queue list rendering
    # ==================================================================

    def _card_for(self, key: str) -> Optional[QueueCard]:
        list_item = self._cards.get(key)
        if list_item is None:
            return None
        widget = self.queue_list.itemWidget(list_item)
        return widget if isinstance(widget, QueueCard) else None

    def _rebuild_queue_list(self) -> None:
        """Bring the list view in line with the model.

        Adding or removing one item used to destroy and re-create every
        card, which is O(queue) widget churn on each of the many
        queue_changed emissions during a run. The common cases -- rows
        removed, rows appended -- are now patched in place; anything else
        (a reorder) still falls back to a full rebuild.
        """
        self.queue_list.setUpdatesEnabled(False)
        try:
            if not self._sync_rows():
                self._full_rebuild()
        finally:
            self.queue_list.setUpdatesEnabled(True)

        count = len(self.model)
        self.count_badge.setText(str(count))
        self.empty_state.setVisible(count == 0)
        self._apply_filter(self.search_box.text())
        self._update_buttons()

    def _row_keys(self) -> List[str]:
        return [
            self._key_of(self.queue_list.item(row))
            for row in range(self.queue_list.count())
        ]

    def _sync_rows(self) -> bool:
        """Patch the view in place. False means a full rebuild is needed."""
        model_keys = [item.key for item in self.model]
        rows = self._row_keys()
        if rows == model_keys:
            return True

        surviving = set(model_keys)
        kept = [key for key in rows if key in surviving]
        # Only removals and appends can be expressed as row edits; if the
        # remaining rows no longer prefix the model, the order changed.
        if kept != model_keys[: len(kept)]:
            return False

        for row in reversed(range(self.queue_list.count())):
            if self._key_of(self.queue_list.item(row)) not in surviving:
                self._destroy_row(row)

        for key in model_keys[len(kept):]:
            item = self.model.get(key)
            if item is None:
                return False
            self._append_card(item)
        return True

    def _full_rebuild(self) -> None:
        selected = {
            self._key_of(self.queue_list.item(row))
            for row in range(self.queue_list.count())
            if self.queue_list.item(row).isSelected()
        }
        for row in reversed(range(self.queue_list.count())):
            self._destroy_row(row)
        self.queue_list.clear()
        self._cards.clear()
        for item in self.model:
            self._append_card(item)
            if item.key in selected:
                self._cards[item.key].setSelected(True)

    def _destroy_row(self, row: int) -> None:
        """Remove one row and free the card widget it owns.

        takeItem() alone drops the QListWidgetItem but leaves the card (and
        its thumbnail pixmap) parented to the viewport, so the image stayed
        on screen and in memory after the item was removed.
        """
        list_item = self.queue_list.item(row)
        if list_item is None:
            return
        key = self._key_of(list_item)
        widget = self.queue_list.itemWidget(list_item)
        if widget is not None:
            self.queue_list.removeItemWidget(list_item)
            widget.setParent(None)
            widget.deleteLater()
        self.queue_list.takeItem(row)
        if self._cards.get(key) is list_item:
            self._cards.pop(key, None)
        self._search_index.pop(key, None)

    def _append_card(self, item: QueueItem) -> None:
        card = QueueCard(item)
        card.removed.connect(self._remove_key)
        card.open_requested.connect(self._open_output)
        card.reveal_requested.connect(self._reveal_output)

        actions = [
            ("Open in browser", lambda u=item.url: webbrowser.open(u)),
            ("Copy URL", lambda u=item.url: QGuiApplication.clipboard().setText(u)),
            ("View thumbnail", lambda k=item.key: self._view_thumbnail(k)),
        ]
        if item.output_path:
            actions += [
                ("Play file", lambda k=item.key: self._open_output(k)),
                ("Show in folder", lambda k=item.key: self._reveal_output(k)),
                ("Copy file path", lambda k=item.key: self._copy_output_path(k)),
            ]
        actions += [
            ("Retry", lambda k=item.key: self._retry_key(k)),
            ("Remove", lambda k=item.key: self._remove_key(k)),
        ]
        card.set_context_actions(actions)

        list_item = QListWidgetItem()
        list_item.setSizeHint(card.sizeHint())
        list_item.setData(Qt.UserRole, item.key)
        self.queue_list.addItem(list_item)
        self.queue_list.setItemWidget(list_item, card)
        self._cards[item.key] = list_item

        if item.thumb_path and Path(item.thumb_path).is_file():
            card.set_thumbnail_path(item.thumb_path)

    @staticmethod
    def _key_of(list_item: Optional[QListWidgetItem]) -> str:
        if list_item is None:
            return ""
        return str(list_item.data(Qt.UserRole) or "")

    @Slot(str)
    def _on_item_changed(self, key: str) -> None:
        # Title, status and uploader all feed the search text.
        self._search_index.pop(key, None)
        item = self.model.get(key)
        card = self._card_for(key)
        if item is None or card is None:
            return
        card.update_from(item)

    def _selected_keys(self) -> List[str]:
        return [
            key
            for key in (
                self._key_of(self.queue_list.item(row))
                for row in range(self.queue_list.count())
                if self.queue_list.item(row).isSelected()
            )
            if key
        ]

    def _on_selection_changed(self) -> None:
        count = len(self.queue_list.selectedItems())
        self.bulk_bar.setVisible(count > 0)
        self.bulk_label.setText(f"{count} selected")

    def _on_rows_moved(self, *_args) -> None:
        order = [
            self._key_of(self.queue_list.item(row))
            for row in range(self.queue_list.count())
        ]
        self.controller.apply_visual_order([k for k in order if k])

    def _search_text(self, key: str) -> str:
        """Lower-cased searchable text for a row, memoised per item."""
        cached = self._search_index.get(key)
        if cached is not None:
            return cached
        item = self.model.get(key)
        haystack = (
            " ".join(
                filter(
                    None,
                    (
                        item.display_title,
                        item.url,
                        item.status.value,
                        item.uploader,
                        item.format_label,
                    ),
                )
            ).lower()
            if item is not None
            else ""
        )
        self._search_index[key] = haystack
        return haystack

    def _apply_filter(self, text: str) -> None:
        needle = (text or "").strip().lower()
        for row in range(self.queue_list.count()):
            list_item = self.queue_list.item(row)
            if not needle:
                if list_item.isHidden():
                    list_item.setHidden(False)
                continue
            hidden = needle not in self._search_text(self._key_of(list_item))
            if hidden != list_item.isHidden():
                list_item.setHidden(hidden)

    # ==================================================================
    # Queue edits
    # ==================================================================

    def _remove_key(self, key: str) -> None:
        self._drop_keys([key])

    def _remove_selected(self) -> None:
        keys = self._selected_keys()
        if keys:
            self._drop_keys(keys)

    def _drop_keys(self, keys: Sequence[str]) -> None:
        # dict.fromkeys: de-duplicate while keeping the click order, so a
        # repeated row cannot be counted twice in the removal log.
        unique = [key for key in dict.fromkeys(keys) if key]
        if not unique:
            return
        doomed = {id(i) for i in (self.model.get(k) for k in unique) if i is not None}
        for key in unique:
            item = self.model.get(key)
            url = item.url if item is not None else key
            # Another format of the same URL may still be queued; its
            # metadata fetch and thumbnail must survive.
            siblings = [
                i for i in self.model.items_for_url(url) if id(i) not in doomed
            ]
            if not siblings:
                if url in self._pending_fetch:
                    # Cancel the backend fetch too. Without this the fetch
                    # kept running and its success handler re-created the
                    # card the user had just deleted.
                    self.request_fetch_cancel.emit(url)
                    self._pending_fetch.discard(url)
                # Cancel *and* delete the cached image: no card is left, so
                # the file is dead weight, and a fetch finishing a moment
                # later must not leave a thumbnail behind.
                self.thumbs.purge(url, item.thumb_path if item is not None else "")
            self._search_index.pop(key, None)
        removed = self.controller.remove_items(unique)
        if removed:
            self.log(f"\U0001f5d1\ufe0f Removed {removed} item(s).")

    def _retry_key(self, key: str) -> None:
        item = self.model.get(key)
        if item is None:
            return
        item.reset_for_retry()
        item.queue_attempts = 0
        item.last_error = ""
        self.model.save()
        self._on_item_changed(key)
        self.log(f"\u21bb Re-queued {short(item.display_title, 60)}")

    def _move_selected(self, *, to_top: bool) -> None:
        keys = self._selected_keys()
        if keys:
            self.controller.move_selection(keys, to_top=to_top)

    def _clear_completed(self) -> None:
        count = self.controller.clear_completed()
        if count:
            self.log(f"\U0001f9f9 Cleared {count} completed item(s).")

    def _update_buttons(self) -> None:
        running = self.controller.is_running
        self.btn_start.setEnabled(self.controller.can_start)
        self.btn_pause.setEnabled(running and not self.controller.is_paused)
        self.btn_skip.setEnabled(running)
        self.btn_stop.setEnabled(running)
        self._refresh_tray()

    # ==================================================================
    # System tray
    # ==================================================================

    @property
    def post_queue_action(self) -> str:
        return self._post_queue_action

    def set_post_queue_action(self, value: str) -> None:
        """Public entry point used by the tray menu."""
        self._set_post_action(value)

    def _apply_tray_settings(self) -> None:
        """Create or tear down the tray to match TRAY_ENABLED."""
        wanted = bool(self.settings.TRAY_ENABLED)
        if wanted and self.tray is None:
            tray = TrayController(self, self.settings, self._app_icon)
            if not tray.available:
                self.log(
                    "\u2139\ufe0f No system tray is available in this session.",
                    AppStyles.WARNING_COLOR,
                    "Warning",
                )
                return
            self.tray = tray
        elif not wanted and self.tray is not None:
            self.tray.shutdown()
            self.tray = None
            # Without a tray icon a hidden window is unreachable, so it
            # has to come back when the tray is switched off.
            if not self.isVisible():
                self.restore_window()
        self._refresh_tray()

    def _refresh_tray(self) -> None:
        if self.tray is not None:
            self.tray.refresh()

    def _notify(self, title: str, message: str, *, warning: bool = False) -> None:
        if self.tray is not None:
            self.tray.notify(title, message, warning=warning)

    def open_downloads(self) -> None:
        self._open_downloads()

    def show_preferences(self) -> None:
        self.activateWindow()
        self._show_preferences()

    def clear_completed(self) -> None:
        self._clear_completed()

    def quit_application(self) -> None:
        """Exit for real, bypassing close-to-tray."""
        self._force_quit = True
        self.close()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if (
            event.type() == event.Type.WindowStateChange
            and self.isMinimized()
            and self.tray is not None
            and self.settings.TRAY_MINIMIZE_TO_TRAY
        ):
            # Defer: hiding inside the state-change handler confuses some
            # window managers into leaving a ghost taskbar entry.
            QTimer.singleShot(0, self.hide_to_tray)
        self._refresh_tray()

    # ==================================================================
    # Clipboard watcher
    # ==================================================================

    def _start_scheduler(self) -> None:
        self.scheduler = Scheduler(self.settings, parent=self)
        self.scheduler.start_queue.connect(self._on_schedule_start)
        self.scheduler.stop_queue.connect(self._on_schedule_stop)
        self.scheduler.power_action.connect(self._on_schedule_power)
        self.scheduler.message.connect(self._on_watcher_message)
        self.scheduler.apply_settings()

    def _on_schedule_start(self) -> None:
        if self.controller.is_running:
            return
        if not self.controller.can_start:
            self.log(
                "\u23f0 Scheduled start skipped: nothing to download.",
                AppStyles.WARNING_COLOR,
            )
            return
        self.log("\u23f0 Scheduled start.", AppStyles.INFO_COLOR)
        self._notify("Scheduled start", "The queue is starting.")
        self.controller.start()

    def _on_schedule_stop(self) -> None:
        if not self.controller.is_running:
            return
        self.log("\u23f0 Scheduled stop.", AppStyles.INFO_COLOR)
        self._notify("Scheduled stop", "The queue is stopping.")
        self.controller.stop_all()

    def _on_schedule_power(self, action: str) -> None:
        """Deliberately pre-empts an unfinished queue.

        The user asked for the power action to win over the queue, so any
        running download is stopped first and the pending post-queue action
        is cleared to avoid two power commands racing each other.
        """
        self._pending_post_action = None
        if self.controller.is_running:
            self.log(
                "\u23f0 Scheduled " + action.lower() + ": stopping the queue first.",
                AppStyles.WARNING_COLOR,
            )
            self.controller.stop_all()
        self._notify("Scheduled " + action, "Running now.", warning=True)
        # force=True: a scheduled power action is an explicit instruction with
        # a time attached. The post-queue guard ("only when everything
        # completed") silently cancelled every scheduled shutdown/sleep,
        # because a scheduled run almost always has items still pending.
        self._run_post_action(action, force=True)

    def _start_watcher(self) -> None:
        self.watcher = ClipboardWatcher(self.settings, parent=self)
        self.watcher.urls_ready.connect(self._on_watcher_urls)
        self.watcher.unlisted_ready.connect(self._on_watcher_unlisted)
        self.watcher.message.connect(self._on_watcher_message)
        self.watcher.running_changed.connect(self._on_watcher_running)
        if self.settings.CLIPBOARD_WATCHER_ENABLED:
            self.watcher.start(announce=False)
        self._on_watcher_running(self.watcher.is_running)

    def set_clipboard_watcher(self, enabled: bool) -> None:
        if self.watcher is None:
            return
        if enabled == self.watcher.is_running:
            return
        self.watcher.set_enabled(bool(enabled))
        self.settings.save_config()

    def queue_clipboard_now(self) -> None:
        """One-shot capture, independent of whether the watcher is running."""
        from ytget_gui.watcher import extract_urls

        text = QGuiApplication.clipboard().text() if QGuiApplication.clipboard() else ""
        urls = extract_urls(text or "")
        if not urls:
            self.log(
                "Clipboard holds no supported links.", AppStyles.WARNING_COLOR, "Warning"
            )
            return
        added = self.enqueue_urls(urls)
        if added and self.watcher is not None:
            self.watcher.note_urls(urls)

    @Slot(bool)
    def _on_watcher_running(self, running: bool) -> None:
        for action in (getattr(self, "action_watcher", None),):
            if action is not None and action.isChecked() != running:
                action.blockSignals(True)
                action.setChecked(running)
                action.blockSignals(False)
        self._refresh_tray()

    @Slot(str, str)
    def _on_watcher_message(self, text: str, level: str) -> None:
        colour = (
            AppStyles.WARNING_COLOR if level == "Warning" else AppStyles.INFO_COLOR
        )
        self.log(text, colour, level)

    @Slot(list)
    def _on_watcher_urls(self, batch: List[Tuple[str, str]]) -> None:
        """Queue watcher hits, grouped so each format preset is applied once."""
        grouped: Dict[str, List[str]] = {}
        for url, label in batch:
            grouped.setdefault(label or "", []).append(url)

        added = 0
        for label, urls in grouped.items():
            added += self.enqueue_urls(urls, format_label=label or None)
        if not added:
            return

        self.log(
            f"\U0001f4cb Clipboard watcher queued {added} item(s).",
            AppStyles.SUCCESS_COLOR,
        )
        if self.settings.WATCHER_NOTIFY:
            self._notify("YTGet", f"Queued {added} link(s) from the clipboard.")
        if self.settings.WATCHER_AUTO_START and self.controller.can_start:
            self.controller.start()

    @Slot(list)
    def _on_watcher_unlisted(self, batch: List[Tuple[str, str]]) -> None:
        """Confirm links from sites outside the watcher's list.

        Reached only when Preferences \u203a Watcher is set to ask. The hosts
        are listed rather than the raw URLs so a long batch stays readable.
        """
        if not batch:
            return
        if self._unlisted_prompt_open:
            # One dialog at a time: the watcher keeps polling while this
            # one is modal. The links are not remembered, so copying them
            # again asks properly.
            log.debug("Unlisted prompt already open; dropping %d link(s)", len(batch))
            return
        if not self.isVisible():
            # A modal dialog parented to a hidden window can end up with
            # no visible owner, so surface the window first.
            self.restore_window()
        hosts = list(dict.fromkeys(host_of(url) or url for url, _ in batch))
        preview = ", ".join(hosts[:5]) + ("\u2026" if len(hosts) > 5 else "")
        self._unlisted_prompt_open = True
        try:
            answer = QMessageBox.question(
                self,
                "Queue links from an unlisted site?",
                f"{len(batch)} copied link(s) come from sites that are not in "
                f"your watcher list:\n\n{preview}\n\nQueue them?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
        finally:
            self._unlisted_prompt_open = False
        if answer != QMessageBox.Yes:
            self.log(
                f"Skipped {len(batch)} link(s) from unlisted site(s).",
                AppStyles.INFO_COLOR,
            )
            return
        if self.watcher is not None:
            self.watcher.accept_unlisted([url for url, _ in batch])
        self._on_watcher_urls(batch)

    # ==================================================================
    # Drag and drop
    # ==================================================================

    @staticmethod
    def _urls_from_mime(mime) -> List[str]:
        if mime.hasUrls():
            return [u.toString() for u in mime.urls()]
        if mime.hasText():
            return mime.text().split()
        return []

    def _set_drop_active(self, active: bool) -> None:
        self.queue_pane.setProperty("dropActive", active)
        style = self.queue_pane.style()
        style.unpolish(self.queue_pane)
        style.polish(self.queue_pane)

    def dragEnterEvent(self, event) -> None:
        candidates = self._urls_from_mime(event.mimeData())
        if any(is_supported_url(c) for c in candidates):
            event.acceptProposedAction()
            self._set_drop_active(True)
            return
        super().dragEnterEvent(event)

    def dragLeaveEvent(self, event) -> None:
        self._set_drop_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        self._set_drop_active(False)
        candidates = [c for c in self._urls_from_mime(event.mimeData()) if is_supported_url(c)]
        if not candidates:
            self.log("No usable URLs in the drop.", AppStyles.WARNING_COLOR, "Warning")
            event.ignore()
            return
        self.enqueue_urls(candidates)
        event.acceptProposedAction()

    # ==================================================================
    # Dialogs and settings
    # ==================================================================

    def _refresh_format_box(self) -> None:
        current = self.format_box.currentText() if self.format_box.count() else ""
        self.format_box.blockSignals(True)
        self.format_box.clear()
        self.format_box.addItems(self.settings.RESOLUTIONS.keys())
        if current in self.settings.RESOLUTIONS:
            self.format_box.setCurrentText(current)
        self.format_box.blockSignals(False)

    def _show_preferences(self) -> None:
        from ytget_gui.dialogs.preferences import PreferencesDialog

        try:
            dialog = PreferencesDialog(self, self.settings)
        except Exception as exc:  # noqa: BLE001
            log.exception("Preferences failed to open")
            QMessageBox.warning(self, "Preferences", f"Could not open Preferences:\n{exc}")
            return

        if not dialog.exec():
            return

        dialog.apply()
        self.settings.save_config()
        self.path_button.setText(str(self.settings.DOWNLOADS_DIR))
        self.console.document().setMaximumBlockCount(
            max(100, int(self.settings.MAX_LOG_LINES))
        )
        self._refresh_format_box()
        # Watcher and tray are live objects, so Preferences has to be pushed
        # into them rather than waiting for a restart.
        if self.watcher is not None:
            self.watcher.apply_settings()
        self._apply_tray_settings()
        self.scheduler.apply_settings()
        self._apply_autostart()
        self.log("\u2705 Preferences saved.", AppStyles.SUCCESS_COLOR)
        active = self._active_options_summary()
        if active:
            self.log("\u2699\ufe0f Active: " + ", ".join(active))

    def _apply_autostart(self) -> None:
        """Registry/LaunchAgent/XDG entry, best effort.

        A failure here must not block saving Preferences, so it is logged
        rather than raised.
        """
        ok, error = autostart.apply(
            self.settings.RUN_ON_STARTUP,
            minimized=self.settings.STARTUP_MINIMIZED,
            delay=self.settings.STARTUP_DELAY_SECONDS,
        )
        if not ok:
            self.log(
                "\u26a0\ufe0f Could not update the startup entry: " + str(error),
                AppStyles.WARNING_COLOR,
            )

    def _show_advanced(self) -> None:
        from ytget_gui.dialogs.advanced import AdvancedOptionsDialog

        try:
            dialog = AdvancedOptionsDialog(self, self.settings, self._pending_options)
        except Exception as exc:  # noqa: BLE001
            log.exception("Advanced options failed to open")
            QMessageBox.warning(self, "Advanced", f"Could not open Advanced:\n{exc}")
            return
        if dialog.exec():
            self._set_pending_options(dialog.get_options())

    def _set_pending_options(self, options: Dict[str, object]) -> None:
        """Hold Advanced options for the items added next.

        Defaults are dropped so an item only carries what the user actually
        set; an empty dict means "behave exactly like the global settings".
        """
        pending = {
            key: value
            for key, value in options.items()
            if value not in ("", None, False)
        }
        self._pending_options = pending
        self._refresh_advanced_button()
        if pending:
            self.log(
                "\u2705 Advanced options armed: "
                + self._describe_options(pending)
                + " \u2014 applied to the items you add next only.",
                AppStyles.SUCCESS_COLOR,
            )
        else:
            self.log("Advanced options cleared.", AppStyles.INFO_COLOR)

    @staticmethod
    def _describe_options(options: Dict[str, object]) -> str:
        parts: List[str] = []
        start = str(options.get("CLIP_START", "") or "")
        end = str(options.get("CLIP_END", "") or "")
        if start or end:
            parts.append(f"clip {start or '0'}\u2013{end or 'end'}")
        if options.get("PLAYLIST_ITEMS"):
            parts.append(f"items {options['PLAYLIST_ITEMS']}")
        if options.get("PLAYLIST_REVERSE"):
            parts.append("reversed")
        return ", ".join(parts) or "none"

    def _refresh_advanced_button(self) -> None:
        button = getattr(self, "btn_advanced", None)
        if button is None:
            return
        armed = bool(self._pending_options)
        button.setText("ADVANCED \u2022" if armed else "ADVANCED")
        button.setToolTip(
            "Applies to the next items added: "
            + self._describe_options(self._pending_options)
            if armed
            else "Clip extraction and playlist selection for the items you add next"
        )

    def _show_about(self) -> None:
        from ytget_gui.dialogs.about_dialog import AboutDialog

        AboutDialog(self.settings, self._app_icon, self).exec()

    def _show_updates(self) -> None:
        from ytget_gui.dialogs.update_manager import UpdateManager

        UpdateManager(self.settings, self).exec()

    def _choose_download_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select Download Folder", str(self.settings.DOWNLOADS_DIR)
        )
        if not path:
            return
        # set_download_path also recreates the output templates and mkdirs the
        # folder. Assigning DOWNLOADS_DIR directly (as before) left both
        # templates pointing at the old directory.
        self.settings.set_download_path(Path(path))
        self.path_button.setText(str(self.settings.DOWNLOADS_DIR))
        self.log(f"\U0001f4c2 Downloads: {self.settings.DOWNLOADS_DIR}")

    def _choose_cookies_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Cookies File",
            str(self.settings.BASE_DIR),
            "Cookies (*.txt *.json);;All Files (*)",
        )
        if not path:
            return
        self.settings.COOKIES_PATH = Path(path)
        self.settings.save_config()
        self.log(f"\U0001f36a Cookies: {path}")

    def _open_downloads(self) -> None:
        directory = self.settings.DOWNLOADS_DIR
        try:
            directory.mkdir(parents=True, exist_ok=True)
            webbrowser.open(directory.as_uri())
        except OSError as exc:
            self.log(f"Could not open {directory}: {exc}", AppStyles.ERROR_COLOR, "Error")

    def _open_output(self, key: str) -> None:
        item = self.model.get(key)
        if item is None or not item.output_path:
            return

        if item.has_output:
            if opener.open_path(item.output_path):
                return
            self.log(
                f"No application is registered to open {Path(item.output_path).name}.",
                AppStyles.WARNING_COLOR,
                "Warning",
            )
            self._reveal_output(key)
            return

        self._handle_missing_output(item)

    def _reveal_output(self, key: str) -> None:
        item = self.model.get(key)
        if item is None or not item.output_path:
            return
        if item.has_output:
            if not opener.reveal_path(item.output_path):
                self.log(
                    "Could not open a file manager.",
                    AppStyles.WARNING_COLOR,
                    "Warning",
                )
            return
        self._handle_missing_output(item)

    def _handle_missing_output(self, item: QueueItem) -> None:
        """The recorded file is gone. Open the nearest surviving folder and
        forget the path, so the card stops offering to play it."""
        missing = item.output_path
        folder = opener.containing_folder(missing) or (
            self.settings.DOWNLOADS_DIR
            if self.settings.DOWNLOADS_DIR.is_dir()
            else None
        )
        self.log(
            f"{Path(missing).name} is no longer at {Path(missing).parent} "
            "\u2014 it was moved or deleted.",
            AppStyles.WARNING_COLOR,
            "Warning",
        )
        self.controller.forget_output(item.key)
        if folder is not None:
            opener.open_path(folder)

    def _view_thumbnail(self, key: str) -> None:
        """Show the cached thumbnail for one queue item.

        Deliberately forgiving: an item whose thumbnail was never fetched (or
        whose cache file was cleaned up) logs a note and, when possible, asks
        for the image again instead of raising.
        """
        item = self.model.get(key)
        if item is None:
            return

        path = item.thumb_path
        if not (path and Path(path).is_file()):
            self.log(
                f"No thumbnail saved yet for {short(item.display_title, 50)}.",
                AppStyles.WARNING_COLOR,
                "Warning",
            )
            # Ask for it now, so the next attempt has something to show.
            self.thumbs.enqueue(item.url)
            return

        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.log(
                f"The saved thumbnail for {short(item.display_title, 50)} "
                "could not be read.",
                AppStyles.WARNING_COLOR,
                "Warning",
            )
            self.thumbs.enqueue(item.url, force=True)
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(short(item.display_title, 70) or "Thumbnail")
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        if self._app_icon is not None:
            dialog.setWindowIcon(self._app_icon)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        label = QLabel()
        label.setAlignment(Qt.AlignCenter)
        # Bounded so a maxres image cannot open a window larger than the screen.
        screen = self.screen() or QGuiApplication.primaryScreen()
        limit = screen.availableGeometry().size() * 0.8 if screen else QSize(960, 540)
        shown = pixmap
        if pixmap.width() > limit.width() or pixmap.height() > limit.height():
            shown = pixmap.scaled(limit, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        label.setPixmap(shown)
        layout.addWidget(label)

        caption = QLabel(f"{pixmap.width()} x {pixmap.height()}  \u00b7  {path}")
        caption.setObjectName("muted")
        caption.setWordWrap(True)
        caption.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(caption)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        open_btn = buttons.addButton("Open in viewer", QDialogButtonBox.ActionRole)
        open_btn.clicked.connect(lambda: opener.open_path(Path(path)))
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.show()

    def _copy_output_path(self, key: str) -> None:
        item = self.model.get(key)
        if item is not None and item.output_path:
            QGuiApplication.clipboard().setText(item.output_path)

    def _set_post_action(self, value: str) -> None:
        if value not in _POST_ACTIONS:
            return
        self._post_queue_action = value
        if self.post_action_box.currentText() != value:
            self.post_action_box.blockSignals(True)
            self.post_action_box.setCurrentText(value)
            self.post_action_box.blockSignals(False)
        for key, action in self._post_action_items.items():
            action.setChecked(key == value)
        self.settings.POST_QUEUE_ACTION = value
        self.settings.save_config()
        self._refresh_tray()

    # ==================================================================
    # Queue persistence
    # ==================================================================

    def _load_queue(self) -> None:
        count, error = self.model.load()
        if error:
            self.log(error, AppStyles.ERROR_COLOR, "Error")
        self._rebuild_queue_list()
        if count:
            self.log(f"\U0001f4e5 Restored {count} queued item(s).")
        stale: List[str] = []
        for item in self.model:
            if not (item.thumb_path and Path(item.thumb_path).is_file()):
                self.thumbs.enqueue(item.url)
            # Only items whose details were never resolved are fetched again.
            # Keying this off a missing size re-fetched titles that were
            # already on screen after every single start, because plenty of
            # sites never advertise a size at all.
            if self._needs_metadata(item) and item.url not in stale:
                stale.append(item.url)
        if stale:
            # Deferred with the rest of start-up so the window still
            # paints immediately. Only the first batch goes out now; the
            # rest follow on the retry timer, one small batch at a time.
            first = stale[:_METADATA_RETRY_BATCH]
            self._pending_fetch.update(first)
            QTimer.singleShot(0, lambda: self.request_fetch.emit(first))
        self._metadata_retry_timer.start()

    def _needs_metadata(self, item: QueueItem) -> bool:
        """True when this item's details were never successfully fetched."""
        if item.metadata_ok or item.is_terminal:
            return False
        if formats.is_spotify_code(item.format_code):
            return False
        return True

    def _retry_missing_metadata(self) -> None:
        """Re-ask for details that never arrived, with a growing backoff.

        A fetch that failed once (almost always a temporary rate-limit) used
        to be abandoned permanently, leaving a card showing nothing but its
        URL until the user removed and re-added the link.
        """
        now = time.time()
        due: List[str] = []
        for item in self.model:
            if not self._needs_metadata(item):
                continue
            if item.url in self._pending_fetch or item.url in due:
                continue
            if item.metadata_retry_at and item.metadata_retry_at > now:
                continue
            due.append(item.url)
            if len(due) >= _METADATA_RETRY_BATCH:
                break
        if not due:
            return
        # Reserve the next slot up front: a fetch that fails again must not
        # come straight back on the following tick.
        for url in due:
            for item in self.model.items_for_url(url):
                item.metadata_retry_at = now + self._metadata_backoff(item)
        self._pending_fetch.update(due)
        self.request_fetch.emit(due)

    @staticmethod
    def _metadata_backoff(item: QueueItem) -> int:
        index = min(max(0, item.metadata_attempts), len(_METADATA_BACKOFF_S) - 1)
        return _METADATA_BACKOFF_S[index]

    def _export_queue(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Queue As", str(self.settings.QUEUE_PATH), "JSON (*.json)"
        )
        if not path:
            return
        if self.model.save(Path(path)):
            self.log(f"\U0001f4be Queue saved to {path}", AppStyles.SUCCESS_COLOR)
        else:
            self.log("Could not save the queue.", AppStyles.ERROR_COLOR, "Error")

    def _import_queue(self) -> None:
        if self.controller.is_busy:
            QMessageBox.information(self, "Queue busy", "Stop the current download before importing a queue.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Queue", str(self.settings.QUEUE_PATH.parent), "JSON (*.json)"
        )
        if not path:
            return
        incoming = QueueModel()
        count, error = incoming.load(Path(path))
        if error:
            self.log(error, AppStyles.ERROR_COLOR, "Error")
            return
        if self._title_queue is not None:
            for item in self.model:
                self._title_queue.cancel(item.url)
        self.model.replace_all(incoming.items)
        self.model.save()
        self._rebuild_queue_list()
        self.log(f"\U0001f4e5 Loaded {count} item(s) from {path}", AppStyles.SUCCESS_COLOR)
        for item in self.model:
            self.thumbs.enqueue(item.url)

    # ==================================================================
    # Cover cropping / post-queue
    # ==================================================================

    def _on_item_completed(self, key: str) -> None:
        """Crop this item's album art as soon as it finishes downloading.

        Doing it per item means stopping the queue no longer leaves
        already-downloaded audio uncropped, and only the new files are
        touched instead of rescanning the whole downloads folder.
        """
        if not self.settings.CROP_AUDIO_COVERS:
            return
        item = self.model.get(key)
        if item is None:
            return
        paths = self._audio_outputs(item)
        if not paths:
            return
        if self._cover_running:
            # A pass is already running (the manual folder scan, or the
            # previous item). Queue these rather than starting a second
            # thread that could rewrite the same tags concurrently.
            self._crop_backlog.extend(paths)
            return
        self._start_cover_crop(paths)

    def _audio_outputs(self, item: QueueItem) -> List[Path]:
        """Audio files produced by an item, for cover cropping."""
        from ytget_gui.workers.cover_crop_worker import SUPPORTED_SUFFIXES

        raw = (item.output_path or "").strip()
        if not raw:
            return []
        try:
            target = Path(raw)
            if target.is_file():
                files = [target]
            elif target.is_dir():
                # Playlists record their destination folder, not a file.
                files = [p for p in target.rglob("*") if p.is_file()]
            else:
                return []
        except OSError:
            return []
        return [p for p in files if p.suffix.lower() in SUPPORTED_SUFFIXES]

    def _on_queue_finished(self) -> None:
        self.log(
            f"\U0001f3c1 Queue complete. After: {self._post_queue_action}.",
            AppStyles.SUCCESS_COLOR,
        )
        self._update_buttons()

        if self._cover_running or self._crop_backlog:
            # Chain the post-queue action behind the crop pass so a shutdown
            # cannot kill the machine mid-rewrite of a file's tags.
            self._pending_post_action = self._post_queue_action
            return

        self._run_post_action(self._post_queue_action)

    def _start_cover_crop(self, paths: Optional[Sequence[Path]] = None) -> bool:
        """Run a crop pass. With `paths`, only those files are touched."""
        if self._cover_running:
            if paths:
                self._crop_backlog.extend(paths)
                return True
            self.log("\u2139\ufe0f Cover cropping is already running.")
            return False

        self._cover_running = True
        self.action_crop.setEnabled(False)
        if not paths:
            self.log("\U0001f5bc\ufe0f Cropping audio covers to 1:1\u2026")

        from ytget_gui.workers.cover_crop_worker import CoverCropWorker

        thread = QThread(self)
        thread.setObjectName("cover-crop")
        worker = CoverCropWorker(
            self.settings.DOWNLOADS_DIR,
            paths=list(paths) if paths else None,
        )
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.log.connect(self._on_worker_log, Qt.QueuedConnection)
        worker.finished.connect(thread.quit, Qt.QueuedConnection)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_cover_crop_done)

        self._cover_thread = thread
        self._cover_worker = worker
        thread.start()
        return True

    def _on_cover_crop_done(self) -> None:
        self._cover_thread = None
        self._cover_worker = None
        self._cover_running = False
        self.action_crop.setEnabled(True)

        if self._crop_backlog:
            # Items that finished while this pass was running.
            pending, self._crop_backlog = self._crop_backlog, []
            if self._start_cover_crop(pending):
                return

        action, self._pending_post_action = self._pending_post_action, None
        if action is not None:
            self._run_post_action(action)

    def _run_post_action(self, action: str, *, force: bool = False) -> None:
        if action == "Keep":
            return
        if action == "Close":
            QTimer.singleShot(0, self.quit_application)
            return

        if not force and any(item.status is not Status.COMPLETED for item in self.model):
            self.log("Power action cancelled: the queue contains failed, cancelled or unfinished items.", AppStyles.WARNING_COLOR)
            return
        command = self._post_action_command(action)
        if not command:
            self.log(
                f"Cannot {action.lower()} on this platform.",
                AppStyles.WARNING_COLOR,
                "Warning",
            )
            return

        self.log(f"\u23fb {action} requested: {' '.join(command)}", AppStyles.WARNING_COLOR)
        try:
            subprocess.run(command, check=False, timeout=30)
        except (OSError, subprocess.SubprocessError) as exc:
            self.log(f"Could not {action.lower()}: {exc}", AppStyles.ERROR_COLOR, "Error")

    @staticmethod
    def _post_action_command(action: str) -> List[str]:
        system = platform.system().lower()

        if system.startswith("win"):
            commands = {
                "Shutdown": ["shutdown", "/s", "/t", "60"],
                "Restart": ["shutdown", "/r", "/t", "60"],
                "Sleep": [
                    "rundll32.exe",
                    "powrprof.dll,SetSuspendState",
                    "0,1,0",
                ],
            }
            return commands.get(action, [])

        if system == "darwin":
            commands = {
                "Shutdown": ["osascript", "-e", 'tell app "System Events" to shut down'],
                "Restart": ["osascript", "-e", 'tell app "System Events" to restart'],
                "Sleep": ["pmset", "sleepnow"],
            }
            return commands.get(action, [])

        # Linux/BSD. systemctl is preferred; the legacy fallbacks are only used
        # when it is genuinely absent. Every element is checked for truthiness,
        # because the previous revision built ["pm-suspend", ""] and passed an
        # empty argument straight to the shell.
        systemctl = shutil.which("systemctl")
        if systemctl:
            verb = {"Shutdown": "poweroff", "Restart": "reboot", "Sleep": "suspend"}
            return [systemctl, verb[action]] if action in verb else []

        fallbacks = {
            "Shutdown": [shutil.which("shutdown"), "now"],
            "Restart": [shutil.which("reboot")],
            "Sleep": [shutil.which("pm-suspend")],
        }
        command = fallbacks.get(action, [])
        return [c for c in command if c]

    # ==================================================================
    # Plain-text link import / export
    # ==================================================================

    def _import_links(self) -> None:
        """One link per line, optionally "url | Format", reviewed before adding."""
        from ytget_gui.dialogs.link_io import LinkImportDialog, parse_link_file

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Links",
            str(self.settings.DOWNLOADS_DIR),
            "Text files (*.txt *.text *.list *.csv);;All files (*)",
        )
        if not path:
            return

        try:
            # errors="replace": a mojibake character is recoverable, a hard
            # decode failure loses the whole file.
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self.log(f"Could not read {path}: {exc}", AppStyles.ERROR_COLOR, "Error")
            return

        pairs, skipped = parse_link_file(text)
        if not pairs:
            QMessageBox.information(
                self,
                "Import Links",
                "No links found in that file.\n\n"
                "Expected one link per line. Lines starting with # are ignored.",
            )
            return

        dialog = LinkImportDialog(
            self,
            pairs,
            list(self.settings.RESOLUTIONS.keys()),
            self.format_box.currentText(),
            source=Path(path).name,
            already_queued=[item.url for item in self.model.items],  # informational
        )
        if not dialog.exec():
            return

        added = 0
        for label, urls in dialog.grouped().items():
            added += self.enqueue_urls(urls, format_label=label)

        summary = f"\U0001f4c4 Imported {added} link(s) from {Path(path).name}"
        if skipped:
            summary += f" ({skipped} line(s) were not links)"
        self.log(summary, AppStyles.SUCCESS_COLOR if added else AppStyles.WARNING_COLOR)

    def _export_links(self) -> None:
        from ytget_gui.dialogs.link_io import LinkExportDialog

        items = list(self.model.items)
        if not items:
            QMessageBox.information(self, "Export Links", "The queue is empty.")
            return

        selected = set(self._selected_keys())
        counts = {
            "all": len(items),
            "selected": len([i for i in items if i.key in selected]),
            "pending": len([i for i in items if i.status == Status.PENDING]),
            "completed": len([i for i in items if i.status == Status.COMPLETED]),
            "error": len([i for i in items if i.status == Status.ERROR]),
        }

        dialog = LinkExportDialog(self, counts, has_selection=bool(selected))
        if not dialog.exec():
            return

        scope = dialog.scope
        if scope == "selected":
            chosen = [i for i in items if i.key in selected]
        elif scope == "pending":
            chosen = [i for i in items if i.status == Status.PENDING]
        elif scope == "completed":
            chosen = [i for i in items if i.status == Status.COMPLETED]
        elif scope == "error":
            chosen = [i for i in items if i.status == Status.ERROR]
        else:
            chosen = items

        if not chosen:
            QMessageBox.information(
                self, "Export Links", "Nothing matches that selection."
            )
            return

        suggested = str(Path(self.settings.DOWNLOADS_DIR) / "ytget-links.txt")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Links", suggested, "Text files (*.txt);;All files (*)"
        )
        if not path:
            return
        if not Path(path).suffix:
            path += ".txt"

        lines: List[str] = []
        if dialog.include_header:
            stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            lines.append(f"# YTGet links - {len(chosen)} item(s) - {stamp}")
            lines.append("# One link per line. Re-import with File > Import Links.")
        for item in chosen:
            if dialog.include_formats and item.format_label:
                lines.append(f"{item.url} | {item.format_label}")
            else:
                lines.append(item.url)

        try:
            Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError as exc:
            self.log(f"Could not write {path}: {exc}", AppStyles.ERROR_COLOR, "Error")
            return

        self.log(
            f"\U0001f4e4 Exported {len(chosen)} link(s) to {path}",
            AppStyles.SUCCESS_COLOR,
        )

    # ==================================================================
    # Window state / shutdown
    # ==================================================================

    def _remember_geometry(self) -> None:
        """Track the last real windowed geometry.

        Qt only keeps a usable `saveGeometry()` while the window is visible and
        normal. Hiding to the tray (especially via minimise, where the window is
        already minimised by the time changeEvent fires) leaves a zero or
        minimised rect behind, which is why a restored window came back at its
        default size instead of the size it had when it was hidden.
        """
        if not self.isVisible() or self.isMinimized():
            return
        if self.isMaximized() or self.isFullScreen():
            self._was_maximized = True
            return
        self._was_maximized = False
        self._normal_geometry = self.geometry()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._remember_geometry()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self._remember_geometry()

    def restore_window(self) -> None:
        """Bring the window back exactly as it was before hiding to the tray."""
        if self._was_maximized:
            self.showMaximized()
        else:
            # showNormal() first: a hidden-while-minimised window keeps the
            # minimised state flag, and setGeometry() on it is ignored.
            self.showNormal()
            geometry = self._normal_geometry
            if geometry is not None and geometry.isValid():
                self.setGeometry(geometry)
        self.raise_()
        self.activateWindow()
        self._refresh_tray()

    def hide_to_tray(self) -> None:
        """Single entry point so geometry is always captured before hiding."""
        self._remember_geometry()
        self.hide()
        self._refresh_tray()

    def _restore_geometry(self) -> None:
        store = QSettings(_version.ORG_NAME, _version.APP_NAME)
        geometry = store.value("main/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        rect = store.value("main/normalRect")
        if rect:
            try:
                x, y, w, h = (int(v) for v in rect)
                if w > 0 and h > 0:
                    self._normal_geometry = QRect(x, y, w, h)
            except (TypeError, ValueError):
                pass
        self._was_maximized = str(
            store.value("main/maximized", False)
        ).lower() in ("true", "1")
        state = store.value("main/windowState")
        if state:
            self.restoreState(state)
        sizes = store.value("main/splitSizes")
        if sizes:
            try:
                self.splitter.setSizes([int(s) for s in sizes])
            except (TypeError, ValueError):
                pass
        else:
            QTimer.singleShot(
                0,
                lambda: self.splitter.setSizes(
                    [int(self.width() * 0.42), int(self.width() * 0.58)]
                ),
            )

    def _save_geometry(self) -> None:
        store = QSettings(_version.ORG_NAME, _version.APP_NAME)
        store.setValue("main/geometry", self.saveGeometry())
        store.setValue("main/windowState", self.saveState())
        store.setValue("main/splitSizes", self.splitter.sizes())
        geometry = self._normal_geometry
        if geometry is not None and geometry.isValid():
            store.setValue(
                "main/normalRect",
                [
                    geometry.x(),
                    geometry.y(),
                    geometry.width(),
                    geometry.height(),
                ],
            )
        store.setValue("main/maximized", self._was_maximized)
        store.sync()

    def closeEvent(self, event) -> None:
        # Close-to-tray: keep running in the background instead of exiting.
        # Only the tray's Exit action (or a real quit) sets _force_quit.
        if (
            not self._force_quit
            and self.tray is not None
            and self.settings.TRAY_CLOSE_TO_TRAY
        ):
            event.ignore()
            self.hide_to_tray()
            self._notify("YTGet is still running", "Reopen it from the tray icon.")
            return

        if self.controller.is_running and self.settings.CONFIRM_ON_QUIT:
            answer = QMessageBox.question(
                self,
                "Quit?",
                "A download is still running. Stop it and quit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return

        deadline = time.monotonic() + _SHUTDOWN_BUDGET_S

        def remaining_ms() -> int:
            return max(0, int((deadline - time.monotonic()) * 1000))

        self._console_timer.stop()
        self._filter_timer.stop()
        if self.watcher is not None:
            self.watcher.stop(announce=False)

        try:
            self._save_geometry()
        except Exception:  # noqa: BLE001 - never block exit on bookkeeping
            log.debug("Could not save window geometry", exc_info=True)

        self.model.save()

        # Request cancellation everywhere first, then spend the remaining budget
        # waiting. Cancelling and waiting per-subsystem serialises the waits.
        self.thumbs.stop(wait=False)
        if self._title_queue is not None:
            self._title_queue.stop()
        if self._cover_worker is not None:
            self._cover_worker.cancel()
        self.controller.shutdown(timeout_ms=remaining_ms())

        for thread in (self._title_thread, self._cover_thread):
            if thread is not None and thread.isRunning():
                thread.quit()
                thread.wait(remaining_ms())

        live = [t for t in (self.controller.thread, self._title_thread, self._cover_thread)
                if t is not None and t.isRunning()]
        if live:
            event.ignore()
            self.settings.CONFIRM_ON_QUIT = False
            self.setEnabled(False)
            self.setWindowTitle("YTGet — stopping background work…")
            QTimer.singleShot(200, self.close)
            return

        self._metadata_retry_timer.stop()
        # Give the thumbnail pool's plain Python threads a moment to end
        # before Qt tears down its thread-local storage under them, which is
        # what printed "QThreadStorage: entry N destroyed before end of
        # thread" at exit. Bounded by whatever is left of the shutdown budget.
        try:
            self.thumbs.join(timeout=min(1.0, remaining_ms() / 1000))
        except Exception:  # noqa: BLE001 - never block exit on cleanup
            log.debug("Thumbnail pool did not join cleanly", exc_info=True)
        if self.tray is not None:
            self.tray.shutdown()
            self.tray = None
        super().closeEvent(event)
        # Qt only emits lastWindowClosed for a *visible* window, so quitting
        # from the tray while the window was hidden closed nothing the event
        # loop noticed: the process stayed alive, invisible, in Task Manager.
        app = QApplication.instance()
        if app is not None:
            app.quit()
