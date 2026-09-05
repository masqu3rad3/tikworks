"""Tests for tik.core.fields and tik.core.side (no Maya required)."""

import json

import pytest

from tik.core.fields import (
    BoolField,
    ChoiceField,
    FieldGroup,
    FieldValidationError,
    FloatField,
    IntField,
    ListField,
    NodeRefField,
    Schema,
    StringField,
    Vector2Field,
    Vector3Field,
    VectorField,
)
from tik.core.side import Side


class Thing(Schema):
    segments = IntField(3, min=1, max=20, help="Number of segments")
    ratio = FloatField(0.5, min=0.0, max=1.0)
    local = BoolField(False, label="Local Joints")
    title = StringField("arm")
    solver = ChoiceField("rp", choices=["rp", "sc"])
    up = VectorField((0, 1, 0))
    tags = ListField(["a"], item_type=str)
    target = NodeRefField()


class Child(Thing):
    extra = IntField(1)


def test_defaults_and_labels():
    thing = Thing()
    assert thing.segments == 3
    assert thing.local is False
    assert Thing.fields()["local"].label == "Local Joints"
    assert Thing.fields()["segments"].label == "Segments"


def test_defaults_are_per_instance_copies():
    first, second = Thing(), Thing()
    first.tags.append("b")
    assert second.tags == ["a"]


def test_int_validation():
    thing = Thing()
    thing.segments = 5.0
    assert thing.segments == 5 and isinstance(thing.segments, int)
    with pytest.raises(FieldValidationError):
        thing.segments = 0
    with pytest.raises(FieldValidationError):
        thing.segments = 2.5
    with pytest.raises(FieldValidationError):
        thing.segments = "3"
    with pytest.raises(FieldValidationError):
        thing.segments = True


def test_float_bool_string_choice():
    thing = Thing()
    thing.ratio = 1
    assert thing.ratio == 1.0
    with pytest.raises(FieldValidationError):
        thing.ratio = 1.5
    thing.local = 1
    assert thing.local is True
    with pytest.raises(FieldValidationError):
        thing.local = "yes"
    with pytest.raises(FieldValidationError):
        thing.title = 3
    thing.solver = "sc"
    with pytest.raises(FieldValidationError):
        thing.solver = "spline"


def test_vector_and_list_and_noderef():
    thing = Thing()
    thing.up = [1, 0, 0]
    assert thing.up == (1.0, 0.0, 0.0)
    with pytest.raises(FieldValidationError):
        thing.up = (1, 0)
    with pytest.raises(FieldValidationError):
        thing.tags = "abc"
    with pytest.raises(FieldValidationError):
        thing.tags = [1]
    thing.target = None
    assert thing.target == ""


def test_values_apply_reset():
    thing = Thing()
    thing.apply({"segments": 7, "local": True})
    assert thing.values()["segments"] == 7
    with pytest.raises(KeyError):
        thing.apply({"nope": 1})
    thing.apply({"nope": 1}, strict=False)
    thing.reset()
    assert thing.segments == 3


def test_schema_is_json_serializable_and_ordered():
    schema = Child.schema()
    assert list(schema) == [
        "segments",
        "ratio",
        "local",
        "title",
        "solver",
        "up",
        "tags",
        "target",
        "extra",
    ]
    json.dumps(schema)
    assert schema["segments"]["min"] == 1
    assert schema["solver"]["choices"] == ["rp", "sc"]
    assert schema["up"]["size"] == 3
    assert schema["tags"]["item_type"] == "str"


def test_side():
    assert Side.from_value("left") is Side.LEFT
    assert Side.from_value("R") is Side.RIGHT
    assert Side.from_value(Side.CENTER) is Side.CENTER
    assert Side.LEFT.mirror is Side.RIGHT
    assert Side.CENTER.mirror is Side.CENTER
    assert Side.RIGHT.multiplier == -1
    assert str(Side.LEFT) == "L"
    with pytest.raises(ValueError):
        Side.from_value("up")


# ------------------------------------------------------------- TableField
def test_table_field_defaults_to_empty():
    from tik.core.fields import Column, TableField

    field = TableField(columns=(Column("label"),))
    assert field.default == []
    assert field.type_name == "table"


def test_table_field_coerces_rows_to_dicts():
    from tik.core.fields import Column, Schema, TableField

    class Holder(Schema):
        rows = TableField(
            columns=(Column("label"), Column("mode", "choice", choices=("a", "b")))
        )

    holder = Holder()
    holder.rows = [{"label": "chest", "mode": "a"}]
    assert holder.rows == [{"label": "chest", "mode": "a"}]


def test_table_field_rejects_a_non_list():
    from tik.core.fields import Column, FieldValidationError, Schema, TableField

    class Holder(Schema):
        rows = TableField(columns=(Column("label"),))

    holder = Holder()
    with pytest.raises(FieldValidationError):
        holder.rows = "chest"


def test_table_field_rejects_unknown_columns():
    from tik.core.fields import Column, FieldValidationError, Schema, TableField

    class Holder(Schema):
        rows = TableField(columns=(Column("label"),))

    holder = Holder()
    with pytest.raises(FieldValidationError):
        holder.rows = [{"label": "chest", "nope": 1}]


def test_table_field_rejects_out_of_range_choices():
    from tik.core.fields import Column, FieldValidationError, Schema, TableField

    class Holder(Schema):
        rows = TableField(columns=(Column("mode", "choice", choices=("a", "b")),))

    holder = Holder()
    with pytest.raises(FieldValidationError):
        holder.rows = [{"mode": "z"}]


