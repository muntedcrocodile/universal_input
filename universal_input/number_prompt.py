"""Non-modal numeric commands contained inside the floating window."""
from PyQt6.QtGui import QIntValidator, QTextCursor
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel, QLineEdit


class NumberPrompt(QFrame):
    def __init__(self, window):
        super().__init__(window.centralWidget())
        self.window = window
        self.setObjectName('numberPrompt')
        self.setStyleSheet('QFrame#numberPrompt { background: #252526; border: 1px solid #454545; border-radius: 5px; } QLineEdit { background: #1e1e1e; color: #d4d4d4; border: 1px solid #007e00; padding: 6px; selection-background-color: #007e00; }')
        layout = QVBoxLayout(self)
        self.title = QLabel()
        self.input = QLineEdit()
        self.input.setValidator(QIntValidator(1, 2147483647, self.input))
        self.hint = QLabel()
        self.hint.setObjectName('hint')
        layout.addWidget(self.title)
        layout.addWidget(self.input)
        layout.addWidget(self.hint)
        self.input.returnPressed.connect(self.accept)
        self.hide()

    def open(self, command):
        window = self.window
        window.spelling_panel.hide()
        window.table_picker.hide()
        window.navigator.reset()
        self.command = command
        self.cursor = QTextCursor(window.edit.textCursor())
        if command == 'line':
            self.maximum = window.edit.document().blockCount()
            title = 'Go to line'
            value = str(self.cursor.blockNumber() + 1)
        else:
            self.entries = list((window.entry_history, window.clipboard_history)[window.active_history].entries)
            self.maximum = len(self.entries)
            title = 'Insert from ' + ('Recents' if window.active_history == 0 else 'Clipboard')
            value = ''
        self.title.setText(title)
        self.input.setAccessibleName(title)
        self.input.setText(value)
        self.input.setPlaceholderText(f'1–{self.maximum}' if self.maximum else 'No entries yet')
        self.input.setEnabled(bool(self.maximum))
        self.hint.setText(f'Enter a number from 1 to {self.maximum}' if self.maximum else 'Copy text or save a draft to add entries.')
        self.setFixedWidth(min(340, self.parentWidget().width() - 24))
        self.adjustSize()
        self.move((self.parentWidget().width() - self.width()) // 2, 60)
        self.show()
        self.raise_()
        if self.maximum:
            self.input.setFocus()
            self.input.selectAll()

    def accept(self):
        number = int(self.input.text() or '0')
        maximum = self.window.edit.document().blockCount() if self.command == 'line' else self.maximum
        if not 1 <= number <= maximum:
            self.hint.setText(f'Choose a number from 1 to {maximum}.')
            return
        self.hide()
        editor = self.window.edit
        if self.command == 'line':
            self.window.navigator.reset()
            cursor = QTextCursor(editor.document().findBlockByNumber(number - 1))
            editor.setTextCursor(cursor)
            editor.ensureCursorVisible()
        else:
            editor.setTextCursor(self.cursor)
            self.window.insert_entry(self.entries[number - 1])
        editor.setFocus()
