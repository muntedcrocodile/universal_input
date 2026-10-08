# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Debounced local completion and a paint-only inline preview."""
import json
import os
from pathlib import Path

from PyQt6.QtCore import QObject, QEvent, QProcess, QTimer, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetricsF, QPalette, QTextCursor, QTextLayout, QTextCharFormat


def data_directory():
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "universal-input"


DEFAULT_COMPLETION = {
    "enabled": True,
    "debounce_ms": 100,
    "context_tokens": 128,
    "max_tokens": 12,
    "threads": 2,
    "python_path": "",
    "model_path": "",
}


class LocalCompletion(QObject):
    result = pyqtSignal(int, str)
    unavailable = pyqtSignal(str)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.read_output)
        # Drain native library diagnostics without retaining prompts or filling pipes.
        self.process.readyReadStandardError.connect(self.process.readAllStandardError)
        self.process.errorOccurred.connect(self.failed)
        self.process.finished.connect(self.failed)
        self.ready = False
        self.busy = False
        self.pending = None
        self.buffer = b""
        self.stopped = False
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self.failed)

    def start(self):
        if self.stopped:
            return
        directory = data_directory()
        python = Path(self.config["python_path"]).expanduser() if self.config["python_path"] else directory / "completion-venv/bin/python"
        model = Path(self.config["model_path"]).expanduser() if self.config["model_path"] else directory / "models/SmolLM2-135M-Q4_K_M.gguf"
        if not python.is_file() or not model.is_file():
            self.failed()
            return
        worker = str(Path(__file__).with_name("completion_worker.py"))
        self.process.start(str(python), [worker, str(model), str(self.config["context_tokens"]),
                                       str(self.config["max_tokens"]), str(self.config["threads"])])
        self.timeout.start(30000)

    def request(self, generation, prefix):
        if self.stopped:
            return
        # At most one running inference plus the latest request, never a typing backlog.
        self.pending = {"id": generation, "prefix": prefix}
        self.dispatch()

    def cancel(self):
        self.pending = None

    def dispatch(self):
        if self.ready and not self.busy and self.pending is not None:
            self.process.write((json.dumps(self.pending) + "\n").encode("utf-8"))
            self.pending = None
            self.busy = True
            self.timeout.start(5000)

    def read_output(self):
        self.buffer += bytes(self.process.readAllStandardOutput())
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            try:
                data = json.loads(line)
                if not isinstance(data, dict):
                    raise ValueError("expected worker message")
                if data.get("ready"):
                    self.ready = True
                elif "error" in data:
                    self.failed()
                    return
                else:
                    self.busy = False
                    self.result.emit(int(data["id"]), str(data["text"]))
                self.timeout.stop()
                self.dispatch()
            except (ValueError, KeyError, TypeError):
                self.failed()
                return

    def failed(self, *_):
        if not self.stopped:
            self.close()
            self.unavailable.emit("Word predictions unavailable. Run scripts/install-completion, then restart the app.")

    def close(self):
        self.stopped = True
        self.timeout.stop()
        self.pending = None
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1000)


