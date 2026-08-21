# File: ytget_gui/dialogs/common.py
"""Shared dialog building blocks.

preferences.py and advanced.py had near-identical private helpers for cards,
form rows, dividers, line edits and error styling, plus two separately
maintained copies of the same 200-line stylesheet. Both now come from here.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ytget_gui.styles import Palette as P
from ytget_gui.widgets.ui_switch import UISwitch

__all__ = [
    "dialog_qss",
    "divider",
    "form_label",
    "section_label",
    "line_edit",
    "combo",
    "spin",
    "check",
    "switch",
    "card",
    "form_row",
    "picker_row",
    "set_error",
    "wrap_scroll",
]


@lru_cache(maxsize=1)
def dialog_qss() -> str:
    """Stylesheet shared by every dialog. Cascades to descendants."""
    return f"""
QDialog {{
    background: {P.PAGE_GRADIENT};
    color: {P.TEXT};
    font-family: {P.UI_FONTS};
}}
QLabel {{ color: {P.TEXT}; background: transparent; }}

#brandIcon {{
    border-radius: 12px;
    font-size: 18px;
    font-weight: 700;
    color: #ffffff;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {P.ACCENT}, stop:1 {P.ACCENT_ALT});
    border: 1px solid rgba(255, 255, 255, 40);
}}
#dlgTitle {{ font-size: 20px; font-weight: 800; color: {P.TEXT}; }}
#dlgSubtitle {{ font-size: 12px; color: {P.TEXT_MUTED}; }}
#sectionLabel {{
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
    color: {P.ACCENT};
    padding: 4px 0 2px 0;
}}
#formLabel {{ font-size: 12.5px; color: {P.TEXT_MUTED}; background: transparent; }}
#formDescription {{ font-size: 12px; color: {P.TEXT_MUTED}; background: transparent; }}

QListWidget#sidebar {{
    background: rgba(10, 10, 25, 180);
    border: 1px solid {P.GLASS_BORDER};
    border-radius: 16px;
    padding: 6px;
    outline: 0;
}}
QListWidget#sidebar::item {{
    padding: 7px 10px 7px 12px;
    margin: 1px 2px;
    border-radius: 11px;
    color: {P.TEXT_MUTED};
    font-size: 13px;
    font-weight: 500;
    border: 1px solid transparent;
}}
QListWidget#sidebar::item:hover {{ background: {P.GLASS_BG}; color: {P.TEXT}; }}
QListWidget#sidebar::item:selected {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(0, 229, 255, 40), stop:1 rgba(124, 77, 255, 25));
    border: 1px solid rgba(0, 229, 255, 60);
    color: {P.TEXT};
    font-weight: 700;
}}

QFrame#card {{
    background: {P.GLASS_BG};
    border: 1px solid {P.GLASS_BORDER};
    border-radius: 16px;
}}
QLabel#cardTitle {{
    font-size: 14.5px;
    font-weight: 700;
    color: {P.TEXT};
    background: transparent;
}}
QLabel#cardSubtitle {{ font-size: 12px; color: {P.TEXT_MUTED}; background: transparent; }}

QFrame#helpBox {{
    background: rgba(0, 229, 255, 12);
    border: 1px dashed rgba(0, 229, 255, 50);
    border-radius: 12px;
}}
QLabel#helpBoxTitle {{
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
    color: {P.ACCENT};
    background: transparent;
}}
QLabel#helpBoxCategory {{
    font-size: 11px;
    font-weight: 700;
    color: {P.TEXT_MUTED};
    background: transparent;
}}
QLabel#helpBoxTokens {{ font-size: 12px; color: {P.TEXT}; background: transparent; }}
QLabel#helpBoxExample {{ font-size: 11px; color: {P.TEXT_MUTED}; background: transparent; }}

