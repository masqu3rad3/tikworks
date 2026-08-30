"""Tests for tik.core.fields and tik.core.side (no Maya required)."""

import json

import pytest

from tik.core.fields import (
    BoolField,
    ChoiceField,
    FieldValidationError,
    FloatField,
    IntField,
    ListField,
    NodeRefField,
    Schema,
    StringField,
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
        "segments", "ratio", "local", "title", "solver", "up", "tags", "target", "extra",
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
        rows = TableField(columns=(Column("label"), Column("mode", "choice", choices=("a", "b"))))

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
        rows = TableField(columns=(Column("label"), Column("mode", "choice", choices=("a",))))

    holder = Holder()
    holder.rows = [{"label": "chest"}]
    assert holder.rows == [{"label": "chest", "mode": ""}]


def test_table_field_schema_carries_columns():
    from tik.core.fields import Column, TableField

    field = TableField(columns=(Column("mode", "choice", choices=("a", "b"), choices_from="modes"),))
    schema = field.to_schema()
    assert schema["type"] == "table"
    assert schema["columns"] == [
        {"name": "mode", "kind": "choice", "choices": ["a", "b"],
         "choices_from": "modes", "label": "Mode"}
    ]
