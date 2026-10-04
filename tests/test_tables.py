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
        assert not window.isVisible()
        assert not window.table_picker.isVisible()
        assert QApplication.activeModalWidget() is None
        assert QApplication.activePopupWidget() is None
        assert window.edit.toPlainText() == "kept draft"
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
    assert "still typing" in window.edit.toPlainText()
    window.hide()
