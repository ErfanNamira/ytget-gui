# -*- coding: utf-8 -*-
"""
YTGet: A modern YouTube downloader with a graphical interface powered by yt-dlp and PySide6.
Supports packaging as a standalone executable with embedded ffmpeg and cookie support.
"""

import sys
import os
import json
import re
import subprocess
import webbrowser
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

# Third-party imports
import requests
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLineEdit, QTextEdit, QListWidget, QListWidgetItem, QLabel, QFileDialog,
    QComboBox, QMessageBox, QToolButton, QSpacerItem, QSizePolicy, QMenuBar,
    QMenu, QStyle, QSplitter
)
from PySide6.QtGui import QAction, QColor, QTextCharFormat, QIcon, QActionGroup, QTextCursor
from PySide6.QtCore import Qt, QThread, Signal, QObject, QProcess, QTimer

def get_base_path() -> Path:
    """Get the base path whether running as script or frozen exe"""
    if getattr(sys, 'frozen', False):
        # Running as bundled exe
        return Path(sys._MEIPASS)
    return Path(__file__).parent.resolve()

# --- Configuration & Styling ---
@dataclass
class AppSettings:
    """Holds all application settings and constants."""
    VERSION: str = "2.1.0"
    APP_NAME: str = "YTGet"
    GITHUB_URL: str = "https://github.com/ErfanNamira/YTGet"

    # Paths - Changed to use working directory's Downloads folder
    BASE_DIR: Path = field(default_factory=get_base_path)
    INTERNAL_DIR: Path = field(init=False)  
    DOWNLOADS_DIR: Path = field(init=False)  
    COOKIES_PATH: Path = field(init=False)  
    FFMPEG_PATH: Path = field(init=False)   
    FFPROBE_PATH: Path = field(init=False)  

    # yt-dlp templates
    OUTPUT_TEMPLATE: str = field(init=False)
    PLAYLIST_TEMPLATE: str = field(init=False)

    # URL Pattern
    YOUTUBE_URL_PATTERN: re.Pattern = field(default_factory=lambda: re.compile(
        r"^(https?://)?(www\.|m\.)?(youtube\.com|youtu\.be)/.+", re.IGNORECASE
    ))

    # Resolutions - Updated with resolution fallback support
    RESOLUTIONS: Dict[str, str] = field(default_factory=lambda: {
        "🎬 2160p (4K)": "251+313/bestvideo[height<=2160]+bestaudio",
        "🎬 1440p (QHD)": "251+271/bestvideo[height<=1440]+bestaudio",
        "🎬 1080p (FHD)": "251+248/bestvideo[height<=1080]+bestaudio",
        "🎬 720p (HD)": "251+247/bestvideo[height<=720]+bestaudio",
        "🎬 480p (SD)": "251+244/bestvideo[height<=480]+bestaudio",
        "🎵 Audio Only (MP3)": "bestaudio",
        "🎵 Playlist (MP3)": "playlist_mp3"
    })

    def __post_init__(self):
        """Initialize paths and create required directories."""
        # Initialize paths
        self.INTERNAL_DIR = self.BASE_DIR / "_internal"
        self.DOWNLOADS_DIR = Path(os.path.join(os.getcwd(), "Downloads"))
        self.COOKIES_PATH = self.BASE_DIR / "cookies.txt"
        self.FFMPEG_PATH = self.BASE_DIR / "ffmpeg.exe"
        self.FFPROBE_PATH = self.BASE_DIR / "ffprobe.exe"
        
        # Initialize templates
        self.OUTPUT_TEMPLATE = str(self.DOWNLOADS_DIR / "%(title)s.%(ext)s")
        self.PLAYLIST_TEMPLATE = str(self.DOWNLOADS_DIR / "%(playlist_index)s - %(title)s.%(ext)s")

        # Create required directories and files
        self.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        self.INTERNAL_DIR.mkdir(parents=True, exist_ok=True)
        
        # Create empty cookies file if it doesn't exist
        if not self.COOKIES_PATH.exists():
            self.COOKIES_PATH.touch()
            
        # Verify ffmpeg and ffprobe exist
        if not self.FFMPEG_PATH.exists():
            raise FileNotFoundError(f"ffmpeg.exe not found at {self.FFMPEG_PATH}")
        if not self.FFPROBE_PATH.exists():
            raise FileNotFoundError(f"ffprobe.exe not found at {self.FFPROBE_PATH}")

    def set_download_path(self, path: Path):
        """Updates the download path and templates."""
        self.DOWNLOADS_DIR = path
        self.OUTPUT_TEMPLATE = str(self.DOWNLOADS_DIR / "%(title)s.%(ext)s")
        self.PLAYLIST_TEMPLATE = str(self.DOWNLOADS_DIR / "%(playlist_index)s - %(title)s.%(ext)s")

