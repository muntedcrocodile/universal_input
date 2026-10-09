# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
from PyQt6.QtGui import QTextTable
from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt
import pytest

from universal_input.editor import EditorWindow


def first_table(window):
    return next(frame for frame in window.edit.document().rootFrame().childFrames() if isinstance(frame, QTextTable))


def test_raw_table_and_rendered_roundtrip(app):
    window = EditorWindow()
    window.insert_table(3, 2)
    assert "| Column 1 | Column 2 |" in window.edit.content_text()
    original = window.edit.content_text()
    window.mode.setCurrentIndex(1)
    table = first_table(window)
    assert (table.rows(), table.columns()) == (3, 2)
    window.mode.setCurrentIndex(0)
    assert window.edit.content_text() == original


def test_rendered_table_hover_buttons_add_rows_and_columns(app):
    window = EditorWindow()
    window.open_draft("")
    window.resize(1280, 600)
    window.mode.setCurrentIndex(1)
    window.insert_table(3, 3)
    app.processEvents()
    table = first_table(window)
    controls = window.table_controls
    border = table.cellAt(1, 1).format().toTableCellFormat()
    assert border.leftBorder() > 0
    assert 0 < border.leftBorderBrush().color().alphaF() < 0.15
    point = window.edit.cursorRect(table.cellAt(1, 1).firstCursorPosition()).center()
    controls.update_at(point)
    assert controls.buttons[0].isVisible()
    assert controls.buttons[1].isVisible()
    assert controls.row_index == 2
    QTest.mouseMove(controls.buttons[0], controls.buttons[0].rect().center())
    QTest.mouseClick(controls.buttons[0], Qt.MouseButton.LeftButton)
    QTest.qWait(60)
    assert table.rows() == 4
    assert table.cellAt(2, 1).format().toTableCellFormat().leftBorder() > 0
    point = window.edit.cursorRect(table.cellAt(1, 1).firstCursorPosition()).center()
    controls.update_at(point)
    assert controls.column_index == 2
    QTest.mouseMove(controls.buttons[1], controls.buttons[1].rect().center())
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


def test_table_grid_click_selects_size_without_a_native_popup(app):
    from PyQt6.QtCore import QPoint
    from PyQt6.QtWidgets import QApplication
    window = EditorWindow()
    window.open_draft("")
    app.processEvents()
    QTest.mouseClick(window.table_button, Qt.MouseButton.LeftButton)
    QTest.qWait(60)
    picker = window.table_picker
    assert picker.isVisible()
    assert not picker.isWindow()
    assert QApplication.activeModalWidget() is None
    assert QApplication.activePopupWidget() is None
    point = QPoint(3 * picker.grid.cell_size + 12, 2 * picker.grid.cell_size + 12)
    QTest.mouseMove(picker.grid, point)
    QTest.qWait(60)
    assert picker.label.text() == "4 columns × 3 rows"
    QTest.mouseClick(picker.grid, Qt.MouseButton.LeftButton, pos=point)
    QTest.qWait(60)
    assert not picker.isVisible()
    window.mode.setCurrentIndex(1)
    assert (first_table(window).rows(), first_table(window).columns()) == (3, 4)
    window.hide()


def test_table_grid_keyboard_escape_and_reopen(app):
    from PyQt6.QtCore import QPoint
    from PyQt6.QtWidgets import QApplication
    window = EditorWindow()
    window.cancelled.connect(window.hide)
    window.open_draft("kept draft")
    app.processEvents()
    for _ in range(3):
        window.toggle_table_picker()
        QTest.qWait(30)
        QTest.keyClick(window.table_picker.grid, Qt.Key.Key_Escape)
        QTest.qWait(60)
        assert window.isVisible()
        assert not window.table_picker.isVisible()
        QTest.keyClick(window.edit, Qt.Key.Key_Escape)
        assert not window.isVisible()
        assert not window.table_picker.isVisible()
        assert QApplication.activeModalWidget() is None
        assert QApplication.activePopupWidget() is None
        assert window.edit.content_text() == "kept draft"
        window.show()
        window.activateWindow()
        window.edit.setFocus()
        app.processEvents()
    window.edit.clear()
    window.toggle_table_picker()
    QTest.qWait(30)
    QTest.keyClick(window.table_picker.grid, Qt.Key.Key_Right)
    QTest.keyClick(window.table_picker.grid, Qt.Key.Key_Down)
    QTest.keyClick(window.table_picker.grid, Qt.Key.Key_Return)
    QTest.qWait(60)
    assert not window.table_picker.isVisible()
    window.mode.setCurrentIndex(1)
    assert (first_table(window).rows(), first_table(window).columns()) == (3, 3)
    window.toggle_table_picker()
    QTest.mouseClick(window.edit.viewport(), Qt.MouseButton.LeftButton,
                     pos=QPoint(window.edit.viewport().width() - 15, window.edit.viewport().height() - 15))
    QTest.qWait(60)
    assert not window.table_picker.isVisible()
    QTest.keyClicks(window.edit, "still typing")
    QTest.qWait(60)
    assert "still typing" in window.edit.content_text()
    window.hide()


