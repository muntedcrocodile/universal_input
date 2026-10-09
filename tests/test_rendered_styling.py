# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
from PyQt6.QtTest import QTest

from universal_input.editor import EditorWindow
from universal_input.quotes import quote_bars


def foreground_at(document, word):
    cursor = document.find(word)
    assert not cursor.isNull()
    block = cursor.block()
    offset = cursor.selectionStart() - block.position()
    return next((span.format.foreground().color().name()
                 for span in block.layout().formats()
                 if span.start <= offset < span.start + span.length), None)


def test_rendered_code_highlights_languages_without_changing_prose_or_export(app):
    source = ('# Heading\n\n**Bold** and `inline` text.\n\n'
              '```python\n# 🦎 comment\ndef greet():\n    return "hello"\n```\n\n'
              '```javascript\nconst count = 42;\n```\n\n'
              '```unknown-language\nplain text\n```')
    window = EditorWindow()
    window.open_draft(source)
    window.mode.setCurrentIndex(1)
    html = window.edit.toHtml()
    QTest.qWait(100)
    document = window.edit.document()
    assert foreground_at(document, 'def') == '#007e00'
    assert foreground_at(document, '"hello"') == '#ce9178'
    assert foreground_at(document, 'const') == '#007e00'
    assert foreground_at(document, '42') == '#b5cea8'
    assert foreground_at(document, 'Bold') is None
    assert foreground_at(document, 'inline') is None
    assert foreground_at(document, 'plain text') is None
    assert window.edit.toHtml() == html
    assert window.draft_markdown() == source
    window.mode.setCurrentIndex(0)
    assert window.edit.content_text() == source


def test_rendered_highlighting_updates_for_language_edits_typing_and_undo(app):
    window = EditorWindow()
    window.open_draft('```text\nreturn 42\n```')
    window.mode.setCurrentIndex(1)
    QTest.qWait(100)
    assert foreground_at(window.edit.document(), 'return') == '#d4d4d4'
    header = window.code_blocks.headers[0]
    header.input.setFocus()
    header.input.selectAll()
    QTest.keyClicks(header.input, 'python')
    QTest.qWait(100)
    assert foreground_at(window.edit.document(), 'return') == '#007e00'
    window.edit.setTextCursor(window.edit.document().find('42'))
    window.edit.insertPlainText('"🦎"')
    QTest.qWait(100)
    assert foreground_at(window.edit.document(), '🦎') == '#ce9178'
    window.edit.undo()
    QTest.qWait(100)
    assert foreground_at(window.edit.document(), '42') == '#b5cea8'
    assert '```python\nreturn 42\n```' in window.draft_markdown()


def test_rendered_multiline_strings_keep_lexer_state(app):
    window = EditorWindow()
    window.mode.setCurrentIndex(1)
    window.open_draft('```python\nmessage = """first\n🦎 second\nthird"""\nreturn 42\n```')
    QTest.qWait(100)
    assert foreground_at(window.edit.document(), 'second') == '#ce9178'
    assert foreground_at(window.edit.document(), 'third') == '#ce9178'
    assert foreground_at(window.edit.document(), 'return') == '#007e00'


def test_quote_bars_are_painted_connected_and_nested_without_changing_text(app):
    source = '> First paragraph\n>\n> Second paragraph\n>\n> > Nested quote\n\nOrdinary text'
    window = EditorWindow()
    window.open_draft(source)
    assert list(quote_bars(window.edit)) == []
    window.mode.setCurrentIndex(1)
    app.processEvents()
    html = window.edit.toHtml()
    bars = list(quote_bars(window.edit))
    assert len(bars) == 4
    assert bars[0].bottom() == bars[1].top()
    assert bars[1].bottom() == bars[2].top()
    assert bars[3].left() > bars[2].left()
    assert bars[3].top() == bars[2].top()
    image = window.edit.viewport().grab().toImage()
    scale = image.devicePixelRatio()
    for bar in bars:
        point = bar.center() * scale
        assert image.pixelColor(round(point.x()), round(point.y())).name() == '#808080'
    assert window.edit.toHtml() == html
    assert window.draft_markdown() == source
    window.mode.setCurrentIndex(0)
    assert list(quote_bars(window.edit)) == []
    assert window.edit.content_text() == source


def test_quote_bars_follow_wrapping_scrolling_and_edits(app):
    window = EditorWindow()
    window.open_draft('> ' + 'A long quotation with several words. ' * 80 + '\n\nNormal')
    window.mode.setCurrentIndex(1)
    app.processEvents()
    window.edit.verticalScrollBar().setValue(0)
    initial = list(quote_bars(window.edit))[0]
    assert initial.height() > window.edit.fontMetrics().height() * 2
    window.edit.verticalScrollBar().setValue(30)
    scrolled = list(quote_bars(window.edit))[0]
    assert scrolled.top() == initial.top() - 30
    window.edit.clear()
    app.processEvents()
    assert list(quote_bars(window.edit)) == []