class AppStyles:
    """Centralized stylesheet and color definitions."""
    WINDOW_BG = "#1e1e1e"
    WIDGET_BG = "#2e2e2e"
    TEXT_COLOR = "#e0e0e0"
    PRIMARY_ACCENT = "#e91e63"
    SUCCESS_COLOR = "#00e676"
    ERROR_COLOR = "#ff5252"
    WARNING_COLOR = "#ffb74d"
    INFO_COLOR = "#64b5f6"
    LOG_BG = "#121212"

    MAIN_STYLESHEET = f"background-color: {WINDOW_BG}; color: {TEXT_COLOR};"
    BUTTON_STYLE = """
        QPushButton {{
            background-color: {bg_color};
            color: {text_color};
            font-size: 15px;
            padding: 10px;
            border-radius: 4px;
            border: none;
        }}
        QPushButton:hover {{ background-color: {hover_color}; }}
        QPushButton:disabled {{ background-color: #555; }}
    """
    QUEUE_LIST_STYLE = f"""
        QListWidget {{
            background-color: {WIDGET_BG};
            color: {TEXT_COLOR};
            font-size: 14px;
            border: 1px solid #444;
        }}
        QListWidget::item:selected {{
            background-color: {PRIMARY_ACCENT};
            color: white;
        }}
    """
    LOG_OUTPUT_STYLE = f"""
        background-color: {LOG_BG};
        color: {TEXT_COLOR};
        font-family: Consolas, 'Courier New', monospace;
        font-size: 13px;
        border: 1px solid #444;
    """

# --- Services / Workers ---

class TitleFetcher(QObject):
    """Fetches video titles using yt-dlp in a separate thread."""
    title_fetched = Signal(str, str)  # url, title
    error = Signal(str, str)         # url, error message
    finished = Signal()              # Signal that the operation is complete

    def __init__(self, url: str, cookies_path: Path, ffprobe_path: Path):
        super().__init__()
        self.url = url
        self.cookies_path = cookies_path
        self.ffprobe_path = ffprobe_path

    def run(self):
        """Executes yt-dlp to get video metadata."""
        try:
            cmd = [
                "yt-dlp",
                "--ffmpeg-location", str(self.ffprobe_path.parent),
                "--skip-download",
                "--print-json",
                self.url
            ]
            
            # Only include cookies if file exists and is not empty
            if self.cookies_path.exists() and self.cookies_path.stat().st_size > 0:
                cmd.insert(1, "--cookies")
                cmd.insert(2, str(self.cookies_path))
            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            proc = subprocess.run(
                cmd, capture_output=True, text=True, check=False,
                timeout=20, startupinfo=startupinfo, encoding='utf-8'
            )

            if proc.returncode != 0:
                self.error.emit(self.url, proc.stderr.strip() or "Unknown error from yt-dlp.")
                self.finished.emit()
                return

            # A single video gives one JSON line, a playlist gives multiple. We only need the first.
            first_line = proc.stdout.strip().splitlines()[0]
            info = json.loads(first_line)
            title = info.get("title", "Unknown Title")
            self.title_fetched.emit(self.url, title)
            self.finished.emit()
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            self.error.emit(self.url, f"Failed to parse title: {e}")
            self.finished.emit()
        except Exception as e:
            self.error.emit(self.url, f"An unexpected error occurred: {e}")
            self.finished.emit()

