"""The Guide Designer's bottom bar: two directions, one at each end."""

import pytest

from tik.trigger.ui.designer.action_bar import DesignerActionBar


@pytest.fixture
def bar(qapp):
    widget = DesignerActionBar()
    widget.show()
    yield widget
    widget.deleteLater()


def test_the_two_draw_buttons_emit(bar):
    seen = []
    bar.draw_selected_requested.connect(lambda: seen.append("selected"))
    bar.draw_all_requested.connect(lambda: seen.append("all"))
    bar.set_selection_enabled(True)
    bar.draw_selected_button.click()
    bar.draw_all_button.click()
    assert seen == ["selected", "all"]


def test_nothing_selected_disables_what_acts_on_a_selection(bar):
    bar.set_selection_enabled(False)
    assert not bar.draw_selected_button.isEnabled()
    assert not bar.select_button.isEnabled()
    assert not bar.mirror_button.isEnabled()


def test_draw_all_and_build_all_never_depend_on_the_selection(bar):
    bar.set_selection_enabled(False)
    assert bar.draw_all_button.isEnabled()
    assert bar.build_all_button.isEnabled()


def test_pending_colours_each_end_independently(bar):
    """One end says the scene is behind the session, the other says the
    session is behind the scene. They must never blur together."""
    bar.set_pending(stale_selected=True, stale_any=True, moved=False)
    assert bar.draw_selected_button.property("alert") is True
    assert bar.draw_all_button.property("alert") is True
    assert bar.sync_button.property("alert") is False

    bar.set_pending(stale_selected=False, stale_any=False, moved=True)
    assert bar.draw_selected_button.property("alert") is False
    assert bar.draw_all_button.property("alert") is False
    assert bar.sync_button.property("alert") is True


def test_stale_outside_the_selection_lights_only_draw_all(bar):
    bar.set_pending(stale_selected=False, stale_any=True, moved=False)
    assert bar.draw_selected_button.property("alert") is False
    assert bar.draw_all_button.property("alert") is True


def test_not_drawn_never_lights_the_bar(bar):
    """Orange means out of date, never not-drawn. A freshly opened session is
    entirely not-drawn, and that is its resting state, not a warning."""
    bar.set_pending(stale_selected=False, stale_any=False, moved=False)
    assert bar.draw_selected_button.property("alert") is False
    assert bar.draw_all_button.property("alert") is False
    assert bar.sync_button.property("alert") is False


def test_the_auto_checkbox_reports_but_does_not_echo(bar):
    seen = []
    bar.auto_sync_toggled.connect(seen.append)
    bar.auto_check.setChecked(False)
    assert seen == [False]
    seen.clear()
    bar.set_auto_sync(True)  # programmatic: must not re-emit
    assert seen == []


def test_auto_quietens_the_sync_button(bar):
    bar.set_auto_sync(True)
    assert bar.sync_button.property("quiet") is True
    bar.set_auto_sync(False)
    assert bar.sync_button.property("quiet") is False


def test_the_captions_name_where_the_data_lands(bar):
    """The bar's geography is the explanation: a rigger who has read no spec
    can still answer "which button writes to my scene?"."""
    from tik.shared.ui.Qt import QtWidgets

    captions = [
        label.text()
        for label in bar.findChildren(QtWidgets.QLabel)
        if label.objectName() == "FieldCaption"
    ]
    assert "→ SCENE" in captions
    assert "→ SESSION" in captions


def test_the_scope_rules_are_hairlines_not_bars(bar):
    """A QFrame.VLine renders 5px wide under this theme; the dividers that
    separate the two directions must not."""
    bar.layout().activate()
    assert bar.selection_rule.width() == 1
    assert bar.build_rule.width() == 1
