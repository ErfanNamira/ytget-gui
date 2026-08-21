# File: ytget_gui/styles.py
"""Design tokens and DPI-aware QSS builders."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtGui import QFont, QGuiApplication


class Palette:
    """Glassmorphism tokens: deep-indigo base, electric-cyan accent."""

    WINDOW_BG = "#0a0e1a"
    WIDGET_BG = "#15102e"
    DIALOG_BG = "#0f1020"
    LOG_BG = "#07080f"

    TEXT = "#F4F4F8"
    TEXT_MUTED = "rgba(255, 255, 255, 150)"
    TEXT_FAINT = "rgba(255, 255, 255, 120)"

    ACCENT = "#00E5FF"
    ACCENT_ALT = "#7C4DFF"
    ACCENT_HOVER = "#33EEFF"
    SUCCESS = "#22D3A5"
    ERROR = "#F87171"
    WARNING = "#FBBF24"
    INFO = "#60A5FA"

    GLASS_BG = "rgba(255, 255, 255, 15)"
    GLASS_BG_HOVER = "rgba(255, 255, 255, 25)"
    GLASS_BORDER = "rgba(255, 255, 255, 30)"
    GLASS_BORDER_HOVER = "rgba(255, 255, 255, 50)"
    DIVIDER = "rgba(255, 255, 255, 20)"
    POPUP_BG = "rgba(20, 20, 40, 240)"

    PAGE_GRADIENT = (
        "qlineargradient(x1:0, y1:0, x2:1, y2:1, "
        "stop:0 #0a0e1a, stop:0.3 #15102e, stop:0.6 #1e1b4b, stop:1 #0c1733)"
    )
    ACCENT_GRADIENT = (
        "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00E5FF, stop:1 #00B8FF)"
    )
    ACCENT_GRADIENT_HOVER = (
        "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #33EEFF, stop:1 #33CCFF)"
    )
    PROGRESS_GRADIENT = (
        "qlineargradient(x1:0, y1:0, x2:1, y2:0, "
        "stop:0 #00E5FF, stop:0.5 #7C4DFF, stop:1 #00B8FF)"
    )

    UI_FONTS = '"Inter", "SF Pro Display", "Segoe UI", sans-serif'
    MONO_FONTS = '"JetBrains Mono", "Fira Code", Consolas, monospace'


def dpi_scale() -> float:
    """Scale factor relative to 96 DPI.

    Deliberately a function, not a module constant: this module is imported
    before QApplication exists, so evaluating it at import time always
    yielded None -> 1.0 and froze scaling permanently on HiDPI displays.
    """
    app = QGuiApplication.instance()
    if app is not None:
        screen = app.primaryScreen()
        if screen is not None:
            return screen.logicalDotsPerInch() / 96.0
    return 1.0


def px(value: float) -> int:
    return max(1, int(round(value * dpi_scale())))


def global_font() -> QFont:
    font = QFont("Inter")
    font.setPointSizeF(10 * dpi_scale())
    return font


class AppStyles:
    """Compatibility facade.

    Existing workers import AppStyles.INFO_COLOR / ERROR_COLOR / etc. for log
    colours, so those names are preserved as aliases onto Palette.
    """

    # Log colours (used by every worker's `log` signal)
    TEXT_COLOR = Palette.TEXT
    INFO_COLOR = Palette.INFO
    SUCCESS_COLOR = Palette.SUCCESS
    ERROR_COLOR = Palette.ERROR
    WARNING_COLOR = Palette.WARNING
    PRIMARY_ACCENT = Palette.ACCENT

    WINDOW_BG = Palette.WINDOW_BG
    WIDGET_BG = Palette.WIDGET_BG
    LOG_BG = Palette.LOG_BG
    DIALOG_BG = Palette.DIALOG_BG
    GLASS_BG = Palette.GLASS_BG
    GLASS_BG_HOVER = Palette.GLASS_BG_HOVER
    GLASS_BORDER = Palette.GLASS_BORDER
    GLASS_BORDER_HOVER = Palette.GLASS_BORDER_HOVER
    GLASS_INNER = Palette.GLASS_BG

    MAIN = f"background-color: {Palette.WINDOW_BG}; color: {Palette.TEXT};"

    # Populated by refresh_styles(); kept as class attributes because the
    # dialogs read AppStyles.DIALOG directly.
    BUTTON: str = ""
    QUEUE: str = ""
    LOG: str = ""
    DIALOG: str = ""

    @staticmethod
    def button() -> str:
        return _button_qss(dpi_scale())

    @staticmethod
    def queue() -> str:
        return _queue_qss(dpi_scale())

    @staticmethod
    def log() -> str:
        return _log_qss(dpi_scale())

    @staticmethod
    def dialog() -> str:
        return _dialog_qss(dpi_scale())


# QSS strings are cached per DPI scale: they are pure functions of the scale
# and were previously rebuilt (string-formatted) on every dialog open.


@lru_cache(maxsize=8)
def _button_qss(scale: float) -> str:
    s = scale
    return f"""
