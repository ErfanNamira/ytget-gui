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

Visual notes
------------
This widget deliberately reuses the same object names as PreferencesDialog
(#card, #cardTitle, #cardSubtitle, #sectionLabel, #formLabel, #input,
#combo, #spin, #check, #divider) so that when it's embedded inside the
dialog's QStackedWidget it automatically inherits the dialog's QSS
(Qt stylesheets cascade to descendants regardless of which widget applied
them). No styling logic lives in this file except for the small
multi-select list, which isn't covered by the dialog's stylesheet.
"""

from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
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
    QGraphicsDropShadowEffect,
)
from PySide6.QtGui import QColor

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

def _g(settings: SpotDLSettings, name: str, default):
    """getattr with a default, so a settings object saved by an older
    version of the app (missing a newly-added field) doesn't raise
    AttributeError and take the whole preferences dialog down with it."""
    return getattr(settings, name, default)


def _label(text: str, tooltip: str = "") -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("formLabel")
    if tooltip:
        lbl.setToolTip(tooltip)
        lbl.setCursor(Qt.WhatsThisCursor)
    return lbl


def _sep() -> QFrame:
    f = QFrame()
    f.setObjectName("divider")
    f.setFrameShape(QFrame.HLine)
    f.setFrameShadow(QFrame.Plain)
    return f


def _combo(items: List[str]) -> QComboBox:
    cb = QComboBox()
    cb.setObjectName("combo")
    cb.addItems(items)
    return cb


def _line(text: str = "", placeholder: str = "") -> QLineEdit:
    le = QLineEdit(text)
    le.setObjectName("input")
    if placeholder:
        le.setPlaceholderText(placeholder)
    return le


def _spin(lo: int, hi: int, val: int) -> QSpinBox:
    sb = QSpinBox()
    sb.setObjectName("spin")
    sb.setRange(lo, hi)
    sb.setValue(val)
    return sb


def _check(text: str, checked: bool, tooltip: str = "") -> QCheckBox:
    cb = QCheckBox(text)
    cb.setObjectName("check")
    cb.setChecked(checked)
    if tooltip:
        cb.setToolTip(tooltip)
    return cb


def _card(title: str, subtitle: str = "") -> tuple[QFrame, QVBoxLayout]:
    """Builds a card matching PreferencesDialog's card style and returns
    (card_frame, content_layout) so callers can add rows to content_layout."""
    card = QFrame()
    card.setObjectName("card")
    v = QVBoxLayout(card)
    v.setContentsMargins(12, 10, 12, 10)
    v.setSpacing(7)

    head = QVBoxLayout()
    head.setContentsMargins(0, 0, 0, 0)
    head.setSpacing(2)
    tl = QLabel(title)
    tl.setObjectName("cardTitle")
    head.addWidget(tl)
    if subtitle:
        st = QLabel(subtitle)
        st.setObjectName("cardSubtitle")
        st.setWordWrap(True)
        head.addWidget(st)
    v.addLayout(head)

    eff = QGraphicsDropShadowEffect(card)
    eff.setBlurRadius(18)
    eff.setColor(QColor(0, 0, 0, 60))
    eff.setOffset(0, 6)
    card.setGraphicsEffect(eff)

    return card, v


# ---------------------------------------------------------------------------
#  Multi-select list widget (for lyrics providers, audio providers)
# ---------------------------------------------------------------------------

class _MultiSelectList(QListWidget):
    """Checkable list; checked items are the "selected" ones."""

    def __init__(self, choices: List[str], selected: List[str], parent=None):
        super().__init__(parent)
        self.setObjectName("multiList")
        self.setSelectionMode(QListWidget.NoSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.setSpacing(1)
        for c in choices:
            item = QListWidgetItem(c)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if c in selected else Qt.Unchecked)
            self.addItem(item)
        # Scoped styling: the dialog's QSS doesn't target plain QListWidget
        # (only #sidebar), so this list styles itself to match the card look.
        self.setStyleSheet("""
            QListWidget#multiList {
                background: transparent;
                border: none;
                font-size: 12.5px;
            }
            QListWidget#multiList::item {
                padding: 3px 4px;
                border-radius: 6px;
            }
            QListWidget#multiList::item:hover {
                background: rgba(127, 127, 127, 0.12);
            }
        """)
        self._fit_to_contents()

    def _fit_to_contents(self) -> None:
        """Grow the widget's fixed height to show every row with no scrollbar."""
        rows = self.count()
        row_h = self.sizeHintForRow(0) if rows else 18
        total = row_h * rows + 2 * self.frameWidth() + 4
        self.setFixedHeight(max(total, row_h + 4))
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

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
        self.setObjectName("scrollArea")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setSpacing(8)
        outer.setContentsMargins(0, 0, 0, 0)

        # Two-column layout: fits everything without vertical scrolling on
        # typical dialog heights, instead of one long stacked column.
        cols = QHBoxLayout()
        cols.setSpacing(10)
        left = QVBoxLayout()
        left.setSpacing(8)
        right = QVBoxLayout()
        right.setSpacing(8)
        cols.addLayout(left, 1)
        cols.addLayout(right, 1)
        outer.addLayout(cols)

        # ── Section: Output + Performance ──────────────────────────────
        card_output, g_lay = _card("Output", "Format, bitrate, threads, and filename template")
        g = QGridLayout()
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(6)
        g.setColumnStretch(1, 1)

        g.addWidget(_label("Format", "Audio format for downloaded tracks"), 0, 0)
        self.fmt_combo = _combo(SPOTDL_FORMATS)
        idx = SPOTDL_FORMATS.index(_g(settings, "SPOTDL_FORMAT", "")) if _g(settings, "SPOTDL_FORMAT", "") in SPOTDL_FORMATS else 0
        self.fmt_combo.setCurrentIndex(idx)
        g.addWidget(self.fmt_combo, 0, 1)

        g.addWidget(_label("Bitrate", "Target bitrate (auto = let spotdl decide)"), 1, 0)
        self.bitrate_combo = _combo(SPOTDL_BITRATES)
        br_idx = SPOTDL_BITRATES.index(_g(settings, "SPOTDL_BITRATE", "")) if _g(settings, "SPOTDL_BITRATE", "") in SPOTDL_BITRATES else 0
        self.bitrate_combo.setCurrentIndex(br_idx)
        g.addWidget(self.bitrate_combo, 1, 1)

        g.addWidget(_label("Download threads", "Parallel download threads (1–32)"), 2, 0)
        self.threads_spin = _spin(1, 32, _g(settings, "SPOTDL_THREADS", 4))
        g.addWidget(self.threads_spin, 2, 1)

        g.addWidget(_label(
            "Output template",
            "Filename template. Tokens: " + "  ".join(SPOTDL_OUTPUT_TOKENS[:8]) + " …"
        ), 3, 0)
        self.output_edit = _line(_g(settings, "SPOTDL_OUTPUT", ""), "{artists} - {title} - {year}.{output-ext}")
        self.output_edit.setToolTip("Available tokens:\n" + "\n".join(SPOTDL_OUTPUT_TOKENS))
        g.addWidget(self.output_edit, 3, 1)

        g_lay.addLayout(g)
        left.addWidget(card_output)

        # ── Section: Lyrics & Audio providers (side by side lists) ──────
        card_prov, prov_lay = _card("Providers", "Lyrics and audio sources spotdl will use")
        prov_cols = QHBoxLayout()
        prov_cols.setSpacing(10)

        lyr = QVBoxLayout()
        lyr.setSpacing(4)
        lyr.addWidget(_label("Lyrics (order matters)", "spotdl tries providers left-to-right"))
        self.lyrics_list = _MultiSelectList(SPOTDL_LYRICS_PROVIDERS, _g(settings, "SPOTDL_LYRICS", []))
        lyr.addWidget(self.lyrics_list)
        self.lrc_check = _check(
            "Generate .lrc sidecar files", _g(settings, "SPOTDL_GENERATE_LRC", False),
            "Write synced lyrics as separate .lrc files next to each track"
        )
        lyr.addWidget(self.lrc_check)
        prov_cols.addLayout(lyr, 1)

        au = QVBoxLayout()
        au.setSpacing(4)
        au.addWidget(_label("Audio sources", "youtube-music gives best metadata"))
        self.audio_list = _MultiSelectList(SPOTDL_AUDIO_PROVIDERS, _g(settings, "SPOTDL_AUDIO_PROVIDERS", []))
        au.addWidget(self.audio_list)
        au.addStretch(1)
        prov_cols.addLayout(au, 1)

        prov_lay.addLayout(prov_cols)
        left.addWidget(card_prov)
        left.addStretch(1)

        # ── Section: yt-dlp / ffmpeg passthrough ─────────────────────────
        card_ytdlp, yt_lay = _card("yt-dlp & ffmpeg passthrough")
        yt = QGridLayout()
        yt.setContentsMargins(0, 0, 0, 0)
        yt.setHorizontalSpacing(10)
        yt.setVerticalSpacing(6)
        yt.setColumnStretch(1, 1)

        yt.addWidget(_label(
            "Extra yt-dlp args",
            "Passed directly to yt-dlp via --yt-dlp-args. "
            "Default: --sleep-interval 1 --max-sleep-interval 2"
        ), 0, 0)
        self.ytdlp_args_edit = _line(_g(settings, "SPOTDL_YT_DLP_ARGS", ""), "--sleep-interval 1 --max-sleep-interval 2")
        yt.addWidget(self.ytdlp_args_edit, 0, 1)

        yt.addWidget(_label("Extra ffmpeg args", "Passed via --ffmpeg-args"), 1, 0)
        self.ffmpeg_args_edit = _line(_g(settings, "SPOTDL_FFMPEG_ARGS", ""), "-b:a 320k")
        yt.addWidget(self.ffmpeg_args_edit, 1, 1)

        yt_lay.addLayout(yt)
        right.addWidget(card_ytdlp)

        # ── Section: Behaviour ───────────────────────────────────────────
        card_beh, beh_lay = _card("Behaviour")
        beh = QGridLayout()
        beh.setContentsMargins(0, 0, 0, 0)
        beh.setHorizontalSpacing(10)
        beh.setVerticalSpacing(4)
        beh.setColumnStretch(1, 1)

        beh.addWidget(_label("Overwrite mode", "What to do when a file already exists"), 0, 0)
        self.overwrite_combo = _combo(SPOTDL_OVERWRITE_MODES)
        ow_idx = SPOTDL_OVERWRITE_MODES.index(_g(settings, "SPOTDL_OVERWRITE", "")) \
            if _g(settings, "SPOTDL_OVERWRITE", "") in SPOTDL_OVERWRITE_MODES else 0
        self.overwrite_combo.setCurrentIndex(ow_idx)
        beh.addWidget(self.overwrite_combo, 0, 1)

        self.playlist_num_check = _check("Add playlist numbering to filenames", _g(settings, "SPOTDL_PLAYLIST_NUMBERING", False))
        beh.addWidget(self.playlist_num_check, 1, 0, 1, 2)

        self.skip_explicit_check = _check("Skip explicit tracks", _g(settings, "SPOTDL_SKIP_EXPLICIT", False))
        beh.addWidget(self.skip_explicit_check, 2, 0, 1, 2)

        self.sponsor_block_check = _check(
            "Enable SponsorBlock", _g(settings, "SPOTDL_SPONSOR_BLOCK", False),
            "Remove sponsored segments from tracks (via yt-dlp SponsorBlock)"
        )
        beh.addWidget(self.sponsor_block_check, 3, 0, 1, 2)

        self.add_unavailable_check = _check(
            "Add unavailable tracks as empty placeholder files", _g(settings, "SPOTDL_ADD_UNAVAILABLE", False)
        )
        beh.addWidget(self.add_unavailable_check, 4, 0, 1, 2)

        beh_lay.addLayout(beh)
        right.addWidget(card_beh)

        # ── Section: Proxy ───────────────────────────────────────────────
        card_proxy, pr_lay = _card("Proxy")
        pr = QGridLayout()
        pr.setContentsMargins(0, 0, 0, 0)
        pr.setHorizontalSpacing(10)
        pr.setVerticalSpacing(6)
        pr.setColumnStretch(1, 1)

        self.use_main_proxy_check = _check(
            "Use the same proxy as the main downloader", _g(settings, "SPOTDL_USE_MAIN_PROXY", False)
        )
        self.use_main_proxy_check.toggled.connect(self._on_proxy_toggle)
        pr.addWidget(self.use_main_proxy_check, 0, 0, 1, 2)

        pr.addWidget(_label("Override proxy URL", "Only used when 'Use main proxy' is unchecked"), 1, 0)
        self.proxy_edit = _line(_g(settings, "SPOTDL_PROXY", ""), "http://user:pass@host:port")
        self.proxy_edit.setEnabled(not _g(settings, "SPOTDL_USE_MAIN_PROXY", False))
        pr.addWidget(self.proxy_edit, 1, 1)

        pr_lay.addLayout(pr)
        right.addWidget(card_proxy)
        right.addStretch(1)

        # ── Info banner ──────────────────────────────────────────────────
        info_card = QFrame()
        info_card.setObjectName("helpBox")
        info_v = QVBoxLayout(info_card)
        info_v.setContentsMargins(12, 6, 12, 6)
        info = QLabel(
            "spotdl must be placed in the program folder or installed via "
            "<code>pip install spotdl</code>. "
            "It requires ffmpeg and deno (both already supported by YTGet)."
        )
        info.setObjectName("helpBoxExample")
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignCenter)
        info_v.addWidget(info)
        outer.addWidget(info_card)

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
