# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from PyQt6.QtGui import QTextDocument, QTextCursor

from universal_input.editor import EditorWindow
from universal_input.markdown import export_markdown


LONG = "This is a long paragraph which should wrap visually without gaining real line breaks. " * 5


def test_rich_import_does_not_add_newlines(app):
    window = EditorWindow()
    window.open_draft(LONG, rich=True, html=f"<p>{LONG}</p>")
    assert window.edit.content_text() == LONG
    assert "\n" not in window.draft_markdown()


def test_rendered_edits_and_raw_roundtrip_do_not_add_newlines(app):
    window = EditorWindow()
    window.open_draft(LONG)
    window.mode.setCurrentIndex(1)
    window.edit.moveCursor(QTextCursor.MoveOperation.Start)
    window.edit.insertPlainText("Updated: ")
    window.mode.setCurrentIndex(0)
    assert window.edit.content_text() == "Updated: " + LONG.rstrip()


@pytest.mark.parametrize("html,expected", [
    (f"<p>{LONG}</p><p>Another paragraph.</p>", LONG + "\n\nAnother paragraph."),
    (f"<p>{LONG}<br>Deliberate break.</p>", LONG + "  \nDeliberate break."),
    (f"<ul><li>{LONG}</li><li>Second item</li></ul>", "- " + LONG + "\n- Second item"),
    (f"<blockquote>{LONG}</blockquote>", "> " + LONG),
    (f"<ul><li>{LONG}<br>Same item</li></ul>", "- " + LONG + "  \n  Same item"),
    (f"<p>{LONG}<b>bold</b>adjacent <i>italic</i></p>", LONG + "**bold**adjacent *italic*"),
    ("<p>Private chars \ue000 \ue001 and 🦎 remain.</p>", "Private chars \ue000 \ue001 and 🦎 remain."),
])
def test_unwrapped_export_preserves_structure_and_formatting(app, html, expected):
    document = QTextDocument()
    document.setHtml(html)
    before = document.toHtml()
    assert export_markdown(document) == expected
    assert document.toHtml() == before
    restored = QTextDocument()
    restored.setMarkdown(expected)
    assert [line.rstrip() for line in restored.toPlainText().splitlines()] == [line.rstrip() for line in document.toPlainText().splitlines()]


def test_code_and_table_lines_are_preserved(app):
    source = "```text\n" + LONG + "\nnext\n```\n\nA table follows.\n\n| One | Two |\n| --- | --- |\n| first | second |"
    document = QTextDocument()
    document.setMarkdown(source)
    result = export_markdown(document)
    assert "```text\n" + LONG + "\nnext\n```" in result
    restored = QTextDocument()
    restored.setMarkdown(result)
    assert restored.toPlainText().strip() == document.toPlainText().strip()
