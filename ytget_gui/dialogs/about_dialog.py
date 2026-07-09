# File: ytget_gui/dialogs/about_dialog.py

from __future__ import annotations

import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QTextBrowser, QGroupBox,
    QGridLayout, QFrame
)

from ytget_gui.settings import AppSettings


class AboutDialog(QDialog):

    def __init__(self, settings: AppSettings, app_icon, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._app_icon = app_icon
        self.init_ui()

    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle(f"About {self.settings.APP_NAME}")
        self.setModal(True)
        self.setMinimumSize(600, 500)
        self.resize(650, 550)

        if self._app_icon:
            self.setWindowIcon(self._app_icon)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Header section
        header_layout = QHBoxLayout()
        if self._app_icon:
            icon_label = QLabel()
            icon_label.setPixmap(self._app_icon.pixmap(64, 64))
            header_layout.addWidget(icon_label)

        title_layout = QVBoxLayout()
        app_title = QLabel(self.settings.APP_NAME)
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        app_title.setFont(title_font)
        title_layout.addWidget(app_title)

        version_label = QLabel(f"Version {self.settings.VERSION}")
        version_label.setStyleSheet("color: #666;")
        title_layout.addWidget(version_label)

        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(separator)

        # Tab widget
        self.tab_widget = QTabWidget()
        self.create_about_tab()
        self.create_license_tab()
        main_layout.addWidget(self.tab_widget)

        # Bottom buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        main_layout.addLayout(button_layout)

    def create_about_tab(self):
        """Create the About tab with project description and links."""
        about_widget = QWidget()
        layout = QVBoxLayout(about_widget)
        layout.setSpacing(15)

        desc_label = QLabel(
            "A modern, lightweight, and user-friendly desktop application "
            "for downloading YouTube videos, playlists, and music.\n\n"
            "Built with Python and PySide6, powered by yt-dlp."
        )
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # Features
        features_group = QGroupBox("Key Features")
        features_layout = QVBoxLayout(features_group)
        features = [
            "• Download videos in multiple formats and qualities",
            "• Extract audio as MP3 or other formats",
            "• Support for playlists and channels",
            "• Queue system for batch downloads",
            "• Cross-platform support (Windows, macOS, Linux)",
            "• Built-in update management"
        ]
        for feature in features:
            features_layout.addWidget(QLabel(feature))
        layout.addWidget(features_group)

        # Links
        links_group = QGroupBox("Links")
        links_layout = QGridLayout(links_group)
        github_link = QLabel('<a href="https://github.com/ErfanNamira/ytget-gui">GitHub Repository</a>')
        github_link.setOpenExternalLinks(True)
        github_link.setTextFormat(Qt.RichText)
        links_layout.addWidget(QLabel("Source Code:"), 0, 0)
        links_layout.addWidget(github_link, 0, 1)

        issue_link = QLabel('<a href="https://github.com/ErfanNamira/ytget-gui/issues">Report an Issue</a>')
        issue_link.setOpenExternalLinks(True)
        issue_link.setTextFormat(Qt.RichText)
        links_layout.addWidget(QLabel("Report Issue:"), 1, 0)
        links_layout.addWidget(issue_link, 1, 1)

        docs_link = QLabel('<a href="https://github.com/ErfanNamira/ytget-gui#readme">Documentation</a>')
        docs_link.setOpenExternalLinks(True)
        docs_link.setTextFormat(Qt.RichText)
        links_layout.addWidget(QLabel("Documentation:"), 2, 0)
        links_layout.addWidget(docs_link, 2, 1)

        layout.addWidget(links_group)

        # Credits
        credits_label = QLabel(
            "<b>Credits:</b><br>"
            "• yt-dlp - YouTube downloader engine<br>"
            "• PySide6 - Qt for Python framework"
        )
        credits_label.setWordWrap(True)
        layout.addWidget(credits_label)

        layout.addStretch()
        self.tab_widget.addTab(about_widget, "About")

    def create_license_tab(self):
        """Create the License tab."""
        license_widget = QWidget()
        layout = QVBoxLayout(license_widget)
        license_text = QTextBrowser()
        license_text.setPlainText(self.get_license_text())
        layout.addWidget(license_text)
        self.tab_widget.addTab(license_widget, "License")

    def get_license_text(self):
        """Return the license text."""
        return """MIT License

Copyright (c) 2026 Erfan Namira

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
