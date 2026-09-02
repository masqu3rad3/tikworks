"""Tests for the MatrixBlend construct."""

from maya import cmds

import tik.maya as tm


def _pair():
    a = tm.Transform.create(name="blend_a")
    b = tm.Transform.create(name="blend_b")
    b.translate = (10, 0, 0)
    return a, b


def test_weight_zero_is_the_base():
    a, b = _pair()
    driven = tm.Transform.create(name="blend_driven")
    blend = tm.MatrixBlend.create(a, [b], name="pair")
    blend.weight_plug(0).value = 0.0
    tm.MatrixConstraint.create(blend.output, driven, maintain_offset=False)
    assert driven.world_translation.length() < 1e-4


def test_weight_one_is_the_target():
    a, b = _pair()
    driven = tm.Transform.create(name="blend_driven_one")
    blend = tm.MatrixBlend.create(a, [b], name="pair_one")
    blend.weight_plug(0).value = 1.0
    tm.MatrixConstraint.create(blend.output, driven, maintain_offset=False)
    assert abs(driven.world_translation.x - 10.0) < 1e-4


def test_weight_is_continuous():
    a, b = _pair()
    driven = tm.Transform.create(name="blend_driven_half")
    blend = tm.MatrixBlend.create(a, [b], name="pair_half")
    blend.weight_plug(0).value = 0.25
    tm.MatrixConstraint.create(blend.output, driven, maintain_offset=False)
    assert abs(driven.world_translation.x - 2.5) < 1e-4


def test_weights_accept_plugs():
    a, b = _pair()
    holder = tm.Transform.create(name="blend_holder")
    switch = holder["ikFk"].create("float", default=1.0, min=0.0, max=1.0)
    blend = tm.MatrixBlend.create(a, [b], [switch], name="pair_plug")
    assert cmds.listConnections(
        blend.weight_plug(0).path, source=True, destination=False
    )


def test_accepts_matrix_plugs_for_base_and_targets():
    a, b = _pair()
    blend = tm.MatrixBlend.create(
        a["worldMatrix[0]"], [b["worldMatrix[0]"]], name="pair_plugs"
    )
    blend.weight_plug(0).value = 1.0
    assert abs(blend.output.value[12] - 10.0) < 1e-4


def test_rejects_mismatched_weights():
    import pytest

    a, b = _pair()
    with pytest.raises(ValueError, match="one entry per target"):
        tm.MatrixBlend.create(a, [b], [0.5, 0.5], name="pair_bad")


def test_delete_removes_the_node():
    a, b = _pair()
    blend = tm.MatrixBlend.create(a, [b], name="pair_delete")
    node_name = blend.node.long_name
    blend.delete()
    assert not cmds.objExists(node_name)
