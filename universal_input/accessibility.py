# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
"""AT-SPI focus discovery and exact-field targeting; no simulated select-all."""
from dataclasses import dataclass
from html import escape
import os
import time

import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, GLib
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

MAX_TEXT = 1_000_000


def is_editable(source):
    if source.get_process_id() == os.getpid():
        return False
    if source.get_role() == Atspi.Role.PASSWORD_TEXT:
        return False
    states = source.get_state_set()
    return (states.contains(Atspi.StateType.EDITABLE)
            and not states.contains(Atspi.StateType.READ_ONLY)
            and not states.contains(Atspi.StateType.DEFUNCT)
            and "Text" in source.get_interfaces())


def read_text(source):
    if Atspi.Text.get_character_count(source) > MAX_TEXT:
        raise RuntimeError("This field is too large to edit safely (limit: 1 million characters).")
    return Atspi.Text.get_text(source, 0, -1)


def rich_hint(source):
    attrs = source.get_attributes()
    tag = attrs.get("tag", "").lower()
    if tag in {"input", "textarea"}:
        return False
    return (attrs.get("contenteditable") == "true"
            or (tag in {"div", "p", "section", "body"} and is_editable(source)))


def formatted_html(source, text):
    """Import basic AT-SPI character formatting, without reading the clipboard."""
    parts, offset = [], 0
    while offset < len(text):
        attrs, _, end = Atspi.Text.get_attribute_run(source, offset, True)
        if end <= offset:
            end = len(text)  # Some plain controls report no attribute range.
        end = min(end, len(text))
        chunk = escape(text[offset:end]).replace("\n", "<br>")
        styles = []
        weight = attrs.get("weight", "400").lower()
        if weight in {"bold", "demibold", "semibold", "heavy", "black"} or (weight.isdigit() and int(weight) >= 600):
            styles.append("font-weight:700")
        if attrs.get("style") in {"italic", "oblique"}:
            styles.append("font-style:italic")
        decorations = []
        if attrs.get("underline", "none") not in {"none", "false", "0"}:
            decorations.append("underline")
        if attrs.get("strikethrough") in {"true", "1"}:
            decorations.append("line-through")
        if decorations:
            styles.append("text-decoration:" + " ".join(decorations))
        parts.append(f'<span style="{";".join(styles)}">{chunk}</span>')
        offset = end
    return '<html><body><p style="white-space:pre-wrap">' + ''.join(parts) + '</p></body></html>'


@dataclass
class Target:
    source: object
    original: str
    window: int
    rich: bool
    label: str
    caret: int
    html: str | None = None

    @classmethod
    def capture(cls, source, window):
        if not is_editable(source):
            raise RuntimeError("Select an accessible, editable text field first.")
        original = read_text(source)
        rich = rich_hint(source)
        try:
            html = formatted_html(source, original)
            rich = rich or any(style in html for style in ("font-weight:700", "font-style:italic", "text-decoration:"))
        except GLib.Error:
            html = None
        if not rich:
            html = None
        return cls(source, original, window, rich,
                   source.get_name() or source.get_application().get_name() or "Text field",
                   Atspi.Text.get_caret_offset(source), html)

    def validate(self):
        if not is_editable(self.source):
            raise RuntimeError("The original field is no longer editable. Your draft is still here.")
        if read_text(self.source) != self.original:
            raise RuntimeError("The original field changed. Copy your draft before reopening that field.")

    def focused(self):
        return self.source.get_state_set().contains(Atspi.StateType.FOCUSED)

    def focus(self):
        if not Atspi.Component.grab_focus(self.source):
            raise RuntimeError("The original application refused focus. Your draft is still here.")

    def select_contents(self):
        count = Atspi.Text.get_character_count(self.source)
        if count:
            if Atspi.Text.get_n_selections(self.source):
                ok = Atspi.Text.set_selection(self.source, 0, 0, count)
            else:
                ok = Atspi.Text.add_selection(self.source, 0, count)
            if not ok:
                raise RuntimeError("The application cannot select this field through accessibility.")
            selection = Atspi.Text.get_selection(self.source, 0)
            if selection.start_offset != 0 or selection.end_offset != count:
                raise RuntimeError("The application did not select the complete field. Transfer stopped.")
        elif not Atspi.Text.set_caret_offset(self.source, 0):
            raise RuntimeError("Cannot position the cursor in the original field.")


class FocusMonitor(QObject):
    focused = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        Atspi.init()
        Atspi.set_timeout(500, 1000)
        self.listener = Atspi.EventListener.new(self.on_event)
        if not self.listener.register("object:state-changed:focused"):
            raise RuntimeError("Could not register accessibility focus events.")
        self.context = GLib.MainContext.default()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.pump)
        self.timer.start(20)

    def find_focused(self):
        """Find a field even when the application never delivered a focus event.

        Bound traversal so a large browser accessibility tree cannot block the UI
        indefinitely. Only inspect states and hierarchy, never field contents.
        """
        deadline = time.monotonic() + 0.8
        root = Atspi.get_desktop(0)
        queue = [root]
        visited = 0
        while queue and visited < 500 and time.monotonic() < deadline:
            node = queue.pop(0)
            visited += 1
            try:
                if node != root and node.get_process_id() == os.getpid():
                    continue
                states = node.get_state_set()
                if states.contains(Atspi.StateType.FOCUSED):
                    if is_editable(node) or node.get_role() == Atspi.Role.PASSWORD_TEXT or states.contains(Atspi.StateType.READ_ONLY):
                        return node
                children = (node.get_child_at_index(i) for i in range(min(node.get_child_count(), 100)))
                # Active/focused branches first, so background windows don't use
                # the entire search budget before reaching the current field.
                for child in children:
                    if child is None:
                        continue
                    child_states = child.get_state_set()
                    if child_states.contains(Atspi.StateType.ACTIVE) or child_states.contains(Atspi.StateType.FOCUSED):
                        queue.insert(0, child)
                    else:
                        queue.append(child)
                    if time.monotonic() >= deadline:
                        break
            except GLib.Error:
                continue
        return None

    def pump(self):
        # Bound each tick so a busy application cannot starve the editor UI.
        for _ in range(30):
            if not self.context.pending():
                break
            self.context.iteration(False)

    def on_event(self, event, *_):
        if event.detail1:
            self.focused.emit(event.source)

    def close(self):
        self.timer.stop()
        self.listener.deregister("object:state-changed:focused")
