# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
import stat
import time

import pytest
import yaml
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtTest import QTest

from universal_input.editor import EditorWindow
from universal_input.quick_insert import normalize_quick_insert
from universal_input.shortcuts import normalize_bindings
from universal_input.storage import Store


def recipe(**kwargs):
    return dict(id="custom", label="Custom", **kwargs)


def wait_until(predicate, timeout=3000):
    deadline = time.monotonic() + timeout / 1000
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert predicate()


def test_yaml_migrates_json_preserves_original_and_shortcuts(tmp_path):
    original = json.dumps(dict(editor_font_size=23, automatic_popup=False,
                               keybindings=dict(code_block=["F7", "Ctrl+Alt+C"], table="")))
    legacy = tmp_path / "config.json"
    legacy.write_text(original)
    store = Store(tmp_path)
    assert legacy.read_text() == original
    assert store.config_path.name == "config.yaml"
    assert stat.S_IMODE(store.config_path.stat().st_mode) == 0o600
    assert store.keybindings["code_block"] == ["F7", "Ctrl+Alt+C"]
    assert store.keybindings["table"] == []
    assert "code_block" not in store.config["keybindings"]
    legacy.write_text("invalid old config")
    assert Store(tmp_path).config["editor_font_size"] == 23


def test_yaml_comments_multiline_and_font_save_preserve_external_edits(tmp_path):
    path = tmp_path / "config.yaml"
    text = '# My settings\neditor_font_size: 18 # pixels\nquick_insert:\n  - id: note\n    label: Note\n    text: |\n      First line\n      Second line\n'
    path.write_text(text)
    store = Store(tmp_path)
    assert path.read_text() == text
    assert store.quick_insert[0]["text"] == "First line\nSecond line\n"
    path.write_text(text.replace("Note", "Memo"))
    store.save_font_size(20)
    assert path.read_text() == text.replace("Note", "Memo").replace("18 #", "20 #")
    assert Store(tmp_path).config["editor_font_size"] == 20


@pytest.mark.parametrize("text", ["quick_insert: [", "quick_insert: null", "- a", "keybindings: {}\nkeybindings: {}", "quick_insert:\n - id: x\n   label: X\n   text: a\n   file: b", "!!python/object:object {}"])
def test_invalid_yaml_never_overwritten(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text)
    with pytest.raises(RuntimeError, match="Invalid configuration"):
        Store(tmp_path)
    assert path.read_text() == text


@pytest.mark.parametrize("item", [recipe(), recipe(text="a", file="b"), recipe(text="a", cursor=-1),
    recipe(command=[]), recipe(command=[1]), recipe(text="a", select=""),
    recipe(text="a", cursor=True), recipe(text="a", typo=True), recipe(action="unknown"),
    recipe(command="sleep 1", timeout=0), recipe(text="a", select="a", cursor=1)])
def test_invalid_recipes(item):
    with pytest.raises(ValueError):
        normalize_quick_insert([item])


def test_duplicate_actions_and_shortcut_conflicts():
    with pytest.raises(ValueError, match="unique"):
        normalize_quick_insert([recipe(text="a"), recipe(text="b")])
    with pytest.raises(ValueError, match="assigned to both"):
        normalize_bindings(quick_insert=[recipe(text="a", shortcut="Ctrl+B")])
    with pytest.raises(ValueError, match="conflicts"):
        normalize_bindings(quick_insert=[dict(id="bold", label="Bold", text="a")])


@pytest.mark.parametrize("rendered", [False, True])
@pytest.mark.parametrize("kind", ["text", "file"])
def test_custom_text_file_selection_and_undo(app, tmp_path, rendered, kind):
    text = "🦎 **chosen** suffix"
    if kind == "file":
        (tmp_path / "snippet.md").write_text(text)
    item = recipe(**{kind: text if kind == "text" else "snippet.md"}, select="chosen")
    window = EditorWindow(quick_insert=[item], config_directory=tmp_path)
    window.open_draft("before replace after")
    if rendered:
        window.mode.setCurrentIndex(1)
    cursor = window.edit.textCursor()
    cursor.setPosition(7)
    cursor.setPosition(14, QTextCursor.MoveMode.KeepAnchor)
    window.edit.setTextCursor(cursor)
    window.quick_actions["custom"]()
    assert window.edit.textCursor().selectedText() == "chosen"
    assert window.edit.content_text().startswith("before 🦎")
    assert window.edit.content_text().endswith("suffix after")
    window.edit.undo()
    assert window.edit.content_text() == "before replace after"


@pytest.mark.parametrize("rendered", [False, True])
@pytest.mark.parametrize("position,expected", [("start", ""), (2, "🦎 "), ("end", "🦎 bold end")])
def test_plain_cursor_positions_count_unicode_characters(app, rendered, position, expected):
    window = EditorWindow(quick_insert=[recipe(text="🦎 bold end", format="plain", cursor=position)])
    window.open_draft("")
    if rendered:
        window.mode.setCurrentIndex(1)
    window.quick_actions["custom"]()
    cursor = window.edit.textCursor()
    cursor.setPosition(0, QTextCursor.MoveMode.KeepAnchor)
    assert cursor.selectedText() == expected


@pytest.mark.parametrize("rendered", [False, True])
def test_markdown_cursor_maps_through_formatting(app, rendered):
    window = EditorWindow(quick_insert=[recipe(text="🦎 **bold** end", cursor=6)])
    window.open_draft("")
    if rendered:
        window.mode.setCurrentIndex(1)
    window.quick_actions["custom"]()
    cursor = window.edit.textCursor()
    cursor.setPosition(0, QTextCursor.MoveMode.KeepAnchor)
    assert cursor.selectedText() == ("🦎 bo" if rendered else "🦎 **bo")


