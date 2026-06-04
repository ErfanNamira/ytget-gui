# File: ytget_gui/dialogs/spotdl_preferences_tab.py

"""
SpotDL preferences tab — drop this widget into your PreferencesDialog
as a tab called "Spotify / SpotDL".

Usage inside PreferencesDialog
-------------------------------
    from ytget_gui.dialogs.spotdl_preferences_tab import SpotDLPreferencesTab

    tab = SpotDLPreferencesTab(spotdl_settings)
    tab_widget.addTab(tab, "🎸 Spotify")

    # On dialog accept:
    tab.apply(spotdl_settings)     # writes values back into the object
"""

from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QSpinBox,
    QListWidget,
    QListWidgetItem,
    QFrame,
    QScrollArea,
    QSizePolicy,
    QToolTip,
)

from ytget_gui.spotdl_settings import (
    SpotDLSettings,
    SPOTDL_FORMATS,
    SPOTDL_LYRICS_PROVIDERS,
    SPOTDL_AUDIO_PROVIDERS,
    SPOTDL_BITRATES,
    SPOTDL_OVERWRITE_MODES,
    SPOTDL_OUTPUT_TOKENS,
)


# ---------------------------------------------------------------------------
#  Small helpers
# ---------------------------------------------------------------------------

def _label(text: str, tooltip: str = "") -> QLabel:
    lbl = QLabel(text)
    if tooltip:
        lbl.setToolTip(tooltip)
        lbl.setCursor(Qt.WhatsThisCursor)
    return lbl


def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setFrameShadow(QFrame.Sunken)
    return f


# ---------------------------------------------------------------------------
#  Multi-select list widget (for lyrics providers, audio providers)
# ---------------------------------------------------------------------------

class _MultiSelectList(QListWidget):
    """Checkable list; checked items are the "selected" ones."""

    def __init__(self, choices: List[str], selected: List[str], parent=None):
        super().__init__(parent)
        self.setMaximumHeight(100)
        self.setSelectionMode(QListWidget.NoSelection)
        for c in choices:
            item = QListWidgetItem(c)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if c in selected else Qt.Unchecked)
            self.addItem(item)

    def get_checked(self) -> List[str]:
        result = []
        for i in range(self.count()):
            item = self.item(i)
            if item.checkState() == Qt.Checked:
                result.append(item.text())
        return result


# ---------------------------------------------------------------------------
#  Main tab widget
# ---------------------------------------------------------------------------

