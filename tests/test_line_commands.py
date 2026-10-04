# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtTest import QTest
from universal_input.editor import EditorWindow
from universal_input.history import History
from universal_input.code_blocks import ROOT_CHROME

CTRL = Qt.KeyboardModifier.ControlModifier
ALT = Qt.KeyboardModifier.AltModifier


def key(window, key, modifier=Qt.KeyboardModifier.NoModifier):
    QTest.keyClick(window.focusWidget() or window.edit, key, modifier)


@pytest.mark.parametrize('rendered', [False, True])
def test_select_line_includes_newline_and_repeats(app, rendered):
    window = EditorWindow()
    window.open_draft('')
    window.mode.setCurrentIndex(int(rendered))
    text = 'a long line 🦎 ' * 40
    window.edit.setPlainText(text + '\nsecond\nthird')
    QTest.qWait(30)
    cursor = window.edit.textCursor(); cursor.setPosition(8)
    window.edit.setTextCursor(cursor)
    key(window, Qt.Key.Key_L, CTRL)
    assert window.edit.textCursor().selectedText() == text + '\u2029'
    key(window, Qt.Key.Key_L, CTRL)
    assert window.edit.textCursor().selectedText() == text + '\u2029second\u2029'
    window.edit.moveCursor(QTextCursor.MoveOperation.End)
    key(window, Qt.Key.Key_L, CTRL)
    assert not window.edit.textCursor().hasSelection()
    assert window.draft_markdown()


@pytest.mark.parametrize('rendered', [False, True])
def test_goto_scrolled_line_validation_and_escape(app, rendered):
    window = EditorWindow()
    window.open_draft('')
    window.mode.setCurrentIndex(int(rendered))
    window.edit.setPlainText('\n'.join('line ' + str(n) for n in range(1, 151)))
    QTest.qWait(30)
    key(window, Qt.Key.Key_G, CTRL)
    prompt = window.number_prompt
    assert prompt.isVisible() and prompt.input.hasFocus() and not prompt.isWindow()
    QTest.keyClicks(prompt.input, '999')
    key(window, Qt.Key.Key_Return)
    assert prompt.isVisible()
    prompt.input.selectAll(); QTest.keyClicks(prompt.input, '120')
    key(window, Qt.Key.Key_Return)
    assert not prompt.isVisible()
    assert window.edit.hasFocus() and window.edit.textCursor().blockNumber() == 119
    assert window.edit.viewport().rect().intersects(window.edit.cursorRect())
    key(window, Qt.Key.Key_G, CTRL)
    QTest.keyClicks(prompt.input, '7')
    key(window, Qt.Key.Key_Escape)
    assert not prompt.isVisible() and window.isVisible()
    assert window.edit.textCursor().blockNumber() == 119
    assert window.edit.line_numbers.width() == window.edit.viewportMargins().left()
    old_width = window.edit.line_numbers.width()
    window.change_font_size(1)
    assert window.edit.line_numbers.width() >= old_width


@pytest.mark.parametrize('shelf', [0, 1])
def test_numeric_history_inserts_beyond_nine_at_selection_and_snapshots_list(app, shelf):
    history = History(limit=50)
    for n in range(20):
        history.add(f'entry {n}')
    window = EditorWindow(entry_history=history if shelf == 0 else None, clipboard_history=history if shelf else None)
    window.open_draft('before replace after')
    QTest.qWait(30)
    window.edit.setTextCursor(window.edit.document().find('replace'))
    window.highlight_history(shelf)
    key(window, Qt.Key.Key_I, ALT)
    prompt = window.number_prompt
    assert prompt.isVisible() and prompt.input.hasFocus()
    expected = history.entries[11].text
    history.add('new arrival')
    QTest.keyClicks(prompt.input, '12')
    key(window, Qt.Key.Key_Return)
    assert window.edit.content_text() == f'before {expected} after'
    assert window.edit.hasFocus() and not prompt.isVisible()


def test_numeric_shortcuts_can_be_remapped_and_empty_history_dismissed(app):
    window = EditorWindow(bindings={'select_line': 'F6', 'goto_line': 'F7', 'insert_history_number': 'F8'})
    window.open_draft('some text')
    QTest.qWait(30)
    key(window, Qt.Key.Key_F6)
    assert window.edit.textCursor().selectedText() == 'some text\u2029'
    key(window, Qt.Key.Key_F7)
    assert window.number_prompt.isVisible()
    key(window, Qt.Key.Key_Escape)
    key(window, Qt.Key.Key_F8)
    assert window.number_prompt.isVisible() and not window.number_prompt.input.isEnabled()
    key(window, Qt.Key.Key_Escape)
    assert window.isVisible() and not window.number_prompt.isVisible()


def test_first_code_header_and_exclusive_language_selection(app):
    window = EditorWindow(font_size=25)
    source = '```python\nprint(42)\nprint(43)\n```\n\nAfter'
    window.open_draft(source)
    window.mode.setCurrentIndex(1)
    QTest.qWait(40)
    window.edit.verticalScrollBar().setValue(0)
    header = window.code_blocks.headers[0]
    assert window.edit.viewport().rect().contains(header.geometry())
    window.navigator.select(header.part)
    assert header.input.selectedText() == 'python'
    assert not window.edit.textCursor().hasSelection()
    QTest.keyPress(header.input, Qt.Key.Key_Tab)
    QTest.keyClick(header.input, Qt.Key.Key_Right)
    QTest.keyRelease(window.edit, Qt.Key.Key_Tab)
    assert window.edit.textCursor().selectedText() == 'print(42)\u2029print(43)'
    # Clicking the header also clears an existing body selection.
    QTest.mouseClick(header.input, Qt.MouseButton.LeftButton)
    assert not window.edit.textCursor().hasSelection()
    assert window.draft_markdown() == source
    clean = window.edit.content_document()
    assert not clean.rootFrame().frameFormat().hasProperty(ROOT_CHROME)
    assert clean.rootFrame().frameFormat().topMargin() == 4
    window.mode.setCurrentIndex(0)
    assert window.edit.document().rootFrame().frameFormat().topMargin() == 4
