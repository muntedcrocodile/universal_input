# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Local spelling, English writing rules, and in-editor correction suggestions."""
from dataclasses import dataclass
import os
from pathlib import Path
import re

import enchant
from PyQt6.QtCore import QEvent, QObject, QPoint, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QListWidget, QListWidgetItem, QTextEdit, QVBoxLayout, QWidget

from .shortcuts import label
from .writing import WORDS, writing_issues

OMIT = re.compile(
    r"(?ms)^[ \t]*(```|~~~)[^\n]*(?:\n.*?(?:^[ \t]*\1[^\n]*(?:\n|$)|\Z)|$)"
    r"|(?P<ticks>`+)(?!`)[^\n]*?(?P=ticks)(?!`)|`[^\n]*$"
    r"|(?:https?://|www\.)\S+|\b[^\s@]+@[^\s@]+|\]\([^)]*(?:\)|$)"
)


@dataclass
class Misspelling:
    start: int
    end: int
    word: str
    kind: str = "spelling"
    suggestions: tuple = ()
    message: str = ""


class SpellChecker(QObject):
    def __init__(self, editor, language="en_AU", personal_path=None, autocorrect=True, grammar_check=True):
        super().__init__(editor)
        self.editor = editor
        self.personal_path = personal_path
        self.english = language.lower().split("_")[0].split("-")[0] == "en"
        self.autocorrect_enabled = autocorrect
        self.grammar_enabled = grammar_check
        if personal_path is not None:
            fd = os.open(personal_path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
            os.close(fd)
            os.chmod(personal_path, 0o600)
        self.dictionary = enchant.DictWithPWL(language, str(personal_path) if personal_path is not None else None)
        self.personal_words = set(Path(personal_path).read_text(encoding="utf-8").splitlines()) if personal_path is not None else set()
        self.errors = []
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(180)
        self.timer.timeout.connect(self.refresh)
        editor.document().contentsChange.connect(self.changed)

    def changed(self, position, removed, added):
        if removed or added:
            self.timer.start()

    def prose(self):
        text = self.editor.toPlainText()
        masked = list(OMIT.sub(lambda match: "\0" * len(match.group()), text))
        # Convert Python code-point positions to Qt UTF-16 positions once.
        offsets = [0]
        for character in text:
            offsets.append(offsets[-1] + (2 if ord(character) > 0xffff else 1))
        if self.editor.rich:
            positions = {offset: index for index, offset in enumerate(offsets)}
            block = self.editor.document().begin()
            while block.isValid():
                fragment_iter = block.begin()
                while not fragment_iter.atEnd():
                    fragment = fragment_iter.fragment()
                    fmt = fragment.charFormat()
                    families = [family.lower() for family in (fmt.fontFamilies() or [])]
                    if "monospace" in families or block.blockFormat().nonBreakableLines():
                        start = positions[fragment.position()]
                        end = positions[fragment.position() + fragment.length()]
                        masked[start:end] = "\0" * (end - start)
                    fragment_iter += 1
                block = block.next()
        return text, "".join(masked), offsets

    def refresh(self):
        text, masked, offsets = self.prose()
        errors, selections = [], []
        rules = writing_issues(masked, self.grammar_enabled, capitalization=self.grammar_enabled) if self.english else []
        covered = set()
        for issue in rules:
            if any(index in covered for index in range(issue.start, issue.end)):
                continue
            errors.append(Misspelling(offsets[issue.start], offsets[issue.end], text[issue.start:issue.end],
                                      issue.kind, (issue.replacement,), issue.message))
            covered.update(range(issue.start, issue.end))
        checked = {}
        for match in WORDS.finditer(masked):
            word = match.group()
            if len(word) < 2:
                continue
            if any(index in covered for index in range(match.start(), match.end())):
                continue
            normalized = word.replace("’", "'")
            if normalized not in checked:
                checked[normalized] = self.dictionary.check(normalized)
            if checked[normalized]:
                continue
            errors.append(Misspelling(offsets[match.start()], offsets[match.end()], word))
        errors.sort(key=lambda error: (error.start, error.end))
        for error in errors:
            cursor = QTextCursor(self.editor.document())
            cursor.setPosition(error.start)
            cursor.setPosition(error.end, QTextCursor.MoveMode.KeepAnchor)
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            selection.format.setUnderlineColor(QColor("#75beff" if error.kind == "grammar" else "#ef8585"))
            selection.format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
            selections.append(selection)
        self.errors = errors
        self.editor.setExtraSelections(selections)

    def autocorrect(self, delimiter):
        """Correct completed words only after a typed boundary, never on load/paste."""
        if not self.autocorrect_enabled or not self.english or len(delimiter) != 1 or delimiter not in " \t\r\n.,!?;:)]}\"":
            return
        saved = self.editor.textCursor()
        if saved.hasSelection():
            return
        text, masked, offsets = self.prose()
        try:
            boundary = offsets.index(saved.position()) - 1
        except ValueError:
            return
        # Do not finish a word in the middle of an identifier or URL.
        if boundary < 1 or (boundary + 1 < len(text) and (text[boundary + 1].isalnum() or text[boundary + 1] in "_/@")):
            return
        candidates = [issue for issue in writing_issues(masked, grammar=False)
                      if issue.automatic and issue.trigger_end == boundary]
        if not candidates:
            return
        cursor = QTextCursor(saved)
        # Begin at the typing caret so undo restores both text and caret.
        # A separate undo step restores exactly the text before autocorrection.
        cursor.beginEditBlock()
        for issue in reversed(candidates):
            cursor.setPosition(offsets[issue.start])
            cursor.setPosition(offsets[issue.end], QTextCursor.MoveMode.KeepAnchor)
            fmt = cursor.charFormat()
            cursor.insertText(issue.replacement, fmt)
        cursor.endEditBlock()
        self.editor.setTextCursor(saved)
        self.refresh()

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
        word = word.replace("’", "'")
        self.dictionary.add(word)
        self.personal_words.add(word)
        self.refresh()

    def personal_word(self, word):
        """Find the actual saved entry, including capitalised uses of it."""
        if not WORDS.fullmatch(word):
            return None
        normalized = word.replace("’", "'")
        if normalized in self.personal_words:
            return normalized
        return next((entry for entry in sorted(self.personal_words)
                     if entry.replace("’", "'").casefold() == normalized.casefold()), None)

    def remove_word(self, word):
        entry = self.personal_word(word)
        if entry is None:
            return
        # Removing from the combined dictionary would blacklist ordinary words.
        # Remove the actual PWL entry so the base dictionary still applies.
        self.dictionary.pwl.remove(entry)
        self.personal_words.remove(entry)
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
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setWordWrap(True)
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
        self.suggestions = list(error.suggestions) if error.suggestions else self.checker.dictionary.suggest(error.word)[:9]
        self.can_add = error.kind == "spelling" and not error.suggestions
        self.title.setText(f"{error.kind.capitalize()}: {error.word}" + (f"\n{error.message}" if error.message else ""))
        self.list.clear()
        choices = self.suggestions + ([f'Add “{error.word}” to dictionary'] if self.can_add else [])
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
        if self.error is None or not 0 <= index < len(self.suggestions) + int(self.can_add):
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
