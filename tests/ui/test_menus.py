"""One menu bar over both views of a session."""

import pytest
from test_pipeline_ui import _stub_designer

from tik.trigger.core.guide_document import GuideDocument, ModuleEntry
from tik.trigger.core.scene_recovery import RecoveredModule, RecoveryReport
from tik.trigger.ui.designer.snapshot_dialog import SnapshotDialog
from tik.trigger.ui.main import TriggerWindow
from tik.trigger.ui.session_view import DESIGNER_TAB, SESSION_TAB


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
    raise AssertionError(
        f"no {title} menu in {[entry.text() for entry in window.menu_bar.actions()]}"
    )


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
    save = next(
        entry for entry in menu(window, "&File").actions() if entry.text() == "Save"
    )
    assert save.shortcut().toString() == "Ctrl+S"
    imp = next(
        entry
        for entry in menu(window, "&File").actions()
        if entry.text() == "Import Guides…"
    )
    assert imp.shortcut().isEmpty()


def test_each_sub_tab_shows_its_own_menu_and_hides_the_other(window):
    """Session on the Session tab, Guides on the Designer tab -- never both."""
    guides = next(
        entry for entry in window.menu_bar.actions() if entry.text() == "&Guides"
    )
    session = next(
        entry for entry in window.menu_bar.actions() if entry.text() == "&Session"
    )

    assert guides.isVisible() is False
    assert session.isVisible() is True

    window.views[0].sub_tabs.setCurrentIndex(DESIGNER_TAB)
    assert guides.isVisible() is True
    assert session.isVisible() is False

    window.views[0].sub_tabs.setCurrentIndex(SESSION_TAB)
    assert guides.isVisible() is False
    assert session.isVisible() is True


def test_the_guides_menu_is_disabled_off_the_designer_tab(window):
    """Enablement tracks the target, separately from which menu is on show."""
    guides = next(
        entry for entry in window.menu_bar.actions() if entry.text() == "&Guides"
    )
    assert guides.isEnabled() is False
    window.views[0].sub_tabs.setCurrentIndex(DESIGNER_TAB)
    assert guides.isEnabled() is True
    window.views[0].sub_tabs.setCurrentIndex(SESSION_TAB)
    assert guides.isEnabled() is False


def test_hiding_a_menu_leaves_its_shortcuts_alive(window):
    """A hidden menu is still entry menu: Ctrl+B keeps working off the Session tab."""
    build = next(
        entry
        for entry in menu(window, "&Session").actions()
        if entry.text() == "Build Rig"
    )
    window.views[0].sub_tabs.setCurrentIndex(DESIGNER_TAB)
    assert window.session_menu_action.isVisible() is False
    assert build.isVisible() is True
    assert build.isEnabled() is True


def test_the_guides_menu_carries_the_designer_verbs(window):
    entries = items(menu(window, "&Guides"))
    for expected in (
        "Mirror",
        "Sever Connections",
        "Select All Guides",
        "Add Scene Nodes",
    ):
        assert expected in entries


def test_edit_dispatches_to_whichever_view_is_active(window):
    view = window.views[0]
    view.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    calls = []
    view.designer.duplicate_current = lambda: calls.append("designer")
    view.duplicate_current = lambda: calls.append("session")
    duplicate = next(
        entry
        for entry in menu(window, "&Edit").actions()
        if entry.text() == "Duplicate"
    )
    duplicate.trigger()
    assert calls == ["designer"]
    view.sub_tabs.setCurrentIndex(SESSION_TAB)
    duplicate.trigger()
    assert calls == ["designer", "session"]


def test_undo_on_the_designer_tab_undoes_trigger_actions(window, monkeypatch):
    """Guide structure lives in the session, so its undo stack is the right one.

    Moving entry guide is entry scene edit and stays on Maya's stack, undone with focus
    in the viewport.
    """
    view = window.views[0]
    view.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    hits = []
    monkeypatch.setattr(view.session, "undo", lambda: hits.append("session") or True)
    undo = next(
        entry for entry in menu(window, "&Edit").actions() if entry.text() == "Undo"
    )
    undo.trigger()
    assert hits == ["session"]


def test_export_guides_asks_for_a_path(window):
    """It once passed True as the *path*, which blew up inside pathlib."""
    view = window.views[0]
    view.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    seen = {}
    view.designer.export_file = (
        lambda path=None, ask=False, selected=False: seen.update(
            path=path, ask=ask, selected=selected
        )
    )
    action = next(
        entry
        for entry in menu(window, "&File").actions()
        if entry.text() == "Export Guides…"
    )
    action.trigger()
    assert seen == {"path": None, "ask": True, "selected": False}


def test_import_guides_takes_no_arguments(window):
    view = window.views[0]
    view.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    seen = []
    view.designer.import_file = lambda *args, **kwargs: seen.append((args, kwargs))
    action = next(
        entry
        for entry in menu(window, "&File").actions()
        if entry.text() == "Import Guides…"
    )
    action.trigger()
    assert seen == [((), {})]


