"""FormBuilder: widgets generated from fields, two-way sync, validation."""

from tik.core.fields import (
    BoolField,
    ChoiceField,
    FieldGroup,
    FloatField,
    IntField,
    ListField,
    NodeRefField,
    Schema,
    StringField,
    Vector2Field,
    VectorField,
)
from tik.shared.ui.collapsible import CollapsibleGroup
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
    span = Vector2Field((-60.0, 75.0), min=-89.0, max=89.0, labels=("Lower", "Upper"))


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


# ------------------------------------------------------------ vector editors


def test_vector_editor_clamps_to_the_field_bounds(qapp):
    form = FormBuilder(Settings())
    editor = form.widget("span")
    assert editor.value() == (-60.0, 75.0)
    for spin in editor.spins:
        assert spin.minimum() == -89.0
        assert spin.maximum() == 89.0


def test_vector_editor_shows_a_caption_per_component(qapp):
    form = FormBuilder(Settings())
    captions = [
        widget.text()
        for widget in form.widget("span").findChildren(QtWidgets.QLabel)
    ]
    assert captions == ["Lower", "Upper"]


def test_an_unlabelled_vector_has_no_captions(qapp):
    form = FormBuilder(Settings())
    assert not form.widget("up").findChildren(QtWidgets.QLabel)


def test_vector_editing_still_reaches_the_target(qapp):
    target = Settings()
    form = FormBuilder(target)
    form.widget("span").spins[0].setValue(-20.0)
    assert target.span == (-20.0, 75.0)


# ------------------------------------------------------------ field groups

TUNING = FieldGroup("Tuning", collapsed=True)
SHAPE = FieldGroup("Shape")


class Groupy(Schema):
    loose = IntField(1)
    also_loose = BoolField(True)
    width = FloatField(1.0, group=SHAPE)
    depth = FloatField(2.0, group=SHAPE)
    gain = FloatField(0.5, group=TUNING)
    stray = FloatField(0.0, group=SHAPE)  # non-adjacent, same group


def test_ungrouped_fields_render_before_any_group(qapp):
    form = FormBuilder(Groupy())
    groups = form.findChildren(CollapsibleGroup)
    assert [group.title for group in groups] == ["Shape", "Tuning"]
    # the plain rows live in the first layout item, before any fold
    assert form._layout.itemAt(0).widget() is None


def test_a_collapsed_group_starts_folded(qapp):
    form = FormBuilder(Groupy())
    assert form.group_widget("Tuning").is_expanded() is False
    assert form.group_widget("Shape").is_expanded() is True


def test_non_adjacent_fields_join_one_group(qapp):
    """Declaring A, A, B, A must make two groups, not three."""
    form = FormBuilder(Groupy())
    assert len(form.findChildren(CollapsibleGroup)) == 2


def test_widgets_inside_a_collapsed_group_are_still_reachable(qapp):
    """_widgets stays flat, so every caller keeps working."""
    form = FormBuilder(Groupy())
    assert form.widget("gain").value() == 0.5
    form.mark_overrides(["gain"])
    assert "bold" in form._labels["gain"].styleSheet()


def test_editing_inside_a_group_reaches_the_target(qapp):
    target = Groupy()
    form = FormBuilder(target)
    form.widget("gain").setValue(0.75)
    assert target.gain == 0.75


def test_the_fold_state_survives_retargeting(qapp):
    form = FormBuilder(Groupy())
    form.group_widget("Tuning").set_expanded(True)
    form.set_target(Settings())
    form.set_target(Groupy())
    assert form.group_widget("Tuning").is_expanded() is True


def test_a_fresh_builder_starts_from_the_declared_default(qapp):
    assert FormBuilder(Groupy()).group_widget("Tuning").is_expanded() is False


def test_a_string_group_renders_as_a_real_fold(qapp):
    """Settings declares group="Geometry" as a bare string."""
    form = FormBuilder(Settings())
    assert form.group_widget("Geometry").is_expanded() is True
    assert form.widget("segments").value() == 3
    assert form.widget("local").isChecked() is False
