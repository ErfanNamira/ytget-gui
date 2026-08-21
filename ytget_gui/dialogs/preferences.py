# File: ytget_gui/dialogs/preferences.py
"""Preferences dialog.

Every field is registered once as a Binding that knows how to read and write
itself. The previous revision listed each setting in four places -- the widget
construction, _load_from_settings, _apply_snapshot and get_settings -- so
omitting one produced a preference that looked editable but silently reverted,
which is exactly how PREFER_HLS, AUTO_RETRY_COUNT and QUEUE_ERROR_RETRIES ended
up unreachable from the UI at all.
"""

from __future__ import annotations

import datetime
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QDate, QSignalBlocker, QSize, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCalendarWidget,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStyle,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ytget_gui.dialogs import common as ui
from ytget_gui.dialogs.spotdl_preferences_tab import SpotDLPreferencesTab
from ytget_gui.settings import (
    BROWSERS,
    FILENAME_FORMAT_PRESETS,
    THUMBNAIL_FORMATS,
    VIDEO_CONTAINERS,
    YOUTUBE_PLAYER_CLIENTS,
    AppSettings,
)
from ytget_gui.utils.validators import (
    is_valid_dateafter,
    is_valid_proxy,
    is_valid_playlist_items,
    is_valid_rate_limit,
    is_valid_sub_langs,
)
from ytget_gui.widgets.ui_switch import UISwitch
from ytget_gui.workers import cookies as cookie_manager

log = logging.getLogger(__name__)

SPONSORBLOCK_CATEGORIES: Tuple[Tuple[str, str], ...] = (
    ("Sponsor", "sponsor"),
    ("Intro", "intro"),
    ("Outro", "outro"),
    ("Self Promotion", "selfpromo"),
    ("Interaction Reminder", "interaction"),
    ("Non-Music", "music_offtopic"),
    ("Preview / Recap", "preview"),
    ("Filler", "filler"),
)

FILENAME_CHOICES: Tuple[Tuple[str, str], ...] = (
    ("Default", "default"),
    ("Title only", "title_only"),
    ("Artist - Title", "artist_title"),
    ("Title - Artist", "title_artist"),
    ("Artist - Album - Title", "artist_album_title"),
    ("Track # - Title", "track_title"),
    ("Album - Track # - Title", "album_track_title"),
    ("Playlist # - Title", "playlist_index_title"),
    ("Uploader - Title", "uploader_title"),
    ("Channel - Title", "channel_title"),
    ("Upload Date - Title", "date_title"),
    ("Video/Track ID - Title", "id_title"),
    ("Custom template\u2026", "custom"),
)

assert all(
    value in ("default", "custom") or value in FILENAME_FORMAT_PRESETS
    for _label, value in FILENAME_CHOICES
), "FILENAME_CHOICES references a preset that does not exist"

CHAPTER_CHOICES: Tuple[Tuple[str, str], ...] = (
    ("Ignore chapters", "none"),
    ("Embed chapters in the file", "embed"),
    ("Split into one file per chapter", "split"),
)

ALLOWED_TEMPLATE_FIELDS = frozenset(
    {
        "title", "artist", "creator", "uploader", "uploader_id", "channel",
        "channel_id", "album", "album_artist", "track", "track_number",
        "track_id", "disc_number", "genre", "release_year", "release_date",
        "upload_date", "playlist_title", "playlist_index", "playlist_id", "id",
        "ext", "duration", "duration_string", "view_count", "like_count",
        "repost_count", "comment_count", "resolution", "height", "width", "fps",
        "vcodec", "acodec", "format_id", "extractor", "extractor_key",
        "language", "season_number", "episode_number", "autonumber", "abr",
        "vbr", "tbr", "epoch",
    }
)

# One %(field[,alt][|default])s / d / f placeholder.
_PLACEHOLDER_RE = re.compile(
    r"%\((?P<fields>[a-zA-Z_][a-zA-Z0-9_]*(?:,[a-zA-Z_][a-zA-Z0-9_]*)*)"
    r"(?:\|[^)%]*)?\)(?P<conv>[-+ #0]*\d*(?:\.\d+)?[sdf])"
)
# Illegal outside a placeholder: this is a filename stub, not a path.
_ILLEGAL_LITERAL_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


@dataclass(frozen=True)
class Binding:
    """Links a settings key to the widget that edits it."""

    key: str
    widget: QWidget
    get: Callable[[], Any]
    set: Callable[[Any], None]


