"""Tests for the AimFrame construct."""

from maya import cmds

import tik.maya as tm


def _setup():
    base = tm.Transform.create(name="af_base")
    target = tm.Transform.create(name="af_target")
    target.translate = (10, 0, 0)
    up = tm.Transform.create(name="af_up")
    up.translate = (10, 0, 0)
    return base, target, up


def test_transform_sits_at_the_base():
    base, target, up = _setup()
    base.translate = (0, 3, 0)
    frame = tm.AimFrame.create(base, target, up, name="af")
    assert (frame.transform.world_translation - base.world_translation).length() < 1e-4


def test_x_axis_aims_at_the_target():
    base, target, up = _setup()
    target.translate = (0, 0, 12)
    frame = tm.AimFrame.create(base, target, up, name="af_aim")
    axis = frame.transform.world_axis("x")
    assert abs(axis.z - 1.0) < 1e-3


def test_local_translate_offsets_along_the_frame():
    base, target, up = _setup()
    frame = tm.AimFrame.create(base, target, up, name="af_offset")
    frame.transform.translate = (0, 5, 0)
    assert abs(frame.transform.world_translation.y - 5.0) < 1e-3


def test_rolling_the_up_target_rolls_the_frame():
    """The twist-awareness that a static captured offset cannot reproduce."""
    base, target, up = _setup()
    frame = tm.AimFrame.create(base, target, up, twist_axis="X", name="af_twist")
    frame.transform.translate = (0, 5, 0)
    before = frame.transform.world_translation
    up.rotate = (90, 0, 0)
    after = frame.transform.world_translation
    assert (after - before).length() > 1.0


def test_parented_frame_keeps_its_world_position():
    base, target, up = _setup()
    base.translate = (0, 4, 0)
    holder = tm.Transform.create(name="af_holder")
    holder.translate = (0, 0, 20)
    frame = tm.AimFrame.create(base, target, up, parent=holder, name="af_parent")
    assert (frame.transform.world_translation - base.world_translation).length() < 1e-3


def test_matrix_only_mode_creates_no_transform():
    base, target, up = _setup()
    frame = tm.AimFrame.create(base, target, up, name="af_plug", create_transform=False)
    assert frame.transform is None
    assert frame.matrix.node.type == "aimMatrix"


def test_up_target_defaults_to_the_aim_target():
    base, target, _up = _setup()
    frame = tm.AimFrame.create(base, target, name="af_default")
    assert frame.node["secondaryTargetMatrix"].node is not None


def test_rejects_a_bad_twist_axis():
    import pytest

    base, target, up = _setup()
    with pytest.raises(ValueError, match="twist_axis"):
        tm.AimFrame.create(base, target, up, twist_axis="W", name="af_bad")


def test_delete_removes_the_nodes():
    base, target, up = _setup()
    frame = tm.AimFrame.create(base, target, up, name="af_delete")
    node_name = frame.node.long_name
    frame.delete()
    assert not cmds.objExists(node_name)


def test_parented_frame_leaves_local_trs_at_zero():
    """Local TRS must stay free: the pole offset is expressed there."""
    base, target, up = _setup()
    base.translate = (0, 4, 0)
    holder = tm.Transform.create(name="af_zero_holder")
    holder.translate = (0, 0, 20)
    frame = tm.AimFrame.create(base, target, up, parent=holder, name="af_zero")
    assert frame.transform.translate.length() < 1e-6
    frame.transform.translate = (0, 5, 0)
    offset = frame.transform.world_translation - base.world_translation
    assert abs(offset.length() - 5.0) < 1e-3
