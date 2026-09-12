"""A module's list field renders as a picker in the Guide Designer.

Spec: docs/superpowers/specs/2026-09-12-movable-pivots-without-presets-design.md

``session_view`` injects a ``list_choices`` callback for the pipeline's action
panel; the Designer's module forms never did, so a ``ListField`` on a module
fell through to the comma-separated line edit. A ``TableField`` column has
always resolved ``choices_from`` off the target -- a list now does the same.
"""

from tik.core.fields import ListField, Schema
from tik.shared.ui.fields import FormBuilder
from tik.shared.ui.Qt import QtCore, QtWidgets


class Toy(Schema):
    """A list whose options are resolved from the target, with no callback."""

    roles: tuple = ("ik", "fk0")
    picked = ListField([], item_type=str, choices_from="roles")


def _rows(widget):
    return [widget.list.item(row) for row in range(widget.list.count())]


def test_a_list_field_resolves_its_choices_off_the_target(qapp):
    """No list_choices callback: the target answers, as a column's does."""
    form = FormBuilder(Toy())
    widget = form.widget("picked")

    assert not isinstance(widget, QtWidgets.QLineEdit)
    assert [item.text() for item in _rows(widget)] == ["ik", "fk0"]


def test_a_role_is_its_own_label_and_its_own_value(qapp):
    form = FormBuilder(Toy())

    row = _rows(form.widget("picked"))[0]
    assert row.text() == "ik"
    assert row.data(QtCore.Qt.UserRole) == "ik"


def test_ticking_a_row_writes_the_role(qapp):
    target = Toy()
    form = FormBuilder(target)

    _rows(form.widget("picked"))[1].setCheckState(QtCore.Qt.Checked)

    assert target.picked == ["fk0"]


def test_an_injected_callback_still_wins(qapp):
    """The pipeline's action panel keeps supplying its own options."""
    form = FormBuilder(Toy(), list_choices=lambda _key: [("Spine", "aaa")])

    assert [item.text() for item in _rows(form.widget("picked"))] == ["Spine"]
