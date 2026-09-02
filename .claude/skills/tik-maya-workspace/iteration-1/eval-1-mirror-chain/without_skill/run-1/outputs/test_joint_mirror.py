"""Tests for Joint.mirror (behavior-mirroring a joint chain across a plane)."""

import pytest
from maya import cmds

from tik.maya.types.joint import Joint


def _build_left_arm_chain():
    """Create a simple 3-joint left arm chain offset from the YZ plane.

    World positions:
        L_shoulder (2, 10, 0) -> L_elbow (6, 10, -1) -> L_wrist (10, 10, 0)
    """
    shoulder = Joint.create(name="L_shoulder", position=(2, 10, 0))
    elbow = Joint.create(name="L_elbow", parent=shoulder, position=(4, 0, -1))
    wrist = Joint.create(name="L_wrist", parent=elbow, position=(4, 0, 1))
    cmds.select(clear=True)
    return shoulder, elbow, wrist


def _world_pos(node):
    """Return the world-space position of a node (wrapper or name)."""
    name = node if isinstance(node, str) else node.long_name
    return cmds.xform(name, query=True, worldSpace=True, translation=True)


def test_mirror_returns_wrapped_joints():
    shoulder, _, _ = _build_left_arm_chain()

    mirrored = shoulder.mirror()

    assert len(mirrored) == 3
    for jnt in mirrored:
        assert isinstance(jnt, Joint)
        assert cmds.nodeType(jnt.long_name) == "joint"


def test_mirror_yz_positions():
    """Mirroring across YZ negates world X and keeps Y/Z."""
    shoulder, elbow, wrist = _build_left_arm_chain()

    mirrored = shoulder.mirror(plane="YZ")

    for src, dst in zip((shoulder, elbow, wrist), mirrored):
        src_pos = _world_pos(src)
        dst_pos = _world_pos(dst)
        expected = (-src_pos[0], src_pos[1], src_pos[2])
        assert dst_pos == pytest.approx(expected, abs=1e-6)


def test_mirror_preserves_hierarchy():
    shoulder, _, _ = _build_left_arm_chain()

    mirrored = shoulder.mirror()

    # Mirrored root lives at the same level as the source root (world here).
    assert mirrored[0].parent is None
    # Chain hierarchy is preserved on the mirrored side.
    assert mirrored[1].parent.long_name == mirrored[0].long_name
    assert mirrored[2].parent.long_name == mirrored[1].long_name


def test_mirror_search_replace_renames():
    shoulder, _, _ = _build_left_arm_chain()

    mirrored = shoulder.mirror(search="L_", replace="R_")

    names = [jnt.name for jnt in mirrored]
    assert names == ["R_shoulder", "R_elbow", "R_wrist"]


def test_mirror_behavior_gives_symmetric_motion():
    """Behavior mirror: identical local rotations produce symmetric poses.

    Rotate the source and mirrored roots by the same local rotation values;
    the mirrored wrist must stay the YZ-mirror of the source wrist.
    """
    shoulder, _, wrist = _build_left_arm_chain()

    mirrored = shoulder.mirror(plane="YZ", behavior=True, search="L_", replace="R_")
    mirrored_root, mirrored_wrist = mirrored[0], mirrored[2]

    rotation = (25.0, -40.0, 15.0)
    shoulder.rotate = rotation
    mirrored_root.rotate = rotation

    src_pos = _world_pos(wrist)
    dst_pos = _world_pos(mirrored_wrist)
    expected = (-src_pos[0], src_pos[1], src_pos[2])
    assert dst_pos == pytest.approx(expected, abs=1e-5)


def test_mirror_xy_and_xz_planes():
    shoulder, elbow, wrist = _build_left_arm_chain()
    sources = (shoulder, elbow, wrist)

    mirrored_xy = shoulder.mirror(plane="XY")
    for src, dst in zip(sources, mirrored_xy):
        src_pos = _world_pos(src)
        expected = (src_pos[0], src_pos[1], -src_pos[2])
        assert _world_pos(dst) == pytest.approx(expected, abs=1e-6)

    mirrored_xz = shoulder.mirror(plane="xz")  # case-insensitive
    for src, dst in zip(sources, mirrored_xz):
        src_pos = _world_pos(src)
        expected = (src_pos[0], -src_pos[1], src_pos[2])
        assert _world_pos(dst) == pytest.approx(expected, abs=1e-6)


def test_mirror_from_mid_chain_keeps_parent():
    """Mirroring a sub-chain parents the mirror under the same parent.

    For a parented joint, Maya mirrors across the plane in the parent's
    space, through the parent's origin. The shoulder here is axis-aligned
    at world (2, 10, 0), so the YZ mirror plane is the world plane x = 2.
    """
    shoulder, elbow, wrist = _build_left_arm_chain()

    mirrored = elbow.mirror()

    assert len(mirrored) == 2
    assert mirrored[0].parent.long_name == shoulder.long_name
    plane_x = _world_pos(shoulder)[0]
    for src, dst in zip((elbow, wrist), mirrored):
        src_pos = _world_pos(src)
        expected = (2 * plane_x - src_pos[0], src_pos[1], src_pos[2])
        assert _world_pos(dst) == pytest.approx(expected, abs=1e-6)


def test_mirror_invalid_plane_raises():
    shoulder, _, _ = _build_left_arm_chain()
    with pytest.raises(ValueError):
        shoulder.mirror(plane="ZZ")


def test_mirror_search_without_replace_raises():
    shoulder, _, _ = _build_left_arm_chain()
    with pytest.raises(ValueError):
        shoulder.mirror(search="L_")
    with pytest.raises(ValueError):
        shoulder.mirror(replace="R_")


def test_mirror_keeps_selection():
    shoulder, _, _ = _build_left_arm_chain()
    cmds.select(shoulder.long_name, replace=True)

    shoulder.mirror()

    assert cmds.ls(selection=True) == [shoulder.name]
