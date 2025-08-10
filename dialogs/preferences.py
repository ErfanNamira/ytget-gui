# File: ytget/dialogs/preferences.py
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Dict

from PySide6.QtCore import QDate, Qt, QRegularExpression, QSize
from PySide6.QtGui import (
    QIcon,
    QRegularExpressionValidator,
    QPalette,
    QColor,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QCalendarWidget,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QStackedWidget,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
    QGraphicsDropShadowEffect,
)

from ytget.styles import AppStyles
from ytget.settings import AppSettings


_SPONSORBLOCK_CATEGORIES = {
    "Sponsor": "sponsor",
    "Intro": "intro",
    "Outro": "outro",
    "Self Promotion": "selfpromo",
    "Interaction Reminder": "interaction",
    "Music Non-Music": "music_offtopic",
    "Preview/Recap": "preview",
    "Filler": "filler",
}


class PreferencesDialog(QDialog):

    MIN_WIDE_LAYOUT = 860  # px breakpoint where sidebar appears
    SIDEBAR_WIDTH = 240

    def __init__(self, parent, settings: AppSettings):
        super().__init__(parent)
        self.settings = settings

        self.setWindowTitle("Preferences")
        self.setMinimumSize(900, 640)
        self.setStyleSheet(AppStyles.DIALOG)

        # State
        self._dirty = False
        self._suppress_dirty = False
        self._initial_snapshot: dict | None = None
        self._colors: dict[str, str] = {}

        # Root
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # Header / Title
        root.addWidget(
            self._build_header(
                title="Preferences",
                subtitle="Calm controls for network, output, and processing. Changes affect new downloads.",
            )
        )

        # Top navigation (shown only on narrow widths)
        self.nav_combo = QComboBox()
        self.nav_combo.setAccessibleName("Preferences sections")
        self.nav_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.nav_combo.hide()  # shown in narrow mode
        root.addWidget(self.nav_combo)

        # Body: sidebar + stack (wide) or stack only (narrow)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)
        root.addLayout(body, 1)

        self.sidebar = self._build_sidebar()
        self.stack = QStackedWidget()

        body.addWidget(self.sidebar)
        body.addWidget(self.stack, 1)

        # Pages
        self.pages = {
            "Network": self._build_network_page(),
            "SponsorBlock": self._build_sponsorblock_page(),
            "Chapters": self._build_chapters_page(),
            "Subtitles": self._build_subtitles_page(),
            "Playlist": self._build_playlist_page(),
            "Post-processing": self._build_post_page(),
            "Output": self._build_output_page(),
            "Experimental": self._build_experimental_page(),
        }
        for name, page in self.pages.items():
            self.stack.addWidget(page)
            self.nav_combo.addItem(name)

        # Hook navigation
        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.sidebar.currentRowChanged.connect(self.nav_combo.setCurrentIndex)
        self.nav_combo.currentIndexChanged.connect(self.stack.setCurrentIndex)
        self.nav_combo.currentIndexChanged.connect(self.sidebar.setCurrentRow)
        self.sidebar.setCurrentRow(0)

        # Footer
        self.footer = self._build_footer()
        root.addWidget(self.footer)

        # Accessibility + calm theme
        self._apply_accessibility()
        self._apply_calm_styles()
        self._apply_elevation()

        # Initial state sync
        self._on_subtitles_toggled(self.subtitles_enabled.isChecked())
        self._on_archive_toggled(self.enable_archive.isChecked())
        self._on_cookies_source_changed(self.cookies_browser_combo.currentText())

        # Track changes after pages are fully initialized
        self._wire_dirty_tracking()

        # Snapshot baseline
        self._initial_snapshot = self.get_settings()
        self._set_dirty(False, reason="Ready — changes affect new downloads")

        # Shortcuts
        QShortcut(QKeySequence.Save, self, activated=self._on_save_clicked)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self._on_revert_clicked)

        # Responsive
        self._update_responsive_layout()

    # ---------- Layout primitives ----------

    def _build_header(self, title: str, subtitle: str) -> QWidget:
        w = QWidget()
        v = QHBoxLayout(w)
        v.setContentsMargins(4, 0, 4, 0)
        v.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(self.style().standardIcon(QStyle.SP_FileDialogInfoView).pixmap(28, 28))
        icon_lbl.setObjectName("prefHeaderIcon")
        icon_lbl.setFixedSize(28, 28)

        txt = QWidget()
        tv = QVBoxLayout(txt)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(2)

        lbl_title = QLabel(title)
        lbl_title.setObjectName("prefHeaderTitle")
        lbl_title.setStyleSheet("font-size: 20px; font-weight: 600;")

        lbl_sub = QLabel(subtitle)
        lbl_sub.setObjectName("prefHeaderSubtitle")
        lbl_sub.setWordWrap(True)

        tv.addWidget(lbl_title)
        tv.addWidget(lbl_sub)

        v.addWidget(icon_lbl, 0, Qt.AlignTop)
        v.addWidget(txt, 1)
        return w

    def _build_sidebar(self) -> QListWidget:
        lw = QListWidget()
        lw.setIconSize(QSize(20, 20))
        lw.setFixedWidth(self.SIDEBAR_WIDTH)
        lw.setUniformItemSizes(True)
        lw.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lw.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        lw.setSelectionMode(QListWidget.SingleSelection)
        lw.setSpacing(2)

        def add_item(text: str, icon: QIcon):
            item = QListWidgetItem(icon, text)
            item.setSizeHint(QSize(item.sizeHint().width(), 36))
            lw.addItem(item)

        style: QStyle = self.style()
        add_item("Network", style.standardIcon(QStyle.SP_DriveNetIcon))
        add_item("SponsorBlock", style.standardIcon(QStyle.SP_DialogYesButton))
        add_item("Chapters", style.standardIcon(QStyle.SP_FileDialogDetailedView))
        add_item("Subtitles", style.standardIcon(QStyle.SP_FileDialogInfoView))
        add_item("Playlist", style.standardIcon(QStyle.SP_DirIcon))
        add_item("Post-processing", style.standardIcon(QStyle.SP_ToolBarHorizontalExtensionButton))
        add_item("Output", style.standardIcon(QStyle.SP_DialogOpenButton))
        add_item("Experimental", style.standardIcon(QStyle.SP_MessageBoxInformation))

        lw.setCurrentRow(0)
        lw.setAccessibleName("Preferences sidebar")
        lw.setToolTip("Select a section")
        return lw

    @staticmethod
    def _section(title: str, hint: str | None = None) -> QWidget:
        # Section header with optional info button
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)

        lbl = QLabel(title)
        lbl.setStyleSheet("font-weight: 600;")
        h.addWidget(lbl)

        h.addStretch(1)

        if hint:
            info = QToolButton()
            info.setText("i")
            info.setToolTip(hint)
            info.setAutoRaise(True)
            info.setCursor(Qt.WhatsThisCursor)
            info.setAccessibleDescription(hint)
            info.setFixedSize(22, 22)
            h.addWidget(info)

        return w

    @staticmethod
    def _hline() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line

    @staticmethod
    def _inline(*widgets: QWidget) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        for x in widgets:
            h.addWidget(x)
        h.addStretch(1)
        return w

    @staticmethod
    def _path_row(value: str, btn_text: str, read_only: bool = True) -> tuple[QLineEdit, QPushButton]:
        le = QLineEdit(value)
        le.setReadOnly(read_only)
        btn = QPushButton(btn_text)
        btn.setMinimumHeight(36)
        return le, btn

    # ---------- Pages ----------

    def _build_network_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        layout.addWidget(self._section("Proxy", "Use a proxy to route traffic. Leave blank to connect directly."))
        proxy_form = QFormLayout()
        proxy_form.setLabelAlignment(Qt.AlignRight)
        proxy_form.setHorizontalSpacing(12)
        proxy_form.setVerticalSpacing(10)

        self.proxy_input = QLineEdit(self.settings.PROXY_URL)
        self.proxy_input.setPlaceholderText("http://proxy:port or socks5://proxy:port")
        self.proxy_input.setToolTip("Supported schemes: http, socks5")
        self.proxy_input.setAccessibleName("Proxy URL input")
        proxy_form.addRow("Proxy URL:", self.proxy_input)

        layout.addLayout(proxy_form)
        layout.addWidget(self._hline())

        layout.addWidget(self._section("Cookies", "Provide a cookies file or import directly from a browser profile."))

        cookies_form = QFormLayout()
        cookies_form.setLabelAlignment(Qt.AlignRight)
        cookies_form.setVerticalSpacing(10)
        cookies_form.setHorizontalSpacing(12)

        self.cookies_path_input, self.btn_browse_cookies = self._path_row(
            str(self.settings.COOKIES_PATH),
            "Browse…",
            read_only=True,
        )
        self.cookies_path_input.setMinimumWidth(280)
        self.cookies_path_input.setAccessibleName("Cookies file path")
        self.btn_browse_cookies.clicked.connect(self._browse_cookies)
        cookies_form.addRow("Cookies file:", self._inline(self.cookies_path_input, self.btn_browse_cookies))

        self.cookies_browser_combo = QComboBox()
        self.cookies_browser_combo.addItems(["", "chrome", "firefox", "edge", "opera", "vivaldi"])
        if self.settings.COOKIES_FROM_BROWSER:
            self.cookies_browser_combo.setCurrentText(self.settings.COOKIES_FROM_BROWSER)
        self.cookies_browser_combo.currentTextChanged.connect(self._on_cookies_source_changed)
        self.cookies_browser_combo.setAccessibleName("Import cookies from browser")
        cookies_form.addRow("Import from browser:", self.cookies_browser_combo)

        layout.addLayout(cookies_form)
        layout.addWidget(self._hline())

        layout.addWidget(self._section("Performance", "Limit throughput and configure retry behavior."))

        perf_form = QFormLayout()
        perf_form.setLabelAlignment(Qt.AlignRight)
        perf_form.setHorizontalSpacing(12)
        perf_form.setVerticalSpacing(10)

        self.limit_rate_input = QLineEdit(self.settings.LIMIT_RATE)
        self.limit_rate_input.setPlaceholderText("e.g., 5M or 500K")
        self.limit_rate_input.setToolTip("Limit download speed (e.g., 5M, 500K). Leave empty for unlimited.")
        self.limit_rate_input.setValidator(QRegularExpressionValidator(QRegularExpression(r"^\s*$|^\d+(\.\d+)?\s*[KkMm]$")))
        self.limit_rate_input.setAccessibleName("Max download speed")

        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(1, 100)
        self.retries_spin.setValue(self.settings.RETRIES)
        self.retries_spin.setAccessibleName("Retry attempts")

        perf_form.addRow("Max download speed:", self.limit_rate_input)
        perf_form.addRow("Retry attempts:", self.retries_spin)
        layout.addLayout(perf_form)

        layout.addStretch(1)
        return page

    def _build_sponsorblock_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(12)

        v.addWidget(self._section("Skip segments", "Automatically skip selected categories using SponsorBlock."))

        self.category_cb: Dict[str, QCheckBox] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)

        items = list(_SPONSORBLOCK_CATEGORIES.items())
        cols = 2
        for i, (label, code) in enumerate(items):
            cb = QCheckBox(label)
            cb.setChecked(code in self.settings.SPONSORBLOCK_CATEGORIES)
            cb.setToolTip(f"Skip {label.lower()} segments")
            cb.setAccessibleName(f"SponsorBlock category: {label}")
            self.category_cb[code] = cb
            r, c = divmod(i, cols)
            grid.addWidget(cb, r, c)

        group = QGroupBox()
        group.setFlat(False)
        gvl = QVBoxLayout(group)
        gvl.setContentsMargins(8, 8, 8, 8)
        gvl.addLayout(grid)

        v.addWidget(group)
        v.addStretch(1)
        return page

    def _build_chapters_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(12)

        v.addWidget(self._section("Chapters mode", "Choose how to treat chapters when available."))

        self.chapters_none = QRadioButton("Don't use chapters")
        self.chapters_embed = QRadioButton("Embed chapters in file")
        self.chapters_split = QRadioButton("Split into files by chapters")

        self.chapters_none.setToolTip("Ignore chapter information")
        self.chapters_embed.setToolTip("Write chapters into container metadata")
        self.chapters_split.setToolTip("Produce separate files for each chapter")

        for rb in (self.chapters_none, self.chapters_embed, self.chapters_split):
            rb.setMinimumHeight(28)

        bg = QButtonGroup(self)
        bg.setExclusive(True)
        bg.addButton(self.chapters_none)
        bg.addButton(self.chapters_embed)
        bg.addButton(self.chapters_split)

        mode = self.settings.CHAPTERS_MODE
        if mode == "embed":
            self.chapters_embed.setChecked(True)
        elif mode == "split":
            self.chapters_split.setChecked(True)
        else:
            self.chapters_none.setChecked(True)

        v.addWidget(self.chapters_none)
        v.addWidget(self.chapters_embed)
        v.addWidget(self.chapters_split)

        v.addStretch(1)
        return page

    def _build_subtitles_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setLabelAlignment(Qt.AlignRight)
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(12)

        header = self._section("Subtitles", "Fetch and format subtitles. Turn off to skip subtitle handling.")
        form.addRow(header)

        self.subtitles_enabled = QCheckBox("Download subtitles")
        self.subtitles_enabled.setChecked(self.settings.WRITE_SUBS)
        self.subtitles_enabled.toggled.connect(self._on_subtitles_toggled)
        self.subtitles_enabled.setAccessibleName("Download subtitles toggle")
        form.addRow(self.subtitles_enabled)

        self.languages_input = QLineEdit(self.settings.SUB_LANGS)
        self.languages_input.setPlaceholderText("en,es,fr")
        self.languages_input.setToolTip("Comma-separated 2–3 letter language codes (e.g., en, es, fra)")
        self.languages_input.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"^\s*$|^\s*[A-Za-z]{2,3}(\s*,\s*[A-Za-z]{2,3})*\s*$"))
        )
        self.languages_input.setAccessibleName("Subtitle languages")
        form.addRow("Languages:", self.languages_input)

        self.auto_subs = QCheckBox("Include auto-generated subtitles")
        self.auto_subs.setChecked(self.settings.WRITE_AUTO_SUBS)
        self.auto_subs.setAccessibleName("Include auto-generated subtitles")
        form.addRow(self.auto_subs)

        self.convert_subs = QCheckBox("Convert subtitles to SRT")
        self.convert_subs.setChecked(self.settings.CONVERT_SUBS_TO_SRT)
        self.convert_subs.setAccessibleName("Convert subtitles to SRT")
        form.addRow(self.convert_subs)
        return page

    def _build_playlist_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setLabelAlignment(Qt.AlignRight)
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(12)

        header = self._section("Playlist", "Control archive and ordering for multi-item downloads.")
        form.addRow(header)

        self.enable_archive = QCheckBox("Enable download archive")
        self.enable_archive.setChecked(self.settings.ENABLE_ARCHIVE)
        self.enable_archive.toggled.connect(self._on_archive_toggled)
        self.enable_archive.setAccessibleName("Enable download archive")
        form.addRow(self.enable_archive)

        self.archive_path_input, self.btn_browse_archive = self._path_row(
            str(self.settings.ARCHIVE_PATH), "Browse…", read_only=True
        )
        self.btn_browse_archive.clicked.connect(self._browse_archive)
        self.archive_path_input.setAccessibleName("Archive file path")
        form.addRow("Archive file:", self._inline(self.archive_path_input, self.btn_browse_archive))

        self.playlist_reverse = QCheckBox("Reverse playlist order")
        self.playlist_reverse.setChecked(self.settings.PLAYLIST_REVERSE)
        self.playlist_reverse.setAccessibleName("Reverse playlist order")
        form.addRow(self.playlist_reverse)

        self.playlist_items = QLineEdit(self.settings.PLAYLIST_ITEMS)
        self.playlist_items.setPlaceholderText("e.g., 1,5-10,15")
        self.playlist_items.setToolTip("Comma-separated indices or ranges (e.g., 1,5-10,15)")
        self.playlist_items.setValidator(
            QRegularExpressionValidator(
                QRegularExpression(r"^\s*$|^\s*\d+(\s*-\s*\d+)?(\s*,\s*\d+(\s*-\s*\d+)?)*\s*$")
            )
        )
        self.playlist_items.setAccessibleName("Playlist items selection")
        form.addRow("Playlist items:", self.playlist_items)
        return page

    def _build_post_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setLabelAlignment(Qt.AlignRight)
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(12)

        header = self._section("Post-processing", "Adjust audio normalization, metadata, and FFmpeg options.")
        form.addRow(header)

        self.audio_normalize = QCheckBox("Normalize audio volume")
        self.audio_normalize.setChecked(self.settings.AUDIO_NORMALIZE)
        self.audio_normalize.setAccessibleName("Normalize audio volume")
        form.addRow(self.audio_normalize)

        self.add_metadata = QCheckBox("Add metadata to files")
        self.add_metadata.setChecked(self.settings.ADD_METADATA)
        self.add_metadata.setAccessibleName("Add metadata to files")
        form.addRow(self.add_metadata)

        self.crop_covers = QCheckBox("Crop audio covers to 1:1 after queue")
        self.crop_covers.setChecked(self.settings.CROP_AUDIO_COVERS)
        self.crop_covers.setAccessibleName("Crop audio covers to 1:1 after queue")
        form.addRow(self.crop_covers)

        self.custom_ffmpeg = QLineEdit(self.settings.CUSTOM_FFMPEG_ARGS)
        self.custom_ffmpeg.setPlaceholderText("-c:v libx265 -crf 23")
        self.custom_ffmpeg.setToolTip("Advanced FFmpeg args (optional)")
        self.custom_ffmpeg.setAccessibleName("Custom FFmpeg arguments")
        form.addRow("Custom FFmpeg args:", self.custom_ffmpeg)
        return page

    def _build_output_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setLabelAlignment(Qt.AlignRight)
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(12)

        header = self._section("Output", "Structure output paths and restrict by upload date.")
        form.addRow(header)

        self.organize_uploader = QCheckBox("Organize by uploader (create folders)")
        self.organize_uploader.setChecked(self.settings.ORGANIZE_BY_UPLOADER)
        self.organize_uploader.setAccessibleName("Organize by uploader")
        form.addRow(self.organize_uploader)

        self.date_after = QLineEdit(self.settings.DATEAFTER)
        self.date_after.setPlaceholderText("YYYYMMDD")
        self.date_after.setToolTip("Download only items uploaded on/after this date")
        self.date_after.setValidator(QRegularExpressionValidator(QRegularExpression(r"^\d{8}$")))
        self.date_after.setAccessibleName("Only download after date")
        self.btn_date_picker = QPushButton("Select date…")
        self.btn_date_picker.clicked.connect(self._pick_date)
        self.btn_date_picker.setMinimumHeight(36)

        form.addRow("Only download after:", self._inline(self.date_after, self.btn_date_picker))
        return page

    def _build_experimental_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setLabelAlignment(Qt.AlignRight)
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(12)

        header = self._section("Experimental", "Early features. Behavior may change.")
        form.addRow(header)

        self.live_stream = QCheckBox("Record live streams from start")
        self.live_stream.setChecked(self.settings.LIVE_FROM_START)
        self.live_stream.setAccessibleName("Record live streams from start")

        self.yt_music = QCheckBox("Enhanced YouTube Music metadata")
        self.yt_music.setChecked(self.settings.YT_MUSIC_METADATA)
        self.yt_music.setAccessibleName("Enhanced YouTube Music metadata")

        form.addRow(self.live_stream)
        form.addRow(self.yt_music)
        return page

    # ---------- Footer ----------

    def _build_footer(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("prefFooter")
        h = QHBoxLayout(bar)
        h.setContentsMargins(12, 10, 12, 10)
        h.setSpacing(10)

        # Status
        self.footer_status = QLabel("")
        self.footer_status.setObjectName("prefFooterStatus")
        self.footer_status.setWordWrap(False)
        self.footer_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        h.addWidget(self.footer_status, 1, Qt.AlignVCenter)

        # Buttons row
        row = QWidget()
        rh = QHBoxLayout(row)
        rh.setContentsMargins(0, 0, 0, 0)
        rh.setSpacing(8)

        style: QStyle = self.style()

        self.btn_revert = QPushButton(style.standardIcon(QStyle.SP_BrowserReload), "Revert")
        self.btn_revert.setObjectName("prefSecondaryBtn")
        self.btn_revert.setAccessibleName("Revert changes")
        self.btn_revert.setToolTip("Revert all changes to last saved values (Ctrl+R)")
        self.btn_revert.clicked.connect(self._on_revert_clicked)

        self.btn_cancel = QPushButton(style.standardIcon(QStyle.SP_DialogCancelButton), "Cancel")
        self.btn_cancel.setObjectName("prefSecondaryBtn")
        self.btn_cancel.setAccessibleName("Cancel and close")
        self.btn_cancel.setToolTip("Close without saving")

        # Qt 6 has SP_DialogSaveButton; fallback to Yes icon if not present
        save_icon = style.standardIcon(getattr(QStyle, "SP_DialogSaveButton", QStyle.SP_DialogYesButton))
        self.btn_save = QPushButton(save_icon, "Save")
        self.btn_save.setObjectName("prefPrimaryBtn")
        self.btn_save.setAccessibleName("Save and close")
        self.btn_save.setToolTip("Save and close (Ctrl+S)")
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self._on_save_clicked)

        # Wire cancel last (so default remains on Save)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)

        # Size harmony
        for b in (self.btn_revert, self.btn_cancel, self.btn_save):
            b.setMinimumHeight(36)
            b.setMinimumWidth(100)

        rh.addWidget(self.btn_revert)
        rh.addWidget(self.btn_cancel)
        rh.addWidget(self.btn_save)

        h.addWidget(row, 0, Qt.AlignRight)
        return bar

    # ---------- Interactions ----------

    def _on_subtitles_toggled(self, enabled: bool):
        self.languages_input.setEnabled(enabled)
        self.auto_subs.setEnabled(enabled)
        self.convert_subs.setEnabled(enabled)

    def _on_archive_toggled(self, enabled: bool):
        self.archive_path_input.setEnabled(enabled)
        self.btn_browse_archive.setEnabled(enabled)

    def _on_cookies_source_changed(self, browser: str):
        use_browser = bool(browser.strip())
        self.cookies_path_input.setEnabled(not use_browser)
        self.btn_browse_cookies.setEnabled(not use_browser)

    # ---------- File pickers ----------

    def _browse_cookies(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Cookies File",
            str(self.settings.BASE_DIR),
            "Text Files (*.txt);;All Files (*)",
        )
        if path:
            self.cookies_path_input.setText(path)

    def _browse_archive(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Select Archive File",
            str(self.settings.BASE_DIR),
            "Text Files (*.txt);;All Files (*)",
        )
        if path:
            self.archive_path_input.setText(path)

    def _pick_date(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Select Date")
        dlg.setStyleSheet(AppStyles.DIALOG)

        v = QVBoxLayout(dlg)
        cal = QCalendarWidget()
        cal.setGridVisible(True)

        try:
            txt = self.date_after.text().strip()
            if txt:
                dt = datetime.datetime.strptime(txt, "%Y%m%d").date()
                cal.setSelectedDate(QDate(dt.year, dt.month, dt.day))
        except Exception:
            pass

        v.addWidget(cal)

        from PySide6.QtWidgets import QDialogButtonBox

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        v.addWidget(bb)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)

        if dlg.exec():
            qd = cal.selectedDate()
            self.date_after.setText(qd.toString("yyyyMMdd"))

    # ---------- Validation / save cycles ----------

    def _validate(self) -> bool:
        # Proxy
        proxy_url = self.proxy_input.text().strip()
        if proxy_url and not (proxy_url.startswith("http://") or proxy_url.startswith("socks5://")):
            self._go_to("Network")
            self._set_status("Invalid proxy: must start with http:// or socks5://", role="error")
            QMessageBox.warning(self, "Invalid proxy", "Proxy URL must start with http:// or socks5://")
            return False

        # Subtitles
        if self.subtitles_enabled.isChecked():
            langs = self.languages_input.text().strip()
            if not langs:
                self._go_to("Subtitles")
                self._set_status("Missing languages: specify at least one code (e.g., en, es)", role="error")
                QMessageBox.warning(self, "Missing languages", "Please specify at least one language code")
                return False
            tokens = [x.strip() for x in langs.split(",") if x.strip()]
            if not tokens or not all(2 <= len(x) <= 3 for x in tokens):
                self._go_to("Subtitles")
                self._set_status("Invalid languages: use 2–3 letters (e.g., en, es, fra)", role="error")
                QMessageBox.warning(
                    self, "Invalid languages", "Language codes should be 2–3 letters (e.g., en, es, fra)"
                )
                return False

        # Date
        date_str = self.date_after.text().strip()
        if date_str:
            try:
                datetime.datetime.strptime(date_str, "%Y%m%d")
            except ValueError:
                self._go_to("Output")
                self._set_status("Invalid date: must be YYYYMMDD (e.g., 20240101)", role="error")
                QMessageBox.warning(self, "Invalid date", "Date must be in YYYYMMDD format (e.g., 20240101)")
                return False

        return True

    def _on_apply_clicked(self):
        if not self._validate():
            return
        # Save snapshot as baseline
        self._initial_snapshot = self.get_settings()
        self._set_dirty(False, reason="Changes applied")
        self._set_status("Saved. Changes will affect new downloads.", role="success")

    def _on_save_clicked(self):
        if not self._validate():
            return
        self._initial_snapshot = self.get_settings()
        self._set_status("Saved", role="success")
        self._set_dirty(False)
        self.accept()

    def _on_cancel_clicked(self):
        self.reject()

    def _on_revert_clicked(self):
        if not self._initial_snapshot:
            return
        self._apply_settings(self._initial_snapshot)
        self._set_dirty(False, reason="Reverted to last saved")

    # Keep compatibility if something calls this method
    def _validate_and_accept(self):
        if self._validate():
            self.accept()

    def reject(self):
        # Intercept close to confirm discard
        if self._dirty:
            resp = QMessageBox.question(
                self,
                "Discard changes?",
                "You have unsaved changes. Discard them and close?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if resp != QMessageBox.Yes:
                return
        super().reject()

    # ---------- Snapshot apply ----------

    def _apply_settings(self, data: dict):
        self._suppress_dirty = True
        try:
            # Network
            self.proxy_input.setText(data.get("PROXY_URL", ""))

            # Cookies
            self.cookies_browser_combo.setCurrentText(data.get("COOKIES_FROM_BROWSER", ""))
            self.cookies_path_input.setText(str(data.get("COOKIES_PATH", "") or ""))

            # SponsorBlock
            sb_selected = set(data.get("SPONSORBLOCK_CATEGORIES", []))
            for code, cb in self.category_cb.items():
                cb.setChecked(code in sb_selected)

            # Chapters
            mode = data.get("CHAPTERS_MODE", "none")
            if mode == "embed":
                self.chapters_embed.setChecked(True)
            elif mode == "split":
                self.chapters_split.setChecked(True)
            else:
                self.chapters_none.setChecked(True)

            # Subtitles
            self.subtitles_enabled.setChecked(bool(data.get("WRITE_SUBS", False)))
            self.languages_input.setText(data.get("SUB_LANGS", ""))
            self.auto_subs.setChecked(bool(data.get("WRITE_AUTO_SUBS", False)))
            self.convert_subs.setChecked(bool(data.get("CONVERT_SUBS_TO_SRT", False)))
            self._on_subtitles_toggled(self.subtitles_enabled.isChecked())

            # Playlist
            self.enable_archive.setChecked(bool(data.get("ENABLE_ARCHIVE", False)))
            self.archive_path_input.setText(str(data.get("ARCHIVE_PATH", "") or ""))
            self._on_archive_toggled(self.enable_archive.isChecked())
            self.playlist_reverse.setChecked(bool(data.get("PLAYLIST_REVERSE", False)))
            self.playlist_items.setText(data.get("PLAYLIST_ITEMS", ""))

            # Post
            self.audio_normalize.setChecked(bool(data.get("AUDIO_NORMALIZE", False)))
            self.add_metadata.setChecked(bool(data.get("ADD_METADATA", False)))
            self.crop_covers.setChecked(bool(data.get("CROP_AUDIO_COVERS", False)))
            self.custom_ffmpeg.setText(data.get("CUSTOM_FFMPEG_ARGS", ""))

            # Output
            self.organize_uploader.setChecked(bool(data.get("ORGANIZE_BY_UPLOADER", False)))
            self.date_after.setText(data.get("DATEAFTER", ""))

            # Experimental
            self.live_stream.setChecked(bool(data.get("LIVE_FROM_START", False)))
            self.yt_music.setChecked(bool(data.get("YT_MUSIC_METADATA", False)))

            # Performance
            self.limit_rate_input.setText(data.get("LIMIT_RATE", ""))
            self.retries_spin.setValue(int(data.get("RETRIES", self.retries_spin.value())))
        finally:
            self._suppress_dirty = False
            self._set_dirty(False)

    def get_settings(self) -> dict:
        sb = [code for code, cb in self.category_cb.items() if cb.isChecked()]

        if self.chapters_embed.isChecked():
            ch_mode = "embed"
        elif self.chapters_split.isChecked():
            ch_mode = "split"
        else:
            ch_mode = "none"

        return {
            "PROXY_URL": self.proxy_input.text().strip(),
            "COOKIES_PATH": Path(self.cookies_path_input.text().strip()),
            "COOKIES_FROM_BROWSER": self.cookies_browser_combo.currentText().strip(),
            "SPONSORBLOCK_CATEGORIES": sb,
            "CHAPTERS_MODE": ch_mode,
            "WRITE_SUBS": self.subtitles_enabled.isChecked(),
            "SUB_LANGS": self.languages_input.text().strip(),
            "WRITE_AUTO_SUBS": self.auto_subs.isChecked(),
            "CONVERT_SUBS_TO_SRT": self.convert_subs.isChecked(),
            "ENABLE_ARCHIVE": self.enable_archive.isChecked(),
            "ARCHIVE_PATH": Path(self.archive_path_input.text().strip()),
            "PLAYLIST_REVERSE": self.playlist_reverse.isChecked(),
            "PLAYLIST_ITEMS": self.playlist_items.text().strip(),
            "AUDIO_NORMALIZE": self.audio_normalize.isChecked(),
            "ADD_METADATA": self.add_metadata.isChecked(),
            "CROP_AUDIO_COVERS": self.crop_covers.isChecked(),
            "CUSTOM_FFMPEG_ARGS": self.custom_ffmpeg.text().strip(),
            "ORGANIZE_BY_UPLOADER": self.organize_uploader.isChecked(),
            "DATEAFTER": self.date_after.text().strip(),
            "LIVE_FROM_START": self.live_stream.isChecked(),
            "YT_MUSIC_METADATA": self.yt_music.isChecked(),
            "LIMIT_RATE": self.limit_rate_input.text().strip(),
            "RETRIES": self.retries_spin.value(),
        }

    # ---------- Dirty tracking ----------

    def _wire_dirty_tracking(self):
        # Helper to connect without repeating
        def watch_lineedit(le: QLineEdit):
            le.textChanged.connect(self._on_any_changed)

        def watch_checkbox(cb: QCheckBox):
            cb.toggled.connect(self._on_any_changed)

        def watch_combobox(cb: QComboBox):
            cb.currentTextChanged.connect(self._on_any_changed)

        def watch_radiobutton(rb: QRadioButton):
            rb.toggled.connect(self._on_any_changed)

        def watch_spin(sp: QSpinBox):
            sp.valueChanged.connect(self._on_any_changed)

        # Network
        watch_lineedit(self.proxy_input)

        # Cookies
        watch_lineedit(self.cookies_path_input)
        watch_combobox(self.cookies_browser_combo)

        # SponsorBlock
        for cb in self.category_cb.values():
            watch_checkbox(cb)

        # Chapters
        watch_radiobutton(self.chapters_none)
        watch_radiobutton(self.chapters_embed)
        watch_radiobutton(self.chapters_split)

        # Subtitles
        watch_checkbox(self.subtitles_enabled)
        watch_lineedit(self.languages_input)
        watch_checkbox(self.auto_subs)
        watch_checkbox(self.convert_subs)

        # Playlist
        watch_checkbox(self.enable_archive)
        watch_lineedit(self.archive_path_input)
        watch_checkbox(self.playlist_reverse)
        watch_lineedit(self.playlist_items)

        # Post-processing
        watch_checkbox(self.audio_normalize)
        watch_checkbox(self.add_metadata)
        watch_checkbox(self.crop_covers)
        watch_lineedit(self.custom_ffmpeg)

        # Output
        watch_checkbox(self.organize_uploader)
        watch_lineedit(self.date_after)

        # Experimental
        watch_checkbox(self.live_stream)
        watch_checkbox(self.yt_music)

        # Performance
        watch_lineedit(self.limit_rate_input)
        watch_spin(self.retries_spin)

    def _on_any_changed(self, *args):
        if self._suppress_dirty:
            return
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool, reason: str | None = None):
        self._dirty = dirty
        self._update_footer_buttons()
        if reason:
            self._set_status(reason, role=("warning" if dirty else "info"))
        else:
            if dirty:
                self._set_status("Unsaved changes — press Ctrl+S to save", role="warning")
            else:
                self._set_status("All changes saved", role="success")

    def _update_footer_buttons(self):
        # Enable actions only when there are changes
        self.btn_save.setEnabled(self._dirty)
        self.btn_revert.setEnabled(self._dirty)

        # Responsive visibility for lesser-used actions
        narrow = self.width() < 700
        self.btn_revert.setVisible(not narrow)

    # ---------- Accessibility & Styling ----------

    def _apply_accessibility(self):
        # Larger interactive targets
        self.setStyleSheet(
            self.styleSheet()
            + """
            *[accessibleName] { }
            QComboBox, QLineEdit, QPushButton, QToolButton, QSpinBox {
                min-height: 36px;
            }
            QCheckBox, QRadioButton { min-height: 28px; }
        """
        )

    def _apply_calm_styles(self):
        # Choose palette direction based on app palette brightness
        base = self.palette().color(QPalette.Window)
        is_dark = (0.299 * base.red() + 0.587 * base.green() + 0.114 * base.blue()) < 128

        if is_dark:
            bg = "#15171a"
            card = "#1d2024"
            border = "#2a2f35"
            text = "#e8eaed"
            subtext = "#b7bec7"
            focus = "#6ea8fe"
            accent = "#89b4fa"
            danger = "#f38ba8"
            success = "#a6e3a1"
            warning = "#f9e2af"
        else:
            bg = "#f7f8fb"
            card = "#ffffff"
            border = "#e6e8ee"
            text = "#1f2328"
            subtext = "#596273"
            focus = "#2f6feb"
            accent = "#3b82f6"
            danger = "#e5484d"
            success = "#1a7f37"
            warning = "#9a6700"

        # store for status coloring
        self._colors = {"text": text, "subtext": subtext, "accent": accent, "danger": danger, "success": success, "warning": warning, "border": border, "card": card, "bg": bg, "focus": focus}

        qss = f"""
        QWidget#prefHeaderIcon {{
            background-color: transparent;
        }}
        QLabel#prefHeaderTitle {{
            color: {text};
        }}
        QLabel#prefHeaderSubtitle {{
            color: {subtext};
        }}
        QListWidget {{
            background-color: {card};
            border: 1px solid {border};
            border-radius: 8px;
            padding: 6px 0;
        }}
        QListWidget::item {{
            padding: 8px 12px;
            border-radius: 6px;
            color: {text};
        }}
        QListWidget::item:selected {{
            background-color: {accent}22;
            color: {text};
        }}
        QGroupBox {{
            background-color: {card};
            border: 1px solid {border};
            border-radius: 10px;
            margin-top: 6px;
        }}
        QGroupBox:title {{
            subcontrol-origin: margin; left: 10px; top: -8px;
            padding: 0 4px; color: {subtext};
            background-color: {card};
        }}
        QLineEdit, QComboBox, QSpinBox {{
            background-color: {card};
            color: {text};
            border: 1px solid {border};
            border-radius: 8px;
            padding: 6px 8px;
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
            border: 1px solid {focus};
        }}
        QPushButton {{
            background-color: {card};
            color: {text};
            border: 1px solid {border};
            border-radius: 8px;
            padding: 4px 10px;
        }}
        QPushButton:hover {{
            background-color: {accent}10;
        }}
        QPushButton:focus {{
            border: 1px solid {focus};
        }}
        QToolButton {{
            border: none; color: {subtext}; background-color: transparent;
        }}
        QToolButton:hover {{
            color: {text};
        }}
        QDialog {{
            background-color: {bg};
        }}
        QFrame[frameShape="4"] {{
            background-color: {border};
            max-height: 1px;
        }}
        QLabel {{
            color: {text};
        }}

        QLabel#prefFooterStatus {{
            color: {subtext};
            font-size: 14px;
            padding: 4px 8px;
        }}
        QPushButton#prefSecondaryBtn {{
            background-color: transparent;
            color: {text};
            border: 1px solid {border};
        }}
        QPushButton#prefSecondaryBtn:hover {{
            background-color: {accent}10;
        }}
        QPushButton#prefNeutralBtn {{
            background-color: {accent}10;
            color: {text};
            border: 1px solid {accent};
        }}
        QPushButton#prefNeutralBtn:hover {{
            background-color: {accent}20;
        }}
        QPushButton#prefPrimaryBtn {{
            background-color: {accent};
            color: white;
            border: none;
        }}
        QPushButton#prefPrimaryBtn:hover {{
            background-color: {accent}cc;
        }}
        QPushButton#prefPrimaryBtn:focus {{
            border: 2px solid {focus};
        }}
        """
        self.setStyleSheet(self.styleSheet() + qss)

    def _apply_elevation(self):
        # Subtle shadows for "card-like" elements (sidebar, group boxes, footer)
        def shadow(widget: QWidget, radius=12, dx=0, dy=2, alpha=60):
            eff = QGraphicsDropShadowEffect(self)
            eff.setBlurRadius(radius)
            eff.setOffset(dx, dy)
            eff.setColor(QColor(0, 0, 0, alpha))
            widget.setGraphicsEffect(eff)

        if hasattr(self, "sidebar") and self.sidebar is not None:
            shadow(self.sidebar, radius=16, dx=0, dy=2, alpha=50)

        for gb in self.findChildren(QGroupBox):
            shadow(gb, radius=12, dx=0, dy=1, alpha=45)

        if hasattr(self, "footer") and self.footer is not None:
            shadow(self.footer, radius=14, dx=0, dy=2, alpha=40)

    def _set_status(self, text: str, role: str = "info"):
        # role: info | success | warning | error
        color_map = {
            "info": self._colors.get("subtext", "#888"),
            "success": self._colors.get("success", "#1a7f37"),
            "warning": self._colors.get("warning", "#9a6700"),
            "error": self._colors.get("danger", "#e5484d"),
        }
        color = color_map.get(role, color_map["info"])
        self.footer_status.setText(text)
        self.footer_status.setStyleSheet(f"color: {color};")

    # ---------- Responsive ----------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_responsive_layout()

    def _update_responsive_layout(self):
        wide = self.width() >= self.MIN_WIDE_LAYOUT
        self.sidebar.setVisible(wide)
        self.nav_combo.setVisible(not wide)
        # Update footer actions visibility/enable state responsively too
        if hasattr(self, "_update_footer_buttons"):
            self._update_footer_buttons()
