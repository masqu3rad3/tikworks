"""Tests for the MatrixConstraint construct."""

from maya import cmds

import tik.maya as tm
from tik.maya.constructs.matrix_constraint import MatrixConstraint


def _close(vector, expected, tolerance=1e-5):
    return all(
        abs(actual - expected) < tolerance for actual, expected in zip(vector, expected)
    )


def test_follows_driver_without_offset():
    driver = tm.Transform.create(name="driver")
    driven = tm.Transform.create(name="driven")
    driven.translate = (5, 0, 0)
    MatrixConstraint.create(driver, driven, maintain_offset=False)
    driver.translate = (1, 2, 3)
    assert _close(driven.world_translation, (1, 2, 3))


def test_maintain_offset():
    driver = tm.Transform.create(name="driver")
    driven = tm.Transform.create(name="driven")
    driven.translate = (5, 0, 0)
    MatrixConstraint.create(driver, driven, maintain_offset=True)
    driver.translate = (1, 0, 0)
    assert abs(driven.world_translation.x - 6) < 1e-6


def test_respects_driven_parent():
    parent = tm.Transform.create(name="parent")
    parent.translate = (10, 0, 0)
    driver = tm.Transform.create(name="driver")
    driven = tm.Transform.create(name="driven", parent=parent.name)
    MatrixConstraint.create(driver, driven, maintain_offset=False)
    driver.translate = (2, 0, 0)
    assert abs(driven.world_translation.x - 2) < 1e-6
    assert abs(driven.translate.x + 8) < 1e-6


def test_skip_channels():
    driver = tm.Transform.create(name="driver")
    driven = tm.Transform.create(name="driven")
    MatrixConstraint.create(
        driver,
        driven,
        maintain_offset=False,
        skip_translate=("y",),
        skip_rotate=("x", "y", "z"),
        skip_scale=("x", "y", "z"),
    )
    assert not cmds.listConnections(f"{driven.name}.ty", source=True, destination=False)
    assert cmds.listConnections(f"{driven.name}.tx", source=True, destination=False)
    assert not cmds.listConnections(f"{driven.name}.rx", source=True, destination=False)
    assert not cmds.listConnections(f"{driven.name}.sx", source=True, destination=False)


def test_joint_orientation_compensation():
    driver = tm.Transform.create(name="driver")
    driver.rotate = (0, 45, 0)
    joint = tm.Joint.create(name="jnt")
    joint.joint_orient = (0, 45, 0)
    MatrixConstraint.create(driver, joint, maintain_offset=False)
    assert abs(joint.rotate.y) < 1e-4
    driver.rotate = (0, 90, 0)
    assert abs(joint.rotate.y - 45) < 1e-4


def test_multiple_drivers_average():
    first = tm.Transform.create(name="first")
    second = tm.Transform.create(name="second")
    second.translate = (4, 0, 0)
    driven = tm.Transform.create(name="driven")
    constraint = MatrixConstraint.create([first, second], driven, maintain_offset=False)
    assert constraint.average is not None
    assert abs(driven.world_translation.x - 2) < 1e-6


def test_matrix_plug_driver():
    driver = tm.Transform.create(name="driver")
    driven = tm.Transform.create(name="driven")
    MatrixConstraint.create(driver["worldMatrix[0]"], driven, maintain_offset=False)
    driver.translate = (0, 7, 0)
    assert abs(driven.world_translation.y - 7) < 1e-6


def test_delete_cleans_nodes():
    driver = tm.Transform.create(name="driver")
    driven = tm.Transform.create(name="driven")
    constraint = MatrixConstraint.create(driver, driven, name="test")
    assert cmds.objExists("test_multMatrix")
    constraint.delete()
    assert not cmds.objExists("test_multMatrix")
    assert not cmds.listConnections(f"{driven.name}.t", source=True, destination=False)


def test_undoable():
    driver = tm.Transform.create(name="driver")
    driven = tm.Transform.create(name="driven")
    cmds.undoInfo(openChunk=True)
    MatrixConstraint.create(driver, driven, name="undo_me")
    cmds.undoInfo(closeChunk=True)
    cmds.undo()
    assert not cmds.objExists("undo_me_multMatrix")


def test_cutoff_ignores_transforms_at_or_above_it():
    """A driver under a moved group should not drag the driven when cut off."""
    cutoff_grp = tm.Transform.create(name="cutoff_grp")
    driver = tm.Transform.create(name="cut_driver", parent=cutoff_grp.long_name)
    driven = tm.Transform.create(name="cut_driven")

    tm.MatrixConstraint.create(driver, driven, maintain_offset=True, cutoff=cutoff_grp)

    cutoff_grp.translate = (0, 10, 0)
    assert driven.world_translation.length() < 1e-4

    driver.translate = (3, 0, 0)
    assert abs(driven.world_translation.x - 3.0) < 1e-4


def test_without_cutoff_the_group_still_drives():
    parent_grp = tm.Transform.create(name="plain_grp")
    driver = tm.Transform.create(name="plain_driver", parent=parent_grp.long_name)
    driven = tm.Transform.create(name="plain_driven")

    tm.MatrixConstraint.create(driver, driven, maintain_offset=True)

    parent_grp.translate = (0, 10, 0)
    assert abs(driven.world_translation.y - 10.0) < 1e-4


def test_maintain_offset_holds_a_joint_orientation():
    """A joint must not snap to the driver's orientation at build time.

    The rotation travels through the joint-orient strand, which has to carry
    the maintained offset like the translate/scale strands do.
    """
    joint = tm.Joint.create(name="offset_jnt")
    joint.joint_orient = (0.0, 35.0, 0.0)
    joint.translate = (2, 0, 0)
    driver = tm.Transform.create(name="offset_driver")
    driver.translate = (2, 0, 0)

    before_rotation = tuple(joint.world_axis("x"))
    before_position = joint.world_translation

    tm.MatrixConstraint.create(driver, joint, maintain_offset=True)

    after_rotation = tuple(joint.world_axis("x"))
    assert (joint.world_translation - before_position).length() < 1e-4
    for axis_before, axis_after in zip(before_rotation, after_rotation):
        assert abs(axis_before - axis_after) < 1e-4


def test_maintain_offset_joint_follows_the_driver_rigidly():
    """Once offset, the joint tracks the driver without snapping to it."""
    joint = tm.Joint.create(name="rigid_jnt")
    joint.joint_orient = (0.0, 35.0, 0.0)
    driver = tm.Transform.create(name="rigid_driver")

    tm.MatrixConstraint.create(driver, joint, maintain_offset=True)
    driver.rotate = (0, 20, 0)

    # The joint keeps its own 35 degrees and adds the driver's 20.
    assert (
        abs(
            joint.world_axis("x").angle(tm.Transform("rigid_driver").world_axis("x"))
            - __import__("math").radians(35)
        )
        < 1e-3
    )
