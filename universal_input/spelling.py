"""Local Enchant/Hunspell checking and a non-modal, in-editor suggestion panel."""
from dataclasses import dataclass
import os
import re

import enchant
from PyQt6.QtCore import QEvent, QObject, QPoint, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QListWidget, QListWidgetItem, QTextEdit, QVBoxLayout, QWidget

from .shortcuts import label

WORDS = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.UNICODE)
OMIT = re.compile(r"(?ms)^\s*(```|~~~)[^\n]*\n.*?(?:^\s*\1[^\n]*(?:\n|$)|\Z)|`[^`\n]*`|https?://\S+|\b\S+@\S+\.\S+|\]\([^)]*\)")


@dataclass
class Misspelling:
    start: int
    end: int
    word: str


class SpellChecker(QObject):
    def __init__(self, editor, language="en_AU", personal_path=None):
        super().__init__(editor)
        self.editor = editor
        self.personal_path = personal_path
        if personal_path is not None:
            fd = os.open(personal_path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
            os.close(fd)
            os.chmod(personal_path, 0o600)
            self.dictionary = enchant.DictWithPWL(language, str(personal_path))
        else:
            self.dictionary = enchant.Dict(language)
        self.errors = []
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(180)
        self.timer.timeout.connect(self.refresh)
        editor.document().contentsChange.connect(self.changed)

    def changed(self, position, removed, added):
        if removed or added:
            self.timer.start()

    def refresh(self):
        text = self.editor.toPlainText()
        masked = OMIT.sub(lambda match: " " * len(match.group()), text)
        errors, selections = [], []
        # Convert Python code-point positions to Qt UTF-16 positions once.
        offsets = [0]
        for character in text:
            offsets.append(offsets[-1] + (2 if ord(character) > 0xffff else 1))
        checked = {}
        for match in WORDS.finditer(masked):
            word = match.group()
            if len(word) < 2:
                continue
            start, end = offsets[match.start()], offsets[match.end()]
            cursor = QTextCursor(self.editor.document())
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            if self.editor.rich:
                fmt = cursor.charFormat()
                families = [family.lower() for family in (fmt.fontFamilies() or [])]
                # Qt marks inline code with the generic monospace family. The
                # editor's Nimbus Mono PS prose must still receive spellchecking.
                if "monospace" in families or cursor.blockFormat().nonBreakableLines():
                    continue
            normalized = word.replace("’", "'")
            if normalized not in checked:
                checked[normalized] = self.dictionary.check(normalized)
            if checked[normalized]:
                continue
            errors.append(Misspelling(start, end, word))
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            selection.format.setUnderlineColor(QColor("#ef8585"))
            selection.format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
            selections.append(selection)
        self.errors = errors
        self.editor.setExtraSelections(selections)

    def selected_error(self):
        cursor = self.editor.textCursor()
        return next((error for error in self.errors if cursor.selectionStart() == error.start and cursor.selectionEnd() == error.end and cursor.selectedText() == error.word), None)

    def jump(self, direction):
        self.refresh()
        if not self.errors:
            return
        cursor = self.editor.textCursor()
        if direction > 0:
            edge = cursor.selectionEnd()
            error = next((error for error in self.errors if error.start >= edge), self.errors[0])
        else:
            edge = cursor.selectionStart()
            error = next((error for error in reversed(self.errors) if error.end <= edge), self.errors[-1])
        cursor.setPosition(error.start)
        cursor.setPosition(error.end, QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cursor)
        self.editor.ensureCursorVisible()

    def add_word(self, word):
        if self.personal_path is not None:
            self.dictionary.add(word)
        else:
            self.dictionary.add_to_session(word)
        self.refresh()


class SuggestionList(QListWidget):
    commands = {}
    chosen = pyqtSignal(int)
    escape_requested = pyqtSignal()

    def event(self, event):
        if event.type() == QEvent.Type.ShortcutOverride and QKeySequence(event.keyCombination()).toString() in self.commands:
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        callback = self.commands.get(QKeySequence(event.keyCombination()).toString())
        if callback:
            callback()
            return
        panel = self.parentWidget()
        if not panel.navigate(event):
            panel.hide()
            panel.editor.setFocus()
            QApplication.sendEvent(panel.editor, event)


class SpellingPanel(QFrame):
    escape_requested = pyqtSignal()

    def __init__(self, parent, editor, checker, bindings):
        super().__init__(parent)
        self.editor, self.checker, self.bindings = editor, checker, bindings
        self.error = None
        self.cursor = None
        self.setObjectName("spellingPanel")
        self.setStyleSheet("QFrame#spellingPanel { background: #252526; border: 1px solid #808080; border-radius: 8px; } QListWidget::item:selected { background: #007e00; color: white; border-radius: 4px; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        self.title = QLabel()
        self.list = SuggestionList()
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.itemClicked.connect(lambda item: self.choose(self.list.row(item)))
        self.list.chosen.connect(self.choose)
        self.list.escape_requested.connect(self.escape_requested)
        layout.addWidget(self.title)
        layout.addWidget(self.list)
        self.setFixedWidth(320)
        self.hide()

    def open(self, error):
        if self.isVisible() and self.error == error:
            return
        self.error = error
        self.cursor = QTextCursor(self.editor.textCursor())
        self.suggestions = self.checker.dictionary.suggest(error.word)[:9]
        self.title.setText(f"Spelling: {error.word}")
        self.list.clear()
        choices = self.suggestions + [f'Add “{error.word}” to dictionary']
        for index, text in enumerate(choices):
            key = label(self.bindings, "add_to_dictionary" if index == len(self.suggestions) else f"choice_{index + 1}")
            item = QListWidgetItem(f"{key}   {text}" if key else text)
            item.setSizeHint(QSize(0, 29))
            self.list.addItem(item)
        self.list.setFixedHeight(len(choices) * 29 + 4)
        self.adjustSize()
        point = self.editor.viewport().mapTo(self.parentWidget(), self.editor.cursorRect().bottomLeft() + QPoint(0, 4))
        self.move(max(0, min(point.x(), self.parentWidget().width() - self.width())), max(0, min(point.y(), self.parentWidget().height() - self.height())))
        self.show()
        self.raise_()
        self.list.setCurrentRow(0)
        QApplication.instance().installEventFilter(self)
        # Keep keyboard/IME input in the document. Only navigation and choosing
        # a suggestion are intercepted while this child panel is visible.
        self.editor.setFocus()

    def navigate(self, event):
        if event.key() in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta, Qt.Key.Key_AltGr):
            event.accept()
            return True
        if event.modifiers() != Qt.KeyboardModifier.NoModifier:
            return False
        key = event.key()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_Right, Qt.Key.Key_Down):
            direction = -1 if key in (Qt.Key.Key_Left, Qt.Key.Key_Up) else 1
            self.list.setCurrentRow((self.list.currentRow() + direction) % self.list.count())
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.choose(self.list.currentRow())
        else:
            return False
        event.accept()
        return True

    def choose(self, index):
        if self.error is None or not 0 <= index <= len(self.suggestions):
            return
        error, cursor = self.error, self.cursor
        if cursor.selectedText() != error.word:
            self.hide()
            return
        self.hide()
        if index == len(self.suggestions):
            self.checker.add_word(error.word)
        else:
            cursor.insertText(self.suggestions[index])
            self.editor.setTextCursor(cursor)
            self.checker.refresh()
        self.editor.setFocus()

    def eventFilter(self, obj, event):
        if self.isVisible() and event.type() == QEvent.Type.MouseButtonPress:
            if isinstance(obj, QWidget) and obj != self and not self.isAncestorOf(obj):
                self.hide()
        return False

    def hideEvent(self, event):
        QApplication.instance().removeEventFilter(self)
        self.error = None
        super().hideEvent(event)
