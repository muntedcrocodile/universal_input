"""X11 shortcut and a single Ctrl+V; never emits Enter into the target."""
from Xlib import X, XK, display, error
from Xlib.ext import xtest
from PyQt6.QtCore import QObject, QSocketNotifier, QTimer, pyqtSignal


class Desktop(QObject):
    invoked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.display = display.Display()
        if not self.display.has_extension("XTEST"):
            raise RuntimeError("This X server does not support XTEST keyboard input.")
        self.root = self.display.screen().root
        self.key = self.keycode("space")
        errors = []
        for locks in (0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask):
            self.root.grab_key(self.key, X.ControlMask | locks, False,
                               X.GrabModeAsync, X.GrabModeAsync,
                               onerror=lambda err, _: errors.append(err))
        self.display.sync()
        if errors:
            self.display.close()
            raise RuntimeError("Ctrl+Space is already registered by another application.")
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
            if event.type == X.KeyPress and event.detail == self.key:
                self.invoked.emit()

    def focused_window(self):
        focus = self.display.get_input_focus().focus
        return focus.id if hasattr(focus, "id") else 0

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
        for name in ("Control_L", "Control_R", "Shift_L", "Shift_R", "Alt_L", "Alt_R", "Super_L", "Super_R", "Return", "KP_Enter"):
            code = self.keycode(name)
            if code and keys[code // 8] & (1 << (code % 8)):
                return True
        return False

    def paste(self):
        ctrl, v = self.keycode("Control_L"), self.keycode("v")
        for kind, key in [(X.KeyPress, ctrl), (X.KeyPress, v), (X.KeyRelease, v), (X.KeyRelease, ctrl)]:
            xtest.fake_input(self.display, kind, key)
        self.display.sync()

    def close(self):
        self.timer.stop()
        self.notifier.setEnabled(False)
        self.root.ungrab_key(self.key, X.AnyModifier)
        self.display.close()
