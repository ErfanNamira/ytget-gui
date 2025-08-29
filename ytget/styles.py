# File: ytget/styles.py
from __future__ import annotations

class AppStyles:
    WINDOW_BG = "#1e1e1e"
    WIDGET_BG = "#2e2e2e"
    TEXT_COLOR = "#e0e0e0"
    PRIMARY_ACCENT = "#e91e63"
    SUCCESS_COLOR = "#00e676"
    ERROR_COLOR = "#ff5252"
    WARNING_COLOR = "#ffb74d"
    INFO_COLOR = "#64b5f6"
    LOG_BG = "#121212"
    DIALOG_BG = "#2a2a2a"

    MAIN = f"background-color: {WINDOW_BG}; color: {TEXT_COLOR};"
    BUTTON = """
        QPushButton {{
            background-color: {bg_color};
            color: {text_color};
            font-size: 15px;
            padding: 10px;
            border-radius: 4px;
            border: none;
        }}
        QPushButton:hover {{ background-color: {hover_color}; }}
        QPushButton:disabled {{ background-color: #555; }}
    """
    QUEUE = f"""
        QListWidget {{
            background-color: {WIDGET_BG};
            color: {TEXT_COLOR};
            font-size: 14px;
            border: 1px solid #444;
        }}
        QListWidget::item:selected {{
            background-color: {PRIMARY_ACCENT};
            color: white;
        }}
    """
    LOG = f"""
        background-color: {LOG_BG};
        color: {TEXT_COLOR};
        font-family: Consolas, 'Courier New', monospace;
        font-size: 13px;
        border: 1px solid #444;
    """
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
            width: 18px;
            height: 18px;
        }}
        QCheckBox::indicator:checked {{
            background-color: {PRIMARY_ACCENT};
            border: 1px solid {PRIMARY_ACCENT};
        }}
        QCheckBox::indicator:unchecked {{
            background-color: #333;
            border: 1px solid #666;
        }}
        QCheckBox::indicator:disabled {{
            background-color: #555;
        }}
        QRadioButton::indicator:checked {{
            background-color: {PRIMARY_ACCENT};
            border: 1px solid {PRIMARY_ACCENT};
            border-radius: 9px;
        }}
        QRadioButton::indicator:unchecked {{
            background-color: #333;
            border: 1px solid #666;
            border-radius: 9px;
        }}
        QLineEdit, QComboBox {{
            background-color: #333;
            color: {TEXT_COLOR};
            border: 1px solid #444;
            padding: 5px;
        }}
    """