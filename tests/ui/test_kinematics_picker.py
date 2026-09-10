"""A list field that declares ``choices_from`` renders as a picker.

``kinematics.modules`` holds instance uuids. Nobody types a uuid, so the field
has to offer the modules by their display key and store their ids.
"""

import pytest

from tik.core.fields import ListField, Schema
from tik.shared.ui.fields import FormBuilder
from tik.shared.ui.Qt import QtCore, QtWidgets


class Scoped(Schema):
    modules = ListField(item_type=str, choices_from="modules")
    tags = ListField(["a", "b"])  # no choices_from: still a plain line edit


def _choices(_key):
    return [("spine", "aaa"), ("L_arm", "bbb"), ("L_wing", "ccc")]


def _form(target=None):
    return FormBuilder(target or Scoped(), list_choices=_choices)


def _rows(widget):
    return [widget.item(row) for row in range(widget.count())]


def test_a_plain_list_field_is_unchanged(qapp):
    """No choices_from means the comma-separated editor, exactly as before."""
    form = _form()
    assert isinstance(form.widget("tags"), QtWidgets.QLineEdit)
    assert form.widget("tags").text() == "a, b"


def test_a_choices_list_field_becomes_a_check_list(qapp):
    form = _form()
    widget = form.widget("modules")
    assert not isinstance(widget, QtWidgets.QLineEdit)
    labels = [item.text() for item in _rows(widget.list)]
    assert labels == ["spine", "L_arm", "L_wing"]


def test_rows_show_the_key_and_carry_the_id(qapp):
    form = _form()
    rows = _rows(form.widget("modules").list)
    assert rows[1].text() == "L_arm"
    assert rows[1].data(QtCore.Qt.UserRole) == "bbb"


def test_ticking_a_row_writes_its_id(qapp):
    target = Scoped()
    form = _form(target)
    widget = form.widget("modules")
    _rows(widget.list)[1].setCheckState(QtCore.Qt.Checked)
    assert target.modules == ["bbb"]


def test_a_stored_id_opens_ticked(qapp):
    target = Scoped()
    target.modules = ["ccc"]
    form = _form(target)
    rows = _rows(form.widget("modules").list)
    assert rows[2].checkState() == QtCore.Qt.Checked
    assert rows[0].checkState() == QtCore.Qt.Unchecked


def test_a_stored_id_nobody_offers_is_kept_and_marked(qapp):
    """Dropping it silently would shrink somebody's build scope on save."""
    target = Scoped()
    target.modules = ["aaa", "gone"]
    form = _form(target)
    rows = _rows(form.widget("modules").list)
    missing = [item for item in rows if "missing" in item.text()]
    assert len(missing) == 1
    assert missing[0].data(QtCore.Qt.UserRole) == "gone"
    assert missing[0].checkState() == QtCore.Qt.Checked
    assert target.modules == ["aaa", "gone"]


def test_unticking_removes_the_id(qapp):
    target = Scoped()
    target.modules = ["aaa", "bbb"]
    form = _form(target)
    rows = _rows(form.widget("modules").list)
    rows[0].setCheckState(QtCore.Qt.Unchecked)
    assert target.modules == ["bbb"]


# --- the filterable picker ----------------------------------------------------


class Filtered(Schema):
    modules = ListField(item_type=str, choices_from="modules", filterable=True)


def _filtered_form(target=None):
    return FormBuilder(target or Filtered(), list_choices=_choices)


def test_a_filterable_field_gets_the_filter_furniture(qapp):
    widget = _filtered_form().widget("modules")
    assert widget.filter_bar is not None
    assert widget.only_selected_box is not None


def test_a_field_without_the_flag_stays_bare(qapp):
    assert _form().widget("modules").filter_bar is None


def test_the_hidden_companion_gets_no_row_of_its_own(qapp):
    """It is drawn inside the list, where the state means something."""
    form = _filtered_form()
    with pytest.raises(KeyError):
        form.widget("modules_only_selected")


def test_a_stored_only_selected_opens_the_box_ticked(qapp):
    target = Filtered()
    target.modules_only_selected = True
    widget = _filtered_form(target).widget("modules")
    assert widget.only_selected_box.isChecked() is True
    assert widget.only_selected is True


def test_toggling_the_box_writes_the_companion_field(qapp):
    target = Filtered()
    form = _filtered_form(target)
    form.widget("modules").only_selected_box.setChecked(True)
    assert target.modules_only_selected is True


def test_toggling_the_box_reports_a_change_like_any_setting(qapp):
    form = _filtered_form()
    seen = []
    form.changed.connect(lambda name, value: seen.append((name, value)))
    form.widget("modules").only_selected_box.setChecked(True)
    assert seen == [("modules_only_selected", True)]


def test_refresh_pushes_the_companion_back_in(qapp):
    target = Filtered()
    form = _filtered_form(target)
    target.modules_only_selected = True
    form.refresh()
    assert form.widget("modules").only_selected is True
