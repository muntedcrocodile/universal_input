import json

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtTest import QTest

from universal_input.editor import EditorWindow
from universal_input.shortcuts import normalize_bindings
from universal_input.storage import Store, atomic_json


@pytest.mark.parametrize("rendered", [False, True])
def test_quick_insert_selects_code_contents_at_cursor(app, rendered):
    window = EditorWindow()
    window.open_draft("🦎 before after")
    if rendered:
        window.mode.setCurrentIndex(1)
    cursor = window.edit.textCursor()
    cursor.setPosition(10)  # after the UTF-16 surrogate pair and ' before '
    window.edit.setTextCursor(cursor)
    window.quick_actions["code_block"]()
    assert window.edit.textCursor().selectedText() == "code"
    window.edit.insertPlainText("print('ready')")
    assert "print('ready')" in window.draft_markdown()
    assert "before" in window.draft_markdown() and "after" in window.draft_markdown()
    if not rendered:
        assert "```text\nprint('ready')\n```" in window.edit.toPlainText()
    window.hide()


@pytest.mark.parametrize("action,placeholder", [("tasks", "First task"), ("quote", "Quoted text"), ("link", "link text")])
def test_quick_insert_selects_placeholders(app, action, placeholder):
    window = EditorWindow()
    window.quick_actions[action]()
    assert window.edit.textCursor().selectedText() == placeholder


def test_highlighting_is_visual_handles_unicode_and_code(app):
    window = EditorWindow()
    text = "🦎 **bold**\n\n```python\ndef greet():\n    return 'hello'\n```"
    window.edit.setPlainText(text)
    before = window.edit.toHtml()
    window.highlighter.refresh()
    assert window.edit.toHtml() == before
    assert window.draft_markdown() == text
    spans = window.edit.document().firstBlock().layout().formats()
    assert any(span.start == 3 and span.format.fontWeight() == QFont.Weight.Bold for span in spans)
    code_spans = window.edit.document().findBlockByNumber(3).layout().formats()
    assert any(span.start == 0 and span.format.foreground().color().name() == "#ff7b72" for span in code_spans)
    window.mode.setCurrentIndex(1)
    assert not window.highlighter.enabled
    window.mode.setCurrentIndex(0)
    assert window.highlighter.enabled
    assert window.edit.toPlainText() == text


def test_spelling_navigation_popup_number_choice_and_dictionary_persist(app, tmp_path):
    dictionary = tmp_path / "personal-dictionary.txt"
    window = EditorWindow(personal_dictionary=dictionary)
    window.open_draft("🦎 colour mispelled and Zorbablax")
    window.spelling.refresh()
    assert [error.word for error in window.spelling.errors] == ["mispelled", "Zorbablax"]
    cursor = window.edit.textCursor()
    cursor.setPosition(0)
    window.edit.setTextCursor(cursor)
    window.spelling.jump(1)
    assert window.edit.textCursor().selectedText() == "mispelled"
    assert window.spelling_panel.isVisible()
    assert not window.spelling_panel.isWindow()
    chosen = window.spelling_panel.suggestions[0]
    window.choose_numbered(0)
    assert chosen in window.edit.toPlainText()
    window.spelling.jump(1)
    assert window.edit.textCursor().selectedText() == "Zorbablax"
    window.spelling_panel.choose(len(window.spelling_panel.suggestions))
    assert "Zorbablax" in dictionary.read_text()
    assert "Zorbablax" not in [error.word for error in window.spelling.errors]
    restored = EditorWindow(personal_dictionary=dictionary)
    restored.edit.setPlainText("Zorbablax")
    restored.spelling.refresh()
    assert not restored.spelling.errors
    window.hide()


def test_spelling_skips_code_and_links_without_exporting_underlines(app):
    window = EditorWindow()
    text = "colour mispelled\n\n```python\nzorbaxxy()\n```\n`zorbaxxy` https://zorbaxxy.example"
    window.edit.setPlainText(text)
    before = window.edit.toHtml()
    window.spelling.refresh()
    assert [error.word for error in window.spelling.errors] == ["mispelled"]
    assert window.edit.extraSelections()
    assert window.edit.toHtml() == before