class DownloadWorker(QObject):
    """Manages a single yt-dlp download process."""
    log = Signal(str, str)  # message, color
    finished = Signal(int)  # exit_code
    error = Signal(str)

    def __init__(self, item: Dict[str, Any], settings: AppSettings):
        super().__init__()
        self.item = item
        self.settings = settings
        self.process: Optional[QProcess] = None
        self._is_cancelled = False

    def run(self):
        """Builds and starts the yt-dlp download command."""
        try:
            cmd = self._build_command()
            self.log.emit(f"🚀 Starting download for: {self._truncate_title(self.item['title'])}\n", AppStyles.INFO_COLOR)

            self.process = QProcess()
            self.process.setProcessChannelMode(QProcess.MergedChannels)
            self.process.readyReadStandardOutput.connect(self._on_ready_read)
            self.process.finished.connect(self._on_finished)
            
            self.process.start(cmd[0], cmd[1:])
            if not self.process.waitForStarted(5000):
                self.error.emit("Failed to start the yt-dlp process.")
                self.finished.emit(-1)
        except Exception as e:
            self.error.emit(f"Error preparing download: {e}")
            self.finished.emit(-1)

    def _truncate_title(self, title: str) -> str:
        """Truncates the title to 35 characters for display."""
        return title[:35] + "..." if len(title) > 35 else title

    def cancel(self):
        """Terminates the running download process."""
        self._is_cancelled = True
        if self.process and self.process.state() == QProcess.Running:
            self.log.emit("⏹️ Cancelling download...\n", AppStyles.WARNING_COLOR)
            self.process.terminate()
            if not self.process.waitForFinished(3000):
                self.process.kill()

    def _on_ready_read(self):
        """Reads and logs output from the process."""
        output = self.process.readAllStandardOutput().data().decode(errors='ignore')
        color = AppStyles.TEXT_COLOR
        if "error" in output.lower():
            color = AppStyles.ERROR_COLOR
        self.log.emit(output, color)

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus):
        """Handles the completion of the download process."""
        if self._is_cancelled:
            self.log.emit("⏹️ Download cancelled by user.\n", AppStyles.WARNING_COLOR)
            self.finished.emit(-1)
            return

        if exit_code == 0:
            self.log.emit("✅ Download finished successfully.\n", AppStyles.SUCCESS_COLOR)
        else:
            self.log.emit(f"❌ yt-dlp exited with code {exit_code}.\n", AppStyles.ERROR_COLOR)
        self.finished.emit(exit_code)

    def _build_command(self) -> List[str]:
        """Constructs the yt-dlp command list."""
        cmd = ["yt-dlp", "--no-warnings", "--progress"]
        format_code = self.item["format_code"]
        is_playlist = format_code == "playlist_mp3"
        is_audio = format_code in ["bestaudio", "playlist_mp3"]

        if self.settings.COOKIES_PATH.exists() and self.settings.COOKIES_PATH.stat().st_size > 0:
            base += ["--cookies", str(self.settings.COOKIES_PATH)]

        # Set ffmpeg location to our _internal directory
        cmd.extend(["--ffmpeg-location", str(self.settings.FFMPEG_PATH.parent)])

        if is_playlist:
            cmd.extend(["--yes-playlist", "-o", self.settings.PLAYLIST_TEMPLATE])
        else:
            cmd.extend(["-o", self.settings.OUTPUT_TEMPLATE])

        if is_audio:
            cmd.extend([
                "-f", "bestaudio",
                "--extract-audio",
                "--audio-format", "mp3",
                "--audio-quality", "0",
                "--embed-thumbnail",
                "--add-metadata"
            ])
        else:
            cmd.extend(["-f", format_code, "--merge-output-format", "mkv"])
        
        cmd.append(self.item["url"])
        return cmd

# --- UI Widgets ---

