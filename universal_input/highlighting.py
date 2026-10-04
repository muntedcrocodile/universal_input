"""Pygments tokenization displayed through Qt's non-destructive highlighter."""
from collections import defaultdict

from pygments.lexers.markup import MarkdownLexer
from pygments.style import Style
from pygments.token import Token, Comment, Keyword, Name, Number, String, Generic, Error
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat


class EditorStyle(Style):
    """VS Code dark token palette with blue accents replaced by our green."""
    styles = {
        Token: '#d4d4d4', Comment: '#6a9955', Keyword: '#007e00',
        Name.Function: '#dcdcaa', Name.Builtin: '#dcdcaa', Name.Class: '#4ec9b0',
        Number: '#b5cea8', String: '#ce9178', String.Regex: '#d16969',
        Generic.Heading: 'bold #007e00', Generic.Subheading: 'bold #007e00',
        Generic.Strong: 'bold', Generic.Emph: 'italic #c586c0',
        Generic.Inserted: '#b5cea8', Generic.Deleted: '#ce9178', Error: '#f44747',
    }


class MarkdownHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        self.source_document = document
        self.enabled = True
        self.spans = {}
        self.formats = {}
        self.lexer = MarkdownLexer(handlecodeblocks=True)
        self.style = EditorStyle
        super().__init__(document)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.refresh)
        document.contentsChange.connect(self.changed)

    def changed(self, position, removed, added):
        if self.enabled and (removed or added):
            self.timer.start()

    def set_enabled(self, enabled):
        if enabled == self.enabled:
            return
        self.enabled = enabled
        self.timer.stop()
        self.spans = {}
        self.setDocument(self.source_document if enabled else None)
        if enabled:
            self.refresh()

    def token_format(self, token):
        if token not in self.formats:
            style = self.style.style_for_token(token)
            fmt = QTextCharFormat()
            if style["color"]:
                fmt.setForeground(QColor("#" + style["color"]))
            if style["bold"]:
                fmt.setFontWeight(QFont.Weight.Bold)
            if style["italic"]:
                fmt.setFontItalic(True)
            if style["underline"]:
                fmt.setFontUnderline(True)
            self.formats[token] = fmt
        return self.formats[token]

    def refresh(self):
        if not self.enabled:
            return
        text = self.source_document.toPlainText()
        spans = defaultdict(list)
        block, column = 0, 0
        # The final newline lets the Markdown lexer recognize a closing fence or
        # heading on the last line. It never changes the actual document.
        for _, token, value in self.lexer.get_tokens_unprocessed(text + "\n"):
            fmt = self.token_format(token)
            # Consume in stream order: Pygments 2.18 reports relative offsets for
            # tokens inside fenced blocks. Qt also counts UTF-16, not code points.
            pieces = value.split("\n")
            for index, piece in enumerate(pieces):
                length = len(piece.encode("utf-16-le")) // 2
                if length:
                    spans[block].append((column, length, fmt))
                    column += length
                if index < len(pieces) - 1:
                    block += 1
                    column = 0
        self.spans = dict(spans)
        self.rehighlight()

    def highlightBlock(self, text):
        if self.enabled:
            for start, length, fmt in self.spans.get(self.currentBlock().blockNumber(), ()):
                self.setFormat(start, length, fmt)
