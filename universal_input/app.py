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


class Controller:
    def __init__(self, app, desktop, monitor, store=None):
        self.app, self.desktop, self.monitor = app, desktop, monitor
        self.store = store
        self.window = EditorWindow(store.entries, store.clipboard) if store else EditorWindow()
        self.window.history_changed.connect(self.save_history)
        self.target = None
        self.drafts = OrderedDict()
        self.generation = 0
        self.last_source = None
        self.suppressed_source = None
        self.busy = False
        self.paused = False
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

    def save_history(self):
        if self.store:
            try:
                self.store.save()
            except OSError:
                self.tray.showMessage("Universal Input", "Could not save history. Check free space and configuration directory permissions.")

    def capture_clipboard(self):
        if self.restoring_clipboard:
            return
        data = self.app.clipboard().mimeData()
        if data and not data.hasFormat("application/x-universal-input-token") and data.hasText():
            self.window.remember_clipboard(data.text(), data.html() if data.hasHtml() else None)

    def make_tray(self):
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor("#171a17"))
        painter = QPainter(pixmap)
        painter.setPen(QColor("#007e00"))
        painter.drawText(pixmap.rect(), 0x84, "U")
        painter.end()
        tray = QSystemTrayIcon(QIcon(pixmap), self.app)
        tray.setToolTip("Universal Input · Ctrl+Alt+Space")
        menu = QMenu()
        menu.setStyleSheet("QMenu { background: #171a17; color: #ecefec; } QMenu::item:selected { background: #007e00; }")
        open_action = menu.addAction("Open editor · Ctrl+Alt+Space")
        open_action.triggered.connect(self.invoke)
        pause = QAction("Pause automatic opening", menu)
        pause.setCheckable(True)
        pause.toggled.connect(lambda value: setattr(self, "paused", value))
        menu.addAction(pause)
        menu.addSeparator()
        menu.addAction("Clear history", self.clear_history)
        menu.addAction("Quit", self.app.quit)
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
                if not self.paused and not self.window.isVisible() and source != self.suppressed_source:
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
        if self.last_source is not None:
            try:
                from .accessibility import Atspi
                if self.last_source.get_state_set().contains(Atspi.StateType.FOCUSED):
                    self.open_source(self.last_source)
                    return
            except Exception:
                pass
        self.tray.showMessage("Universal Input", "Focus an accessible text field first. Password fields are excluded.")

    def open_source(self, source):
        from .accessibility import Target
        target = Target.capture(source, self.desktop.focused_window())
        if target.window <= 1:
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
        self.busy = False
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
                    raise RuntimeError("Shortcut keys are still held. Release them and try Ctrl+Enter again.")
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
            self.expected = self.window.edit.toPlainText()
            if not self.window.draft_markdown():
                from .accessibility import Atspi
                if not Atspi.EditableText.set_text_contents(self.target.source, ""):
                    raise RuntimeError("The application refused to clear this field. Your draft is still here.")
                self.expected_variants = {""}
                self.deadline = time.monotonic() + 2
                self.later(100, self.verify)
                return
            self.target.select_contents()
            clipboard = self.app.clipboard()
            old = clipboard.mimeData()
            self.saved_clipboard = QMimeData()
            if old:
                for fmt in old.formats():
                    self.saved_clipboard.setData(fmt, old.data(fmt))
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
            markdown, html, _ = self.window.payload()
            self.window.remember_entry(markdown, html)
            self.drafts.pop(self.target.source, None)
            self.target = None
            self.busy = False
            self.window.send.setEnabled(True)
            self.window.edit.clear()
            self.restore_clipboard()
        except Exception as exc:
            self.fail(exc)

    def restore_clipboard(self):
        if self.saved_clipboard is not None:
            current = self.app.clipboard().mimeData()
            if current and bytes(current.data("application/x-universal-input-token")) == self.clipboard_token:
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
        window.cancelled.connect(app.quit)
        window.commit_requested.connect(lambda: window.status.setText("Demo only — no target field. Run without --demo for desktop integration."))
        window.open_draft("", label="Demo")
    else:
        from .accessibility import FocusMonitor
        from .x11 import Desktop
        from .storage import Store
        try:
            store = Store()
            desktop = Desktop()
            monitor = FocusMonitor()
            controller = Controller(app, desktop, monitor, store)
            if store.warning:
                controller.tray.showMessage("Universal Input", store.warning)
            app.aboutToQuit.connect(controller.close)
        except Exception as exc:
            print(f"Could not start Universal Input: {exc}", file=sys.stderr)
            return 1
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    timer = QTimer()
    timer.start(250)
    timer.timeout.connect(lambda: None)
    return app.exec()
