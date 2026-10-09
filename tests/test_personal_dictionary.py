# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QContextMenuEvent
from PyQt6.QtWidgets import QApplication, QMenu

from universal_input.editor import EditorWindow


def removal_actions(menu):
    return [action for action in menu.actions() if "from personal dictionary" in action.text()]


@pytest.mark.parametrize("rendered", [False, True])
def test_right_click_removes_saved_word_and_refreshes_spelling(app, tmp_path, monkeypatch, rendered):
    path = tmp_path / "words.txt"
    window = EditorWindow(personal_dictionary=path)
    window.spelling.add_word("zorbablax")
    window.spelling.add_word("Flibberzorp")
    window.open_draft("🦎 Zorbablax and Flibberzorp")
    window.mode.setCurrentIndex(int(rendered))
    window.edit.setTextCursor(window.edit.document().find("Zorbablax"))
    before = window.edit.toHtml()
    window.spelling.refresh()
    assert not window.spelling.errors
    opened = []

    def choose_removal(menu, position):
        actions = removal_actions(menu)
        assert len(actions) == 1
        assert "Zorbablax" in actions[0].text()
        assert any("Copy" in action.text() for action in menu.actions())
        opened.append(True)
        actions[0].trigger()

    monkeypatch.setattr(QMenu, "exec", choose_removal)
    position = window.edit.cursorRect().center()
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, position,
                             window.edit.viewport().mapToGlobal(position))
    QApplication.sendEvent(window.edit.viewport(), event)
    assert opened == [True]
    assert path.read_text().splitlines() == ["Flibberzorp"]
    assert path.stat().st_mode & 0o777 == 0o600
    assert [error.word for error in window.spelling.errors] == ["Zorbablax"]
    assert window.edit.toHtml() == before
    assert window.edit.textCursor().selectedText() == "Zorbablax"
    restored = EditorWindow(personal_dictionary=path)
    assert not restored.spelling.dictionary.check("Zorbablax")
    assert restored.spelling.dictionary.check("Flibberzorp")
    window.spelling.add_word("zorbablax")
    assert not window.spelling.errors  # Removal can be reversed by adding again.


@pytest.mark.parametrize("selection", ["colour", "unknownwordz", "Zorbablax colour", ""])
def test_remove_option_only_for_a_selected_personal_word(app, selection):
    window = EditorWindow()
    window.spelling.add_word("Zorbablax")
    window.edit.setPlainText("Zorbablax colour unknownwordz")
    if selection:
        window.edit.setTextCursor(window.edit.document().find(selection))
    menu = window.edit.createStandardContextMenu(QPoint(0, 0))
    assert not removal_actions(menu)
    menu.deleteLater()


@pytest.mark.parametrize("persistent", [False, True])
def test_removal_keeps_base_dictionary_and_supports_demo(app, tmp_path, persistent):
    path = tmp_path / "words.txt" if persistent else None
    window = EditorWindow(personal_dictionary=path)
    window.spelling.add_word("colour")
    window.edit.setPlainText("colour")
    window.edit.setTextCursor(window.edit.document().find("colour"))
    menu = window.edit.createStandardContextMenu()
    removal_actions(menu)[0].trigger()
    menu.deleteLater()
    assert window.spelling.personal_word("colour") is None
    assert window.spelling.dictionary.check("colour")
    assert not window.spelling.errors
    window.spelling.add_word("Zorbablax")
    window.spelling.remove_word("Zorbablax")
    assert not window.spelling.dictionary.check("Zorbablax")
    window.spelling.remove_word("Zorbablax")  # Stale action is harmless.
    if persistent:
        assert path.read_text() == ""


def test_removal_handles_curly_apostrophes(app, tmp_path):
    window = EditorWindow(personal_dictionary=tmp_path / "words.txt")
    window.spelling.add_word("zorb’s")
    assert window.spelling.personal_word("zorb’s") == "zorb's"
    window.spelling.remove_word("zorb’s")
    assert not window.spelling.dictionary.check("zorb's")
    assert not window.spelling.personal_words
