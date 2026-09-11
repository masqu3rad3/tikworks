"""``ask_choice`` answers through the same seam as every message box.

Without it, a pick-one question is the one dialog a headless test cannot
answer -- a hole in the one-dialog-surface guarantee that only shows up when
somebody adds a picker.
"""

from tik.shared.ui import feedback
from tik.shared.ui.feedback import Feedback


def _with_handler(handler):
    previous = feedback.set_handler(handler)
    try:
        return Feedback().ask_choice(
            title="Which module?", label="Module:", options=["L_a", "L_b"]
        )
    finally:
        feedback.set_handler(previous)


def test_a_handler_answers_the_choice():
    assert _with_handler(lambda *args: "L_b") == "L_b"


def test_the_handler_sees_the_options_in_the_buttons_slot():
    seen = {}

    def handler(kind, title, text, details, buttons):
        seen.update(kind=kind, title=title, label=text, buttons=list(buttons))
        return buttons[0]

    assert _with_handler(handler) == "L_a"
    assert seen["kind"] == "choice"
    assert seen["title"] == "Which module?"
    assert seen["label"] == "Module:"
    assert seen["buttons"] == ["L_a", "L_b"]


def test_the_options_reach_the_handler_as_a_list():
    """A caller may pass any sequence; the seam normalises it."""
    seen = {}

    def handler(kind, title, text, details, buttons):
        seen["buttons"] = buttons
        return None if not buttons else buttons[0]

    previous = feedback.set_handler(handler)
    try:
        Feedback().ask_choice(options=("a", "b"))
    finally:
        feedback.set_handler(previous)
    assert seen["buttons"] == ["a", "b"]
