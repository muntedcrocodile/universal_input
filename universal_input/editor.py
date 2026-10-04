"""Floating editor. This module never reads or writes another application."""
from PyQt6.QtCore import Qt, QEvent, QSize, pyqtSignal
from PyQt6.QtGui import QFont, QKeySequence, QShortcut, QTextCharFormat, QTextCursor, QTextDocument, QTextTable, QTextLength, QTextFrameFormat, QColor
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QTextEdit, QVBoxLayout, QWidget, QListWidget, QListWidgetItem, QFrame,
    QToolButton,
)

from .history import History
from .highlighting import MarkdownHighlighter
from .tables import TableControls
from .table_picker import TablePicker
from .spelling import SpellChecker, SpellingPanel
from .shortcuts import normalize_bindings, label as shortcut_label
from .markdown import export_markdown
from .design import DragBar, ResizeGrip, HistoryDelegate, ModeComboBox, QuickInsertButton, STYLESHEET


class DraftEdit(QTextEdit):
    def __init__(self):
        super().__init__()
        self.rich = False
        self.commands = {}
        self.setAcceptRichText(False)
        self.setPlaceholderText("Start writing…")
        self.setFont(QFont("Nimbus Mono PS", 12))

    def event(self, event):
        if event.type() == QEvent.Type.ShortcutOverride:
            if QKeySequence(event.keyCombination()).toString() in self.commands:
                event.accept()
                return True
        return super().event(event)

    def keyPressEvent(self, event):
        callback = self.commands.get(QKeySequence(event.keyCombination()).toString())
        if callback:
            callback()
            event.accept()
        else:
            super().keyPressEvent(event)

    def toggle_format(self, kind):
        if not self.rich:
            marker = {"bold": "**", "italic": "*", "strike": "~~", "code": "`", "underline": "__"}[kind]
            cursor = self.textCursor()
            start, end = cursor.selectionStart(), cursor.selectionEnd()
            # Read through QTextCursor to respect Qt's UTF-16 character offsets.
            selected = cursor.selectedText().replace("\u2029", "\n")
            before = QTextCursor(self.document())
            before.setPosition(max(0, start - len(marker)))
            before.setPosition(start, QTextCursor.MoveMode.KeepAnchor)
            after = QTextCursor(self.document())
            after.setPosition(end)
            after.setPosition(min(self.document().characterCount() - 1, end + len(marker)), QTextCursor.MoveMode.KeepAnchor)
            if start == end and after.selectedText() == marker and before.selectedText() != marker:
                cursor.setPosition(end + len(marker))
                self.setTextCursor(cursor)
                return
            cursor.beginEditBlock()
            if before.selectedText() == marker and after.selectedText() == marker:
                cursor.setPosition(start - len(marker))
                cursor.setPosition(end + len(marker), QTextCursor.MoveMode.KeepAnchor)
                cursor.insertText(selected)
                new_start, new_end = start - len(marker), end - len(marker)
            elif selected.startswith(marker) and selected.endswith(marker) and len(selected) >= 2 * len(marker):
                cursor.insertText(selected[len(marker):-len(marker)])
                new_start, new_end = start, end - 2 * len(marker)
            else:
                cursor.insertText(marker + selected + marker)
                new_start, new_end = start + len(marker), end + len(marker)
            cursor.endEditBlock()
            cursor.setPosition(new_start)
            cursor.setPosition(new_end, QTextCursor.MoveMode.KeepAnchor)
            self.setTextCursor(cursor)
            return
        current = self.currentCharFormat()
        fmt = QTextCharFormat()
        if kind == "bold":
            fmt.setFontWeight(QFont.Weight.Normal if current.fontWeight() >= QFont.Weight.Bold else QFont.Weight.Bold)
        elif kind == "italic":
            fmt.setFontItalic(not current.fontItalic())
        elif kind == "underline":
            fmt.setFontUnderline(not current.fontUnderline())
        elif kind == "strike":
            fmt.setFontStrikeOut(not current.fontStrikeOut())
        elif kind == "code":
            fmt.setFontFamilies(["Sans Serif" if current.fontFamilies() == ["monospace"] else "monospace"])
        self.mergeCurrentCharFormat(fmt)