def test_empty_list_and_shortcut_only_action(app):
    empty = EditorWindow(quick_insert=[])
    assert not empty.quick_actions
    assert "Ctrl+Alt+C" not in empty.edit.commands
    window = EditorWindow(quick_insert=[recipe(text="custom", shortcut=["F7", "F8"], toolbar=False)])
    assert not window.quick_buttons
    window.open_draft("")
    QTest.qWait(80)
    QTest.keyClick(window.edit, Qt.Key.Key_F8)
    assert window.edit.content_text() == "custom"


def test_table_action_can_be_renamed_and_shortcut_only(app):
    window = EditorWindow(quick_insert=[dict(id="grid", label="Grid", action="table", toolbar=False)])
    window.open_draft("")
    window.quick_actions["grid"]()
    assert window.table_picker.isVisible()
    window.insert_table(2, 2)
    assert window.edit.textCursor().selectedText() == "Column 1"


def test_missing_file_preserves_draft(app, tmp_path):
    window = EditorWindow(quick_insert=[recipe(file="missing.txt")], config_directory=tmp_path)
    window.open_draft("unchanged")
    window.quick_actions["custom"]()
    assert window.edit.content_text() == "unchanged"
    assert "missing.txt" in window.status.text()


@pytest.mark.parametrize("command", [["printf", "%s", "**result**"], "printf '**result**'"])
def test_command_success_selection_and_undo(app, tmp_path, command):
    window = EditorWindow(quick_insert=[recipe(command=command, select="result")], config_directory=tmp_path)
    window.open_draft("replace")
    window.edit.selectAll()
    window.quick_actions["custom"]()
    wait_until(lambda: window.source_job is None)
    assert window.edit.content_text() == "**result**"
    assert window.edit.textCursor().selectedText() == "result"
    window.edit.undo()
    assert window.edit.content_text() == "replace"


@pytest.mark.parametrize("command,message,timeout", [
    (["/missing/program"], "", 10), (["sh", "-c", "exit 7"], "exit 7", 10),
    (["sleep", "5"], "timed out", 0.1),
    (["python3", "-c", "import sys; sys.stdout.buffer.write(b'\\xff')"], "UTF-8", 10),
    (["python3", "-c", "print('x' * 1100000)"], "1 MiB", 10),
])
def test_command_failures_leave_draft_untouched(app, command, message, timeout):
    window = EditorWindow(quick_insert=[recipe(command=command, timeout=timeout)])
    window.open_draft("unchanged")
    window.quick_actions["custom"]()
    wait_until(lambda: window.source_job is None)
    assert window.edit.content_text() == "unchanged"
    assert message in window.status.text()
    QTest.qWait(30)


@pytest.mark.parametrize("change", ["edit", "cursor", "hide", "mode"])
def test_pending_command_does_not_insert_into_changed_destination(app, change):
    window = EditorWindow(quick_insert=[recipe(command=["sh", "-c", "sleep 0.1; printf wrong"])])
    window.open_draft("original")
    window.quick_actions["custom"]()
    if change == "edit":
        window.edit.insertPlainText("changed")
    elif change == "cursor":
        window.edit.moveCursor(QTextCursor.MoveOperation.Start)
    elif change == "mode":
        window.mode.setCurrentIndex(1)
    else:
        window.hide()
    QTest.qWait(250)
    assert "wrong" not in window.edit.content_text()


@pytest.mark.parametrize("text", [
    "indent_width: &size 4\neditor_font_size: *size\n",
    "quick_insert: []\n...\n",
    "{quick_insert: []}\n",
])
def test_font_save_handles_yaml_aliases_and_document_end(tmp_path, text):
    # Load a valid starting configuration; simulate an external edit while open.
    store = Store(tmp_path)
    store.config_path.write_text(text)
    store.save_font_size(22)
    data = yaml.safe_load(store.config_path.read_text())
    assert data["editor_font_size"] == 22
    if "indent_width" in data:
        assert data["indent_width"] == 4


@pytest.mark.parametrize("rendered", [False, True])
def test_plain_format_keeps_markdown_literal(app, rendered):
    window = EditorWindow(quick_insert=[recipe(text="**literal**", format="plain", select="literal")])
    window.open_draft("")
    if rendered:
        window.mode.setCurrentIndex(1)
    window.quick_actions["custom"]()
    assert window.edit.toPlainText().startswith("**literal**")
    assert window.edit.textCursor().selectedText() == "literal"
    assert window.edit.textCursor().charFormat().fontWeight() < 700


def test_file_reads_fresh_and_rejects_large_or_invalid_text(app, tmp_path):
    path = tmp_path / "snippet.txt"
    window = EditorWindow(quick_insert=[recipe(file="snippet.txt")], config_directory=tmp_path)
    window.open_draft("")
    for value in ("first", "second"):
        path.write_text(value)
        window.edit.selectAll()
        window.quick_actions["custom"]()
        window.edit.ensure_trailing_newline()
        assert window.edit.content_text() == value
    for value in (b"x" * 1100000, b"\xff"):
        path.write_bytes(value)
        window.quick_actions["custom"]()
        assert window.edit.content_text() == "second"


def test_command_working_directory_and_literal_arguments(app, tmp_path):
    (tmp_path / "value").write_text("directory works")
    window = EditorWindow(quick_insert=[recipe(command=["cat", "value"])], config_directory=tmp_path)
    window.open_draft("")
    window.quick_actions["custom"]()
    wait_until(lambda: window.source_job is None)
    assert window.edit.content_text() == "directory works"


def test_example_configuration_loads(tmp_path):
    from pathlib import Path
    (tmp_path / "config.yaml").write_text(Path("config.example.yaml").read_text())
    assert len(Store(tmp_path).quick_insert) == 7
