"""The Guide Designer's bottom bar: three groups, split by what they act on."""

import pytest

from tik.shared.ui.Qt import QtWidgets
from tik.trigger.ui.designer.action_bar import DesignerActionBar


@pytest.fixture
def bar(qapp):
    widget = DesignerActionBar()
    widget.show()
    yield widget
    widget.deleteLater()


def test_nothing_selected_disables_the_selection_group(bar):
    bar.set_selection([])
    assert bar.selection_label.text().endswith("none")
    assert not bar.select_button.isEnabled()
    assert not bar.mirror_button.isEnabled()
    assert not bar.build_selected_button.isEnabled()


def test_one_selection_names_it(bar):
    """The label is the answer to 'what will Mirror mirror?'."""
    bar.set_selection(["L_arm"])
    assert bar.selection_label.text().endswith("L_arm")
    assert bar.select_button.isEnabled()


def test_several_selections_are_counted(bar):
    bar.set_selection(["L_arm", "R_arm"])
    assert "2 modules" in bar.selection_label.text()


def test_build_all_never_depends_on_the_selection(bar):
    bar.set_selection([])
    assert bar.build_all_button.isEnabled()


def test_the_auto_checkbox_reports_but_does_not_echo(bar):
    seen = []
    bar.auto_sync_toggled.connect(seen.append)
    bar.auto_check.setChecked(False)
    assert seen == [False]
    seen.clear()
    bar.set_auto_sync(True)   # programmatic: must not re-emit
    assert seen == []


def test_drift_shows_a_pill_only_when_there_is_drift(bar):
    bar.set_drift(0)
    assert not bar.drift_pill.isVisible()
    assert bar.drift_pill.text() == ""
    bar.set_drift(3)
    assert bar.drift_pill.isVisible()
    assert "3" in bar.drift_pill.text()


def test_up_to_date_shows_only_when_auto_is_off_and_drift_is_clean(bar):
    """Spec 2.3: a trailing 'up to date' only when Auto cannot say it for us."""
    # default state: Auto on, no drift -- the label stays hidden
    assert not bar.up_to_date_label.isVisible()

    bar.set_auto_sync(False)
    assert bar.up_to_date_label.isVisible()  # Auto off, scene already clean

    bar.set_drift(2)
    assert not bar.up_to_date_label.isVisible()  # drift trumps "up to date"

    bar.set_drift(0)
    assert bar.up_to_date_label.isVisible()  # clean again, Auto still off

    bar.set_auto_sync(True)
    assert not bar.up_to_date_label.isVisible()  # Auto handles it now


def test_the_scope_rule_is_a_hairline_not_a_bar(bar):
    """A QFrame.VLine renders 5px wide under this theme; the divider that
    keeps 'Build all' from reading as 'build what I picked' must not.
    """
    bar.layout().activate()
    assert bar.rule.width() == 1
