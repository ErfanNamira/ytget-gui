# File: ytget_gui/tray.py
"""System tray icon and menu.

The tray is a *view* over MainWindow/QueueController, exactly like the bottom
bar: it holds no queue state of its own, it only reflects what `refresh()` is
told and forwards user intent back to the window. That is what keeps the tray
menu, the bottom bar and the Settings menu from drifting apart.

Everything here degrades gracefully: if no tray is available (common on bare
Linux sessions), `TrayController.available` is False and the window keeps
working with no tray-specific behaviour.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, Optional

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ytget_gui import _version

log = logging.getLogger(__name__)

POST_ACTION_CHOICES = (
    ("Keep running", "Keep"),
    ("Shut down", "Shutdown"),
    ("Sleep", "Sleep"),
    ("Restart", "Restart"),
    (f"Close {_version.APP_NAME}", "Close"),
)


class TrayController(QObject):
    """Owns the QSystemTrayIcon and its menu."""

    def __init__(self, window, settings, icon: Optional[QIcon] = None) -> None:
        super().__init__(window)
        self.window = window
        self.settings = settings
        self._icon = icon
        self.tray: Optional[QSystemTrayIcon] = None
        self._post_actions: Dict[str, QAction] = {}

        if not QSystemTrayIcon.isSystemTrayAvailable():
            log.info("No system tray available; tray icon disabled.")
            return
        if icon is None or icon.isNull():
            log.warning("No app icon found; tray icon disabled.")
            return

        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip(_version.APP_NAME)
        self.tray.setContextMenu(self._build_menu())
        self.tray.activated.connect(self._on_activated)
        self.tray.show()

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        return self.tray is not None

    def _add(
        self,
        menu: QMenu,
        text: str,
        handler: Callable[[], None],
        *,
        checkable: bool = False,
    ) -> QAction:
        action = QAction(text, self)
        action.setCheckable(checkable)
        if checkable:
            action.toggled.connect(lambda checked: handler(checked))
        else:
            action.triggered.connect(lambda _checked=False: handler())
        menu.addAction(action)
        return action

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _build_menu(self) -> QMenu:
        menu = QMenu()

        self.header = QAction(f"{_version.APP_NAME} {_version.__version__}", self)
        self.header.setEnabled(False)
        menu.addAction(self.header)

        self.status_action = QAction("Idle", self)
        self.status_action.setEnabled(False)
        menu.addAction(self.status_action)
        menu.addSeparator()

        self.action_show = self._add(menu, "Show YTGet", self.show_window)
        self.action_hide = self._add(menu, "Hide to tray", self.hide_window)
        menu.addSeparator()

        self.action_start = self._add(menu, "\u25b6  Start queue", self.window.controller.start)
        self.action_pause = self._add(menu, "\u23f8  Pause queue", self.window.controller.pause)
        self.action_skip = self._add(menu, "\u23ed  Skip current item", self.window.controller.skip_current)
        self.action_stop = self._add(menu, "\u23f9  Stop queue", self.window.controller.stop_all)
        menu.addSeparator()

        post_menu = menu.addMenu("When the queue finishes")
        group = QActionGroup(self)
        group.setExclusive(True)
        for label, value in POST_ACTION_CHOICES:
            action = QAction(label, self, checkable=True)
            action.triggered.connect(
                lambda _checked=False, v=value: self.window.set_post_queue_action(v)
            )
            group.addAction(action)
            post_menu.addAction(action)
            self._post_actions[value] = action

        self.action_watcher = self._add(
            menu,
            "Clipboard watcher",
            self.window.set_clipboard_watcher,
            checkable=True,
        )
        self.action_watcher.setToolTip("Queue links automatically as you copy them")
        menu.addSeparator()

        self._add(menu, "Paste and queue now", self.window.queue_clipboard_now)
        self._add(menu, "Clear finished items", self.window.clear_completed)
        self._add(menu, "Open download folder", self.window.open_downloads)
        self._add(menu, "Preferences\u2026", self.window.show_preferences)
        menu.addSeparator()
        self._add(menu, "Exit", self.window.quit_application)

        self.menu = menu
        return menu

    # ------------------------------------------------------------------
    # Window visibility
    # ------------------------------------------------------------------

    def show_window(self) -> None:
        window = self.window
        # MainWindow.restore_window() re-applies the pre-hide size and
        # maximised state; showNormal() alone resets to the default size.
        restore = getattr(window, "restore_window", None)
        if callable(restore):
            restore()
            return
        window.showNormal()
        window.raise_()
        window.activateWindow()

    def hide_window(self) -> None:
        hide = getattr(self.window, "hide_to_tray", None)
        if callable(hide):
            hide()
            return
        self.window.hide()
        self.refresh()

    def _on_activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.Trigger,
            QSystemTrayIcon.DoubleClick,
            QSystemTrayIcon.MiddleClick,
        ):
            if self.window.isVisible() and not self.window.isMinimized():
                self.hide_window()
            else:
                self.show_window()

    # ------------------------------------------------------------------
    # Updates
    # ------------------------------------------------------------------

    def notify(self, title: str, message: str, *, warning: bool = False) -> None:
        if self.tray is None or not getattr(self.settings, "TRAY_NOTIFICATIONS", True):
            return
        if not QSystemTrayIcon.supportsMessages():
            return
        icon = (
            QSystemTrayIcon.MessageIcon.Warning
            if warning
            else QSystemTrayIcon.MessageIcon.Information
        )
        try:
            self.tray.showMessage(title, message, icon, 5000)
        except RuntimeError:
            log.debug("Tray notification failed", exc_info=True)

    def refresh(self) -> None:
        """Re-read window/controller state into the menu and tooltip."""
        if self.tray is None:
            return

        controller = self.window.controller
        model = self.window.model
        running = controller.is_running
        visible = self.window.isVisible() and not self.window.isMinimized()

        self.action_show.setVisible(not visible)
        self.action_hide.setVisible(visible)

        self.action_start.setEnabled(controller.can_start)
        self.action_pause.setEnabled(running and not controller.is_paused)
        self.action_skip.setEnabled(running)
        self.action_stop.setEnabled(running)

        wanted = getattr(self.window, "post_queue_action", "Keep")
        for value, action in self._post_actions.items():
            if action.isChecked() != (value == wanted):
                action.setChecked(value == wanted)

        watcher = getattr(self.window, "watcher", None)
        watching = bool(watcher is not None and watcher.is_running)
        if self.action_watcher.isChecked() != watching:
            # blockSignals, or setChecked re-enters set_clipboard_watcher.
            self.action_watcher.blockSignals(True)
            self.action_watcher.setChecked(watching)
            self.action_watcher.blockSignals(False)

        pending = sum(1 for item in model.items if not item.is_terminal)
        current = controller.current_item
        if running and current is not None:
            state = f"{current.progress}% \u00b7 {current.display_title[:40]}"
        elif controller.is_paused and pending:
            state = f"Paused \u00b7 {pending} waiting"
        elif pending:
            state = f"{pending} item(s) waiting"
        else:
            state = "Idle"
        self.status_action.setText(state)

        tooltip = [f"{_version.APP_NAME} {_version.__version__}", state]
        if watching:
            tooltip.append("Clipboard watcher: on")
        self.tray.setToolTip("\n".join(tooltip))

    def shutdown(self) -> None:
        if self.tray is not None:
            self.tray.hide()
            self.tray.setContextMenu(None)
            self.tray = None
