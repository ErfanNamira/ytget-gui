# File: ytget_gui/dialogs/advanced.py
from __future__ import annotations

from typing import Optional, List, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from ytget_gui.styles import AppStyles
from ytget_gui.settings import AppSettings


# ----------------------------
# Design utilities
# ----------------------------
def _hex(color: QtGui.QColor) -> str:
    c = color.toRgb()
    return f"#{c.red():02x}{c.green():02x}{c.blue():02x}"


def _is_dark(color: QtGui.QColor) -> bool:
    # Perceptual lightness check (HSL)
    return color.lightnessF() < 0.5


def _contrast_on(bg: QtGui.QColor) -> QtGui.QColor:
    # Simple WCAG-ish contrast heuristic using YIQ
    yiq = (bg.red() * 299 + bg.green() * 587 + bg.blue() * 114) / 1000
    return QtGui.QColor("#0b0b0b") if yiq > 150 else QtGui.QColor("#ffffff")


def _mix(a: QtGui.QColor, b: QtGui.QColor, t: float) -> QtGui.QColor:
    return QtGui.QColor(
        int(a.red() * (1 - t) + b.red() * t),
        int(a.green() * (1 - t) + b.green() * t),
        int(a.blue() * (1 - t) + b.blue() * t),
    )


def _tint(color: QtGui.QColor, factor: float) -> QtGui.QColor:
    # factor > 1 -> lighter, < 1 -> darker
    if factor == 1.0:
        return QtGui.QColor(color)
    white = QtGui.QColor("#ffffff")
    black = QtGui.QColor("#000000")
    return _mix(color, white if factor > 1 else black, abs(factor - 1.0))


# ----------------------------
# Controls
# ----------------------------
class UISwitch(QtWidgets.QCheckBox):
    """
    Minimal, animated switch with high-contrast on dark backgrounds.
    - Smooth thumb animation
    - Keyboard accessible (Space/Enter)
    - Respects focus and disabled states
    """

    offsetChanged = QtCore.Signal(float)

    def __init__(self, text: str = "", parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(text, parent)
        self._offset = 1.0 if self.isChecked() else 0.0
        self._anim = QtCore.QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QtCore.QEasingCurve.InOutCubic)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.toggled.connect(self._on_toggled)

    def sizeHint(self) -> QtCore.QSize:
        fm = self.fontMetrics()
        text_w = fm.horizontalAdvance(self.text()) if self.text() else 0
        padding = 10 if text_w else 0
        return QtCore.QSize(56 + text_w + padding, 32)

    @QtCore.Property(float)
    def offset(self) -> float:
        return self._offset

    @offset.setter
    def offset(self, value: float) -> None:
        nv = max(0.0, min(1.0, float(value)))
        if nv == self._offset:
            return
        self._offset = nv
        self.offsetChanged.emit(self._offset)
        self.update()

    def _on_toggled(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)

        # Metrics
        track_w, track_h = 48.0, 28.0
        margin = 2.0
        thumb_d = track_h - margin * 2
        rect = QtCore.QRectF(0, 0, track_w, track_h)
        rect.moveTopLeft(QtCore.QPointF(0, (self.height() - track_h) / 2.0))

        # Color system (high-contrast on dark)
        palette = self.palette()
        is_dark = _is_dark(palette.window().color())
        accent = palette.color(QtGui.QPalette.Highlight)
        accent_on = _contrast_on(accent)
        mut_mid = palette.color(QtGui.QPalette.Mid)
        mut_midlight = palette.color(QtGui.QPalette.Midlight)
        base_bg = palette.color(QtGui.QPalette.Base)

        off_track = mut_midlight if not is_dark else _mix(mut_midlight, QtGui.QColor("#2a2f3a"), 0.6)
        track_color = accent if (self.isChecked() and self.isEnabled()) else off_track
        thumb_border = _mix(mut_mid, QtGui.QColor("#000000" if is_dark else "#ffffff"), 0.2)
        thumb_fill = base_bg if is_dark else _mix(base_bg, QtGui.QColor("#ffffff"), 0.5)

        # Track
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(track_color)
        p.drawRoundedRect(rect, track_h / 2, track_h / 2)

        # Focus ring
        if self.hasFocus():
            ring = QtGui.QPen(accent)
            ring.setWidthF(2.0)
            p.setPen(ring)
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), (track_h - 2) / 2, (track_h - 2) / 2)

        # Thumb
        x = rect.left() + margin + self._offset * (track_w - 2 * margin - thumb_d)
        y = rect.top() + margin
        thumb_rect = QtCore.QRectF(x, y, thumb_d, thumb_d)

        # Shadow (subtle)
        if self.isEnabled():
            shadow = QtGui.QColor(0, 0, 0, 100 if is_dark else 40)
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(shadow)
            p.drawEllipse(thumb_rect.adjusted(0.5, 1.2, 0.5, 1.2))

        p.setPen(QtGui.QPen(thumb_border, 1.0))
        p.setBrush(thumb_fill)
        p.drawEllipse(thumb_rect)

        # Label
        if self.text():
            p.setPen(palette.color(QtGui.QPalette.Text))
            text_rect = QtCore.QRectF(rect.right() + 8, 0, self.width() - rect.right() - 8, self.height())
            p.drawText(text_rect, QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, self.text())


