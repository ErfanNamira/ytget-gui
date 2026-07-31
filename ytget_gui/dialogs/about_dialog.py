# File: ytget_gui/dialogs/about_dialog.py

from __future__ import annotations

import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QTextBrowser, QGroupBox,
    QGridLayout, QFrame, QGraphicsDropShadowEffect
)

from ytget_gui.settings import AppSettings
from ytget_gui.styles import AppStyles


class AboutDialog(QDialog):

    def __init__(self, settings: AppSettings, app_icon, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._app_icon = app_icon
        self.init_ui()

    def init_ui(self):
        """Initialize the user interface."""
        app_name = getattr(self.settings, "APP_NAME", "Application")
        self.setWindowTitle(f"About {app_name}")
        self.setModal(True)
        self.setMinimumSize(600, 500)
        self.resize(660, 560)

        if self._app_icon:
            self.setWindowIcon(self._app_icon)

        # Glassmorphism dialog background
        self.setStyleSheet(f"""
            QDialog {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0a0e1a, stop:0.3 #15102e,
                    stop:0.6 #1e1b4b, stop:1 #0c1733);
                color: #F4F4F8;
                font-family: "Inter", "Segoe UI", sans-serif;
            }}
            QLabel {{
                color: #F4F4F8;
                background: transparent;
            }}
            QGroupBox {{
                font-weight: bold;
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 12px;
                margin-top: 1ex;
                background: rgba(255, 255, 255, 15);
                padding-top: 12px;
                color: #F4F4F8;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 8px;
                color: #00E5FF;
            }}
            QTabWidget::pane {{
                border: 1px solid rgba(255, 255, 255, 25);
                border-radius: 10px;
                background: rgba(255, 255, 255, 10);
            }}
            QTabBar::tab {{
                background: rgba(255, 255, 255, 15);
                color: rgba(255, 255, 255, 150);
                border: 1px solid rgba(255, 255, 255, 25);
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                padding: 6px 16px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: rgba(0, 229, 255, 30);
                color: #00E5FF;
                border-color: rgba(0, 229, 255, 60);
            }}
            QTabBar::tab:hover {{
                background: rgba(255, 255, 255, 25);
                color: #F4F4F8;
            }}
            QTextBrowser {{
                background: rgba(5, 5, 15, 180);
                color: rgba(255, 255, 255, 160);
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 8px;
                font-family: "JetBrains Mono", Consolas, monospace;
                font-size: 11px;
                padding: 8px;
            }}
            QPushButton {{
                background: rgba(255, 255, 255, 15);
                color: rgba(255, 255, 255, 180);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 8px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 25);
                color: #F4F4F8;
                border: 1px solid rgba(255, 255, 255, 50);
            }}
            QFrame {{
                background: transparent;
            }}
            QFrame[frameShape="4"] {{
                background: rgba(255, 255, 255, 20);
                max-height: 1px;
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Header section
        header_layout = QHBoxLayout()
        if self._app_icon:
            icon_label = QLabel()
            icon_label.setPixmap(self._app_icon.pixmap(64, 64))
            icon_label.setFixedSize(64, 64)
            # Glass icon container
            icon_label.setStyleSheet("""
                background: rgba(255, 255, 255, 15);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 16px;
            """)
            header_layout.addWidget(icon_label)

        title_layout = QVBoxLayout()
        app_title = QLabel(app_name)
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        app_title.setFont(title_font)
        app_title.setStyleSheet("color: #F4F4F8;")
        title_layout.addWidget(app_title)

        version = getattr(self.settings, "VERSION", "unknown")
        version_label = QLabel(f"Version {version}")
        version_label.setStyleSheet("color: rgba(255, 255, 255, 150); font-size: 13px;")
        title_layout.addWidget(version_label)

        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Plain)
        separator.setStyleSheet("background: rgba(255, 255, 255, 20); max-height: 1px; border: none;")
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
        about_widget.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(about_widget)
        layout.setSpacing(15)

        desc_label = QLabel(
            "A modern, lightweight, and user-friendly desktop application "
            "for downloading YouTube videos, playlists, and music.\n\n"
            "Built with Python and PySide6, powered by yt-dlp."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: rgba(255, 255, 255, 180); font-size: 13px; line-height: 1.6;")
        layout.addWidget(desc_label)

        # Features
        features_group = QGroupBox("Key Features")
        features_layout = QVBoxLayout(features_group)
        features = [
            "Download videos in multiple formats and qualities",
            "Extract audio as MP3 or other formats",
            "Support for playlists and channels",
            "Queue system for batch downloads",
            "Cross-platform support (Windows, macOS, Linux)",
            "Built-in update management",
        ]
        features_label = QLabel("\n".join(f"• {f}" for f in features))
        features_label.setWordWrap(True)
        features_label.setStyleSheet("color: rgba(255, 255, 255, 160); font-size: 12px;")
        features_layout.addWidget(features_label)
        layout.addWidget(features_group)

        # Links
        links_group = QGroupBox("Links")
        links_layout = QGridLayout(links_group)
        link_style = "color: #00E5FF; text-decoration: none;"
        
        github_link = QLabel(f'<a href="https://github.com/ErfanNamira/ytget-gui" style="color: #00E5FF;">GitHub Repository</a>')
        github_link.setOpenExternalLinks(True)
        github_link.setTextFormat(Qt.RichText)
        links_layout.addWidget(QLabel("Source Code:"), 0, 0)
        links_layout.addWidget(github_link, 0, 1)

        issue_link = QLabel(f'<a href="https://github.com/ErfanNamira/ytget-gui/issues" style="color: #00E5FF;">Report an Issue</a>')
        issue_link.setOpenExternalLinks(True)
        issue_link.setTextFormat(Qt.RichText)
        links_layout.addWidget(QLabel("Report Issue:"), 1, 0)
        links_layout.addWidget(issue_link, 1, 1)

        docs_link = QLabel(f'<a href="https://github.com/ErfanNamira/ytget-gui#readme" style="color: #00E5FF;">Documentation</a>')
        docs_link.setOpenExternalLinks(True)
        docs_link.setTextFormat(Qt.RichText)
        links_layout.addWidget(QLabel("Documentation:"), 2, 0)
        links_layout.addWidget(docs_link, 2, 1)

        layout.addWidget(links_group)

        # Credits
        credits_label = QLabel(
            "<b style='color: #F4F4F8;'>Credits:</b><br>"
            "<span style='color: rgba(255,255,255,160);'>"
            "• yt-dlp - YouTube downloader engine<br>"
            "• PySide6 - Qt for Python framework"
            "</span>"
        )
        credits_label.setWordWrap(True)
        credits_label.setTextFormat(Qt.RichText)
        layout.addWidget(credits_label)

        layout.addStretch()
        self.tab_widget.addTab(about_widget, "About")

    def create_license_tab(self):
        """Create the License tab."""
        license_widget = QWidget()
        license_widget.setStyleSheet("background: transparent;")
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
