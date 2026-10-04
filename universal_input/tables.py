"""Word-style table insertion guides inside the rendered draft."""
from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QFrame, QToolButton


class TableControls(QObject):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.table = None
        self.row_index = self.column_index = 0
        self.buttons = []
        self.lines = []
        editor.setMouseTracking(True)
        editor.viewport().setMouseTracking(True)
        editor.viewport().installEventFilter(self)
        for label, action in (("Add row here", self.add_row), ("Add column here", self.add_column)):
            button = QToolButton(editor.viewport())
            button.setText("+")
            button.setToolTip(label)
            button.setAccessibleName(label)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setStyleSheet("QToolButton { background: #007e00; color: white; border: none; border-radius: 10px; padding: 0px; font-family: Lato; font-size: 18px; font-weight: bold; }")
            button.setFixedSize(20, 20)
            button.clicked.connect(action)
            line = QFrame(editor.viewport())
            line.setStyleSheet("background: #007e00;")
            line.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.buttons.append(button)
            self.lines.append(line)
        editor.verticalScrollBar().valueChanged.connect(self.hide)
        editor.horizontalScrollBar().valueChanged.connect(self.hide)
        editor.textChanged.connect(self.hide)
        self.hide()

    def hide(self, *_):
        self.table = None
        for widget in self.buttons + self.lines:
            widget.hide()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseMove:
            self.update_at(event.position().toPoint())
        elif event.type() in (QEvent.Type.Leave, QEvent.Type.Resize):
            self.hide()
        return False

    def update_at(self, point):
        if not self.editor.rich:
            self.hide()
            return
        cursor = self.editor.cursorForPosition(point)
        table = cursor.currentTable()
        if table is None:
            self.hide()
            return
        layout = self.editor.document().documentLayout()
        dx, dy = -self.editor.horizontalScrollBar().value(), -self.editor.verticalScrollBar().value()
        rect = layout.frameBoundingRect(table).translated(dx, dy)
        if not rect.adjusted(-12, -12, 24, 12).contains(point.toPointF()):
            self.hide()
            return
        cell = table.cellAt(cursor)
        if not cell.isValid():
            self.hide()
            return
        first = layout.blockBoundingRect(cell.firstCursorPosition().block()).translated(dx, dy)
        last = layout.blockBoundingRect(cell.lastCursorPosition().block()).translated(dx, dy)
        padding = table.format().cellPadding() + table.format().cellSpacing() / 2 + table.format().border()
        self.table = table
        self.row_index = cell.row() + cell.rowSpan()
        self.column_index = cell.column() + cell.columnSpan()
        row_y = min(rect.bottom(), last.bottom() + padding)
        column_x = min(rect.right(), first.right() + padding)
        if cell.row() == 0 and point.y() < first.top() + 3:
            self.row_index, row_y = 0, rect.top()
        if cell.column() == 0 and point.x() < first.left() + 3:
            self.column_index, column_x = 0, rect.left()
        self.lines[0].setGeometry(int(rect.left()), int(row_y), max(1, int(rect.width())), 2)
        self.lines[1].setGeometry(int(column_x), int(rect.top()), 2, max(1, int(rect.height())))
        viewport = self.editor.viewport()
        self.buttons[0].move(min(viewport.width() - 22, int(rect.right()) + 2), max(0, min(viewport.height() - 22, int(row_y) - 9)))
        self.buttons[1].move(max(0, min(viewport.width() - 22, int(column_x) - 9)), max(0, int(rect.top()) - 22))
        for widget in self.lines + self.buttons:
            widget.show()
            widget.raise_()

    def add_row(self):
        if self.table is None:
            return
        table, index = self.table, self.row_index
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        table.insertRows(index, 1)
        cursor.endEditBlock()
        self.editor.setTextCursor(table.cellAt(index, 0).firstCursorPosition())
        self.editor.setFocus()
        self.hide()

    def add_column(self):
        if self.table is None:
            return
        table, index = self.table, self.column_index
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        table.insertColumns(index, 1)
        cursor.endEditBlock()
        self.editor.setTextCursor(table.cellAt(0, index).firstCursorPosition())
        self.editor.setFocus()
        self.hide()
