# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Configurable insertion recipes and bounded, asynchronous command sources."""
from copy import deepcopy
from importlib.resources import files
from pathlib import Path
import re
import os
import signal
import shutil

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal

MAX_SOURCE_BYTES = 1024 * 1024
DEFAULT_QUICK_INSERT = [
    dict(id="table", label="Table ▾", shortcut="Ctrl+Alt+T", action="table"),
    dict(id="code_block", label="Code", shortcut="Ctrl+Alt+C", text="```text\ncode\n```", select="text", padding=True),
    dict(id="tasks", label="Tasks", shortcut="Ctrl+Alt+L", text="- [ ] First task\n- [ ] Second task", select="First task", padding=True),
    dict(id="quote", label="Quote", shortcut="Ctrl+Alt+Q", text="> Quoted text", select="Quoted text", padding=True),
    dict(id="link", label="Link", shortcut="Ctrl+Alt+K", text="[link text](https://example.com)", select="link text", padding=True),
    dict(id="divider", label="Divider", shortcut="Ctrl+Alt+D", text="---", padding=True),
    dict(id="template", label="Template", text=files("universal_input").joinpath("templates/markdown.md").read_text(encoding="utf-8").rstrip("\n"), select="Markdown template", padding=True),
]


def normalize_quick_insert(value=None):
    items = deepcopy(DEFAULT_QUICK_INSERT if value is None else value)
    if not isinstance(items, list):
        raise ValueError("quick_insert must be a list")
    ids = set()
    common = {"id", "label", "shortcut", "toolbar"}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each quick_insert item must be a mapping")
        name = item.get("id")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", name) or name in ids:
            raise ValueError("quick_insert ids must be unique lowercase identifiers")
        ids.add(name)
        if not isinstance(item.get("label"), str) or not item["label"].strip():
            raise ValueError(f"quick_insert {name}: label must be nonempty text")
        if type(item.setdefault("toolbar", True)) is not bool:
            raise ValueError(f"quick_insert {name}: toolbar must be true or false")
        if "action" in item:
            if item["action"] != "table" or set(item) - common - {"action"}:
                raise ValueError(f"quick_insert {name}: table action accepts only id, label, shortcut, toolbar")
            continue
        allowed = common | {"text", "file", "command", "select", "cursor", "padding", "format", "timeout"}
        if set(item) - allowed:
            raise ValueError(f"quick_insert {name}: unknown fields {sorted(set(item) - allowed)}")
        sources = set(item) & {"text", "file", "command"}
        if len(sources) != 1:
            raise ValueError(f"quick_insert {name}: specify exactly one of text, file, command")
        source = next(iter(sources))
        value = item[source]
        if source == "command":
            if not ((isinstance(value, str) and value.strip() and "\0" not in value) or
                    (isinstance(value, list) and value and all(isinstance(arg, str) and '\0' not in arg for arg in value) and value[0])):
                raise ValueError(f"quick_insert {name}: command must be a shell string or nonempty argument list")
        elif not isinstance(value, str) or (source == "file" and not value):
            raise ValueError(f"quick_insert {name}: {source} must be text")
        if item.setdefault("format", "markdown") not in ("markdown", "plain"):
            raise ValueError(f"quick_insert {name}: format must be markdown or plain")
        if type(item.setdefault("padding", False)) is not bool:
            raise ValueError(f"quick_insert {name}: padding must be true or false")
        cursor = item.get("cursor", "end")
        if not ((type(cursor) is int and cursor >= 0) or (isinstance(cursor, str) and cursor in ("start", "end"))):
            raise ValueError(f"quick_insert {name}: cursor must be start, end, or a nonnegative character offset")
        if "select" in item and (not isinstance(item["select"], str) or not item["select"] or "cursor" in item):
            raise ValueError(f"quick_insert {name}: select must be nonempty text and cannot be combined with cursor")
        timeout = item.setdefault("timeout", 10)
        if type(timeout) not in (int, float) or not 0.1 <= timeout <= 300:
            raise ValueError(f"quick_insert {name}: timeout must be between 0.1 and 300 seconds")
    return items


def read_source(item, directory):
    if "text" in item:
        return item["text"]
    path = Path(item["file"]).expanduser()
    if not path.is_absolute():
        path = Path(directory) / path
    with path.open("rb") as stream:
        data = stream.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        raise ValueError("File exceeds the 1 MiB insertion limit")
    return data.decode("utf-8")


class CommandSource(QObject):
    ready = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, item, directory, parent=None):
        super().__init__(parent)
        self.item, self.directory = item, directory
        self.output = bytearray()
        self.done = False
        self.session_launcher = shutil.which("setsid")
        self.process = QProcess(self)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self.fail("Command timed out"))
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.readyReadStandardError.connect(lambda: self.process.readAllStandardError())
        self.process.errorOccurred.connect(lambda error: self.fail(self.process.errorString()))
        self.process.finished.connect(self.finished)

    def start(self):
        command = self.item["command"]
        args = ["/bin/sh", "-c", command] if isinstance(command, str) else command
        self.process.setWorkingDirectory(str(self.directory))
        self.process.setStandardInputFile(QProcess.nullDevice())
        self.timer.start(round(self.item["timeout"] * 1000))
        if self.session_launcher:
            args = [self.session_launcher, *args]
        self.process.start(args[0], args[1:])

    def read_output(self):
        data = bytes(self.process.readAllStandardOutput())
        if self.done:
            return
        if len(self.output) + len(data) > MAX_SOURCE_BYTES:
            self.fail("Command output exceeds the 1 MiB insertion limit")
        else:
            self.output.extend(data)

    def finished(self, code, status):
        self.read_output()
        if self.done:
            return
        if code or status != QProcess.ExitStatus.NormalExit:
            self.fail(f"Command failed (exit {code})")
            return
        try:
            text = self.output.decode("utf-8")
        except UnicodeError:
            self.fail("Command output is not UTF-8 text")
            return
        self.done = True
        self.timer.stop()
        self.ready.emit(text)

    def fail(self, message):
        if not self.done:
            self.cancel()
            self.failed.emit(message)

    def cancel(self):
        self.done = True
        self.timer.stop()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            if self.session_launcher and self.process.processId():
                try:
                    os.killpg(self.process.processId(), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            self.process.kill()
        else:
            self.deleteLater()
