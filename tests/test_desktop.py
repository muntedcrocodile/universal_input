"""Run only on an isolated Xvfb + D-Bus session, never the user's desktop."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from universal_input.storage import atomic_json

pytestmark = pytest.mark.skipif(os.environ.get("UNIVERSAL_INPUT_TEST_DESKTOP") != "1", reason="requires isolated test desktop")


def wait_for(app, predicate, timeout=6):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        QTest.qWait(30)
    raise AssertionError("Condition did not become true before timeout")


def test_desktop_draft_commit_cancel_and_rich_transfer(app, tmp_path):
    from universal_input.accessibility import FocusMonitor
    from universal_input.app import Controller
    from universal_input.x11 import Desktop

    monitor = FocusMonitor()
    desktop = Desktop()
    from universal_input.storage import Store
    store = Store(tmp_path / "config")
    controller = Controller(app, desktop, monitor, store)
    process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("target_app.py")), str(tmp_path)])

    def state():
        path = tmp_path / "state.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def focus(field, **kwargs):
        atomic_json(tmp_path / "command.json", {"field": field, **kwargs})

    try:
        wait_for(app, lambda: controller.window.isVisible())
        assert controller.window.edit.content_text() == "original"
        controller.window.edit.setPlainText("draft **bold** 🦎\nsecond line")
        QTest.qWait(150)
        assert state()["plain"] == "original"  # Nothing leaks while drafting.
        QTest.keyClick(controller.window.edit, Qt.Key.Key_Escape, Qt.KeyboardModifier.ControlModifier)
        QTest.qWait(60)
        assert not controller.window.isVisible()
        assert state()["plain"] == "original"
        assert Store(store.directory).entries.entries[0].text == "draft **bold** 🦎\nsecond line"
        controller.last_source = None  # Simulate a missing focus event.
        # The global shortcut can reopen the same field after Escape.
        from Xlib import X
        from Xlib.ext import xtest
        for kind, key in [(X.KeyPress, "Control_L"), (X.KeyPress, "space"), (X.KeyRelease, "space"), (X.KeyRelease, "Control_L")]:
            xtest.fake_input(desktop.display, kind, desktop.keycode(key))
        desktop.display.sync()
        wait_for(app, lambda: controller.window.isVisible())
        assert controller.window.draft_markdown() == "draft **bold** 🦎\nsecond line"
        assert "Resumed" in controller.window.status.text()
        controller.cancel()
        QTest.qWait(150)

        # Password and read-only fields must not invoke the editor.
        focus("password")
        QTest.qWait(200)
        assert not controller.window.isVisible()
        focus("readonly")
        QTest.qWait(200)
        assert not controller.window.isVisible()

        focus("plain")
        wait_for(app, lambda: controller.window.isVisible())
        QTest.keyClick(controller.window.edit, Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier)
        QTest.qWait(60)
        assert controller.window.mode.currentText() == "Rendered"
        QTest.keyClick(controller.window.edit, Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
        QTest.qWait(60)
        assert controller.window.mode.currentText() == "Raw"
        controller.window.remember_entry("older")
        controller.window.remember_entry("newest")
        app.clipboard().setText("clip one")
        app.clipboard().setText("clip two")
        QTest.keyClick(controller.window.edit, Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        QTest.qWait(60)
        assert controller.window.active_history == 1
        controller.window.edit.clear()
        QTest.keyClick(controller.window.edit, Qt.Key.Key_2, Qt.KeyboardModifier.AltModifier)
        QTest.qWait(60)
        assert controller.window.edit.content_text() == "clip one"
        QTest.keyClick(controller.window.edit, Qt.Key.Key_Left, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        QTest.qWait(60)
        assert controller.window.active_history == 0
        QTest.keyClick(controller.window.edit, Qt.Key.Key_1, Qt.KeyboardModifier.AltModifier)
        QTest.qWait(60)
        assert controller.window.edit.content_text() == "clip onenewest"
        controller.window.edit.setPlainText("replacement **bold** 🦎")
        app.clipboard().setText("previous clipboard")
        QTest.keyClick(controller.window.edit, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
        wait_for(app, lambda: not controller.busy and not controller.window.isVisible())
        wait_for(app, lambda: state()["plain"] == "replacement **bold** 🦎")
        assert state()["submitted"] == 0
        assert app.clipboard().text() == "previous clipboard"
        QTest.qWait(200)
        assert not controller.window.isVisible()  # No popup loop after insertion.

        focus("rich")
        wait_for(app, lambda: controller.window.isVisible())
        assert controller.window.edit.content_text() == "rich original"
        controller.window.mode.setCurrentIndex(1)
        controller.window.edit.setPlainText("formatted replacement")
        controller.window.edit.selectAll()
        controller.window.edit.toggle_format("bold")
        controller.commit()
        wait_for(app, lambda: not controller.busy and not controller.window.isVisible())
        wait_for(app, lambda: state()["rich"] == "formatted replacement")
        assert "font-weight:700" in state()["html"]

        # A Markdown draft negotiates HTML automatically with a rich target.
        focus("plain")
        wait_for(app, lambda: controller.window.isVisible())
        controller.cancel()
        focus("rich")
        wait_for(app, lambda: controller.window.isVisible())
        from universal_input.accessibility import Atspi
        assert "**formatted replacement**" in controller.window.draft_markdown(), Atspi.Text.get_attribute_run(controller.target.source, 0, True)
        controller.window.mode.setCurrentIndex(0)
        controller.window.edit.setPlainText("**automatic rich**")
        controller.commit()
        wait_for(app, lambda: not controller.busy and not controller.window.isVisible())
        wait_for(app, lambda: state()["rich"] == "automatic rich")
        assert "font-weight:700" in state()["html"]

        # Empty drafts explicitly clear the entire original field.
        focus("plain")
        wait_for(app, lambda: controller.window.isVisible())
        controller.window.edit.clear()
        controller.commit()
        wait_for(app, lambda: not controller.busy and not controller.window.isVisible())
        wait_for(app, lambda: state()["plain"] == "")
        focus("readonly")
        QTest.qWait(150)

        # Escape also cancels a queued transfer without reopening or writing.
        focus("plain")
        wait_for(app, lambda: controller.window.isVisible())
        controller.window.edit.setPlainText("cancel queued insertion")
        controller.commit()
        controller.cancel()
        assert not controller.window.isVisible()
        QTest.qWait(350)
        assert not controller.window.isVisible()
        assert state()["plain"] == ""
        focus("readonly")
        QTest.qWait(150)

        # A changed source must stop transfer, preserving the edited draft.
        focus("plain")
        wait_for(app, lambda: controller.window.isVisible())
        controller.window.edit.setPlainText("do not overwrite")
        focus("plain", text="external change")
        wait_for(app, lambda: state()["plain"] == "external change")
        controller.commit()
        assert controller.window.isVisible()
        assert "changed" in controller.window.status.text()
        assert controller.window.edit.content_text() == "do not overwrite"
        assert state()["plain"] == "external change"
    finally:
        controller.window.hide()
        controller.tray.hide()
        controller.close()
        process.terminate()
        process.wait(timeout=5)


def test_ctrl_space_without_accessibility_copies_and_replaces_whole_field(app, tmp_path):
    from PyQt6.QtCore import QObject, pyqtSignal
    from Xlib import X
    from Xlib.ext import xtest
    from universal_input.app import Controller
    from universal_input.x11 import Desktop

    class UnavailableMonitor(QObject):
        focused = pyqtSignal(object)

        def find_focused(self):
            return None

        def close(self):
            pass

    desktop = Desktop()
    controller = Controller(app, desktop, UnavailableMonitor())
    process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("target_app.py")), str(tmp_path)])

    def state():
        path = tmp_path / "state.json"
        return json.loads(path.read_text()) if path.exists() else {}

    try:
        wait_for(app, lambda: bool(state()))
        command = tmp_path / "command.json"
        atomic_json(command, {"field": "plain", "cursor": 3})
        wait_for(app, lambda: not command.exists())
        QTest.qWait(100)
        app.clipboard().setText("preserve my clipboard")
        for kind, key in [(X.KeyPress, "Control_L"), (X.KeyPress, "space"), (X.KeyRelease, "space"), (X.KeyRelease, "Control_L")]:
            xtest.fake_input(desktop.display, kind, desktop.keycode(key))
        desktop.display.sync()
        wait_for(app, lambda: controller.window.isVisible())
        assert controller.target.manual
        assert controller.window.edit.content_text() == "original"
        assert controller.target.replace_all
        assert app.clipboard().text() == "preserve my clipboard"
        controller.window.edit.setPlainText("ZZ")
        assert state()["plain"] == "original"
        controller.commit()
        wait_for(app, lambda: not controller.busy and not controller.window.isVisible())
        wait_for(app, lambda: state()["plain"] == "ZZ")
        assert state()["submitted"] == 0
        assert app.clipboard().text() == "preserve my clipboard"
        assert controller.window.entry_history.entries[0].text == "ZZ"
        controller.invoke()
        wait_for(app, lambda: controller.window.isVisible())
        assert controller.window.edit.content_text() == "ZZ"
        controller.window.edit.clear()
        controller.commit()
        wait_for(app, lambda: not controller.busy and not controller.window.isVisible())
        wait_for(app, lambda: state()["plain"] == "")
        assert app.clipboard().text() == "preserve my clipboard"

        # A failed Copy must never load the pre-existing clipboard as field text.
        desktop.copy = lambda: None
        controller.invoke()
        wait_for(app, lambda: controller.window.isVisible())
        assert controller.window.edit.content_text() == ""
        assert not controller.target.replace_all
        assert "Could not copy" in controller.window.status.text()
        assert app.clipboard().text() == "preserve my clipboard"
        controller.cancel()
    finally:
        controller.window.hide()
        controller.tray.hide()
        controller.close()
        process.terminate()
        process.wait(timeout=5)


def test_editor_bypasses_window_manager_and_accepts_native_keyboard(app):
    from Xlib import X, XK, display
    from Xlib.ext import xtest
    from universal_input.editor import EditorWindow

    connection = display.Display()
    window = EditorWindow()
    window.cancelled.connect(window.hide)
    try:
        window.open_draft("")
        app.processEvents()
        native = connection.create_resource_object("window", int(window.winId()))
        assert native.get_attributes().override_redirect
        wait_for(app, lambda: connection.get_input_focus().focus.id == native.id)
        for index, name in enumerate(("x", "Escape", "Escape")):
            code = connection.keysym_to_keycode(XK.string_to_keysym(name))
            xtest.fake_input(connection, X.KeyPress, code)
            xtest.fake_input(connection, X.KeyRelease, code)
            connection.sync()
            if name == "x":
                wait_for(app, lambda: window.edit.content_text() == "x")
            elif index == 1:
                wait_for(app, window.escape_timer.isActive)
                assert window.isVisible()
            else:
                wait_for(app, lambda: not window.isVisible())
    finally:
        window.hide()
        connection.close()


def test_signal_shutdown_with_table_picker_open(app, tmp_path):
    script = """