def test_config_bindings_aliases_disable_and_conflicts(app, tmp_path):
    store = Store(tmp_path)
    config = json.loads(store.config_path.read_text())
    config["keybindings"].update({"toggle_mode": "F6", "bold": "", "code_block": ["F7", "Ctrl+Alt+C"]})
    atomic_json(store.config_path, config)
    restored = Store(tmp_path)
    window = EditorWindow(bindings=restored.keybindings)
    window.open_draft("text")
    QTest.qWait(60)
    QTest.keyClick(window.edit, Qt.Key.Key_F6)
    QTest.qWait(60)
    assert window.mode.currentText() == "Rendered"
    assert window.mode.shortcut == "F6"
    assert "Ctrl+B" not in window.edit.commands
    QTest.keyClick(window.edit, Qt.Key.Key_F7)
    QTest.qWait(60)
    assert window.edit.textCursor().selectedText() == "code"
    with pytest.raises(ValueError, match="assigned to both"):
        normalize_bindings({"bold": "Ctrl+M"})
    with pytest.raises(ValueError, match="Unknown"):
        normalize_bindings({"typo": "Ctrl+T"})
    window.hide()


def test_spelling_popup_keyboard_choices_and_dictionary(app, tmp_path):
    window = EditorWindow(personal_dictionary=tmp_path / "words.txt")
    window.cancelled.connect(window.hide)
    window.open_draft("mispelled Zorbablax")
    window.edit.moveCursor(QTextCursor.MoveOperation.Start)
    QTest.keyClick(window.edit, Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier)
    panel = window.spelling_panel
    assert panel.isVisible()
    QTest.keyClick(panel.list, Qt.Key.Key_Down)
    assert panel.list.currentRow() == 1
    QTest.keyClick(panel.list, Qt.Key.Key_Up)
    assert panel.list.currentRow() == 0
    replacement = panel.suggestions[0]
    QTest.keyClick(panel.list, Qt.Key.Key_1, Qt.KeyboardModifier.AltModifier)
    assert window.edit.toPlainText().startswith(replacement)
    QTest.keyClick(window.edit, Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier)
    assert window.edit.textCursor().selectedText() == "Zorbablax"
    number = len(panel.suggestions) + 1
    QTest.keyClick(panel.list, getattr(Qt.Key, f"Key_{number}"), Qt.KeyboardModifier.AltModifier)
    assert "Zorbablax" in (tmp_path / "words.txt").read_text()
    window.edit.setPlainText("mispelled")
    window.edit.moveCursor(QTextCursor.MoveOperation.Start)
    QTest.keyClick(window.edit, Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(panel.list, Qt.Key.Key_Escape)
    assert not window.isVisible()
    assert not panel.isVisible()


@pytest.mark.parametrize("rendered", [False, True])
def test_font_size_shortcuts_persist_without_changing_text(app, tmp_path, rendered):
    store = Store(tmp_path)
    window = EditorWindow(font_size=store.config["editor_font_size"])
    window.font_size_changed.connect(store.save_font_size)
    window.open_draft("**bold** and text")
    if rendered:
        window.mode.setCurrentIndex(1)
    cursor = window.edit.textCursor()
    cursor.setPosition(1)
    cursor.setPosition(3, QTextCursor.MoveMode.KeepAnchor)
    window.edit.setTextCursor(cursor)
    before = window.draft_markdown()
    QTest.keyClick(window.edit, Qt.Key.Key_Plus, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    assert window.font_size == 17
    assert window.edit.font().pixelSize() == 17
    assert window.draft_markdown() == before
    assert window.edit.textCursor().selectionStart() == 1
    restored = Store(tmp_path)
    assert restored.config["editor_font_size"] == 17
    reopened = EditorWindow(font_size=restored.config["editor_font_size"])
    assert reopened.edit.font().pixelSize() == 17
    window.mode.setCurrentIndex(1 - window.mode.currentIndex())
    assert window.edit.font().pixelSize() == 17
    QTest.keyClick(window.edit, Qt.Key.Key_Underscore, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    assert window.font_size == 16
    assert Store(tmp_path).config["editor_font_size"] == 16
    window.hide()
