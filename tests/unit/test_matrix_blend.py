"""Tests for the MatrixBlend construct."""

from maya import cmds

import tik.maya as tm


def _pair():
    base = tm.Transform.create(name="blend_a")
    target = tm.Transform.create(name="blend_b")
    target.translate = (10, 0, 0)
    return base, target


def test_weight_zero_is_the_base():
    base, target = _pair()
    driven = tm.Transform.create(name="blend_driven")
    blend = tm.MatrixBlend.create(base, [target], name="pair")
    blend.weight_plug(0).value = 0.0
    tm.MatrixConstraint.create(blend.output, driven, maintain_offset=False)
    assert driven.world_translation.length() < 1e-4


def test_weight_one_is_the_target():
    base, target = _pair()
    driven = tm.Transform.create(name="blend_driven_one")
    blend = tm.MatrixBlend.create(base, [target], name="pair_one")
    blend.weight_plug(0).value = 1.0
    tm.MatrixConstraint.create(blend.output, driven, maintain_offset=False)
    assert abs(driven.world_translation.x - 10.0) < 1e-4


def test_weight_is_continuous():
    base, target = _pair()
    driven = tm.Transform.create(name="blend_driven_half")
    blend = tm.MatrixBlend.create(base, [target], name="pair_half")
    blend.weight_plug(0).value = 0.25
    tm.MatrixConstraint.create(blend.output, driven, maintain_offset=False)
    assert abs(driven.world_translation.x - 2.5) < 1e-4


def test_weights_accept_plugs():
    base, target = _pair()
    holder = tm.Transform.create(name="blend_holder")
    switch = holder["ikFk"].create("float", default=1.0, min=0.0, max=1.0)
    blend = tm.MatrixBlend.create(base, [target], [switch], name="pair_plug")
    assert cmds.listConnections(
        blend.weight_plug(0).path, source=True, destination=False
    )


def test_accepts_matrix_plugs_for_base_and_targets():
    base, target = _pair()
    blend = tm.MatrixBlend.create(
        base["worldMatrix[0]"], [target["worldMatrix[0]"]], name="pair_plugs"
    )
    blend.weight_plug(0).value = 1.0
    assert abs(blend.output.value[12] - 10.0) < 1e-4


def test_rejects_mismatched_weights():
    import pytest

    base, target = _pair()
    with pytest.raises(ValueError, match="one entry per target"):
        tm.MatrixBlend.create(base, [target], [0.5, 0.5], name="pair_bad")


def test_delete_removes_the_node():
    base, target = _pair()
    blend = tm.MatrixBlend.create(base, [target], name="pair_delete")
    node_name = blend.node.long_name
    blend.delete()
    assert not cmds.objExists(node_name)
