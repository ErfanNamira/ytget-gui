# File: ytget_gui/theme.py
"""Main-window stylesheet, built from the Palette tokens.

Previously a ~500-line string literal inside main_window.py with every colour
hard-coded, so changing an accent meant a find-and-replace across two files
that had already drifted apart. Generated once and cached.
"""

from __future__ import annotations

from functools import lru_cache

from ytget_gui.styles import Palette as P


@lru_cache(maxsize=1)
def main_window_qss() -> str:
    return f"""
/* ---- Root ---------------------------------------------------------- */
QMainWindow {{
    background: {P.PAGE_GRADIENT};
    color: {P.TEXT};
    font-family: {P.UI_FONTS};
    font-size: 13px;
}}
#CentralWidget, #TopBar, #BottomBar, #QueuePane, #QueueHeader {{
    background: transparent;
}}
#TopBar {{ border-bottom: 1px solid {P.DIVIDER}; }}
#BottomBar {{ border-top: 1px solid {P.DIVIDER}; }}
#QueuePane {{ border-right: 1px solid {P.DIVIDER}; }}
#QueueHeader {{ border-bottom: 1px solid rgba(255, 255, 255, 15); }}

/* ---- Brand --------------------------------------------------------- */
#Brand {{
    font-size: 16px;
    font-weight: 800;
    letter-spacing: 1.5px;
    color: {P.ACCENT};
}}
#BrandDot {{ color: #FF3B6B; font-size: 22px; font-weight: 900; }}
#VersionChip {{
    background: {P.GLASS_BG_HOVER};
    border: 1px solid rgba(255, 255, 255, 40);
    color: rgba(255, 255, 255, 180);
    font-size: 10px;
    border-radius: 6px;
    padding: 2px 8px;
}}
#Separator {{ color: {P.GLASS_BORDER}; }}

/* ---- URL entry ----------------------------------------------------- */
#UrlWrap {{
    background: {P.GLASS_BG};
    border: 1px solid {P.GLASS_BORDER};
    border-radius: 10px;
}}
#UrlWrap:hover {{
    background: {P.GLASS_BG_HOVER};
    border: 1px solid {P.GLASS_BORDER_HOVER};
}}
#UrlWrap QLineEdit {{
    background: transparent;
    border: none;
    color: {P.TEXT};
    font-size: 13px;
    padding: 9px 12px;
    selection-background-color: {P.ACCENT};
    selection-color: {P.WINDOW_BG};
}}
#UrlWrap[invalid="true"] {{
    border: 1px solid rgba(248, 113, 113, 140);
    background: rgba(248, 113, 113, 18);
}}

/* ---- Combo boxes (shared) ------------------------------------------ */
#FormatBox, #SortBox, #FilterBox, #PostActionBox {{
    background: {P.GLASS_BG};
    border: 1px solid {P.GLASS_BORDER};
    border-radius: 8px;
    color: rgba(255, 255, 255, 200);
    padding: 6px 10px;
}}
#FormatBox {{ font-size: 12px; min-width: 150px; }}
#SortBox {{ font-size: 11px; min-width: 78px; }}
#FilterBox {{ font-size: 11px; min-width: 84px; }}
#PostActionBox {{ font-size: 11px; min-width: 96px; }}
#FormatBox:hover, #SortBox:hover, #FilterBox:hover, #PostActionBox:hover {{
    background: {P.GLASS_BG_HOVER};
    border: 1px solid {P.GLASS_BORDER_HOVER};
}}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox::down-arrow {{
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid rgba(255, 255, 255, 150);
    margin-right: 7px;
}}
QComboBox QAbstractItemView {{
    background: {P.POPUP_BG};
    border: 1px solid {P.GLASS_BORDER};
    border-radius: 8px;
    color: {P.TEXT};
    selection-background-color: rgba(0, 229, 255, 80);
    selection-color: #ffffff;
    padding: 4px;
    outline: none;
}}

/* ---- Buttons ------------------------------------------------------- */
QPushButton {{ font-family: {P.UI_FONTS}; font-size: 12px; }}

#BtnAdd, #BtnStart {{
    background: {P.ACCENT_GRADIENT};
    color: {P.WINDOW_BG};
    border: 1px solid rgba(0, 229, 255, 100);
    border-radius: 8px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
#BtnAdd {{ padding: 8px 18px; }}
#BtnStart {{ padding: 9px 22px; font-size: 13px; min-width: 92px; }}
#BtnAdd:hover, #BtnStart:hover {{ background: {P.ACCENT_GRADIENT_HOVER}; }}
#BtnAdd:disabled, #BtnStart:disabled {{
    background: rgba(255, 255, 255, 10);
    color: rgba(255, 255, 255, 70);
    border: 1px solid rgba(255, 255, 255, 20);
}}

#BtnPaste, #BtnTopbar, #BtnPause, #BtnSkip, #ConsoleTool, #BulkBtn, #PathBtn {{
    background: {P.GLASS_BG};
    color: rgba(255, 255, 255, 180);
    border: 1px solid {P.GLASS_BORDER};
    border-radius: 8px;
}}
#BtnPaste {{ padding: 8px 14px; }}
#BtnTopbar {{ padding: 7px 13px; }}
#BtnPause {{ padding: 9px 18px; }}
#BtnSkip {{ padding: 9px 14px; }}
#ConsoleTool, #BulkBtn {{ padding: 4px 10px; font-size: 11px; border-radius: 6px; }}
#PathBtn {{ padding: 5px 10px; font-size: 11px; max-width: 300px; }}
#BtnPaste:hover, #BtnTopbar:hover, #BtnPause:hover:enabled, #BtnSkip:hover:enabled,
#ConsoleTool:hover, #BulkBtn:hover, #PathBtn:hover {{
    color: {P.TEXT};
    background: {P.GLASS_BG_HOVER};
    border: 1px solid {P.GLASS_BORDER_HOVER};
}}
#BtnPause:disabled, #BtnSkip:disabled {{
    color: rgba(255, 255, 255, 50);
    border: 1px solid rgba(255, 255, 255, 15);
}}

#BtnClear {{
    background: transparent;
    color: rgba(255, 255, 255, 110);
    border: none;
    border-radius: 6px;
    font-size: 14px;
}}
#BtnClear:hover {{ color: rgba(255, 255, 255, 210); background: {P.GLASS_BG}; }}

#BtnStop {{
    background: rgba(248, 113, 113, 15);
    color: rgba(248, 113, 113, 130);
    border: 1px solid rgba(248, 113, 113, 30);
    border-radius: 8px;
    padding: 9px 14px;
}}
#BtnStop:enabled {{ color: {P.ERROR}; border: 1px solid rgba(248, 113, 113, 60); }}
#BtnStop:hover:enabled {{
    color: #FECACA;
    background: rgba(248, 113, 113, 32);
    border: 1px solid rgba(248, 113, 113, 90);
}}
#BtnStop:disabled {{
    color: rgba(255, 255, 255, 40);
    background: rgba(255, 255, 255, 10);
    border: 1px solid rgba(255, 255, 255, 15);
}}

/* ---- Splitter ------------------------------------------------------ */
QSplitter::handle {{ background: {P.GLASS_BG}; width: 1px; }}
QSplitter::handle:hover {{ background: rgba(0, 229, 255, 110); }}

/* ---- Queue pane ---------------------------------------------------- */
#PaneLabel, #ConsolePaneLabel {{
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
    color: {P.TEXT_FAINT};
}}
#CountBadge {{
    background: rgba(0, 229, 255, 30);
    color: {P.ACCENT};
    border: 1px solid rgba(0, 229, 255, 60);
    border-radius: 6px;
    font-size: 10px;
    padding: 1px 7px;
}}
#SearchBox {{
    background: {P.GLASS_BG};
    border: 1px solid {P.GLASS_BORDER};
    border-radius: 8px;
    color: rgba(255, 255, 255, 200);
    font-size: 12px;
    padding: 6px 10px;
}}
#SearchBox:focus {{
    border: 1px solid rgba(0, 229, 255, 130);
    background: rgba(0, 229, 255, 12);
    color: {P.TEXT};
}}
#QueueList {{ background: transparent; border: none; }}
#QueueList::item {{
    background: transparent;
    border: none;
    padding: 0px;
    border-radius: 12px;
}}
#QueueList::item:selected {{ background: rgba(0, 229, 255, 22); border-radius: 12px; }}
#EmptyState {{
    color: rgba(255, 255, 255, 90);
    background: transparent;
    font-size: 12px;
}}
#QueuePane[dropActive="true"] {{
    background: rgba(0, 229, 255, 26);
    border-right: 2px solid rgba(0, 229, 255, 130);
}}

/* ---- Bulk bar ------------------------------------------------------ */
#BulkBar {{
    background: rgba(0, 229, 255, 15);
    border-top: 1px solid rgba(0, 229, 255, 40);
}}
#BulkLabel {{ color: {P.ACCENT}; font-size: 11px; }}

/* ---- Console ------------------------------------------------------- */
#ConsolePane {{
    background: rgba(5, 5, 15, 220);
    border-left: 1px solid {P.DIVIDER};
}}
#ConsoleToolbar {{
    background: transparent;
    border-bottom: 1px solid rgba(255, 255, 255, 15);
}}
#Console {{
    background: rgba(5, 5, 15, 200);
    color: rgba(255, 255, 255, 165);
    border: none;
    border-top: 1px solid rgba(255, 255, 255, 15);
    font-family: {P.MONO_FONTS};
    font-size: 12px;
    padding: 14px;
}}

/* ---- Progress ------------------------------------------------------ */
#GlobalProgress {{
    background: {P.GLASS_BG};
    border: none;
    border-radius: 2px;
    max-height: 3px;
}}
#GlobalProgress::chunk {{ background: {P.PROGRESS_GRADIENT}; border-radius: 2px; }}
#AfterLabel {{ color: {P.TEXT_FAINT}; font-size: 11px; }}

/* ---- Scrollbars ---------------------------------------------------- */
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; border: none; }}
QScrollBar::handle:vertical {{
    background: rgba(255, 255, 255, 40);
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: rgba(255, 255, 255, 75); }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 0; border: none; }}
QScrollBar::handle:horizontal {{
    background: rgba(255, 255, 255, 40);
    border-radius: 4px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{ background: rgba(255, 255, 255, 75); }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---- Menus --------------------------------------------------------- */
QMenuBar {{
    background: transparent;
    color: {P.TEXT_MUTED};
    font-size: 12px;
    border-bottom: 1px solid {P.DIVIDER};
    padding: 2px 4px;
}}
QMenuBar::item {{ padding: 4px 10px; border-radius: 6px; }}
QMenuBar::item:selected {{ background: {P.GLASS_BG_HOVER}; color: {P.TEXT}; }}
QMenu {{
    background: {P.POPUP_BG};
    border: 1px solid {P.GLASS_BORDER};
    border-radius: 10px;
    color: rgba(255, 255, 255, 205);
    font-size: 12px;
    padding: 6px;
}}
QMenu::item {{ padding: 6px 24px 6px 14px; border-radius: 6px; }}
QMenu::item:selected {{ background: rgba(0, 229, 255, 40); color: {P.TEXT}; }}
QMenu::separator {{ height: 1px; background: {P.DIVIDER}; margin: 4px 8px; }}

/* ---- Queue card ---------------------------------------------------- */
QFrame#QueueCard {{
    background: rgba(255, 255, 255, 18);
    border: 1px solid {P.GLASS_BORDER};
    border-radius: 12px;
}}
QFrame#QueueCard[elevated="true"] {{
    background: rgba(255, 255, 255, 30);
    border: 1px solid {P.GLASS_BORDER_HOVER};
}}
QFrame#QueueCard[active="true"] {{
    border: 1px solid rgba(0, 229, 255, 110);
    background: rgba(0, 229, 255, 16);
}}
QFrame#QueueCard #DragHandle {{ color: rgba(255, 255, 255, 65); font-size: 14px; }}
QFrame#QueueCard #Thumb {{
    background: rgba(0, 0, 0, 100);
    border: 1px solid {P.DIVIDER};
    border-radius: 8px;
}}
QFrame#QueueCard #CardTitle {{ color: {P.TEXT}; font-size: 13px; font-weight: 600; }}
QFrame#QueueCard #CardMeta {{ color: {P.TEXT_FAINT}; font-size: 11px; }}
QFrame#QueueCard #StatusChip {{
    border-radius: 6px;
    padding: 1px 8px;
    font-size: 10px;
    font-weight: 600;
}}
QFrame#QueueCard #Progress {{
    background: {P.DIVIDER};
    border: none;
    border-radius: 3px;
}}
QFrame#QueueCard #Progress::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {P.ACCENT}, stop:1 {P.ACCENT_ALT});
    border-radius: 3px;
}}
QFrame#QueueCard #Percent {{ color: {P.TEXT_MUTED}; font-size: 10px; }}
QFrame#QueueCard #IconBtn {{
    background: {P.GLASS_BG};
    color: {P.TEXT_FAINT};
    border: 1px solid rgba(255, 255, 255, 25);
    border-radius: 6px;
    font-size: 11px;
}}
QFrame#QueueCard #IconBtn:hover {{ background: {P.GLASS_BG_HOVER}; color: {P.TEXT}; }}

/* ---- Tooltip ------------------------------------------------------- */
QToolTip {{
    background: {P.POPUP_BG};
    color: {P.TEXT};
    border: 1px solid {P.GLASS_BORDER};
    border-radius: 6px;
    padding: 5px 8px;
    font-size: 11px;
}}
"""
