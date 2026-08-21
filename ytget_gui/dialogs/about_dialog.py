# File: ytget_gui/dialogs/about_dialog.py
"""About dialog: version, environment and licence."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ytget_gui import _version
from ytget_gui.dialogs import common as ui
from ytget_gui.settings import AppSettings
from ytget_gui.utils.paths import is_frozen, platform_label

MIT_LICENCE = """MIT License

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

FEATURES: Tuple[str, ...] = (
    "Download video in any resolution yt-dlp can reach, up to 8K",
    "Extract audio as MP3, FLAC or Opus with embedded artwork",
    "Playlists, channels and Spotify links via spotdl",
    "A persistent queue that survives restarts",
    "SponsorBlock, chapters, subtitles and metadata tagging",
    "Built-in updater for yt-dlp, spotdl and deno",
)

CREDITS: Tuple[Tuple[str, str], ...] = (
    ("yt-dlp", "https://github.com/yt-dlp/yt-dlp"),
    ("spotDL", "https://github.com/spotDL/spotify-downloader"),
    ("FFmpeg", "https://ffmpeg.org"),
    ("PySide6 / Qt", "https://doc.qt.io/qtforpython"),
    ("mutagen", "https://mutagen.readthedocs.io"),
    ("Pillow", "https://python-pillow.org"),
)


class AboutDialog(QDialog):
    def __init__(
        self,
        settings: AppSettings,
        app_icon: Optional[QIcon] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self._icon = app_icon

        self.setWindowTitle(f"About {_version.APP_NAME}")
        self.setModal(True)
        self.setMinimumSize(620, 540)
        self.resize(680, 580)
        self.setStyleSheet(ui.dialog_qss())
        if app_icon is not None:
            self.setWindowIcon(app_icon)

        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(14)
        if self._icon is not None:
            badge = QLabel()
            badge.setPixmap(self._icon.pixmap(64, 64))
            badge.setFixedSize(64, 64)
            badge.setStyleSheet(
                "background: rgba(255, 255, 255, 15);"
                "border: 1px solid rgba(255, 255, 255, 30);"
                "border-radius: 16px;"
            )
            header.addWidget(badge)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        name = QLabel(_version.APP_NAME)
        font = QFont()
        font.setPointSize(20)
        font.setBold(True)
        name.setFont(font)
        version = QLabel(
            f"Version {_version.__version__}  \u00b7  {platform_label()}"
            + ("  \u00b7  packaged" if is_frozen() else "  \u00b7  from source")
        )
        version.setObjectName("dlgSubtitle")
        titles.addWidget(name)
        titles.addWidget(version)
        header.addLayout(titles)
        header.addStretch(1)
        root.addLayout(header)
        root.addWidget(ui.divider())

        tabs = QTabWidget()
        tabs.addTab(self._about_tab(), "About")
        tabs.addTab(self._environment_tab(), "Environment")
        tabs.addTab(self._licence_tab(), "Licence")
        root.addWidget(tabs, 1)

        buttons = QDialogButtonBox()
        copy_button = QPushButton("Copy diagnostics")
        copy_button.setToolTip("Copy version and paths for a bug report")
        copy_button.clicked.connect(self._copy_diagnostics)
        buttons.addButton(copy_button, QDialogButtonBox.ActionRole)
        close_button = buttons.addButton(QDialogButtonBox.Close)
        close_button.setDefault(True)
        buttons.rejected.connect(self.accept)
        close_button.clicked.connect(self.accept)
        root.addWidget(buttons)

    # ------------------------------------------------------------------

    def _about_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(14)

        description = QLabel(
            "A desktop front-end for yt-dlp and spotdl. Queue up videos, "
            "playlists and Spotify links, and let them download unattended."
        )
        description.setWordWrap(True)
        description.setObjectName("dlgSubtitle")
        layout.addWidget(description)

        # Real bullet characters. The previous revision's literals had been
        # round-tripped through cp1252 and rendered as "\u00e2\u20ac\u00a2".
        features = QLabel("\n".join(f"\u2022  {item}" for item in FEATURES))
        features.setWordWrap(True)
        features.setObjectName("helpBoxTokens")
        layout.addWidget(ui.card(features, title="What it does"))

        links_holder = QWidget()
        grid = QGridLayout(links_holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        for row, (label, url) in enumerate(
            (
                ("Source code", _version.GITHUB_URL),
                ("Report an issue", f"{_version.GITHUB_URL}/issues"),
                ("Documentation", f"{_version.GITHUB_URL}#readme"),
            )
        ):
            grid.addWidget(ui.form_label(label), row, 0)
            link = QLabel(f'<a href="{url}" style="color:#00E5FF;">{url}</a>')
            link.setTextFormat(Qt.RichText)
            link.setOpenExternalLinks(True)
            link.setTextInteractionFlags(Qt.TextBrowserInteraction)
            grid.addWidget(link, row, 1)
        grid.setColumnStretch(1, 1)
        layout.addWidget(ui.card(links_holder, title="Links"))

        credits_text = "<br>".join(
            f"\u2022 <a href='{url}' style='color:#00E5FF;'>{name}</a>"
            for name, url in CREDITS
        )
        credits = QLabel(credits_text)
        credits.setTextFormat(Qt.RichText)
        credits.setOpenExternalLinks(True)
        credits.setWordWrap(True)
        credits.setObjectName("helpBoxTokens")
        layout.addWidget(ui.card(credits, title="Built on"))

        layout.addStretch(1)
        return page

    def _environment_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        view = QTextBrowser()
        view.setPlainText(self._diagnostics())
        layout.addWidget(view)
        return page

    def _licence_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        view = QTextBrowser()
        view.setPlainText(MIT_LICENCE)
        layout.addWidget(view)
        return page

    # ------------------------------------------------------------------

    def _diagnostics(self) -> str:
        import sys

        s = self.settings
        lines: List[str] = [
            f"{_version.APP_NAME} {_version.__version__}",
            f"Platform:  {platform_label()}",
            f"Python:    {sys.version.split()[0]}",
            f"Packaged:  {'yes' if is_frozen() else 'no'}",
            "",
            f"Base:      {s.BASE_DIR}",
            f"Downloads: {s.DOWNLOADS_DIR}",
            f"Config:    {s.CONFIG_PATH}",
            "",
        ]
        for label, path in (
            ("yt-dlp", s.YT_DLP_PATH),
            ("ffmpeg", s.FFMPEG_PATH),
            ("ffprobe", s.FFPROBE_PATH),
            ("deno", s.DENO_PATH),
        ):
            marker = "found  " if Path(path).is_file() else "MISSING"
            lines.append(f"{label:<9} {marker} {path}")

        from ytget_gui.workers.spotdl_worker import _find_spotdl

        spotdl = _find_spotdl(s)
        lines.append(f"{'spotdl':<9} {'found  ' if spotdl else 'MISSING'} {spotdl or ''}")
        return "\n".join(lines)

    def _copy_diagnostics(self) -> None:
        QGuiApplication.clipboard().setText(self._diagnostics())