class SpotDLPreferencesTab(QScrollArea):
    """
    A scrollable preferences panel for SpotDL options.
    Instantiate with the current SpotDLSettings object.
    Call .apply(settings) to write values back.
    """

    def __init__(self, settings: SpotDLSettings, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(14)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── Section: Output ──────────────────────────────────────────────
        grp_output = QGroupBox("Output")
        g = QGridLayout(grp_output)
        g.setSpacing(8)

        g.addWidget(_label("Format:", "Audio format for downloaded tracks"), 0, 0)
        self.fmt_combo = QComboBox()
        self.fmt_combo.addItems(SPOTDL_FORMATS)
        idx = SPOTDL_FORMATS.index(settings.SPOTDL_FORMAT) if settings.SPOTDL_FORMAT in SPOTDL_FORMATS else 0
        self.fmt_combo.setCurrentIndex(idx)
        g.addWidget(self.fmt_combo, 0, 1)

        g.addWidget(_label("Bitrate:", "Target bitrate (auto = let spotdl decide)"), 1, 0)
        self.bitrate_combo = QComboBox()
        self.bitrate_combo.addItems(SPOTDL_BITRATES)
        br_idx = SPOTDL_BITRATES.index(settings.SPOTDL_BITRATE) if settings.SPOTDL_BITRATE in SPOTDL_BITRATES else 0
        self.bitrate_combo.setCurrentIndex(br_idx)
        g.addWidget(self.bitrate_combo, 1, 1)

        g.addWidget(_label(
            "Output template:",
            "Filename template. Tokens: " + "  ".join(SPOTDL_OUTPUT_TOKENS[:8]) + " …"
        ), 2, 0)
        self.output_edit = QLineEdit(settings.SPOTDL_OUTPUT)
        self.output_edit.setPlaceholderText("{artists} - {title} - {year}.{output-ext}")
        self.output_edit.setToolTip(
            "Available tokens:\n" + "\n".join(SPOTDL_OUTPUT_TOKENS)
        )
        g.addWidget(self.output_edit, 2, 1)

        layout.addWidget(grp_output)

        # ── Section: Performance ─────────────────────────────────────────
        grp_perf = QGroupBox("Performance")
        p = QGridLayout(grp_perf)
        p.setSpacing(8)

        p.addWidget(_label("Download threads:", "Parallel download threads (1–32)"), 0, 0)
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 32)
        self.threads_spin.setValue(settings.SPOTDL_THREADS)
        p.addWidget(self.threads_spin, 0, 1)

        layout.addWidget(grp_perf)

        # ── Section: Lyrics ──────────────────────────────────────────────
        grp_lyrics = QGroupBox("Lyrics")
        lyr = QVBoxLayout(grp_lyrics)
        lyr.setSpacing(6)

        lyr.addWidget(_label(
            "Lyrics providers (checked = enabled, order matters):",
            "spotdl tries providers left-to-right"
        ))
        self.lyrics_list = _MultiSelectList(SPOTDL_LYRICS_PROVIDERS, settings.SPOTDL_LYRICS)
        lyr.addWidget(self.lyrics_list)

        self.lrc_check = QCheckBox("Generate .lrc sidecar files")
        self.lrc_check.setChecked(settings.SPOTDL_GENERATE_LRC)
        self.lrc_check.setToolTip("Write synced lyrics as separate .lrc files next to each track")
        lyr.addWidget(self.lrc_check)

        layout.addWidget(grp_lyrics)

        # ── Section: Audio source ────────────────────────────────────────
        grp_audio = QGroupBox("Audio source providers")
        au = QVBoxLayout(grp_audio)
        au.setSpacing(6)

        au.addWidget(_label(
            "Audio providers (checked = enabled):",
            "spotdl searches these services for audio; youtube-music gives best metadata"
        ))
        self.audio_list = _MultiSelectList(SPOTDL_AUDIO_PROVIDERS, settings.SPOTDL_AUDIO_PROVIDERS)
        au.addWidget(self.audio_list)

        layout.addWidget(grp_audio)

        # ── Section: yt-dlp / ffmpeg passthrough ─────────────────────────
        grp_ytdlp = QGroupBox("yt-dlp & ffmpeg passthrough")
        yt = QGridLayout(grp_ytdlp)
        yt.setSpacing(8)

        yt.addWidget(_label(
            "Extra yt-dlp args:",
            "Passed directly to yt-dlp via --yt-dlp-args. "
            "Default: --sleep-interval 1 --max-sleep-interval 2"
        ), 0, 0)
        self.ytdlp_args_edit = QLineEdit(settings.SPOTDL_YT_DLP_ARGS)
        self.ytdlp_args_edit.setPlaceholderText("--sleep-interval 1 --max-sleep-interval 2")
        yt.addWidget(self.ytdlp_args_edit, 0, 1)

        yt.addWidget(_label("Extra ffmpeg args:", "Passed via --ffmpeg-args"), 1, 0)
        self.ffmpeg_args_edit = QLineEdit(settings.SPOTDL_FFMPEG_ARGS)
        self.ffmpeg_args_edit.setPlaceholderText("-b:a 320k")
        yt.addWidget(self.ffmpeg_args_edit, 1, 1)

        layout.addWidget(grp_ytdlp)

        # ── Section: Behaviour ───────────────────────────────────────────
        grp_beh = QGroupBox("Behaviour")
        beh = QGridLayout(grp_beh)
        beh.setSpacing(8)

        beh.addWidget(_label("Overwrite mode:", "What to do when a file already exists"), 0, 0)
        self.overwrite_combo = QComboBox()
        self.overwrite_combo.addItems(SPOTDL_OVERWRITE_MODES)
        ow_idx = SPOTDL_OVERWRITE_MODES.index(settings.SPOTDL_OVERWRITE) \
            if settings.SPOTDL_OVERWRITE in SPOTDL_OVERWRITE_MODES else 0
        self.overwrite_combo.setCurrentIndex(ow_idx)
        beh.addWidget(self.overwrite_combo, 0, 1)

        self.playlist_num_check = QCheckBox("Add playlist numbering to filenames")
        self.playlist_num_check.setChecked(settings.SPOTDL_PLAYLIST_NUMBERING)
        beh.addWidget(self.playlist_num_check, 1, 0, 1, 2)

        self.skip_explicit_check = QCheckBox("Skip explicit tracks")
        self.skip_explicit_check.setChecked(settings.SPOTDL_SKIP_EXPLICIT)
        beh.addWidget(self.skip_explicit_check, 2, 0, 1, 2)

        self.sponsor_block_check = QCheckBox("Enable SponsorBlock")
        self.sponsor_block_check.setChecked(settings.SPOTDL_SPONSOR_BLOCK)
        self.sponsor_block_check.setToolTip("Remove sponsored segments from tracks (via yt-dlp SponsorBlock)")
        beh.addWidget(self.sponsor_block_check, 3, 0, 1, 2)

        self.add_unavailable_check = QCheckBox("Add unavailable tracks as empty placeholder files")
        self.add_unavailable_check.setChecked(settings.SPOTDL_ADD_UNAVAILABLE)
        beh.addWidget(self.add_unavailable_check, 4, 0, 1, 2)

        layout.addWidget(grp_beh)

        # ── Section: Proxy ───────────────────────────────────────────────
        grp_proxy = QGroupBox("Proxy")
        pr = QGridLayout(grp_proxy)
        pr.setSpacing(8)

        self.use_main_proxy_check = QCheckBox("Use the same proxy as the main downloader")
        self.use_main_proxy_check.setChecked(settings.SPOTDL_USE_MAIN_PROXY)
        self.use_main_proxy_check.toggled.connect(self._on_proxy_toggle)
        pr.addWidget(self.use_main_proxy_check, 0, 0, 1, 2)

        pr.addWidget(_label("Override proxy URL:", "Only used when 'Use main proxy' is unchecked"), 1, 0)
        self.proxy_edit = QLineEdit(settings.SPOTDL_PROXY)
        self.proxy_edit.setPlaceholderText("http://user:pass@host:port")
        self.proxy_edit.setEnabled(not settings.SPOTDL_USE_MAIN_PROXY)
        pr.addWidget(self.proxy_edit, 1, 1)

        layout.addWidget(grp_proxy)

        # ── Info banner ──────────────────────────────────────────────────
        info = QLabel(
            "<i>spotdl must be placed in the program folder or installed via "
            "<code>pip install spotdl</code>. "
            "It requires ffmpeg and deno (both already supported by YTGet).</i>"
        )
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignCenter)
        layout.addWidget(info)
        layout.addStretch()

        self.setWidget(container)

    # ------------------------------------------------------------------
    def _on_proxy_toggle(self, checked: bool):
        self.proxy_edit.setEnabled(not checked)

    # ------------------------------------------------------------------
    def apply(self, settings: SpotDLSettings):
        """Write UI values back into *settings* (mutates in-place)."""
        settings.SPOTDL_FORMAT = self.fmt_combo.currentText()
        settings.SPOTDL_BITRATE = self.bitrate_combo.currentText()
        settings.SPOTDL_OUTPUT = self.output_edit.text().strip() or "{artists} - {title} - {year}.{output-ext}"
        settings.SPOTDL_THREADS = self.threads_spin.value()
        settings.SPOTDL_LYRICS = self.lyrics_list.get_checked()
        settings.SPOTDL_GENERATE_LRC = self.lrc_check.isChecked()
        settings.SPOTDL_AUDIO_PROVIDERS = self.audio_list.get_checked()
        settings.SPOTDL_YT_DLP_ARGS = self.ytdlp_args_edit.text().strip()
        settings.SPOTDL_FFMPEG_ARGS = self.ffmpeg_args_edit.text().strip()
        settings.SPOTDL_OVERWRITE = self.overwrite_combo.currentText()
        settings.SPOTDL_PLAYLIST_NUMBERING = self.playlist_num_check.isChecked()
        settings.SPOTDL_SKIP_EXPLICIT = self.skip_explicit_check.isChecked()
        settings.SPOTDL_SPONSOR_BLOCK = self.sponsor_block_check.isChecked()
        settings.SPOTDL_ADD_UNAVAILABLE = self.add_unavailable_check.isChecked()
        settings.SPOTDL_USE_MAIN_PROXY = self.use_main_proxy_check.isChecked()
        settings.SPOTDL_PROXY = self.proxy_edit.text().strip()