QLineEdit#input, QComboBox#combo, QSpinBox#spin {{
    background: {P.GLASS_BG};
    color: {P.TEXT};
    border: 1px solid {P.GLASS_BORDER};
    border-radius: 10px;
    padding: 6px 10px;
    selection-background-color: {P.ACCENT};
    selection-color: {P.WINDOW_BG};
    font-size: 13px;
}}
QLineEdit#input:hover, QComboBox#combo:hover, QSpinBox#spin:hover {{
    background: rgba(255, 255, 255, 22);
    border: 1px solid {P.GLASS_BORDER_HOVER};
}}
QLineEdit#input:focus, QComboBox#combo:focus, QSpinBox#spin:focus {{
    border: 1px solid {P.ACCENT};
    background: rgba(0, 229, 255, 12);
}}
QLineEdit#input[state="error"] {{
    border: 1px solid {P.ERROR};
    background: rgba(248, 113, 113, 25);
}}
QLineEdit#input:disabled, QComboBox#combo:disabled, QSpinBox#spin:disabled {{
    color: rgba(255, 255, 255, 80);
    background: rgba(255, 255, 255, 8);
    border: 1px solid rgba(255, 255, 255, 15);
}}
QComboBox#combo::drop-down {{ border: none; width: 24px; }}
QComboBox#combo::down-arrow {{
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid rgba(255, 255, 255, 150);
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background: {P.POPUP_BG};
    border: 1px solid {P.GLASS_BORDER};
    border-radius: 8px;
    color: {P.TEXT};
    selection-background-color: rgba(0, 229, 255, 80);
    padding: 4px;
    outline: none;
}}

QCheckBox#check, QRadioButton#radio {{
    color: {P.TEXT};
    font-size: 13px;
    spacing: 8px;
    background: transparent;
}}
QCheckBox#check::indicator, QRadioButton#radio::indicator {{
    width: 17px;
    height: 17px;
    border-radius: 5px;
    border: 1px solid {P.GLASS_BORDER};
    background: {P.GLASS_BG};
}}
QRadioButton#radio::indicator {{ border-radius: 9px; }}
QCheckBox#check::indicator:hover, QRadioButton#radio::indicator:hover {{
    border: 1px solid rgba(255, 255, 255, 65);
}}
QCheckBox#check::indicator:checked, QRadioButton#radio::indicator:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {P.ACCENT}, stop:1 {P.ACCENT_ALT});
    border: 1px solid {P.ACCENT};
}}

#divider {{
    background: {P.DIVIDER};
    min-height: 1px;
    max-height: 1px;
    border: none;
}}
#status {{ color: {P.TEXT_MUTED}; font-size: 12.5px; font-weight: 600; }}
#status[state="dirty"] {{ color: {P.WARNING}; }}
#status[state="clean"] {{ color: {P.SUCCESS}; }}

QScrollArea#scrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: rgba(255, 255, 255, 40);
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: rgba(255, 255, 255, 75); }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}

