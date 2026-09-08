"""Shape resolution: rigger override -> module manifest -> the fallback."""

from __future__ import annotations

from tik.trigger.core import shapes
from tik.trigger.core.module import Module


class Toy(Module):
    module_type = "toy"
    controls = ("ik", "fk", "pole")
    control_shapes = {"ik": "Cube", "fk": "Circle"}


def test_manifest_default_wins_when_nothing_is_overridden():
    toy = Toy()
    assert toy.resolve_control_shape("ik") == ("Cube", 1.0)
    assert toy.resolve_control_shape("fk") == ("Circle", 1.0)


def test_an_undeclared_control_falls_back():
    """'pole' is a control with no manifest default."""
    assert Toy().resolve_control_shape("pole") == (shapes.DEFAULT_SHAPE, 1.0)


def test_an_override_wins_over_the_manifest():
    toy = Toy()
    toy.control_shape_overrides = [{"control": "ik", "shape": "Diamond", "size": 2.0}]
    assert toy.resolve_control_shape("ik") == ("Diamond", 2.0)
    # Untouched controls keep their manifest default.
    assert toy.resolve_control_shape("fk") == ("Circle", 1.0)


def test_resolution_is_per_field_not_per_row():
    """A row setting only a size keeps the manifest shape, and vice versa."""
    toy = Toy()
    toy.control_shape_overrides = [
        {"control": "ik", "size": 3.0},
        {"control": "fk", "shape": "Diamond"},
    ]
    assert toy.resolve_control_shape("ik") == ("Cube", 3.0)
    assert toy.resolve_control_shape("fk") == ("Diamond", 1.0)


def test_deleting_a_row_reverts_to_the_module_default():
    toy = Toy()
    toy.control_shape_overrides = [{"control": "ik", "shape": "Diamond"}]
    assert toy.resolve_control_shape("ik") == ("Diamond", 1.0)
    toy.control_shape_overrides = []
    assert toy.resolve_control_shape("ik") == ("Cube", 1.0)


def test_an_unresolvable_override_falls_back_to_the_manifest():
    toy = Toy()
    toy.control_shape_overrides = [{"control": "ik", "shape": "NotAShape", "size": 2.0}]
    # The size still applies: only the unknown name is discarded.
    assert toy.resolve_control_shape("ik") == ("Cube", 2.0)


def test_the_table_is_sparse_and_round_trips():
    toy = Toy()
    toy.control_shape_overrides = [{"control": "ik", "shape": "Diamond"}]
    values = toy.values()
    assert values["control_shape_overrides"] == [
        {"control": "ik", "shape": "Diamond", "size": ""}
    ]
    other = Toy()
    other.apply(values, strict=False)
    assert other.resolve_control_shape("ik") == ("Diamond", 1.0)


def test_the_field_declares_its_row_source():
    assert Toy.control_shape_overrides.rows_from == "control_names"
    kinds = {c.name: c.kind for c in Toy.control_shape_overrides.columns}
    assert kinds == {"control": "choice", "shape": "shape", "size": "float"}


def test_defaults_follow_settings_when_a_module_overrides_them():
    class Chain(Module):
        module_type = "chain"

        @classmethod
        def control_names(cls, settings=None):
            count = int((settings or {}).get("segments", 2))
            return tuple(f"fk{index}" for index in range(count))

        @classmethod
        def control_shape_defaults(cls, settings=None):
            return {role: "Circle" for role in cls.control_names(settings)}

    assert Chain.control_shape_defaults({"segments": 3}) == {
        "fk0": "Circle",
        "fk1": "Circle",
        "fk2": "Circle",
    }


def test_limb_control_shapes_mirrors_limb_control_names():
    from tik.trigger.systems.limb import limb_control_names, limb_control_shapes

    labels = ("upperarm", "lowerarm", "hand")
    assert tuple(limb_control_shapes(labels=labels)) == limb_control_names(
        labels=labels
    )
    assert all(
        shapes.has_shape(name) for name in limb_control_shapes(labels=labels).values()
    )
