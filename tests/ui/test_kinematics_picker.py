"""A list field that declares ``choices_from`` renders as a picker.

``kinematics.modules`` holds instance uuids. Nobody types a uuid, so the field
has to offer the modules by their display key and store their ids.
"""

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
