# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Small compatibility fixes for Qt's Markdown writer."""
import re
from PyQt6.QtGui import QFont, QTextCursor, QTextBlockFormat, QTextCharFormat, QTextFormat, QTextListFormat


def unwrapped_markdown(document):
    """Export prose without Qt's hard-coded 80-column Markdown reflow.

    Protect source whitespace and mark prose block boundaries in the disposable
    clone. Any remaining newlines inside those markers came from the writer,
    so they can be removed without guessing which source breaks were authored.
    Code blocks and tables bypass this: Qt already exports them without wrapping.
    """
    contents = document.toHtml()
    whitespace = sorted({char for char in document.toRawText() if char.isspace() and char != "\u2029"})
    tokens = (chr(code) for code in range(0xe000, 0xf900) if chr(code) not in contents)
    start_token, end_token = next(tokens), next(tokens)
    protected = {char: next(tokens) for char in whitespace}
    translation = str.maketrans(protected)
    edits, continuations = [], []
    block = document.begin()
    while block.isValid():
        fmt = block.blockFormat()
        cursor = QTextCursor(block)
        is_code = (fmt.nonBreakableLines() or fmt.hasProperty(QTextFormat.Property.BlockCodeFence)
                   or bool(fmt.stringProperty(QTextFormat.Property.BlockCodeLanguage)))
        if block.text() and not is_code and cursor.currentTable() is None:
            fragments = []
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                fragments.append(fragment)
                iterator += 1
            for index, fragment in enumerate(fragments):
                text = fragment.text().translate(translation)
                marker_format = QTextCharFormat(fragment.charFormat())
                marker_format.setProperty(int(QTextFormat.Property.UserProperty) + 913, True)
                if index == 0:
                    edits.append((fragment.position(), 0, start_token, marker_format))
                if index == len(fragments) - 1:
                    edits.append((fragment.position() + fragment.length(), 0, end_token, marker_format))
                edits.append((fragment.position(), fragment.length(), text, fragment.charFormat()))
            continuation = "> " * fmt.intProperty(QTextFormat.Property.BlockQuoteLevel)
            if block.textList():
                list_format = block.textList().format()
                bullet = list_format.style() in (QTextListFormat.Style.ListDisc, QTextListFormat.Style.ListCircle, QTextListFormat.Style.ListSquare)
                continuation += " " * (list_format.indent() * (2 if bullet else 4))
            continuations.append(continuation)
        block = block.next()
    for position, length, text, fmt in sorted(edits, key=lambda edit: (edit[0], edit[1]), reverse=True):
        cursor = QTextCursor(document)
        cursor.setPosition(position)
        cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(text, fmt)
    continuations = iter(continuations)

    def restore(match):
        continuation = next(continuations)
        text = re.sub(r"\n(?:> )*[ \t]*", "", match.group(1))
        for char, token in protected.items():
            text = text.replace(token, "  \n" + continuation if char == "\u2028" else char)
        return text

    return re.sub(start_token + r"(.*?)" + end_token, restore, document.toMarkdown(), flags=re.DOTALL)


def export_markdown(document):
    # The writing font is a view preference, not an inline-code marker.
    document = document.clone()
    document.setDefaultFont(QFont('Sans Serif', 12))
    # Qt's writer can absorb a final empty prose block into the preceding code
    # fence. Extra empty prose blocks flush the fence; rstrip below drops them.
    end = QTextCursor(document)
    end.movePosition(QTextCursor.MoveOperation.End)
    for _ in range(2):
        end.insertBlock(QTextBlockFormat(), QTextCharFormat())
    lines = unwrapped_markdown(document).splitlines(keepends=True)
    fence = None
    for index, line in enumerate(lines):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence is not None:
            continue
        stripped = line.strip()
        # Qt emits zero dashes for a newly inserted empty table column.
        # GFM requires a nonempty delimiter for every column.
        if (index and stripped.startswith("|") and stripped.endswith("|")
                and "-" in stripped and re.fullmatch(r"[| :\-]+", stripped)
                and lines[index - 1].lstrip().startswith("|")):
            cells = stripped[1:-1].split("|")
            cells = [(":" if cell.strip().startswith(":") else "") + "---" +
                     (":" if cell.strip().endswith(":") else "") for cell in cells]
            lines[index] = "|" + "|".join(cells) + "|" + ("\n" if line.endswith("\n") else "")
    return "".join(lines).rstrip("\n")
