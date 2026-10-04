# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Persistent language headers and visual containers for rendered code blocks."""
from PyQt6.QtCore import QObject, QEvent, QTimer, Qt, QRegularExpression, QRectF
from PyQt6.QtGui import QColor, QPen, QTextCursor, QTextFormat, QTextBlockFormat, QRegularExpressionValidator
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit

from .navigation import rendered_parts, Part
from .shortcuts import label

CHROME = int(QTextFormat.Property.UserProperty) + 20
ROOT_CHROME = CHROME + 1
HEADER_HEIGHT = 32
PADDING = 10


def strip_code_chrome(document):
    frame = document.rootFrame()
    fmt = frame.frameFormat()
    if fmt.hasProperty(ROOT_CHROME):
        fmt.setTopMargin(float(fmt.property(ROOT_CHROME)))
        fmt.clearProperty(ROOT_CHROME)
        frame.setFrameFormat(fmt)
    block = document.begin()
    while block.isValid():
        fmt = block.blockFormat()
        original = fmt.property(CHROME)
        if original is not None:
            original = [float(value) for value in original.split(',')]
            fmt.setTopMargin(original[0])
            fmt.setBottomMargin(original[1])
            fmt.setLeftMargin(original[2])
            fmt.setRightMargin(original[3])
            fmt.clearProperty(CHROME)
            QTextCursor(block).setBlockFormat(fmt)
        block = block.next()


class CodeHeader(QFrame):
    def __init__(self, controls, part):
        super().__init__(controls.editor.viewport())
        self.controls = controls
        self.first_block = controls.editor.document().findBlock(part.start)
        self.part = part
        self.setObjectName('codeHeader')
        self.setStyleSheet('QFrame#codeHeader { background: #252526; border: none; border-bottom: 1px solid #454545; } QLineEdit { background: transparent; color: #d4d4d4; border: 1px solid transparent; padding: 2px 6px; selection-background-color: #007e00; } QLineEdit:focus { border-color: #007e00; }')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(8)
        layout.addWidget(QLabel('Language'))
        self.input = QLineEdit(part.value)
        self.input.setAccessibleName('Code block language')
        self.input.setPlaceholderText('plain text')
        self.input.setMaximumWidth(180)
        self.input.setValidator(QRegularExpressionValidator(QRegularExpression('[A-Za-z0-9_+.#-]*'), self.input))
        self.input.installEventFilter(controls)
        self.input.textEdited.connect(self.update_language)
        self.input.returnPressed.connect(lambda: controls.window.navigator.jump(1))
        layout.addWidget(self.input)
        layout.addStretch()
        hint = QLabel(f"{label(controls.window.bindings, 'previous_part')} / {label(controls.window.bindings, 'next_part')}")
        hint.setObjectName('hint')
        layout.addWidget(hint)
        self.setFixedHeight(HEADER_HEIGHT)

    def update_language(self, value):
        cursor = QTextCursor(self.controls.editor.document())
        cursor.setPosition(self.part.start)
        cursor.setPosition(self.part.end, QTextCursor.MoveMode.KeepAnchor)
        fmt = QTextBlockFormat()
        fmt.setProperty(QTextFormat.Property.BlockCodeLanguage, value)
        cursor.mergeBlockFormat(fmt)
        self.part.value = value
        self.controls.window.raw_snapshot = None