class PreferencesDialog(QDialog):
    NARROW_WIDTH = 900

    def __init__(self, parent: Optional[QWidget], settings: AppSettings) -> None:
        super().__init__(parent)
        self.settings = settings

        self.setWindowTitle("Preferences")
        self.setModal(True)
        self.setMinimumSize(980, 680)
        self.setSizeGripEnabled(True)
        self.setStyleSheet(ui.dialog_qss())

        self._bindings: List[Binding] = []
        self._labels: List[QLabel] = []
        self._sponsor_checks: Dict[str, QCheckBox] = {}
        self._chapter_radios: Dict[str, QRadioButton] = {}
        self._sponsor_grid: Optional[QGridLayout] = None
        self._sponsor_columns = 0
        self._snapshot: Dict[str, Any] = {}
        self._dirty = False

        self._build_shell()
        self._build_pages()
        self._align_labels()
        self._load()
        self._wire()
        self._validate()
        self._set_dirty(False)
        self._update_responsive()

    # ==================================================================
    # Shell
    # ==================================================================

    def _build_shell(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(12)
        badge = QLabel("\u2699")
        badge.setObjectName("brandIcon")
        badge.setFixedSize(40, 40)
        badge.setAlignment(Qt.AlignCenter)

        titles = QVBoxLayout()
        titles.setContentsMargins(0, 0, 0, 0)
        titles.setSpacing(2)
        title = QLabel("Preferences")
        title.setObjectName("dlgTitle")
        subtitle = QLabel(
            "Network, output and processing options. Changes apply to new downloads."
        )
        subtitle.setObjectName("dlgSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)

        header.addWidget(badge, 0, Qt.AlignVCenter)
        header.addLayout(titles, 1)
        root.addLayout(header)
        root.addWidget(ui.divider())

        self.section_combo = QComboBox()
        self.section_combo.setObjectName("combo")
        self.section_combo.setVisible(False)
        self.section_combo.setAccessibleName("Preferences section")
        root.addWidget(self.section_combo)

        body = QSplitter(Qt.Horizontal, self)
        body.setChildrenCollapsible(False)
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setIconSize(QSize(18, 18))
        self.sidebar.setUniformItemSizes(True)
        self.sidebar.setSpacing(2)
        self.sidebar.setFixedWidth(240)
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sidebar.setAccessibleName("Preferences sections")

        self.stack = QStackedWidget()
        body.addWidget(self.sidebar)
        body.addWidget(self.stack)
        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        root.addWidget(body, 1)

        root.addWidget(ui.divider())

        footer = QHBoxLayout()
        footer.setSpacing(6)
        self.status_label = QLabel()
        self.status_label.setObjectName("status")
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        self.reset_button = self.buttons.addButton("Reset", QDialogButtonBox.ResetRole)
        self.reset_button.setToolTip("Revert to the last saved values (Ctrl+R)")
        self.reset_button.setShortcut(QKeySequence("Ctrl+R"))
        footer.addWidget(self.status_label, 1, Qt.AlignVCenter)
        footer.addWidget(self.buttons, 0, Qt.AlignRight)
        root.addLayout(footer)

        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self._reject)
        self.reset_button.clicked.connect(self._reset)
        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.section_combo.currentIndexChanged.connect(self.stack.setCurrentIndex)
        self.stack.currentChanged.connect(self._sync_navigation)

        QShortcut(QKeySequence.Save, self, activated=self._accept)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._accept)
        QShortcut(QKeySequence("Ctrl+Tab"), self, activated=lambda: self._step(1))
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self, activated=lambda: self._step(-1))

    def _add_page(self, name: str, icon_enum, content: QWidget, *, scroll: bool = True) -> None:
        icon = self.style().standardIcon(icon_enum)
        item = QListWidgetItem(icon, name)
        item.setSizeHint(QSize(item.sizeHint().width(), 34))
        self.sidebar.addItem(item)
        self.stack.addWidget(ui.wrap_scroll(content) if scroll else content)
        self.section_combo.addItem(icon, name)

    def _register(
        self, key: str, widget: QWidget, get: Callable[[], Any], setter: Callable[[Any], None]
    ) -> QWidget:
        self._bindings.append(Binding(key, widget, get, setter))
        return widget

    def _bind_text(self, key: str, widget: QLineEdit) -> QLineEdit:
        return self._register(
            key, widget, lambda w=widget: w.text().strip(),
            lambda v, w=widget: w.setText("" if v is None else str(v)),
        )

    def _bind_switch(self, key: str, widget: UISwitch) -> UISwitch:
        return self._register(
            key, widget, widget.isChecked, lambda v, w=widget: w.setChecked(bool(v))
        )

    def _bind_check(self, key: str, widget: QCheckBox) -> QCheckBox:
        return self._register(
            key, widget, widget.isChecked, lambda v, w=widget: w.setChecked(bool(v))
        )

    def _bind_spin(self, key: str, widget: QSpinBox) -> QSpinBox:
        return self._register(
            key, widget, widget.value, lambda v, w=widget: w.setValue(int(v or 0))
        )

    def _bind_combo_text(self, key: str, widget: QComboBox) -> QComboBox:
        return self._register(
            key, widget, widget.currentText,
            lambda v, w=widget: w.setCurrentText(str(v)),
        )

    def _bind_combo_mapped(
        self, key: str, widget: QComboBox, pairs: Sequence[Tuple[str, str]], fallback: str
    ) -> QComboBox:
        """Combo whose display labels differ from the stored values."""
        labels = [label for label, _ in pairs]
        values = [value for _, value in pairs]

        def getter() -> str:
            index = widget.currentIndex()
            return values[index] if 0 <= index < len(values) else fallback

        def setter(value: Any) -> None:
            try:
                widget.setCurrentIndex(values.index(str(value)))
            except ValueError:
                widget.setCurrentIndex(values.index(fallback))

        widget.clear()
        widget.addItems(labels)
        return self._register(key, widget, getter, setter)

    # ==================================================================
    # Pages
    # ==================================================================

    def _build_pages(self) -> None:
        icons = QStyle
        self._add_page("Network", icons.SP_DriveNetIcon, self._page_network())
        self._add_page("Cookies", icons.SP_DialogSaveButton, self._page_cookies())
        self._add_page("SponsorBlock", icons.SP_DialogYesButton, self._page_sponsorblock())
        self._add_page("Subtitles", icons.SP_FileDialogInfoView, self._page_subtitles())
        self._add_page("Playlist", icons.SP_DirIcon, self._page_playlist())
        self._add_page("Output", icons.SP_DialogOpenButton, self._page_output())
        self._add_page("Processing", icons.SP_FileDialogDetailedView, self._page_processing())
        self._add_page("Thumbnails", icons.SP_FileDialogContentsView, self._page_thumbnails())
        self._add_page("Advanced", icons.SP_MessageBoxWarning, self._page_advanced())

        self.spotdl_tab = SpotDLPreferencesTab(self.settings.SPOTDL)
        self._add_page("Spotify", icons.SP_MediaPlay, self.spotdl_tab, scroll=False)

        self.sidebar.setCurrentRow(0)
        self.section_combo.setCurrentIndex(0)

    @staticmethod
    def _column(*rows: QWidget) -> QWidget:
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for row in rows:
            layout.addWidget(row)
        return holder

    def _page(self, *cards: QWidget) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for card in cards:
            layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _row(self, label: str, widget: QWidget, description: str = "") -> QWidget:
        return ui.form_row(label, widget, description, label_registry=self._labels)

    # -- Network -------------------------------------------------------

    def _page_network(self) -> QWidget:
        self.proxy_input = self._bind_text(
            "PROXY_URL",
            ui.line_edit(
                "http://host:port, socks5://host:port",
                "Supported schemes: http, https, socks4, socks5, socks5h",
                "Proxy URL",
            ),
        )

        self.ignore_ssl = self._bind_check(
            "IGNORE_SSL_ERRORS",
            ui.check(
                "Ignore SSL certificate errors (unsafe)",
                "Adds --no-check-certificates. Prefer a custom CA below.",
            ),
        )

        self.ca_cert_input = self._bind_text(
            "CUSTOM_CA_CERT",
            ui.line_edit(
                "Path to a CA certificate",
                "Trust one certificate instead of disabling verification "
                "entirely. Takes precedence over ignoring SSL errors.",
                "Custom CA certificate",
            ),
        )
        ca_row = ui.picker_row(self.ca_cert_input, "Browse\u2026", self._browse_ca)

        network_card = ui.card(
            self._column(
                self._row("Proxy", self.proxy_input),
                self._row("", self.ignore_ssl),
                self._row("Custom CA", ca_row),
            ),
            title="Connection",
            subtitle="Route traffic through a proxy and control TLS trust.",
        )

        self.limit_rate = self._bind_text(
            "LIMIT_RATE",
            ui.line_edit("e.g. 5M, 500K", "Leave empty for unlimited", "Speed limit"),
        )
        self.retries = self._bind_spin(
            "RETRIES", ui.spin(1, 100, "Network retries")
        )
        self.auto_retry = self._bind_spin(
            "AUTO_RETRY_COUNT", ui.spin(0, 20, "Automatic restarts")
        )
        self.queue_retries = self._bind_spin(
            "QUEUE_ERROR_RETRIES", ui.spin(0, 20, "Queue retries")
        )

        performance_card = ui.card(
            self._column(
                self._row("Max speed", self.limit_rate),
                self._row("Network retries", self.retries, ""),
                self._row(
                    "Restart attempts",
                    self.auto_retry,
                    "Re-run a download from scratch after a transient failure "
                    "such as an expired link or HTTP 403. 0 disables.",
                ),
                self._row(
                    "Queue retries",
                    self.queue_retries,
                    "Times a failed item returns to the back of the queue "
                    "before it is marked as an error.",
                ),
            ),
            title="Reliability",
            subtitle="Retry behaviour for unstable networks and rate limits.",
        )

        return self._page(network_card, performance_card)

    # -- Cookies -------------------------------------------------------

    def _page_cookies(self) -> QWidget:
        self.cookies_path = self._bind_text(
            "COOKIES_PATH",
            ui.line_edit("Path to cookies.txt", "Netscape-format cookie file", "Cookies file"),
        )
        cookies_row = ui.picker_row(self.cookies_path, "Browse\u2026", self._browse_cookies)

        self.cookies_browser = self._bind_combo_text(
            "COOKIES_FROM_BROWSER", ui.combo(BROWSERS, "Read cookies from browser")
        )
        self.cookies_auto = self._bind_switch(
            "COOKIES_AUTO_REFRESH", ui.switch("Refresh cookies automatically")
        )

        self.import_button = QPushButton("Import cookies now")
        self.import_button.setMinimumHeight(34)
        self.import_button.clicked.connect(self._import_cookies)

        self.cookies_status = QLabel()
        self.cookies_status.setObjectName("formDescription")
        self.cookies_status.setWordWrap(True)

        return self._page(
            ui.card(
                self._column(
                    self._row("Cookies file", cookies_row),
                    self._row(
                        "Read from browser",
                        self.cookies_browser,
                        "Takes precedence over the file above",
                    ),
                    self._row(
                        "Auto refresh",
                        self.cookies_auto,
                        "Re-export before every download. Slower, but keeps "
                        "long sessions from expiring mid-queue.",
                    ),
                    self._row("", self.import_button),
                    self.cookies_status,
                ),
                title="Cookies",
                subtitle="Needed for age-restricted, private and members-only content.",
            )
        )

    # -- SponsorBlock --------------------------------------------------

    def _page_sponsorblock(self) -> QWidget:
        holder = QWidget()
        self._sponsor_grid = QGridLayout(holder)
        self._sponsor_grid.setContentsMargins(0, 0, 0, 0)
        self._sponsor_grid.setHorizontalSpacing(16)
        self._sponsor_grid.setVerticalSpacing(5)

        for label, code in SPONSORBLOCK_CATEGORIES:
            box = ui.check(label, f"Remove {label.lower()} segments")
            self._sponsor_checks[code] = box

        self._layout_sponsorblock(2)
        self._sponsor_holder = holder

        return self._page(
            ui.card(
                holder,
                title="SponsorBlock",
                subtitle="Cut the selected segments out while downloading. "
                "Skipped for Shorts, which have no submissions.",
            )
        )

    def _layout_sponsorblock(self, columns: int) -> None:
        if self._sponsor_grid is None or columns == self._sponsor_columns:
            return
        self._sponsor_columns = columns
        while self._sponsor_grid.count():
            entry = self._sponsor_grid.takeAt(0)
            widget = entry.widget()
            if widget is not None:
                widget.setParent(self._sponsor_holder)
        for index, box in enumerate(self._sponsor_checks.values()):
            row, column = divmod(index, columns)
            self._sponsor_grid.addWidget(box, row, column)

    # -- Subtitles -----------------------------------------------------

    def _page_subtitles(self) -> QWidget:
        self.subs_enabled = self._bind_switch("WRITE_SUBS", ui.switch("Download subtitles"))
        self.sub_langs = self._bind_text(
            "SUB_LANGS",
            ui.line_edit("en,es,fr", "Two or three letter codes", "Subtitle languages"),
        )
        self.auto_subs = self._bind_check(
            "WRITE_AUTO_SUBS", ui.check("Include auto-generated subtitles")
        )
        self.convert_subs = self._bind_check(
            "CONVERT_SUBS_TO_SRT", ui.check("Convert subtitles to SRT")
        )

        self.subs_enabled.toggled.connect(self._on_subs_toggled)

        return self._page(
            ui.card(
                self._column(
                    self._row("Subtitles", self.subs_enabled, "Fetch subtitle tracks when available"),
                    self._row("Languages", self.sub_langs),
                    self._row("", self.auto_subs),
                    self._row("", self.convert_subs),
                ),
                title="Subtitles",
            )
        )

    def _on_subs_toggled(self, enabled: bool) -> None:
        for widget in (self.sub_langs, self.auto_subs, self.convert_subs):
            widget.setEnabled(enabled)

    # -- Playlist ------------------------------------------------------

    def _page_playlist(self) -> QWidget:
        self.archive_enabled = self._bind_switch(
            "ENABLE_ARCHIVE", ui.switch("Use a download archive")
        )
        self.archive_path = self._bind_text(
            "ARCHIVE_PATH",
            ui.line_edit("Path to archive.txt", "Records what has been downloaded", "Archive file"),
        )
        archive_row = ui.picker_row(self.archive_path, "Browse\u2026", self._browse_archive)

        self.playlist_reverse = self._bind_switch(
            "PLAYLIST_REVERSE", ui.switch("Reverse playlist order")
        )
        self.playlist_items = self._bind_text(
            "PLAYLIST_ITEMS",
            ui.line_edit("e.g. 1,5-10,15", "Indices and ranges", "Playlist items"),
        )

        self.archive_enabled.toggled.connect(self.archive_path.setEnabled)

        return self._page(
            ui.card(
                self._column(
                    self._row("Archive", self.archive_enabled, "Skip items already downloaded"),
                    self._row("Archive file", archive_row),
                    self._row("Order", self.playlist_reverse, "Download from last to first"),
                    self._row("Items", self.playlist_items),
                ),
                title="Playlists",
            )
        )

    # -- Output --------------------------------------------------------

    def _page_output(self) -> QWidget:
        self.downloads_dir = self._bind_text(
            "DOWNLOADS_DIR",
            ui.line_edit("Download folder", "Where finished files are written", "Download folder"),
        )
        downloads_row = ui.picker_row(self.downloads_dir, "Browse\u2026", self._browse_downloads)

        self.filename_combo = self._bind_combo_mapped(
            "FILENAME_FORMAT", ui.combo([], "Filename format"), FILENAME_CHOICES, "default"
        )
        self.filename_preview = QLabel()
        self.filename_preview.setObjectName("helpBoxExample")
        self.filename_preview.setTextFormat(Qt.RichText)
        self.filename_preview.setWordWrap(True)

        self.custom_filename = self._bind_text(
            "CUSTOM_FILENAME_TEMPLATE",
            ui.line_edit(
                "%(artist)s - %(title)s",
                "A yt-dlp field template with no path or extension",
                "Custom filename template",
            ),
        )
        self.custom_filename_row = self._row("Custom template", self.custom_filename)
        self.filename_help = self._build_filename_help()

        self.filename_combo.currentIndexChanged.connect(self._on_filename_changed)

        self.organize_uploader = self._bind_switch(
            "ORGANIZE_BY_UPLOADER", ui.switch("Group by uploader")
        )
        self.video_container = self._bind_combo_text(
            "VIDEO_FORMAT", ui.combo(VIDEO_CONTAINERS, "Video container")
        )

        self.date_after = self._bind_text(
            "DATEAFTER", ui.line_edit("YYYYMMDD", "Only items uploaded on or after", "Upload date filter")
        )
        date_row = ui.picker_row(self.date_after, "Pick\u2026", self._pick_date)

        return self._page(
            ui.card(
                self._column(
                    self._row("Folder", downloads_row),
                    self._row("Grouping", self.organize_uploader, "Create one folder per uploader"),
                    self._row("Video container", self.video_container, "Used for video downloads"),
                    self._row("Only after", date_row),
                ),
                title="Destination",
            ),
            ui.card(
                self._column(
                    self._row("Naming", self.filename_combo, "How files are named on disk"),
                    self.filename_preview,
                    self.custom_filename_row,
                    self.filename_help,
                ),
                title="File names",
            ),
        )

    def _build_filename_help(self) -> QWidget:
        box = QWidget()
        box.setObjectName("helpBox")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        heading = QLabel("Available fields")
        heading.setObjectName("helpBoxTitle")
        layout.addWidget(heading)

        groups: Tuple[Tuple[str, Tuple[Tuple[str, str], ...]], ...] = (
            ("TITLE & MEDIA", (
                ("title", "song or video title"),
                ("ext", "file extension"),
                ("duration_string", "length"),
                ("resolution", "e.g. 1920x1080"),
            )),
            ("PEOPLE", (
                ("artist", "track artist"),
                ("uploader", "uploader name"),
                ("channel", "channel name"),
            )),
            ("ALBUM & PLAYLIST", (
                ("album", "album name"),
                ("track_number", "track number"),
                ("playlist_title", "playlist name"),
                ("playlist_index", "position in playlist"),
            )),
            ("OTHER", (
                ("id", "unique ID"),
                ("upload_date", "YYYYMMDD"),
                ("release_year", "release year"),
                ("autonumber", "download sequence"),
            )),
        )

        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(4)
        for column, (name, fields) in enumerate(groups):
            heading_label = QLabel(name)
            heading_label.setObjectName("helpBoxCategory")
            grid.addWidget(heading_label, 0, column)

            body = "<br>".join(
                f"<code>%({field})s</code> &nbsp;"
                f"<span style='opacity:0.8;'>{description}</span>"
                for field, description in fields
            )
            tokens = QLabel(body)
            tokens.setObjectName("helpBoxTokens")
            tokens.setTextFormat(Qt.RichText)
            tokens.setWordWrap(True)
            tokens.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(tokens, 1, column, Qt.AlignTop)
            grid.setColumnStretch(column, 1)
        layout.addLayout(grid)

        example = QLabel(
            "Example: <code>%(artist)s - %(title)s</code> "
            "\u2192 <i>Tony Ann - Icarus.mp3</i>"
        )
        example.setObjectName("helpBoxExample")
        example.setTextFormat(Qt.RichText)
        layout.addWidget(example)
        return box

    def _on_filename_changed(self, _index: int = 0) -> None:
        value = self._filename_value()
        custom = value == "custom"
        self.custom_filename_row.setVisible(custom)
        self.filename_help.setVisible(custom)
        self.custom_filename.setEnabled(custom)

        if value == "default":
            self.filename_preview.setText(
                "<i>Uses the smart default for each download type.</i>"
            )
            self.filename_preview.setVisible(True)
        elif custom:
            self.filename_preview.setVisible(False)
        else:
            template = FILENAME_FORMAT_PRESETS.get(value, "")
            text = f"Template: <code>{template}.%(ext)s</code>"
            if value in ("track_title", "album_track_title"):
                text += (
                    " <i>The track number comes from the playlist position, so "
                    "single downloads show \u201cUnknown\u201d.</i>"
                )
            self.filename_preview.setText(text)
            self.filename_preview.setVisible(True)
        self._validate()

    def _filename_value(self) -> str:
        index = self.filename_combo.currentIndex()
        if 0 <= index < len(FILENAME_CHOICES):
            return FILENAME_CHOICES[index][1]
        return "default"

    # -- Processing ----------------------------------------------------

    def _page_processing(self) -> QWidget:
        self.add_metadata = self._bind_switch("ADD_METADATA", ui.switch("Write metadata tags"))
        self.audio_normalize = self._bind_switch(
            "AUDIO_NORMALIZE", ui.switch("Normalise loudness")
        )
        self.crop_covers = self._bind_switch(
            "CROP_AUDIO_COVERS", ui.switch("Crop album art to a square")
        )
        self.yt_music = self._bind_switch(
            "YT_MUSIC_METADATA", ui.switch("Enhanced YouTube Music metadata")
        )
        self.live_from_start = self._bind_switch(
            "LIVE_FROM_START", ui.switch("Record live streams from the start")
        )

        self.chapters_combo = self._bind_combo_mapped(
            "CHAPTERS_MODE", ui.combo([], "Chapter handling"), CHAPTER_CHOICES, "embed"
        )

        self.custom_ffmpeg = self._bind_text(
            "CUSTOM_FFMPEG_ARGS",
            ui.line_edit("-c:v libx265 -crf 23", "Extra ffmpeg arguments", "ffmpeg arguments"),
        )

        return self._page(
            ui.card(
                self._column(
                    self._row("Metadata", self.add_metadata, "Title, artist and album tags"),
                    self._row(
                        "Loudness",
                        self.audio_normalize,
                        "Apply EBU R128 normalisation to \u221214 LUFS",
                    ),
                    self._row("Album art", self.crop_covers, "Centre-crop covers to 1:1 after the queue"),
                    self._row("Chapters", self.chapters_combo),
                ),
                title="Post-processing",
            ),
            ui.card(
                self._column(
                    self._row(
                        "YouTube Music",
                        self.yt_music,
                        "Better artist and album detection for music.youtube.com",
                    ),
                    self._row("Live streams", self.live_from_start, "Rewind to the beginning"),
                    self._row("ffmpeg arguments", self.custom_ffmpeg),
                ),
                title="Extras",
                subtitle="These are experimental and may change between releases.",
            ),
        )

    # -- Thumbnails ----------------------------------------------------

    def _page_thumbnails(self) -> QWidget:
        self.embed_thumbnail = self._bind_switch(
            "EMBED_THUMBNAIL", ui.switch("Embed the thumbnail")
        )
        self.write_thumbnail = self._bind_switch(
            "WRITE_THUMBNAIL", ui.switch("Keep the thumbnail file")
        )
        self.convert_thumbnails = self._bind_switch(
            "CONVERT_THUMBNAILS", ui.switch("Convert thumbnails")
        )
        self.thumbnail_format = self._bind_combo_text(
            "THUMBNAIL_FORMAT", ui.combo(THUMBNAIL_FORMATS, "Thumbnail format")
        )
        self.convert_thumbnails.toggled.connect(self.thumbnail_format.setEnabled)

        return self._page(
            ui.card(
                self._column(
                    self._row("Embed", self.embed_thumbnail, "Store the cover inside the media file"),
                    self._row("Keep file", self.write_thumbnail, "Save the image alongside the download"),
                    self._row("Convert", self.convert_thumbnails, "WebP thumbnails are not universally supported"),
                    self._row("Format", self.thumbnail_format),
                ),
                title="Thumbnails",
            )
        )

    # -- Advanced ------------------------------------------------------

    def _page_advanced(self) -> QWidget:
        self.player_client = self._bind_combo_mapped(
            "YOUTUBE_PLAYER_CLIENT",
            ui.combo([], "YouTube player client"),
            tuple(YOUTUBE_PLAYER_CLIENTS.items()),
            "auto",
        )
        self.extra_args = self._bind_text(
            "EXTRA_YTDLP_ARGS",
            ui.line_edit(
                "--sleep-interval 15 --max-sleep-interval 20",
                "Appended to every yt-dlp command, after all other flags",
                "Extra yt-dlp arguments",
            ),
        )

        self.prefer_hls = self._bind_switch("PREFER_HLS", ui.switch("Prefer HLS streams"))
        self.hls_domains = self._register(
            "HLS_PREFERRED_DOMAINS",
            ui.line_edit(
                "example.com, cdn.example.net",
                "Comma-separated hosts. YouTube is always excluded.",
                "HLS domains",
            ),
            lambda: [
                part.strip().lower()
                for part in self.hls_domains.text().split(",")
                if part.strip()
            ],
            lambda value: self.hls_domains.setText(", ".join(value or [])),
        )
        self.prefer_hls.toggled.connect(self.hls_domains.setEnabled)

        self.max_log_lines = self._bind_spin(
            "MAX_LOG_LINES", ui.spin(100, 50_000, "Console history", " lines")
        )
        self.log_thumbnails = self._bind_check(
            "LOG_THUMBNAILS", ui.check("Log thumbnail failures")
        )
        self.confirm_quit = self._bind_check(
            "CONFIRM_ON_QUIT", ui.check("Ask before quitting during a download")
        )

        return self._page(
            ui.card(
                self._column(
                    self._row(
                        "Player client",
                        self.player_client,
                        "Override the extraction client when the default one breaks",
                    ),
                    self._row("Extra arguments", self.extra_args),
                ),
                title="yt-dlp",
                subtitle="These override the application's own flags.",
            ),
            ui.card(
                self._column(
                    self._row(
                        "Prefer HLS",
                        self.prefer_hls,
                        "Only for sites that do not offer usable DASH streams. "
                        "Forcing HLS elsewhere lowers the maximum resolution.",
                    ),
                    self._row("Domains", self.hls_domains),
                ),
                title="Streaming protocol",
            ),
            ui.card(
                self._column(
                    self._row("Console history", self.max_log_lines),
                    self._row("", self.log_thumbnails),
                    self._row("", self.confirm_quit),
                ),
                title="Interface",
            ),
        )

    # ==================================================================
    # Load / save
    # ==================================================================

    def _load(self) -> None:
        for binding in self._bindings:
            value = getattr(self.settings, binding.key, None)
            if isinstance(value, Path):
                value = str(value)
            blocker = QSignalBlocker(binding.widget)
            try:
                binding.set(value)
            except Exception:  # noqa: BLE001 - a bad stored value must not block the dialog
                log.debug("Could not load %s", binding.key, exc_info=True)
            finally:
                del blocker

        selected = set(getattr(self.settings, "SPONSORBLOCK_CATEGORIES", []) or [])
        for code, box in self._sponsor_checks.items():
            box.setChecked(code in selected)

        last = getattr(self.settings, "COOKIES_LAST_IMPORTED", "")
        self.cookies_status.setText(f"Last imported: {last}" if last else "")

        self._on_subs_toggled(self.subs_enabled.isChecked())
        self.archive_path.setEnabled(self.archive_enabled.isChecked())
        self.thumbnail_format.setEnabled(self.convert_thumbnails.isChecked())
        self.hls_domains.setEnabled(self.prefer_hls.isChecked())
        self._on_filename_changed()
        self._snapshot = self.get_settings()

    def get_settings(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        for binding in self._bindings:
            try:
                data[binding.key] = binding.get()
            except Exception:  # noqa: BLE001
                log.debug("Could not read %s", binding.key, exc_info=True)

        data["SPONSORBLOCK_CATEGORIES"] = [
            code for code, box in self._sponsor_checks.items() if box.isChecked()
        ]
        data["COOKIES_LAST_IMPORTED"] = getattr(
            self.settings, "COOKIES_LAST_IMPORTED", ""
        )

        # Empty path fields fall back to the current value rather than being
        # written as "", which Path() turns into "." -- that produced
        # `--cookies .` and `--download-archive .` on every invocation.
        for key, fallback in (
            ("COOKIES_PATH", self.settings.COOKIES_PATH),
            ("ARCHIVE_PATH", self.settings.ARCHIVE_PATH),
            ("DOWNLOADS_DIR", self.settings.DOWNLOADS_DIR),
        ):
            text = str(data.get(key) or "").strip()
            data[key] = Path(text) if text else Path(fallback)

        return data

    def apply(self) -> None:
        """Write the form into settings. Called by MainWindow on accept."""
        self.settings.apply(self.get_settings())
        try:
            self.spotdl_tab.apply(self.settings.SPOTDL)
            self.settings.SPOTDL.normalise()
        except Exception:  # noqa: BLE001
            log.exception("Could not apply SpotDL preferences")
        self._snapshot = self.get_settings()
        self._set_dirty(False)

    def _reset(self) -> None:
        if not self._snapshot:
            return
        for binding in self._bindings:
            if binding.key not in self._snapshot:
                continue
            value = self._snapshot[binding.key]
            if isinstance(value, Path):
                value = str(value)
            blocker = QSignalBlocker(binding.widget)
            try:
                binding.set(value)
            finally:
                del blocker

        selected = set(self._snapshot.get("SPONSORBLOCK_CATEGORIES", []))
        for code, box in self._sponsor_checks.items():
            box.setChecked(code in selected)

        self._on_filename_changed()
        self._set_dirty(False)
        self._validate()

    # ==================================================================
    # Dirty tracking
    # ==================================================================

    def _wire(self) -> None:
        watched: List[QWidget] = [b.widget for b in self._bindings]
        watched.extend(self._sponsor_checks.values())

        for widget in watched:
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self._on_changed)
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._on_changed)
            elif isinstance(widget, QSpinBox):
                widget.valueChanged.connect(self._on_changed)
            elif isinstance(widget, (QCheckBox, UISwitch, QRadioButton)):
                widget.toggled.connect(self._on_changed)

        for widget in (
            self.proxy_input,
            self.ca_cert_input,
            self.limit_rate,
            self.sub_langs,
            self.playlist_items,
            self.date_after,
            self.custom_filename,
            self.downloads_dir,
        ):
            widget.textChanged.connect(self._validate)

        self.subs_enabled.toggled.connect(self._validate)
        self.filename_combo.currentIndexChanged.connect(self._validate)

    def _on_changed(self, *_args) -> None:
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self.status_label.setText(
            "\u25cf Unsaved changes \u2014 press Ctrl+S to save"
            if dirty
            else "\u2713 All changes saved"
        )
        self.status_label.setProperty("state", "dirty" if dirty else "clean")
        style = self.status_label.style()
        style.unpolish(self.status_label)
        style.polish(self.status_label)
        self.reset_button.setEnabled(dirty)

    # ==================================================================
    # Validation
    # ==================================================================

    def validate_filename_template(self, text: str) -> Tuple[bool, str]:
        raw = text.strip()
        if not raw:
            return False, "Enter a template, e.g. %(title)s"
        if len(raw) > 180:
            return False, "Template is too long (180 characters maximum)"
        if raw != raw.strip(" ."):
            return False, "Cannot start or end with a space or a period"

        # Mask escaped percent signs so they cannot be mistaken for a
        # malformed placeholder.
        working = raw.replace("%%", "\u0000")

        found = False
        literals: List[str] = []
        position = 0
        for match in _PLACEHOLDER_RE.finditer(working):
            found = True
            literals.append(working[position : match.start()])
            for field in match.group("fields").split(","):
                if field not in ALLOWED_TEMPLATE_FIELDS:
                    return False, f"Unknown field: %({field})s"
            position = match.end()
        literals.append(working[position:])

        remainder = "".join(literals)
        if "%" in remainder:
            return False, "Malformed placeholder \u2014 use %(field)s"
        if _ILLEGAL_LITERAL_RE.search(remainder.replace("\u0000", "%")):
            return False, "Cannot contain \\ / : * ? \" < > | or control characters"
        if not found:
            return False, "Include at least one field, e.g. %(title)s"
        return True, ""

    def _validate(self) -> None:
        proxy_ok = is_valid_proxy(self.proxy_input.text())
        ui.set_error(
            self.proxy_input, not proxy_ok,
            "Use http://, https://, socks4:// or socks5://",
        )

        ca_text = self.ca_cert_input.text().strip()
        ca_ok = not ca_text or Path(ca_text).is_file()
        ui.set_error(self.ca_cert_input, not ca_ok, "That file does not exist")

        rate_ok = is_valid_rate_limit(self.limit_rate.text())
        ui.set_error(self.limit_rate, not rate_ok, "Use a number with K, M or G")

        langs_needed = self.subs_enabled.isChecked()
        langs_text = self.sub_langs.text().strip()
        langs_ok = (not langs_needed) or (
            bool(langs_text) and is_valid_sub_langs(langs_text)
        )
        ui.set_error(
            self.sub_langs, not langs_ok, "Two or three letter codes, e.g. en, es, fra"
        )

        items_ok = is_valid_playlist_items(self.playlist_items.text())
        ui.set_error(self.playlist_items, not items_ok, "Use indices and ranges: 1,5-10,15")

        date_ok = is_valid_dateafter(self.date_after.text())
        ui.set_error(self.date_after, not date_ok, "Use YYYYMMDD, e.g. 20240101")

        folder_text = self.downloads_dir.text().strip()
        folder_ok = not folder_text or not Path(folder_text).is_file()
        ui.set_error(self.downloads_dir, not folder_ok, "That is a file, not a folder")

        if self._filename_value() == "custom":
            name_ok, name_error = self.validate_filename_template(
                self.custom_filename.text()
            )
        else:
            name_ok, name_error = True, ""
        ui.set_error(self.custom_filename, not name_ok, name_error)

        valid = all(
            (proxy_ok, ca_ok, rate_ok, langs_ok, items_ok, date_ok, folder_ok, name_ok)
        )
        save = self.buttons.button(QDialogButtonBox.Save)
        if save is not None:
            save.setEnabled(valid)
            save.setDefault(valid)
            save.setToolTip(
                "Save changes" if valid else "Fix the highlighted fields to save"
            )

    def _first_invalid(self) -> Optional[QWidget]:
        for binding in self._bindings:
            if (binding.widget.property("state") or "") == "error":
                return binding.widget
        return None

    # ==================================================================
    # Pickers
    # ==================================================================

    def _browse_cookies(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Cookies File", str(self.settings.BASE_DIR),
            "Cookies (*.txt *.json);;All Files (*)",
        )
        if path:
            self.cookies_path.setText(path)

    def _browse_ca(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select CA Certificate", str(self.settings.BASE_DIR),
            "Certificates (*.crt *.pem *.cer);;All Files (*)",
        )
        if path:
            self.ca_cert_input.setText(path)

    def _browse_archive(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Select Archive File", str(self.settings.ARCHIVE_PATH),
            "Text Files (*.txt);;All Files (*)",
        )
        if path:
            self.archive_path.setText(path)

    def _browse_downloads(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select Download Folder", str(self.settings.DOWNLOADS_DIR)
        )
        if path:
            self.downloads_dir.setText(path)

    def _pick_date(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Date")
        dialog.setStyleSheet(ui.dialog_qss())
        layout = QVBoxLayout(dialog)

        calendar = QCalendarWidget()
        calendar.setGridVisible(True)
        current = self.date_after.text().strip()
        if current:
            try:
                parsed = datetime.datetime.strptime(current, "%Y%m%d").date()
                calendar.setSelectedDate(QDate(parsed.year, parsed.month, parsed.day))
            except ValueError:
                pass
        layout.addWidget(calendar)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec():
            self.date_after.setText(calendar.selectedDate().toString("yyyyMMdd"))

    def _import_cookies(self) -> None:
        browser = self.cookies_browser.currentText().strip()
        if not browser:
            QMessageBox.information(
                self, "Choose a browser",
                "Select a browser to import cookies from first.",
            )
            return

        target = Path(self.settings.BASE_DIR) / "cookies.txt"
        self.import_button.setEnabled(False)
        try:
            ok, message = cookie_manager.export_for_browser(browser, target)
        finally:
            self.import_button.setEnabled(True)

        if not ok:
            QMessageBox.warning(self, "Import failed", message)
            return

        stamp = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
        self.cookies_path.setText(str(target))
        self.cookies_status.setText(f"Last imported: {target.name} ({stamp})")
        self.settings.COOKIES_LAST_IMPORTED = f"{target.name} ({stamp})"
        self.settings.COOKIES_PATH = target
        self.settings.save_config()
        QMessageBox.information(self, "Cookies imported", message)

    # ==================================================================
    # Navigation / events
    # ==================================================================

    def _step(self, delta: int) -> None:
        count = self.sidebar.count()
        if count:
            self.sidebar.setCurrentRow((self.sidebar.currentRow() + delta) % count)

    def _sync_navigation(self, index: int) -> None:
        if not 0 <= index < self.stack.count():
            return
        if self.sidebar.currentRow() != index:
            blocker = QSignalBlocker(self.sidebar)
            self.sidebar.setCurrentRow(index)
            del blocker
        if self.section_combo.currentIndex() != index:
            blocker = QSignalBlocker(self.section_combo)
            self.section_combo.setCurrentIndex(index)
            del blocker

    def _update_responsive(self) -> None:
        narrow = self.width() < self.NARROW_WIDTH
        self.sidebar.setVisible(not narrow)
        self.section_combo.setVisible(narrow)
        self._sync_navigation(self.stack.currentIndex())

        available = max(0, self.stack.width() - 64)
        if available >= 900:
            columns = 4
        elif available >= 700:
            columns = 3
        elif available >= 460:
            columns = 2
        else:
            columns = 1
        self._layout_sponsorblock(columns)

    def _align_labels(self) -> None:
        metrics = self.fontMetrics()
        width = max(
            (metrics.horizontalAdvance(label.text()) for label in self._labels),
            default=0,
        )
        for label in self._labels:
            label.setMinimumWidth(width + 8)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_responsive()

    def _accept(self) -> None:
        self._validate()
        save = self.buttons.button(QDialogButtonBox.Save)
        if save is not None and not save.isEnabled():
            invalid = self._first_invalid()
            if invalid is not None:
                invalid.setFocus(Qt.OtherFocusReason)
                QToolTip.showText(
                    invalid.mapToGlobal(invalid.rect().bottomLeft()),
                    invalid.toolTip(),
                    invalid,
                )
            return
        self.accept()

    def _reject(self) -> None:
        if self._dirty:
            answer = QMessageBox.question(
                self,
                "Discard changes?",
                "You have unsaved changes. Discard them and close?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        self.reject()