from pathlib import Path
import sys
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
from universal_input.app import main
from universal_input.editor import EditorWindow

def open_picker():
    window = next(w for w in QApplication.topLevelWidgets() if isinstance(w, EditorWindow))
    window.toggle_table_picker()
    Path(sys.argv[1]).write_text('ready')

original = EditorWindow.open_draft
def opened(self, *args, **kwargs):
    original(self, *args, **kwargs)
    QTimer.singleShot(100, open_picker)
EditorWindow.open_draft = opened
raise SystemExit(main(['--demo']))
"""
    ready = tmp_path / "ready"
    process = subprocess.Popen([sys.executable, "-c", script, str(ready)])
    try:
        wait_for(app, ready.exists)
        process.terminate()
        assert process.wait(timeout=3) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)


def test_custom_global_shortcut_and_native_editor_shortcuts(app):
    from Xlib import X
    from Xlib.ext import xtest
    from universal_input.editor import EditorWindow
    from universal_input.x11 import Desktop

    desktop = Desktop(["Ctrl+Shift+F8"])
    window = EditorWindow()
    called = []
    desktop.invoked.connect(lambda: called.append(True))

    def chord(*names):
        for name in names:
            xtest.fake_input(desktop.display, X.KeyPress, desktop.keycode(name))
        for name in reversed(names):
            xtest.fake_input(desktop.display, X.KeyRelease, desktop.keycode(name))
        desktop.display.sync()

    try:
        window.open_draft("A draft")
        wait_for(app, lambda: desktop.focused_window() == int(window.winId()))
        chord("Control_L", "Shift_L", "F8")
        wait_for(app, lambda: bool(called))
        chord("Control_L", "m")
        wait_for(app, lambda: window.edit.rich)
        chord("Control_L", "Shift_L", "equal")
        wait_for(app, lambda: window.font_size == 17)
        chord("Control_L", "Shift_L", "minus")
        wait_for(app, lambda: window.font_size == 16)
    finally:
        window.shutdown()
        desktop.close()


@pytest.mark.parametrize('rendered', [False, True])
def test_native_held_tab_navigates_and_releases(app, rendered):
    from Xlib import X
    from Xlib.ext import xtest
    from universal_input.editor import EditorWindow
    from universal_input.x11 import Desktop
    desktop = Desktop([])
    window = EditorWindow()
    try:
        window.open_draft('')
        window.mode.setCurrentIndex(int(rendered))
        window.quick_actions['code_block']()
        wait_for(app, lambda: desktop.focused_window() == int(window.winId()))
        for kind, name in [(X.KeyPress, 'Tab'), (X.KeyPress, 'Right'), (X.KeyRelease, 'Right'), (X.KeyRelease, 'Tab')]:
            xtest.fake_input(desktop.display, kind, desktop.keycode(name))
        desktop.display.sync()
        wait_for(app, lambda: window.edit.textCursor().selectedText() == 'code' and not window.tab_held)
        for kind in (X.KeyPress, X.KeyRelease):
            xtest.fake_input(desktop.display, kind, desktop.keycode('Right'))
        desktop.display.sync()
        wait_for(app, lambda: not window.edit.textCursor().hasSelection())
        assert '\t' not in window.edit.toPlainText()
    finally:
        window.shutdown()
        desktop.close()