class EditorWindow(QMainWindow):
    commit_requested = pyqtSignal()
    cancelled = pyqtSignal()
    history_changed = pyqtSignal()

    font_size_changed = pyqtSignal(int)

    def __init__(self, entry_history=None, clipboard_history=None, bindings=None, personal_dictionary=None, spell_language="en_AU", font_size=16):
        super().__init__()
        self.font_size = font_size
        self.bindings = normalize_bindings(bindings)
        self.setWindowTitle("Universal Input")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.X11BypassWindowManagerHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(0.96)
        self.edit = DraftEdit()
        self.highlighter = MarkdownHighlighter(self.edit.document())
        self.spelling = SpellChecker(self.edit, spell_language, personal_dictionary)
        self.table_controls = TableControls(self.edit)
        self.heading = QLabel("Universal Input")
        self.heading.setObjectName("brand")
        self.heading.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.mode = ModeComboBox()
        self.mode.addItems(["Raw", "Rendered"])
        self.mode.shortcut = shortcut_label(self.bindings, "toggle_mode")
        self.mode.mode_keys = [shortcut_label(self.bindings, "raw_mode"), shortcut_label(self.bindings, "rendered_mode")]
        self.raw_snapshot = None
        self.rendered_snapshot = None
        self.mode.currentIndexChanged.connect(self.change_mode)
        self.entry_history = entry_history if entry_history is not None else History()
        self.clipboard_history = clipboard_history if clipboard_history is not None else History()
        self.active_history = 0
        self.history_lists = []
        self.history_frames = []
        self.history_headers = []
        self.history_titles = []
        self.history_keys = []
        histories = QHBoxLayout()
        for title in ("Recents", "Clipboard"):
            frame = QFrame()
            frame.setObjectName("historyPanel")
            panel = QVBoxLayout(frame)
            panel.setContentsMargins(0, 0, 0, 0)
            panel.setSpacing(7)
            shelf_header = QWidget()
            shelf_header.setObjectName("shelfHeader")
            shelf_layout = QHBoxLayout(shelf_header)
            shelf_layout.setContentsMargins(7, 7, 7, 9)
            label = QLabel(title)
            label.setStyleSheet("font-weight: 600;")
            keys = QLabel("Alt 1–9")
            keys.setObjectName("hint")
            shelf_layout.addWidget(label)
            shelf_layout.addStretch()
            shelf_layout.addWidget(keys)
            self.history_headers.append(shelf_header)
            self.history_titles.append(label)
            self.history_keys.append(keys)
            panel.addWidget(shelf_header)
            listing = QListWidget()
            listing.setItemDelegate(HistoryDelegate(listing))
            listing.setMouseTracking(True)
            listing.setFont(QFont("Lato", 10))
            listing.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            listing.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            listing.itemClicked.connect(lambda item, index=len(self.history_lists): self.insert_history(index, item.data(Qt.ItemDataRole.UserRole)))
            panel.addWidget(listing)
            self.history_lists.append(listing)
            self.history_frames.append(frame)
            histories.addWidget(frame)
        self.highlight_history(0)
        self.status = QLabel("Ready to write")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        self.send = QPushButton(f"Insert    {shortcut_label(self.bindings, 'insert')}")
        self.send.setObjectName("primaryAction")
        self.send.clicked.connect(self.commit_requested)
        cancel = QPushButton(f"Close    {shortcut_label(self.bindings, 'close')}")
        cancel.setObjectName("escapeAction")
        cancel.setToolTip("Save this draft to Recents and close")
        cancel.clicked.connect(self.cancelled)
        bar = DragBar()
        bar.setObjectName("commandBar")
        header = QHBoxLayout(bar)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(3)
        header.addWidget(self.mode)
        self.table_button = QuickInsertButton("Table ▾", shortcut_label(self.bindings, "table"))
        self.table_button.clicked.connect(self.toggle_table_picker)
        header.addWidget(self.table_button)
        self.quick_actions = {"table": self.toggle_table_picker}
        for action, title, markdown, placeholder in [
            ("code_block", "Code", "```text\ncode\n```", "code"),
            ("tasks", "Tasks", "- [ ] First task\n- [ ] Second task", "First task"),
            ("quote", "Quote", "> Quoted text", "Quoted text"),
            ("link", "Link", "[link text](https://example.com)", "link text"),
            ("divider", "Divider", "---", None),
        ]:
            callback = lambda checked=False, markdown=markdown, placeholder=placeholder: self.insert_markdown(markdown, placeholder)
            self.quick_actions[action] = callback
            button = QuickInsertButton(title, shortcut_label(self.bindings, action))
            button.clicked.connect(callback)
            header.addWidget(button)
        header.addStretch()
        header.addWidget(self.heading)
        footer = QHBoxLayout()
        footer.setSpacing(8)
        footer.addWidget(self.status, 1)
        self.word_count = QLabel("0 words")
        self.word_count.setObjectName("wordCount")
        self.edit.textChanged.connect(self.update_word_count)
        footer.addWidget(self.word_count)
        footer.addWidget(cancel)
        footer.addWidget(self.send)
        footer.addWidget(ResizeGrip(self))
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 15, 20, 14)
        layout.setSpacing(10)
        layout.addWidget(bar)
        layout.addWidget(self.edit, 3)
        layout.addLayout(histories, 2)
        history_hint = QLabel(f"History  {shortcut_label(self.bindings, 'history_left')} / {shortcut_label(self.bindings, 'history_right')}     Spelling  {shortcut_label(self.bindings, 'previous_misspelling')} / {shortcut_label(self.bindings, 'next_misspelling')}")
        history_hint.setObjectName("hint")
        history_hint.setWordWrap(True)
        layout.addWidget(history_hint)
        layout.addLayout(footer)
        body = QWidget()
        body.setObjectName("panel")
        body.setLayout(layout)
        self.setCentralWidget(body)
        self.table_picker = TablePicker(body, self.table_button)
        self.table_picker.chosen.connect(self.insert_table)
        self.table_picker.escape_requested.connect(self.cancelled)
        self.spelling_panel = SpellingPanel(body, self.edit, self.spelling, self.bindings)
        self.spelling_panel.escape_requested.connect(self.cancelled)
        self.edit.selectionChanged.connect(self.show_spelling_selection)
        self.setStyleSheet(STYLESHEET)
        self.apply_view_font(False)
        self.shortcuts = []
        actions = {
            "insert": self.commit_requested.emit,
            "close": self.cancelled.emit,
            "raw_mode": lambda: self.mode.setCurrentIndex(0),
            "rendered_mode": lambda: self.mode.setCurrentIndex(1),
            "toggle_mode": lambda: self.mode.setCurrentIndex(1 - self.mode.currentIndex()),
            "history_left": lambda: self.highlight_history(0),
            "history_right": lambda: self.highlight_history(1),
            "previous_misspelling": lambda: self.spelling.jump(-1),
            "next_misspelling": lambda: self.spelling.jump(1),
            "spelling_suggestions": self.show_spelling_selection,
            "increase_font_size": lambda: self.change_font_size(1),
            "decrease_font_size": lambda: self.change_font_size(-1),
            **self.quick_actions,
        }
        for action, kind in (("bold", "bold"), ("italic", "italic"), ("underline", "underline"), ("strike", "strike"), ("inline_code", "code")):
            actions[action] = lambda kind=kind: self.edit.toggle_format(kind)
        for number in range(1, 10):
            actions[f"choice_{number}"] = lambda row=number - 1: self.choose_numbered(row)
        for action, callback in actions.items():
            for key in self.bindings[action]:
                self.bind(key, callback)
        self.spelling_panel.list.commands = self.edit.commands
        self.table_picker.grid.commands = self.edit.commands
        self.refresh_histories()

    def show_spelling_selection(self):
        if not hasattr(self, "spelling_panel"):
            return
        error = self.spelling.selected_error()
        if error:
            self.table_picker.hide()
            self.spelling_panel.open(error)
        else:
            self.spelling_panel.hide()

    def choose_numbered(self, row):
        if self.spelling_panel.isVisible():
            self.spelling_panel.choose(row)
        else:
            self.insert_history(self.active_history, row)

    def insert_markdown(self, markdown, placeholder=None):
        cursor = self.edit.textCursor()
        start = cursor.selectionStart()
        cursor.beginEditBlock()
        if self.edit.rich:
            document = QTextDocument()
            document.setDefaultFont(self.edit.font())
            document.setMarkdown(markdown)
            self.edit.insertHtml(document.toHtml())
            self.style_tables()
        else:
            self.edit.insertPlainText("\n\n" + markdown + "\n\n")
        end = self.edit.textCursor().position()
        cursor.endEditBlock()
        if placeholder:
            selected = self.edit.document().find(placeholder, start)
            if not selected.isNull() and selected.selectionEnd() <= end:
                self.edit.setTextCursor(selected)
        self.edit.ensureCursorVisible()
        self.edit.setFocus()

    def style_tables(self):
        def visit(frame):
            for child in frame.childFrames():
                if isinstance(child, QTextTable):
                    fmt = child.format()
                    fmt.setBorder(1)
                    fmt.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
                    fmt.setBorderBrush(QColor("#414b41"))
                    fmt.setCellPadding(6)
                    fmt.setCellSpacing(0)
                    fmt.setWidth(QTextLength(QTextLength.Type.PercentageLength, 96))
                    fmt.setHeaderRowCount(1)
                    child.setFormat(fmt)
                visit(child)
        visit(self.edit.document().rootFrame())

    def insert_table(self, rows, columns):
        header = "| " + " | ".join(f"Column {i + 1}" for i in range(columns)) + " |"
        separator = "| " + " | ".join("---" for _ in range(columns)) + " |"
        body = ["| " + " | ".join(" " for _ in range(columns)) + " |" for _ in range(rows - 1)]
        self.insert_markdown("\n".join([header, separator, *body]), "Column 1")

    def toggle_table_picker(self):
        self.spelling_panel.hide()
        if self.table_picker.isVisible():
            self.table_picker.hide()
            self.edit.setFocus()
        else:
            self.table_picker.open()

    def hideEvent(self, event):
        self.table_picker.hide()
        self.spelling_panel.hide()
        super().hideEvent(event)

    def update_word_count(self):
        count = len(self.edit.toPlainText().split())
        self.word_count.setText(f"{count} {'word' if count == 1 else 'words'}")

    def highlight_history(self, index):
        self.active_history = index
        for number, header in enumerate(self.history_headers):
            active = number == index
            color = "#007e00" if active else "#414d43"
            header.setStyleSheet(f"QWidget#shelfHeader {{ background: transparent; border: none; border-bottom: {3 if active else 1}px solid {color}; }}")
            self.history_keys[number].setText(f"{shortcut_label(self.bindings, 'choice_1')} … {shortcut_label(self.bindings, 'choice_9')}" if active else shortcut_label(self.bindings, "history_left" if number == 0 else "history_right"))

    def refresh_histories(self):
        for title, listing, history, label in zip(("Recents", "Clipboard"), self.history_lists, (self.entry_history, self.clipboard_history), self.history_titles):
            label.setText(f"{title}   {len(history.entries)}")
            listing.clear()
            for index, entry in enumerate(history.entries):
                preview = " ".join(entry.text.split())
                item = QListWidgetItem(preview[:200])
                item.setSizeHint(QSize(0, 29))
                item.setData(Qt.ItemDataRole.UserRole, index)
                item.setToolTip(entry.text[:2000])
                listing.addItem(item)
            if not history.entries:
                item = QListWidgetItem("Close a draft to keep it here" if title == "Recents" else "Copy text to keep it here")
                item.setSizeHint(QSize(0, 29))
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                listing.addItem(item)

    def remember_entry(self, text, html=None):
        if self.entry_history.add(text, html):
            self.refresh_histories()
            self.history_changed.emit()

    def remember_clipboard(self, text, html=None):
        if self.clipboard_history.add(text, html):
            self.refresh_histories()
            self.history_changed.emit()

    def insert_history(self, index, row):
        self.highlight_history(index)
        entries = (self.entry_history, self.clipboard_history)[index].entries
        if row is None or not 0 <= row < len(entries):
            return
        entry = entries[row]
        if self.edit.rich and entry.html:
            self.edit.insertHtml(entry.html)
        elif self.edit.rich:
            doc = QTextDocument()
            doc.setMarkdown(entry.text)
            self.edit.insertHtml(doc.toHtml())
        else:
            self.edit.insertPlainText(entry.text)
        self.edit.setFocus()

    def bind(self, key, callback):
        shortcut = QShortcut(QKeySequence(key), self)
        shortcut.activated.connect(callback)
        self.shortcuts.append(shortcut)
        self.edit.commands[QKeySequence(key).toString()] = callback

    def draft_markdown(self):
        if not self.edit.rich:
            return self.edit.toPlainText()
        if self.raw_snapshot is not None and self.edit.toHtml() == self.rendered_snapshot:
            return self.raw_snapshot
        return export_markdown(self.edit.document())

    def payload(self):
        """Convert only at the transfer boundary; the destination chooses a MIME type."""
        markdown = self.draft_markdown()
        if self.edit.rich:
            return markdown, self.edit.toHtml(), self.edit.toPlainText()
        document = QTextDocument()
        document.setMarkdown(markdown)
        return markdown, document.toHtml(), document.toPlainText()

    def apply_view_font(self, rendered):
        family = "Bitstream Charter" if rendered else "Nimbus Mono PS"
        size = self.font_size
        self.edit.setStyleSheet(f"QTextEdit {{ font-family: '{family}'; font-size: {size}px; }}")
        self.edit.document().setDefaultFont(self.edit.font())

    def change_font_size(self, direction):
        size = max(10, min(48, self.font_size + direction))
        if size == self.font_size:
            return
        pristine = self.edit.rich and self.raw_snapshot is not None and self.edit.toHtml() == self.rendered_snapshot
        self.font_size = size
        self.apply_view_font(self.edit.rich)
        if pristine:
            self.rendered_snapshot = self.edit.toHtml()
        self.table_controls.hide()
        self.spelling_panel.hide()
        self.font_size_changed.emit(size)

    def shutdown(self):
        # Detach the Python highlighter before Qt tears down its text document.
        self.hide()
        self.highlighter.set_enabled(False)
        self.spelling.timer.stop()

    def change_mode(self, index):
        rendered = bool(index)
        if rendered == self.edit.rich:
            return
        markdown = self.draft_markdown()
        self.highlighter.set_enabled(not rendered)
        self.apply_view_font(rendered)
        if rendered:
            self.edit.setMarkdown(markdown)
            self.style_tables()
            self.raw_snapshot = markdown
            self.rendered_snapshot = self.edit.toHtml()
        else:
            self.edit.setPlainText(markdown)
        self.edit.rich = rendered
        self.edit.setAcceptRichText(rendered)
        self.edit.setFocus()

    def open_draft(self, text, rich=False, html=None, label="", caret=None):
        # Destination capability never selects the editing mode.
        markdown = text
        if rich and html:
            document = QTextDocument()
            document.setHtml(html)
            markdown = export_markdown(document)
        rendered = bool(self.mode.currentIndex())
        self.edit.rich = rendered
        self.edit.setAcceptRichText(rendered)
        self.highlighter.set_enabled(not rendered)
        self.apply_view_font(rendered)
        if rendered:
            self.edit.setMarkdown(markdown)
            self.style_tables()
            self.raw_snapshot = markdown
            self.rendered_snapshot = self.edit.toHtml()
        else:
            self.edit.setPlainText(markdown)
            self.raw_snapshot = None
            self.rendered_snapshot = None
        cursor = self.edit.textCursor()
        # AT-SPI offsets count Unicode code points, Qt counts UTF-16 units.
        offset = len(markdown[:caret].encode("utf-16-le")) // 2 if caret is not None and not rendered and not rich else self.edit.document().characterCount() - 1
        cursor.setPosition(min(offset, self.edit.document().characterCount() - 1))
        self.edit.setTextCursor(cursor)
        self.status.setText(f"Editing {label or 'text field'}")
        geometry = self.screen().availableGeometry()
        self.resize(int(geometry.width() * .5), int(geometry.height() / 3))
        self.move(geometry.center() - self.rect().center())
        self.show()
        self.raise_()
        self.activateWindow()
        self.edit.setFocus()

    def closeEvent(self, event):
        event.ignore()
        self.cancelled.emit()