def test_hover_path_reaches_row_button_and_keeps_boundary(app):
    from PyQt6.QtCore import QPoint
    window = EditorWindow()
    window.open_draft("")
    window.resize(1000, 650)
    window.mode.setCurrentIndex(1)
    window.insert_table(3, 3)
    app.processEvents()
    table = first_table(window)
    controls = window.table_controls
    viewport = window.edit.viewport()
    start = window.edit.cursorRect(table.cellAt(1, 2).firstCursorPosition()).center()
    QTest.mouseMove(viewport, start)
    QTest.qWait(30)
    controls.update_at(start)
    button = controls.buttons[0]
    target = button.geometry().center()
    for step in range(1, 21):
        point = QPoint(start.x() + (target.x() - start.x()) * step // 20,
                       start.y() + (target.y() - start.y()) * step // 20)
        QTest.mouseMove(viewport, point)
        controls.update_at(point)
        QTest.qWait(5)
        assert button.isVisible()
        assert controls.row_index == 2
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert table.rows() == 4
    window.hide()


@pytest.mark.parametrize('rendered', [False, True])
@pytest.mark.parametrize('keyboard', [False, True])
def test_custom_table_dimensions_use_entry_popup(app, rendered, keyboard):
    window = EditorWindow()
    window.open_draft('before replace after')
    QTest.qWait(30)
    window.mode.setCurrentIndex(int(rendered))
    window.edit.setTextCursor(window.edit.document().find('replace'))
    window.toggle_table_picker()
    if keyboard:
        QTest.keyClick(window.table_picker.grid, Qt.Key.Key_C)
    else:
        QTest.mouseClick(window.table_picker.custom_button, Qt.MouseButton.LeftButton)
    prompt = window.number_prompt
    assert not window.table_picker.isVisible()
    assert prompt.isVisible() and prompt.input.hasFocus() and not prompt.isWindow()
    QTest.keyClicks(prompt.input, '20')
    QTest.keyClick(prompt.input, Qt.Key.Key_Return)
    assert prompt.isVisible() and prompt.title.text() == 'Table columns'
    QTest.keyClicks(prompt.input, '12')
    QTest.keyClick(prompt.input, Qt.Key.Key_Return)
    assert not prompt.isVisible() and window.edit.hasFocus()
    if rendered:
        table = first_table(window)
        assert (table.rows(), table.columns()) == (20, 12)
    else:
        table_lines = [line for line in window.edit.content_text().splitlines() if line.startswith('|')]
        assert len(table_lines) == 21  # Header, separator, and 19 body rows.
        assert all(line.count('|') == 13 for line in table_lines)
    assert 'before' in window.draft_markdown() and 'after' in window.draft_markdown()
    window.edit.undo()
    assert window.edit.content_text() == 'before replace after'


def test_custom_table_validation_and_escape_do_not_insert(app):
    window = EditorWindow()
    window.open_draft('kept draft')
    QTest.qWait(30)
    window.toggle_table_picker()
    window.table_picker.choose_custom()
    prompt = window.number_prompt
    prompt.input.setText('1001')
    prompt.accept()
    assert prompt.command == 'table_rows' and prompt.isVisible()
    prompt.input.setText('1000')
    prompt.accept()
    assert prompt.command == 'table_columns' and prompt.maximum == 10
    prompt.input.setText('11')
    prompt.accept()
    assert prompt.isVisible() and '1 to 10' in prompt.hint.text()
    QTest.keyClick(prompt.input, Qt.Key.Key_Escape)
    assert not prompt.isVisible() and window.isVisible()
    assert window.edit.content_text() == 'kept draft'


def test_highlighting_refresh_keeps_table_hover_controls(app):
    window = EditorWindow()
    window.open_draft("")
    window.mode.setCurrentIndex(1)
    window.insert_table(3, 3)
    app.processEvents()
    table = first_table(window)
    point = window.edit.cursorRect(table.cellAt(1, 1).firstCursorPosition()).center()
    window.table_controls.update_at(point)
    assert window.table_controls.buttons[0].isVisible()
    window.highlighter.refresh()
    assert window.table_controls.buttons[0].isVisible()
    assert window.table_controls.row_index == 2
    window.edit.insertPlainText("changed")
    assert not window.table_controls.buttons[0].isVisible()
