"""An in-window table grid: no modal loop, native popup, or input grab."""
from PyQt6.QtCore import QEvent, QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout, QWidget


class TableGrid(QWidget):
    chosen = pyqtSignal(int, int)
    changed = pyqtSignal(int, int)
    escape_requested = pyqtSignal()
    columns = 10
    rows = 8
    cell_size = 24

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_rows = self.selected_columns = 2
        self.setFixedSize(self.columns * self.cell_size, self.rows * self.cell_size)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Table size grid")
        self.setAccessibleDescription("Use arrow keys to choose columns and rows, then Enter to insert.")

    def select(self, rows, columns):
        self.selected_rows = max(1, min(self.rows, rows))
        self.selected_columns = max(1, min(self.columns, columns))
        self.changed.emit(self.selected_rows, self.selected_columns)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        for row in range(self.rows):
            for column in range(self.columns):
                chosen = row < self.selected_rows and column < self.selected_columns
                painter.setPen(QPen(QColor("#007e00" if chosen else "#536254"), 1))
                painter.setBrush(QColor("#007e00" if chosen else "#171d19"))
                painter.drawRoundedRect(QRect(column * self.cell_size + 2, row * self.cell_size + 2, self.cell_size - 5, self.cell_size - 5), 2, 2)

    def mouseMoveEvent(self, event):
        point = event.position().toPoint()
        if self.rect().contains(point):
            self.select(point.y() // self.cell_size + 1, point.x() // self.cell_size + 1)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.mouseMoveEvent(event)
            self.chosen.emit(self.selected_rows, self.selected_columns)

    def event(self, event):
        if event.type() == QEvent.Type.ShortcutOverride and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape, Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        row, column = self.selected_rows, self.selected_columns
        if event.key() == Qt.Key.Key_Left:
            self.select(row, column - 1)
        elif event.key() == Qt.Key.Key_Right:
            self.select(row, column + 1)
        elif event.key() == Qt.Key.Key_Up:
            self.select(row - 1, column)
        elif event.key() == Qt.Key.Key_Down:
            self.select(row + 1, column)
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.chosen.emit(row, column)
        elif event.key() == Qt.Key.Key_Escape:
            self.escape_requested.emit()
        else:
            super().keyPressEvent(event)


class TablePicker(QFrame):
    chosen = pyqtSignal(int, int)
    escape_requested = pyqtSignal()

    def __init__(self, parent, anchor):
        super().__init__(parent)
        self.anchor = anchor
        self.setObjectName("tablePicker")
        self.setStyleSheet("QFrame#tablePicker { background: #202622; border: 1px solid #667867; border-radius: 8px; } QLabel { border: none; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        self.label = QLabel()
        self.grid = TableGrid(self)
        hint = QLabel("Arrow keys choose. Enter inserts.")
        hint.setObjectName("hint")
        layout.addWidget(self.label)
        layout.addWidget(self.grid)
        layout.addWidget(hint)
        self.grid.changed.connect(self.describe)
        self.grid.chosen.connect(self.choose)
        self.grid.escape_requested.connect(self.escape_requested)
        self.hide()

    def describe(self, rows, columns):
        self.label.setText(f"{columns} {'column' if columns == 1 else 'columns'} × {rows} {'row' if rows == 1 else 'rows'}")

    def open(self):
        self.grid.select(2, 2)
        self.adjustSize()
        point = self.anchor.mapTo(self.parentWidget(), QPoint(0, self.anchor.height() + 6))
        self.move(max(0, min(point.x(), self.parentWidget().width() - self.width())), max(0, min(point.y(), self.parentWidget().height() - self.height())))
        self.show()
        self.raise_()
        QApplication.instance().installEventFilter(self)
        self.grid.setFocus(Qt.FocusReason.PopupFocusReason)

    def choose(self, rows, columns):
        self.hide()
        self.chosen.emit(rows, columns)

    def eventFilter(self, obj, event):
        if self.isVisible() and event.type() == QEvent.Type.MouseButtonPress:
            if isinstance(obj, QWidget) and obj != self.anchor and obj != self and not self.isAncestorOf(obj):
                self.hide()
        return False

    def hideEvent(self, event):
        QApplication.instance().removeEventFilter(self)
        super().hideEvent(event)
