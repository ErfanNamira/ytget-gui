# File: ytget/widgets/queue_item.py
from __future__ import annotations

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QToolButton, QStyle
from PySide6.QtCore import Qt

from ytget.styles import AppStyles

MAX_TITLE = 35

class QueueItemWidget(QWidget):
    def __init__(self, title: str, url: str):
        super().__init__()
        self.title = title
        self.url = url
        self.is_active = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)

        display_title = title[:MAX_TITLE] + "..." if len(title) > MAX_TITLE else title
        self.label = QLabel(display_title)
        self.label.setToolTip(f"{title}\n{url}")
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.label, 1)

        style = self.style()
        self.btn_up = QToolButton(toolTip="Move Up", icon=style.standardIcon(QStyle.SP_ArrowUp))
        self.btn_down = QToolButton(toolTip="Move Down", icon=style.standardIcon(QStyle.SP_ArrowDown))
        self.btn_delete = QToolButton(toolTip="Remove", icon=style.standardIcon(QStyle.SP_DialogCloseButton))

        layout.addWidget(self.btn_up)
        layout.addWidget(self.btn_down)
        layout.addWidget(self.btn_delete)

    def set_active(self, active: bool):
        self.is_active = active
        font = self.label.font()
        font.setBold(active)
        self.label.setFont(font)
        color = AppStyles.SUCCESS_COLOR if active else AppStyles.TEXT_COLOR
        self.label.setStyleSheet(f"color: {color};")