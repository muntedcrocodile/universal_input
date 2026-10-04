# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Small compatibility fixes for Qt's Markdown writer."""
import re
from PyQt6.QtGui import QFont, QTextCursor, QTextBlockFormat, QTextCharFormat


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
    lines = document.toMarkdown().splitlines(keepends=True)
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
