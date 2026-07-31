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
    # ── Glassmorphism palette ──────────────────────────────────────────
    # Deep space gradient base
    WINDOW_BG      = "#0a0e1a"
    WIDGET_BG      = "#15102e"
    TEXT_COLOR     = "#F4F4F8"
    PRIMARY_ACCENT = "#00E5FF"   # electric cyan
    SUCCESS_COLOR  = "#22D3A5"   # mint
    ERROR_COLOR    = "#F87171"   # soft red
    WARNING_COLOR  = "#FBBF24"   # amber
    INFO_COLOR     = "#60A5FA"   # sky blue
    LOG_BG         = "#07080f"   # near-black for console
    DIALOG_BG      = "#0f1020"   # dialog glass base

    # Glass token helpers (rgba strings for QSS)
    GLASS_BG       = "rgba(20, 20, 40, 180)"
    GLASS_BG_HOVER = "rgba(30, 30, 55, 200)"
    GLASS_BORDER   = "rgba(255, 255, 255, 30)"
    GLASS_BORDER_HOVER = "rgba(255, 255, 255, 50)"
    GLASS_INNER    = "rgba(255, 255, 255, 15)"

    # Main window background & text (DPI-independent, safe as a constant)
    MAIN = f"background-color: {WINDOW_BG}; color: {TEXT_COLOR};"

    @classmethod
    def button(cls) -> str:
        s = get_dpi_scale()
        return f"""
            QPushButton {{
                background-color: {cls.GLASS_INNER};
                color: {cls.TEXT_COLOR};
                font-size: {int(13 * s)}px;
                padding: {int(10 * s)}px;
                border-radius: {int(8 * s)}px;
                border: 1px solid {cls.GLASS_BORDER};
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 30);
                border: 1px solid {cls.GLASS_BORDER_HOVER};
            }}
            QPushButton:disabled {{
                background-color: rgba(255, 255, 255, 10);
                color: rgba(255, 255, 255, 80);
            }}
        """

    @classmethod
    def queue(cls) -> str:
        s = get_dpi_scale()
        return f"""
            QListWidget {{
                background-color: transparent;
                color: {cls.TEXT_COLOR};
                font-size: {int(13 * s)}px;
                border: none;
            }}
            QListWidget::item:selected {{
                background-color: rgba(0, 229, 255, 40);
                color: white;
                border-radius: 8px;
            }}
        """

    @classmethod
    def log(cls) -> str:
        s = get_dpi_scale()
        return f"""
            background-color: {cls.LOG_BG};
            color: {cls.TEXT_COLOR};
            font-family: "JetBrains Mono", "Fira Code", Consolas, monospace;
            font-size: {int(12 * s)}px;
            border: 1px solid {cls.GLASS_BORDER};
            border-radius: 8px;
        """

    @classmethod
    def dialog(cls) -> str:
        s = get_dpi_scale()
        return f"""
            QDialog {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0a0e1a, stop:0.3 #15102e,
                    stop:0.6 #1e1b4b, stop:1 #0c1733);
                color: {cls.TEXT_COLOR};
            }}
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {cls.GLASS_BORDER};
                border-radius: 12px;
                margin-top: 1ex;
                background: {cls.GLASS_INNER};
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
                border-radius: 4px;
            }}
            QCheckBox::indicator:unchecked {{
                background-color: rgba(255, 255, 255, 15);
                border: 1px solid {cls.GLASS_BORDER};
                border-radius: 4px;
            }}
            QCheckBox::indicator:disabled {{
                background-color: rgba(255, 255, 255, 10);
            }}
            QRadioButton::indicator:checked {{
                background-color: {cls.PRIMARY_ACCENT};
                border: 1px solid {cls.PRIMARY_ACCENT};
                border-radius: {int(9 * s)}px;
            }}
            QRadioButton::indicator:unchecked {{
                background-color: rgba(255, 255, 255, 15);
                border: 1px solid {cls.GLASS_BORDER};
                border-radius: {int(9 * s)}px;
            }}
            QLineEdit, QComboBox, QSpinBox {{
                background-color: rgba(255, 255, 255, 15);
                color: {cls.TEXT_COLOR};
                border: 1px solid {cls.GLASS_BORDER};
                border-radius: 8px;
                padding: {int(6 * s)}px;
                font-size: {int(13 * s)}px;
            }}
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
                border: 1px solid {cls.PRIMARY_ACCENT};
                background-color: rgba(0, 229, 255, 15);
            }}
        """

    # Backward-compatible class attributes
    BUTTON = ""
    QUEUE = ""
    LOG = ""
    DIALOG = ""


def refresh_styles() -> None:
    """
    Recompute AppStyles.BUTTON / QUEUE / LOG / DIALOG using the *current*
    DPI scale. Call this once, after the QApplication (and its primary
    screen) exist.
    """
    AppStyles.BUTTON = AppStyles.button()
    AppStyles.QUEUE = AppStyles.queue()
    AppStyles.LOG = AppStyles.log()
    AppStyles.DIALOG = AppStyles.dialog()


# Populate with a best-effort value immediately
refresh_styles()
