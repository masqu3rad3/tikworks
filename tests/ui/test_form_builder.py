"""FormBuilder: widgets generated from fields, two-way sync, validation."""

from tik.core.fields import (
    BoolField,
    ChoiceField,
    FloatField,
    IntField,
    ListField,
    NodeRefField,
    Schema,
    StringField,
    VectorField,
)
from tik.shared.ui.fields import FormBuilder
from tik.shared.ui.Qt import QtWidgets


class Settings(Schema):
    segments = IntField(3, min=1, max=10, group="Geometry")
    size = FloatField(1.5, min=0.0)
    local = BoolField(False)
    title = StringField("arm")
    solver = ChoiceField("rp", choices=["rp", "sc"])
    up = VectorField((0, 1, 0))
    tags = ListField(["a", "b"])
    target = NodeRefField()
    secret = StringField("x", hidden=True)


def test_builds_widgets_and_reads_defaults(qapp):
    form = FormBuilder(Settings())
    assert isinstance(form.widget("segments"), QtWidgets.QSpinBox)
    assert form.widget("segments").value() == 3
    assert form.widget("segments").maximum() == 10
    assert isinstance(form.widget("local"), QtWidgets.QCheckBox)
    assert form.widget("solver").currentData() == "rp"
    assert form.widget("up").value() == (0.0, 1.0, 0.0)
    assert form.widget("tags").text() == "a, b"
    assert "secret" not in form._widgets


def test_widget_edits_update_target_and_emit(qapp):
    target = Settings()
    form = FormBuilder(target)
    seen = []
    form.changed.connect(lambda name, value: seen.append((name, value)))
    form.widget("segments").setValue(7)
    form.widget("local").setChecked(True)
    form.widget("solver").setCurrentIndex(1)
    form.widget("up").spins[2].setValue(2.5)
    form.widget("tags").setText("x, y")
    form.widget("tags").editingFinished.emit()
    form.widget("target").line.setText("node1")
    form.widget("target").line.editingFinished.emit()
    assert target.segments == 7 and target.local is True and target.solver == "sc"
    assert target.up == (0.0, 1.0, 2.5)
    assert target.tags == ["x", "y"]
    assert target.target == "node1"
    assert ("segments", 7) in seen and ("solver", "sc") in seen


def test_validation_error_reverts_widget(qapp):
    target = Settings()
    form = FormBuilder(target)
    errors = []
    form.error.connect(lambda name, message: errors.append(name))
    form._on_change("size", -3)  # bypass the spinbox clamp to hit field validation
    assert errors == ["size"]
    assert target.size == 1.5
    assert form.widget("size").value() == 1.5


def test_node_picker(qapp):
    target = Settings()
    form = FormBuilder(target, node_picker=lambda: "picked")
    form.widget("target").button.click()
    assert target.target == "picked"


def test_set_target_none_clears(qapp):
    form = FormBuilder(Settings())
    form.set_target(None)
    assert form._widgets == {}
    assert form.values() == {}


# ------------------------------------------------------------ table field
def test_table_widget_round_trips_rows():
    from tik.core.fields import Column, TableField

    class Holder(Schema):
        rows = TableField(columns=(
            Column("mode", "choice", choices=("parent", "point")),
            Column("label", "string"),
        ))

    holder = Holder()
    holder.rows = [{"mode": "point", "label": "chest"}]
    builder = FormBuilder(holder)
    widget = builder.widget("rows")
    assert widget.value() == [{"mode": "point", "label": "chest"}]


def test_table_widget_adds_and_removes_rows():
    from tik.core.fields import Column, TableField

    class Holder(Schema):
        rows = TableField(columns=(Column("label", "string"),))

    holder = Holder()
    builder = FormBuilder(holder)
    widget = builder.widget("rows")
    widget.add_row()
    assert len(holder.rows) == 1
    widget.remove_row(0)
    assert holder.rows == []


def test_table_widget_resolves_choices_from_the_target():
    """A column's options can come from the object being edited."""
    from tik.core.fields import Column, TableField

    class Holder(Schema):
        controls = ("ik", "pole")
        rows = TableField(columns=(Column("control", "choice", choices_from="controls"),))

    builder = FormBuilder(Holder())
    widget = builder.widget("rows")
    widget.add_row()
    combo = widget.cell_widget(0, 0)
    assert [combo.itemText(index) for index in range(combo.count())] == ["ik", "pole"]