class QueueItemWidget(QWidget):
    """Custom widget for displaying an item in the download queue."""
    def __init__(self, title: str, url: str):
        super().__init__()
        self.title = title
        self.url = url
        self.is_active = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)

        # Truncate title to 35 characters
        display_title = title[:35] + "..." if len(title) > 35 else title
        self.label = QLabel(display_title)
        self.label.setToolTip(f"{title}\n{url}")
        layout.addWidget(self.label, 1) # Add stretch factor

        # Use standard icons for a native feel
        style = self.style()
        self.btn_up = QToolButton(toolTip="Move Up", icon=style.standardIcon(QStyle.SP_ArrowUp))
        self.btn_down = QToolButton(toolTip="Move Down", icon=style.standardIcon(QStyle.SP_ArrowDown))
        self.btn_delete = QToolButton(toolTip="Remove", icon=style.standardIcon(QStyle.SP_DialogCloseButton))

        layout.addWidget(self.btn_up)
        layout.addWidget(self.btn_down)
        layout.addWidget(self.btn_delete)
        
    def set_active(self, active: bool):
        """Styles the item label to indicate it's the current download."""
        self.is_active = active
        font = self.label.font()
        font.setBold(active)
        self.label.setFont(font)
        color = AppStyles.SUCCESS_COLOR if active else AppStyles.TEXT_COLOR
        self.label.setStyleSheet(f"color: {color};")

# --- Main Application Logic ---

