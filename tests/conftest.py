import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


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
