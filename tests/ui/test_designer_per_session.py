"""Each session tab owns a Guide Designer and the scene's checkout."""

import pytest
from test_pipeline_ui import _stub_designer

from tik.trigger.session import Session
from tik.trigger.ui.main import TriggerWindow
from tik.trigger.ui.session_view import DESIGNER_TAB, SESSION_TAB


@pytest.fixture
def window(qapp):
    win = TriggerWindow(designer_factory=_stub_designer)
    yield win
    win.close()


def test_the_designer_is_not_built_until_its_sub_tab_is_opened(window):
    assert window.views[0].designer is None
    assert window.active_designer is None


def test_each_session_tab_gets_its_own_designer(window):
    first = window.views[0]
    window.new_session()
    second = window.views[-1]
    first.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    second.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    assert first.designer is not second.designer


def test_the_active_designer_follows_the_session_tab(window):
    first = window.views[0]
    window.new_session()
    second = window.views[-1]
    for view in (first, second):
        view.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    assert window.active_designer is second.designer
    window.tabs.setCurrentIndex(0)
    assert window.active_designer is first.designer


def test_opening_the_designer_hands_the_scene_to_that_session(window, monkeypatch):
    calls = []
    monkeypatch.setattr(
        Session, "hand_over", staticmethod(lambda out, inc: calls.append((out, inc)))
    )
    view = window.views[0]
    view.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    assert calls == [(None, view.session)]


def test_switching_session_tabs_hands_over(window, monkeypatch):
    # patched from the start: the window only advances its bookkeeping when a
    # hand-over succeeds, and the real one cannot here (no Maya)
    calls = []
    monkeypatch.setattr(
        Session, "hand_over", staticmethod(lambda out, inc: calls.append((out, inc)))
    )
    first = window.views[0]
    window.new_session()
    second = window.views[-1]
    for view in (first, second):
        view.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    calls.clear()
    window.tabs.setCurrentIndex(0)
    assert calls == [(second.session, first.session)]


def test_switching_sub_tabs_does_not_hand_over(window, monkeypatch):
    """Session and Guide Designer are two views of one document."""
    calls = []
    monkeypatch.setattr(
        Session, "hand_over", staticmethod(lambda out, inc: calls.append((out, inc)))
    )
    view = window.views[0]
    view.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    calls.clear()
    view.sub_tabs.setCurrentIndex(SESSION_TAB)
    view.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    assert calls == []


def test_a_foreign_checkout_is_reported_not_taken(window, monkeypatch):
    from tik.trigger.core.exceptions import SessionError

    def refuse(outgoing, incoming):
        raise SessionError("The guides in this scene belong to another session.")

    monkeypatch.setattr(Session, "hand_over", staticmethod(refuse))
    window.views[0].sub_tabs.setCurrentIndex(DESIGNER_TAB)
    assert window.active_designer is not None  # still usable
    assert window._checked_out_view is None


def test_closing_a_tab_releases_its_designer(window):
    window.new_session()
    second = window.views[-1]
    second.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    designer = second.designer
    window.close_tab(window.tabs.indexOf(second))
    assert designer._torn_down is True


def test_opening_the_designer_never_draws(window):
    """Reversed deliberately. Opening the Designer used to redraw guides a
    build had cleared -- an unasked-for draw, which is what this design
    removes. Switching tabs must not put a joint in the scene: the modules
    are reported not-drawn and Draw is the rigger's to press."""
    view = window.views[0]
    view.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    calls = []
    view.designer.guides.draw = lambda *args, **kwargs: calls.append("draw")
    view.sub_tabs.setCurrentIndex(SESSION_TAB)
    view.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    assert calls == []
