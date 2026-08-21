# File: ytget_gui/main_window.py
"""Main window: a view over QueueController.

All scheduling, retry policy and worker lifecycle now live in
ytget_gui.queue.controller. This file builds widgets, forwards user intent to
the controller, and renders controller signals.
"""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QSettings, QSize, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QActionGroup, QColor, QGuiApplication, QIcon, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
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

from ytget_gui import _version
from ytget_gui.dialogs.about_dialog import AboutDialog
from ytget_gui.dialogs.advanced import AdvancedOptionsDialog
from ytget_gui.dialogs.preferences import PreferencesDialog
from ytget_gui.dialogs.update_manager import UpdateManager
from ytget_gui.queue.controller import QueueController
from ytget_gui.queue.model import QueueItem, QueueModel, Status
from ytget_gui.settings import AppSettings
from ytget_gui.styles import AppStyles, Palette
from ytget_gui.theme import main_window_qss
from ytget_gui.utils import opener
from ytget_gui.utils.text import short
from ytget_gui.utils.validators import is_supported_url
from ytget_gui.widgets.queue_card import QueueCard
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
        self._pending_fetch: set[str] = set()
        self._log_entries: List[Tuple[str, str, str]] = []
        self._console_pending: List[Tuple[str, str]] = []

        self._post_queue_action = "Keep"
        self._post_action_items: Dict[str, QAction] = {}

        self._title_thread: Optional[QThread] = None
        self._title_queue: Optional[TitleFetchQueue] = None
        self._cover_thread: Optional[QThread] = None
        self._cover_worker: Optional[CoverCropWorker] = None
        self._cover_running = False
        self._pending_post_action: Optional[str] = None

        self._build_ui()
        self._build_menu()
        self._connect_controller()
        self._start_thumb_manager()
        self._start_title_queue()
        self._restore_geometry()
        self._load_queue()
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

        help_menu = menubar.addMenu("Help")
        help_menu.addAction("Check for Updates\u2026", self._show_updates)
        help_menu.addAction("About", self._show_about)

    # ==================================================================
    # Wiring
    # ==================================================================

    def _connect_controller(self) -> None:
        self.controller.log_message.connect(self._on_worker_log)
        self.controller.item_changed.connect(self._on_item_changed)
        self.controller.queue_changed.connect(self._rebuild_queue_list)
        self.controller.overall_progress.connect(self.global_progress.setValue)
        self.controller.running_changed.connect(lambda _: self._update_buttons())
        self.controller.queue_finished.connect(self._on_queue_finished)

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
        if s.CLIP_START and s.CLIP_END:
            parts.append(f"clip {s.CLIP_START}\u2013{s.CLIP_END}")
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
            self.url_input.setText(text)
            self.url_input.setCursorPosition(len(text))

    def _add_from_input(self) -> None:
        url = self.url_input.text().strip()
        if not is_supported_url(url):
            self.log("Invalid or unsupported URL.", AppStyles.WARNING_COLOR, "Warning")
            return
        if self.enqueue_urls([url]):
            self.url_input.clear()

    def enqueue_urls(self, urls: Sequence[str]) -> int:
        """Add URLs and start metadata fetches. Returns the number added."""
        accepted: List[str] = []
        label = self.format_box.currentText()
        code = self.settings.RESOLUTIONS.get(label, "best")

        for raw in urls:
            url = (raw or "").strip()
            if not is_supported_url(url):
                continue
            if self.model.contains(url):
                self.log(f"Already queued: {short(url, 60)}", AppStyles.INFO_COLOR)
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
            )
            if self.controller.add_item(item):
                accepted.append(url)

        if not accepted:
            return 0

        self._pending_fetch.update(accepted)
        self.request_fetch.emit(accepted)
        for url in accepted:
            self.thumbs.enqueue(url)
        self.log(f"\u2795 Queued {len(accepted)} item(s); fetching details\u2026")
        return len(accepted)

    # ==================================================================
    # Metadata / thumbnails
    # ==================================================================

    @Slot(str)
    def _on_fetch_started(self, url: str) -> None:
        log.debug("Fetching metadata for %s", url)

    @Slot(str, str, str, str, bool)
    def _on_metadata(
        self, url: str, title: str, video_id: str, thumb_url: str, is_playlist: bool
    ) -> None:
        self._pending_fetch.discard(url)
        item = self.model.get(url)
        if item is None:
            # Removed while the fetch was in flight; nothing to update.
            return

        item.title = title or item.title
        item.video_id = video_id
        item.thumbnail_url = thumb_url
        item.is_playlist = is_playlist
        self.model.save()
        self._on_item_changed(url)
        self.log(f"\u2705 {short(item.display_title, 60)}")

    @Slot(str, str)
    def _on_metadata_error(self, url: str, message: str) -> None:
        self._pending_fetch.discard(url)
        item = self.model.get(url)
        if item is not None:
            item.last_error = message
            self._on_item_changed(url)
        # Non-fatal: the item stays queued and the download may still succeed,
        # since yt-dlp resolves metadata again at download time.
        self.log(
            f"Could not fetch details for {short(url, 50)}: {short(message, 90)}",
            AppStyles.WARNING_COLOR,
            "Warning",
        )

    @Slot(str, str)
    def _on_thumb_ready(self, url: str, path: str) -> None:
        if not path:
            return
        item = self.model.get(url)
        if item is None:
            return
        item.thumb_path = path
        card = self._card_for(url)
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

    def _card_for(self, url: str) -> Optional[QueueCard]:
        list_item = self._cards.get(url)
        if list_item is None:
            return None
        widget = self.queue_list.itemWidget(list_item)
        return widget if isinstance(widget, QueueCard) else None

    def _rebuild_queue_list(self) -> None:
        selected = {
            self._url_of(self.queue_list.item(row))
            for row in range(self.queue_list.count())
            if self.queue_list.item(row).isSelected()
        }

        # Suppressing updates collapses N layout+repaint cycles into one; each
        # card carries its own hover shadow, so an unsuppressed rebuild of a
        # long queue is visibly janky.
        self.queue_list.setUpdatesEnabled(False)
        try:
            self.queue_list.clear()
            self._cards.clear()
            for item in self.model:
                self._append_card(item)
                if item.url in selected:
                    self._cards[item.url].setSelected(True)
        finally:
            self.queue_list.setUpdatesEnabled(True)

        self.count_badge.setText(str(len(self.model)))
        self.empty_state.setVisible(len(self.model) == 0)
        self._apply_filter(self.search_box.text())
        self._update_buttons()

    def _append_card(self, item: QueueItem) -> None:
        card = QueueCard(item)
        card.removed.connect(self._remove_url)
        card.open_requested.connect(self._open_output)
        card.reveal_requested.connect(self._reveal_output)

        actions = [
            ("Open in browser", lambda u=item.url: webbrowser.open(u)),
            ("Copy URL", lambda u=item.url: QGuiApplication.clipboard().setText(u)),
        ]
        if item.output_path:
            actions += [
                ("Play file", lambda u=item.url: self._open_output(u)),
                ("Show in folder", lambda u=item.url: self._reveal_output(u)),
                ("Copy file path", lambda u=item.url: self._copy_output_path(u)),
            ]
        actions += [
            ("Retry", lambda u=item.url: self._retry_url(u)),
            ("Remove", lambda u=item.url: self._remove_url(u)),
        ]
        card.set_context_actions(actions)

        list_item = QListWidgetItem()
        list_item.setSizeHint(card.sizeHint())
        list_item.setData(Qt.UserRole, item.url)
        self.queue_list.addItem(list_item)
        self.queue_list.setItemWidget(list_item, card)
        self._cards[item.url] = list_item

        if item.thumb_path and Path(item.thumb_path).is_file():
            card.set_thumbnail_path(item.thumb_path)

    @staticmethod
    def _url_of(list_item: Optional[QListWidgetItem]) -> str:
        if list_item is None:
            return ""
        return str(list_item.data(Qt.UserRole) or "")

    @Slot(str)
    def _on_item_changed(self, url: str) -> None:
        item = self.model.get(url)
        card = self._card_for(url)
        if item is None or card is None:
            return
        card.update_from(item)

    def _selected_urls(self) -> List[str]:
        return [
            url
            for url in (
                self._url_of(self.queue_list.item(row))
                for row in range(self.queue_list.count())
                if self.queue_list.item(row).isSelected()
            )
            if url
        ]

    def _on_selection_changed(self) -> None:
        count = len(self.queue_list.selectedItems())
        self.bulk_bar.setVisible(count > 0)
        self.bulk_label.setText(f"{count} selected")

    def _on_rows_moved(self, *_args) -> None:
        order = [
            self._url_of(self.queue_list.item(row))
            for row in range(self.queue_list.count())
        ]
        self.controller.apply_visual_order([u for u in order if u])

    def _apply_filter(self, text: str) -> None:
        needle = (text or "").strip().lower()
        for row in range(self.queue_list.count()):
            list_item = self.queue_list.item(row)
            if not needle:
                list_item.setHidden(False)
                continue
            item = self.model.get(self._url_of(list_item))
            haystack = " ".join(
                filter(
                    None,
                    (
                        item.display_title if item else "",
                        item.url if item else "",
                        item.status.value if item else "",
                        item.uploader if item else "",
                    ),
                )
            ).lower()
            list_item.setHidden(needle not in haystack)

    # ==================================================================
    # Queue edits
    # ==================================================================

    def _remove_url(self, url: str) -> None:
        self._drop_urls([url])

    def _remove_selected(self) -> None:
        urls = self._selected_urls()
        if urls:
            self._drop_urls(urls)

    def _drop_urls(self, urls: Sequence[str]) -> None:
        for url in urls:
            if url in self._pending_fetch:
                # Cancel the backend fetch too. Without this the fetch kept
                # running and its success handler re-created the card the user
                # had just deleted.
                self.request_fetch_cancel.emit(url)
                self._pending_fetch.discard(url)
            self.thumbs.cancel(url)
        removed = self.controller.remove_items(list(urls))
        if removed:
            self.log(f"\U0001f5d1\ufe0f Removed {removed} item(s).")

    def _retry_url(self, url: str) -> None:
        item = self.model.get(url)
        if item is None:
            return
        item.reset_for_retry()
        item.queue_attempts = 0
        item.last_error = ""
        self.model.save()
        self._on_item_changed(url)
        self.log(f"\u21bb Re-queued {short(item.display_title, 60)}")

    def _move_selected(self, *, to_top: bool) -> None:
        urls = self._selected_urls()
        if urls:
            self.controller.move_selection(urls, to_top=to_top)

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
        self.log("\u2705 Preferences saved.", AppStyles.SUCCESS_COLOR)
        active = self._active_options_summary()
        if active:
            self.log("\u2699\ufe0f Active: " + ", ".join(active))

    def _show_advanced(self) -> None:
        try:
            dialog = AdvancedOptionsDialog(self, self.settings)
        except Exception as exc:  # noqa: BLE001
            log.exception("Advanced options failed to open")
            QMessageBox.warning(self, "Advanced", f"Could not open Advanced:\n{exc}")
            return
        if dialog.exec():
            self.settings.apply(dialog.get_options())
            self.settings.save_config()
            self.log("\u2705 Advanced options applied.", AppStyles.SUCCESS_COLOR)

    def _show_about(self) -> None:
        AboutDialog(self.settings, self._app_icon, self).exec()

    def _show_updates(self) -> None:
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

    def _open_output(self, url: str) -> None:
        item = self.model.get(url)
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
            self._reveal_output(url)
            return

        self._handle_missing_output(item)

    def _reveal_output(self, url: str) -> None:
        item = self.model.get(url)
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
        self.controller.forget_output(item.url)
        if folder is not None:
            opener.open_path(folder)

    def _copy_output_path(self, url: str) -> None:
        item = self.model.get(url)
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
        for item in self.model:
            if not (item.thumb_path and Path(item.thumb_path).is_file()):
                self.thumbs.enqueue(item.url)

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
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Queue", str(self.settings.QUEUE_PATH.parent), "JSON (*.json)"
        )
        if not path:
            return
        count, error = self.model.load(Path(path))
        if error:
            self.log(error, AppStyles.ERROR_COLOR, "Error")
            return
        self.model.save()
        self._rebuild_queue_list()
        self.log(f"\U0001f4e5 Loaded {count} item(s) from {path}", AppStyles.SUCCESS_COLOR)
        for item in self.model:
            self.thumbs.enqueue(item.url)

    # ==================================================================
    # Cover cropping / post-queue
    # ==================================================================

    def _on_queue_finished(self) -> None:
        self.log(
            f"\U0001f3c1 Queue complete. After: {self._post_queue_action}.",
            AppStyles.SUCCESS_COLOR,
        )
        self._update_buttons()

        if self.settings.CROP_AUDIO_COVERS:
            # Chain the post-queue action behind the crop pass so a shutdown
            # cannot kill the machine mid-rewrite of a file's tags.
            self._pending_post_action = self._post_queue_action
            if self._start_cover_crop():
                return
            self._pending_post_action = None

        self._run_post_action(self._post_queue_action)

    def _start_cover_crop(self) -> bool:
        if self._cover_running:
            self.log("\u2139\ufe0f Cover cropping is already running.")
            return False

        self._cover_running = True
        self.action_crop.setEnabled(False)
        self.log("\U0001f5bc\ufe0f Cropping audio covers to 1:1\u2026")

        thread = QThread(self)
        thread.setObjectName("cover-crop")
        worker = CoverCropWorker(self.settings.DOWNLOADS_DIR)
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

        action, self._pending_post_action = self._pending_post_action, None
        if action is not None:
            self._run_post_action(action)

    def _run_post_action(self, action: str) -> None:
        if action == "Keep":
            return
        if action == "Close":
            QTimer.singleShot(0, self.close)
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
    # Window state / shutdown
    # ==================================================================

    def _restore_geometry(self) -> None:
        store = QSettings(_version.ORG_NAME, _version.APP_NAME)
        geometry = store.value("main/geometry")
        if geometry:
            self.restoreGeometry(geometry)
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
        store.sync()

    def closeEvent(self, event) -> None:
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

        super().closeEvent(event)
