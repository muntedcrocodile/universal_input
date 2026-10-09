# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Desktop controller: focus → isolated draft → explicit, verified transfer."""
from collections import OrderedDict
import argparse
import os
import signal
import sys
import time

from PyQt6.QtCore import QLockFile, QMimeData, QStandardPaths, QTimer
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .editor import EditorWindow
from .shortcuts import normalize_bindings, label


class Controller:
    def __init__(self, app, desktop, monitor, store=None):
        self.app, self.desktop, self.monitor = app, desktop, monitor
        self.store = store
        self.bindings = store.keybindings if store else normalize_bindings()
        self.open_key = label(self.bindings, "open") or "the tray menu"
        self.window = EditorWindow(store.entries, store.clipboard, self.bindings,
                                   store.directory / "personal-dictionary.txt", store.config["spellcheck_language"],
                                   store.config["editor_font_size"], store.config["window_width_percent"],
                                   store.config["window_height_percent"], store.config["indent_width"],
                                   completion_config=store.config["completion"]) if store else EditorWindow()
        self.window.history_changed.connect(self.save_history)
        self.window.font_size_changed.connect(self.save_font_size)
        self.target = None
        self.drafts = OrderedDict()
        self.generation = 0
        self.last_source = None
        self.suppressed_source = None
        self.busy = False
        self.capturing = False
        self.paused = False
        self.automatic_popup = store.config["automatic_popup"] if store else True
        self.saved_clipboard = None
        self.clipboard_token = None
        self.window.commit_requested.connect(self.commit)
        self.window.cancelled.connect(self.cancel)
        desktop.invoked.connect(self.invoke)
        monitor.focused.connect(self.on_focus)
        self.tray = self.make_tray()
        self.restoring_clipboard = False
        app.clipboard().dataChanged.connect(self.capture_clipboard)
        self.capture_clipboard()

    def save_font_size(self, size):
        if self.store:
            try:
                self.store.save_font_size(size)
            except OSError:
                self.window.status.setText("Could not save font size. Check configuration directory permissions and free space.")

    def save_history(self):
        if self.store:
            try:
                self.store.save()
            except OSError:
                self.tray.showMessage("Universal Input", "Could not save history. Check free space and configuration directory permissions.")

    def capture_clipboard(self):
        if self.restoring_clipboard or self.capturing:
            return
        data = self.app.clipboard().mimeData()
        if data and not data.hasFormat("application/x-universal-input-token") and data.hasText():
            self.window.remember_clipboard(data.text(), data.html() if data.hasHtml() else None)

    def make_tray(self):
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor("#1e1e1e"))
        painter = QPainter(pixmap)
        painter.setPen(QColor("#007e00"))
        painter.drawText(pixmap.rect(), 0x84, "U")
        painter.end()
        tray = QSystemTrayIcon(QIcon(pixmap), self.app)
        tray.setToolTip(f"Universal Input · {self.open_key}")
        menu = QMenu()
        menu.setStyleSheet("QMenu { background: #1e1e1e; color: #d4d4d4; } QMenu::item:selected { background: #007e00; }")
        open_action = menu.addAction(f"Open editor · {self.open_key}")
        open_action.triggered.connect(self.invoke)
        pause = QAction("Pause automatic opening", menu)
        pause.setCheckable(True)
        pause.setEnabled(self.automatic_popup)
        if not self.automatic_popup:
            pause.setText("Automatic opening disabled in config")
        pause.toggled.connect(lambda value: setattr(self, "paused", value))
        menu.addAction(pause)
        menu.addSeparator()
        menu.addAction("Clear history", self.clear_history)
        menu.addAction("Quit", lambda: self.app.exit(0))
        tray.setContextMenu(menu)
        tray.activated.connect(lambda reason: self.invoke() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        tray.show()
        self.menu = menu
        return tray

    def clear_history(self):
        self.window.entry_history.entries.clear()
        self.window.clipboard_history.entries.clear()
        self.drafts.clear()
        self.window.refresh_histories()
        self.save_history()

    def on_focus(self, source):
        from .accessibility import is_editable, Atspi
        try:
            if source.get_process_id() == os.getpid():
                return
            if self.busy or not source.get_state_set().contains(Atspi.StateType.FOCUSED):
                return
            if source != self.suppressed_source:
                self.suppressed_source = None
            if is_editable(source):
                self.last_source = source
                if self.automatic_popup and not self.paused and not self.window.isVisible() and source != self.suppressed_source:
                    self.open_source(source)
            else:
                self.last_source = None
        except Exception as exc:
            # Never log field contents or application-supplied exceptions.
            print(f"Focus detection skipped ({type(exc).__name__}).", file=sys.stderr)

    def invoke(self):
        if self.busy:
            return
        if self.window.isVisible():
            self.window.raise_()
            self.window.activateWindow()
            return
        from .accessibility import Atspi, is_editable
        window = self.desktop.focused_window()
        if window <= 1:
            self.tray.showMessage("Universal Input", f"Click where you want to type, then use {self.open_key}.")
            return
        source = None
        self.fallback_reason = "The app did not expose an editable field."
        if self.last_source is not None:
            try:
                if self.last_source.get_state_set().contains(Atspi.StateType.FOCUSED):
                    source = self.last_source
            except Exception:
                pass
        if source is None:
            try:
                source = self.monitor.find_focused()
            except Exception:
                pass
        if source is not None:
            try:
                if source.get_role() == Atspi.Role.PASSWORD_TEXT or source.get_state_set().contains(Atspi.StateType.READ_ONLY):
                    self.tray.showMessage("Universal Input", "This field is password-protected or read-only.")
                    return
                if is_editable(source):
                    self.open_source(source)
                    return
            except Exception:
                pass
        # The manual shortcut works even without accessible field discovery.
        # Bind to the captured window only; do not pretend we identified a field.
        self.open_manual(window)

    def open_manual(self, window, source=None):
        from .manual import ManualTarget
        if self.desktop.focused_window() != window:
            self.tray.showMessage("Universal Input", f"Focus changed. Click your field and use {self.open_key} again.")
            return
        self.target = ManualTarget(self.desktop, window, source=source)
        self.busy = self.capturing = True
        self.generation += 1
        self.deadline = time.monotonic() + 3
        self.capture_manual_text()

    def snapshot_clipboard(self):
        old = self.app.clipboard().mimeData()
        self.saved_clipboard = QMimeData()
        if old:
            for fmt in old.formats():
                self.saved_clipboard.setData(fmt, old.data(fmt))

    def capture_manual_text(self):
        try:
            self.target.validate()
            if not self.target.focused():
                raise RuntimeError("Focus changed before copying.")
            if self.desktop.modifiers_down():
                if time.monotonic() >= self.deadline:
                    raise RuntimeError("Shortcut keys are still held.")
                self.later(30, self.capture_manual_text)
                return
            self.snapshot_clipboard()
            probe = QMimeData()
            self.clipboard_token = os.urandom(16)
            probe.setData("application/x-universal-input-token", self.clipboard_token)
            self.app.clipboard().setMimeData(probe)
            self.desktop.select_all()
            self.desktop.copy()
            self.deadline = time.monotonic() + 1
            self.later(50, self.read_manual_copy)
        except Exception:
            self.finish_manual_capture(None)

    def read_manual_copy(self):
        try:
            if not self.target.focused():
                raise RuntimeError("Focus changed before copying completed.")
            data = self.app.clipboard().mimeData()
            if data and data.hasText() and not data.hasFormat("application/x-universal-input-token"):
                text = data.text()
                html = data.html() if data.hasHtml() else None
                self.finish_manual_capture(text, html)
            elif time.monotonic() < self.deadline:
                self.later(50, self.read_manual_copy)
            else:
                self.finish_manual_capture(None)
        except Exception:
            self.finish_manual_capture(None)

    def finish_manual_capture(self, text, html=None):
        self.restore_clipboard(force=text is not None)
        self.busy = self.capturing = False
        self.target.original = text or ""
        self.target.replace_all = text is not None
        self.window.open_draft(text or "", rich=bool(html), html=html, label="current field")
        self.window.status.setText(
            f"Editing copied field. {self.fallback_reason} {label(self.bindings, 'insert') or 'Insert'} replaces its contents." if text is not None else
            f"Could not copy this field. {label(self.bindings, 'insert') or 'Insert'} pastes at its current selection."
        )

    def open_source(self, source):
        from .accessibility import Atspi, CopyRequiredError, Target
        window = self.desktop.focused_window()
        if window <= 1:
            return
        try:
            target = Target.capture(source, window)
        except CopyRequiredError:
            if not source.get_state_set().contains(Atspi.StateType.FOCUSED):
                raise RuntimeError("Focus changed before copying the field.")
            self.fallback_reason = "The app exposes its text as nested content."
            self.open_manual(window, source)
            return
        self.target = target
        cached = self.drafts.get(source)
        if cached and cached["original"] == target.original:
            self.window.mode.setCurrentIndex(cached["mode"])
            self.window.open_draft(cached["markdown"], label=target.label)
            cursor = self.window.edit.textCursor()
            cursor.setPosition(min(cached["cursor"], self.window.edit.document().characterCount() - 1))
            self.window.edit.setTextCursor(cursor)
            self.window.status.setText(f"Resumed draft for {target.label}")
        else:
            self.drafts.pop(source, None)
            self.window.open_draft(target.original, target.rich, target.html, target.label, target.caret)

    def save_current_draft(self):
        if self.target is None:
            return
        markdown, html, _ = self.window.payload()
        self.window.remember_entry(markdown, html)
        if getattr(self.target, "manual", False):
            return
        source = self.target.source
        self.drafts.pop(source, None)
        self.drafts[source] = {
            "original": self.target.original, "markdown": markdown,
            "mode": self.window.mode.currentIndex(),
            "cursor": self.window.edit.textCursor().position(),
        }
        while len(self.drafts) > 50:
            self.drafts.popitem(last=False)

    def cancel(self):
        self.window.hide()
        self.generation += 1  # Invalidate every scheduled step of an unfinished transfer.
        self.busy = self.capturing = False
        self.window.send.setEnabled(True)
        self.save_current_draft()
        self.restore_clipboard()
        target, self.target = self.target, None
        if target:
            self.suppressed_source = target.source
            try:
                self.desktop.restore_focus(target.window)
                target.focus()
            except Exception:
                pass
        self.window.edit.clear()

    def later(self, milliseconds, callback):
        generation = self.generation
        QTimer.singleShot(milliseconds, lambda: callback() if self.busy and self.generation == generation else None)

    def commit(self):
        if self.busy or self.target is None:
            return
        try:
            self.target.validate()
            self.generation += 1
            self.busy = True
            self.window.send.setEnabled(False)
            self.window.status.setText("Release the shortcut keys to insert…")
            self.deadline = time.monotonic() + 3
            self.wait_for_release()
        except Exception as exc:
            self.fail(exc)

    def wait_for_release(self):
        try:
            if self.desktop.modifiers_down():
                if time.monotonic() >= self.deadline:
                    raise RuntimeError("Shortcut keys are still held. Release them and try inserting again.")
                self.later(30, self.wait_for_release)
                return
            self.target.validate()
            self.window.hide()
            self.suppressed_source = self.target.source
            self.desktop.restore_focus(self.target.window)
            self.target.focus()
            self.later(150, self.transfer)
        except Exception as exc:
            self.fail(exc)

    def transfer(self):
        try:
            self.target.validate()
            if not self.target.focused() or self.desktop.focused_window() != self.target.window:
                raise RuntimeError("Focus changed before insertion. Your draft is still here.")
            if self.desktop.modifiers_down():
                raise RuntimeError("A shortcut key is held. Release it and try again.")
            self.expected = self.window.edit.content_text()
            if not self.window.draft_markdown():
                if getattr(self.target, "manual", False):
                    if self.target.replace_all:
                        self.target.select_contents()
                        self.desktop.delete_selection()
                    self.complete_transfer()
                    return
                from .accessibility import Atspi
                if not Atspi.EditableText.set_text_contents(self.target.source, ""):
                    raise RuntimeError("The application refused to clear this field. Your draft is still here.")
                self.expected_variants = {""}
                self.deadline = time.monotonic() + 2
                self.later(100, self.verify)
                return
            self.target.select_contents()
            clipboard = self.app.clipboard()
            self.snapshot_clipboard()
            data = QMimeData()
            markdown, html, rendered = self.window.payload()
            data.setText(markdown)
            data.setHtml(html)
            self.expected_variants = {markdown.replace("\r\n", "\n"), rendered.replace("\r\n", "\n")}
            self.clipboard_token = os.urandom(16)
            data.setData("application/x-universal-input-token", self.clipboard_token)
            clipboard.setMimeData(data)
            # Check focus again after accessibility calls and clipboard negotiation.
            if not self.target.focused() or self.desktop.focused_window() != self.target.window:
                raise RuntimeError("Focus changed before insertion. Your draft is still here.")
            self.desktop.paste()
            self.deadline = time.monotonic() + 2
            if getattr(self.target, "manual", False):
                # Without readback, allow the target time to request clipboard data.
                self.later(1000, self.complete_transfer)
            else:
                self.later(100, self.verify)
        except Exception as exc:
            self.fail(exc)

    def verify(self):
        from .accessibility import read_text
        try:
            if read_text(self.target.source).replace("\r\n", "\n") not in self.expected_variants:
                if time.monotonic() < self.deadline:
                    self.later(100, self.verify)
                    return
                raise RuntimeError("Could not verify insertion. Check the original field before retrying; your draft is retained.")
            self.complete_transfer()
        except Exception as exc:
            self.fail(exc)

    def complete_transfer(self):
        markdown, html, _ = self.window.payload()
        self.window.remember_entry(markdown, html)
        self.drafts.pop(self.target.source, None)
        self.target = None
        self.busy = False
        self.window.send.setEnabled(True)
        self.window.edit.clear()
        self.restore_clipboard()

    def restore_clipboard(self, force=False):
        if self.saved_clipboard is not None:
            current = self.app.clipboard().mimeData()
            if force or (current and bytes(current.data("application/x-universal-input-token")) == self.clipboard_token):
                self.restoring_clipboard = True
                try:
                    self.app.clipboard().setMimeData(self.saved_clipboard)
                finally:
                    self.restoring_clipboard = False
            self.saved_clipboard = None
            self.clipboard_token = None

    def fail(self, exc):
        self.restore_clipboard()
        self.busy = False
        self.window.send.setEnabled(True)
        # Only our own errors contain user-facing text; remote errors may include content.
        message = str(exc) if isinstance(exc, RuntimeError) else f"Transfer stopped ({type(exc).__name__}). Your draft is still here."
        self.window.status.setText(message)
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        self.window.edit.setFocus()

    def close(self):
        self.generation += 1
        self.busy = False
        self.save_current_draft()
        self.app.clipboard().dataChanged.disconnect(self.capture_clipboard)
        self.restore_clipboard()
        self.monitor.close()
        self.desktop.close()
        self.window.shutdown()


def main(argv=None):
    parser = argparse.ArgumentParser(description="A floating draft editor for accessible Linux/X11 text fields.")
    parser.add_argument("--demo", action="store_true", help="Open the editor without monitoring other applications")
    args = parser.parse_args(argv)
    if not args.demo and (os.environ.get("XDG_SESSION_TYPE") == "wayland" or not os.environ.get("DISPLAY")):
        parser.error("Desktop integration currently requires an X11 session. Use --demo to try the editor.")
    app = QApplication([sys.argv[0]])
    app.setApplicationName("Universal Input")
    app.setQuitOnLastWindowClosed(False)
    lock = QLockFile(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.RuntimeLocation) + "/universal-input.lock")
    if not args.demo and not lock.tryLock(0):
        print("Universal Input is already running.", file=sys.stderr)
        return 1
    if args.demo:
        window = EditorWindow()
        window.cancelled.connect(lambda: app.exit(0))
        window.commit_requested.connect(lambda: window.status.setText("Demo only — no target field. Run without --demo for desktop integration."))
        window.open_draft("", label="Demo")
        app.aboutToQuit.connect(window.shutdown)
    else:
        from .accessibility import FocusMonitor
        from .x11 import Desktop
        from .storage import Store
        try:
            store = Store()
            desktop = Desktop(store.keybindings["open"])
            monitor = FocusMonitor()
            controller = Controller(app, desktop, monitor, store)
            if store.warning:
                controller.tray.showMessage("Universal Input", store.warning)
            app.aboutToQuit.connect(controller.close)
        except Exception as exc:
            print(f"Could not start Universal Input: {exc}", file=sys.stderr)
            return 1
    signal.signal(signal.SIGINT, lambda *_: app.exit(0))
    signal.signal(signal.SIGTERM, lambda *_: app.exit(0))
    timer = QTimer()
    timer.start(250)
    timer.timeout.connect(lambda: None)
    return app.exec()
