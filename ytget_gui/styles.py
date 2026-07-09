# File: ytget_gui/styles.py

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QFont

# Enable high-DPI scaling and pixmaps across all platforms
QGuiApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QGuiApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

# Compute a DPI scale factor (96 DPI as the baseline)
_app = QGuiApplication.instance()
if _app and _app.primaryScreen():
    dpi_scale = _app.primaryScreen().logicalDotsPerInch() / 96.0
else:
    dpi_scale = 1.0

# Define a global font scaled for the display’s DPI
GLOBAL_FONT = QFont("Inter")
GLOBAL_FONT.setPointSizeF(10 * dpi_scale)


class AppStyles:
    WINDOW_BG      = "#242731"   # was #1e1e1e — lifted, slight blue-grey tint
    WIDGET_BG      = "#2f333e"   # was #2e2e2e — a bit lighter, more separation from window
    TEXT_COLOR     = "#e8e8ee"   # was #e0e0e0 — slightly brighter for contrast
    PRIMARY_ACCENT = "#e91e63"   
    SUCCESS_COLOR  = "#00e676"
    ERROR_COLOR    = "#ff5252"
    WARNING_COLOR  = "#ffb74d"
    INFO_COLOR     = "#64b5f6"
    LOG_BG         = "#1a1c22"   # was #121212 — no longer near-black
    DIALOG_BG      = "#33374280" # was #2a2a2a — lighter, distinguishable from window

    # Main window background & text
    MAIN = f"background-color: {WINDOW_BG}; color: {TEXT_COLOR};"

    # Button styling with dynamic DPI-scaled metrics
    BUTTON = f"""
        QPushButton {{
            background-color: {PRIMARY_ACCENT};
            color: {TEXT_COLOR};
            font-size: {int(15 * dpi_scale)}px;
            padding: {int(10 * dpi_scale)}px;
            border-radius: {int(4 * dpi_scale)}px;
            border: none;
        }}
        QPushButton:hover {{ background-color: {WARNING_COLOR}; }}
        QPushButton:disabled {{ background-color: #555; }}
    """

    # Queue list styling
    QUEUE = f"""
        QListWidget {{
            background-color: {WIDGET_BG};
            color: {TEXT_COLOR};
            font-size: {int(14 * dpi_scale)}px;
            border: 1px solid #444;
        }}
        QListWidget::item:selected {{
            background-color: {PRIMARY_ACCENT};
            color: white;
        }}
    """

    # Console (log) styling
    LOG = f"""
        background-color: {LOG_BG};
        color: {TEXT_COLOR};
        font-family: Consolas, 'Courier New', monospace;
        font-size: {int(13 * dpi_scale)}px;
        border: 1px solid #444;
    """

    # Dialog and form styling
    DIALOG = f"""
        QDialog {{
            background-color: {DIALOG_BG};
            color: {TEXT_COLOR};
        }}
        QGroupBox {{
            font-weight: bold;
            border: 1px solid #444;
            border-radius: 5px;
            margin-top: 1ex;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top center;
            padding: 0 3px;
        }}
        QCheckBox::indicator, QRadioButton::indicator {{
            width: {int(18 * dpi_scale)}px;
            height: {int(18 * dpi_scale)}px;
        }}
        QCheckBox::indicator:checked {{
            background-color: {PRIMARY_ACCENT};
            border: 1px solid {PRIMARY_ACCENT};
        }}
        QCheckBox::indicator:unchecked {{
            background-color: #3a3f4b;
            border: 1px solid #6a6f7a;
        }}
        QCheckBox::indicator:disabled {{
            background-color: #555;
        }}
        QRadioButton::indicator:checked {{
            background-color: {PRIMARY_ACCENT};
            border: 1px solid {PRIMARY_ACCENT};
            border-radius: {int(9 * dpi_scale)}px;
        }}
        QRadioButton::indicator:unchecked {{
            background-color: #333;
            border: 1px solid #666;
            border-radius: {int(9 * dpi_scale)}px;
        }}
        QLineEdit, QComboBox, QSpinBox {{
            background-color: #3a3f4b;
            color: {TEXT_COLOR};
            border: 1px solid #444;
            padding: {int(5 * dpi_scale)}px;
            font-size: {int(13 * dpi_scale)}px;
        }}
    """
