# File: ytget_gui/styles.py

from __future__ import annotations

from PySide6.QtGui import QGuiApplication, QFont


def get_dpi_scale() -> float:
    """
    Compute a DPI scale factor (96 DPI as the baseline).

    This is intentionally a function rather than a module-level constant:
    this module is imported (via main_window) before QApplication exists,
    so evaluating QGuiApplication.instance() at import time always returns
    None and silently freezes scaling at 1.0. Calling this lazily -- after
    the QApplication and its primary screen are available -- gives the
    real value.
    """
    app = QGuiApplication.instance()
    if app and app.primaryScreen():
        return app.primaryScreen().logicalDotsPerInch() / 96.0
    return 1.0


def get_global_font() -> QFont:
    """Build a font scaled for the current display's DPI."""
    font = QFont("Inter")
    font.setPointSizeF(10 * get_dpi_scale())
    return font


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

    # Main window background & text (DPI-independent, safe as a constant)
    MAIN = f"background-color: {WINDOW_BG}; color: {TEXT_COLOR};"

    # NOTE: BUTTON/QUEUE/LOG/DIALOG below are built lazily via classmethods
    # (instead of being frozen f-strings at class-definition/import time)
    # so they pick up the *real* DPI scale once QApplication actually
    # exists, rather than always baking in dpi_scale == 1.0.

    @classmethod
    def button(cls) -> str:
        s = get_dpi_scale()
        return f"""
            QPushButton {{
                background-color: {cls.PRIMARY_ACCENT};
                color: {cls.TEXT_COLOR};
                font-size: {int(15 * s)}px;
                padding: {int(10 * s)}px;
                border-radius: {int(4 * s)}px;
                border: none;
            }}
            QPushButton:hover {{ background-color: {cls.WARNING_COLOR}; }}
            QPushButton:disabled {{ background-color: #555; }}
        """

    @classmethod
    def queue(cls) -> str:
        s = get_dpi_scale()
        return f"""
            QListWidget {{
                background-color: {cls.WIDGET_BG};
                color: {cls.TEXT_COLOR};
                font-size: {int(14 * s)}px;
                border: 1px solid #444;
            }}
            QListWidget::item:selected {{
                background-color: {cls.PRIMARY_ACCENT};
                color: white;
            }}
        """

    @classmethod
    def log(cls) -> str:
        s = get_dpi_scale()
        return f"""
            background-color: {cls.LOG_BG};
            color: {cls.TEXT_COLOR};
            font-family: Consolas, 'Courier New', monospace;
            font-size: {int(13 * s)}px;
            border: 1px solid #444;
        """

    @classmethod
    def dialog(cls) -> str:
        s = get_dpi_scale()
        return f"""
            QDialog {{
                background-color: {cls.DIALOG_BG};
                color: {cls.TEXT_COLOR};
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
                width: {int(18 * s)}px;
                height: {int(18 * s)}px;
            }}
            QCheckBox::indicator:checked {{
                background-color: {cls.PRIMARY_ACCENT};
                border: 1px solid {cls.PRIMARY_ACCENT};
            }}
            QCheckBox::indicator:unchecked {{
                background-color: #3a3f4b;
                border: 1px solid #6a6f7a;
            }}
            QCheckBox::indicator:disabled {{
                background-color: #555;
            }}
            QRadioButton::indicator:checked {{
                background-color: {cls.PRIMARY_ACCENT};
                border: 1px solid {cls.PRIMARY_ACCENT};
                border-radius: {int(9 * s)}px;
            }}
            QRadioButton::indicator:unchecked {{
                background-color: #333;
                border: 1px solid #666;
                border-radius: {int(9 * s)}px;
            }}
            QLineEdit, QComboBox, QSpinBox {{
                background-color: #3a3f4b;
                color: {cls.TEXT_COLOR};
                border: 1px solid #444;
                padding: {int(5 * s)}px;
                font-size: {int(13 * s)}px;
            }}
        """

    # Backward-compatible class attributes (AppStyles.BUTTON, .QUEUE, ...).
    # Populated by refresh_styles() below. Default to a dpi_scale == 1.0
    # rendering so the class is still usable if refresh_styles() is never
    # called (e.g. in a headless/test context).
    BUTTON = ""
    QUEUE = ""
    LOG = ""
    DIALOG = ""


def refresh_styles() -> None:
    """
    Recompute AppStyles.BUTTON / QUEUE / LOG / DIALOG using the *current*
    DPI scale. Call this once, after the QApplication (and its primary
    screen) exist -- e.g. right after `app.setPalette(...)` in main() --
    so class-level attribute access (AppStyles.BUTTON) keeps working
    everywhere it's already used, but with a correct, non-frozen value.
    """
    AppStyles.BUTTON = AppStyles.button()
    AppStyles.QUEUE = AppStyles.queue()
    AppStyles.LOG = AppStyles.log()
    AppStyles.DIALOG = AppStyles.dialog()


# Populate with a best-effort value immediately (covers the case where a
# QApplication already exists at import time, e.g. in a REPL or test).
refresh_styles()
