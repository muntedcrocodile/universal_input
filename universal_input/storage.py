"""Private, atomic configuration and history storage."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile
import time

from .history import History

DEFAULT_CONFIG = {"recent_entries_limit": 50, "clipboard_entries_limit": 50}


def atomic_json(path, data):
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


class Store:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory is not None else Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "universal-input"
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.directory.chmod(0o700)
        self.config_path = self.directory / "config.json"
        self.history_path = self.directory / "history.json"
        if not self.config_path.exists():
            atomic_json(self.config_path, DEFAULT_CONFIG)
        self.config_path.chmod(0o600)
        try:
            self.config = json.loads(self.config_path.read_text())
            if not isinstance(self.config, dict):
                raise ValueError("expected an object")
            for key, default in DEFAULT_CONFIG.items():
                value = self.config.setdefault(key, default)
                if type(value) is not int or not 0 <= value <= 500:
                    raise ValueError(f"{key} must be an integer from 0 to 500")
        except (ValueError, OSError) as exc:
            raise RuntimeError(f"Invalid configuration at {self.config_path}: {exc}") from exc
        self.entries = History(self.config["recent_entries_limit"])
        self.clipboard = History(self.config["clipboard_entries_limit"])
        self.warning = None
        self.load()

    def load(self):
        if not self.history_path.exists():
            return
        self.history_path.chmod(0o600)
        try:
            data = json.loads(self.history_path.read_text())
            if not isinstance(data, dict) or data.get("version") != 1:
                raise ValueError("unsupported history format")
            # Validate both lists before changing either in-memory history.
            for key in ("recent_entries", "clipboard_entries"):
                rows = data.get(key, [])
                if not isinstance(rows, list) or any(
                    not isinstance(row, dict) or not isinstance(row.get("text"), str)
                    or (row.get("html") is not None and not isinstance(row["html"], str))
                    for row in rows
                ):
                    raise ValueError("invalid history entry")
            for key, history in (("recent_entries", self.entries), ("clipboard_entries", self.clipboard)):
                for row in reversed(data.get(key, [])[:history.limit]):
                    history.add(row["text"], row.get("html"))
        except ValueError:
            backup = self.history_path.with_name(f"history.invalid-{time.time_ns()}.json")
            self.history_path.rename(backup)
            self.warning = f"Unreadable history preserved at {backup}. Starting a new history."
        self.save()  # Enforce reduced limits on disk as well as in memory.

    def save(self):
        atomic_json(self.history_path, {
            "version": 1,
            "recent_entries": [asdict(entry) for entry in self.entries.entries],
            "clipboard_entries": [asdict(entry) for entry in self.clipboard.entries],
        })