def test_redraw_views_keeps_f5_and_sync_takes_f6(window):
    guides = items(menu(window, "&Guides"))
    assert "Sync From Scene" in guides
    sync_action = next(
        entry
        for entry in menu(window, "&Guides").actions()
        if entry.text() == "Sync From Scene"
    )
    assert sync_action.shortcut().toString() == "F6"

    layout_menu = next(
        entry.menu()
        for entry in menu(window, "&Guides").actions()
        if entry.menu() is not None and entry.text() == "Layout"
    )
    layout_entries = items(layout_menu)
    assert "Redraw Views" in layout_entries
    assert "Refresh" not in layout_entries
    redraw = next(
        entry for entry in layout_menu.actions() if entry.text() == "Redraw Views"
    )
    assert redraw.shortcut().toString() == "F5"


def test_snapshot_is_a_menu_command_not_a_button(window):
    entries = items(menu(window, "&Guides"))
    assert "Snapshot Guides From Scene…" in entries


def test_auto_sync_action_is_checkable_and_starts_on(window):
    assert window.auto_sync_action.isCheckable()
    assert window.auto_sync_action.isChecked()


def test_snapshot_menu_command_reports_then_replaces_the_session(window, monkeypatch):
    """The menu action reaches the real command, which is destructive only
    once the dialog is accepted -- and only then does the session change."""
    view = window.views[0]
    view.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    # This test really replaces the session's document, which leaves it
    # modified; the fixture's teardown then closes the window, and entry modified
    # session makes closeEvent pop entry real, blocking "discard changes?"
    # QMessageBox. Answer it without entry dialog so teardown cannot hang.
    monkeypatch.setattr(window, "ask_discard", lambda session: True)
    designer = view.designer
    entry = ModuleEntry(
        instance_id="new-id", module_type="fkchain", name="arm", side="L"
    )
    found = RecoveryReport(
        modules=[RecoveredModule("new-id", "L_arm", "fkchain", True, 4)],
        guide_count=4,
    )
    document = GuideDocument(modules=[entry])
    designer.guides.snapshot_from_scene = lambda: (document, found)
    action = next(
        entry
        for entry in menu(window, "&Guides").actions()
        if entry.text() == "Snapshot Guides From Scene…"
    )

    monkeypatch.setattr(SnapshotDialog, "exec", lambda self: SnapshotDialog.Rejected)
    action.trigger()
    assert view.session.document.guides.modules == []

    monkeypatch.setattr(SnapshotDialog, "exec", lambda self: SnapshotDialog.Accepted)
    action.trigger()
    assert view.session.document.guides is document


def test_auto_sync_binding_is_two_way_and_does_not_recurse(window):
    """Designer -> menu and menu -> Designer, without ping-ponging."""
    view = window.views[0]
    view.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    designer = view.designer

    # starts in step: the Designer syncs its stored default before the
    # window ever connects, so entering the Designer tab must pull the menu
    # up to date with it, not just leave the menu's own construction-time default
    assert window.auto_sync_action.isChecked() is designer.guides.auto_sync

    # every hop through set_auto_sync is recorded, so a bounce back would
    # show up as an extra, unexpected call
    designer_calls = []
    original = designer.set_auto_sync

    def _tracking_set_auto_sync(on):
        designer_calls.append(on)
        return original(on)

    designer.set_auto_sync = _tracking_set_auto_sync

    # Designer -> menu: toggling the Designer's own setting updates the menu
    designer.set_auto_sync(False)
    assert window.auto_sync_action.isChecked() is False
    assert designer_calls == [False]  # the mirrored update did not call back in

    # menu -> Designer: toggling the menu action updates the Designer (and,
    # through it, the action bar's checkbox)
    window.auto_sync_action.trigger()  # checkable action: trigger() toggles it
    assert window.auto_sync_action.isChecked() is True
    assert designer_calls == [False, True]  # exactly the user's click, no ping-pong
    assert designer.guides.auto_sync is True
    assert designer.action_bar.auto_check.isChecked() is True


def test_auto_sync_stays_bound_after_closing_and_reopening_a_tab(window):
    """Regression: a closed tab's Designer can be collected and its address
    reused by a later Designer. Dedup keyed on id(designer) would then see
    that id as "already connected" and skip wiring the new instance's
    signal, so the menu would silently stop tracking the bar. Goes through
    the real tab lifecycle (new_session / close_tab), not internals.
    """
    window.new_session()
    closed_view = window.views[-1]
    closed_view.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    assert closed_view.designer is not None
    window.close_tab(window.tabs.indexOf(closed_view))

    window.new_session()
    reopened_view = window.views[-1]
    reopened_view.sub_tabs.setCurrentIndex(DESIGNER_TAB)
    designer = reopened_view.designer
    assert designer is not None

    designer.set_auto_sync(False)
    assert window.auto_sync_action.isChecked() is False


def test_session_menu_has_build_and_publish(window):
    entries = {item.text(): item for item in menu(window, "&Session").actions()}
    assert "Build & Publish" in entries
    assert entries["Build & Publish"].shortcut().toString() == "Ctrl+Shift+P"
    # it sits beside the plain build verbs
    labels = [item.text() for item in menu(window, "&Session").actions()]
    assert labels[:3] == ["Build Rig", "Build & Publish", "Build Until Here"]
