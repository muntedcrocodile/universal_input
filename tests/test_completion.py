# SPDX-FileCopyrightText: 2026 muntedcrocodile
# SPDX-License-Identifier: AGPL-3.0-or-later
import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QTextCursor
from PyQt6.QtTest import QTest

from universal_input.completion import DEFAULT_COMPLETION, InlineCompletion, LocalCompletion
from universal_input.completion_worker import Predictor, healing_prompt, matching_tokens, short_completion
from universal_input.editor import EditorWindow
from universal_input.storage import Store, atomic_json


class FakeBackend(QObject):
    result = pyqtSignal(int, str)

    def __init__(self):
        super().__init__()
        self.requests = []

    def request(self, generation, prefix):
        self.requests.append((generation, prefix))

    def cancel(self):
        pass

    def close(self):
        pass


def editor(text, position=None, rendered=False):
    window = EditorWindow(autocorrect=False, grammar_check=False)
    window.open_draft(text)
    if rendered:
        window.mode.setCurrentIndex(1)
        window.edit.moveCursor(QTextCursor.MoveOperation.Start)
        window.edit.moveCursor(QTextCursor.MoveOperation.EndOfBlock)
    backend = FakeBackend()
    completion = InlineCompletion(window.edit, backend, 20)
    window.completion = window.edit.completion = completion
    QTest.qWait(30)
    if position is not None:
        cursor = window.edit.textCursor()
        cursor.setPosition(position)
        window.edit.setTextCursor(cursor)
    completion.changed()
    return window, completion, backend


def suggest(completion, backend, text):
    completion.timer.stop()
    completion.request()
    generation, _ = backend.requests[-1]
    backend.result.emit(generation, text)
    return generation


@pytest.mark.parametrize("text,position,allowed", [
    ("hello", 5, True), ("hello world", 5, True),
    ("hello\nworld", 5, True), ("hello world", 3, False),
    ("hello world", 6, False), ("hello, world", 5, False),
    ("", 0, False), ("   ", 3, False), ("🦎 hello", 8, True),
])
def test_prediction_boundaries(app, text, position, allowed):
    window, completion, _ = editor(text, position)
    assert (completion.context() is not None) == allowed
    if text == "🦎 hello":
        assert completion.context() == text


@pytest.mark.parametrize("rendered", [False, True])
def test_ghost_is_not_content_and_tab_accepts_one_undo_step(app, rendered):
    window, completion, backend = editor("I am writ", rendered=rendered)
    before = window.payload()
    suggest(completion, backend, "ing")
    assert completion.suggestion == "ing"
    window.edit.viewport().grab()  # Exercise the paint path, including rich text.
    assert window.payload() == before
    QTest.keyClick(window.edit, Qt.Key.Key_Tab)
    assert window.edit.content_text() == "I am writing"
    assert window.edit.hasFocus()
    window.edit.undo()
    assert window.payload() == before


def test_completion_before_existing_space_preserves_suffix_and_unicode(app):
    window, completion, backend = editor("🦎 a simp example", 9)
    assert completion.context() == "🦎 a simp"
    suggest(completion, backend, "le")
    window.edit.viewport().grab()
    QTest.keyClick(window.edit, Qt.Key.Key_Tab)
    assert window.edit.content_text() == "🦎 a simple example"


def test_stale_results_selection_escape_hide_and_mode_changes(app):
    window, completion, backend = editor("hello")
    generation = suggest(completion, backend, " world")
    QTest.keyClicks(window.edit, "!")
    backend.result.emit(generation, " stale")
    assert not completion.suggestion
    suggest(completion, backend, " again")
    window.edit.selectAll()
    assert not completion.suggestion and completion.context() is None
    window.edit.moveCursor(QTextCursor.MoveOperation.Start)
    window.edit.moveCursor(QTextCursor.MoveOperation.EndOfBlock)
    suggest(completion, backend, " again")
    QTest.keyClick(window.edit, Qt.Key.Key_Escape)
    assert not completion.suggestion
    assert not completion.timer.isActive()
    suggest(completion, backend, " again")
    window.mode.setCurrentIndex(1)
    assert not completion.suggestion
    suggest(completion, backend, " again")
    window.hide()
    assert not completion.suggestion and not completion.timer.isActive()


def test_tab_chord_and_modified_tab_do_not_accept(app):
    window, completion, backend = editor("[hello](world) ")
    original = window.draft_markdown()
    suggest(completion, backend, "again")
    for modifier in (Qt.KeyboardModifier.ShiftModifier, Qt.KeyboardModifier.ControlModifier):
        QTest.keyClick(window.edit, Qt.Key.Key_Tab, modifier)
        assert window.draft_markdown() == original
    QTest.keyPress(window.edit, Qt.Key.Key_Tab)
    QTest.keyClick(window.edit, Qt.Key.Key_Left)
    QTest.keyRelease(window.edit, Qt.Key.Key_Tab)
    assert window.draft_markdown() == original
    assert window.edit.textCursor().hasSelection()


def test_debounce_only_requests_latest_prefix(app):
    window, completion, backend = editor("hello")
    backend.requests.clear()
    QTest.keyClicks(window.edit, " world")
    QTest.qWait(60)
    assert len(backend.requests) == 1
    assert backend.requests[0][1] == "hello world"


def test_context_payload_is_bounded(app):
    window, completion, _ = editor("hello " * 2000)
    assert len(completion.context()) <= 4096