def test_table_field_fills_missing_columns():
    from tik.core.fields import Column, Schema, TableField

    class Holder(Schema):
        rows = TableField(
            columns=(Column("label"), Column("mode", "choice", choices=("a",)))
        )

    holder = Holder()
    holder.rows = [{"label": "chest"}]
    assert holder.rows == [{"label": "chest", "mode": ""}]


def test_table_field_schema_carries_columns():
    from tik.core.fields import Column, TableField

    field = TableField(
        columns=(Column("mode", "choice", choices=("a", "b"), choices_from="modes"),)
    )
    schema = field.to_schema()
    assert schema["type"] == "table"
    assert schema["columns"] == [
        {
            "name": "mode",
            "kind": "choice",
            "choices": ["a", "b"],
            "choices_from": "modes",
            "label": "Mode",
        }
    ]


def test_last_fields_render_after_the_others():
    """A trailing field is a property of its role, not of one UI."""
    from tik.core.fields import Schema

    class Base(Schema):
        trailing = StringField("", last=True)
        early = IntField(1)

    class Child(Base):
        own = BoolField(False)

    assert list(Child.fields()) == ["early", "own", "trailing"]


def test_field_order_is_otherwise_definition_order():
    from tik.core.fields import Schema

    class Ordered(Schema):
        first = IntField(1)
        second = IntField(2)
        third = IntField(3)

    assert list(Ordered.fields()) == ["first", "second", "third"]


# --------------------------------------------------------------- field groups

TUNING = FieldGroup("Tuning", collapsed=True)


class Grouped(Schema):
    plain = IntField(1)
    legacy = IntField(2, group="Geometry")
    tuned = FloatField(0.5, group=TUNING)
    also_tuned = FloatField(1.5, group=TUNING)


def test_a_field_group_survives_declaration():
    field = Grouped.fields()["tuned"]
    assert isinstance(field.group, FieldGroup)
    assert field.group.label == "Tuning"
    assert field.group.collapsed is True


def test_a_plain_string_group_still_works():
    """Back-compat: callers passing a bare string keep today's behaviour."""
    field = Grouped.fields()["legacy"]
    assert isinstance(field.group, FieldGroup)
    assert field.group.label == "Geometry"
    assert field.group.collapsed is False


def test_an_ungrouped_field_has_no_group():
    assert Grouped.fields()["plain"].group is None


def test_the_same_group_object_is_shared():
    fields = Grouped.fields()
    assert fields["tuned"].group == fields["also_tuned"].group


def test_schema_keeps_group_as_a_label_string():
    """Anything reading a schema today must be unaffected."""
    schema = Grouped.schema()
    assert schema["tuned"]["group"] == "Tuning"
    assert schema["tuned"]["group_collapsed"] is True
    assert schema["legacy"]["group"] == "Geometry"
    assert schema["legacy"]["group_collapsed"] is False
    assert schema["plain"]["group"] is None
    assert schema["plain"]["group_collapsed"] is False
    json.dumps(schema)  # still serialisable


def test_field_groups_compare_by_value():
    assert FieldGroup("A") == FieldGroup("A")
    assert FieldGroup("A", collapsed=True) != FieldGroup("A")


# ------------------------------------------------------------- vector fields


class Vectors(Schema):
    pair = Vector2Field((-60.0, 75.0), min=-89.0, max=89.0, labels=("Lower", "Upper"))
    triple = Vector3Field((0.0, 1.0, 0.0), labels=("X", "Y", "Z"))


def test_vector2_holds_two_floats():
    thing = Vectors()
    assert thing.pair == (-60.0, 75.0)
    thing.pair = (-10, 20)
    assert thing.pair == (-10.0, 20.0)


def test_vector2_rejects_the_wrong_arity():
    thing = Vectors()
    with pytest.raises(FieldValidationError):
        thing.pair = (1.0, 2.0, 3.0)


def test_vector_bounds_apply_to_every_component():
    thing = Vectors()
    with pytest.raises(FieldValidationError):
        thing.pair = (-95.0, 10.0)
    with pytest.raises(FieldValidationError):
        thing.pair = (-10.0, 95.0)


def test_vector_size_and_labels_reach_the_schema():
    schema = Vectors.schema()
    assert schema["pair"]["type"] == "vector"
    assert schema["pair"]["size"] == 2
    assert schema["pair"]["labels"] == ["Lower", "Upper"]
    assert schema["triple"]["size"] == 3
    json.dumps(schema)


def test_labels_default_to_none():
    class Bare(Schema):
        up = Vector3Field()

    assert Bare.schema()["up"]["labels"] is None


def test_a_vector_round_trips_through_values_and_apply():
    thing = Vectors()
    thing.pair = (-30.0, 45.0)
    restored = Vectors()
    restored.apply(thing.values())
    assert restored.pair == (-30.0, 45.0)


def test_vector2_rejects_a_size_override():
    with pytest.raises(TypeError):
        Vector2Field((0.0, 0.0), size=3)


def test_text_field_normalises_line_breaks_and_none():
    from tik.core.fields import TextField

    class Note(Schema):
        body = TextField("", language="python")

    note = Note()
    note.body = "a\r\nb\rc"
    assert note.body == "a\nb\nc"
    note.body = None
    assert note.body == ""
    with pytest.raises(FieldValidationError):
        note.body = 3
    schema = Note.schema()["body"]
    assert schema["type"] == "text" and schema["language"] == "python"


def test_text_field_is_exported_by_trigger_core():
    from tik.core.fields import TextField
    from tik.trigger.core import TextField as exported

    assert exported is TextField
