# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Manual-only opening through the global shortcut on a disposable desktop."""
import os
from pathlib import Path
import subprocess
import sys

import pytest
from PyQt6.QtTest import QTest

from universal_input.storage import Store, atomic_json
from test_desktop import wait_for

pytestmark = pytest.mark.skipif(os.environ.get("UNIVERSAL_INPUT_TEST_DESKTOP") != "1", reason="requires isolated test desktop")


def test_manual_only_configuration_still_opens_with_global_shortcut(app, tmp_path):
    from Xlib import X
    from Xlib.ext import xtest
    from universal_input.accessibility import FocusMonitor
    from universal_input.app import Controller
    from universal_input.x11 import Desktop

    store = Store(tmp_path / "config")
    store.config["automatic_popup"] = False
    atomic_json(store.config_path, store.config)
    desktop = Desktop()
    controller = Controller(app, desktop, FocusMonitor(), Store(store.directory))
    process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("target_app.py")), str(tmp_path)])
    try:
        wait_for(app, lambda: controller.last_source is not None)
        QTest.qWait(200)
        assert not controller.window.isVisible()
        for kind, key in [(X.KeyPress, "Control_L"), (X.KeyPress, "space"),
                          (X.KeyRelease, "space"), (X.KeyRelease, "Control_L")]:
            xtest.fake_input(desktop.display, kind, desktop.keycode(key))
        desktop.display.sync()
        wait_for(app, lambda: controller.window.isVisible())
        assert controller.window.edit.content_text() == "original"
        controller.cancel()
        atomic_json(tmp_path / "command.json", {"field": "rich"})
        wait_for(app, lambda: not (tmp_path / "command.json").exists())
        QTest.qWait(200)
        assert not controller.window.isVisible()
    finally:
        controller.tray.hide()
        controller.close()
        process.terminate()
        process.wait(timeout=5)
