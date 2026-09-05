"""The shared dialog surface: every tikworks dialog goes through it."""

from __future__ import annotations

import pytest

from tik.shared.ui import feedback
from tik.shared.ui.feedback import Feedback


@pytest.fixture(autouse=True)
def _clean_seams():
    """Never let a seam leak into another test -- they are module state."""
    previous_handler = feedback.set_handler(None)
    previous_browser = feedback.set_browser(None)
    yield
    feedback.set_handler(previous_handler)
    feedback.set_browser(previous_browser)


def test_handler_answers_a_question_without_a_modal(qapp):
    """The seam that makes a headless run impossible to hang."""
    seen = []

    def handler(kind, title, text, details, buttons):
        seen.append((kind, title, buttons))
        return "discard"

    feedback.set_handler(handler)
    answer = Feedback().pop_question(
        title="Unsaved changes",
        text="Save changes?",
        buttons=["save", "discard", "cancel"],
    )
    assert answer == "discard"
    assert seen == [("question", "Unsaved changes", ["save", "discard", "cancel"])]


def test_handler_answers_info_error_warning_and_about(qapp):
    kinds = []

    def handler(kind, title, text, details, buttons):
        kinds.append(kind)
        return "ok"

    feedback.set_handler(handler)
    box = Feedback()
    box.pop_info("Info", "hello")
    box.pop_error("Error", "boom")
    box.pop_warning("Careful", "hmm")
    box.pop_about("About", "v1")
    assert kinds == ["info", "error", "warning", "about"]


def test_set_handler_returns_the_previous_handler(qapp):
    def first(kind, title, text, details, buttons):
        return "ok"

    assert feedback.set_handler(first) is None
    assert feedback.set_handler(None) is first


def test_pop_question_rejects_an_unknown_button(qapp):
    with pytest.raises(ValueError):
        Feedback().pop_question(buttons=["save", "explode"])


def test_browse_helpers_use_the_module_browser(qapp):
    calls = []

    def browser(mode, extensions, current):
        calls.append((mode, tuple(extensions), current))
        return "D:/picked.tr"

    feedback.set_browser(browser)
    box = Feedback()
    assert box.browse_open("Open", "D:/start", [".tr"]) == "D:/picked.tr"
    assert box.browse_save("Save", "", [".tr"]) == "D:/picked.tr"
    assert box.browse_dir("Folder", "D:/here") == "D:/picked.tr"
    assert calls == [
        ("open", (".tr",), "D:/start"),
        ("save", (".tr",), ""),
        ("dir", (), "D:/here"),
    ]


def test_a_browser_that_cancels_returns_an_empty_string(qapp):
    feedback.set_browser(lambda mode, extensions, current: None)
    assert Feedback().browse_open() == ""


def test_file_filter_is_derived_from_extensions_but_can_be_given(qapp):
    assert Feedback._file_filter(()) == "All files (*)"
    assert Feedback._file_filter((".tr",)) == "Files (*.tr)"
    assert Feedback._file_filter((".tr", ".trg")) == "Files (*.tr *.trg)"


def test_parent_falls_back_to_the_maya_main_window_lazily(qapp, monkeypatch):
    """Resolved at dialog time: a Feedback built at import must not capture
    a main window that does not exist yet."""
    box = Feedback()
    assert box.parent is None
    monkeypatch.setattr(feedback, "get_main_window", lambda: "main-window")
    assert box._host() == "main-window"
    explicit = Feedback("mine")
    assert explicit._host() == "mine"


def test_a_labelled_button_still_answers_with_its_key(qapp):
    """``("yes", "Sync and redraw")`` in, ``"yes"`` out.

    Callers pass and receive keys; a label only changes what the button says,
    so no call site has to learn a Qt enum to ask a three-way question.
    """
    seen = {}

    def handler(kind, title, text, details, buttons):
        seen["buttons"] = buttons
        return "discard"

    feedback.set_handler(handler)
    answer = Feedback().pop_question(
        title="Redraw guides",
        text="The guides have been moved since the last sync.",
        buttons=[
            ("yes", "Sync and redraw"),
            ("discard", "Discard and redraw"),
            "cancel",
        ],
    )
    assert answer == "discard"
    assert seen["buttons"] == ["yes", "discard", "cancel"]


def test_a_labelled_button_reaches_a_real_dialog_as_its_label(qapp):
    """No handler installed: the label must land on the actual QMessageBox."""
    from tik.shared.ui.Qt import QtWidgets

    captured = {}

    def fake_exec(self):
        captured["texts"] = [button.text() for button in self.buttons()]
        return QtWidgets.QMessageBox.Cancel

    original = QtWidgets.QMessageBox.exec
    QtWidgets.QMessageBox.exec = fake_exec
    try:
        Feedback().pop_question(
            title="Redraw guides",
            text="moved",
            buttons=[("yes", "Sync and redraw"), "cancel"],
        )
    finally:
        QtWidgets.QMessageBox.exec = original
    assert "Sync and redraw" in captured["texts"]
