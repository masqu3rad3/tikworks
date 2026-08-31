"""Each session tab owns a Guide Designer and a checkout of the scene."""

import pytest

from tik.trigger.ui.main import DESIGNER_MODE, TriggerWindow

from test_pipeline_ui import _stub_designer


@pytest.fixture
def window(qapp):
    win = TriggerWindow(designer_factory=_stub_designer)
    yield win
    win.close()


def test_the_designer_is_not_built_until_the_mode_is_opened(window):
    assert window._designers == {}


def test_each_session_tab_gets_its_own_designer(window):
    first = window.views[0]
    window.new_session()
    second = window.views[-1]
    assert first is not second
    assert window.designer_for(first) is not window.designer_for(second)


def test_the_designer_mode_follows_the_active_tab(window):
    first = window.views[0]
    window.new_session()
    second = window.views[-1]
    window.mode_bar.setCurrentIndex(DESIGNER_MODE)
    assert window.active_designer is window.designer_for(second)
    window.tabs.setCurrentIndex(0)
    assert window.active_designer is window.designer_for(first)


def test_closing_a_tab_drops_its_designer(window):
    window.new_session()
    second = window.views[-1]
    designer = window.designer_for(second)
    window.close_tab(window.tabs.indexOf(second))
    assert designer not in window._designers.values()


def test_the_designers_menu_bar_follows_the_active_tab(window):
    first = window.views[0]
    window.new_session()
    window.mode_bar.setCurrentIndex(DESIGNER_MODE)
    second_menus = window.current_menu_bar()
    window.tabs.setCurrentIndex(0)
    assert window.current_menu_bar() is window.designer_for(first).menu_bar
    assert window.current_menu_bar() is not second_menus


def test_activating_a_designer_checks_its_session_out(window, monkeypatch):
    calls = []
    for view in window.views:
        monkeypatch.setattr(view.session, "checkout_guides",
                            lambda force=False, v=view: calls.append(v))
    window.mode_bar.setCurrentIndex(DESIGNER_MODE)
    assert calls == [window.views[0]]


def test_switching_tabs_captures_the_outgoing_session(window, monkeypatch):
    first = window.views[0]
    window.new_session()
    second = window.views[-1]
    captured, checked_out = [], []
    for view in (first, second):
        monkeypatch.setattr(view.session, "capture_guides",
                            lambda v=view: captured.append(v) or False)
        monkeypatch.setattr(view.session, "checkout_guides",
                            lambda force=False, v=view: checked_out.append(v))
    window.mode_bar.setCurrentIndex(DESIGNER_MODE)
    assert checked_out == [second]
    window.tabs.setCurrentIndex(0)
    # the tab we left keeps its work before the other one takes the scene
    assert captured == [second]
    assert checked_out == [second, first]


def test_a_foreign_checkout_is_reported_not_taken(window, monkeypatch):
    from tik.trigger.core.exceptions import SessionError

    view = window.views[0]
    forced = []

    def refuse(force=False):
        forced.append(force)
        raise SessionError("The guides in this scene belong to another session.")

    monkeypatch.setattr(view.session, "checkout_guides", refuse)
    window.mode_bar.setCurrentIndex(DESIGNER_MODE)
    assert forced == [False]  # never forced on the user's behalf


def test_the_designer_shows_which_session_owns_the_scene(window):
    window.mode_bar.setCurrentIndex(DESIGNER_MODE)
    designer = window.active_designer
    assert designer.status.text("session") == window.views[0].session.name
