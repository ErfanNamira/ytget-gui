# File: ytget/dialogs/preferences.py
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import QDate

from ytget.styles import AppStyles
from ytget.settings import AppSettings
from ytget.dialogs.advanced import UISwitch


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


class PreferencesDialog(QtWidgets.QDialog):

    MIN_WIDE_LAYOUT = 900

    def __init__(self, parent: Optional[QtWidgets.QWidget], settings: AppSettings):
        super().__init__(parent)
        self.settings = settings

        self.setWindowTitle("Preferences")
        self.setModal(True)
        self.setMinimumSize(980, 660)
        self.setSizeGripEnabled(True)

        # State
        self._initial_snapshot: dict = {}
        self._dirty = False
        self._base_tips: Dict[QtWidgets.QWidget, str] = {}
        self._filters_installed = False
        self._validation_actions: Dict[QtWidgets.QLineEdit, QtGui.QAction] = {}

        # SponsorBlock layout helpers
        self._sb_gridw: Optional[QtWidgets.QWidget] = None
        self._sb_grid: Optional[QtWidgets.QGridLayout] = None
        self._sb_ordered_cbs: List[QtWidgets.QCheckBox] = []

        # Global alignment helpers
        self._label_refs: List[QtWidgets.QLabel] = []
        self._label_col_width: int = 0

        # Build UI and styles
        self._build_ui()
        self._apply_styles()

        # Data and behavior
        self._build_pages()
        self._finalize_label_column()
        self._load_from_settings()
        self._wire_validation()
        self._wire_dirty_tracking()
        self._validate_all()
        self._set_dirty(False)
        self._update_responsive_layout()
        self._focus_first_in_current_page()

        # Keyboard navigation
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Tab"), self, activated=self._nav_next)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Shift+Tab"), self, activated=self._nav_prev)
        QtGui.QShortcut(QtGui.QKeySequence.MoveToNextPage, self, activated=self._nav_next)
        QtGui.QShortcut(QtGui.QKeySequence.MoveToPreviousPage, self, activated=self._nav_prev)

    # ---------- UI scaffold ----------
    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        # Header (brand + subtitle)
        header = QtWidgets.QWidget(self)
        header.setObjectName("header")
        hb = QtWidgets.QHBoxLayout(header)
        hb.setContentsMargins(0, 0, 0, 0)
        hb.setSpacing(12)

        # Brand icon
        brand_ic = QtWidgets.QLabel()
        brand_ic.setObjectName("brandIcon")
        brand_ic.setFixedSize(28, 28)
        brand_ic.setPixmap(self.style().standardIcon(QtWidgets.QStyle.SP_ComputerIcon).pixmap(28, 28))

        title_box = QtWidgets.QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(2)

        title = QtWidgets.QLabel("Preferences")
        title.setObjectName("dlgTitle")
        title.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)

        subtitle = QtWidgets.QLabel("Configure network, output, and processing. Changes affect new downloads.")
        subtitle.setObjectName("dlgSubtitle")
        subtitle.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)

        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        hb.addWidget(brand_ic, 0, QtCore.Qt.AlignVCenter)
        hb.addLayout(title_box, 1)
        root.addWidget(header)
        root.addWidget(self._divider())

        # Section picker for narrow layouts
        top_nav_row = QtWidgets.QWidget(self)
        tn = QtWidgets.QHBoxLayout(top_nav_row)
        tn.setContentsMargins(0, 0, 0, 0)
        tn.setSpacing(8)
        self.section_combo = QtWidgets.QComboBox()
        self.section_combo.setObjectName("sectionCombo")
        self.section_combo.setVisible(False)
        tn.addWidget(self.section_combo, 1)
        root.addWidget(top_nav_row)

        # Body: sidebar + stack
        body = QtWidgets.QSplitter(self)
        body.setObjectName("contentSplitter")
        body.setOrientation(QtCore.Qt.Horizontal)
        body.setChildrenCollapsible(False)
        root.addWidget(body, 1)

        self.sidebar = QtWidgets.QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setIconSize(QtCore.QSize(18, 18))
        self.sidebar.setUniformItemSizes(True)
        self.sidebar.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.sidebar.setSpacing(2)
        self.sidebar.setFixedWidth(244)
        self.sidebar.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.sidebar.setAccessibleName("Preferences sections")
        self.sidebar.setAccessibleDescription("Select a section to adjust preferences")

        self.stack = QtWidgets.QStackedWidget()
        self.stack.setObjectName("stack")
        body.addWidget(self.sidebar)
        body.addWidget(self.stack)
        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)

        root.addWidget(self._divider())

        # Footer with status and actions
        footer = QtWidgets.QWidget(self)
        footer.setObjectName("footer")
        fl = QtWidgets.QHBoxLayout(footer)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(10)

        self.status_lbl = QtWidgets.QLabel("All changes saved")
        self.status_lbl.setObjectName("status")
        self.status_lbl.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)

        self.buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
        )
        self.buttons.setObjectName("footerButtons")
        self.reset_btn = self.buttons.addButton("Reset", QtWidgets.QDialogButtonBox.ResetRole)
        self.reset_btn.hide()
        self.reset_btn.setToolTip("Revert all changes to the last saved values (Ctrl+R)")
        self.reset_btn.setShortcut(QtGui.QKeySequence("Ctrl+R"))

        fl.addWidget(self.status_lbl, 1, QtCore.Qt.AlignVCenter)
        fl.addWidget(self.buttons, 0, QtCore.Qt.AlignRight)
        root.addWidget(footer)

        # Signals
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self._on_reject)
        self.reset_btn.clicked.connect(self._on_reset)
        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.section_combo.currentIndexChanged.connect(self.stack.setCurrentIndex)
        self.stack.currentChanged.connect(self._sync_nav_selection)
        self.stack.currentChanged.connect(lambda _: self._focus_first_in_current_page())

        # Shortcuts
        QtGui.QShortcut(QtGui.QKeySequence.Save, self, activated=self._on_accept)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Enter"), self, activated=self._on_accept)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Return"), self, activated=self._on_accept)

    # ---------- Page registry ----------
    def _wrap_scroll(self, content: QtWidgets.QWidget) -> QtWidgets.QScrollArea:
        sa = QtWidgets.QScrollArea()
        sa.setObjectName("scrollArea")
        sa.setFrameShape(QtWidgets.QFrame.NoFrame)
        sa.setWidgetResizable(True)
        sa.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        vp = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(vp)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        v.addWidget(content)
        v.addStretch(1)
        sa.setWidget(vp)
        return sa

    def _add_card_elevation(self, card: QtWidgets.QFrame) -> None:
        eff = QtWidgets.QGraphicsDropShadowEffect(card)
        eff.setBlurRadius(18)
        eff.setColor(QtGui.QColor(0, 0, 0, 60))
        eff.setOffset(0, 6)
        card.setGraphicsEffect(eff)

    def _add_page(self, name: str, icon: QtGui.QIcon, content: QtWidgets.QWidget):
        item = QtWidgets.QListWidgetItem(icon, name)
        item.setSizeHint(QtCore.QSize(item.sizeHint().width(), 38))
        self.sidebar.addItem(item)

        # Wrap content in a scroll area
        sa = self._wrap_scroll(content)
        self.stack.addWidget(sa)

        # Section combo
        self.section_combo.addItem(icon, name)

        # Track for external reference if needed
        if not hasattr(self, "_pages"):
            self._pages = {}
        self._pages[name] = content

    def _build_pages(self) -> None:
        style = self.style()
        self._add_page("Network", style.standardIcon(QtWidgets.QStyle.SP_DriveNetIcon), self._page_network())
        self._add_page("SponsorBlock", style.standardIcon(QtWidgets.QStyle.SP_DialogYesButton), self._page_sponsorblock())
        self._add_page("Chapters", style.standardIcon(QtWidgets.QStyle.SP_FileDialogDetailedView), self._page_chapters())
        self._add_page("Subtitles", style.standardIcon(QtWidgets.QStyle.SP_FileDialogInfoView), self._page_subtitles())
        self._add_page("Playlist", style.standardIcon(QtWidgets.QStyle.SP_DirIcon), self._page_playlist())
        self._add_page("Post-processing", style.standardIcon(QtWidgets.QStyle.SP_ToolBarHorizontalExtensionButton), self._page_post())
        self._add_page("Output", style.standardIcon(QtWidgets.QStyle.SP_DialogOpenButton), self._page_output())
        self._add_page("Experimental", style.standardIcon(QtWidgets.QStyle.SP_MessageBoxInformation), self._page_experimental())

        self.sidebar.setCurrentRow(0)
        self.section_combo.setCurrentIndex(0)

    # ---------- Layout primitives ----------
    def _divider(self) -> QtWidgets.QFrame:
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Plain)
        line.setObjectName("divider")
        return line

    def _section_label(self, text: str) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName("sectionLabel")
        return lbl

    def _card(self, *inner: QtWidgets.QWidget, title: Optional[str] = None, subtitle: Optional[str] = None) -> QtWidgets.QFrame:
        card = QtWidgets.QFrame()
        card.setObjectName("card")
        v = QtWidgets.QVBoxLayout(card)
        v.setContentsMargins(14, 12, 14, 14)
        v.setSpacing(10)

        if title:
            head = QtWidgets.QWidget()
            hl = QtWidgets.QVBoxLayout(head)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(2)
            tl = QtWidgets.QLabel(title)
            tl.setObjectName("cardTitle")
            hl.addWidget(tl)
            if subtitle:
                st = QtWidgets.QLabel(subtitle)
                st.setObjectName("cardSubtitle")
                st.setWordWrap(True)
                hl.addWidget(st)
            v.addWidget(head)

        for w in inner:
            v.addWidget(w)

        self._add_card_elevation(card)
        return card

    def _tweak_toggle(self, w: QtWidgets.QWidget) -> None:
        sp = w.sizePolicy()
        sp.setHorizontalPolicy(QtWidgets.QSizePolicy.Fixed)
        sp.setVerticalPolicy(QtWidgets.QSizePolicy.Fixed)
        w.setSizePolicy(sp)
        w.setMinimumHeight(24)
        # If UISwitch exposes setText, ensure it's empty—label/description live outside
        if hasattr(w, "setText"):
            try:
                w.setText("")
            except Exception:
                pass

    def _form_row(self, label: str, widget: QtWidgets.QWidget, description: Optional[str] = None) -> QtWidgets.QWidget:
        """
        Consistent 3-column row:
        [label][description/content stretch][control]
        - Fields (line edit, combo, spin) span middle + right columns
        - UISwitch toggles align in right column; optional description sits in middle column
        - Checkboxes/radios (self-labeled) span middle + right columns; label column kept for alignment
        """
        row = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(row)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)

        # Label column
        l = QtWidgets.QLabel(label)
        l.setObjectName("formLabel")
        l.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self._label_refs.append(l)
        grid.addWidget(l, 0, 0, 1, 1)

        is_switch = isinstance(widget, UISwitch)
        is_checkbox = isinstance(widget, QtWidgets.QCheckBox)
        is_radio = isinstance(widget, QtWidgets.QRadioButton)
        is_field = isinstance(widget, (QtWidgets.QLineEdit, QtWidgets.QComboBox, QtWidgets.QSpinBox))

        # Middle column content
        if description and (is_switch or (label and (is_checkbox or is_radio))):
            desc_lbl = QtWidgets.QLabel(description)
            desc_lbl.setObjectName("formDescription")
            desc_lbl.setWordWrap(True)
            desc_lbl.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)
            desc_lbl.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
            grid.addWidget(desc_lbl, 0, 1, 1, 1)
        else:
            spacer = QtWidgets.QWidget()
            spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
            grid.addWidget(spacer, 0, 1, 1, 1)

        # Right/content placement
        if is_switch:
            self._tweak_toggle(widget)
            grid.addWidget(widget, 0, 2, 1, 1, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        elif is_field:
            sp = widget.sizePolicy()
            sp.setHorizontalPolicy(QtWidgets.QSizePolicy.Expanding)
            widget.setSizePolicy(sp)
            if isinstance(widget, QtWidgets.QLineEdit):
                widget.setMinimumHeight(36)
                widget.setProperty("hasTrailingAdorner", True)
            grid.addWidget(widget, 0, 1, 1, 2)
        elif is_checkbox or is_radio:
            # Self-labeled controls: occupy middle+right for clean alignment
            sp = widget.sizePolicy()
            sp.setHorizontalPolicy(QtWidgets.QSizePolicy.Fixed)
            widget.setSizePolicy(sp)
            grid.addWidget(widget, 0, 1, 1, 2, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        else:
            # Fallback
            grid.addWidget(widget, 0, 1, 1, 2)

        grid.setColumnStretch(1, 1)
        return row

    def _line_edit(self, placeholder: str = "", tip: str = "", name: str = "input") -> QtWidgets.QLineEdit:
        le = QtWidgets.QLineEdit()
        le.setClearButtonEnabled(True)
        le.setMinimumHeight(36)
        if placeholder:
            le.setPlaceholderText(placeholder)
        if tip:
            le.setToolTip(tip)
            self._base_tips[le] = tip
        le.setObjectName(name)
        return le

    def _picker_row(self, le: QtWidgets.QLineEdit, button_text: str, cb) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        btn = QtWidgets.QPushButton(button_text)
        btn.setMinimumHeight(36)
        btn.clicked.connect(cb)
        h.addWidget(le, 1)
        h.addWidget(btn, 0)
        return w

    # ---------- Pages ----------
    def _page_network(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        pv = QtWidgets.QVBoxLayout(page)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(12)

        # Proxy + cookies card
        proxy_form = QtWidgets.QWidget()
        pf = QtWidgets.QVBoxLayout(proxy_form)
        pf.setContentsMargins(0, 0, 0, 0)
        pf.setSpacing(10)

        self.proxy_input = self._line_edit(
            placeholder="http://proxy:port, https://proxy:port, or socks5://proxy:port",
            tip="Supported schemes: http, https, socks5",
        )
        self.proxy_input.setAccessibleName("Proxy URL")
        self.proxy_input.setAccessibleDescription("Enter a proxy URL including scheme and port")
        pf.addWidget(self._form_row("Proxy URL", self.proxy_input))

        self.cookies_path_input = self._line_edit(tip="Path to exported cookies file (.txt or .json)")
        self.cookies_path_input.setAccessibleName("Cookies file path")
        self.cookies_path_input.setAccessibleDescription("Select a cookies file to use for authenticated requests")
        cookies_row = self._picker_row(self.cookies_path_input, "Browse…", self._browse_cookies)
        pf.addWidget(self._form_row("Cookies file", cookies_row))

        self.cookies_browser_combo = QtWidgets.QComboBox()
        self.cookies_browser_combo.setObjectName("combo")
        self.cookies_browser_combo.addItems(["", "chrome", "firefox", "edge", "opera", "vivaldi"])
        self.cookies_browser_combo.setAccessibleName("Import cookies from browser")
        self._base_tips[self.cookies_browser_combo] = "Import cookies directly from a supported browser profile"
        pf.addWidget(self._form_row("Import from browser", self.cookies_browser_combo))

        proxy_card = self._card(
            proxy_form,
            title="Network access",
            subtitle="Route traffic via a proxy or provide cookies for authenticated sessions.",
        )
        pv.addWidget(proxy_card)

        # Performance card
        perf_form = QtWidgets.QWidget()
        prf = QtWidgets.QVBoxLayout(perf_form)
        prf.setContentsMargins(0, 0, 0, 0)
        prf.setSpacing(10)

        self.limit_rate_input = self._line_edit(
            placeholder="e.g., 5M, 500K, 1G",
            tip="Limit download speed (e.g., 5M, 500K, 1G). Leave empty for unlimited.",
        )
        self.limit_rate_input.setAccessibleName("Maximum download speed")
        prf.addWidget(self._form_row("Max download speed", self.limit_rate_input))

        self.retries_spin = QtWidgets.QSpinBox()
        self.retries_spin.setRange(1, 100)
        self.retries_spin.setMinimumHeight(36)
        self.retries_spin.setObjectName("spin")
        self.retries_spin.setAccessibleName("Retry attempts")
        prf.addWidget(self._form_row("Retry attempts", self.retries_spin))

        perf_card = self._card(
            perf_form,
            title="Performance",
            subtitle="Throughput limits and retry behavior for unstable networks.",
        )
        pv.addWidget(perf_card)

        self.cookies_browser_combo.currentTextChanged.connect(self._on_cookies_source_changed)
        return page

    def _page_sponsorblock(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        pv = QtWidgets.QVBoxLayout(page)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(12)

        self._sb_gridw = QtWidgets.QWidget()
        self._sb_gridw.setObjectName("sbGridw")
        self._sb_grid = QtWidgets.QGridLayout(self._sb_gridw)
        self._sb_grid.setContentsMargins(0, 0, 0, 0)
        self._sb_grid.setHorizontalSpacing(16)
        self._sb_grid.setVerticalSpacing(8)

        self.category_cb: Dict[str, QtWidgets.QCheckBox] = {}
        items = list(_SPONSORBLOCK_CATEGORIES.items())

        self._sb_ordered_cbs.clear()
        for (label, code) in items:
            cb = QtWidgets.QCheckBox(label)
            cb.setObjectName("check")
            sp = cb.sizePolicy()
            sp.setHorizontalPolicy(QtWidgets.QSizePolicy.Fixed)
            cb.setSizePolicy(sp)
            cb.setAccessibleName(f"SponsorBlock category: {label}")
            self.category_cb[code] = cb
            self._sb_ordered_cbs.append(cb)

        # Initial layout (will be reflowed responsively)
        self._layout_sponsorblock(cols=2)

        card = self._card(
            self._sb_gridw,
            title="SponsorBlock",
            subtitle="Automatically skip selected categories while downloading.",
        )
        pv.addWidget(card)
        return page

    def _layout_sponsorblock(self, cols: int) -> None:
        if not self._sb_grid or not self._sb_gridw or not self._sb_ordered_cbs:
            return
        # Clear grid
        while self._sb_grid.count():
            it = self._sb_grid.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(self._sb_gridw)
        # Re-add with new columns
        for i, cb in enumerate(self._sb_ordered_cbs):
            r, c = divmod(i, cols)
            self._sb_grid.addWidget(cb, r, c)

    def _page_chapters(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        pv = QtWidgets.QVBoxLayout(page)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(12)

        group = QtWidgets.QWidget()
        gl = QtWidgets.QVBoxLayout(group)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(8)

        self.chapters_none = QtWidgets.QRadioButton("Don't use chapters")
        self.chapters_embed = QtWidgets.QRadioButton("Embed chapters in file")
        self.chapters_split = QtWidgets.QRadioButton("Split into files by chapters")

        for rb in (self.chapters_none, self.chapters_embed, self.chapters_split):
            rb.setObjectName("radio")
            rb.setMinimumHeight(28)
            sp = rb.sizePolicy()
            sp.setHorizontalPolicy(QtWidgets.QSizePolicy.Fixed)
            rb.setSizePolicy(sp)
            gl.addWidget(rb)

        card = self._card(group, title="Chapters", subtitle="Choose how to treat chapters when present.")
        pv.addWidget(card)
        return page

    def _page_subtitles(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        pv = QtWidgets.QVBoxLayout(page)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(12)

        form = QtWidgets.QWidget()
        fl = QtWidgets.QVBoxLayout(form)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(10)

        # UISwitch in right column, label+desc managed by form row
        self.subtitles_enabled = UISwitch("")
        self._tweak_toggle(self.subtitles_enabled)
        self.subtitles_enabled.setAccessibleName("Enable subtitles")
        fl.addWidget(self._form_row("Subtitles", self.subtitles_enabled, "Download subtitle tracks if available"))

        self.languages_input = self._line_edit(
            placeholder="en,es,fr",
            tip="Comma-separated 2–3 letter language codes (e.g., en, es, fra)",
        )
        self.languages_input.setAccessibleName("Subtitle languages")
        fl.addWidget(self._form_row("Languages", self.languages_input))

        self.auto_subs = QtWidgets.QCheckBox("Include auto-generated subtitles")
        self.auto_subs.setObjectName("check")
        self.auto_subs.setAccessibleName("Include auto-generated subtitles")
        fl.addWidget(self._form_row("", self.auto_subs))

        self.convert_subs = QtWidgets.QCheckBox("Convert subtitles to SRT")
        self.convert_subs.setObjectName("check")
        self.convert_subs.setAccessibleName("Convert subtitles to SRT")
        fl.addWidget(self._form_row("", self.convert_subs))

        card = self._card(form, title="Subtitles", subtitle="Fetch, convert, and include subtitles in your downloads.")
        pv.addWidget(card)

        self.subtitles_enabled.toggled.connect(self._on_subtitles_toggled)
        return page

    def _page_playlist(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        pv = QtWidgets.QVBoxLayout(page)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(12)

        form = QtWidgets.QWidget()
        fl = QtWidgets.QVBoxLayout(form)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(10)

        self.enable_archive = UISwitch("")
        self._tweak_toggle(self.enable_archive)
        self.enable_archive.setAccessibleName("Enable download archive")
        self.enable_archive.setEnabled(True)
        fl.addWidget(self._form_row("Archive", self.enable_archive, "Track downloaded items to avoid duplicates"))

        self.archive_path_input = self._line_edit(tip="Text file to track downloaded items (yt-dlp --download-archive)")
        self.archive_path_input.setAccessibleName("Archive file path")
        archive_row = self._picker_row(self.archive_path_input, "Browse…", self._browse_archive)
        fl.addWidget(self._form_row("Archive file", archive_row))

        self.playlist_reverse = UISwitch("")
        self._tweak_toggle(self.playlist_reverse)
        self.playlist_reverse.setAccessibleName("Reverse playlist order")
        self.playlist_reverse.setEnabled(True)
        fl.addWidget(self._form_row("Order", self.playlist_reverse, "Download items in reverse order"))

        self.playlist_items = self._line_edit(
            placeholder="e.g., 1,5-10,15",
            tip="Comma-separated indices or ranges (e.g., 1,5-10,15)",
        )
        self.playlist_items.setAccessibleName("Playlist items selection")
        fl.addWidget(self._form_row("Items", self.playlist_items))

        card = self._card(form, title="Playlist", subtitle="Control archive and ordering for multi-item downloads.")
        pv.addWidget(card)

        self.enable_archive.toggled.connect(lambda en: self.archive_path_input.setEnabled(en))
        return page

    def _page_post(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        pv = QtWidgets.QVBoxLayout(page)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(12)

        form = QtWidgets.QWidget()
        fl = QtWidgets.QVBoxLayout(form)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(10)

        self.audio_normalize = UISwitch("")
        self._tweak_toggle(self.audio_normalize)
        self.audio_normalize.setAccessibleName("Normalize audio volume")
        self.audio_normalize.setEnabled(True)
        fl.addWidget(self._form_row("Audio normalize", self.audio_normalize, "Adjust volume to a consistent level"))

        self.add_metadata = UISwitch("")
        self._tweak_toggle(self.add_metadata)
        self.add_metadata.setAccessibleName("Add metadata to files")
        self.add_metadata.setEnabled(True)
        fl.addWidget(self._form_row("Metadata", self.add_metadata, "Write tags (title, artist, album) into files"))

        self.crop_covers = UISwitch("")
        self._tweak_toggle(self.crop_covers)
        self.crop_covers.setAccessibleName("Crop audio covers to square")
        self.crop_covers.setEnabled(True)
        fl.addWidget(self._form_row("Covers", self.crop_covers, "Crop artwork to a 1:1 aspect ratio"))
        
        self.video_format_combo = QtWidgets.QComboBox()
        self.video_format_combo.setObjectName("combo")
        self.video_format_combo.addItems([".mkv", ".mp4", ".webm"])
        self.video_format_combo.setAccessibleName("Preferred video format")
        fl.addWidget(self._form_row("Video format", self.video_format_combo, "Choose output container"))

        self.custom_ffmpeg = self._line_edit(
            placeholder="-c:v libx265 -crf 23",
            tip="Advanced FFmpeg args (optional)",
        )
        self.custom_ffmpeg.setAccessibleName("Custom FFmpeg arguments")
        fl.addWidget(self._form_row("Custom FFmpeg args", self.custom_ffmpeg))

        card = self._card(form, title="Post-processing", subtitle="Fine-tune audio, metadata, and FFmpeg options.")
        pv.addWidget(card)
        return page

    def _page_output(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        pv = QtWidgets.QVBoxLayout(page)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(12)

        form = QtWidgets.QWidget()
        fl = QtWidgets.QVBoxLayout(form)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(10)

        self.organize_uploader = UISwitch("")
        self._tweak_toggle(self.organize_uploader)
        self.organize_uploader.setAccessibleName("Organize output by uploader")
        fl.addWidget(self._form_row("Folders", self.organize_uploader, "Place downloads into uploader-named folders"))

        self.date_after = self._line_edit(placeholder="YYYYMMDD", tip="Download only items uploaded on/after this date")
        self.date_after.setAccessibleName("Only download after date")
        self.btn_date_picker = QtWidgets.QPushButton("Select date…")
        self.btn_date_picker.setMinimumHeight(36)
        self.btn_date_picker.clicked.connect(self._pick_date)
        dr = QtWidgets.QWidget()
        dh = QtWidgets.QHBoxLayout(dr)
        dh.setContentsMargins(0, 0, 0, 0)
        dh.setSpacing(8)
        dh.addWidget(self.date_after, 1)
        dh.addWidget(self.btn_date_picker, 0)
        fl.addWidget(self._form_row("Only download after", dr))

        card = self._card(form, title="Output", subtitle="Organize your library and restrict by upload date.")
        pv.addWidget(card)
        return page

    def _page_experimental(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        pv = QtWidgets.QVBoxLayout(page)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(12)

        form = QtWidgets.QWidget()
        fl = QtWidgets.QVBoxLayout(form)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(10)

        self.live_stream = UISwitch("")
        self._tweak_toggle(self.live_stream)
        self.live_stream.setAccessibleName("Record live streams from start")
        self.live_stream.setEnabled(True)
        fl.addWidget(self._form_row("Live streams", self.live_stream, "Record live content from the beginning"))

        self.yt_music = UISwitch("")
        self._tweak_toggle(self.yt_music)
        self.yt_music.setAccessibleName("Enhanced YouTube Music metadata")
        self.yt_music.setEnabled(True)
        fl.addWidget(self._form_row("Music metadata", self.yt_music, "Prefer richer metadata for YouTube Music"))

        card = self._card(form, title="Experimental", subtitle="Early features. Behavior may change.")
        pv.addWidget(card)
        return page

    # ---------- Styling ----------
    def _apply_styles(self) -> None:
        base = ""
        try:
            base = getattr(AppStyles, "DIALOG", "") or ""
        except Exception:
            base = ""

        pal = self.palette()
        win = pal.color(QtGui.QPalette.Window)
        base_bg = pal.color(QtGui.QPalette.Base)
        highlight = pal.color(QtGui.QPalette.Highlight)

        def _hex(c: QtGui.QColor) -> str:
            c = c.toRgb()
            return f"#{c.red():02x}{c.green():02x}{c.blue():02x}"

        def _is_dark(c: QtGui.QColor) -> bool:
            return (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) < 128

        def _mix(a: QtGui.QColor, b: QtGui.QColor, t: float) -> QtGui.QColor:
            return QtGui.QColor(
                int(a.red() * (1 - t) + b.red() * t),
                int(a.green() * (1 - t) + b.green() * t),
                int(a.blue() * (1 - t) + b.blue() * t),
            )

        def _contrast_on(bg: QtGui.QColor) -> QtGui.QColor:
            yiq = (bg.red() * 299 + bg.green() * 587 + bg.blue() * 114) / 1000
            return QtGui.QColor("#0b0b0b") if yiq > 150 else QtGui.QColor("#ffffff")

        is_dark = _is_dark(win)
        strong_text = QtGui.QColor("#EAEFF7") if is_dark else QtGui.QColor("#0E1320")
        muted_text = QtGui.QColor("#AAB4C0") if is_dark else QtGui.QColor("#5B6470")
        section_text = QtGui.QColor("#C2CAD6") if is_dark else QtGui.QColor("#3A4250")
        border_c = QtGui.QColor("#39414D") if is_dark else QtGui.QColor("#D9DEE5")
        divider_c = QtGui.QColor("#2B313B") if is_dark else QtGui.QColor("#E7EBF0")
        card_bg = _mix(base_bg, QtGui.QColor("#0F131A"), 0.7) if is_dark else QtGui.QColor("#FFFFFF")
        card_hover = _mix(card_bg, QtGui.QColor("#ffffff"), 0.06 if is_dark else 0.02)
        field_bg = card_bg
        field_hover = card_hover
        focus_text_on_highlight = _contrast_on(highlight)
        error_border = QtGui.QColor("#F97066") if is_dark else QtGui.QColor("#D13438")
        error_bg = QtGui.QColor(255, 92, 92, 28 if is_dark else 18)
        brand_accent = _mix(highlight, strong_text, 0.8)

        css = f"""
        QDialog {{
            background: {_hex(win)};
        }}

        /* Header */
        #brandIcon {{
            border-radius: 6px;
            background: {_hex(_mix(highlight, win, 0.85))};
        }}
        #dlgTitle {{
            font-size: 20px;
            font-weight: 700;
            letter-spacing: 0.2px;
            color: {_hex(strong_text)};
        }}
        #dlgSubtitle {{
            font-size: 12px;
            color: {_hex(muted_text)};
        }}

        /* Sidebar and nav */
        QListWidget#sidebar {{
            background: transparent;
            border: 1px solid {_hex(border_c)};
            border-radius: 12px;
            padding: 6px 0;
        }}
        QListWidget#sidebar::item {{
            padding: 10px 12px;
            margin: 2px 6px;
            border-radius: 10px;
            color: {_hex(strong_text)};
        }}
        QListWidget#sidebar::item:selected {{
            background: {_hex(_mix(border_c, highlight, 0.8))}33;
            border: 1px solid {_hex(_mix(border_c, highlight, 0.35))};
        }}
        QComboBox#sectionCombo {{
            min-height: 36px;
            border: 1px solid {_hex(border_c)};
            border-radius: 10px;
            padding: 6px 10px;
            background: {_hex(card_bg)};
            color: {_hex(strong_text)};
        }}

        /* Scroll area */
        QScrollArea#scrollArea {{
            background: transparent;
            border: none;
        }}
        QScrollArea#scrollArea > QWidget#qt_scrollarea_viewport {{
            background: transparent;
        }}

        /* Cards */
        QFrame#card {{
            background: {_hex(card_bg)};
            border: 1px solid {_hex(border_c)};
            border-radius: 14px;
        }}
        QFrame#card:hover {{
            border-color: {_hex(_mix(border_c, highlight, 0.35))};
            background: {_hex(field_hover)};
        }}
        QLabel#cardTitle {{
            font-size: 14px;
            font-weight: 600;
            color: {_hex(strong_text)};
        }}
        QLabel#cardSubtitle {{
            font-size: 12px;
            color: {_hex(muted_text)};
        }}

        /* Section and form labels */
        #sectionLabel {{
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.4px;
            color: {_hex(section_text)};
        }}
        #formLabel {{
            font-size: 12px;
            color: {_hex(muted_text)};
        }}
        #formDescription {{
            font-size: 12px;
            color: {_hex(muted_text)};
        }}

        /* Inputs */
        QLineEdit#input, QComboBox#combo, QSpinBox#spin {{
            background: {_hex(field_bg)};
            color: {_hex(strong_text)};
            border: 1px solid {_hex(border_c)};
            border-radius: 10px;
            padding: 8px 12px;
            selection-background-color: {_hex(highlight)};
            selection-color: {_hex(focus_text_on_highlight)};
            font-size: 13px;
        }}
        QLineEdit#input:hover, QComboBox#combo:hover, QSpinBox#spin:hover {{
            background: {_hex(field_hover)};
            border-color: {_hex(_mix(border_c, highlight, 0.25))};
        }}
        QLineEdit#input:focus, QComboBox#combo:focus, QSpinBox#spin:focus {{
            border-color: {_hex(highlight)};
            background: {_hex(field_hover)};
        }}
        QLineEdit#input[state="error"] {{
            border-color: {_hex(error_border)};
            background: {_hex(error_bg)};
        }}

        QCheckBox#check, QRadioButton#radio {{
            color: {_hex(strong_text)};
        }}

        /* Divider */
        #divider {{
            background: {_hex(divider_c)};
            min-height: 1px;
        }}

        /* Footer */
        #status {{
            color: {_hex(muted_text)};
        }}
        QDialogButtonBox QPushButton {{
            border-radius: 10px;
            padding: 8px 14px;
            font-weight: 600;
        }}
        QDialogButtonBox QPushButton:default {{
            background: {_hex(highlight)};
            color: {_hex(focus_text_on_highlight)};
        }}
        QDialogButtonBox QPushButton:!default {{
            background: transparent;
            color: {_hex(strong_text)};
            border: 1px solid {_hex(border_c)};
        }}
        QDialogButtonBox QPushButton:hover {{
            border-color: {_hex(_mix(border_c, highlight, 0.35))};
        }}
        QDialogButtonBox QPushButton:disabled {{
            color: {_hex(_mix(muted_text, strong_text, 0.25))};
            background: {_hex(_mix(win, field_bg, 0.2))};
            border-color: {_hex(_mix(border_c, win, 0.2))};
        }}
        """
        self.setStyleSheet((base + "\n" + css).strip())

    # ---------- Behavior helpers ----------
    def _on_cookies_source_changed(self, browser: str) -> None:
        use_browser = bool(browser.strip())
        self.cookies_path_input.setEnabled(not use_browser)

    def _on_subtitles_toggled(self, enabled: bool) -> None:
        self.languages_input.setEnabled(enabled)
        self.auto_subs.setEnabled(enabled)
        self.convert_subs.setEnabled(enabled)

    def _on_archive_toggled(self, enabled: bool) -> None:
        self.archive_path_input.setEnabled(enabled)

    def _browse_cookies(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select Cookies File",
            str(self.settings.BASE_DIR),
            "Cookies (*.txt *.json);;All Files (*)",
        )
        if path:
            self.cookies_path_input.setText(path)

    def _browse_archive(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Select Archive File",
            str(self.settings.BASE_DIR),
            "Text Files (*.txt);;All Files (*)",
        )
        if path:
            self.archive_path_input.setText(path)

    def _pick_date(self) -> None:
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Select Date")
        try:
            dlg.setStyleSheet(getattr(AppStyles, "DIALOG", "") or "")
        except Exception:
            pass

        v = QtWidgets.QVBoxLayout(dlg)
        cal = QtWidgets.QCalendarWidget()
        cal.setGridVisible(True)

        try:
            txt = self.date_after.text().strip()
            if txt:
                dt = datetime.datetime.strptime(txt, "%Y%m%d").date()
                cal.setSelectedDate(QDate(dt.year, dt.month, dt.day))
        except Exception:
            pass

        v.addWidget(cal)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        v.addWidget(bb)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)

        if dlg.exec():
            qd = cal.selectedDate()
            self.date_after.setText(qd.toString("yyyyMMdd"))

    # ---------- Validation ----------
    def _wire_validation(self) -> None:
        self._rx_rate = QtCore.QRegularExpression(r"^\s*$|^\d+(\.\d+)?\s*[KkMmGg]$")
        self._rx_langs = QtCore.QRegularExpression(r"^\s*$|^\s*[A-Za-z]{2,3}(\s*,\s*[A-Za-z]{2,3})*\s*$")
        self._rx_items = QtCore.QRegularExpression(r"^\s*$|^\s*\d+(\s*-\s*\d+)?(\s*,\s*\d+(\s*-\s*\d+)?)*\s*$")
        self._rx_date = QtCore.QRegularExpression(r"^\s*$|^\d{8}$")

        self.limit_rate_input.setValidator(QtGui.QRegularExpressionValidator(self._rx_rate, self))
        self.languages_input.setValidator(QtGui.QRegularExpressionValidator(self._rx_langs, self))
        self.playlist_items.setValidator(QtGui.QRegularExpressionValidator(self._rx_items, self))
        self.date_after.setValidator(QtGui.QRegularExpressionValidator(self._rx_date, self))

        for w in (
            self.proxy_input,
            self.cookies_path_input,
            self.limit_rate_input,
            self.languages_input,
            self.playlist_items,
            self.date_after,
        ):
            w.textChanged.connect(self._validate_all)

        self.retries_spin.valueChanged.connect(self._validate_all)
        self.cookies_browser_combo.currentTextChanged.connect(self._validate_all)
        self.subtitles_enabled.toggled.connect(self._validate_all)
        self.enable_archive.toggled.connect(self._validate_all)

    def _mark_error(self, w: QtWidgets.QWidget, has_error: bool, tip: Optional[str] = None) -> None:
        w.setProperty("state", "error" if has_error else "")
        w.style().unpolish(w)
        w.style().polish(w)
        if has_error and tip:
            w.setToolTip(tip)
        elif w in self._base_tips:
            w.setToolTip(self._base_tips[w])

        # Inline adorner for QLineEdit
        if isinstance(w, QtWidgets.QLineEdit):
            self._set_line_adorn(w, not has_error)

    def _set_line_adorn(self, le: QtWidgets.QLineEdit, ok: bool) -> None:
        
        if le in self._validation_actions:
            act = self._validation_actions.pop(le)
            le.removeAction(act)

        icon = self.style().standardIcon(
            QtWidgets.QStyle.SP_DialogApplyButton if ok or not le.text().strip() else QtWidgets.QStyle.SP_MessageBoxWarning
        )
        # Only show on error or when non-empty and ok
        show = (not ok) or (ok and bool(le.text().strip()))
        if not show:
            return
        act = le.addAction(icon, QtWidgets.QLineEdit.TrailingPosition)
        self._validation_actions[le] = act

    def _validate_all(self) -> None:
        proxy = self.proxy_input.text().strip()
        proxy_ok = (proxy == "") or proxy.startswith(("http://", "https://", "socks5://"))

        # Cookies: ok if browser chosen; if not, file path can be empty
        cookies_ok = True

        rate_ok = self._rx_rate.match(self.limit_rate_input.text()).hasMatch()
        langs_ok = (not self.subtitles_enabled.isChecked()) or (
            self._rx_langs.match(self.languages_input.text()).hasMatch()
            and bool(self.languages_input.text().strip())
        )
        items_ok = self._rx_items.match(self.playlist_items.text()).hasMatch()

        date_txt = self.date_after.text().strip()
        date_ok = self._rx_date.match(date_txt).hasMatch()
        if date_ok and date_txt:
            try:
                datetime.datetime.strptime(date_txt, "%Y%m%d")
            except ValueError:
                date_ok = False

        # Archive path optional even if enabled
        archive_ok = True

        self._mark_error(self.proxy_input, not proxy_ok, "Must start with http://, https://, or socks5://")
        self._mark_error(self.limit_rate_input, not rate_ok, "Use a number with K, M, or G (e.g., 500K, 5M, 1G)")
        self._mark_error(
            self.languages_input,
            not langs_ok and self.subtitles_enabled.isChecked(),
            "Provide 2–3 letter codes, e.g., en, es, fra",
        )
        self._mark_error(self.playlist_items, not items_ok, "Use indices or ranges: 1,5-10,15")
        self._mark_error(self.date_after, not date_ok, "Must be YYYYMMDD (e.g., 20240101)")

        all_ok = proxy_ok and cookies_ok and rate_ok and langs_ok and items_ok and date_ok and archive_ok
        self._set_save_enabled(all_ok)

    def _set_save_enabled(self, enabled: bool) -> None:
        btn = self.buttons.button(QtWidgets.QDialogButtonBox.Save)
        if btn:
            btn.setEnabled(enabled)
            if enabled:
                btn.setDefault(True)
            btn.setToolTip("Save changes" if enabled else "Fix highlighted fields to enable Save")

    # ---------- Dirty tracking ----------
    def _wire_dirty_tracking(self) -> None:
        def watch(w: QtCore.QObject):
            if isinstance(w, QtWidgets.QLineEdit):
                w.textChanged.connect(self._on_any_changed)
            elif isinstance(w, QtWidgets.QComboBox):
                w.currentTextChanged.connect(self._on_any_changed)
            elif isinstance(w, QtWidgets.QSpinBox):
                w.valueChanged.connect(self._on_any_changed)
            elif isinstance(w, (QtWidgets.QCheckBox, UISwitch, QtWidgets.QRadioButton)):
                w.toggled.connect(self._on_any_changed)

        for w in (
            # Network
            self.proxy_input,
            self.cookies_path_input,
            self.cookies_browser_combo,
            self.limit_rate_input,
            self.retries_spin,
            # SponsorBlock
            *self.category_cb.values(),
            # Chapters
            self.chapters_none,
            self.chapters_embed,
            self.chapters_split,
            # Subtitles
            self.subtitles_enabled,
            self.languages_input,
            self.auto_subs,
            self.convert_subs,
            # Playlist
            self.enable_archive,
            self.archive_path_input,
            self.playlist_reverse,
            self.playlist_items,
            # Post
            self.audio_normalize,
            self.add_metadata,
            self.crop_covers,
            self.custom_ffmpeg,
            self.video_format_combo,
            # Output
            self.organize_uploader,
            self.date_after,
            # Experimental
            self.live_stream,
            self.yt_music,
        ):
            watch(w)

        # Baseline snapshot
        self._initial_snapshot = self.get_settings()

    def _on_any_changed(self, *args) -> None:
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self._update_status()

    def _update_status(self) -> None:
        self.status_lbl.setText("Unsaved changes — press Ctrl+S to save" if self._dirty else "All changes saved")
        self.reset_btn.setEnabled(self._dirty)

    def _on_reset(self) -> None:
        if not self._initial_snapshot:
            return
        self._apply_snapshot(self._initial_snapshot)
        self._set_dirty(False)
        self._validate_all()

    # ---------- Navigation helpers ----------
    def _nav_next(self) -> None:
        idx = self.sidebar.currentRow()
        count = self.sidebar.count()
        if count == 0:
            return
        self.sidebar.setCurrentRow((idx + 1) % count)

    def _nav_prev(self) -> None:
        idx = self.sidebar.currentRow()
        count = self.sidebar.count()
        if count == 0:
            return
        self.sidebar.setCurrentRow((idx - 1) % count)

    def _focus_first_in_current_page(self) -> None:
        # Current page is wrapped in a QScrollArea
        sa = self.stack.currentWidget()
        if not isinstance(sa, QtWidgets.QScrollArea):
            return
        page = sa.widget()
        if not page:
            return
        # Preferred order of focusable widgets
        candidates: List[QtWidgets.QWidget] = []
        for t in (QtWidgets.QLineEdit, QtWidgets.QComboBox, QtWidgets.QSpinBox, UISwitch, QtWidgets.QCheckBox, QtWidgets.QRadioButton):
            candidates.extend(page.findChildren(t))
        for w in candidates:
            if w.isVisible() and w.isEnabled() and w.focusPolicy() != QtCore.Qt.NoFocus:
                w.setFocus(QtCore.Qt.OtherFocusReason)
                self._ensure_widget_visible(w)
                break

    def _ensure_widget_visible(self, w: QtWidgets.QWidget) -> None:
        # Find containing QScrollArea
        parent = w.parent()
        sa: Optional[QtWidgets.QScrollArea] = None
        while parent:
            if isinstance(parent, QtWidgets.QScrollArea):
                sa = parent
                break
            parent = parent.parent()

        if not isinstance(sa, QtWidgets.QScrollArea):
            return

        try:
            sa.ensureWidgetVisible(w, 24, 24)  # margins
            return
        except Exception:
            pass

        # Fallback: compute position in viewport and adjust scroll bars
        vp = sa.viewport()
        top_left = w.mapTo(vp, QtCore.QPoint(0, 0))
        # Keep a small margin
        margin_x, margin_y = 24, 24

        hbar = sa.horizontalScrollBar()
        vbar = sa.verticalScrollBar()

        # Horizontal
        x = top_left.x()
        if x < hbar.value() + margin_x:
            hbar.setValue(max(0, x - margin_x))
        else:
            right = x + w.width()
            view_right = hbar.value() + vp.width() - margin_x
            if right > view_right:
                hbar.setValue(min(hbar.maximum(), right - vp.width() + margin_x))

        # Vertical
        y = top_left.y()
        if y < vbar.value() + margin_y:
            vbar.setValue(max(0, y - margin_y))
        else:
            bottom = y + w.height()
            view_bottom = vbar.value() + vp.height() - margin_y
            if bottom > view_bottom:
                vbar.setValue(min(vbar.maximum(), bottom - vp.height() + margin_y))

    # ---------- Accept / Reject ----------
    def _on_accept(self) -> None:
        btn = self.buttons.button(QtWidgets.QDialogButtonBox.Save)
        if btn and not btn.isEnabled():
            err = self._first_error_widget()
            if err:
                err.setFocus(QtCore.Qt.OtherFocusReason)
                self._ensure_widget_visible(err)
                QtWidgets.QToolTip.showText(err.mapToGlobal(err.rect().bottomLeft()), err.toolTip(), err)
            return

        self.apply()
        self._initial_snapshot = self.get_settings()
        self._set_dirty(False)
        self.accept()

    def _on_reject(self) -> None:
        if self._dirty:
            resp = QtWidgets.QMessageBox.question(
                self,
                "Discard changes?",
                "You have unsaved changes. Discard them and close?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if resp != QtWidgets.QMessageBox.Yes:
                return
        self.reject()

    # ---------- Data I/O ----------
    def _load_from_settings(self) -> None:
        # Network
        self.proxy_input.setText(getattr(self.settings, "PROXY_URL", "") or "")
        self.cookies_path_input.setText(str(getattr(self.settings, "COOKIES_PATH", "") or ""))
        self.cookies_browser_combo.setCurrentText(getattr(self.settings, "COOKIES_FROM_BROWSER", "") or "")
        self.retries_spin.setValue(int(getattr(self.settings, "RETRIES", 3)))
        self.limit_rate_input.setText(getattr(self.settings, "LIMIT_RATE", "") or "")

        # SponsorBlock
        selected = set(getattr(self.settings, "SPONSORBLOCK_CATEGORIES", []) or [])
        for code, cb in self.category_cb.items():
            cb.setChecked(code in selected)

        # Chapters
        mode = getattr(self.settings, "CHAPTERS_MODE", "none")
        if mode == "embed":
            self.chapters_embed.setChecked(True)
        elif mode == "split":
            self.chapters_split.setChecked(True)
        else:
            self.chapters_none.setChecked(True)

        # Subtitles
        self.subtitles_enabled.setChecked(bool(getattr(self.settings, "WRITE_SUBS", False)))
        self.languages_input.setText(getattr(self.settings, "SUB_LANGS", "") or "")
        self.auto_subs.setChecked(bool(getattr(self.settings, "WRITE_AUTO_SUBS", False)))
        self.convert_subs.setChecked(bool(getattr(self.settings, "CONVERT_SUBS_TO_SRT", False)))
        self._on_subtitles_toggled(self.subtitles_enabled.isChecked())

        # Playlist
        self.enable_archive.setChecked(bool(getattr(self.settings, "ENABLE_ARCHIVE", False)))
        self.archive_path_input.setText(str(getattr(self.settings, "ARCHIVE_PATH", "") or ""))
        self._on_archive_toggled(self.enable_archive.isChecked())
        self.playlist_reverse.setChecked(bool(getattr(self.settings, "PLAYLIST_REVERSE", False)))
        self.playlist_items.setText(getattr(self.settings, "PLAYLIST_ITEMS", "") or "")

        # Post-processing
        self.audio_normalize.setChecked(bool(getattr(self.settings, "AUDIO_NORMALIZE", False)))
        self.add_metadata.setChecked(bool(getattr(self.settings, "ADD_METADATA", False)))
        self.crop_covers.setChecked(bool(getattr(self.settings, "CROP_AUDIO_COVERS", False)))
        self.custom_ffmpeg.setText(getattr(self.settings, "CUSTOM_FFMPEG_ARGS", "") or "")
        vf = getattr(self.settings, "VIDEO_FORMAT", ".mkv") or ".mkv"
        if vf not in (".mkv", ".mp4", ".webm"):
            vf = ".mkv"
        self.video_format_combo.setCurrentText(vf)

        # Output
        self.organize_uploader.setChecked(bool(getattr(self.settings, "ORGANIZE_BY_UPLOADER", False)))
        self.date_after.setText(getattr(self.settings, "DATEAFTER", "") or "")

        # Experimental
        self.live_stream.setChecked(bool(getattr(self.settings, "LIVE_FROM_START", False)))
        self.yt_music.setChecked(bool(getattr(self.settings, "YT_MUSIC_METADATA", False)))

    def _apply_snapshot(self, data: dict) -> None:
        # Network
        self.proxy_input.setText(data.get("PROXY_URL", ""))
        self.cookies_browser_combo.setCurrentText(data.get("COOKIES_FROM_BROWSER", ""))
        self.cookies_path_input.setText(str(data.get("COOKIES_PATH", "") or ""))
        self.limit_rate_input.setText(data.get("LIMIT_RATE", ""))
        self.retries_spin.setValue(int(data.get("RETRIES", self.retries_spin.value())))

        # SponsorBlock
        sel = set(data.get("SPONSORBLOCK_CATEGORIES", []))
        for code, cb in self.category_cb.items():
            cb.setChecked(code in sel)

        # Chapters
        ch = data.get("CHAPTERS_MODE", "none")
        if ch == "embed":
            self.chapters_embed.setChecked(True)
        elif ch == "split":
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

        # Post-processing
        self.audio_normalize.setChecked(bool(data.get("AUDIO_NORMALIZE", False)))
        self.add_metadata.setChecked(bool(data.get("ADD_METADATA", False)))
        self.crop_covers.setChecked(bool(data.get("CROP_AUDIO_COVERS", False)))
        self.custom_ffmpeg.setText(data.get("CUSTOM_FFMPEG_ARGS", ""))
        vf = data.get("VIDEO_FORMAT", ".mkv") or ".mkv"
        if vf not in (".mkv", ".mp4", ".webm"):
            vf = ".mkv"
        self.video_format_combo.setCurrentText(vf)

        # Output
        self.organize_uploader.setChecked(bool(data.get("ORGANIZE_BY_UPLOADER", False)))
        self.date_after.setText(data.get("DATEAFTER", ""))

        # Experimental
        self.live_stream.setChecked(bool(data.get("LIVE_FROM_START", False)))
        self.yt_music.setChecked(bool(data.get("YT_MUSIC_METADATA", False)))

    def get_settings(self) -> dict:
        # Chapters mode
        if self.chapters_embed.isChecked():
            ch_mode = "embed"
        elif self.chapters_split.isChecked():
            ch_mode = "split"
        else:
            ch_mode = "none"

        sb = [code for code, cb in self.category_cb.items() if cb.isChecked()]

        return {
            "PROXY_URL": self.proxy_input.text().strip(),
            "COOKIES_PATH": Path(self.cookies_path_input.text().strip()) if self.cookies_path_input.text().strip() else Path(""),
            "COOKIES_FROM_BROWSER": self.cookies_browser_combo.currentText().strip(),
            "SPONSORBLOCK_CATEGORIES": sb,
            "CHAPTERS_MODE": ch_mode,
            "WRITE_SUBS": self.subtitles_enabled.isChecked(),
            "SUB_LANGS": self.languages_input.text().strip(),
            "WRITE_AUTO_SUBS": self.auto_subs.isChecked(),
            "CONVERT_SUBS_TO_SRT": self.convert_subs.isChecked(),
            "ENABLE_ARCHIVE": self.enable_archive.isChecked(),
            "ARCHIVE_PATH": Path(self.archive_path_input.text().strip()) if self.archive_path_input.text().strip() else Path(""),
            "PLAYLIST_REVERSE": self.playlist_reverse.isChecked(),
            "PLAYLIST_ITEMS": self.playlist_items.text().strip(),
            "AUDIO_NORMALIZE": self.audio_normalize.isChecked(),
            "ADD_METADATA": self.add_metadata.isChecked(),
            "CROP_AUDIO_COVERS": self.crop_covers.isChecked(),
            "CUSTOM_FFMPEG_ARGS": self.custom_ffmpeg.text().strip(),
            "VIDEO_FORMAT": self.video_format_combo.currentText(),
            "ORGANIZE_BY_UPLOADER": self.organize_uploader.isChecked(),
            "DATEAFTER": self.date_after.text().strip(),
            "LIVE_FROM_START": self.live_stream.isChecked(),
            "YT_MUSIC_METADATA": self.yt_music.isChecked(),
            "LIMIT_RATE": self.limit_rate_input.text().strip(),
            "RETRIES": self.retries_spin.value(),
        }

    def apply(self) -> None:
        """
        Applies current form values to self.settings (preferred integration point for MainWindow).
        """
        data = self.get_settings()
        for k, v in data.items():
            if hasattr(self.settings, k):
                try:
                    setattr(self.settings, k, v)
                except Exception:
                    # هgnore non-writable attributes
                    pass

    def validate_and_accept(self) -> None:
        self._validate_all()
        btn = self.buttons.button(QtWidgets.QDialogButtonBox.Save)
        if btn and btn.isEnabled():
            self.apply()
            self.accept()

    # ---------- Events ----------
    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        if not self._filters_installed:
            self._filters_installed = True
            for le in self._line_edits_for_filters():
                le.installEventFilter(self)
        self._update_responsive_layout()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_responsive_layout()

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.KeyPress and isinstance(obj, QtWidgets.QLineEdit):
            ke = QtGui.QKeyEvent(event)
            if ke.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
                btn = self.buttons.button(QtWidgets.QDialogButtonBox.Save)
                if btn and not btn.isEnabled():
                    err = self._first_error_widget()
                    if err:
                        err.setFocus(QtCore.Qt.OtherFocusReason)
                        self._ensure_widget_visible(err)
                        QtWidgets.QToolTip.showText(err.mapToGlobal(err.rect().bottomLeft()), err.toolTip(), err)
                    return True
        return super().eventFilter(obj, event)

    # ---------- Utilities ----------
    def _line_edits_for_filters(self) -> List[QtWidgets.QLineEdit]:
        fields: List[QtWidgets.QLineEdit] = []
        for w in (
            getattr(self, "proxy_input", None),
            getattr(self, "cookies_path_input", None),
            getattr(self, "limit_rate_input", None),
            getattr(self, "languages_input", None),
            getattr(self, "playlist_items", None),
            getattr(self, "date_after", None),
            getattr(self, "custom_ffmpeg", None),
            getattr(self, "archive_path_input", None),
        ):
            if isinstance(w, QtWidgets.QLineEdit):
                fields.append(w)
        return fields

    def _first_error_widget(self) -> Optional[QtWidgets.QWidget]:
        for w in (self.proxy_input, self.limit_rate_input, self.languages_input, self.playlist_items, self.date_after):
            if (w.property("state") or "") == "error":
                return w
        return None

    # ---------- Responsive helpers ----------
    def _update_responsive_layout(self) -> None:
        is_narrow = self.width() < self.MIN_WIDE_LAYOUT
        # Toggle sidebar and top section combo for narrow widths
        self.sidebar.setVisible(not is_narrow)
        self.section_combo.setVisible(is_narrow)

        # Keep selections in sync when toggling views
        idx = self.stack.currentIndex()
        if self.section_combo.currentIndex() != idx:
            block = QtCore.QSignalBlocker(self.section_combo)
            self.section_combo.setCurrentIndex(idx)
        if self.sidebar.currentRow() != idx:
            block = QtCore.QSignalBlocker(self.sidebar)
            self.sidebar.setCurrentRow(idx)

        # Responsive SponsorBlock grid reflow (1–4 columns)
        try:
            if hasattr(self, "_sb_gridw") and self._sb_gridw:
                avail = max(0, self.stack.width() - 64)
                cols = 1
                if avail >= 900:
                    cols = 4
                elif avail >= 700:
                    cols = 3
                elif avail >= 480:
                    cols = 2
                if getattr(self, "_sb_cols", None) != cols:
                    self._sb_cols = cols
                    self._layout_sponsorblock(cols)
        except Exception:
            pass

    def _sync_nav_selection(self, index: int) -> None:
        # Sync both nav controls without causing loops
        if 0 <= index < self.stack.count():
            if self.sidebar.currentRow() != index:
                block1 = QtCore.QSignalBlocker(self.sidebar)
                self.sidebar.setCurrentRow(index)
            if self.section_combo.currentIndex() != index:
                block2 = QtCore.QSignalBlocker(self.section_combo)
                self.section_combo.setCurrentIndex(index)

    # ---------- Label alignment pass ----------
    def _finalize_label_column(self) -> None:
        """
        Measure widest label and set a uniform minimum width, so every form row
        aligns perfectly across all pages. Keeps toggles snapped to the right.
        """
        max_w = 0
        fm = self.fontMetrics()
        for lbl in self._label_refs:
            max_w = max(max_w, fm.horizontalAdvance(lbl.text()) + 8)
        for lbl in self._label_refs:
            lbl.setMinimumWidth(max_w)
