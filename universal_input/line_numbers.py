"""A quiet, right-aligned gutter for the editor's logical text lines."""
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QPainter, QFontMetrics
from PyQt6.QtWidgets import QWidget


class LineNumbers(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAccessibleName('Line numbers')
        editor.document().blockCountChanged.connect(self.refresh)
        editor.document().documentLayout().documentSizeChanged.connect(self.refresh)
        editor.cursorPositionChanged.connect(self.update)
        editor.verticalScrollBar().valueChanged.connect(self.update)
        self.refresh()

    def refresh(self, *_):
        editor = self.editor
        self.setFont(editor.font())
        width = QFontMetrics(editor.font()).horizontalAdvance('9' * max(2, len(str(editor.document().blockCount())))) + 22
        if editor.viewportMargins().left() != width:
            editor.setViewportMargins(width, 0, 0, 0)
        viewport = editor.viewport().geometry()
        self.setGeometry(viewport.x() - width, viewport.y(), width, viewport.height())
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setFont(self.editor.font())
        document = self.editor.document()
        layout = document.documentLayout()
        scroll = self.editor.verticalScrollBar().value()
        active = self.editor.textCursor().blockNumber()
        block = document.begin()
        rows = {}
        while block.isValid():
            rect = layout.blockBoundingRect(block)
            top = rect.top() - scroll
            if top > self.height():
                break
            text_layout = block.layout()
            if rect.bottom() >= scroll and text_layout.lineCount():
                line = text_layout.lineAt(0)
                y = top + line.y()
                # Table cells share a row. Show the first cell's number unless
                # another cell on that row contains the cursor.
                row = round(y)
                if row not in rows or block.blockNumber() == active:
                    rows[row] = (y, line.height(), block.blockNumber())
            block = block.next()
        for y, height, number in rows.values():
            painter.setPen(QColor('#cccccc' if number == active else '#858585'))
            painter.drawText(QRectF(0, y, self.width() - 12, height), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(number + 1))
