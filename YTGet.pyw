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
import datetime
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

# Third-party imports
import requests
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLineEdit, QTextEdit, QListWidget, QListWidgetItem, QLabel, QFileDialog,
    QComboBox, QMessageBox, QToolButton, QSpacerItem, QSizePolicy, QMenuBar,
    QMenu, QStyle, QSplitter, QDialog, QDialogButtonBox, QGroupBox,
    QCheckBox, QTabWidget, QFormLayout, QRadioButton, QCalendarWidget,
    QGridLayout, QSpinBox, QDoubleSpinBox, QInputDialog
)
from PySide6.QtGui import QAction, QColor, QTextCharFormat, QIcon, QActionGroup, QTextCursor, QPalette
from PySide6.QtCore import Qt, QThread, Signal, QObject, QProcess, QTimer, QDate

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
    VERSION: str = "2.2.1"
    APP_NAME: str = "YTGet"
    GITHUB_URL: str = "https://github.com/ErfanNamira/YTGet"
    CONFIG_PATH: Path = field(init=False)

    # Paths - Changed to use working directory's Downloads folder
    BASE_DIR: Path = field(default_factory=get_base_path)
    INTERNAL_DIR: Path = field(init=False)  
    DOWNLOADS_DIR: Path = field(init=False)  
    COOKIES_PATH: Path = field(init=False) 
    YT_DLP_PATH: Path = field(init=False)
    FFMPEG_PATH: Path = field(init=False)   
    FFPROBE_PATH: Path = field(init=False)  
    ARCHIVE_PATH: Path = field(init=False)

    # yt-dlp templates
    OUTPUT_TEMPLATE: str = field(init=False)
    PLAYLIST_TEMPLATE: str = field(init=False)

    # URL Pattern
    YOUTUBE_URL_PATTERN: re.Pattern = field(default_factory=lambda: re.compile(
        r"^(https?://)?(www\.|m\.)?(youtube\.com|youtu\.be|music\.youtube\.com)/.+", re.IGNORECASE
    ))

    # Resolutions - Updated with resolution fallback support
    RESOLUTIONS: Dict[str, str] = field(default_factory=lambda: {
        "🎬 2160p (4K)": "251+313/bestvideo[height<=2160]+bestaudio",
        "🎬 1440p (QHD)": "251+271/bestvideo[height<=1440]+bestaudio",
        "🎬 1080p (FHD)": "251+248/bestvideo[height<=1080]+bestaudio",
        "🎬 720p (HD)": "251+247/bestvideo[height<=720]+bestaudio",
        "🎬 480p (SD)": "251+244/bestvideo[height<=480]+bestaudio",
        "🎵 Audio Only (MP3)": "bestaudio",
        "🎵 Playlist (MP3)": "playlist_mp3",
        "🎵 YouTube Music": "youtube_music"
    })
    
    # Settings with defaults
    PROXY_URL: str = ""
    SPONSORBLOCK_CATEGORIES: List[str] = field(default_factory=list)
    CHAPTERS_MODE: str = "none"  # "none", "embed", "split"
    WRITE_SUBS: bool = False
    SUB_LANGS: str = "en"
    WRITE_AUTO_SUBS: bool = False
    CONVERT_SUBS_TO_SRT: bool = False
    ENABLE_ARCHIVE: bool = False
    PLAYLIST_REVERSE: bool = False
    AUDIO_NORMALIZE: bool = False
    ADD_METADATA: bool = True
    LIMIT_RATE: str = ""
    RETRIES: int = 10
    ORGANIZE_BY_UPLOADER: bool = False
    DATEAFTER: str = ""
    COOKIES_FROM_BROWSER: str = ""
    LIVE_FROM_START: bool = False
    YT_MUSIC_METADATA: bool = False
    PLAYLIST_ITEMS: str = ""
    CLIP_START: str = ""
    CLIP_END: str = ""
    CUSTOM_FFMPEG_ARGS: str = ""

    def __post_init__(self):
        """Initialize paths and create required directories."""
        # Initialize paths
        self.INTERNAL_DIR = self.BASE_DIR / "_internal"
        self.DOWNLOADS_DIR = Path(os.path.join(os.getcwd(), "Downloads"))
        self.COOKIES_PATH = self.BASE_DIR / "cookies.txt"
        self.YT_DLP_PATH = self.BASE_DIR / "yt-dlp.exe"
        self.FFMPEG_PATH = self.BASE_DIR / "ffmpeg.exe"
        self.FFPROBE_PATH = self.BASE_DIR / "ffprobe.exe"
        self.ARCHIVE_PATH = self.BASE_DIR / "archive.txt"
        self.CONFIG_PATH = self.BASE_DIR / "config.json"
        
        # Initialize templates
        self.OUTPUT_TEMPLATE = str(self.DOWNLOADS_DIR / "%(title)s.%(ext)s")
        self.PLAYLIST_TEMPLATE = str(self.DOWNLOADS_DIR / "%(playlist_index)s - %(title)s.%(ext)s")

        # Create required directories and files
        self.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        self.INTERNAL_DIR.mkdir(parents=True, exist_ok=True)
        
        # Create empty cookies file if it doesn't exist
        if not self.COOKIES_PATH.exists():
            self.COOKIES_PATH.touch()
            
        # Create empty archive file if enabled
        if self.ENABLE_ARCHIVE and not self.ARCHIVE_PATH.exists():
            self.ARCHIVE_PATH.touch()
            
        # Verify ffmpeg and ffprobe exist
        if not self.YT_DLP_PATH.exists():  # Add this check
            raise FileNotFoundError(f"yt-dlp.exe not found at {self.YT_DLP_PATH}")
        if not self.FFMPEG_PATH.exists():
            raise FileNotFoundError(f"ffmpeg.exe not found at {self.FFMPEG_PATH}")
        if not self.FFPROBE_PATH.exists():
            raise FileNotFoundError(f"ffprobe.exe not found at {self.FFPROBE_PATH}")
        
        # Load config if exists
        self.load_config()

    def set_download_path(self, path: Path):
        """Updates the download path and templates."""
        self.DOWNLOADS_DIR = path
        self.OUTPUT_TEMPLATE = str(self.DOWNLOADS_DIR / "%(title)s.%(ext)s")
        self.PLAYLIST_TEMPLATE = str(self.DOWNLOADS_DIR / "%(playlist_index)s - %(title)s.%(ext)s")
        self.save_config()
    
    def save_config(self):
        """Save current settings to config file."""
        config = {
            "PROXY_URL": self.PROXY_URL,
            "SPONSORBLOCK_CATEGORIES": self.SPONSORBLOCK_CATEGORIES,
            "CHAPTERS_MODE": self.CHAPTERS_MODE,
            "WRITE_SUBS": self.WRITE_SUBS,
            "SUB_LANGS": self.SUB_LANGS,
            "WRITE_AUTO_SUBS": self.WRITE_AUTO_SUBS,
            "CONVERT_SUBS_TO_SRT": self.CONVERT_SUBS_TO_SRT,
            "ENABLE_ARCHIVE": self.ENABLE_ARCHIVE,
            "PLAYLIST_REVERSE": self.PLAYLIST_REVERSE,
            "AUDIO_NORMALIZE": self.AUDIO_NORMALIZE,
            "ADD_METADATA": self.ADD_METADATA,
            "LIMIT_RATE": self.LIMIT_RATE,
            "RETRIES": self.RETRIES,
            "ORGANIZE_BY_UPLOADER": self.ORGANIZE_BY_UPLOADER,
            "DATEAFTER": self.DATEAFTER,
            "COOKIES_FROM_BROWSER": self.COOKIES_FROM_BROWSER,
            "LIVE_FROM_START": self.LIVE_FROM_START,
            "YT_MUSIC_METADATA": self.YT_MUSIC_METADATA,
            "PLAYLIST_ITEMS": self.PLAYLIST_ITEMS,
            "CLIP_START": self.CLIP_START,
            "CLIP_END": self.CLIP_END,
            "CUSTOM_FFMPEG_ARGS": self.CUSTOM_FFMPEG_ARGS,
            "DOWNLOADS_DIR": str(self.DOWNLOADS_DIR)
        }
        
        with open(self.CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
    
    def load_config(self):
        """Load settings from config file if exists."""
        if not self.CONFIG_PATH.exists():
            return
            
        try:
            with open(self.CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            # Apply loaded settings
            self.PROXY_URL = config.get("PROXY_URL", self.PROXY_URL)
            self.SPONSORBLOCK_CATEGORIES = config.get("SPONSORBLOCK_CATEGORIES", self.SPONSORBLOCK_CATEGORIES)
            self.CHAPTERS_MODE = config.get("CHAPTERS_MODE", self.CHAPTERS_MODE)
            self.WRITE_SUBS = config.get("WRITE_SUBS", self.WRITE_SUBS)
            self.SUB_LANGS = config.get("SUB_LANGS", self.SUB_LANGS)
            self.WRITE_AUTO_SUBS = config.get("WRITE_AUTO_SUBS", self.WRITE_AUTO_SUBS)
            self.CONVERT_SUBS_TO_SRT = config.get("CONVERT_SUBS_TO_SRT", self.CONVERT_SUBS_TO_SRT)
            self.ENABLE_ARCHIVE = config.get("ENABLE_ARCHIVE", self.ENABLE_ARCHIVE)
            self.PLAYLIST_REVERSE = config.get("PLAYLIST_REVERSE", self.PLAYLIST_REVERSE)
            self.AUDIO_NORMALIZE = config.get("AUDIO_NORMALIZE", self.AUDIO_NORMALIZE)
            self.ADD_METADATA = config.get("ADD_METADATA", self.ADD_METADATA)
            self.LIMIT_RATE = config.get("LIMIT_RATE", self.LIMIT_RATE)
            self.RETRIES = config.get("RETRIES", self.RETRIES)
            self.ORGANIZE_BY_UPLOADER = config.get("ORGANIZE_BY_UPLOADER", self.ORGANIZE_BY_UPLOADER)
            self.DATEAFTER = config.get("DATEAFTER", self.DATEAFTER)
            self.COOKIES_FROM_BROWSER = config.get("COOKIES_FROM_BROWSER", self.COOKIES_FROM_BROWSER)
            self.LIVE_FROM_START = config.get("LIVE_FROM_START", self.LIVE_FROM_START)
            self.YT_MUSIC_METADATA = config.get("YT_MUSIC_METADATA", self.YT_MUSIC_METADATA)
            self.PLAYLIST_ITEMS = config.get("PLAYLIST_ITEMS", self.PLAYLIST_ITEMS)
            self.CLIP_START = config.get("CLIP_START", self.CLIP_START)
            self.CLIP_END = config.get("CLIP_END", self.CLIP_END)
            self.CUSTOM_FFMPEG_ARGS = config.get("CUSTOM_FFMPEG_ARGS", self.CUSTOM_FFMPEG_ARGS)
            
            # Update download path if changed
            if "DOWNLOADS_DIR" in config:
                self.DOWNLOADS_DIR = Path(config["DOWNLOADS_DIR"])
                self.OUTPUT_TEMPLATE = str(self.DOWNLOADS_DIR / "%(title)s.%(ext)s")
                self.PLAYLIST_TEMPLATE = str(self.DOWNLOADS_DIR / "%(playlist_index)s - %(title)s.%(ext)s")
                
        except Exception as e:
            print(f"Error loading config: {e}")

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
    DIALOG_BG = "#2a2a2a"

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
    DIALOG_STYLE = f"""
        QDialog {{
            background-color: {DIALOG_BG};
            color: {TEXT_COLOR};
        }}
        QGroupBox {{
            font-weight: bold;
            border: 1px solid #444;
            border-radius: 5px;
            margin-top: 1ex;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top center;
            padding: 0 3px;
        }}
        QCheckBox::indicator, QRadioButton::indicator {{
            width: 18px;
            height: 18px;
        }}
        QCheckBox::indicator:checked {{
            background-color: {PRIMARY_ACCENT};
            border: 1px solid {PRIMARY_ACCENT};
        }}
        QCheckBox::indicator:unchecked {{
            background-color: #333;
            border: 1px solid #666;
        }}
        QCheckBox::indicator:disabled {{
            background-color: #555;
        }}
        QRadioButton::indicator:checked {{
            background-color: {PRIMARY_ACCENT};
            border: 1px solid {PRIMARY_ACCENT};
            border-radius: 9px;
        }}
        QRadioButton::indicator:unchecked {{
            background-color: #333;
            border: 1px solid #666;
            border-radius: 9px;
        }}
        QLineEdit, QComboBox {{
            background-color: #333;
            color: {TEXT_COLOR};
            border: 1px solid #444;
            padding: 5px;
        }}
    """

# --- Preferences Dialog ---
class PreferencesDialog(QDialog):
    """Dialog for configuring advanced download options."""
    def __init__(self, parent: QWidget, settings: AppSettings):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Preferences")
        self.setMinimumSize(800, 650)  # Larger for additional settings
        self.setStyleSheet(AppStyles.DIALOG_STYLE)
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Tab widget
        tab_widget = QTabWidget()
        layout.addWidget(tab_widget)
        
        # Network Tab
        network_tab = QWidget()
        network_layout = QVBoxLayout(network_tab)
        network_layout.setContentsMargins(5, 5, 5, 5)
        tab_widget.addTab(network_tab, "Network")
        
        # Proxy settings
        proxy_group = QGroupBox("Proxy Settings")
        proxy_layout = QFormLayout(proxy_group)
        proxy_layout.setContentsMargins(10, 15, 10, 15)
        self.proxy_input = QLineEdit(self.settings.PROXY_URL)
        self.proxy_input.setPlaceholderText("http://proxy:port or socks5://proxy:port")
        proxy_layout.addRow("Proxy URL:", self.proxy_input)
        network_layout.addWidget(proxy_group)
        
        # Cookies settings
        cookies_group = QGroupBox("Cookies")
        cookies_layout = QFormLayout(cookies_group)
        cookies_layout.setContentsMargins(10, 15, 10, 15)
        self.cookies_path_input = QLineEdit(str(self.settings.COOKIES_PATH))
        self.cookies_path_input.setReadOnly(True)
        self.btn_browse_cookies = QPushButton("Browse...")
        self.btn_browse_cookies.setStyleSheet(AppStyles.BUTTON_STYLE.format(
            bg_color=AppStyles.INFO_COLOR, text_color="white", hover_color="#81d4fa"))
        
        # Browser cookie import
        self.cookies_browser_combo = QComboBox()
        self.cookies_browser_combo.addItems(["", "chrome", "firefox", "edge", "opera", "vivaldi"])
        if self.settings.COOKIES_FROM_BROWSER:
            self.cookies_browser_combo.setCurrentText(self.settings.COOKIES_FROM_BROWSER)
        
        cookies_layout.addRow("Cookies File:", self.cookies_path_input)
        cookies_layout.addRow(self.btn_browse_cookies)
        cookies_layout.addRow("Import from Browser:", self.cookies_browser_combo)
        network_layout.addWidget(cookies_group)
        
        # Rate limiting and retries
        rate_group = QGroupBox("Performance")
        rate_layout = QGridLayout(rate_group)
        rate_layout.setContentsMargins(10, 15, 10, 15)
        
        self.limit_rate_input = QLineEdit(self.settings.LIMIT_RATE)
        self.limit_rate_input.setPlaceholderText("e.g., 5M or 500K")
        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(1, 100)
        self.retries_spin.setValue(self.settings.RETRIES)
        
        rate_layout.addWidget(QLabel("Max Download Speed:"), 0, 0)
        rate_layout.addWidget(self.limit_rate_input, 0, 1)
        rate_layout.addWidget(QLabel("Retry Attempts:"), 1, 0)
        rate_layout.addWidget(self.retries_spin, 1, 1)
        
        network_layout.addWidget(rate_group)
        network_layout.addStretch()
        
        # SponsorBlock Tab
        sponsorblock_tab = QWidget()
        sponsorblock_layout = QVBoxLayout(sponsorblock_tab)
        sponsorblock_layout.setContentsMargins(5, 5, 5, 5)
        tab_widget.addTab(sponsorblock_tab, "SponsorBlock")
        
        # SponsorBlock settings
        sponsorblock_group = QGroupBox("Skip Segments")
        sponsorblock_group_layout = QVBoxLayout(sponsorblock_group)
        sponsorblock_group_layout.setContentsMargins(10, 15, 10, 15)
        
        # SponsorBlock categories
        categories = {
            "Sponsor": "sponsor",
            "Intro": "intro",
            "Outro": "outro",
            "Self Promotion": "selfpromo",
            "Interaction Reminder": "interaction",
            "Music Non-Music": "music_offtopic",
            "Preview/Recap": "preview",
            "Filler": "filler"
        }
        
        self.category_checkboxes = {}
        for name, code in categories.items():
            cb = QCheckBox(name)
            cb.setChecked(code in self.settings.SPONSORBLOCK_CATEGORIES)
            self.category_checkboxes[code] = cb
            sponsorblock_group_layout.addWidget(cb)
        
        sponsorblock_group_layout.addStretch()
        sponsorblock_group.setLayout(sponsorblock_group_layout)
        sponsorblock_layout.addWidget(sponsorblock_group)
        sponsorblock_layout.addStretch()
        
        # Chapters Tab
        chapters_tab = QWidget()
        chapters_layout = QVBoxLayout(chapters_tab)
        chapters_layout.setContentsMargins(5, 5, 5, 5)
        tab_widget.addTab(chapters_tab, "Chapters")
        
        # Chapters settings
        chapters_group = QGroupBox("Chapter Handling")
        chapters_group_layout = QVBoxLayout(chapters_group)
        chapters_group_layout.setContentsMargins(10, 15, 10, 15)
        
        self.chapters_none = QRadioButton("No chapter handling")
        self.chapters_embed = QRadioButton("Embed chapters in file")
        self.chapters_split = QRadioButton("Split by chapters (create multiple files)")
        
        # Set current selection
        if self.settings.CHAPTERS_MODE == "none":
            self.chapters_none.setChecked(True)
        elif self.settings.CHAPTERS_MODE == "embed":
            self.chapters_embed.setChecked(True)
        elif self.settings.CHAPTERS_MODE == "split":
            self.chapters_split.setChecked(True)
        
        chapters_group_layout.addWidget(self.chapters_none)
        chapters_group_layout.addWidget(self.chapters_embed)
        chapters_group_layout.addWidget(self.chapters_split)
        chapters_group_layout.addStretch()
        chapters_group.setLayout(chapters_group_layout)
        chapters_layout.addWidget(chapters_group)
        chapters_layout.addStretch()
        
        # Subtitles Tab
        subtitles_tab = QWidget()
        subtitles_layout = QVBoxLayout(subtitles_tab)
        subtitles_layout.setContentsMargins(5, 5, 5, 5)
        tab_widget.addTab(subtitles_tab, "Subtitles")
        
        # Subtitle settings
        subtitles_group = QGroupBox("Subtitle Options")
        subtitles_group_layout = QFormLayout(subtitles_group)
        subtitles_group_layout.setContentsMargins(10, 15, 10, 15)
        
        self.subtitles_enabled = QCheckBox("Download subtitles")
        self.subtitles_enabled.setChecked(self.settings.WRITE_SUBS)
        subtitles_group_layout.addRow(self.subtitles_enabled)
        
        self.languages_input = QLineEdit(self.settings.SUB_LANGS)
        self.languages_input.setPlaceholderText("en,es,fr (comma separated)")
        subtitles_group_layout.addRow("Languages:", self.languages_input)
        
        self.auto_subs = QCheckBox("Include auto-generated subtitles")
        self.auto_subs.setChecked(self.settings.WRITE_AUTO_SUBS)
        subtitles_group_layout.addRow(self.auto_subs)
        
        self.convert_subs = QCheckBox("Convert subtitles to SRT format")
        self.convert_subs.setChecked(self.settings.CONVERT_SUBS_TO_SRT)
        subtitles_group_layout.addRow(self.convert_subs)
        
        subtitles_group.setLayout(subtitles_group_layout)
        subtitles_layout.addWidget(subtitles_group)
        subtitles_layout.addStretch()
        
        # Playlist Tab
        playlist_tab = QWidget()
        playlist_layout = QVBoxLayout(playlist_tab)
        playlist_layout.setContentsMargins(5, 5, 5, 5)
        tab_widget.addTab(playlist_tab, "Playlist")
        
        # Playlist settings
        playlist_group = QGroupBox("Playlist Options")
        playlist_group_layout = QFormLayout(playlist_group)
        playlist_group_layout.setContentsMargins(10, 15, 10, 15)
        
        self.enable_archive = QCheckBox("Enable download archive")
        self.enable_archive.setChecked(self.settings.ENABLE_ARCHIVE)
        playlist_group_layout.addRow(self.enable_archive)
        
        self.archive_path_input = QLineEdit(str(self.settings.ARCHIVE_PATH))
        self.archive_path_input.setReadOnly(True)
        self.btn_browse_archive = QPushButton("Browse...")
        self.btn_browse_archive.setStyleSheet(AppStyles.BUTTON_STYLE.format(
            bg_color=AppStyles.INFO_COLOR, text_color="white", hover_color="#81d4fa"))
        playlist_group_layout.addRow("Archive File:", self.archive_path_input)
        playlist_group_layout.addRow(self.btn_browse_archive)
        
        self.playlist_reverse = QCheckBox("Reverse playlist order")
        self.playlist_reverse.setChecked(self.settings.PLAYLIST_REVERSE)
        playlist_group_layout.addRow(self.playlist_reverse)
        
        self.playlist_items = QLineEdit(self.settings.PLAYLIST_ITEMS)
        self.playlist_items.setPlaceholderText("e.g., 1,5-10,15")
        playlist_group_layout.addRow("Playlist Items:", self.playlist_items)
        
        playlist_layout.addWidget(playlist_group)
        playlist_layout.addStretch()
        
        # Post-Processing Tab
        post_tab = QWidget()
        post_layout = QVBoxLayout(post_tab)
        post_layout.setContentsMargins(5, 5, 5, 5)
        tab_widget.addTab(post_tab, "Post-Processing")
        
        # Post-processing settings
        post_group = QGroupBox("Post-Processing Options")
        post_group_layout = QFormLayout(post_group)
        post_group_layout.setContentsMargins(10, 15, 10, 15)
        
        self.audio_normalize = QCheckBox("Normalize audio volume")
        self.audio_normalize.setChecked(self.settings.AUDIO_NORMALIZE)
        post_group_layout.addRow(self.audio_normalize)
        
        self.add_metadata = QCheckBox("Add metadata to files")
        self.add_metadata.setChecked(self.settings.ADD_METADATA)
        post_group_layout.addRow(self.add_metadata)
        
        self.custom_ffmpeg = QLineEdit(self.settings.CUSTOM_FFMPEG_ARGS)
        self.custom_ffmpeg.setPlaceholderText("e.g., -c:v libx265 -crf 23")
        post_group_layout.addRow("Custom FFmpeg Args:", self.custom_ffmpeg)
        
        post_layout.addWidget(post_group)
        post_layout.addStretch()
        
        # Output Tab
        output_tab = QWidget()
        output_layout = QVBoxLayout(output_tab)
        output_layout.setContentsMargins(5, 5, 5, 5)
        tab_widget.addTab(output_tab, "Output")
        
        # Output settings
        output_group = QGroupBox("Output Options")
        output_group_layout = QFormLayout(output_group)
        output_group_layout.setContentsMargins(10, 15, 10, 15)
        
        self.organize_uploader = QCheckBox("Organize by uploader (creates folders)")
        self.organize_uploader.setChecked(self.settings.ORGANIZE_BY_UPLOADER)
        output_group_layout.addRow(self.organize_uploader)
        
        self.date_after = QLineEdit(self.settings.DATEAFTER)
        self.date_after.setPlaceholderText("YYYYMMDD")
        output_group_layout.addRow("Only Download After:", self.date_after)
        
        self.btn_date_picker = QPushButton("Select Date...")
        self.btn_date_picker.setStyleSheet(AppStyles.BUTTON_STYLE.format(
            bg_color=AppStyles.INFO_COLOR, text_color="white", hover_color="#81d4fa"))
        output_group_layout.addRow(self.btn_date_picker)
        
        output_layout.addWidget(output_group)
        output_layout.addStretch()
        
        # Experimental Tab
        exp_tab = QWidget()
        exp_layout = QVBoxLayout(exp_tab)
        exp_layout.setContentsMargins(5, 5, 5, 5)
        tab_widget.addTab(exp_tab, "Experimental")
        
        # Experimental settings
        exp_group = QGroupBox("Experimental Features")
        exp_group_layout = QFormLayout(exp_group)
        exp_group_layout.setContentsMargins(10, 15, 10, 15)
        
        self.live_stream = QCheckBox("Record live streams from start")
        self.live_stream.setChecked(self.settings.LIVE_FROM_START)
        exp_group_layout.addRow(self.live_stream)
        
        self.yt_music = QCheckBox("Enhanced YouTube Music metadata")
        self.yt_music.setChecked(self.settings.YT_MUSIC_METADATA)
        exp_group_layout.addRow(self.yt_music)
        
        exp_layout.addWidget(exp_group)
        exp_layout.addStretch()
        
        # Clip Settings
        clip_tab = QWidget()
        clip_layout = QVBoxLayout(clip_tab)
        clip_layout.setContentsMargins(5, 5, 5, 5)
        tab_widget.addTab(clip_tab, "Clip Extraction")
        
        # Clip settings
        clip_group = QGroupBox("Clip Options")
        clip_group_layout = QFormLayout(clip_group)
        clip_group_layout.setContentsMargins(10, 15, 10, 15)
        
        self.clip_start = QLineEdit(self.settings.CLIP_START)
        self.clip_start.setPlaceholderText("HH:MM:SS or seconds")
        clip_group_layout.addRow("Start Time:", self.clip_start)
        
        self.clip_end = QLineEdit(self.settings.CLIP_END)
        self.clip_end.setPlaceholderText("HH:MM:SS or seconds")
        clip_group_layout.addRow("End Time:", self.clip_end)
        
        clip_layout.addWidget(clip_group)
        clip_layout.addStretch()
        
        # Connect signals for dynamic behavior
        self.subtitles_enabled.toggled.connect(self._update_subtitle_controls)
        self.enable_archive.toggled.connect(self._update_archive_controls)
        self._update_subtitle_controls(self.settings.WRITE_SUBS)
        self._update_archive_controls(self.settings.ENABLE_ARCHIVE)
        
        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.setStyleSheet("QPushButton { min-width: 80px; }")
        button_box.accepted.connect(self._validate_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # Connect signals
        self.btn_browse_cookies.clicked.connect(self.browse_cookies)
        self.btn_browse_archive.clicked.connect(self.browse_archive)
        self.btn_date_picker.clicked.connect(self.select_date)
    
    def _update_subtitle_controls(self, enabled: bool):
        """Enable/disable subtitle controls based on main checkbox."""
        self.languages_input.setEnabled(enabled)
        self.auto_subs.setEnabled(enabled)
        self.convert_subs.setEnabled(enabled)
        
    def _update_archive_controls(self, enabled: bool):
        """Enable/disable archive controls based on main checkbox."""
        self.archive_path_input.setEnabled(enabled)
        self.btn_browse_archive.setEnabled(enabled)
        
    def _validate_and_accept(self):
        """Validate settings before accepting the dialog."""
        # Validate proxy URL if provided
        proxy_url = self.proxy_input.text().strip()
        if proxy_url:
            if not (proxy_url.startswith("http://") or proxy_url.startswith("socks5://")):
                QMessageBox.warning(self, "Invalid Proxy", 
                                  "Proxy URL must start with http:// or socks5://")
                return
        
        # Validate subtitle languages if enabled
        if self.subtitles_enabled.isChecked():
            langs = self.languages_input.text().strip()
            if not langs:
                QMessageBox.warning(self, "Missing Languages", 
                                  "Please specify at least one language code")
                return
            if not all(len(lang.strip()) == 2 for lang in langs.split(",")):
                QMessageBox.warning(self, "Invalid Languages", 
                                  "Language codes should be 2 letters (e.g., en,es,fr)")
                return
        
        # Validate date format
        date_str = self.date_after.text().strip()
        if date_str:
            try:
                datetime.datetime.strptime(date_str, "%Y%m%d")
            except ValueError:
                QMessageBox.warning(self, "Invalid Date", 
                                  "Date must be in YYYYMMDD format (e.g., 20230101)")
                return
                
        self.accept()
        
    def browse_cookies(self):
        """Open file dialog to select cookies file."""
        path, _ = QFileDialog.getOpenFileName(
            self, 
            "Select Cookies File", 
            str(self.settings.BASE_DIR), 
            "Text Files (*.txt);;All Files (*)"
        )
        if path:
            self.cookies_path_input.setText(path)
    
    def browse_archive(self):
        """Open file dialog to select archive file."""
        path, _ = QFileDialog.getOpenFileName(
            self, 
            "Select Archive File", 
            str(self.settings.BASE_DIR), 
            "Text Files (*.txt);;All Files (*)"
        )
        if path:
            self.archive_path_input.setText(path)
            
    def select_date(self):
        """Open calendar dialog to select date."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Date")
        dialog.setMinimumSize(300, 250)
        layout = QVBoxLayout(dialog)
        
        calendar = QCalendarWidget()
        calendar.setGridVisible(True)
        layout.addWidget(calendar)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec() == QDialog.Accepted:
            selected_date = calendar.selectedDate()
            self.date_after.setText(selected_date.toString("yyyyMMdd"))
    
    def get_settings(self) -> dict:
        """Return the settings from the dialog."""
        # Network
        proxy_url = self.proxy_input.text().strip()
        cookies_path = Path(self.cookies_path_input.text().strip())
        cookies_browser = self.cookies_browser_combo.currentText().strip()
        
        # SponsorBlock
        sponsorblock_categories = []
        for code, cb in self.category_checkboxes.items():
            if cb.isChecked():
                sponsorblock_categories.append(code)
        
        # Chapters
        chapters_mode = "none"
        if self.chapters_embed.isChecked():
            chapters_mode = "embed"
        elif self.chapters_split.isChecked():
            chapters_mode = "split"
        
        # Subtitles
        write_subs = self.subtitles_enabled.isChecked()
        sub_langs = self.languages_input.text().strip()
        write_auto_subs = self.auto_subs.isChecked()
        convert_subs = self.convert_subs.isChecked()
        
        # Playlist
        enable_archive = self.enable_archive.isChecked()
        archive_path = Path(self.archive_path_input.text().strip())
        playlist_reverse = self.playlist_reverse.isChecked()
        playlist_items = self.playlist_items.text().strip()
        
        # Post-processing
        audio_normalize = self.audio_normalize.isChecked()
        add_metadata = self.add_metadata.isChecked()
        custom_ffmpeg = self.custom_ffmpeg.text().strip()
        
        # Output
        organize_uploader = self.organize_uploader.isChecked()
        date_after = self.date_after.text().strip()
        
        # Experimental
        live_stream = self.live_stream.isChecked()
        yt_music = self.yt_music.isChecked()
        
        # Clip
        clip_start = self.clip_start.text().strip()
        clip_end = self.clip_end.text().strip()
        
        # Network
        limit_rate = self.limit_rate_input.text().strip()
        retries = self.retries_spin.value()
        
        return {
            "PROXY_URL": proxy_url,
            "COOKIES_PATH": cookies_path,
            "COOKIES_FROM_BROWSER": cookies_browser,
            "SPONSORBLOCK_CATEGORIES": sponsorblock_categories,
            "CHAPTERS_MODE": chapters_mode,
            "WRITE_SUBS": write_subs,
            "SUB_LANGS": sub_langs,
            "WRITE_AUTO_SUBS": write_auto_subs,
            "CONVERT_SUBS_TO_SRT": convert_subs,
            "ENABLE_ARCHIVE": enable_archive,
            "ARCHIVE_PATH": archive_path,
            "PLAYLIST_REVERSE": playlist_reverse,
            "PLAYLIST_ITEMS": playlist_items,
            "AUDIO_NORMALIZE": audio_normalize,
            "ADD_METADATA": add_metadata,
            "CUSTOM_FFMPEG_ARGS": custom_ffmpeg,
            "ORGANIZE_BY_UPLOADER": organize_uploader,
            "DATEAFTER": date_after,
            "LIVE_FROM_START": live_stream,
            "YT_MUSIC_METADATA": yt_music,
            "CLIP_START": clip_start,
            "CLIP_END": clip_end,
            "LIMIT_RATE": limit_rate,
            "RETRIES": retries
        }

# --- Services / Workers ---

class TitleFetcher(QObject):
    """Fetches video/playlist titles using yt-dlp in a separate thread."""
    title_fetched = Signal(str, str)  # url, title
    error = Signal(str, str)         # url, error message
    finished = Signal()              # Signal that the operation is complete

    def __init__(self, url: str, cookies_path: Path, ffprobe_path: Path, proxy_url: str):
        super().__init__()
        self.url = url
        self.cookies_path = cookies_path
        self.ffprobe_path = ffprobe_path
        self.proxy_url = proxy_url

    def run(self):
        """Executes yt-dlp to get video/playlist metadata."""
        try:
            cmd = [
                str(self.ffprobe_path.parent / "yt-dlp.exe"),
                "--ffmpeg-location", str(self.ffprobe_path.parent),
                "--skip-download",
                "--print-json",
                "--ignore-errors",  # Continue if one item in playlist fails
                "--flat-playlist",   # Only get playlist info, not all videos
                self.url
            ]
            
            # Include cookies if available
            if self.cookies_path.exists() and self.cookies_path.stat().st_size > 0:
                cmd.extend(["--cookies", str(self.cookies_path)])
            
            # Add proxy if configured
            if self.proxy_url:
                cmd.extend(["--proxy", self.proxy_url])

            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=120,  # Increased timeout for playlists
                startupinfo=startupinfo,
                encoding='utf-8'
            )

            if proc.returncode != 0:
                error_msg = proc.stderr.strip() or "Unknown error from yt-dlp"
                self.error.emit(self.url, error_msg)
                self.finished.emit()
                return

            output = proc.stdout.strip()
            if not output:
                self.error.emit(self.url, "No metadata received from yt-dlp")
                self.finished.emit()
                return

            # Get first line of output (works for both single videos and playlists)
            first_line = output.splitlines()[0]
            info = json.loads(first_line)
            
            # Prefer playlist title if available, otherwise fall back to video title
            title = info.get("playlist_title") or info.get("title", "Unknown Title")
            
            # For playlists, append "[Playlist]" to the title
            if "playlist_title" in info:
                title = f"{title} [Playlist]"
            
            self.title_fetched.emit(self.url, title)
            self.finished.emit()
            
        except subprocess.TimeoutExpired:
            self.error.emit(self.url, "Timeout while fetching metadata (120 seconds)")
            self.finished.emit()
        except json.JSONDecodeError as e:
            self.error.emit(self.url, f"Failed to parse metadata: {str(e)}")
            self.finished.emit()
        except Exception as e:
            self.error.emit(self.url, f"An unexpected error occurred: {str(e)}")
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
        cmd = [str(self.settings.YT_DLP_PATH), "--no-warnings", "--progress"]
        format_code = self.item["format_code"]
        is_playlist = "list=" in self.item["url"] or format_code in ["playlist_mp3", "youtube_music"]
        is_audio = format_code in ["bestaudio", "playlist_mp3", "youtube_music"]

        # Add cookies if available
        if self.settings.COOKIES_PATH.exists() and self.settings.COOKIES_PATH.stat().st_size > 0:
            cmd.extend(["--cookies", str(self.settings.COOKIES_PATH)])
            
        # Add browser cookies if specified
        if self.settings.COOKIES_FROM_BROWSER:
            cmd.extend(["--cookies-from-browser", self.settings.COOKIES_FROM_BROWSER])
            
        # Add proxy if configured
        if self.settings.PROXY_URL:
            cmd.extend(["--proxy", self.settings.PROXY_URL])
            
        # Add rate limiting
        if self.settings.LIMIT_RATE:
            cmd.extend(["--limit-rate", self.settings.LIMIT_RATE])
            
        # Add retry settings
        cmd.extend(["--retries", str(self.settings.RETRIES)])
            
        # Add date filter
        if self.settings.DATEAFTER:
            cmd.extend(["--dateafter", self.settings.DATEAFTER])
            
        # Add live stream option
        if self.settings.LIVE_FROM_START:
            cmd.append("--live-from-start")
            
        # Set ffmpeg location to our _internal directory
        cmd.extend(["--ffmpeg-location", str(self.settings.FFMPEG_PATH.parent)])

        # Add ignore-errors flag for playlists
        if is_playlist:
            cmd.append("--ignore-errors")
            
        # Add download archive if enabled
        if self.settings.ENABLE_ARCHIVE:
            cmd.extend(["--download-archive", str(self.settings.ARCHIVE_PATH)])
            
        # Add playlist reverse
        if self.settings.PLAYLIST_REVERSE:
            cmd.append("--playlist-reverse")
            
        # Add playlist items selection
        if self.settings.PLAYLIST_ITEMS:
            cmd.extend(["--playlist-items", self.settings.PLAYLIST_ITEMS])
            
        # Add clip extraction
        if self.settings.CLIP_START and self.settings.CLIP_END:
            cmd.extend(["--download-sections", f"*{self.settings.CLIP_START}-{self.settings.CLIP_END}"])

        if is_playlist:
            cmd.extend(["--yes-playlist", "-o", self.settings.PLAYLIST_TEMPLATE])
        else:
            cmd.extend(["-o", self.settings.OUTPUT_TEMPLATE])
            
        # Apply organization by uploader
        if self.settings.ORGANIZE_BY_UPLOADER:
            if is_playlist:
                cmd[-1] = str(self.settings.DOWNLOADS_DIR / "%(uploader)s" / "%(playlist_index)s - %(title)s.%(ext)s")
            else:
                cmd[-1] = str(self.settings.DOWNLOADS_DIR / "%(uploader)s" / "%(title)s.%(ext)s")

        # Audio-specific settings
        if is_audio:
            cmd.extend([
                "-f", "bestaudio",
                "--extract-audio",
                "--audio-format", "mp3",
                "--audio-quality", "0",
                "--embed-thumbnail",
            ])
            
            # Add metadata if enabled
            if self.settings.ADD_METADATA:
                cmd.append("--add-metadata")
                
            # YouTube Music metadata enhancement
            if format_code == "youtube_music" and self.settings.YT_MUSIC_METADATA:
                cmd.extend([
                    "--parse-metadata", "description:(?s)(?P<meta_comment>.+)",
                    "--parse-metadata", "%(meta_comment)s:(?P<artist>.+) - .+",
                    "--parse-metadata", "%(meta_comment)s:.+ - (?P<title>.+)"
                ])
                
            # Audio normalization
            if self.settings.AUDIO_NORMALIZE:
                cmd.append("--audio-normalize")
        else:
            # Video-specific settings
            cmd.extend(["-f", format_code, "--merge-output-format", "mkv"])
            
            # Add metadata if enabled
            if self.settings.ADD_METADATA:
                cmd.append("--add-metadata")
                
        # Add SponsorBlock integration if categories are selected
        if self.settings.SPONSORBLOCK_CATEGORIES:
            categories = ",".join(self.settings.SPONSORBLOCK_CATEGORIES)
            cmd.extend(["--sponsorblock-remove", categories])
            
        # Add chapters handling
        if self.settings.CHAPTERS_MODE == "split":
            cmd.append("--split-chapters")
        elif self.settings.CHAPTERS_MODE == "embed":
            cmd.append("--embed-chapters")
            
        # Add subtitle handling
        if self.settings.WRITE_SUBS:
            cmd.append("--write-subs")
            
            if self.settings.SUB_LANGS:
                cmd.extend(["--sub-langs", self.settings.SUB_LANGS])
                
            if self.settings.WRITE_AUTO_SUBS:
                cmd.append("--write-auto-subs")
                
            if self.settings.CONVERT_SUBS_TO_SRT:
                cmd.extend(["--convert-subs", "srt"])
                
        # Add custom FFmpeg arguments
        if self.settings.CUSTOM_FFMPEG_ARGS:
            cmd.extend(["--exec", f"ffmpeg -i {{}} {self.settings.CUSTOM_FFMPEG_ARGS} {{}}.out && move /Y {{}}.out {{}}"])
        
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

# --- Advanced Options Dialog ---
class AdvancedOptionsDialog(QDialog):
    """Dialog for configuring clip extraction and playlist options."""
    def __init__(self, parent: QWidget, settings: AppSettings):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Advanced Options")
        self.setStyleSheet(AppStyles.DIALOG_STYLE)
        self.setMinimumSize(400, 300)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Clip extraction group
        clip_group = QGroupBox("Clip Extraction")
        clip_layout = QFormLayout(clip_group)
        
        self.clip_start = QLineEdit(self.settings.CLIP_START)
        self.clip_start.setPlaceholderText("HH:MM:SS or seconds")
        clip_layout.addRow("Start Time:", self.clip_start)
        
        self.clip_end = QLineEdit(self.settings.CLIP_END)
        self.clip_end.setPlaceholderText("HH:MM:SS or seconds")
        clip_layout.addRow("End Time:", self.clip_end)
        
        layout.addWidget(clip_group)
        
        # Playlist options group
        playlist_group = QGroupBox("Playlist Options")
        playlist_layout = QFormLayout(playlist_group)
        
        self.playlist_items = QLineEdit(self.settings.PLAYLIST_ITEMS)
        self.playlist_items.setPlaceholderText("e.g., 1,5-10,15")
        playlist_layout.addRow("Items to Download:", self.playlist_items)
        
        self.playlist_reverse = QCheckBox("Reverse playlist order")
        self.playlist_reverse.setChecked(self.settings.PLAYLIST_REVERSE)
        playlist_layout.addRow(self.playlist_reverse)
        
        layout.addWidget(playlist_group)
        
        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
    def get_options(self) -> dict:
        """Return the options from the dialog."""
        return {
            "CLIP_START": self.clip_start.text().strip(),
            "CLIP_END": self.clip_end.text().strip(),
            "PLAYLIST_ITEMS": self.playlist_items.text().strip(),
            "PLAYLIST_REVERSE": self.playlist_reverse.isChecked()
        }

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
        self._log_settings()

    def _log_settings(self):
        """Log current settings to output window."""
        self.log("💡 Welcome to YTGet! Paste a URL to begin.\n", AppStyles.INFO_COLOR)
        self.log(f"📂 Download folder: {self.settings.DOWNLOADS_DIR}\n", AppStyles.INFO_COLOR)
        self.log(f"🔧 Using ffmpeg from: {self.settings.FFMPEG_PATH}\n", AppStyles.INFO_COLOR)
        
        # Log settings status
        if self.settings.PROXY_URL:
            self.log(f"🌐 Using proxy: {self.settings.PROXY_URL}\n", AppStyles.INFO_COLOR)
        if self.settings.SPONSORBLOCK_CATEGORIES:
            cats = ", ".join(self.settings.SPONSORBLOCK_CATEGORIES)
            self.log(f"⏩ SponsorBlock enabled for: {cats}\n", AppStyles.INFO_COLOR)
        if self.settings.CHAPTERS_MODE != "none":
            self.log(f"📖 Chapters handling: {self.settings.CHAPTERS_MODE}\n", AppStyles.INFO_COLOR)
        if self.settings.WRITE_SUBS:
            self.log(f"📝 Subtitle download enabled for: {self.settings.SUB_LANGS}\n", AppStyles.INFO_COLOR)
        if self.settings.ENABLE_ARCHIVE:
            self.log(f"📚 Download archive enabled: {self.settings.ARCHIVE_PATH}\n", AppStyles.INFO_COLOR)
        if self.settings.PLAYLIST_REVERSE:
            self.log(f"↩️ Playlist reverse order enabled\n", AppStyles.INFO_COLOR)
        if self.settings.AUDIO_NORMALIZE:
            self.log(f"🔊 Audio normalization enabled\n", AppStyles.INFO_COLOR)
        if self.settings.LIMIT_RATE:
            self.log(f"📉 Rate limiting: {self.settings.LIMIT_RATE}\n", AppStyles.INFO_COLOR)
        if self.settings.ORGANIZE_BY_UPLOADER:
            self.log(f"🗂️ Organizing by uploader\n", AppStyles.INFO_COLOR)
        if self.settings.DATEAFTER:
            self.log(f"📅 Only downloading after: {self.settings.DATEAFTER}\n", AppStyles.INFO_COLOR)
        if self.settings.LIVE_FROM_START:
            self.log(f"🔴 Live stream recording enabled\n", AppStyles.INFO_COLOR)
        if self.settings.YT_MUSIC_METADATA:
            self.log(f"🎵 Enhanced YouTube Music metadata enabled\n", AppStyles.INFO_COLOR)
        if self.settings.CLIP_START and self.settings.CLIP_END:
            self.log(f"⏱️ Clip extraction: {self.settings.CLIP_START}-{self.settings.CLIP_END}\n", AppStyles.INFO_COLOR)

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
        format_row = QHBoxLayout()
        self.format_box = QComboBox()
        self.format_box.addItems(self.settings.RESOLUTIONS.keys())
        self.format_box.setStyleSheet("padding: 8px; font-size: 15px;")
        format_row.addWidget(self.format_box, 3)
        
        self.btn_advanced = QPushButton("⚙️ Advanced")
        self.btn_advanced.setStyleSheet(AppStyles.BUTTON_STYLE.format(
            bg_color=AppStyles.INFO_COLOR, text_color="white", hover_color="#81d4fa"))
        format_row.addWidget(self.btn_advanced, 1)
        right_layout.addLayout(format_row)

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
        
        # Set initial splitter sizes (1/3 for queue, 2/3 for controls)
        QTimer.singleShot(100, lambda: splitter.setSizes([self.width()//3, self.width()*2//3]))

    def _setup_connections(self):
        """Connects widget signals to handler slots."""
        self.url_input.textChanged.connect(self._on_url_text_changed)
        self.url_input.returnPressed.connect(self._add_to_queue)
        self.btn_add_queue.clicked.connect(self._add_to_queue)
        self.btn_start_queue.clicked.connect(self._start_queue)
        self.btn_pause_queue.clicked.connect(self._pause_queue)
        self.btn_advanced.clicked.connect(self._show_advanced_options)

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
        settings_menu.addAction("Preferences...", self._show_preferences, "Ctrl+P")
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
        self.title_fetcher = TitleFetcher(
            url, 
            self.settings.COOKIES_PATH, 
            self.settings.FFPROBE_PATH,
            self.settings.PROXY_URL
        )
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
        
    def _show_preferences(self):
        """Show preferences dialog to configure advanced options."""
        dialog = PreferencesDialog(self, self.settings)
        if dialog.exec() == QDialog.Accepted:
            new_settings = dialog.get_settings()
            
            # Update settings
            self.settings.PROXY_URL = new_settings["PROXY_URL"]
            self.settings.COOKIES_PATH = new_settings["COOKIES_PATH"]
            self.settings.COOKIES_FROM_BROWSER = new_settings["COOKIES_FROM_BROWSER"]
            self.settings.SPONSORBLOCK_CATEGORIES = new_settings["SPONSORBLOCK_CATEGORIES"]
            self.settings.CHAPTERS_MODE = new_settings["CHAPTERS_MODE"]
            self.settings.WRITE_SUBS = new_settings["WRITE_SUBS"]
            self.settings.SUB_LANGS = new_settings["SUB_LANGS"]
            self.settings.WRITE_AUTO_SUBS = new_settings["WRITE_AUTO_SUBS"]
            self.settings.CONVERT_SUBS_TO_SRT = new_settings["CONVERT_SUBS_TO_SRT"]
            self.settings.ENABLE_ARCHIVE = new_settings["ENABLE_ARCHIVE"]
            self.settings.ARCHIVE_PATH = new_settings["ARCHIVE_PATH"]
            self.settings.PLAYLIST_REVERSE = new_settings["PLAYLIST_REVERSE"]
            self.settings.PLAYLIST_ITEMS = new_settings["PLAYLIST_ITEMS"]
            self.settings.AUDIO_NORMALIZE = new_settings["AUDIO_NORMALIZE"]
            self.settings.ADD_METADATA = new_settings["ADD_METADATA"]
            self.settings.CUSTOM_FFMPEG_ARGS = new_settings["CUSTOM_FFMPEG_ARGS"]
            self.settings.ORGANIZE_BY_UPLOADER = new_settings["ORGANIZE_BY_UPLOADER"]
            self.settings.DATEAFTER = new_settings["DATEAFTER"]
            self.settings.LIVE_FROM_START = new_settings["LIVE_FROM_START"]
            self.settings.YT_MUSIC_METADATA = new_settings["YT_MUSIC_METADATA"]
            self.settings.CLIP_START = new_settings["CLIP_START"]
            self.settings.CLIP_END = new_settings["CLIP_END"]
            self.settings.LIMIT_RATE = new_settings["LIMIT_RATE"]
            self.settings.RETRIES = new_settings["RETRIES"]
            
            # Save to config
            self.settings.save_config()
            
            # Log changes
            self.log("⚙️ Settings updated and saved to config\n", AppStyles.INFO_COLOR)
            self._log_settings()

    def _show_advanced_options(self):
        """Show advanced options dialog for clip extraction and playlist settings."""
        dialog = AdvancedOptionsDialog(self, self.settings)
        if dialog.exec() == QDialog.Accepted:
            options = dialog.get_options()
            self.settings.CLIP_START = options["CLIP_START"]
            self.settings.CLIP_END = options["CLIP_END"]
            self.settings.PLAYLIST_ITEMS = options["PLAYLIST_ITEMS"]
            self.settings.PLAYLIST_REVERSE = options["PLAYLIST_REVERSE"]
            self.settings.save_config()
            
            self.log("⚙️ Advanced options updated\n", AppStyles.INFO_COLOR)
            if self.settings.CLIP_START and self.settings.CLIP_END:
                self.log(f"⏱️ Clip extraction set: {self.settings.CLIP_START}-{self.settings.CLIP_END}\n", AppStyles.INFO_COLOR)
            if self.settings.PLAYLIST_ITEMS:
                self.log(f"🎬 Playlist items set: {self.settings.PLAYLIST_ITEMS}\n", AppStyles.INFO_COLOR)
            if self.settings.PLAYLIST_REVERSE:
                self.log("↩️ Playlist reverse order enabled\n", AppStyles.INFO_COLOR)

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
