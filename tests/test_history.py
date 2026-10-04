import json
import stat

import pytest
from PyQt6.QtGui import QTextCursor

from universal_input.editor import EditorWindow
from universal_input.history import History
from universal_input.storage import Store, atomic_json


def test_history_deduplicates_promotes_and_limits():
    history = History(limit=2)
    for text in ("one", "two", "one", "three"):
        history.add(text)
    assert [e.text for e in history.entries] == ["three", "one"]
    assert not history.add("")
    assert not History(limit=0).add("disabled")


def test_history_roundtrip_and_permissions(tmp_path):
    store = Store(tmp_path / "config")
    store.entries.add("🦎 rich", "<b>🦎 rich</b>")
    store.clipboard.add("clipboard\nentry")
    store.save()
    restored = Store(store.directory)
    assert restored.entries.entries == store.entries.entries
    assert restored.clipboard.entries == store.clipboard.entries
    assert stat.S_IMODE(store.directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(store.history_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(store.config_path.stat().st_mode) == 0o600


def test_reduced_limits_trim_persisted_history(tmp_path):
    store = Store(tmp_path)
    for i in range(10):
        store.entries.add(str(i))
        store.clipboard.add(str(i))
    store.save()
    atomic_json(store.config_path, {"recent_entries_limit": 2, "clipboard_entries_limit": 0})
    restored = Store(tmp_path)
    assert [e.text for e in restored.entries.entries] == ["9", "8"]
    assert not restored.clipboard.entries
    assert len(json.loads(store.history_path.read_text())["recent_entries"]) == 2
    assert json.loads(store.history_path.read_text())["clipboard_entries"] == []


def test_invalid_history_is_preserved_and_config_is_not_overwritten(tmp_path):
    store = Store(tmp_path)
    store.history_path.write_text("invalid json")
    restored = Store(tmp_path)
    assert restored.warning
    backups = list(tmp_path.glob("history.invalid-*.json"))
    assert len(backups) == 1
    assert backups[0].read_text() == "invalid json"
    atomic_json(store.config_path, {"recent_entries_limit": -1})
    with pytest.raises(RuntimeError, match="Invalid configuration"):
        Store(tmp_path)
    assert json.loads(store.config_path.read_text())["recent_entries_limit"] == -1


def test_history_inserts_at_cursor_and_replaces_selection(app):
    window = EditorWindow()
    window.remember_entry("recent")
    window.remember_clipboard("clipboard")
    window.edit.setPlainText("before after")
    cursor = window.edit.textCursor()
    cursor.setPosition(7)
    window.edit.setTextCursor(cursor)
    window.insert_history(0, 0)
    assert window.edit.toPlainText() == "before recentafter"
    window.edit.selectAll()
    window.insert_history(1, 0)
    assert window.edit.toPlainText() == "clipboard"
    assert window.active_history == 1
    window.insert_history(1, 8)
    assert window.edit.toPlainText() == "clipboard"


def test_recent_history_restores_canonical_markdown_exactly(app):
    window = EditorWindow()
    window.remember_entry("**bold**", "<b>bold</b>")
    window.insert_history(0, 0)
    assert window.edit.toPlainText() == "**bold**"
