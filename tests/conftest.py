# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolate_completion_runtime(monkeypatch, tmp_path):
    # Desktop tests must not load models from the developer's real installation.
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))


@pytest.fixture(autouse=True)
def dispose_editors(app):
    yield
    from PyQt6.QtCore import QCoreApplication, QEvent
    from universal_input.editor import EditorWindow
    for widget in QApplication.topLevelWidgets():
        if isinstance(widget, EditorWindow):
            widget.shutdown()
            widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
