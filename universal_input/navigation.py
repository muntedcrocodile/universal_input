"""Editable Markdown parts in source and rendered documents."""
from dataclasses import dataclass
import re

from PyQt6.QtCore import QPoint, Qt, QRegularExpression
from PyQt6.QtGui import QTextCursor, QTextFormat, QTextCharFormat, QTextBlockFormat, QRegularExpressionValidator
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit


@dataclass
class Part:
    kind: str
    start: int
    end: int
    value: str | None = None


def raw_parts(text):
    """Recognise common editable constructs, keeping all Markdown delimiters out."""
    parts = []
    offsets = [0]
    for char in text:
        offsets.append(offsets[-1] + (2 if ord(char) > 0xffff else 1))

    def add(kind, start, end):
        parts.append(Part(kind, offsets[start], offsets[end]))

    lines = list(re.finditer(r"[^\n]*(?:\n|$)", text))
    index = 0
    while index < len(lines):
        line = lines[index]
        content = line.group().rstrip('\n')
        base = line.start()
        fence = re.match(r"^ {0,3}(`{3,}|~{3,})[ \t]*([^ \t]*)(?:[ \t].*)?$", content)
        if fence:
            marker = fence.group(1)
            add('code_language', base + fence.start(2), base + fence.end(2))
            end_index = index + 1
            while end_index < len(lines) and not re.fullmatch(r" {0,3}" + re.escape(marker[0]) + '{' + str(len(marker)) + r",}[ \t]*", lines[end_index].group().rstrip('\n')):
                end_index += 1
            end = lines[end_index].start() if end_index < len(lines) else len(text)
            if end > line.end() and text[end - 1] == '\n':
                end -= 1
            add('code_body', line.end(), max(line.end(), end))
            index = end_index + 1
            continue
        task = re.match(r"\s*(?:[-+*]|\d+[.)])\s+(?:\[[ xX]\]\s*)?(.*)", content)
        if task:
            add('task', base + task.start(1), base + task.end(1))
        elif content.strip().startswith('|') and content.strip().endswith('|'):
            if not re.fullmatch(r'[ |:\-]+', content):
                bars = list(re.finditer(r'(?<!\\)\|', content))
                for left, right in zip(bars, bars[1:]):
                    a, b = left.end(), right.start()
                    while a < b and content[a].isspace():
                        a += 1
                    while b > a and content[b - 1].isspace():
                        b -= 1
                    add('cell', base + a, base + b)
        elif content.strip() and not re.fullmatch(r'\s*(?:---+|\*\*\*+|___+)\s*', content):
            # Balanced destinations allow URLs such as https://host/path_(name).
            specials = []
            for match in re.finditer(r'(?<!!)\[((?:\\.|[^\]\\])*)\]\(', content):
                start = match.end()
                position, depth = start, 1
                while position < len(content) and depth:
                    if content[position] == '\\':
                        position += 2
                        continue
                    if content[position] == '(':
                        depth += 1
                    elif content[position] == ')':
                        depth -= 1
                    if depth:
                        position += 1
                if depth == 0:
                    specials.extend([('link_text', match.start(1), match.end(1)), ('link_url', start, position)])
            if specials:
                for kind, start, end in specials:
                    add(kind, base + start, base + end)
            else:
                prefix = re.match(r'\s*(?:(?:>\s*)+|#{1,6}\s+)', content)
                start = prefix.end() if prefix else len(content) - len(content.lstrip())
                add('text', base + start, base + len(content.rstrip()))
        index += 1
    return parts


def rendered_parts(document):
    parts = []
    block = document.begin()
    seen_cells = set()
    while block.isValid():
        fmt = block.blockFormat()
        if fmt.nonBreakableLines():
            first, last = block, block
            language = fmt.stringProperty(QTextFormat.Property.BlockCodeLanguage)
            while last.next().isValid() and last.next().blockFormat().nonBreakableLines() and last.next().blockFormat().stringProperty(QTextFormat.Property.BlockCodeLanguage) == language:
                last = last.next()
            end = last.position() + last.length() - 1
            parts.extend([Part('code_language', first.position(), end, language), Part('code_body', first.position(), end)])
            block = last.next()
            continue
        cursor = QTextCursor(block)
        table = cursor.currentTable()
        if table:
            cell = table.cellAt(cursor)
            start, end = cell.firstCursorPosition().position(), cell.lastCursorPosition().position()
            if start not in seen_cells:
                parts.append(Part('cell', start, end))
                seen_cells.add(start)
        elif block.textList():
            parts.append(Part('task', block.position(), block.position() + block.length() - 1))
        else:
            links = []
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid() and fragment.charFormat().isAnchor() and fragment.charFormat().anchorHref():
                    start, end, url = fragment.position(), fragment.position() + fragment.length(), fragment.charFormat().anchorHref()
                    if links and links[-1][1] == start and links[-1][2] == url:
                        links[-1] = (links[-1][0], end, url)
                    else:
                        links.append((start, end, url))
                iterator += 1
            if links:
                for start, end, url in links:
                    parts.extend([Part('link_text', start, end), Part('link_url', start, end, url)])
            elif block.text().strip():
                parts.append(Part('text', block.position(), block.position() + block.length() - 1))
        block = block.next()
    return parts