@pytest.mark.parametrize("prefix,generated,expected", [
    ("I am writ", "ing a letter today", "ing"),
    ("I would like to ", " thank you for your help", "thank"),
    ("Thank you", " for your help today", " for"),
    ("A simp", "le", ""),
    ("Hello ", "world\nsecret", "world"),
    ("Hi ", "word\tword ", "word"),
    ("A simp", "le, example", "le,"),
    ("Hello ", "world\u00a0again", "world"),
    ("Hello ", "world\rnext", "world"),
    ("Hello ", "internationalisation ", "internationalisation"),
    ("Hello ", "unfinished", ""),
    ("Hello ", "\nnext word ", ""),
    ("Hello ", "bad\x00word ", ""),
])
def test_short_completion(prefix, generated, expected):
    assert short_completion(prefix, generated) == expected


def test_generation_waits_for_whitespace_across_tokens_and_healing(monkeypatch):
    monkeypatch.setitem(sys.modules, "llama_cpp", SimpleNamespace(
        LogitsProcessorList=list, StoppingCriteriaList=list))

    class Model:
        n_tokens = 1

        def tokenize(self, *_args, **_kwargs):
            return [0]

        def create_completion(self, **kwargs):
            stop = kwargs["stopping_criteria"][0]
            # Replayed " simp" includes whitespace; "le" completes the word
            # over further tokens, and the next token establishes its boundary.
            for tokens, expected in [([0, 1], False), ([0, 1, 2], False),
                                     ([0, 1, 2, 3], False), ([0, 1, 2, 3, 4], True)]:
                self.n_tokens = len(tokens)
                assert stop(tokens, None) is expected
            return {"choices": [{"text": " simple example", "finish_reason": "stop"}]}

    predictor = Predictor.__new__(Predictor)
    predictor.context_tokens, predictor.max_tokens = 128, 12
    predictor.model = Model()
    predictor.vocabulary = [b"context", b" sim", b"p", b"le", b" example"]
    assert predictor.predict("This is a simp") == "le"


@pytest.mark.parametrize("prefix,expected", [
    ("I am writ", ("I am", b" writ")),
    ("hello ", ("hello", b"")),
    ("hel", ("", b"hel")),
    ("🦎 café", ("🦎", " café".encode())),
])
def test_token_healing_preserves_typed_prefix(prefix, expected):
    assert healing_prompt(prefix) == expected


def test_token_healing_allows_only_prefix_compatible_tokens():
    vocabulary = [b"", b" write", b" writing", b" read", b" w", b" writ"]
    assert matching_tokens(b" writ", vocabulary) == [1, 2, 4, 5]


@pytest.mark.parametrize("settings", [
    {"automatic_popup": "false"}, {"completion": False},
    {"completion": {"enabled": 1}}, {"completion": {"context_tokens": 0}},
    {"completion": {"threads": 9}}, {"completion": {"model_path": []}},
])
def test_invalid_config_is_preserved(tmp_path, settings):
    atomic_json(tmp_path / "config.json", settings)
    with pytest.raises(RuntimeError, match="Invalid configuration"):
        Store(tmp_path)
    assert json.loads((tmp_path / "config.json").read_text()) == settings


def test_config_migration_preserves_manual_opening_and_other_settings(tmp_path):
    atomic_json(tmp_path / "config.json", {"automatic_popup": False, "editor_font_size": 25})
    store = Store(tmp_path)
    assert store.config["automatic_popup"] is False
    assert store.config["completion"] == DEFAULT_COMPLETION
    assert store.config["editor_font_size"] == 25


@pytest.mark.parametrize("automatic,paused,opens", [(False, False, False), (True, False, True), (True, True, False)])
def test_focus_tracks_source_but_only_opens_when_enabled(app, monkeypatch, automatic, paused, opens):
    from universal_input import accessibility
    from universal_input.app import Controller
    monkeypatch.setattr(accessibility, "is_editable", lambda _: True)
    source = Mock()
    source.get_process_id.return_value = -1
    source.get_state_set.return_value.contains.return_value = True
    controller = Controller.__new__(Controller)
    controller.busy = False
    controller.paused = paused
    controller.automatic_popup = automatic
    controller.suppressed_source = None
    controller.window = Mock()
    controller.window.isVisible.return_value = False
    controller.open_source = Mock()
    controller.on_focus(source)
    assert controller.last_source is source
    assert controller.open_source.called == opens


def test_backend_unavailable_does_not_block_editor(app, tmp_path):
    backend = LocalCompletion({**DEFAULT_COMPLETION, "python_path": str(tmp_path / "missing")})
    messages = []
    backend.unavailable.connect(messages.append)
    backend.start()
    assert backend.stopped and len(messages) == 1
    backend.request(1, "hello")
    assert backend.pending is None


def test_backend_coalesces_pending_requests_and_stops(app, tmp_path):
    # A deterministic subprocess exercises the actual asynchronous IPC path.
    script = tmp_path / "fake-worker"
    script.write_text(f'#!{sys.executable}\nimport json,sys,time\nprint(json.dumps({{"ready":True}}),flush=True)\n'
                      'for line in sys.stdin:\n r=json.loads(line); time.sleep(.06); print(json.dumps({"id":r["id"],"text":" next"}),flush=True)\n')
    script.chmod(0o700)
    model = tmp_path / "model.gguf"
    model.touch()
    backend = LocalCompletion({**DEFAULT_COMPLETION, "python_path": str(script), "model_path": str(model)})
    received = []
    backend.result.connect(lambda generation, text: received.append((generation, text)))
    backend.start()
    try:
        for _ in range(100):
            if backend.ready:
                break
            QTest.qWait(10)
        assert backend.ready
        backend.request(1, "first")
        backend.request(2, "second")
        backend.request(3, "latest")
        for _ in range(100):
            if len(received) == 2:
                break
            QTest.qWait(10)
        assert received == [(1, " next"), (3, " next")]
    finally:
        backend.close()
    assert not backend.process.processId()
