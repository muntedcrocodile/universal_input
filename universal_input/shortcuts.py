# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Application keybindings shared by the global grab, editor, and visible hints."""
from copy import deepcopy
from PyQt6.QtGui import QKeySequence

DEFAULT_BINDINGS = {
    "open": "Ctrl+Space",
    "insert": ["Ctrl+Return", "Ctrl+Enter"],
    "close": "Ctrl+Escape",
    "dismiss_popup": "Escape",
    "raw_mode": "Ctrl+1",
    "rendered_mode": "Ctrl+2",
    "toggle_mode": ["Ctrl+M", "Ctrl+Shift+M"],
    "bold": "Ctrl+B",
    "italic": "Ctrl+I",
    "underline": "Ctrl+U",
    "strike": "Ctrl+Shift+X",
    "inline_code": "Ctrl+`",
    "previous_misspelling": "Ctrl+Alt+Left",
    "next_misspelling": "Ctrl+Alt+Right",
    "spelling_suggestions": "Alt+Return",
    "add_to_dictionary": "Alt+A",
    "previous_part": "Tab+Left",
    "next_part": "Tab+Right",
    "indent": "Ctrl+]",
    "dedent": "Ctrl+[",
    "select_line": "Ctrl+L",
    "goto_line": "Ctrl+G",
    "insert_history_number": "Alt+I",
    "increase_font_size": ["Ctrl+Shift++", "Ctrl+Shift+=", "Ctrl++"],
    "decrease_font_size": ["Ctrl+Shift+-", "Ctrl+Shift+_"],
    "history_left": "Ctrl+R",
    "history_right": "Ctrl+P",
    **{f"choice_{number}": f"Alt+{number}" for number in range(1, 10)},
}


def normalize_bindings(overrides=None, quick_insert=None):
    from .quick_insert import normalize_quick_insert
    items = normalize_quick_insert(quick_insert)
    if overrides is not None and not isinstance(overrides, dict):
        raise ValueError("keybindings must be an object")
    bindings = deepcopy(DEFAULT_BINDINGS)
    for item in items:
        if item["id"] in bindings:
            raise ValueError(f"quick_insert id conflicts with application action: {item['id']}")
        bindings[item["id"]] = item.get("shortcut", [])
    for action, value in (overrides or {}).items():
        if action not in bindings:
            raise ValueError(f"Unknown keybinding action: {action}")
        bindings[action] = value
    owners = {}
    for action, value in bindings.items():
        values = [value] if isinstance(value, str) else value
        if not isinstance(values, list) or any(not isinstance(key, str) for key in values):
            raise ValueError(f"{action}: use a shortcut string or a list of strings")
        normalized = []
        for key in values:
            if not key.strip():
                continue
            held_tab = key.startswith("Tab+")
            if held_tab and action == "open":
                raise ValueError("The global open shortcut cannot use Tab as a modifier")
            sequence = QKeySequence.fromString(key[4:] if held_tab else key, QKeySequence.SequenceFormat.PortableText)
            canonical = sequence.toString(QKeySequence.SequenceFormat.PortableText)
            if sequence.count() != 1 or not canonical or int(sequence[0].key()) in (0, 0x01ffffff):
                raise ValueError(f"{action}: invalid single-chord shortcut {key!r}")
            if held_tab:
                canonical = "Tab+" + canonical
            owner = owners.get(canonical)
            if owner and owner != action:
                raise ValueError(f"Shortcut {canonical} is assigned to both {owner} and {action}")
            owners[canonical] = action
            if canonical not in normalized:
                normalized.append(canonical)
        bindings[action] = normalized
    return bindings


def label(bindings, action):
    keys = bindings.get(action, [])
    return keys[0] if keys else ""
