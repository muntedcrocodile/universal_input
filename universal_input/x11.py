# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
"""X11 shortcut and a single Ctrl+V; never emits Enter into the target."""
from Xlib import X, XK, display, error
from Xlib.ext import xtest
from PyQt6.QtCore import QObject, QSocketNotifier, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence
from .shortcuts import normalize_bindings


class Desktop(QObject):
    invoked = pyqtSignal()

    def __init__(self, shortcuts=None):
        super().__init__()
        self.display = display.Display()
        if not self.display.has_extension("XTEST"):
            raise RuntimeError("This X server does not support XTEST keyboard input.")
        self.root = self.display.screen().root
        shortcuts = normalize_bindings()["open"] if shortcuts is None else shortcuts
        self.grabs = []
        errors = []
        for shortcut in shortcuts:
            combination = QKeySequence(shortcut)[0]
            key = int(combination.key())
            names = {int(Qt.Key.Key_Space): "space", int(Qt.Key.Key_Return): "Return",
                     int(Qt.Key.Key_Enter): "KP_Enter", int(Qt.Key.Key_Escape): "Escape",
                     int(Qt.Key.Key_Tab): "Tab", int(Qt.Key.Key_Backspace): "BackSpace",
                     int(Qt.Key.Key_Left): "Left", int(Qt.Key.Key_Right): "Right",
                     int(Qt.Key.Key_Up): "Up", int(Qt.Key.Key_Down): "Down"}
            if int(Qt.Key.Key_F1) <= key <= int(Qt.Key.Key_F35):
                symbol = XK.string_to_keysym(f"F{key - int(Qt.Key.Key_F1) + 1}")
            elif key in names:
                symbol = XK.string_to_keysym(names[key])
            elif 32 <= key <= 126:
                symbol = ord(chr(key).lower())
            else:
                raise RuntimeError(f"Unsupported global shortcut key: {shortcut}")
            code = self.display.keysym_to_keycode(symbol)
            if not code:
                raise RuntimeError(f"No keyboard mapping for {shortcut}")
            mask = 0
            for modifier, xmask in ((Qt.KeyboardModifier.ControlModifier, X.ControlMask),
                                    (Qt.KeyboardModifier.AltModifier, X.Mod1Mask),
                                    (Qt.KeyboardModifier.ShiftModifier, X.ShiftMask),
                                    (Qt.KeyboardModifier.MetaModifier, X.Mod4Mask)):
                if combination.keyboardModifiers() & modifier:
                    mask |= xmask
            self.grabs.append((code, mask))
            for locks in (0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask):
                self.root.grab_key(code, mask | locks, False, X.GrabModeAsync, X.GrabModeAsync,
                                   onerror=lambda err, _: errors.append(err))
        self.display.sync()
        if errors:
            self.display.close()
            raise RuntimeError(f"Global shortcut already in use: {', '.join(shortcuts)}")
        self.notifier = QSocketNotifier(self.display.fileno(), QSocketNotifier.Type.Read, self)
        self.notifier.activated.connect(self.events)
        # Xlib round trips can move events into its own queue before the socket
        # notifier sees them. Drain that queue as well.
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.events)
        self.timer.start(30)

    def keycode(self, name):
        return self.display.keysym_to_keycode(XK.string_to_keysym(name))

    def events(self, *_):
        while self.display.pending_events():
            event = self.display.next_event()
            if event.type == X.KeyPress and (event.detail, event.state & ~(X.LockMask | X.Mod2Mask)) in self.grabs:
                self.invoked.emit()

    def focused_window(self):
        focus = self.display.get_input_focus().focus
        return focus.id if hasattr(focus, "id") else 0

    def focus_is_within(self, windows):
        """Whether native keyboard focus belongs to one of these window trees."""
        focus = self.focused_window()
        try:
            # Qt controls can have their own native child windows. Bound the
            # walk in case another application disappears during the query.
            for _ in range(32):
                if focus in windows:
                    return True
                if focus <= 1 or focus == self.root.id:
                    return False
                parent = self.display.create_resource_object("window", focus).query_tree().parent
                focus = parent.id if parent else 0
        except error.XError:
            return False
        return False

    def window_exists(self, window):
        try:
            self.display.create_resource_object("window", window).get_attributes()
            return True
        except error.XError:
            return False

    def restore_focus(self, window):
        errors = []
        self.display.create_resource_object("window", window).set_input_focus(
            X.RevertToParent, X.CurrentTime, onerror=lambda err, _: errors.append(err))
        self.display.sync()
        if errors:
            raise RuntimeError("The original window is no longer available.")

    def modifiers_down(self):
        keys = self.display.query_keymap()
        for name in ("Control_L", "Control_R", "Shift_L", "Shift_R", "Alt_L", "Alt_R", "Super_L", "Super_R", "Return", "KP_Enter", "Tab"):
            code = self.keycode(name)
            if code and keys[code // 8] & (1 << (code % 8)):
                return True
        return False

    def chord(self, letter):
        ctrl, key = self.keycode("Control_L"), self.keycode(letter)
        for kind, code in [(X.KeyPress, ctrl), (X.KeyPress, key), (X.KeyRelease, key), (X.KeyRelease, ctrl)]:
            xtest.fake_input(self.display, kind, code)
        self.display.sync()

    def select_all(self):
        self.chord("a")

    def copy(self):
        self.chord("c")

    def paste(self):
        self.chord("v")

    def delete_selection(self):
        key = self.keycode("BackSpace")
        xtest.fake_input(self.display, X.KeyPress, key)
        xtest.fake_input(self.display, X.KeyRelease, key)
        self.display.sync()

    def close(self):
        self.timer.stop()
        self.notifier.setEnabled(False)
        for code, mask in self.grabs:
            for locks in (0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask):
                self.root.ungrab_key(code, mask | locks)
        self.display.close()
