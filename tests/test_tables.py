from PyQt6.QtGui import QTextTable
from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt

from universal_input.editor import EditorWindow


def first_table(window):
    return next(frame for frame in window.edit.document().rootFrame().childFrames() if isinstance(frame, QTextTable))


def test_raw_table_and_rendered_roundtrip(app):
    window = EditorWindow()
    window.insert_table(3, 2)
    assert "| Column 1 | Column 2 |" in window.edit.toPlainText()
    original = window.edit.toPlainText()
    window.mode.setCurrentIndex(1)
    table = first_table(window)
    assert (table.rows(), table.columns()) == (3, 2)
    window.mode.setCurrentIndex(0)
    assert window.edit.toPlainText() == original


def test_rendered_table_hover_buttons_add_rows_and_columns(app):
    window = EditorWindow()
    window.open_draft("")
    window.resize(1280, 600)
    window.mode.setCurrentIndex(1)
    window.insert_table(3, 3)
    app.processEvents()
    table = first_table(window)
    controls = window.table_controls
    point = window.edit.cursorRect(table.cellAt(1, 1).firstCursorPosition()).center()
    controls.update_at(point)
    assert controls.buttons[0].isVisible()
    assert controls.buttons[1].isVisible()
    assert controls.row_index == 2
    QTest.mouseClick(controls.buttons[0], Qt.MouseButton.LeftButton)
    QTest.qWait(60)
    assert table.rows() == 4
    point = window.edit.cursorRect(table.cellAt(1, 1).firstCursorPosition()).center()
    controls.update_at(point)
    assert controls.column_index == 2
    QTest.mouseClick(controls.buttons[1], Qt.MouseButton.LeftButton)
    QTest.qWait(60)
    assert table.columns() == 4
    markdown, html, _ = window.payload()
    assert "Column 1" in markdown
    assert "<table" in html
    window.mode.setCurrentIndex(0)
    assert not controls.buttons[0].isVisible()
    window.mode.setCurrentIndex(1)
    assert (first_table(window).rows(), first_table(window).columns()) == (4, 4)
    window.hide()


def test_rendered_table_edit_is_undoable(app):
    window = EditorWindow()
    window.mode.setCurrentIndex(1)
    window.insert_table(2, 2)
    table = first_table(window)
    window.table_controls.table = table
    window.table_controls.row_index = 1
    window.table_controls.add_row()
    assert table.rows() == 3
    window.edit.undo()
    assert first_table(window).rows() == 2
