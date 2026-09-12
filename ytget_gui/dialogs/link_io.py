# File: ytget_gui/dialogs/link_io.py
"""Plain-text link import/export dialogs.

Importing is deliberately a review step rather than a silent bulk add: a text
file is usually hand-assembled, so it tends to contain stale lines, duplicates
and the odd non-URL. The dialog shows exactly what was parsed, lets each line
be excluded, and allows either one format for everything or a per-link choice.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ytget_gui.dialogs import common as ui

# A line may be a bare URL or "url | Format label" / "url<TAB>Format label",
# which is what this module's own export writes.
_SPLIT = re.compile(r"\s*(?:\||\t)\s*")
_COMMENT = ("#", ";", "//")

EXPORT_SCOPES: Tuple[Tuple[str, str], ...] = (
    ("Everything in the queue", "all"),
    ("Selected items only", "selected"),
    ("Waiting items only", "pending"),
    ("Finished items only", "completed"),
    ("Failed items only", "error"),
)


def parse_link_file(text: str) -> Tuple[List[Tuple[str, str]], int]:
    """Return ``([(url, format_label_or_empty)], skipped_line_count)``.

    One link per line. Blank lines and comments are ignored silently; anything
    else that does not look like a URL is counted as skipped so the caller can
    report it instead of losing it quietly.
    """
    pairs: List[Tuple[str, str]] = []
    skipped = 0
    seen: set[str] = set()

    for raw in text.splitlines():
        line = raw.strip().strip("\ufeff")
        if not line or line.startswith(_COMMENT):
            continue

        parts = _SPLIT.split(line, maxsplit=1)
        url = parts[0].strip().strip("<>\"'")
        label = parts[1].strip() if len(parts) > 1 else ""

        if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://\S+$", url):
            # Tolerate a bare "www." or "youtube.com/..." line.
            if re.match(r"^(?:www\.)?[\w.-]+\.[a-z]{2,}/\S*$", url, re.IGNORECASE):
                url = "https://" + url
            else:
                skipped += 1
                continue

        if url in seen:
            continue
        seen.add(url)
        pairs.append((url, label))

    return pairs, skipped


class LinkImportDialog(QDialog):
    """Review parsed links and pick formats before queueing."""

    _COL_USE = 0
    _COL_LINK = 1
    _COL_FORMAT = 2

    def __init__(
        self,
        parent: Optional[QWidget],
        pairs: Sequence[Tuple[str, str]],
        format_labels: Sequence[str],
        default_label: str,
        *,
        source: str = "",
        already_queued: Sequence[str] = (),
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import Links")
        self.setModal(True)
        self.setStyleSheet(ui.dialog_qss())
        self.resize(820, 520)

        self._labels = list(format_labels)
        self._default = default_label if default_label in self._labels else (
            self._labels[0] if self._labels else ""
        )
        queued = {u for u in already_queued}

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        heading = f"{len(pairs)} link(s) found"
        if source:
            heading += f" in {source}"
        root.addWidget(ui.section_label(heading))

        # -- bulk format row ------------------------------------------
        bulk = QHBoxLayout()
        bulk.setSpacing(8)
        bulk.addWidget(ui.form_label("Format for all links"))
        self.bulk_combo = ui.combo(self._labels, "Format for all links")
        self.bulk_combo.setCurrentText(self._default)
        bulk.addWidget(self.bulk_combo, 1)
        apply_all = QPushButton("Apply to all")
        apply_all.clicked.connect(self._apply_to_all)
        bulk.addWidget(apply_all)
        root.addLayout(bulk)

        # -- table ----------------------------------------------------
        self.table = QTableWidget(len(pairs), 3, self)
        self.table.setHorizontalHeaderLabels(["Add", "Link", "Format"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(self._COL_USE, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self._COL_LINK, QHeaderView.Stretch)
        header.setSectionResizeMode(self._COL_FORMAT, QHeaderView.ResizeToContents)

        self._combos: List[QComboBox] = []
        for row, (url, label) in enumerate(pairs):
            duplicate = url in queued

            use = QTableWidgetItem()
            use.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            use.setCheckState(Qt.Unchecked if duplicate else Qt.Checked)
            if duplicate:
                use.setToolTip("Already in the queue")
            self.table.setItem(row, self._COL_USE, use)

            link_item = QTableWidgetItem(url + ("  (already queued)" if duplicate else ""))
            link_item.setToolTip(url)
            self.table.setItem(row, self._COL_LINK, link_item)

            combo = ui.combo(self._labels, "Format")
            combo.setCurrentText(label if label in self._labels else self._default)
            self.table.setCellWidget(row, self._COL_FORMAT, combo)
            self._combos.append(combo)

        self.table.setRowHeight(0, 30) if pairs else None
        root.addWidget(self.table, 1)

        # -- selection helpers ----------------------------------------
        tools = QHBoxLayout()
        tools.setSpacing(8)
        for text, state in (("Select all", True), ("Select none", False)):
            button = QPushButton(text)
            button.clicked.connect(lambda _=False, s=state: self._set_all(s))
            tools.addWidget(button)
        tools.addStretch(1)
        self.count_label = QLabel("")
        self.count_label.setObjectName("muted")
        tools.addWidget(self.count_label)
        root.addLayout(tools)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.button(QDialogButtonBox.Ok).setText("Add to Queue")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._ok_button = buttons.button(QDialogButtonBox.Ok)

        self.table.itemChanged.connect(self._refresh_count)
        self._refresh_count()

    # ------------------------------------------------------------------
    def _apply_to_all(self) -> None:
        label = self.bulk_combo.currentText()
        for combo in self._combos:
            combo.setCurrentText(label)

    def _set_all(self, checked: bool) -> None:
        state = Qt.Checked if checked else Qt.Unchecked
        for row in range(self.table.rowCount()):
            item = self.table.item(row, self._COL_USE)
            if item is not None:
                item.setCheckState(state)

    def _refresh_count(self, *_args) -> None:
        count = len(self.selections())
        self.count_label.setText(f"{count} selected")
        self._ok_button.setEnabled(count > 0)

    def selections(self) -> List[Tuple[str, str]]:
        """Checked rows as ``(url, format_label)``."""
        out: List[Tuple[str, str]] = []
        for row in range(self.table.rowCount()):
            use = self.table.item(row, self._COL_USE)
            link = self.table.item(row, self._COL_LINK)
            if use is None or link is None or use.checkState() != Qt.Checked:
                continue
            url = link.toolTip() or link.text()
            out.append((url, self._combos[row].currentText()))
        return out

    def grouped(self) -> Dict[str, List[str]]:
        """Selections grouped by format label, preserving file order."""
        groups: Dict[str, List[str]] = {}
        for url, label in self.selections():
            groups.setdefault(label, []).append(url)
        return groups


class LinkExportDialog(QDialog):
    """Choose which links to write out, and whether to keep the formats."""

    def __init__(
        self,
        parent: Optional[QWidget],
        counts: Dict[str, int],
        *,
        has_selection: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Links")
        self.setModal(True)
        self.setStyleSheet(ui.dialog_qss())

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)
        root.addWidget(ui.section_label("Write one link per line to a text file"))

        self._values: List[str] = []
        labels: List[str] = []
        for label, value in EXPORT_SCOPES:
            if value == "selected" and not has_selection:
                continue
            count = counts.get(value, 0)
            labels.append(f"{label}  ({count})")
            self._values.append(value)

        self.scope_combo = ui.combo(labels, "What to export")
        root.addWidget(ui.form_row("Include", self.scope_combo, label_registry=None))

        self.with_formats = ui.check(
            "Write the format after each link",
            "Saves as \"url | Format\", which YTGet reads back on import.",
        )
        self.with_formats.setChecked(True)
        self.with_header = ui.check(
            "Add a comment header",
            "A leading # line with the date and item count.",
        )
        self.with_header.setChecked(True)
        root.addWidget(self.with_formats)
        root.addWidget(self.with_header)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.button(QDialogButtonBox.Ok).setText("Choose File\u2026")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    @property
    def scope(self) -> str:
        index = self.scope_combo.currentIndex()
        return self._values[index] if 0 <= index < len(self._values) else "all"

    @property
    def include_formats(self) -> bool:
        return self.with_formats.isChecked()

    @property
    def include_header(self) -> bool:
        return self.with_header.isChecked()
