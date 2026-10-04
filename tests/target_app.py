"""A separate, disposable desktop application for the integration test."""
import json
from pathlib import Path
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QLineEdit, QTextEdit, QVBoxLayout, QWidget

app = QApplication([])
window = QWidget()
window.setWindowTitle("Universal Input test target")
layout = QVBoxLayout(window)
plain = QLineEdit("original")
plain.setAccessibleName("Test plain field")
rich = QTextEdit()
rich.setPlainText("rich original")
rich.setAccessibleName("Test rich field")
password = QLineEdit()
password.setEchoMode(QLineEdit.EchoMode.Password)
readonly = QLineEdit("Read only")
readonly.setReadOnly(True)
for widget in (plain, rich, password, readonly):
    layout.addWidget(widget)
window.resize(500, 400)
window.show()
window.activateWindow()
plain.setFocus()
folder = Path(sys.argv[1])
submitted = 0

def submit():
    global submitted
    submitted += 1

plain.returnPressed.connect(submit)

def tick():
    command = folder / "command.json"
    if command.exists():
        data = json.loads(command.read_text())
        command.unlink()
        window.raise_()
        window.activateWindow()
        widget = {"plain": plain, "rich": rich, "password": password, "readonly": readonly}[data["field"]]
        if "text" in data:
            widget.setText(data["text"])
        widget.setFocus()
        if "cursor" in data:
            widget.setCursorPosition(data["cursor"])
    data = {"window": int(window.winId()), "plain": plain.text(), "rich": rich.toPlainText(), "html": rich.toHtml(), "submitted": submitted}
    temp = folder / "state.tmp"
    temp.write_text(json.dumps(data))
    temp.replace(folder / "state.json")

timer = QTimer()
timer.timeout.connect(tick)
timer.start(30)
app.exec()
