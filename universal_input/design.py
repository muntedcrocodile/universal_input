"""Native desktop visual language: translucent writing panel, quiet controls."""
from PyQt6.QtCore import Qt, QRect, QPoint, QSize
from PyQt6.QtGui import QColor, QFont, QPen, QPainter, QPolygon
from PyQt6.QtWidgets import QWidget, QStyledItemDelegate, QStyle, QComboBox, QSizeGrip


class ModeComboBox(QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#cbd4c9"), 1.5))
        x, y = self.width() - 15, self.height() // 2
        painter.drawPolyline(QPolygon([QPoint(x - 4, y - 2), QPoint(x, y + 2), QPoint(x + 4, y - 2)]))


class DragBar(QWidget):
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.offset = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            handle = self.window().windowHandle()
            unmanaged = bool(self.window().windowFlags() & Qt.WindowType.X11BypassWindowManagerHint)
            if handle and not unmanaged and handle.startSystemMove():
                self.offset = None
            event.accept()

    def mouseMoveEvent(self, event):
        offset = getattr(self, "offset", None)
        if offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - offset)

    def mouseReleaseEvent(self, event):
        self.offset = None


class ResizeGrip(QSizeGrip):
    """Resize directly: an unmanaged window cannot use i3's resize protocol."""
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.globalPosition().toPoint()
            self.initial_size = self.window().size()
            event.accept()

    def mouseMoveEvent(self, event):
        origin = getattr(self, "origin", None)
        if origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - origin
            size = self.initial_size + QSize(delta.x(), delta.y())
            self.window().resize(size.expandedTo(self.window().minimumSizeHint()))
            event.accept()

    def mouseReleaseEvent(self, event):
        self.origin = None
        event.accept()


class HistoryDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        painter.save()
        rect = option.rect.adjusted(0, 2, -2, -2)
        active = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if active or hover:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#007e00" if active else "#303a32"))
            painter.drawRoundedRect(rect, 5, 5)
        row = index.data(Qt.ItemDataRole.UserRole)
        painter.setFont(QFont("Lato", 10))
        if row is None:
            painter.setPen(QColor("#abb5aa"))
            painter.drawText(rect.adjusted(8, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter, index.data())
        else:
            key = QRect(rect.left() + 6, rect.center().y() - 9, 22, 19)
            painter.setPen(QPen(QColor("#627162" if active else "#414d43"), 1))
            painter.setBrush(QColor("#246d29" if active else "#262f28"))
            painter.drawRoundedRect(key, 3, 3)
            painter.setPen(QColor("#f0f2ec" if active else "#abb5aa"))
            painter.drawText(key, Qt.AlignmentFlag.AlignCenter, str(row + 1))
            text_rect = rect.adjusted(40, 0, -8, 0)
            painter.setPen(QColor("#f0f2ec"))
            text = option.fontMetrics.elidedText(index.data(), Qt.TextElideMode.ElideRight, text_rect.width())
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, text)
        painter.restore()


STYLESHEET = """
QMainWindow { background: transparent; }
QWidget { color: #f0f2ec; font-family: 'Lato'; font-size: 13px; }
QWidget#panel { background: rgba(32, 38, 34, 238); border: 1px solid #414d43; border-radius: 16px; }
QWidget#commandBar { background: transparent; }
QLabel { background: transparent; border: none; }
QLabel#brand { color: #abb5aa; font-size: 12px; }
QLabel#hint, QLabel#status, QLabel#wordCount { color: #abb5aa; font-size: 12px; }
QTextEdit { background: rgba(23, 29, 25, 224); border: 1px solid #414d43; border-radius: 9px; padding: 18px; color: #f0f2ec; selection-background-color: #007e00; selection-color: white; }
QTextEdit:focus { border-color: #667867; }
QToolButton { background: transparent; border: 1px solid transparent; border-radius: 5px; padding: 6px 8px; color: #cbd4c9; }
QToolButton:hover { background: #354237; color: white; }
QToolButton:focus { border-color: #007e00; }
QToolButton::menu-indicator { image: none; }
QComboBox { background: #303a32; border: 1px solid #536254; border-radius: 6px; padding: 7px 24px 7px 10px; min-width: 142px; }
QComboBox:focus { border-color: #007e00; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #202622; color: #f0f2ec; selection-background-color: #007e00; border: 1px solid #414d43; }
QPushButton { background: transparent; border: 1px solid #414d43; border-radius: 6px; padding: 8px 13px; }
QPushButton:hover { background: #354237; }
QPushButton:focus { border-color: #007e00; }
QPushButton#primaryAction { background: #007e00; border: 1px solid #007e00; color: white; font-weight: 600; }
QPushButton#primaryAction:hover { background: #0a8c0a; }
QPushButton#escapeAction { color: #abb5aa; border-color: transparent; }
QFrame#historyPanel { background: transparent; border: none; }
QListWidget { background: transparent; border: none; outline: none; }
QMenu, QDialog { background: #202622; color: #f0f2ec; }
QMenu { border: 1px solid #414d43; padding: 5px; }
QMenu::item { padding: 7px 18px; border-radius: 4px; }
QMenu::item:selected { background: #007e00; }
QSpinBox { background: #171d19; color: #f0f2ec; padding: 6px; border: 1px solid #414d43; border-radius: 4px; }
QToolTip { background: #202622; color: #f0f2ec; border: 1px solid #414d43; padding: 5px; }
QScrollBar:vertical { background: transparent; width: 7px; margin: 2px; }
QScrollBar:horizontal { background: transparent; height: 7px; margin: 2px; }
QScrollBar::handle { background: #536254; border-radius: 3px; min-height: 22px; min-width: 22px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QSizeGrip { background: transparent; width: 12px; height: 12px; }
"""