class InlineCompletion(QObject):
    def __init__(self, editor, backend, debounce_ms=100):
        super().__init__(editor)
        self.editor, self.backend = editor, backend
        self.generation = 0
        self.suggestion = ""
        self.snapshot = None
        self.preedit = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(debounce_ms)
        self.timer.timeout.connect(self.request)
        editor.textChanged.connect(self.changed)
        editor.cursorPositionChanged.connect(self.changed)
        editor.selectionChanged.connect(self.changed)
        editor.installEventFilter(self)
        editor.viewport().installEventFilter(self)
        backend.result.connect(self.receive)

    def context(self):
        edit = self.editor
        cursor = edit.textCursor()
        if not edit.isVisible() or not edit.hasFocus() or edit.isReadOnly() or cursor.hasSelection() or self.preedit:
            return None
        following = QTextCursor(cursor)
        following.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
        # Never insert into an existing word (including punctuation boundaries).
        if following.selectedText() not in ("", " ", "\u2029", "\u2028"):
            return None
        preceding = QTextCursor(cursor)
        # Bound the IPC payload too. Token truncation happens in the worker.
        preceding.setPosition(max(0, cursor.position() - 4096), QTextCursor.MoveMode.KeepAnchor)
        prefix = preceding.selectedText().replace("\u2029", "\n").replace("\u2028", "\n")
        if prefix and 0xD800 <= ord(prefix[0]) <= 0xDFFF:
            prefix = prefix[1:]  # The bounded UTF-16 window may split an emoji.
        return prefix if prefix.strip() else None

    def clear(self):
        self.generation += 1
        self.timer.stop()
        self.backend.cancel()
        self.suggestion = ""
        self.snapshot = None
        self.editor.viewport().update()

    def changed(self):
        self.clear()
        if self.context() is not None:
            self.timer.start()

    def request(self):
        prefix = self.context()
        if prefix is not None:
            self.snapshot = (self.editor.document().revision(), self.editor.textCursor().position(), prefix)
            self.backend.request(self.generation, prefix)

    def current(self):
        return self.snapshot == (self.editor.document().revision(), self.editor.textCursor().position(), self.context())

    def receive(self, generation, text):
        if generation != self.generation or not self.current() or not text.strip():
            return
        if any(ord(char) < 32 for char in text):
            return
        # Keep suggestions to the visible line; reserve room for existing text.
        font, suffix, line, _ = self.line_details()
        metrics = QFontMetricsF(font)
        width = self.editor.viewport().width() - self.editor.cursorRect().right() - 12 - metrics.horizontalAdvance(suffix)
        if line.isValid():
            width = min(width, line.x() + line.width() - line.cursorToX(self.editor.textCursor().positionInBlock())[0]
                        - metrics.horizontalAdvance(suffix) - 2)
        while text and metrics.horizontalAdvance(text) > width:
            # Drop complete words; never accept characters the user cannot see.
            text = text.rstrip().rsplit(" ", 1)[0] if " " in text.strip() else ""
        self.suggestion = text.rstrip()
        self.editor.viewport().update()

    def accept(self):
        if not self.suggestion or not self.current():
            return False
        text = self.suggestion
        self.clear()
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        cursor.insertText(text)
        cursor.endEditBlock()
        self.editor.setTextCursor(cursor)
        self.editor.ensureCursorVisible()
        return True

    def line_details(self):
        cursor = self.editor.textCursor()
        block = cursor.block()
        line = block.layout().lineForTextPosition(cursor.positionInBlock())
        end = block.position() + line.textStart() + line.textLength() if line.isValid() else block.position() + block.length() - 1
        tail = QTextCursor(cursor)
        tail.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        font = cursor.charFormat().font().resolve(self.editor.font())
        return font, tail.selectedText(), line, block

    def paint(self, painter):
        if not self.suggestion or not self.current():
            return
        edit = self.editor
        font, suffix, original_line, block = self.line_details()
        cursor = edit.textCursor()
        start = cursor.positionInBlock()
        length = len(self.suggestion.encode("utf-16-le")) // 2
        layout = QTextLayout(self.suggestion + suffix, font)
        formats = []
        # Preserve rich text and syntax colours in the shifted existing suffix.
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            item = QTextLayout.FormatRange()
            item.start = fragment.position() - block.position()
            item.length = fragment.length()
            item.format = fragment.charFormat()
            formats.append(item)
            iterator += 1
        formats.extend(block.layout().formats())
        shifted = []
        for item in formats:
            end = item.start + item.length
            if end > start:
                copy = QTextLayout.FormatRange()
                copy.start = max(item.start, start) - start + length
                copy.length = end - max(item.start, start)
                copy.format = item.format
                shifted.append(copy)
        ghost = QTextLayout.FormatRange()
        ghost.start, ghost.length = 0, length
        ghost.format = QTextCharFormat(cursor.charFormat())
        ghost.format.setForeground(QColor("#858585"))
        ghost.format.setFontUnderline(False)
        shifted.append(ghost)
        layout.setFormats(shifted)
        layout.beginLayout()
        line = layout.createLine()
        line.setLineWidth(100000)
        layout.endLayout()
        rect = edit.cursorRect()
        ascent = original_line.ascent() if original_line.isValid() else line.ascent()
        origin = QPointF(rect.x(), rect.y() + ascent - line.ascent())
        painter.save()
        painter.setClipRect(edit.viewport().rect())
        if suffix:
            painter.fillRect(QRectF(rect.x() + 1, rect.y(), line.naturalTextWidth() + 1, rect.height()), QColor("#1e1e1e"))
        painter.setPen(edit.palette().color(QPalette.ColorRole.Text))
        layout.draw(painter, origin)
        painter.restore()

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind in (QEvent.Type.FocusOut, QEvent.Type.Hide, QEvent.Type.MouseButtonPress, QEvent.Type.Resize):
            self.clear()
        elif kind in (QEvent.Type.FocusIn, QEvent.Type.Show):
            self.changed()
        elif kind == QEvent.Type.InputMethod:
            self.preedit = bool(event.preeditString())
            self.changed()
        return False

    def close(self):
        self.clear()
        self.backend.close()