QPushButton {{
    background: {P.GLASS_BG};
    color: {P.TEXT};
    border: 1px solid {P.GLASS_BORDER};
    border-radius: 10px;
    padding: 7px 14px;
    font-size: 13px;
}}
QPushButton:hover {{
    background: rgba(255, 255, 255, 22);
    border: 1px solid {P.GLASS_BORDER_HOVER};
}}
QPushButton:disabled {{
    color: rgba(255, 255, 255, 60);
    background: rgba(255, 255, 255, 8);
    border: 1px solid rgba(255, 255, 255, 15);
}}
QDialogButtonBox QPushButton {{ font-weight: 700; min-width: 84px; }}
QDialogButtonBox QPushButton:default {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {P.ACCENT}, stop:1 {P.ACCENT_ALT});
    color: #ffffff;
    border: none;
}}
QDialogButtonBox QPushButton:default:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #33EEFF, stop:1 #9C6DFF);
}}
"""


# ----------------------------------------------------------------------
# Primitives
# ----------------------------------------------------------------------


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("divider")
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Plain)
    return line


def section_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("sectionLabel")
    return label


def form_label(text: str, tooltip: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("formLabel")
    if tooltip:
        label.setToolTip(tooltip)
    return label


def line_edit(
    placeholder: str = "", tooltip: str = "", accessible: str = ""
) -> QLineEdit:
    widget = QLineEdit()
    widget.setObjectName("input")
    widget.setClearButtonEnabled(True)
    widget.setMinimumHeight(34)
    if placeholder:
        widget.setPlaceholderText(placeholder)
    if tooltip:
        widget.setToolTip(tooltip)
    widget.setAccessibleName(accessible or placeholder or "Text field")
    return widget


def combo(items: Iterable[str], accessible: str = "") -> QComboBox:
    widget = QComboBox()
    widget.setObjectName("combo")
    widget.setMinimumHeight(34)
    widget.addItems(list(items))
    if accessible:
        widget.setAccessibleName(accessible)
    return widget


def spin(low: int, high: int, accessible: str = "", suffix: str = "") -> QSpinBox:
    widget = QSpinBox()
    widget.setObjectName("spin")
    widget.setMinimumHeight(34)
    widget.setRange(low, high)
    if suffix:
        widget.setSuffix(suffix)
    if accessible:
        widget.setAccessibleName(accessible)
    return widget


def check(text: str, tooltip: str = "") -> QCheckBox:
    widget = QCheckBox(text)
    widget.setObjectName("check")
    if tooltip:
        widget.setToolTip(tooltip)
    widget.setAccessibleName(text)
    return widget


def switch(accessible: str) -> UISwitch:
    widget = UISwitch("")
    widget.setAccessibleName(accessible)
    widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    return widget


def card(
    *children: QWidget,
    title: Optional[str] = None,
    subtitle: Optional[str] = None,
) -> QFrame:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(7)

    if title:
        header = QVBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        header.addWidget(title_label)
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("cardSubtitle")
            subtitle_label.setWordWrap(True)
            header.addWidget(subtitle_label)
        layout.addLayout(header)

    for child in children:
        layout.addWidget(child)

    effect = QGraphicsDropShadowEffect(frame)
    effect.setBlurRadius(18)
    effect.setColor(QColor(0, 0, 0, 60))
    effect.setOffset(0, 6)
    frame.setGraphicsEffect(effect)
    return frame


def form_row(
    label: str,
    widget: QWidget,
    description: str = "",
    label_registry: Optional[List[QLabel]] = None,
) -> QWidget:
    """Three-column row: [label] [description / field] [control].

    Fields span the middle and right columns; switches sit in the right column
    with an optional description beside them.
    """
    row = QWidget()
    grid = QGridLayout(row)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(14)
    grid.setVerticalSpacing(4)

    text_label = form_label(label)
    text_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if label_registry is not None:
        label_registry.append(text_label)
    grid.addWidget(text_label, 0, 0)

    is_switch = isinstance(widget, UISwitch)
    is_toggle = isinstance(widget, (QCheckBox, QRadioButton)) and not is_switch
    is_field = isinstance(widget, (QLineEdit, QComboBox, QSpinBox))

    if description and (is_switch or is_toggle):
        note = QLabel(description)
        note.setObjectName("formDescription")
        note.setWordWrap(True)
        note.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        grid.addWidget(note, 0, 1)
    else:
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        grid.addWidget(spacer, 0, 1)

    if is_switch:
        grid.addWidget(widget, 0, 2, Qt.AlignRight | Qt.AlignVCenter)
    elif is_field:
        policy = widget.sizePolicy()
        policy.setHorizontalPolicy(QSizePolicy.Expanding)
        widget.setSizePolicy(policy)
        grid.addWidget(widget, 0, 1, 1, 2)
    elif is_toggle:
        grid.addWidget(widget, 0, 1, 1, 2, Qt.AlignLeft | Qt.AlignVCenter)
    else:
        grid.addWidget(widget, 0, 1, 1, 2)

    grid.setColumnStretch(1, 1)
    return row


def picker_row(field: QLineEdit, button_text: str, callback: Callable[[], None]) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    button = QPushButton(button_text)
    button.setMinimumHeight(34)
    button.clicked.connect(callback)
    layout.addWidget(field, 1)
    layout.addWidget(button, 0)
    return row


def set_error(widget: QWidget, has_error: bool, tooltip: str = "") -> None:
    """Toggle the error style, repolishing only when the state changes."""
    current = widget.property("state") or ""
    wanted = "error" if has_error else ""
    if current != wanted:
        widget.setProperty("state", wanted)
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
    if has_error and tooltip:
        widget.setToolTip(tooltip)


def wrap_scroll(content: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setObjectName("scrollArea")
    area.setFrameShape(QFrame.NoFrame)
    area.setWidgetResizable(True)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    holder = QWidget()
    layout = QVBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    layout.addWidget(content)
    layout.addStretch(1)
    area.setWidget(holder)
    return area
