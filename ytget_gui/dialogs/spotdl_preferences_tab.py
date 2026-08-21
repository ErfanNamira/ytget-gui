# File: ytget_gui/dialogs/spotdl_preferences_tab.py
"""Spotify / SpotDL preferences panel.

Embedded in PreferencesDialog's stack. Reuses the shared dialog object names
(#card, #input, #combo, #spin, #check) so it inherits the dialog stylesheet.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ytget_gui.dialogs import common as ui
from ytget_gui.spotdl_settings import (
    DEFAULT_OUTPUT_TEMPLATE,
    MAX_THREADS,
    SPOTDL_AUDIO_PROVIDERS,
    SPOTDL_BITRATES,
    SPOTDL_FORMATS,
    SPOTDL_LYRICS_PROVIDERS,
    SPOTDL_OUTPUT_TOKENS,
    SPOTDL_OVERWRITE_MODES,
    SpotDLSettings,
)


class OrderedMultiSelect(QListWidget):
    """Checkable list. Check order is preserved, because spotdl tries providers
    in the order given and the previous implementation always returned them in
    display order, silently discarding the user's priority."""

    def __init__(
        self, choices: Sequence[str], selected: Sequence[str], parent=None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("multiList")
        self.setSelectionMode(QListWidget.NoSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.setSpacing(1)

        self._order: List[str] = [c for c in selected if c in choices]

        # Checked entries first, in their configured order, so the priority is
        # visible rather than implied.
        ordered = self._order + [c for c in choices if c not in self._order]
        for choice in ordered:
            item = QListWidgetItem(choice)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if choice in self._order else Qt.Unchecked)
            self.addItem(item)

        self.setStyleSheet(
            """
            QListWidget#multiList {
                background: rgba(255, 255, 255, 10);
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 8px;
                font-size: 12.5px;
                padding: 4px;
            }
            QListWidget#multiList::item {
                padding: 4px 6px;
                border-radius: 6px;
                color: rgba(255, 255, 255, 185);
            }
            QListWidget#multiList::item:hover { background: rgba(255, 255, 255, 25); }
            QListWidget#multiList::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid rgba(255, 255, 255, 40);
                background: rgba(255, 255, 255, 15);
            }
            QListWidget#multiList::indicator:checked {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #00E5FF, stop:1 #7C4DFF);
                border: 1px solid #00E5FF;
            }
            """
        )

        self.itemChanged.connect(self._track_order)
        self._fit()

    def _track_order(self, item: QListWidgetItem) -> None:
        text = item.text()
        if item.checkState() == Qt.Checked:
            if text not in self._order:
                self._order.append(text)
        elif text in self._order:
            self._order.remove(text)

    def _fit(self) -> None:
        rows = self.count()
        row_height = self.sizeHintForRow(0) if rows else 18
        self.setFixedHeight(max(row_height + 8, row_height * rows + 2 * self.frameWidth() + 8))
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def checked(self) -> List[str]:
        present = {
            self.item(i).text()
            for i in range(self.count())
            if self.item(i).checkState() == Qt.Checked
        }
        return [c for c in self._order if c in present]


class SpotDLPreferencesTab(QScrollArea):
    def __init__(self, settings: SpotDLSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("scrollArea")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        columns = QHBoxLayout()
        columns.setSpacing(10)
        left = QVBoxLayout()
        left.setSpacing(8)
        right = QVBoxLayout()
        right.setSpacing(8)
        columns.addLayout(left, 1)
        columns.addLayout(right, 1)
        outer.addLayout(columns)

        left.addWidget(self._output_card(settings))
        left.addWidget(self._providers_card(settings))
        left.addStretch(1)

        right.addWidget(self._behaviour_card(settings))
        right.addWidget(self._passthrough_card(settings))
        right.addWidget(self._proxy_card(settings))
        right.addStretch(1)

        note = QWidget()
        note.setObjectName("helpBox")
        note_layout = QVBoxLayout(note)
        note_layout.setContentsMargins(12, 8, 12, 8)
        info = QLabel(
            "spotdl must sit next to the application or be installed with "
            "<code>pip install spotdl</code>. It needs ffmpeg and deno, both of "
            "which YTGet already manages."
        )
        info.setObjectName("helpBoxExample")
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignCenter)
        note_layout.addWidget(info)
        outer.addWidget(note)

        self.setWidget(container)

    # ------------------------------------------------------------------

    @staticmethod
    def _grid() -> tuple[QWidget, QGridLayout]:
        holder = QWidget()
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)
        return holder, grid

    def _output_card(self, s: SpotDLSettings) -> QWidget:
        holder, grid = self._grid()

        self.format_combo = ui.combo(SPOTDL_FORMATS, "Audio format")
        self.format_combo.setCurrentText(s.SPOTDL_FORMAT)
        grid.addWidget(ui.form_label("Format", "Container for downloaded tracks"), 0, 0)
        grid.addWidget(self.format_combo, 0, 1)

        self.bitrate_combo = ui.combo(SPOTDL_BITRATES, "Bitrate")
        self.bitrate_combo.setCurrentText(s.SPOTDL_BITRATE)
        grid.addWidget(ui.form_label("Bitrate", "auto lets spotdl decide"), 1, 0)
        grid.addWidget(self.bitrate_combo, 1, 1)

        self.threads_spin = ui.spin(1, MAX_THREADS, "Download threads")
        self.threads_spin.setValue(s.SPOTDL_THREADS)
        grid.addWidget(
            ui.form_label("Threads", f"Parallel downloads (1\u2013{MAX_THREADS})"), 2, 0
        )
        grid.addWidget(self.threads_spin, 2, 1)

        self.output_edit = ui.line_edit(DEFAULT_OUTPUT_TEMPLATE, "", "Output template")
        self.output_edit.setText(s.SPOTDL_OUTPUT)
        self.output_edit.setToolTip("Available tokens:\n" + "\n".join(SPOTDL_OUTPUT_TOKENS))
        grid.addWidget(ui.form_label("Template", "Filename pattern"), 3, 0)
        grid.addWidget(self.output_edit, 3, 1)

        return ui.card(
            holder, title="Output", subtitle="Format, quality and file naming."
        )

    def _providers_card(self, s: SpotDLSettings) -> QWidget:
        holder = QWidget()
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        lyrics_column = QVBoxLayout()
        lyrics_column.setSpacing(4)
        lyrics_column.addWidget(
            ui.form_label("Lyrics", "Tried in the order you check them")
        )
        self.lyrics_list = OrderedMultiSelect(SPOTDL_LYRICS_PROVIDERS, s.SPOTDL_LYRICS)
        lyrics_column.addWidget(self.lyrics_list)
        self.lrc_check = ui.check(
            "Write .lrc sidecar files", "Synced lyrics beside each track"
        )
        self.lrc_check.setChecked(s.SPOTDL_GENERATE_LRC)
        lyrics_column.addWidget(self.lrc_check)
        lyrics_column.addStretch(1)
        layout.addLayout(lyrics_column, 1)

        audio_column = QVBoxLayout()
        audio_column.setSpacing(4)
        audio_column.addWidget(
            ui.form_label("Audio sources", "youtube-music gives the best matches")
        )
        self.audio_list = OrderedMultiSelect(
            SPOTDL_AUDIO_PROVIDERS, s.SPOTDL_AUDIO_PROVIDERS
        )
        audio_column.addWidget(self.audio_list)
        audio_column.addStretch(1)
        layout.addLayout(audio_column, 1)

        return ui.card(
            holder,
            title="Providers",
            subtitle="Each extra source adds lookup time per track.",
        )

    def _behaviour_card(self, s: SpotDLSettings) -> QWidget:
        holder, grid = self._grid()

        self.overwrite_combo = ui.combo(SPOTDL_OVERWRITE_MODES, "Overwrite mode")
        self.overwrite_combo.setCurrentText(s.SPOTDL_OVERWRITE)
        grid.addWidget(ui.form_label("Existing files", "What to do on a collision"), 0, 0)
        grid.addWidget(self.overwrite_combo, 0, 1)

        self.numbering_check = ui.check("Number playlist tracks")
        self.numbering_check.setChecked(s.SPOTDL_PLAYLIST_NUMBERING)
        grid.addWidget(self.numbering_check, 1, 0, 1, 2)

        self.explicit_check = ui.check("Skip explicit tracks")
        self.explicit_check.setChecked(s.SPOTDL_SKIP_EXPLICIT)
        grid.addWidget(self.explicit_check, 2, 0, 1, 2)

        self.sponsor_check = ui.check(
            "Remove sponsored segments", "Uses SponsorBlock via yt-dlp"
        )
        self.sponsor_check.setChecked(s.SPOTDL_SPONSOR_BLOCK)
        grid.addWidget(self.sponsor_check, 3, 0, 1, 2)

        self.unavailable_check = ui.check(
            "Create placeholders for unavailable tracks"
        )
        self.unavailable_check.setChecked(s.SPOTDL_ADD_UNAVAILABLE)
        grid.addWidget(self.unavailable_check, 4, 0, 1, 2)

        return ui.card(holder, title="Behaviour")

    def _passthrough_card(self, s: SpotDLSettings) -> QWidget:
        holder, grid = self._grid()

        self.ytdlp_args = ui.line_edit(
            "--sleep-interval 1 --max-sleep-interval 2", "", "yt-dlp arguments"
        )
        self.ytdlp_args.setText(s.SPOTDL_YT_DLP_ARGS)
        grid.addWidget(ui.form_label("yt-dlp", "Passed via --yt-dlp-args"), 0, 0)
        grid.addWidget(self.ytdlp_args, 0, 1)

        self.ffmpeg_args = ui.line_edit("-b:a 320k", "", "ffmpeg arguments")
        self.ffmpeg_args.setText(s.SPOTDL_FFMPEG_ARGS)
        grid.addWidget(ui.form_label("ffmpeg", "Passed via --ffmpeg-args"), 1, 0)
        grid.addWidget(self.ffmpeg_args, 1, 1)

        return ui.card(holder, title="Passthrough")

    def _proxy_card(self, s: SpotDLSettings) -> QWidget:
        holder, grid = self._grid()

        self.use_main_proxy = ui.check("Use the main proxy setting")
        self.use_main_proxy.setChecked(s.SPOTDL_USE_MAIN_PROXY)
        self.use_main_proxy.toggled.connect(
            lambda checked: self.proxy_edit.setEnabled(not checked)
        )
        grid.addWidget(self.use_main_proxy, 0, 0, 1, 2)

        self.proxy_edit = ui.line_edit("http://host:port", "", "SpotDL proxy")
        self.proxy_edit.setText(s.SPOTDL_PROXY)
        self.proxy_edit.setEnabled(not s.SPOTDL_USE_MAIN_PROXY)
        grid.addWidget(ui.form_label("Override", "Used when the box above is clear"), 1, 0)
        grid.addWidget(self.proxy_edit, 1, 1)

        return ui.card(holder, title="Proxy")

    # ------------------------------------------------------------------

    def apply(self, settings: SpotDLSettings) -> None:
        """Write the form into `settings`, mutating it in place."""
        settings.SPOTDL_FORMAT = self.format_combo.currentText()
        settings.SPOTDL_BITRATE = self.bitrate_combo.currentText()
        settings.SPOTDL_THREADS = self.threads_spin.value()
        settings.SPOTDL_OUTPUT = (
            self.output_edit.text().strip() or DEFAULT_OUTPUT_TEMPLATE
        )
        settings.SPOTDL_LYRICS = self.lyrics_list.checked()
        settings.SPOTDL_GENERATE_LRC = self.lrc_check.isChecked()
        settings.SPOTDL_AUDIO_PROVIDERS = self.audio_list.checked()
        settings.SPOTDL_OVERWRITE = self.overwrite_combo.currentText()
        settings.SPOTDL_PLAYLIST_NUMBERING = self.numbering_check.isChecked()
        settings.SPOTDL_SKIP_EXPLICIT = self.explicit_check.isChecked()
        settings.SPOTDL_SPONSOR_BLOCK = self.sponsor_check.isChecked()
        settings.SPOTDL_ADD_UNAVAILABLE = self.unavailable_check.isChecked()
        settings.SPOTDL_YT_DLP_ARGS = self.ytdlp_args.text().strip()
        settings.SPOTDL_FFMPEG_ARGS = self.ffmpeg_args.text().strip()
        settings.SPOTDL_USE_MAIN_PROXY = self.use_main_proxy.isChecked()
        settings.SPOTDL_PROXY = self.proxy_edit.text().strip()
        settings.normalise()
