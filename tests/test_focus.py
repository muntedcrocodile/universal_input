# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Native focus regression tests, restricted to the disposable test desktop."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtTest import QTest

from universal_input.storage import Store, atomic_json
from test_desktop import wait_for

pytestmark = pytest.mark.skipif(os.environ.get("UNIVERSAL_INPUT_TEST_DESKTOP") != "1", reason="requires isolated test desktop")


class UnavailableMonitor(QObject):
    focused = pyqtSignal(object)

    def find_focused(self):
        return None

    def close(self):
        pass


def test_monitor_enables_desktop_accessibility(app):
    from gi.repository import Gio, GLib
    from universal_input.accessibility import FocusMonitor

    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    args = ("org.a11y.Bus", "/org/a11y/bus", "org.freedesktop.DBus.Properties")
    bus.call_sync(*args, "Set",
                  GLib.Variant("(ssv)", ("org.a11y.Status", "IsEnabled", GLib.Variant("b", False))),
                  None, Gio.DBusCallFlags.NONE, 1000, None)
    monitor = FocusMonitor()
    try:
        result = bus.call_sync(*args, "Get", GLib.Variant("(ss)", ("org.a11y.Status", "IsEnabled")),
                               None, Gio.DBusCallFlags.NONE, 1000, None)
        assert result.unpack() == (True,)
    finally:
        monitor.close()


@pytest.mark.parametrize('failure', ['lookup', 'capture'])
def test_copy_fallback_explains_accessibility_failures_without_logging_text(app, tmp_path, monkeypatch, capsys, failure):
    from universal_input.accessibility import FocusMonitor, Target
    from universal_input.app import Controller
    from universal_input.x11 import Desktop

    monitor = FocusMonitor()
    controller = Controller(app, Desktop(), monitor, Store(tmp_path / 'config'))
    controller.paused = True
    process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('target_app.py')), str(tmp_path)])
    try:
        wait_for(app, lambda: controller.last_source is not None)

        def unavailable(*args):
            raise RuntimeError('private field contents must not be logged')

        if failure == 'lookup':
            controller.last_source = None
            monkeypatch.setattr(monitor, 'find_focused', unavailable)
            expected = 'Accessibility lookup failed.'
        else:
            monkeypatch.setattr(Target, 'capture', unavailable)
            expected = 'The app could not provide its field text.'
        controller.invoke()
        wait_for(app, lambda: controller.window.isVisible())
        assert controller.target.manual
        assert controller.window.edit.content_text() == 'original'
        assert expected in controller.window.status.text()
        diagnostic = capsys.readouterr().err
        assert 'RuntimeError' in diagnostic and 'trying Copy' in diagnostic
        assert 'private field contents' not in diagnostic
    finally:
        controller.window.hide()
        controller.tray.hide()
        controller.close()
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.parametrize("manual", [False, True])
def test_focus_loss_saves_draft_without_stealing_focus_or_inserting(app, tmp_path, manual):
    from universal_input.accessibility import FocusMonitor
    from universal_input.app import Controller
    from universal_input.x11 import Desktop

    desktop = Desktop()
    store = Store(tmp_path / "config")
    controller = Controller(app, desktop, UnavailableMonitor() if manual else FocusMonitor(), store)
    process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("target_app.py")), str(tmp_path)])

    def state():
        path = tmp_path / "state.json"
        return json.loads(path.read_text()) if path.exists() else {}

    try:
        wait_for(app, lambda: bool(state()))
        if manual:
            controller.invoke()
        wait_for(app, lambda: controller.window.isVisible())
        window = controller.window
        wait_for(app, lambda: desktop.focused_window() == int(window.winId()))
        window.edit.setPlainText("preserved draft **bold** 🦎")

        # Focus may move to child controls or native popups without closing.
        window.mode.setFocus()
        window.mode.showPopup()
        QTest.qWait(400)
        assert window.isVisible()
        window.mode.hidePopup()
        window.edit.setFocus()
        window.toggle_table_picker()
        QTest.qWait(400)
        assert window.isVisible()
        window.table_picker.hide()
        menu = window.edit.createStandardContextMenu()
        menu.popup(window.edit.mapToGlobal(window.edit.rect().center()))
        QTest.qWait(400)
        assert menu.isVisible() and window.isVisible()
        menu.close()
        menu.deleteLater()
        window.edit.setFocus()

        # Moving to a non-editable field should close, keep the new focus, and
        # leave the original text untouched, including without accessibility.
        command = tmp_path / "command.json"
        atomic_json(command, {"field": "readonly"})
        wait_for(app, lambda: not command.exists())
        # Xvfb has no window manager to honour activateWindow requests.
        desktop.restore_focus(state()["window"])
        wait_for(app, lambda: not window.isVisible())
        assert desktop.focused_window() == state()["window"]
        assert state()["plain"] == "original"
        assert state()["submitted"] == 0
        assert not controller.busy and controller.target is None
        assert Store(store.directory).entries.entries[0].text == "preserved draft **bold** 🦎"
        QTest.qWait(300)
        assert not window.isVisible()

        if not manual:
            atomic_json(command, {"field": "plain"})
            wait_for(app, lambda: window.isVisible())
            assert window.draft_markdown() == "preserved draft **bold** 🦎"
            assert "Resumed" in window.status.text()

        # A vanished destination must not leave an orphaned editor up.
        if manual:
            atomic_json(command, {"field": "plain"})
            wait_for(app, lambda: not command.exists())
            controller.invoke()
            wait_for(app, lambda: window.isVisible())
        window.edit.setPlainText("draft before closing target")
        process.terminate()
        process.wait(timeout=5)
        desktop.root.set_input_focus(0, 0)
        desktop.display.sync()
        wait_for(app, lambda: not window.isVisible())
        assert Store(store.directory).entries.entries[0].text == "draft before closing target"
    finally:
        controller.window.hide()
        controller.tray.hide()
        controller.close()
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


def test_focus_loss_cancels_pending_insertion_and_ignores_transient_loss(app, tmp_path):
    from Xlib import X
    from universal_input.app import Controller
    from universal_input.manual import ManualTarget
    from universal_input.x11 import Desktop

    desktop = Desktop()
    controller = Controller(app, desktop, UnavailableMonitor(), Store(tmp_path))
    external = desktop.root.create_window(0, 0, 100, 100, 0, X.CopyFromParent)
    external.map()
    desktop.display.sync()
    try:
        controller.target = ManualTarget(desktop, external.id)
        controller.window.open_draft("pending insertion")
        native = int(controller.window.winId())
        wait_for(app, lambda: desktop.focused_window() == native)
        external.set_input_focus(X.RevertToParent, X.CurrentTime)
        desktop.display.sync()
        controller.check_editor_focus()
        desktop.restore_focus(native)
        controller.check_editor_focus()
        QTest.qWait(350)
        assert controller.window.isVisible()

        desktop.modifiers_down = lambda: True
        controller.commit()
        assert controller.busy
        external.set_input_focus(X.RevertToParent, X.CurrentTime)
        desktop.display.sync()
        wait_for(app, lambda: not controller.window.isVisible())
        assert not controller.busy
        assert controller.target is None
        QTest.qWait(350)
        assert not controller.window.isVisible()
        assert desktop.focused_window() == external.id
        assert Store(tmp_path).entries.entries[0].text == "pending insertion"
    finally:
        controller.tray.hide()
        external.destroy()
        controller.close()
