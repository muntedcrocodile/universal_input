"""Floating editor. This module never reads or writes another application."""
from PyQt6.QtCore import Qt, QEvent, QSize, pyqtSignal
from PyQt6.QtGui import QFont, QKeySequence, QShortcut, QTextCharFormat, QTextCursor, QTextDocument, QTextTable, QTextLength, QTextFrameFormat, QColor
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QTextEdit, QVBoxLayout, QWidget, QListWidget, QListWidgetItem, QFrame,
    QToolButton,
)

from .history import History
from .tables import TableControls
from .table_picker import TablePicker
from .markdown import export_markdown
from .design import DragBar, ResizeGrip, HistoryDelegate, ModeComboBox, STYLESHEET


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

    def __init__(self, entry_history=None, clipboard_history=None):
        super().__init__()
        self.setWindowTitle("Universal Input")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.X11BypassWindowManagerHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(0.96)
        self.edit = DraftEdit()
        self.table_controls = TableControls(self.edit)
        self.heading = QLabel("Universal Input")
        self.heading.setObjectName("brand")
        self.heading.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.mode = ModeComboBox()
        self.mode.addItems(["Raw", "Markdown rendered"])
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
        self.send = QPushButton("Insert    Ctrl+↵")
        self.send.setObjectName("primaryAction")
        self.send.clicked.connect(self.commit_requested)
        cancel = QPushButton("Close    Esc")
        cancel.setObjectName("escapeAction")
        cancel.setToolTip("Save this draft to Recents and close")
        cancel.clicked.connect(self.cancelled)
        bar = DragBar()
        bar.setObjectName("commandBar")
        header = QHBoxLayout(bar)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(3)
        header.addWidget(self.mode)
        self.table_button = QToolButton()
        self.table_button.setText("Table ▾")
        self.table_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table_button.setToolTip("Choose table size · Ctrl+Alt+T")
        self.table_button.clicked.connect(self.toggle_table_picker)
        header.addWidget(self.table_button)
        for label, markdown in [
            ("Code", "```text\ncode\n```"),
            ("Tasks", "- [ ] First task\n- [ ] Second task"),
            ("Quote", "> Quoted text"),
            ("Link", "[link text](https://example.com)"),
            ("Divider", "---"),
        ]:
            button = QToolButton()
            button.setText(label)
            button.setToolTip(f"Insert {label.lower()}")
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(lambda checked=False, markdown=markdown: self.insert_markdown(markdown))
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
        history_hint = QLabel("Ctrl + ← / →  choose history      Alt + 1–9  insert      Ctrl + 1 / 2  change view")
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
        self.setStyleSheet(STYLESHEET)
        self.apply_view_font(False)
        self.shortcuts = []
        for key, callback in [
            ("Ctrl+Return", self.commit_requested.emit), ("Ctrl+Enter", self.commit_requested.emit),
            ("Escape", self.cancelled.emit),
            ("Ctrl+Alt+T", self.toggle_table_picker),
            ("Ctrl+1", lambda: self.mode.setCurrentIndex(0)),
            ("Ctrl+2", lambda: self.mode.setCurrentIndex(1)),
            ("Ctrl+Left", lambda: self.highlight_history(0)),
            ("Ctrl+Right", lambda: self.highlight_history(1)),
            ("Ctrl+Shift+M", lambda: self.mode.setCurrentIndex(1 - self.mode.currentIndex())),
        ]:
            self.bind(key, callback)
        for key, kind in [("Ctrl+B", "bold"), ("Ctrl+I", "italic"), ("Ctrl+U", "underline"), ("Ctrl+Shift+X", "strike"), ("Ctrl+`", "code")]:
            self.bind(key, lambda kind=kind: self.edit.toggle_format(kind))

        for number in range(1, 10):
            self.bind(f"Alt+{number}", lambda row=number - 1: self.insert_history(self.active_history, row))
        self.refresh_histories()

    def insert_markdown(self, markdown):
        if self.edit.rich:
            document = QTextDocument()
            document.setDefaultFont(self.edit.font())
            document.setMarkdown(markdown)
            self.edit.insertHtml(document.toHtml())
            self.style_tables()
        else:
            self.edit.insertPlainText("\n\n" + markdown + "\n\n")
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
        self.insert_markdown("\n".join([header, separator, *body]))

    def toggle_table_picker(self):
        if self.table_picker.isVisible():
            self.table_picker.hide()
            self.edit.setFocus()
        else:
            self.table_picker.open()

    def hideEvent(self, event):
        self.table_picker.hide()
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
            self.history_keys[number].setText("Alt 1–9" if active else ("Ctrl ←" if number == 0 else "Ctrl →"))

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
        family, size = ("Bitstream Charter", 19) if rendered else ("Nimbus Mono PS", 16)
        self.edit.setStyleSheet(f"QTextEdit {{ font-family: '{family}'; font-size: {size}px; }}")
        self.edit.document().setDefaultFont(self.edit.font())

    def change_mode(self, index):
        rendered = bool(index)
        if rendered == self.edit.rich:
            return
        markdown = self.draft_markdown()
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
