"""Closing must never silently drop a rigger's work."""

from __future__ import annotations

import pytest

from tik.shared.ui import feedback
from tik.shared.ui.Qt import QtGui
from tik.trigger.core import Action, StringField, clear_registries, register_action
from tik.trigger.ui.main import TriggerWindow


class Mark(Action):
    """A throwaway action, so ``add_action`` really dirties the session."""

    label = "Mark"
    tag = StringField("")

    def run(self, ctx):
        pass


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_action("mark", category="build")(Mark)
    yield
    clear_registries()


@pytest.fixture
def window(qapp):
    made = TriggerWindow()
    yield made
    # never let a stuck dialog hang teardown
    made.ask_save_discard = lambda session: "discard"
    made.close()


@pytest.fixture(autouse=True)
def _clean_seams():
    previous = feedback.set_handler(None)
    yield
    feedback.set_handler(previous)


def _answer(window, *replies):
    """Queue answers for ask_save_discard and record what it was asked."""
    asked = []
    answers = list(replies)

    def ask(session):
        asked.append(session.name)
        return answers.pop(0) if answers else "cancel"

    window.ask_save_discard = ask
    return asked


def test_a_clean_tab_closes_without_asking(window):
    asked = _answer(window, "cancel")
    assert window.close_tab(0) is True
    assert asked == []


def test_discard_closes_the_tab(window):
    window.current_view.add_action("mark")
    asked = _answer(window, "discard")
    assert window.close_tab(0) is True
    assert asked == ["untitled"]


def test_cancel_keeps_the_tab(window):
    view = window.current_view
    view.add_action("mark")
    _answer(window, "cancel")
    assert window.close_tab(0) is False
    assert window.tabs.count() == 1
    assert window.current_view is view


def test_save_writes_the_session_then_closes(window, tmp_path, monkeypatch):
    view = window.current_view
    view.add_action("mark")
    target = tmp_path / "hero.tr"
    monkeypatch.setattr(
        feedback.Feedback, "browse_save", lambda self, *args, **kwargs: str(target)
    )
    _answer(window, "save")
    assert window.close_tab(0) is True
    assert target.exists()


def test_a_cancelled_save_as_blocks_the_close(window, monkeypatch):
    view = window.current_view
    view.add_action("mark")
    monkeypatch.setattr(
        feedback.Feedback, "browse_save", lambda self, *args, **kwargs: ""
    )
    _answer(window, "save")
    assert window.close_tab(0) is False
    assert window.tabs.count() == 1


def test_close_event_asks_once_per_dirty_tab(window):
    window.current_view.add_action("mark")
    second = window.new_session()
    second.add_action("mark")
    asked = _answer(window, "discard", "discard")
    event = QtGui.QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted() is True
    assert len(asked) == 2


def test_cancel_on_the_second_tab_aborts_the_whole_close(window, tmp_path):
    """The first tab is saved and stays saved -- Cancel stops the close, it
    does not roll a completed save back."""
    first = window.current_view
    first.add_action("mark")
    first.session.save(str(tmp_path / "first.tr"))
    first.add_action("mark")
    second = window.new_session()
    second.add_action("mark")

    asked = _answer(window, "save", "cancel")
    event = QtGui.QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted() is False
    assert asked == ["first.tr", "untitled"]
    assert first.session.is_modified is False


def test_guide_drift_is_captured_before_the_dirty_check(window):
    """Nothing in Maya fires when a guide is dragged, so a clean-looking
    session must be re-read from the scene before we believe it."""
    view = window.current_view
    window._checked_out_view = view
    captured = []

    def capture():
        captured.append(True)
        view.session.document.meta["dragged"] = "yes"
        return True

    view.session.capture_guides = capture
    asked = _answer(window, "discard")
    assert window.close_tab(0) is True
    assert captured == [True]
    assert asked == ["untitled"]


def test_a_tab_that_does_not_own_the_scene_is_not_captured(window):
    view = window.current_view
    window._checked_out_view = None
    called = []
    view.session.capture_guides = lambda: called.append(True)
    window.close_tab(0)
    assert called == []


def test_a_failing_capture_does_not_trap_the_window(window):
    view = window.current_view
    window._checked_out_view = view

    def explode():
        raise RuntimeError("no scene")

    view.session.capture_guides = explode
    _answer(window, "cancel")
    assert window.close_tab(0) is True  # clean session: closes anyway


def test_open_session_keeps_a_modified_untitled_tab(window, tmp_path):
    """The untouched-tab sweep judged emptiness by the action list, so a tab
    holding guides but no actions was destroyed without a word."""
    saved = window.current_view
    saved.add_action("mark")
    saved.session.save(str(tmp_path / "hero.tr"))

    scratch = window.new_session()
    scratch.session.document.meta["note"] = "unsaved guide work"
    scratch.session.touch()
    assert scratch.session.is_modified

    window.close_tab(window.tabs.indexOf(saved))
    window.open_session(str(tmp_path / "hero.tr"))
    assert scratch in window.views


def test_import_actions_records_an_undo_step(window, tmp_path):
    """main.import_actions called session._touch(), which does not exist."""
    source = window.new_session()
    source.add_action("mark")
    source.session.save(str(tmp_path / "source.tr"))
    _answer(window, "discard")
    window.close_tab(window.tabs.indexOf(source))

    target = window.current_view
    window.import_actions(str(tmp_path / "source.tr"))
    assert target.session.paths() == ["mark"]
    assert target.session.can_undo is True
