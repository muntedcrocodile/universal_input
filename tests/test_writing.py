# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
import yaml

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtTest import QTest

from universal_input.editor import EditorWindow
from universal_input.storage import Store, atomic_yaml
from universal_input.writing import writing_issues


@pytest.mark.parametrize("rendered", [False, True])
@pytest.mark.parametrize("typed,expected", [
    ("ill go ", "I'll go "), ("ill check ", "I'll check "),
    ("im ready. ", "I'm ready. "), ("i dont know!", "I don't know!"),
    ("teh cat ", "the cat "), ("Thier book ", "Their book "),
    ("ive received it,", "I've received it,"),
    ("feel ill ", "feel ill "), ("ill health ", "ill health "),
    ("ill will ", "ill will "), ("the ill have ", "the ill have "),
    ("well were cant wont hell ", "well were cant wont hell "),
    ("IM IVE ", "IM IVE "),
])
def test_typing_corrections_and_ambiguous_words(app, rendered, typed, expected):
    window = EditorWindow()
    window.mode.setCurrentIndex(int(rendered))
    QTest.keyClicks(window.edit, typed)
    assert window.edit.content_text() == expected
    assert window.edit.textCursor().position() == len(expected)


@pytest.mark.parametrize("rendered", [False, True])
def test_autocorrect_undo_redo_and_continue(app, rendered):
    window = EditorWindow()
    window.mode.setCurrentIndex(int(rendered))
    QTest.keyClicks(window.edit, "dont ")
    assert window.edit.content_text() == "don't "
    QTest.keyClick(window.edit, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert window.edit.content_text() == "dont "
    QTest.qWait(220)
    assert window.edit.content_text() == "dont "  # Checking never reapplies it.
    window.edit.redo()
    assert window.edit.content_text() == "don't "
    window.edit.undo()
    QTest.keyClicks(window.edit, "change ")
    assert window.edit.content_text() == "dont change "


@pytest.mark.parametrize("rendered", [False, True])
def test_loaded_text_is_only_suggested_and_unicode_positions(app, rendered):
    window = EditorWindow()
    window.open_draft("🦎 ill go and dont worry. They is ready. the the book")
    window.mode.setCurrentIndex(int(rendered))
    before = window.edit.toHtml()
    window.spelling.refresh()
    errors = window.spelling.errors
    assert [(e.word, e.suggestions) for e in errors] == [
        ("ill", ("I'll",)), ("dont", ("don't",)), ("is", ("are",)), ("the the", ("The",)),
    ]
    assert errors[0].start == 3
    assert window.edit.toHtml() == before
    window.edit.moveCursor(QTextCursor.MoveOperation.Start)
    window.spelling.jump(1)
    assert window.spelling_panel.suggestions == ["I'll"]
    QTest.keyClick(window.edit, Qt.Key.Key_Return)
    assert window.edit.content_text().startswith("🦎 I'll go")


@pytest.mark.parametrize("rendered", [False, True])
def test_grammar_popup_navigation_and_no_dictionary_action(app, tmp_path, rendered):
    dictionary = tmp_path / "words.txt"
    window = EditorWindow(personal_dictionary=dictionary)
    window.open_draft("They is ready. A apple. The the book.")
    window.mode.setCurrentIndex(int(rendered))
    window.edit.moveCursor(QTextCursor.MoveOperation.Start)
    window.spelling.jump(1)
    panel = window.spelling_panel
    assert panel.isVisible()
    assert panel.title.text().startswith("Grammar: is")
    assert panel.suggestions == ["are"]
    assert panel.list.count() == 1
    QTest.keyClick(window.edit, Qt.Key.Key_A, Qt.KeyboardModifier.AltModifier)
    assert dictionary.read_text() == ""
    assert panel.isVisible()
    QTest.keyClick(window.edit, Qt.Key.Key_1, Qt.KeyboardModifier.AltModifier)
    assert window.edit.content_text().startswith("They are ready")
    window.spelling.jump(1)
    assert panel.suggestions == ["An"]
    panel.choose(0)
    window.spelling.jump(1)
    assert panel.suggestions == ["The"]
    panel.choose(0)
    assert window.edit.content_text() == "They are ready. An apple. The book."


@pytest.mark.parametrize("rendered", [False, True])
def test_checks_skip_code_destinations_and_email(app, rendered):
    window = EditorWindow()
    window.edit.setPlainText("`dont they is`\n\n```text\nill go\na apple\n```\n\nhttps://dont.example/a\ndont@example.com\n[label](https://dont.example)\n\nThey is ready.")
    window.mode.setCurrentIndex(int(rendered))
    window.spelling.refresh()
    assert [(e.word, e.kind) for e in window.spelling.errors] == [("is", "grammar")]


@pytest.mark.parametrize("prefix", ["`", "``", "```text\n", "~~~text\n", "https://", "www.", "name@", "[label](https://"])
def test_autocorrect_skips_raw_nonprose(app, prefix):
    window = EditorWindow()
    window.edit.setPlainText(prefix)
    cursor = window.edit.textCursor()
    cursor.setPosition(len(prefix))
    window.edit.setTextCursor(cursor)
    QTest.keyClicks(window.edit, "dont ")
    assert window.edit.content_text() == prefix + "dont "


@pytest.mark.parametrize("rendered", [False, True])
def test_enter_autocorrect_and_unicode_caret(app, rendered):
    window = EditorWindow()
    window.mode.setCurrentIndex(int(rendered))
    window.edit.setPlainText("🦎 ")
    cursor = window.edit.textCursor()
    cursor.setPosition(3)
    window.edit.setTextCursor(cursor)
    QTest.keyClicks(window.edit, "ill go")
    QTest.keyClick(window.edit, Qt.Key.Key_Return)
    assert window.edit.content_text() == "🦎 I'll go\n"
    assert window.edit.textCursor().position() == 11
    window.edit.undo()
    assert window.edit.content_text() == "🦎 ill go\n"
    assert window.edit.textCursor().position() == 10


@pytest.mark.parametrize("rendered", [False, True])
def test_nonprose_does_not_form_grammar_phrases(app, rendered):
    window = EditorWindow()
    window.edit.setPlainText("They `example` is. The ``dont`` the.")
    window.mode.setCurrentIndex(int(rendered))
    window.spelling.refresh()
    assert window.spelling.errors == []


def test_rendered_fenced_code_is_not_autocorrected(app):
    window = EditorWindow()
    window.edit.setPlainText("```text\ndont\n```")
    window.mode.setCurrentIndex(1)
    cursor = window.edit.document().find("dont")
    cursor.clearSelection()
    window.edit.setTextCursor(cursor)
    QTest.keyClicks(window.edit, " ")
    assert "dont " in window.edit.content_text()
    window.spelling.refresh()
    assert window.spelling.errors == []


def test_rich_inline_code_and_bold_autocorrect(app):
    window = EditorWindow()
    window.mode.setCurrentIndex(1)
    window.edit.toggle_format("code")
    QTest.keyClicks(window.edit, "dont ")
    assert window.edit.content_text() == "dont "
    window.edit.toggle_format("code")
    window.edit.toggle_format("bold")
    QTest.keyClicks(window.edit, "dont ")
    assert window.edit.content_text() == "dont don't "
    cursor = window.edit.textCursor()
    cursor.setPosition(5)
    cursor.setPosition(10, QTextCursor.MoveMode.KeepAnchor)
    assert cursor.charFormat().fontWeight() == QFont.Weight.Bold


def test_paste_is_not_rewritten_and_settings_disable_features(app):
    window = EditorWindow(autocorrect=False, grammar_check=False)
    QTest.keyClicks(window.edit, "dont They is ")
    assert window.edit.content_text() == "dont They is "
    window.spelling.refresh()
    assert [(e.word, e.kind) for e in window.spelling.errors] == [("dont", "spelling")]
    window.spelling.autocorrect_enabled = True
    app.clipboard().setText("ill go dont They is")
    window.edit.selectAll()
    window.edit.paste()
    assert window.edit.content_text() == "ill go dont They is"
    window.spelling.refresh()
    assert window.edit.content_text() == "ill go dont They is"


def test_rules_are_disabled_for_non_english(app):
    window = EditorWindow()
    window.spelling.english = False  # No additional dictionary installation required.
    QTest.keyClicks(window.edit, "dont ill go ")
    assert window.edit.content_text() == "dont ill go "
    window.spelling.refresh()
    assert not any(e.suggestions or e.kind == "grammar" for e in window.spelling.errors)


@pytest.mark.parametrize("text", ["I am well. She has it. We have it.", "Does she have it? Did he do it?", "If I were there, he would know.", "a university and an hour", "had had that that", "dont_change im2", "ill health and ill will", "feeling ill before work"])
def test_valid_grammar_and_identifiers(text):
    assert not writing_issues(text)


def test_quoted_words_and_curly_apostrophes():
    assert [issue.replacement for issue in writing_issues("'dont' ‘i’m’")] == ["don't", "I’m"]


@pytest.mark.parametrize("rendered", [False, True])
@pytest.mark.parametrize("text,expected", [
    ("First sentence. next sentence ", "First sentence. Next sentence "),
    ("Ready? yes! lets go ", "Ready? Yes! Lets go "),
    ('Done. "next step ', 'Done. "Next step '),
    ("Done. teh book ", "Done. The book "),
    ("Done. ill go ", "Done. I'll go "),
    ("Ask Dr. smith ", "Ask Dr. smith "),
    ("It is e.g. green ", "It is e.g. green "),
    ("It costs 3.14 each ", "It costs 3.14 each "),
    ("Wait... maybe ", "Wait... maybe "),
])
def test_sentence_capitalization_while_typing(app, rendered, text, expected):
    window = EditorWindow()
    window.mode.setCurrentIndex(int(rendered))
    QTest.keyClicks(window.edit, text)
    assert window.edit.content_text() == expected


def test_loaded_sentence_capitalization_is_a_suggestion(app):
    window = EditorWindow()
    window.open_draft("First sentence. next sentence. ill go.")
    window.spelling.refresh()
    assert [(e.word, e.suggestions) for e in window.spelling.errors] == [("next", ("Next",)), ("ill", ("I'll",))]
    assert window.edit.content_text() == "First sentence. next sentence. ill go."


def test_config_defaults_migration_and_validation(tmp_path):
    store = Store(tmp_path)
    config = yaml.safe_load(store.config_path.read_text())
    del config["autocorrect"]
    del config["grammar_check"]
    atomic_yaml(store.config_path, config)
    assert Store(tmp_path).config["autocorrect"] is True
    assert Store(tmp_path).config["grammar_check"] is True
    config.update(autocorrect=False, grammar_check=False)
    atomic_yaml(store.config_path, config)
    assert Store(tmp_path).config["autocorrect"] is False
    for key in ("autocorrect", "grammar_check"):
        atomic_yaml(store.config_path, dict(config, **{key: "false"}))
        with pytest.raises(RuntimeError, match=key):
            Store(tmp_path)