QPushButton {{
    background-color: {Palette.GLASS_BG};
    color: {Palette.TEXT};
    font-size: {int(13 * s)}px;
    padding: {int(10 * s)}px;
    border-radius: {int(8 * s)}px;
    border: 1px solid {Palette.GLASS_BORDER};
}}
QPushButton:hover {{
    background-color: {Palette.GLASS_BG_HOVER};
    border: 1px solid {Palette.GLASS_BORDER_HOVER};
}}
QPushButton:disabled {{
    background-color: rgba(255, 255, 255, 10);
    color: rgba(255, 255, 255, 80);
}}
"""


@lru_cache(maxsize=8)
def _queue_qss(scale: float) -> str:
    s = scale
    return f"""
QListWidget {{
    background-color: transparent;
    color: {Palette.TEXT};
    font-size: {int(13 * s)}px;
    border: none;
}}
QListWidget::item:selected {{
    background-color: rgba(0, 229, 255, 40);
    color: #ffffff;
    border-radius: {int(8 * s)}px;
}}
"""


@lru_cache(maxsize=8)
def _log_qss(scale: float) -> str:
    s = scale
    return f"""
background-color: {Palette.LOG_BG};
color: {Palette.TEXT};
font-family: {Palette.MONO_FONTS};
font-size: {int(12 * s)}px;
border: 1px solid {Palette.GLASS_BORDER};
border-radius: {int(8 * s)}px;
"""


@lru_cache(maxsize=8)
def _dialog_qss(scale: float) -> str:
    s = scale
    return f"""
QDialog {{
    background: {Palette.PAGE_GRADIENT};
    color: {Palette.TEXT};
    font-family: {Palette.UI_FONTS};
}}
QGroupBox {{
    font-weight: bold;
    border: 1px solid {Palette.GLASS_BORDER};
    border-radius: {int(12 * s)}px;
    margin-top: 1ex;
    background: {Palette.GLASS_BG};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top center;
    padding: 0 {int(6 * s)}px;
    color: {Palette.ACCENT};
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: {int(18 * s)}px;
    height: {int(18 * s)}px;
}}
QCheckBox::indicator:checked {{
    background-color: {Palette.ACCENT};
    border: 1px solid {Palette.ACCENT};
    border-radius: {int(4 * s)}px;
}}
QCheckBox::indicator:unchecked {{
    background-color: {Palette.GLASS_BG};
    border: 1px solid {Palette.GLASS_BORDER};
    border-radius: {int(4 * s)}px;
}}
QCheckBox::indicator:disabled {{
    background-color: rgba(255, 255, 255, 10);
}}
QRadioButton::indicator:checked {{
    background-color: {Palette.ACCENT};
    border: 1px solid {Palette.ACCENT};
    border-radius: {int(9 * s)}px;
}}
QRadioButton::indicator:unchecked {{
    background-color: {Palette.GLASS_BG};
    border: 1px solid {Palette.GLASS_BORDER};
    border-radius: {int(9 * s)}px;
}}
QLineEdit, QComboBox, QSpinBox {{
    background-color: {Palette.GLASS_BG};
    color: {Palette.TEXT};
    border: 1px solid {Palette.GLASS_BORDER};
    border-radius: {int(8 * s)}px;
    padding: {int(6 * s)}px;
    font-size: {int(13 * s)}px;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border: 1px solid {Palette.ACCENT};
    background-color: rgba(0, 229, 255, 15);
}}
"""


def refresh_styles() -> None:
    """Recompute the cached QSS strings using the *current* DPI scale.

    Call once after QApplication and its primary screen exist.
    """
    AppStyles.BUTTON = AppStyles.button()
    AppStyles.QUEUE = AppStyles.queue()
    AppStyles.LOG = AppStyles.log()
    AppStyles.DIALOG = AppStyles.dialog()


# Best-effort values at import time (scale 1.0); corrected by refresh_styles().
refresh_styles()