# ----------------------------
# Dialog
# ----------------------------
class AdvancedOptionsDialog(QtWidgets.QDialog):
    """
    - Keyboard: Esc=Cancel, Ctrl+Enter=Save, Alt+R=Reset
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget], settings: AppSettings):
        super().__init__(parent)
        self.settings = settings

        # Window basics
        self.setWindowTitle("Advanced")
        self.setModal(True)
        self.setMinimumSize(560, 320)
        self._build_ui()
        self._apply_styles()  # after UI is built to target object names

        # Validators and live checks
        self._init_validators()
        self._wire_live_validation()

        # Load settings
        self._load_from_settings()

        # Initial validation
        self._validate_all()

    # ----------------------------
    # UI construction
    # ----------------------------
    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(16)

        # Header
        header = QtWidgets.QWidget(self)
        header.setObjectName("header")
        hbox = QtWidgets.QHBoxLayout(header)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(8)

        title = QtWidgets.QLabel("Advanced options")
        title.setObjectName("dlgTitle")
        title.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)

        subtitle = QtWidgets.QLabel("Clip extraction and playlist controls")
        subtitle.setObjectName("dlgSubtitle")
        subtitle.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)

        title_box = QtWidgets.QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(2)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        hbox.addLayout(title_box, 1)
        root.addWidget(header)

        root.addWidget(self._divider())

        # Content grid (labels left, controls right)
        content = QtWidgets.QWidget(self)
        form = QtWidgets.QGridLayout(content)
        form.setContentsMargins(0, 6, 0, 6)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)

        # Clip section label row
        clip_section = self._section_label("Clip extraction")
        form.addWidget(clip_section, 0, 0, 1, 2)

        # Clip fields
        self.clip_start = self._line_edit(
            placeholder="HH:MM:SS or seconds",
            tooltip="Start time. Examples: 75, 01:15, 1:02:45",
            accessible_name="Clip start time",
        )
        self.clip_end = self._line_edit(
            placeholder="HH:MM:SS or seconds",
            tooltip="End time. Examples: 120, 02:00, 01:10:05",
            accessible_name="Clip end time",
        )

        form.addWidget(self._form_label("Start time"), 1, 0)
        form.addWidget(self.clip_start, 1, 1)
        form.addWidget(self._form_label("End time"), 2, 0)
        form.addWidget(self.clip_end, 2, 1)

        # Playlist section
        playlist_section = self._section_label("Playlist")
        form.addWidget(playlist_section, 3, 0, 1, 2)

        self.playlist_items = self._line_edit(
            placeholder="e.g., 1, 3-5, 10",
            tooltip="Comma-separated indices and ranges (e.g., 1, 3-5, 10).",
            accessible_name="Playlist items to download",
        )

        self.playlist_reverse = UISwitch("Reverse order")
        self.playlist_reverse.setToolTip("Download playlist items in reverse order.")
        self.playlist_reverse.setAccessibleName("Reverse playlist order switch")

        form.addWidget(self._form_label("Items"), 4, 0)
        form.addWidget(self.playlist_items, 4, 1)
        form.addWidget(self._form_label("Order"), 5, 0)
        form.addWidget(self.playlist_reverse, 5, 1, QtCore.Qt.AlignLeft)

        root.addWidget(content)
        root.addWidget(self._divider())

        # Footer buttons
        self.buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
        )
        self.buttons.setObjectName("footerButtons")
        self.reset_btn = self.buttons.addButton("Reset", QtWidgets.QDialogButtonBox.ResetRole)
        self.reset_btn.setShortcut(QtGui.QKeySequence("Alt+R"))

        root.addWidget(self.buttons)

        # Signals
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        self.reset_btn.clicked.connect(self._reset_fields)

        # Tab order (left-to-right, top-to-bottom)
        self.setTabOrder(self.clip_start, self.clip_end)
        self.setTabOrder(self.clip_end, self.playlist_items)
        self.setTabOrder(self.playlist_items, self.playlist_reverse)

    # ----------------------------
    # UI helpers
    # ----------------------------
    def _section_label(self, text: str) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName("sectionLabel")
        return lbl

    def _form_label(self, text: str) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName("formLabel")
        return lbl

    def _line_edit(self, placeholder: str, tooltip: str, accessible_name: str) -> QtWidgets.QLineEdit:
        le = QtWidgets.QLineEdit()
        le.setClearButtonEnabled(True)
        le.setPlaceholderText(placeholder)
        le.setToolTip(tooltip)
        le.setAccessibleName(accessible_name)
        le.setMinimumHeight(36)
        le.setObjectName("input")
        return le

    def _divider(self) -> QtWidgets.QFrame:
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Plain)
        line.setObjectName("divider")
        return line

    # ----------------------------
    # Styling (dark-friendly, high-contrast)
    # ----------------------------
    def _apply_styles(self) -> None:
        base = ""
        try:
            base = getattr(AppStyles, "DIALOG", "") or ""
        except Exception:
            base = ""

        pal = self.palette()
        win = pal.color(QtGui.QPalette.Window)
        base_bg = pal.color(QtGui.QPalette.Base)
        text = pal.color(QtGui.QPalette.Text)
        highlight = pal.color(QtGui.QPalette.Highlight)
        is_dark = _is_dark(win)

        # Compute accessible colors with good contrast on dark and light setups.
        strong_text = QtGui.QColor("#EAEFF7") if is_dark else QtGui.QColor("#0E1320")
        muted_text = QtGui.QColor("#AAB4C0") if is_dark else QtGui.QColor("#5B6470")
        section_text = QtGui.QColor("#C2CAD6") if is_dark else QtGui.QColor("#3A4250")
        border_c = QtGui.QColor("#39414D") if is_dark else QtGui.QColor("#D9DEE5")
        divider_c = QtGui.QColor("#2B313B") if is_dark else QtGui.QColor("#E7EBF0")
        field_bg = _mix(base_bg, QtGui.QColor("#0F131A"), 0.7) if is_dark else QtGui.QColor("#FFFFFF")
        field_bg_hover = _mix(field_bg, QtGui.QColor("#ffffff"), 0.06 if is_dark else 0.02)
        focus_ring = highlight
        focus_text_on_highlight = _contrast_on(highlight)
        error_border = QtGui.QColor("#F97066") if is_dark else QtGui.QColor("#D13438")
        error_bg = QtGui.QColor(255, 92, 92, 28 if is_dark else 18)

        css = f"""
        /* Dialog surface */
        QDialog {{
            background: { _hex(win) };
        }}

        /* Header */
        #dlgTitle {{
            font-size: 18px;
            font-weight: 600;
            color: { _hex(strong_text) };
            margin-bottom: 2px;
        }}
        #dlgSubtitle {{
            font-size: 12px;
            color: { _hex(muted_text) };
        }}

        /* Section labels */
        #sectionLabel {{
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.4px;
            color: { _hex(section_text) };
            padding: 4px 0 2px 0;
        }}

        /* Form labels */
        #formLabel {{
            font-size: 12px;
            color: { _hex(muted_text) };
            padding-top: 4px;
        }}

        /* Inputs */
        QLineEdit#input {{
            background: { _hex(field_bg) };
            color: { _hex(strong_text) };
            border: 1px solid { _hex(border_c) };
            border-radius: 10px;
            padding: 8px 12px;
            selection-background-color: { _hex(highlight) };
            selection-color: { _hex(focus_text_on_highlight) };
            font-size: 13px;
        }}
        QLineEdit#input:hover {{
            background: { _hex(field_bg_hover) };
            border-color: { _hex(_mix(border_c, highlight, 0.25)) };
        }}
        QLineEdit#input:focus {{
            border-color: { _hex(highlight) };
            outline: none;
        }}
        QLineEdit#input[state="error"] {{
            border-color: { _hex(error_border) };
            background: { _hex(error_bg) };
        }}
        QLineEdit#input:disabled {{
            color: { _hex(_mix(muted_text, strong_text, 0.3)) };
            background: { _hex(_mix(field_bg, win, 0.2)) };
        }}

        /* Divider */
        #divider {{
            background: { _hex(divider_c) };
            min-height: 1px;
        }}

        /* Buttons */
        QDialogButtonBox QPushButton {{
            border-radius: 10px;
            padding: 8px 14px;
            font-weight: 600;
        }}
        QDialogButtonBox QPushButton:default {{
            background: { _hex(highlight) };
            color: { _hex(focus_text_on_highlight) };
        }}
        QDialogButtonBox QPushButton:!default {{
            background: transparent;
            color: { _hex(strong_text) };
            border: 1px solid { _hex(border_c) };
        }}
        QDialogButtonBox QPushButton:hover {{
            border-color: { _hex(_mix(border_c, highlight, 0.35)) };
        }}
        QDialogButtonBox QPushButton:pressed {{
            padding-top: 9px;
            padding-bottom: 7px;
        }}
        QDialogButtonBox QPushButton:disabled {{
            color: { _hex(_mix(muted_text, strong_text, 0.2)) };
            background: { _hex(_mix(win, field_bg, 0.2)) };
            border-color: { _hex(_mix(border_c, win, 0.2)) };
        }}
        """
        self.setStyleSheet((base + "\n" + css).strip())

    # ----------------------------
    # Validation
    # ----------------------------
    def _init_validators(self) -> None:
        # Time: seconds or [H:]MM:SS with MM/SS in 00-59
        # Allow hours with 1–3 digits, minutes/seconds 00–59; also allow M:SS
        time_pattern = r"^(?:\d+|(?:\d{1,3}:)?[0-5]?\d:[0-5]\d)$"
        self._time_rx = QtCore.QRegularExpression(time_pattern)
        self._time_validator = QtGui.QRegularExpressionValidator(self._time_rx, self)

        # Playlist items: "1, 3-5, 10"
        pl_pattern = r"^\s*\d+\s*(?:-\s*\d+\s*)?(?:\s*,\s*\d+\s*(?:-\s*\d+\s*)?)*\s*$"
        self._pl_rx = QtCore.QRegularExpression(pl_pattern)
        self._pl_validator = QtGui.QRegularExpressionValidator(self._pl_rx, self)

        self.clip_start.setValidator(self._time_validator)
        self.clip_end.setValidator(self._time_validator)
        self.playlist_items.setValidator(self._pl_validator)

        # Base tooltips (used when valid)
        self._base_tips = {
            self.clip_start: "Start time. Examples: 75, 01:15, 1:02:45",
            self.clip_end: "End time. Examples: 120, 02:00, 01:10:05",
            self.playlist_items: "Comma-separated indices and ranges (e.g., 1, 3-5, 10).",
        }

    def _wire_live_validation(self) -> None:
        self.clip_start.textChanged.connect(self._validate_all)
        self.clip_end.textChanged.connect(self._validate_all)
        self.playlist_items.textChanged.connect(self._validate_all)

    def _set_error_state(self, widget: QtWidgets.QWidget, has_error: bool, tip: Optional[str] = None) -> None:
        widget.setProperty("state", "error" if has_error else "")
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        if has_error and tip:
            widget.setToolTip(tip)
        elif widget in self._base_tips:
            widget.setToolTip(self._base_tips[widget])

    def _validate_all(self) -> None:
        start_txt = self.clip_start.text().strip()
        end_txt = self.clip_end.text().strip()
        pl_txt = self.playlist_items.text().strip()

        start_ok = (start_txt == "") or self._time_rx.match(start_txt).hasMatch()
        end_ok = (end_txt == "") or self._time_rx.match(end_txt).hasMatch()
        pl_ok_syntax = (pl_txt == "") or self._pl_rx.match(pl_txt).hasMatch()
        pl_ok_semantic = pl_ok_syntax and self._playlist_semantics_ok(pl_txt)

        # Reset tooltips to base first
        for w in (self.clip_start, self.clip_end, self.playlist_items):
            if w in self._base_tips:
                w.setToolTip(self._base_tips[w])

        # Ordering check only if both provided and syntactically valid
        ordering_ok = True
        ordering_msg = ""
        if start_ok and end_ok and start_txt and end_txt:
            s = self._to_seconds(start_txt)
            e = self._to_seconds(end_txt)
            if s is None or e is None or e <= s:
                ordering_ok = False
                ordering_msg = "End must be greater than start."

        # Apply error states with tooltips
        self._set_error_state(
            self.clip_start,
            has_error=not start_ok and start_txt != "",
            tip="Invalid format. Use seconds or [H:]MM:SS (e.g., 75, 01:15, 1:02:45).",
        )

        end_tip = "Invalid format. Use seconds or [H:]MM:SS."
        if ordering_msg and end_txt:
            end_tip = ordering_msg
        self._set_error_state(
            self.clip_end,
            has_error=(not end_ok and end_txt != "") or (bool(ordering_msg) and end_txt != ""),
            tip=end_tip,
        )

        self._set_error_state(
            self.playlist_items,
            has_error=not pl_ok_semantic and pl_txt != "",
            tip="Invalid list. Use positive numbers and non-decreasing ranges separated by commas (e.g., 1, 3-5, 10).",
        )

        all_valid = start_ok and end_ok and ordering_ok and pl_ok_semantic
        self._set_save_enabled(all_valid)

        # Button tooltip reflects current state
        save_btn = self.buttons.button(QtWidgets.QDialogButtonBox.Save)
        if save_btn:
            save_btn.setToolTip("Save changes" if all_valid else "Fix the highlighted fields to enable Save.")

    def _playlist_semantics_ok(self, text: str) -> bool:
        txt = text.strip()
        if not txt:
            return True
        # Validate positive integers; for ranges, start <= end
        try:
            parts = [p.strip() for p in txt.split(",")]
            for p in parts:
                if "-" in p:
                    a, b = [x.strip() for x in p.split("-", 1)]
                    if not a.isdigit() or not b.isdigit():
                        return False
                    start, end = int(a), int(b)
                    if start <= 0 or end <= 0 or end < start:
                        return False
                else:
                    if not p.isdigit() or int(p) <= 0:
                        return False
            return True
        except Exception:
            return False

    def _set_save_enabled(self, enabled: bool) -> None:
        btn = self.buttons.button(QtWidgets.QDialogButtonBox.Save)
        if btn:
            btn.setEnabled(enabled)
            if enabled:
                btn.setDefault(True)

    def _to_seconds(self, value: str) -> Optional[int]:
        v = value.strip()
        if not v:
            return None
        if v.isdigit():
            try:
                return int(v)
            except ValueError:
                return None
        parts = v.split(":")
        try:
            if len(parts) == 2:
                mm, ss = parts
                m, s = int(mm), int(ss)
                if not (m >= 0 and 0 <= s <= 59):
                    return None
                return m * 60 + s
            if len(parts) == 3:
                hh, mm, ss = parts
                h, m, s = int(hh), int(mm), int(ss)
                if not (h >= 0 and 0 <= m <= 59 and 0 <= s <= 59):
                    return None
                return h * 3600 + m * 60 + s
        except ValueError:
            return None
        return None

    # ----------------------------
    # Data I/O
    # ----------------------------
    def get_options(self) -> dict:
        return {
            "CLIP_START": self.clip_start.text().strip(),
            "CLIP_END": self.clip_end.text().strip(),
            "PLAYLIST_ITEMS": self.playlist_items.text().strip(),
            "PLAYLIST_REVERSE": self.playlist_reverse.isChecked(),
        }

    def _load_from_settings(self) -> None:
        self.clip_start.setText(self._safe_str(getattr(self.settings, "CLIP_START", "")))
        self.clip_end.setText(self._safe_str(getattr(self.settings, "CLIP_END", "")))
        self.playlist_items.setText(self._safe_str(getattr(self.settings, "PLAYLIST_ITEMS", "")))
        self.playlist_reverse.setChecked(bool(getattr(self.settings, "PLAYLIST_REVERSE", False)))

    def _reset_fields(self) -> None:
        self.clip_start.clear()
        self.clip_end.clear()
        self.playlist_items.clear()
        self.playlist_reverse.setChecked(False)
        self._validate_all()

    @staticmethod
    def _safe_str(v) -> str:
        return "" if v is None else str(v)

    # ----------------------------
    # Accept flow & keyboard
    # ----------------------------
    def _on_accept(self) -> None:
        self._validate_all()
        save_btn = self.buttons.button(QtWidgets.QDialogButtonBox.Save)
        if save_btn and not save_btn.isEnabled():
            invalids = self._invalid_widgets()
            if invalids:
                w = invalids[0]
                w.setFocus(QtCore.Qt.OtherFocusReason)
                global_pos = w.mapToGlobal(w.rect().bottomLeft())
                QtWidgets.QToolTip.showText(global_pos, w.toolTip(), w)
            return
        self.accept()

    def keyPressEvent(self, e: QtGui.QKeyEvent) -> None:
        if ((e.modifiers() & (QtCore.Qt.ControlModifier | QtCore.Qt.MetaModifier))
            and e.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter)):
            self._on_accept()
            return
        super().keyPressEvent(e)
        
    def _invalid_widgets(self) -> List[QtWidgets.QWidget]:
        widgets: List[QtWidgets.QWidget] = []

        def is_error(w: QtWidgets.QWidget) -> bool:
            return (w.property("state") or "") == "error"

        for w in (self.clip_start, self.clip_end, self.playlist_items):
            if is_error(w):
                widgets.append(w)
        return widgets