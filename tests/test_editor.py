from PyQt6.QtGui import QTextCursor, QFont
from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt

from universal_input.editor import EditorWindow


def select(edit, start, end):
    cursor = edit.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    edit.setTextCursor(cursor)


def test_markdown_wrap_and_toggle(app):
    window = EditorWindow()
    window.edit.setPlainText("hello world")
    select(window.edit, 6, 11)
    window.edit.toggle_format("bold")
    assert window.edit.content_text() == "hello **world**"
    assert window.edit.textCursor().selectedText() == "world"
    window.edit.toggle_format("bold")
    assert window.edit.content_text() == "hello world"


def test_empty_selection_leaves_cursor_inside_markers(app):
    window = EditorWindow()
    window.edit.toggle_format("italic")
    window.edit.insertPlainText("hello")
    assert window.edit.content_text() == "*hello*"


def test_unicode_selection(app):
    window = EditorWindow()
    window.edit.setPlainText("🦎 hello")
    select(window.edit, 3, 8)
    window.edit.toggle_format("bold")
    assert window.edit.content_text() == "🦎 **hello**"
    window.edit.undo()
    assert window.edit.content_text() == "🦎 hello"


def test_rich_formatting_changes_document_not_text(app):
    window = EditorWindow()
    window.edit.rich = True
    window.edit.setPlainText("hello")
    window.edit.selectAll()
    window.edit.toggle_format("bold")
    assert window.edit.content_text() == "hello"
    assert window.edit.currentCharFormat().fontWeight() == QFont.Weight.Bold
    assert "font-weight:700" in window.edit.toHtml()
    window.edit.toggle_format("bold")
    assert window.edit.currentCharFormat().fontWeight() == QFont.Weight.Normal


def test_rich_toggle_applies_to_subsequent_typing(app):
    window = EditorWindow()
    window.edit.rich = True
    window.edit.toggle_format("bold")
    window.edit.insertPlainText("bold")
    window.edit.toggle_format("bold")
    window.edit.insertPlainText(" normal")
    select(window.edit, 0, 4)
    assert window.edit.currentCharFormat().fontWeight() == QFont.Weight.Bold
    select(window.edit, 5, 11)
    assert window.edit.currentCharFormat().fontWeight() == QFont.Weight.Normal


def test_mode_switch_preserves_formatting(app):
    window = EditorWindow()
    window.edit.setPlainText("**bold**")
    window.mode.setCurrentIndex(1)
    assert window.edit.content_text() == "bold"
    window.mode.setCurrentIndex(0)
    assert window.edit.content_text() == "**bold**"


def test_open_loads_literal_markdown_and_unicode_caret(app):
    window = EditorWindow()
    window.open_draft("🦎 **existing**", caret=2)
    assert window.edit.content_text() == "🦎 **existing**"
    assert window.edit.textCursor().position() == 3
    window.hide()


def test_markdown_toggle_off_after_typing(app):
    window = EditorWindow()
    window.edit.toggle_format("bold")
    window.edit.insertPlainText("bold")
    window.edit.toggle_format("bold")
    window.edit.insertPlainText(" normal")
    assert window.edit.content_text() == "**bold** normal"


def test_view_roundtrip_preserves_raw_source_until_edited(app):
    window = EditorWindow()
    original = "# heading\n\ntext  with   spaces\n\n\n"
    window.open_draft(original)
    window.mode.setCurrentIndex(1)
    assert window.payload()[0] == original
    window.mode.setCurrentIndex(0)
    assert window.edit.content_text() == original
    window.hide()


def test_editing_mode_independent_of_destination(app):
    window = EditorWindow()
    window.mode.setCurrentIndex(1)
    window.open_draft("**bold**", rich=False)
    assert window.mode.currentText() == "Rendered"
    assert window.edit.content_text() == "bold"
    markdown, html, rendered = window.payload()
    assert markdown == "**bold**"
    assert rendered == "bold"
    assert "font-weight:700" in html
    window.hide()
