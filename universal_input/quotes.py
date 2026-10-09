# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Paint rendered blockquote bars in the document's existing quote margins."""
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QTextFormat


def quote_bars(editor):
    if not editor.rich:
        return
    document = editor.document()
    layout = document.documentLayout()
    dx = -editor.horizontalScrollBar().value()
    dy = -editor.verticalScrollBar().value()
    block = document.begin()
    while block.isValid():
        rect = layout.blockBoundingRect(block).translated(dx, dy)
        if rect.top() > editor.viewport().height():
            break
        depth = block.blockFormat().intProperty(QTextFormat.Property.BlockQuoteLevel)
        following = block.next()
        next_depth = following.blockFormat().intProperty(QTextFormat.Property.BlockQuoteLevel) if following.isValid() else 0
        if depth and rect.bottom() >= 0:
            for level in range(1, depth + 1):
                bottom = rect.bottom()
                if next_depth >= level:
                    bottom = layout.blockBoundingRect(following).top() + dy
                # Qt reserves 40 px per quote level when importing Markdown.
                x = rect.left() + 40 * level - 16
                yield QRectF(x, rect.top(), 3, bottom - rect.top())
        block = following


def paint_quote_bars(editor, painter):
    for rect in quote_bars(editor):
        painter.fillRect(rect, QColor('#808080'))
