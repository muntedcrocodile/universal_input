import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor, QTextDocument
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
from universal_input.editor import EditorWindow
from universal_input.navigation import raw_parts
from universal_input.shortcuts import normalize_bindings


def jump(window, direction=1):
    target = QApplication.focusWidget() or window.edit
    QTest.keyPress(target, Qt.Key.Key_Tab)
    QTest.keyClick(QApplication.focusWidget() or target, Qt.Key.Key_Right if direction > 0 else Qt.Key.Key_Left)
    QTest.keyRelease(QApplication.focusWidget() or target, Qt.Key.Key_Tab)


@pytest.mark.parametrize('rendered', [False, True])
def test_code_language_then_body_and_reverse_after_edits(app, rendered):
    window = EditorWindow()
    window.open_draft('')
    window.mode.setCurrentIndex(int(rendered))
    QTest.qWait(40)
    window.quick_actions['code_block']()
    target = window.navigator.input if rendered else window.edit
    assert target.selectedText() == 'text' if rendered else target.textCursor().selectedText() == 'text'
    QTest.keyClicks(target, 'python')
    jump(window)
    assert window.edit.textCursor().selectedText() == 'code'
    QTest.keyClicks(window.edit, 'print(42)')
    jump(window, -1)
    if rendered:
        assert window.navigator.input.selectedText() == 'python'
    else:
        assert window.edit.textCursor().selectedText() == 'python'
    assert '```python\nprint(42)\n```' in window.draft_markdown()
    assert '\t' not in window.edit.toPlainText()
    window.hide()


@pytest.mark.parametrize('rendered', [False, True])
def test_tasks_and_link_parts(app, rendered):
    window = EditorWindow()
    window.open_draft('')
    window.mode.setCurrentIndex(int(rendered))
    QTest.qWait(40)
    window.quick_actions['tasks']()
    assert window.edit.textCursor().selectedText() == 'First task'
    jump(window)
    assert window.edit.textCursor().selectedText() == 'Second task'
    jump(window, -1)
    assert window.edit.textCursor().selectedText() == 'First task'
    window.open_draft('')
    window.quick_actions['link']()
    QTest.keyClicks(window.edit, 'Docs')
    jump(window)
    target = window.navigator.input if rendered else window.edit
    assert (target.selectedText() if rendered else target.textCursor().selectedText()) == 'https://example.com'
    QTest.keyClicks(target, 'https://example.org/docs')
    jump(window, -1)
    assert window.edit.textCursor().selectedText() == 'Docs'
    assert '[Docs](https://example.org/docs)' in window.draft_markdown()
    window.hide()


def test_tab_suppressed_even_with_shift_and_custom_navigation_keys(app):
    window = EditorWindow(bindings=normalize_bindings({'previous_part': 'F8', 'next_part': 'Tab+Down'}))
    window.open_draft('[label](url)')
    QTest.qWait(40)
    window.edit.setTextCursor(window.edit.document().find('label'))
    before = window.draft_markdown()
    for modifier in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier, Qt.KeyboardModifier.ControlModifier):
        QTest.keyClick(window.edit, Qt.Key.Key_Tab, modifier)
    assert window.draft_markdown() == before
    assert window.edit.hasFocus()
    QTest.keyPress(window.edit, Qt.Key.Key_Tab)
    QTest.keyClick(window.edit, Qt.Key.Key_Down)
    QTest.keyRelease(window.edit, Qt.Key.Key_Tab)
    assert window.edit.textCursor().selectedText() == 'url'
    QTest.keyClick(window.edit, Qt.Key.Key_F8)
    assert window.edit.textCursor().selectedText() == 'label'
    window.hide()


def test_raw_parser_handles_unicode_empty_cells_and_balanced_urls():
    text = '🦎 [label](https://example.org/a_(b))\n\n| A | B |\n|---|---|\n|   | c |\n\n~~~\nbody\n~~~\n'
    parts = raw_parts(text)
    document = QTextDocument(); document.setPlainText(text)
    def selected(part):
        cursor = QTextCursor(document); cursor.setPosition(part.start); cursor.setPosition(part.end, QTextCursor.MoveMode.KeepAnchor)
        return cursor.selectedText()
    assert [(p.kind, selected(p)) for p in parts] == [('link_text', 'label'), ('link_url', 'https://example.org/a_(b)'), ('cell', 'A'), ('cell', 'B'), ('cell', ''), ('cell', 'c'), ('code_language', ''), ('code_body', 'body')]


@pytest.mark.parametrize('rendered', [False, True])
def test_indent_selected_block_repeat_dedent_and_undo(app, rendered):
    window = EditorWindow(indent_width=4)
    window.open_draft('one\n  two\nthree')
    if rendered:
        window.mode.setCurrentIndex(1)
        window.edit.setPlainText('one\n  two\nthree')
    QTest.qWait(40)
    cursor = window.edit.textCursor(); cursor.setPosition(0); cursor.setPosition(10, QTextCursor.MoveMode.KeepAnchor)
    window.edit.setTextCursor(cursor)
    QTest.keyClick(window.edit, Qt.Key.Key_BracketRight, Qt.KeyboardModifier.ControlModifier)
    assert window.edit.content_text() == '    one\n      two\nthree'
    assert window.edit.textCursor().selectedText() == '    one\u2029      two'
    QTest.keyClick(window.edit, Qt.Key.Key_BracketRight, Qt.KeyboardModifier.ControlModifier)
    assert window.edit.content_text() == '        one\n          two\nthree'
    QTest.keyClick(window.edit, Qt.Key.Key_BracketLeft, Qt.KeyboardModifier.ControlModifier)
    assert window.edit.content_text() == '    one\n      two\nthree'
    window.edit.undo()
    assert window.edit.content_text() == '        one\n          two\nthree'
    window.hide()


@pytest.mark.parametrize('rendered', [False, True])
def test_trailing_newline_stays_editable_but_does_not_transfer(app, rendered):
    window = EditorWindow()
    window.open_draft('hello')
    window.mode.setCurrentIndex(int(rendered))
    QTest.qWait(40)
    assert window.edit.toPlainText() == 'hello\n'
    assert window.payload()[2] == 'hello'
    window.edit.moveCursor(QTextCursor.MoveOperation.End)
    QTest.keyClicks(window.edit, 'second')
    assert window.edit.toPlainText() == 'hello\nsecond\n'
    assert not window.payload()[0].endswith('\n')
    assert window.payload()[2] == ('hello\nsecond' if rendered else 'hello second')
    if not rendered:
        assert window.payload()[0] == 'hello\nsecond'
    clean = QTextDocument(); clean.setHtml(window.payload()[1])
    assert clean.toPlainText() == window.payload()[2]
    window.edit.undo()
    QTest.qWait(20)
    assert window.edit.toPlainText().endswith('\n')
    window.edit.selectAll()
    QTest.keyClick(window.edit, Qt.Key.Key_Backspace)
    assert window.edit.toPlainText() == '\n'
    assert window.payload()[0] == '' and window.payload()[2] == ''
    window.hide()


def test_loaded_user_newlines_preserved_in_raw_payload(app):
    window = EditorWindow()
    window.open_draft('hello\n\n')
    assert window.edit.toPlainText() == 'hello\n\n\n'
    assert window.payload()[0] == 'hello\n\n'
    window.hide()