class YTGetGUI(QMainWindow):
    """The main application window."""
    def __init__(self):
        super().__init__()
        try:
            self.settings = AppSettings()
        except FileNotFoundError as e:
            QMessageBox.critical(None, "Missing Required Files", str(e))
            sys.exit(1)
            
        self.styles = AppStyles()

        self.queue: List[Dict[str, Any]] = []
        self.current_download_item: Optional[Dict[str, Any]] = None
        self.is_downloading = False
        self.queue_paused = True

        # Worker threads
        self.download_thread: Optional[QThread] = None
        self.download_worker: Optional[DownloadWorker] = None
        self.title_fetch_thread: Optional[QThread] = None
        self.title_fetcher: Optional[TitleFetcher] = None
        
        # Post-queue action
        self.post_queue_action = "Keep"

        self._setup_ui()
        self._setup_connections()
        self._setup_menu()

    def _setup_ui(self):
        """Initializes all UI components."""
        self.setWindowTitle(f"{self.settings.APP_NAME} {self.settings.VERSION}")
        
        # Try multiple icon locations
        icon_paths = [
            self.settings.BASE_DIR / "icon.ico",
            self.settings.INTERNAL_DIR / "icon.ico"
        ]
        
        for path in icon_paths:
            if path.exists():
                self.setWindowIcon(QIcon(str(path)))
                break
        
        self.setGeometry(200, 200, 950, 650)
        self.setStyleSheet(self.styles.MAIN_STYLESHEET)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # Create a splitter for resizable panels
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # Left Panel: Queue List (1/3 of window)
        queue_container = QWidget()
        queue_layout = QVBoxLayout(queue_container)
        queue_layout.setContentsMargins(0, 0, 0, 0)
        
        self.queue_list = QListWidget()
        self.queue_list.setStyleSheet(self.styles.QUEUE_LIST_STYLE)
        queue_layout.addWidget(self.queue_list)
        
        splitter.addWidget(queue_container)
        splitter.setStretchFactor(0, 1)  # Queue takes 1/3 of space

        # Right Panel: Controls (2/3 of window)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 0, 0, 0)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(1, 2)  # Controls take 2/3 of space

        # URL Input
        self.url_input = QLineEdit(placeholderText="🔎 Paste YouTube URL and press Enter")
        self.url_input.setStyleSheet("padding: 8px; font-size: 16px;")
        right_layout.addWidget(self.url_input)

        # Format Selection
        self.format_box = QComboBox()
        self.format_box.addItems(self.settings.RESOLUTIONS.keys())
        self.format_box.setStyleSheet("padding: 8px; font-size: 15px; margin-top: 5px;")
        right_layout.addWidget(self.format_box)

        # Button Row
        btn_row = QHBoxLayout()
        self.btn_add_queue = QPushButton("➕ Add to Queue", enabled=False)
        self.btn_start_queue = QPushButton("▶️ Start Queue")
        self.btn_pause_queue = QPushButton("⏸️ Pause Queue", enabled=False)

        self.btn_add_queue.setStyleSheet(self.styles.BUTTON_STYLE.format(
            bg_color=AppStyles.INFO_COLOR, text_color="white", hover_color="#81d4fa"))
        self.btn_start_queue.setStyleSheet(self.styles.BUTTON_STYLE.format(
            bg_color=AppStyles.SUCCESS_COLOR, text_color="black", hover_color="#69f0ae"))
        self.btn_pause_queue.setStyleSheet(self.styles.BUTTON_STYLE.format(
            bg_color=AppStyles.WARNING_COLOR, text_color="black", hover_color="#ffd54f"))
        btn_row.addWidget(self.btn_add_queue)
        btn_row.addWidget(self.btn_start_queue)
        btn_row.addWidget(self.btn_pause_queue)
        right_layout.addLayout(btn_row)

        # Log Output
        self.log_output = QTextEdit(readOnly=True)
        self.log_output.setStyleSheet(self.styles.LOG_OUTPUT_STYLE)
        right_layout.addWidget(self.log_output)
        
        self.log("💡 Welcome to YTGet! Paste a URL to begin.\n", AppStyles.INFO_COLOR)
        self.log(f"📂 Download folder: {self.settings.DOWNLOADS_DIR}\n", AppStyles.INFO_COLOR)
        self.log(f"🔧 Using ffmpeg from: {self.settings.FFMPEG_PATH}\n", AppStyles.INFO_COLOR)
        
        # Set initial splitter sizes (1/3 for queue, 2/3 for controls)
        QTimer.singleShot(100, lambda: splitter.setSizes([self.width()//3, self.width()*2//3]))

    def _setup_connections(self):
        """Connects widget signals to handler slots."""
        self.url_input.textChanged.connect(self._on_url_text_changed)
        self.url_input.returnPressed.connect(self._add_to_queue)
        self.btn_add_queue.clicked.connect(self._add_to_queue)
        self.btn_start_queue.clicked.connect(self._start_queue)
        self.btn_pause_queue.clicked.connect(self._pause_queue)

    def _setup_menu(self):
        """Creates the main menu bar."""
        menubar = self.menuBar()
        menubar.setStyleSheet("QMenuBar { background-color: #333; } QMenu::item:selected { background-color: #555; }")

        # File Menu
        file_menu = menubar.addMenu("File")
        file_menu.addAction("Save Queue", self._save_queue_to_disk, "Ctrl+S")
        file_menu.addAction("Load Queue", self._load_queue_from_disk, "Ctrl+O")
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close, "Ctrl+Q")
        
        # Settings Menu
        settings_menu = menubar.addMenu("Settings")
        settings_menu.addAction("Set Download Folder...", self._set_download_path)
        settings_menu.addAction("Set Cookies File...", self._set_cookies_path)
        settings_menu.addSeparator()
        
        # Post-queue actions submenu
        post_action_menu = settings_menu.addMenu("When Queue Finishes...")
        action_group = QActionGroup(self)
        action_group.setExclusive(True)
        
        actions = {
            "Keep Running": "Keep", "Shutdown PC": "Shutdown", 
            "Sleep PC": "Sleep", "Restart PC": "Restart", "Close YTGet": "Close"
        }
        for text, value in actions.items():
            action = QAction(text, self, checkable=True)
            if value == self.post_queue_action:
                action.setChecked(True)
            action.triggered.connect(lambda checked, v=value: self._set_post_queue_action(v))
            action_group.addAction(action)
            post_action_menu.addAction(action)
            
        # Help Menu
        help_menu = menubar.addMenu("Help")
        help_menu.addAction("Check for Updates", self._check_for_updates)
        help_menu.addAction("Open Download Folder", lambda: webbrowser.open(self.settings.DOWNLOADS_DIR.as_uri()))
        help_menu.addAction("About", self._show_about)

    # --- Core Logic Methods ---

    def _on_url_text_changed(self, text: str):
        """Enables 'Add' button only if URL seems valid."""
        is_valid = bool(self.settings.YOUTUBE_URL_PATTERN.match(text))
        self.btn_add_queue.setEnabled(is_valid)

    def _add_to_queue(self):
        """Fetches title and adds a new item to the queue."""
        url = self.url_input.text().strip()
        if not self.settings.YOUTUBE_URL_PATTERN.match(url):
            self.log("⚠️ Invalid YouTube URL format.\n", AppStyles.WARNING_COLOR)
            return

        self.url_input.clear()
        self.btn_add_queue.setEnabled(False)
        self.log(f"🔎 Fetching title for: {url[:50]}...\n", AppStyles.INFO_COLOR)
        
        try:
            # Check if thread exists and is running (safe check)
            if hasattr(self, 'title_fetch_thread') and self.title_fetch_thread is not None:
                if self.title_fetch_thread.isRunning():
                    self.title_fetch_thread.quit()
                    self.title_fetch_thread.wait()
        except RuntimeError:
            # If the C++ object is already deleted, just continue
            pass
        
        self.title_fetch_thread = QThread()
        self.title_fetcher = TitleFetcher(url, self.settings.COOKIES_PATH, self.settings.FFPROBE_PATH)
        self.title_fetcher.moveToThread(self.title_fetch_thread)
        
        self.title_fetch_thread.started.connect(self.title_fetcher.run)
        self.title_fetcher.title_fetched.connect(self._on_title_fetched)
        self.title_fetcher.error.connect(self._on_title_error)
        self.title_fetcher.finished.connect(self.title_fetch_thread.quit)
        self.title_fetch_thread.finished.connect(lambda: self.title_fetcher.deleteLater())
        self.title_fetch_thread.finished.connect(lambda: self.title_fetch_thread.deleteLater())
        self.title_fetch_thread.start()

    def _on_title_fetched(self, url: str, title: str):
        """Callback for successful title fetch."""
        format_text = self.format_box.currentText()
        item = {
            "url": url,
            "title": title,
            "format_code": self.settings.RESOLUTIONS[format_text]
        }
        self.queue.append(item)
        self.log(f"✅ Added to queue: {self._truncate_title(title)}\n", AppStyles.SUCCESS_COLOR)
        self._refresh_queue_list()
        self._update_button_states()

    def _truncate_title(self, title: str) -> str:
        """Truncates the title to 35 characters for display."""
        return title[:35] + "..." if len(title) > 35 else title

    def _on_title_error(self, url: str, error_msg: str):
        """Callback for title fetch failure."""
        self.log(f"❌ Error fetching title for {url[:50]}: {error_msg}\n", AppStyles.ERROR_COLOR)
        self.btn_add_queue.setEnabled(True)

    def _start_queue(self):
        """Starts processing the download queue."""
        if self.is_downloading and not self.queue_paused:
            self.log("ℹ️ Queue is already running.\n", AppStyles.INFO_COLOR)
            return
        if not self.queue:
            self.log("⚠️ Queue is empty. Add items to start.\n", AppStyles.WARNING_COLOR)
            return
        if self.queue_paused and self.is_downloading:
            # Resume paused queue
            self.queue_paused = False
            self.log("▶️ Resuming queue processing...\n", AppStyles.SUCCESS_COLOR)
            self._download_next()
        else:
            # Start new queue
            self.queue_paused = False
            self.log("▶️ Starting queue processing...\n", AppStyles.SUCCESS_COLOR)
            self._download_next()
        
        self._update_button_states()

    def _pause_queue(self):
        """Pauses the queue and cancels the current download."""
        if not self.is_downloading:
            self.log("ℹ️ Queue is not running.\n", AppStyles.INFO_COLOR)
            return
            
        self.queue_paused = True
        if self.download_worker:
            self.download_worker.cancel() # Worker will emit finished signal
        self._update_button_states()
    
    def _download_next(self):
        """Initiates the download of the next item in the queue."""
        if self.queue_paused or self.is_downloading or not self.queue:
            if not self.queue and not self.is_downloading:
                self._on_queue_finished()
            return

        self.is_downloading = True
        self.current_download_item = self.queue[0]
        self._refresh_queue_list() # Mark current item
        self._update_button_states()
        
        try:
            if hasattr(self, 'download_thread') and self.download_thread is not None:
                if self.download_thread.isRunning():
                    self.download_thread.quit()
                    self.download_thread.wait()
        except RuntimeError:
            pass
        
        self.download_thread = QThread()
        self.download_worker = DownloadWorker(self.current_download_item, self.settings)
        self.download_worker.moveToThread(self.download_thread)
        
        self.download_thread.started.connect(self.download_worker.run)
        self.download_worker.log.connect(self.log)
        self.download_worker.error.connect(lambda msg: self.log(f"❌ {msg}\n", AppStyles.ERROR_COLOR))
        self.download_worker.finished.connect(self._on_download_finished)
        self.download_worker.finished.connect(self.download_thread.quit)
        self.download_thread.finished.connect(lambda: self.download_worker.deleteLater())
        self.download_thread.finished.connect(lambda: self.download_thread.deleteLater())
        
        self.download_thread.start()

    def _on_download_finished(self, exit_code: int):
        """Handles completion of a single download and moves to the next."""
        self.is_downloading = False
        self.current_download_item = None
        
        # Only remove from queue on success
        if exit_code == 0 and self.queue:
            self.queue.pop(0)

        self._refresh_queue_list()
        self._update_button_states()

        # Automatically continue if not paused
        if not self.queue_paused and self.queue:
            self._download_next()
        elif not self.queue:  # Queue is empty
            self._on_queue_finished()

    def _on_queue_finished(self):
        """Executes the configured action when the queue is empty."""
        self.log(f"🏁 Queue complete! Action: {self.post_queue_action}.\n", AppStyles.SUCCESS_COLOR)
        
        action = self.post_queue_action
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
    
    # --- UI & State Helpers ---
    
    def _refresh_queue_list(self):
        """Redraws the entire queue list widget from the self.queue list."""
        self.queue_list.clear()
        for i, item in enumerate(self.queue):
            widget = QueueItemWidget(item["title"], item["url"])
            list_item = QListWidgetItem()
            list_item.setSizeHint(widget.sizeHint())
            
            # Store the index in the widget object to avoid lambda capture issues
            widget.btn_delete.clicked.connect(lambda checked, idx=i: self._remove_queue_item(idx))
            widget.btn_up.clicked.connect(lambda checked, idx=i: self._move_queue_item(idx, -1))
            widget.btn_down.clicked.connect(lambda checked, idx=i: self._move_queue_item(idx, 1))
            
            # Highlight the currently downloading item
            if item == self.current_download_item:
                 widget.set_active(True)
            
            self.queue_list.addItem(list_item)
            self.queue_list.setItemWidget(list_item, widget)

    def _remove_queue_item(self, index: int):
        if 0 <= index < len(self.queue):
            # If removing the current download, pause the queue
            if self.is_downloading and self.queue[index] == self.current_download_item:
                self.log("⚠️ Cannot remove an active download. Pause the queue first.\n", AppStyles.WARNING_COLOR)
                return
            
            item = self.queue.pop(index)
            self.log(f"🗑️ Removed from queue: {self._truncate_title(item['title'])}\n", AppStyles.INFO_COLOR)
            self._refresh_queue_list()
            self._update_button_states()

    def _move_queue_item(self, index: int, direction: int):
        new_index = index + direction
        if not (0 <= index < len(self.queue) and 0 <= new_index < len(self.queue)):
            return
        # Cannot move the active download
        if self.is_downloading and (self.queue[index] == self.current_download_item or self.queue[new_index] == self.current_download_item):
            self.log("⚠️ Cannot move an active download.\n", AppStyles.WARNING_COLOR)
            return

        self.queue.insert(new_index, self.queue.pop(index))
        self._refresh_queue_list()

    def _update_button_states(self):
        """Enables/disables buttons based on application state."""
        has_items = bool(self.queue)
        self.btn_start_queue.setEnabled(has_items and (self.queue_paused or not self.is_downloading))
        self.btn_pause_queue.setEnabled(self.is_downloading and not self.queue_paused)
        self.btn_add_queue.setEnabled(not self.is_downloading or self.queue_paused)
    
    def log(self, text: str, color: str = AppStyles.TEXT_COLOR):
        """Appends colorized text to the log widget."""
        cursor = self.log_output.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor.setCharFormat(fmt)
        
        cursor.insertText(text)
        self.log_output.ensureCursorVisible()

    # --- Menu Actions & File I/O ---

    def _save_queue_to_disk(self):
        """Saves the current queue to a JSON file."""
        if not self.queue:
            self.log("⚠️ Queue is empty, nothing to save.\n", AppStyles.WARNING_COLOR)
            return
        
        save_path, _ = QFileDialog.getSaveFileName(self, "Save Queue", str(self.settings.BASE_DIR / "queue.json"), "JSON Files (*.json)")
        if save_path:
            try:
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(self.queue, f, indent=2)
                self.log(f"💾 Queue saved to {save_path}\n", AppStyles.SUCCESS_COLOR)
                # Refresh queue list to ensure buttons work
                self._refresh_queue_list()
            except Exception as e:
                self.log(f"❌ Failed to save queue: {e}\n", AppStyles.ERROR_COLOR)

    def _load_queue_from_disk(self):
        """Loads a queue from a JSON file."""
        if self.is_downloading:
            self.log("⚠️ Cannot load a new queue while a download is active.\n", AppStyles.WARNING_COLOR)
            return
            
        load_path, _ = QFileDialog.getOpenFileName(self, "Load Queue", str(self.settings.BASE_DIR), "JSON Files (*.json)")
        if load_path:
            try:
                with open(load_path, "r", encoding="utf-8") as f:
                    loaded_queue = json.load(f)
                if not isinstance(loaded_queue, list):
                    raise ValueError("Invalid queue file format.")
                self.queue = loaded_queue
                self._refresh_queue_list()
                self._update_button_states()
                self.log(f"📂 Queue loaded from {load_path}\n", AppStyles.SUCCESS_COLOR)
            except (Exception, json.JSONDecodeError, ValueError) as e:
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
            self.log(f"🍪 Cookies path set to: {path_str}\n", AppStyles.INFO_COLOR)
            
    def _set_post_queue_action(self, action: str):
        self.post_queue_action = action
        self.log(f"⚙️ Post-queue action set to: {action}\n", AppStyles.INFO_COLOR)

    def _check_for_updates(self):
        """Checks GitHub for the latest release version."""
        self.log("🌐 Checking for updates...\n", AppStyles.INFO_COLOR)
        try:
            response = requests.head(f"{self.settings.GITHUB_URL}/releases/latest", allow_redirects=True, timeout=5)
            response.raise_for_status()
            latest_version_tag = response.url.rstrip('/').split('/')[-1].lstrip('v')

            if latest_version_tag > self.settings.VERSION:
                reply = QMessageBox.information(self, "Update Available",
                    f"A new version ({latest_version_tag}) is available!\n"
                    f"You are using version {self.settings.VERSION}.\n\n"
                    "Do you want to open the releases page?",
                    QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.Yes:
                    webbrowser.open(f"{self.settings.GITHUB_URL}/releases")
            else:
                QMessageBox.information(self, "Up to Date", "You are using the latest version.")
        except requests.RequestException as e:
            QMessageBox.warning(self, "Update Check Failed", f"Could not check for updates: {e}")

    def _show_about(self):
        QMessageBox.about(self, "About YTGet",
            f"<h2>{self.settings.APP_NAME} {self.settings.VERSION}</h2>"
            "<p>A simple yet powerful GUI for yt-dlp.</p>"
            "<p>Built with Python and PySide6.</p>"
            f"<p><a href='{self.settings.GITHUB_URL}'>Visit on GitHub</a></p>")

    def closeEvent(self, event):
        """Handle window close event."""
        # Clean up any running threads safely
        try:
            if hasattr(self, 'download_thread') and self.download_thread is not None:
                if self.download_thread.isRunning():
                    if hasattr(self, 'download_worker') and self.download_worker is not None:
                        self.download_worker.cancel()
                    self.download_thread.quit()
                    self.download_thread.wait()
        except RuntimeError:
            pass
        
        try:
            if hasattr(self, 'title_fetch_thread') and self.title_fetch_thread is not None:
                if self.title_fetch_thread.isRunning():
                    self.title_fetch_thread.quit()
                    self.title_fetch_thread.wait()
        except RuntimeError:
            pass

        # Ask to save queue if it's not empty
        if self.queue:
            reply = QMessageBox.question(self, 'Exit Confirmation',
                "You have items in your queue. Do you want to save the queue before exiting?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            
            if reply == QMessageBox.Save:
                self._save_queue_to_disk()
                event.accept()
            elif reply == QMessageBox.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

def main():
    """Application entry point."""
    app = QApplication(sys.argv)
    window = YTGetGUI()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