class CodeBlocks(QObject):
    def __init__(self, window):
        super().__init__(window.edit)
        self.window, self.editor = window, window.edit
        self.headers = []
        self.rectangles = []
        self.refreshing = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.refresh)
        self.editor.document().contentsChanged.connect(lambda: self.timer.start(0))
        self.editor.verticalScrollBar().valueChanged.connect(self.position)
        self.editor.horizontalScrollBar().valueChanged.connect(self.position)
        self.editor.viewport().installEventFilter(self)

    def reset(self):
        self.timer.stop()
        for header in self.headers:
            self.remove_header(header)
        self.headers = []
        self.rectangles = []
        self.editor.viewport().update()

    def remove_header(self, header):
        if self.window.navigator.input is header.input:
            self.window.navigator.input = self.window.navigator.popup_input
        header.hide()
        header.input.removeEventFilter(self)
        header.deleteLater()

    def refresh(self):
        if self.refreshing:
            return
        if not self.editor.rich:
            self.reset()
            return
        self.refreshing = True
        try:
            parts = [part for part in rendered_parts(self.editor.document()) if part.kind == 'code_language']
            remaining = list(self.headers)
            headers = []
            for part in parts:
                first = self.editor.document().findBlock(part.start)
                last = self.editor.document().findBlock(part.end)
                header = next((header for header in remaining if header.first_block == first), None)
                if header:
                    remaining.remove(header)
                    header.part = part
                    if not header.input.hasFocus():
                        header.input.setText(part.value)
                else:
                    header = CodeHeader(self, part)
                headers.append(header)
                block = first
                while block.isValid():
                    fmt = block.blockFormat()
                    desired = (HEADER_HEIGHT + PADDING if block == first else 0, PADDING if block == last else 0, PADDING, PADDING)
                    actual = (fmt.topMargin(), fmt.bottomMargin(), fmt.leftMargin(), fmt.rightMargin())
                    if actual != desired:
                        if fmt.property(CHROME) is None:
                            fmt.setProperty(CHROME, ','.join(str(value) for value in actual))
                        fmt.setTopMargin(desired[0]); fmt.setBottomMargin(desired[1])
                        fmt.setLeftMargin(desired[2]); fmt.setRightMargin(desired[3])
                        cursor = QTextCursor(block)
                        # Decoration belongs to the edit that created this block.
                        cursor.joinPreviousEditBlock()
                        cursor.setBlockFormat(fmt)
                        cursor.endEditBlock()
                    if block == last:
                        break
                    block = block.next()
            for header in remaining:
                self.remove_header(header)
            self.headers = headers
            # Qt ignores the first paragraph's top margin. Reserve its header
            # in the root frame instead, without adding any document content.
            frame = self.editor.document().rootFrame()
            fmt = frame.frameFormat()
            original = float(fmt.property(ROOT_CHROME)) if fmt.hasProperty(ROOT_CHROME) else fmt.topMargin()
            needs_header = bool(parts and parts[0].start == 0)
            desired = original + HEADER_HEIGHT + PADDING if needs_header else original
            if fmt.topMargin() != desired:
                if needs_header:
                    fmt.setProperty(ROOT_CHROME, original)
                else:
                    fmt.clearProperty(ROOT_CHROME)
                fmt.setTopMargin(desired)
                cursor = QTextCursor(self.editor.document())
                cursor.joinPreviousEditBlock()
                frame.setFrameFormat(fmt)
                cursor.endEditBlock()
            self.position()
        finally:
            self.refreshing = False

    def position(self, *_):
        self.rectangles = []
        if not self.editor.rich:
            return
        layout = self.editor.document().documentLayout()
        dx = -self.editor.horizontalScrollBar().value()
        dy = -self.editor.verticalScrollBar().value()
        for header in self.headers:
            if not header.first_block.isValid():
                header.hide()
                continue
            part = header.part
            first = layout.blockBoundingRect(self.editor.document().findBlock(part.start)).translated(dx, dy)
            last = layout.blockBoundingRect(self.editor.document().findBlock(part.end)).translated(dx, dy)
            rect = QRectF(first.left(), first.top() - HEADER_HEIGHT - PADDING,
                          first.width(), last.bottom() - first.top() + HEADER_HEIGHT + 2 * PADDING)
            self.rectangles.append(rect)
            header.setGeometry(int(rect.left() + 1), int(rect.top() + 1), max(1, int(rect.width() - 2)), HEADER_HEIGHT)
            header.show()
            header.raise_()
        self.editor.viewport().update()

    def paint(self, painter):
        painter.save()
        painter.setPen(QPen(QColor('#454545'), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for rect in self.rectangles:
            painter.drawRoundedRect(rect, 5, 5)
        painter.restore()

    def focus_language(self, part):
        self.refresh()
        header = next((header for header in self.headers if header.part.start == part.start), None)
        if header is None:
            return None
        if header.y() < 0:
            bar = self.editor.verticalScrollBar()
            bar.setValue(bar.value() + header.y() - 4)
            self.position()
        header.input.setFocus()
        header.input.selectAll()
        return header.input

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Resize and obj == self.editor.viewport():
            self.position()
        elif isinstance(obj, QLineEdit) and event.type() == QEvent.Type.FocusIn:
            header = next((header for header in self.headers if header.input == obj), None)
            if header:
                nav = self.window.navigator
                nav.current = Part('code_language', header.part.start, header.part.end, header.part.value)
                nav.marker = QTextCursor(self.editor.document())
                nav.marker.setPosition(header.part.start)
                nav.marker.setKeepPositionOnInsert(True)
                nav.input = obj
                cursor = QTextCursor(self.editor.document())
                cursor.setPosition(header.part.start)
                was_selecting = nav.selecting
                nav.selecting = True
                self.editor.setTextCursor(cursor)
                nav.selecting = was_selecting
                self.window.spelling_panel.hide()
        return False
