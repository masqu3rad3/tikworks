"""The per-control shape fold: every control listed, sparse storage beneath."""

from __future__ import annotations

import pytest

from tik.core.fields import Column, Schema, TableField
from tik.shared.ui.fields import FormBuilder


class Toy(Schema):
    rows = TableField(
        [],
        label="Control Shapes",
        rows_from="control_names",
        columns=(
            Column("control", "choice", choices_from="control_names"),
            Column("shape", "shape"),
            Column("size", "float"),
        ),
    )

    control_names = ("ik", "fk", "pole")
    control_shape_defaults = {"ik": "Cube", "fk": "Circle"}


@pytest.fixture
def form(qapp):
    builder = FormBuilder(Toy())
    return builder


def test_one_row_per_control(form):
    editor = form.widget("rows")
    assert editor.roles() == ("ik", "fk", "pole")


def test_unset_rows_show_the_module_default_as_a_placeholder(form):
    button, _spin = form.widget("rows").row_widgets("ik")
    assert button.value() == ""
    assert "Cube" in button.toolTip()


def test_editing_writes_a_sparse_row(form):
    editor = form.widget("rows")
    button, _spin = editor.row_widgets("ik")
    button.picker.choose("Diamond")
    assert editor.value() == [{"control": "ik", "shape": "Diamond", "size": ""}]


def test_the_size_spinner_writes_its_own_field(form):
    editor = form.widget("rows")
    _button, spin = editor.row_widgets("fk")
    spin.setValue(2.5)
    assert editor.value() == [{"control": "fk", "shape": "", "size": 2.5}]


def test_clearing_removes_the_row(form):
    editor = form.widget("rows")
    button, spin = editor.row_widgets("ik")
    button.picker.choose("Diamond")
    assert editor.value()
    button.setValue("")
    spin.setValue(1.0)
    editor.refresh_value()
    assert editor.value() == []


def test_set_value_populates_the_matching_rows(form):
    editor = form.widget("rows")
    editor.setValue([{"control": "pole", "shape": "Star", "size": 0.5}])
    button, spin = editor.row_widgets("pole")
    assert button.value() == "Star"
    assert spin.value() == pytest.approx(0.5)
    # The others stay inherited.
    assert editor.row_widgets("ik")[0].value() == ""


def test_a_plain_table_still_gets_the_add_remove_editor(qapp):
    """rows_from is the opt-in; without it nothing changes."""
    from tik.shared.ui.fields import _TableEditor

    class Plain(Schema):
        rows = TableField([], columns=(Column("label"),))

    builder = FormBuilder(Plain())
    assert isinstance(builder.widget("rows"), _TableEditor)