class PartNavigator:
    def __init__(self, window):
        self.window = window
        self.editor = window.edit
        self.current = None
        self.marker = None
        self.selecting = False
        self.field = QFrame(window.centralWidget())
        self.field.setObjectName('partField')
        self.field.setStyleSheet("QFrame#partField { background: #252526; border: 1px solid #808080; border-radius: 6px; } QLineEdit { background: #1e1e1e; border: 1px solid #454545; padding: 6px; selection-background-color: #007e00; }")
        layout = QHBoxLayout(self.field)
        self.label = QLabel()
        self.input = QLineEdit()
        self.popup_input = self.input
        self.input.setMinimumWidth(220)
        layout.addWidget(self.label)
        layout.addWidget(self.input)
        self.input.textEdited.connect(self.edit_metadata)
        self.input.returnPressed.connect(lambda: self.jump(1))
        self.field.hide()

    def parts(self):
        return rendered_parts(self.editor.document()) if self.editor.rich else raw_parts(self.editor.toPlainText())

    def reset(self):
        self.field.hide()
        self.current = self.marker = None
        self.input = self.popup_input

    def dismiss(self):
        self.field.hide()
        self.editor.setFocus()

    def jump(self, direction):
        parts = self.parts()
        if not parts:
            return
        cursor = self.editor.textCursor()
        current = None
        if self.current and self.marker:
            current = next((i for i, part in enumerate(parts) if part.kind == self.current.kind and part.start == self.marker.position() and (self.field.isVisible() or self.input.hasFocus() or part.start <= cursor.position() <= part.end)), None)
        if current is None and cursor.hasSelection():
            current = next((i for i, part in enumerate(parts) if part.value is None and (part.start, part.end) == (cursor.selectionStart(), cursor.selectionEnd())), None)
        if current is not None:
            index = (current + direction) % len(parts)
        else:
            containing = [i for i, part in enumerate(parts) if part.start <= cursor.position() <= part.end]
            if containing:
                index = containing[0]
            elif direction > 0:
                index = next((i for i, part in enumerate(parts) if part.start >= cursor.position()), 0)
            else:
                index = next((i for i in reversed(range(len(parts))) if parts[i].end <= cursor.position()), len(parts) - 1)
        self.select(parts[index])

    def select(self, part):
        self.selecting = True
        try:
            self.window.spelling_panel.hide()
            self.window.table_picker.hide()
            self.field.hide()
            self.current = part
            self.marker = QTextCursor(self.editor.document())
            self.marker.setPosition(part.start)
            self.marker.setKeepPositionOnInsert(True)
            cursor = QTextCursor(self.marker)
            cursor.setKeepPositionOnInsert(False)
            if part.value is None:
                cursor.setPosition(part.end, QTextCursor.MoveMode.KeepAnchor)
            self.editor.setTextCursor(cursor)
            self.editor.ensureCursorVisible()
            if part.value is not None:
                if part.kind == 'code_language':
                    header_input = self.window.code_blocks.focus_language(part)
                    if header_input:
                        self.input = header_input
                        return
                self.input = self.popup_input
                self.label.setText('Language' if part.kind == 'code_language' else 'Link URL')
                self.input.setValidator(QRegularExpressionValidator(QRegularExpression('[A-Za-z0-9_+.#-]*'), self.input) if part.kind == 'code_language' else None)
                self.input.setText(part.value)
                self.field.adjustSize()
                parent = self.field.parentWidget()
                point = self.editor.viewport().mapTo(parent, self.editor.cursorRect().bottomLeft() + QPoint(0, 4))
                self.field.move(max(0, min(point.x(), parent.width() - self.field.width())), max(0, min(point.y(), parent.height() - self.field.height())))
                self.field.show()
                self.field.raise_()
                self.input.setFocus()
                self.input.selectAll()
            else:
                self.editor.setFocus()
        finally:
            self.selecting = False

    def edit_metadata(self, text):
        if not self.current or not self.field.isVisible():
            return
        part = self.current
        cursor = QTextCursor(self.editor.document())
        cursor.setPosition(part.start)
        cursor.setPosition(part.end, QTextCursor.MoveMode.KeepAnchor)
        cursor.beginEditBlock()
        if part.kind == 'link_url':
            fmt = QTextCharFormat()
            fmt.setAnchor(True)
            fmt.setAnchorHref(text)
            cursor.mergeCharFormat(fmt)
        else:
            fmt = QTextBlockFormat()
            fmt.setProperty(QTextFormat.Property.BlockCodeLanguage, text)
            cursor.mergeBlockFormat(fmt)
        cursor.endEditBlock()
        self.current.value = text
        self.window.raw_snapshot = None
