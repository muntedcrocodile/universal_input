# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Native desktop visual language: translucent writing panel, quiet controls."""
from PyQt6.QtCore import Qt, QRect, QPoint, QSize
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPen, QPainter, QPolygon
from PyQt6.QtWidgets import QWidget, QStyledItemDelegate, QStyle, QComboBox, QSizeGrip, QToolButton, QStyleOptionToolButton


class ModeChoiceDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        painter.save()
        painter.setPen(QColor("#969696"))
        painter.drawText(option.rect.adjusted(0, 0, -8, 0), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self.parent().mode_keys[index.row()])
        painter.restore()


class ModeComboBox(QComboBox):
    def __init__(self):
        super().__init__()
        self.shortcut = ""
        self.mode_keys = ["", ""]
        self.setItemDelegate(ModeChoiceDelegate(self))

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(QFont("Lato", 8))
        painter.setPen(QColor("#969696"))
        painter.drawText(self.rect().adjusted(0, 0, -31, 0), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self.shortcut)
        painter.setPen(QPen(QColor("#cccccc"), 1.5))
        x, y = self.width() - 15, self.height() // 2
        painter.drawPolyline(QPolygon([QPoint(x - 4, y - 2), QPoint(x, y + 2), QPoint(x + 4, y - 2)]))


class QuickInsertButton(QToolButton):
    def __init__(self, text, shortcut):
        super().__init__()
        self.setText(text)
        self.shortcut = shortcut
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip(f"Insert {text.lower()}\n{shortcut}".strip())

    def sizeHint(self):
        width = max(QFontMetrics(QFont("Lato", 10)).horizontalAdvance(self.text()), QFontMetrics(QFont("Lato", 8)).horizontalAdvance(self.shortcut))
        return QSize(width + 20, 44)

    def paintEvent(self, event):
        option = QStyleOptionToolButton()
        self.initStyleOption(option)
        option.text = ""
        painter = QPainter(self)
        self.style().drawComplexControl(QStyle.ComplexControl.CC_ToolButton, option, painter, self)
        painter.setPen(QColor("#d4d4d4"))
        painter.setFont(QFont("Lato", 10))
        painter.drawText(self.rect().adjusted(0, 3, 0, -18), Qt.AlignmentFlag.AlignCenter, self.text())
        painter.setPen(QColor("#969696"))
        painter.setFont(QFont("Lato", 8))
        painter.drawText(self.rect().adjusted(0, 23, 0, -3), Qt.AlignmentFlag.AlignCenter, self.shortcut)


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
            painter.setBrush(QColor("#007e00" if active else "#3c3c3c"))
            painter.drawRoundedRect(rect, 5, 5)
        row = index.data(Qt.ItemDataRole.UserRole)
        painter.setFont(QFont("Lato", 10))
        if row is None:
            painter.setPen(QColor("#969696"))
            painter.drawText(rect.adjusted(8, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter, index.data())
        else:
            key = QRect(rect.left() + 6, rect.center().y() - 9, 22, 19)
            painter.setPen(QPen(QColor("#808080" if active else "#454545"), 1))
            painter.setBrush(QColor("#007e00" if active else "#333333"))
            painter.drawRoundedRect(key, 3, 3)
            painter.setPen(QColor("#d4d4d4" if active else "#969696"))
            painter.drawText(key, Qt.AlignmentFlag.AlignCenter, str(row + 1))
            text_rect = rect.adjusted(40, 0, -8, 0)
            painter.setPen(QColor("#d4d4d4"))
            text = option.fontMetrics.elidedText(index.data(), Qt.TextElideMode.ElideRight, text_rect.width())
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, text)
        painter.restore()


STYLESHEET = """
QMainWindow { background: transparent; }
QWidget { color: #d4d4d4; font-family: 'Lato'; font-size: 13px; }
QWidget#panel { background: rgba(37, 37, 38, 238); border: 1px solid #454545; border-radius: 16px; }
QWidget#commandBar { background: transparent; }
QScrollArea#quickInsertScroll, QWidget#quickInsertViewport, QWidget#quickInsertButtons { background: transparent; border: none; }
QLabel { background: transparent; border: none; }
QLabel#brand { color: #969696; font-size: 12px; }
QLabel#hint, QLabel#status, QLabel#wordCount { color: #969696; font-size: 12px; }
QTextEdit { background: rgba(30, 30, 30, 224); border: 1px solid #454545; border-radius: 9px; padding: 18px; color: #d4d4d4; selection-background-color: #007e00; selection-color: white; }
QTextEdit:focus { border-color: #007e00; }
QToolButton { background: transparent; border: 1px solid transparent; border-radius: 5px; padding: 6px 8px; color: #cccccc; }
QToolButton:hover { background: #3e3e42; color: white; }
QToolButton:focus { border-color: #007e00; }
QToolButton::menu-indicator { image: none; }
QComboBox { background: #3c3c3c; border: 1px solid #5a5a5a; border-radius: 6px; padding: 7px 24px 7px 10px; min-width: 142px; }
QComboBox:focus { border-color: #007e00; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: #252526; color: #d4d4d4; selection-background-color: #007e00; border: 1px solid #454545; }
QPushButton { background: transparent; border: 1px solid #454545; border-radius: 6px; padding: 8px 13px; }
QPushButton:hover { background: #3e3e42; }
QPushButton:focus { border-color: #007e00; }
QPushButton#primaryAction { background: #007e00; border: 1px solid #007e00; color: white; font-weight: 600; }
QPushButton#primaryAction:hover { background: #0a8c0a; }
QPushButton#escapeAction { color: #969696; border-color: transparent; }
QFrame#historyPanel { background: transparent; border: none; }
QListWidget { background: transparent; border: none; outline: none; }
QMenu, QDialog { background: #252526; color: #d4d4d4; }
QMenu { border: 1px solid #454545; padding: 5px; }
QMenu::item { padding: 7px 18px; border-radius: 4px; }
QMenu::item:selected { background: #007e00; }
QSpinBox { background: #1e1e1e; color: #d4d4d4; padding: 6px; border: 1px solid #454545; border-radius: 4px; }
QToolTip { background: #252526; color: #d4d4d4; border: 1px solid #454545; padding: 5px; }
QScrollBar:vertical { background: transparent; width: 7px; margin: 2px; }
QScrollBar:horizontal { background: transparent; height: 7px; margin: 2px; }
QScrollBar::handle { background: #5a5a5a; border-radius: 3px; min-height: 22px; min-width: 22px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QSizeGrip { background: transparent; width: 12px; height: 12px; }
"""
