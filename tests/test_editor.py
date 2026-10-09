# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
from PyQt6.QtGui import QTextCursor, QFont
from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt
import pytest

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


@pytest.mark.parametrize('markdown,word', [
    ('# Heading\n\nFirst paragraph.\n\nA **second** paragraph.', 'second'),
    ('🦎 **hello** world', 'hello'),
    ('- first\n- second\n- third', 'second'),
    ('Before\n\n```python\nprint("hello")\n```\n\nAfter', 'hello'),
    ('| First | Second |\n| --- | --- |\n| apple | banana |', 'banana'),
    ('[label](https://example.com) followed by text', 'label'),
])
def test_mode_hotkey_keeps_cursor_in_same_word(app, markdown, word):
    window = EditorWindow()
    window.open_draft(markdown)
    found = window.edit.document().find(word)
    position = found.selectionStart() + 2
    select(window.edit, position, position)
    QTest.keyClick(window.edit, Qt.Key.Key_M, Qt.KeyboardModifier.ControlModifier)
    assert window.edit.rich
    assert window.edit.textCursor().position() == window.edit.document().find(word).selectionStart() + 2
    QTest.keyClick(window.edit, Qt.Key.Key_M, Qt.KeyboardModifier.ControlModifier)
    assert not window.edit.rich
    assert window.edit.textCursor().position() == position


@pytest.mark.parametrize('backward', [False, True])
def test_mode_switch_preserves_selection_and_direction(app, backward):
    window = EditorWindow()
    window.edit.setPlainText('🦎 **selected** text')
    start, end = (5, 13) if not backward else (13, 5)
    select(window.edit, start, end)
    window.mode.setCurrentIndex(1)
    cursor = window.edit.textCursor()
    assert cursor.selectedText() == 'selected'
    assert (cursor.position() < cursor.anchor()) == backward
    window.mode.setCurrentIndex(0)
    assert (window.edit.textCursor().anchor(), window.edit.textCursor().position()) == (start, end)


def test_mode_switch_maps_new_selection_in_rendered_view(app):
    window = EditorWindow()
    window.edit.setPlainText('First **bold** and *second* word')
    window.mode.setCurrentIndex(1)
    window.edit.setTextCursor(window.edit.document().find('second'))
    window.mode.setCurrentIndex(0)
    assert window.edit.textCursor().selectedText() == 'second'


def test_mode_switch_maps_cursor_after_rendered_edit(app):
    window = EditorWindow()
    window.edit.setPlainText('# Heading\n\nSome **bold** words')
    window.mode.setCurrentIndex(1)
    window.edit.setTextCursor(window.edit.document().find('bold'))
    window.edit.insertPlainText('changed')
    window.mode.setCurrentIndex(0)
    expected = window.edit.document().find('changed').selectionEnd()
    assert window.edit.textCursor().position() == expected
    window.edit.insertPlainText('!')
    assert 'changed!' in window.edit.content_text()


@pytest.mark.parametrize('position', [0, 1, 2, 6, 7, 8, 9])
def test_mode_roundtrip_restores_exact_cursor_at_markup_and_end(app, position):
    window = EditorWindow()
    window.edit.setPlainText('**bold**')
    select(window.edit, position, position)
    window.mode.setCurrentIndex(1)
    window.mode.setCurrentIndex(0)
    assert window.edit.textCursor().position() == position


def test_mode_switch_keeps_cursor_visible_in_long_draft(app):
    window = EditorWindow()
    window.open_draft('\n\n'.join(f'Paragraph {i}: **some text**' for i in range(40)))
    found = window.edit.document().find('Paragraph 35')
    position = found.selectionStart() + 4
    select(window.edit, position, position)
    for mode in (1, 0):
        window.mode.setCurrentIndex(mode)
        app.processEvents()
        assert window.edit.textCursor().position() == window.edit.document().find('Paragraph 35').selectionStart() + 4
        assert window.edit.viewport().rect().intersects(window.edit.cursorRect())


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
