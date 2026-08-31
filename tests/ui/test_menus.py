"""One menu bar over both views of a session."""

import pytest

from tik.trigger.ui.main import TriggerWindow
from tik.trigger.ui.session_view import DESIGNER_TAB, SESSION_TAB

from test_pipeline_ui import _stub_designer


@pytest.fixture
def window(qapp):
    win = TriggerWindow(designer_factory=_stub_designer)
    win.show()
    yield win
    win.close()


def menu(window, title):
    for action in window.menu_bar.actions():
        if action.text() == title:
            return action.menu()
    raise AssertionError(f"no {title} menu in {[a.text() for a in window.menu_bar.actions()]}")


def items(menu_obj):
    return [action.text() for action in menu_obj.actions() if not action.isSeparator()]


def test_the_bar_has_one_set_of_menus(window):
    titles = [action.text() for action in window.menu_bar.actions()]
    assert titles == ["&File", "&Edit", "&Session", "&Guides", "&Tools", "&Help"]


def test_file_saves_the_session_and_exchanges_guide_files(window):
    entries = items(menu(window, "&File"))
    assert "Save" in entries
    assert "Import Guides…" in entries and "Export Guides…" in entries
    # Ctrl+S saves the session; the guide library has no save shortcut
    save = next(a for a in menu(window, "&File").actions() if a.text() == "Save")
    assert save.shortcut().toString() == "Ctrl+S"
    imp = next(a for a in menu(window, "&File").actions() if a.text() == "Import Guides…")
    assert imp.shortcut().isEmpty()


def test_the_guides_menu_is_disabled_off_the_designer_tab(window):
    guides = next(a for a in window.menu_bar.actions() if a.text() == "&Guides")
    assert guides.isEnabled() is False
    window.views[0].sub_tabs.setCurrentIndex(DESIGNER_TAB)
    assert guides.isEnabled() is True
    window.views[0].sub_tabs.setCurrentIndex(SESSION_TAB)
    assert guides.isEnabled() is False


def test_the_guides_menu_carries_the_designer_verbs(window):
    entries = items(menu(window, "&Guides"))
    for expected in ("Mirror", "Sever Connections", "Select All Guides", "Add Scene Nodes"):
        assert expected in entries


def test_edit_dispatches_to_whichever_view_is_active(window):
    view = window.views[0]
    view.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    calls = []
    view.designer.duplicate_current = lambda: calls.append("designer")
    view.duplicate_current = lambda: calls.append("session")
    duplicate = next(a for a in menu(window, "&Edit").actions() if a.text() == "Duplicate")
    duplicate.trigger()
    assert calls == ["designer"]
    view.sub_tabs.setCurrentIndex(SESSION_TAB)
    duplicate.trigger()
    assert calls == ["designer", "session"]


def test_undo_on_the_designer_tab_goes_to_maya(window, monkeypatch):
    """Guide edits are scene edits; the session's action undo is the wrong stack."""
    view = window.views[0]
    view.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    hits = []
    monkeypatch.setattr(window, "_maya_undo", lambda: hits.append("maya"))
    monkeypatch.setattr(view.session, "undo", lambda: hits.append("session") or True)
    undo = next(a for a in menu(window, "&Edit").actions() if a.text() == "Undo")
    undo.trigger()
    assert hits == ["maya"]
    view.sub_tabs.setCurrentIndex(SESSION_TAB)
    undo.trigger()
    assert hits == ["maya", "session"]
