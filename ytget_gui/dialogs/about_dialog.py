# File: ytget_gui/dialogs/about_dialog.py

from __future__ import annotations

import sys
import platform
import json
import urllib.request
import subprocess
import shutil
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QTextBrowser, QProgressBar, QGroupBox,
    QGridLayout, QFrame, QMessageBox
)

from ytget_gui.settings import AppSettings


class AboutDialog(QDialog):

    def __init__(self, settings: AppSettings, app_icon, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._app_icon = app_icon
        self.init_ui()
        self.load_dependency_status()

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
        self.create_system_tab()
        self.create_dependencies_tab()
        self.create_license_tab()
        main_layout.addWidget(self.tab_widget)

        # Bottom buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        self.update_btn = QPushButton("Check for Updates")
        self.update_btn.clicked.connect(self.check_for_updates)
        button_layout.addWidget(self.update_btn)

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

    def create_system_tab(self):
        """Create the System Information tab."""
        system_widget = QWidget()
        layout = QVBoxLayout(system_widget)

        system_group = QGroupBox("System Information")
        system_layout = QGridLayout(system_group)
        system_info = {
            "Operating System": f"{platform.system()} {platform.release()}",
            "OS Version": platform.version(),
            "Architecture": platform.machine(),
            "Python Version": platform.python_version(),
            "Processor": platform.processor() or "Not available",
            "Hostname": platform.node()
        }
        row = 0
        for key, value in system_info.items():
            key_label = QLabel(f"{key}:")
            key_label.setStyleSheet("font-weight: bold;")
            value_label = QLabel(value)
            value_label.setWordWrap(True)
            system_layout.addWidget(key_label, row, 0, Qt.AlignTop)
            system_layout.addWidget(value_label, row, 1)
            row += 1
        layout.addWidget(system_group)

        # Application paths (only CONFIG, DOWNLOADS, etc. – no temp)
        paths_group = QGroupBox("Application Paths")
        paths_layout = QGridLayout(paths_group)
        paths = {
            "Config File": str(self.settings.CONFIG_PATH),
            "Downloads Folder": str(self.settings.DOWNLOADS_DIR),
            "Cookies File": str(self.settings.COOKIES_PATH),
            "Archive File": str(self.settings.ARCHIVE_PATH),
            "Internal Dir": str(self.settings.INTERNAL_DIR)
        }
        row = 0
        for key, value in paths.items():
            key_label = QLabel(f"{key}:")
            key_label.setStyleSheet("font-weight: bold;")
            value_label = QLabel(value)
            value_label.setWordWrap(True)
            paths_layout.addWidget(key_label, row, 0, Qt.AlignTop)
            paths_layout.addWidget(value_label, row, 1)
            row += 1
        layout.addWidget(paths_group)

        layout.addStretch()
        self.tab_widget.addTab(system_widget, "System")

    def create_dependencies_tab(self):
        """Create the Dependencies tab using AppSettings resolved paths."""
        deps_widget = QWidget()
        layout = QVBoxLayout(deps_widget)

        self.deps_status_label = QLabel("Checking dependencies...")
        layout.addWidget(self.deps_status_label)

        self.deps_progress = QProgressBar()
        self.deps_progress.setVisible(False)
        layout.addWidget(self.deps_progress)

        self.deps_text = QTextBrowser()
        self.deps_text.setOpenExternalLinks(False)
        layout.addWidget(self.deps_text)

        refresh_btn = QPushButton("Refresh Dependency Status")
        refresh_btn.clicked.connect(self.load_dependency_status)
        layout.addWidget(refresh_btn)

        self.tab_widget.addTab(deps_widget, "Dependencies")

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

    def load_dependency_status(self):
        """Load and display dependency status."""
        self.deps_progress.setVisible(True)
        self.deps_progress.setRange(0, 0)
        self.deps_status_label.setText("Checking dependencies...")
        QTimer.singleShot(100, self._check_dependencies)

    def _check_dependencies(self):
        """Check all dependencies using the resolved paths from AppSettings."""
        # List of (display name, path_attr, version_func, optional_note)
        deps = [
            ("yt-dlp", "YT_DLP_PATH", self._get_ytdlp_version, "required for downloads"),
            ("FFmpeg", "FFMPEG_PATH", self._get_ffmpeg_version, "required for conversion/merging"),
            ("FFprobe", "FFPROBE_PATH", self._get_ffprobe_version, "optional (metadata)"),
            ("Deno", "DENO_PATH", self._get_deno_version, "required for advanced features"),
            ("PhantomJS", "PHANTOMJS_PATH", self._get_phantomjs_version, "optional (some extractors)")
        ]

        html = "<h3>Dependency Status</h3><table width='100%' cellpadding='5'>"
        html += "<tr><th>Dependency</th><th>Version</th><th>Location</th><th>Status</th></tr>"

        for name, attr, version_func, note in deps:
            path = getattr(self.settings, attr, None)
            version = "Not found"
            location = "Not found"
            status = "✗ Missing"
            status_color = "#f44336"
            if path and Path(path).exists():
                try:
                    version = version_func(str(path))
                    location = str(path)
                    status = "✓ Available"
                    status_color = "#4CAF50"
                except Exception as e:
                    version = f"Error: {e}"
                    location = str(path)
                    status = "✗ Failed"
                    status_color = "#ff9800"
            elif path is None:
                location = "Not configured"
            else:
                location = str(path) + " (missing)"

            html += f"""
            <tr>
                <td><b>{name}</b><br><small>{note}</small></td>
                <td>{version}</td>
                <td>{location}</td>
                <td style='color:{status_color}'>{status}</td>
            </tr>
            """

        html += "</table><br><b>Notes:</b><br>"
        html += "• Dependencies are resolved via: environment variable → system PATH → bundled in app directory<br>"
        html += "• The location column shows the exact binary path being used.<br>"

        self.deps_text.setHtml(html)
        self.deps_status_label.setText("Dependency check completed")
        self.deps_progress.setVisible(False)

    # ---------- Version retrieval helpers ----------
    def _get_ytdlp_version(self, exe_path: str) -> str:
        """Get yt-dlp version by running --version."""
        result = subprocess.run([exe_path, "--version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
        raise Exception("version check failed")

    def _get_ffmpeg_version(self, exe_path: str) -> str:
        """Get FFmpeg version."""
        result = subprocess.run([exe_path, "-version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            first_line = result.stdout.split('\n')[0]
            # e.g., "ffmpeg version 8.1.1 ..."
            parts = first_line.split()
            if len(parts) >= 3:
                return parts[2]
            return "version unknown"
        raise Exception("version check failed")

    def _get_ffprobe_version(self, exe_path: str) -> str:
        """Get FFprobe version."""
        result = subprocess.run([exe_path, "-version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            first_line = result.stdout.split('\n')[0]
            parts = first_line.split()
            if len(parts) >= 3:
                return parts[2]
            return "version unknown"
        raise Exception("version check failed")

    def _get_deno_version(self, exe_path: str) -> str:
        """Get Deno version."""
        result = subprocess.run([exe_path, "--version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            # first line: "deno 1.45.2 ..."
            first_line = result.stdout.split('\n')[0]
            parts = first_line.split()
            if len(parts) >= 2:
                return parts[1]
            return "version unknown"
        raise Exception("version check failed")

    def _get_phantomjs_version(self, exe_path: str) -> str:
        """Get PhantomJS version."""
        result = subprocess.run([exe_path, "--version"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
        raise Exception("version check failed")

    # ---------- Update checker ----------
    def check_for_updates(self):
        """Check for application updates using GitHub API."""
        self.update_btn.setEnabled(False)
        self.update_btn.setText("Checking...")
        QTimer.singleShot(2000, self._show_update_result)

    def _show_update_result(self):
        """Display update check results."""
        self.update_btn.setEnabled(True)
        self.update_btn.setText("Check for Updates")

        try:
            url = "https://api.github.com/repos/ErfanNamira/ytget-gui/releases/latest"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                latest_version = data.get('tag_name', '').lstrip('v')
                current_version = self.settings.VERSION

                if latest_version > current_version:
                    msg = QMessageBox(self)
                    msg.setWindowTitle("Update Available")
                    msg.setText(f"Version {latest_version} is available!")
                    msg.setInformativeText(
                        f"You are currently using version {current_version}.\n\n"
                        "Would you like to visit the download page?"
                    )
                    msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                    msg.setDefaultButton(QMessageBox.Yes)
                    if msg.exec() == QMessageBox.Yes:
                        QDesktopServices.openUrl(QUrl(data.get('html_url', 'https://github.com/ErfanNamira/ytget-gui')))
                else:
                    QMessageBox.information(
                        self,
                        "No Updates Available",
                        f"You are using the latest version ({current_version})."
                    )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Update Check Failed",
                f"Could not check for updates:\n{str(e)}"
            )
