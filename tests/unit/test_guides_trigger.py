"""Guides: .trg format, live-scene handler, kinematics from file."""

import json
from pathlib import Path

import pytest
from maya import cmds
from maya.api import OpenMaya

import tik.maya as tm
import tik.trigger as trigger
from tik.trigger.core import get_module
from tik.trigger.maya import Builder
from tik.trigger.core.exceptions import GuideError
from tik.trigger.guides import GuideFile, Guides

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def guides():
    backend = trigger.maya_backend()
    return Guides(backend)


def test_add_settings_attrs_export_import_roundtrip(guides, tmp_path):
    body = guides.add("base", name="body")
    arm = guides.add("arm", side="L", name="arm", parent=body, pole_pin=False)
    tail = guides.add("fkchain", name="tail", parent=body, segments=3)
    assert arm.pole_pin is False and arm.parent.instance_id == body.instance_id
    arm.pole_pin = True
    assert arm.pole_pin is True
    root = arm.root
    assert cmds.getAttr(f"{root.name}.pole_pin") is True
    with pytest.raises(AttributeError):
        arm.nope = 1
    cmds.xform(guides.backend.guide_node(tail.instance_id, "segment", 2).long_name, ws=True, t=(0, 3, -9))

    path = guides.export(tmp_path / "hero")
    assert path.suffix == ".trg"
    records = json.loads(path.read_text())["joints"]
    assert {record["module"] for record in records} == {"base", "arm", "fkchain"}
    root_record = next(record for record in records if record["name"] == root.name)
    assert root_record["parent"] == body.root.name
    assert root_record["settings"]["pole_pin"] is True

    guides.clear()
    assert guides.instances() == []
    handles = guides.import_(path)
    names = sorted((handle.name, handle.side.value) for handle in handles)
    assert names == [("arm", "L"), ("body", "C"), ("tail", "C")]
    new_arm = guides.find("arm", "L")
    assert new_arm.pole_pin is True and new_arm.parent.name == "body"
    tip = guides.backend.guide_node(guides.find("tail").instance_id, "segment", 2)
    assert tuple(round(value, 3) for value in tip.world_position) == (0.0, 3.0, -9.0)


def test_mirror_and_test_build(guides):
    body = guides.add("base", name="body")
    arm = guides.add("arm", side="L", name="arm", parent=body)
    cmds.xform(arm.root.long_name, ws=True, t=(3, 12, 1))
    mirrored = guides.mirror(arm)
    assert mirrored.side.value == "R" and mirrored.name == "arm"
    assert round(mirrored.root.world_position.x, 3) == -3.0
    assert mirrored.parent.instance_id == body.instance_id
    cmds.xform(arm.root.long_name, ws=True, t=(4, 12, 1))
    again = guides.mirror(arm)
    assert again.instance_id == mirrored.instance_id and round(again.root.world_position.x, 3) == -4.0
    with pytest.raises(GuideError):
        guides.mirror(body)
    report = guides.test_build(body, arm)
    assert report.count == 2 and cmds.objExists("test_rig")
    assert guides.find("arm", "L") is not None  # guides kept
    assert guides["body"].instance_id == body.instance_id
    with pytest.raises(GuideError):
        guides["ghost"]


def test_duplicate_copies_everything_with_a_unique_name(guides):
    body = guides.add("base", name="body")
    arm = guides.add("arm", side="L", name="arm", pole_pin=True)
    guides.connect("L_arm.root", "body.root")
    cmds.xform(arm.root.long_name, ws=True, t=(3, 12, 1))
    copy = guides.duplicate(arm)
    assert copy.key == "L_arm1" and copy.instance_id != arm.instance_id
    assert copy.settings == arm.settings and copy.inputs == {"root": "body.root"}
    assert round(copy.root.world_position.x, 3) == 3.0
    assert len(guides.instances()) == 3


# ------------------------------------------------------- mirror correctness
#
# Guide mirroring negates world X and flips rotateY/rotateZ. These tests pin it
# against an independently computed reflection matrix, so the assertions derive
# the truth rather than restating the implementation.
#
# Mirroring is conjugation by the reflection M, and conjugation distributes over
# a product: M(Rx*Ry*Rz)M = (MRxM)(MRyM)(MRzM). Each euler factor maps on its own
# -- MRx(a)M = Rx(a), MRy(b)M = Ry(-b), MRz(c)M = Rz(-c) -- so composition order
# never enters and (rx, -ry, -rz) is exact, not an approximation. That is why no
# matrix machinery is needed for a world-YZ mirror.

_REFLECT_YZ = OpenMaya.MMatrix(
    [-1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
)


def _world(node):
    return OpenMaya.MMatrix(cmds.getAttr(f"{node.long_name}.worldMatrix[0]"))


def _reflected(node):
    """The world matrix ``node`` should have after a world-YZ mirror."""
    return _REFLECT_YZ * _world(node) * _REFLECT_YZ


def _matrices_match(first, second, tolerance=1e-4):
    return all(abs(a - b) < tolerance for a, b in zip(first, second))


def _mirrored_pair(guides, role, position, rotation=(0, 0, 0)):
    """Place one guide of an arm, mirror it, and return (source, mirrored)."""
    body = guides.add("base", name="body")
    arm = guides.add("arm", side="L", name="arm", parent=body)
    source = guides.backend.guide_node(arm.instance_id, role)
    cmds.xform(source.long_name, ws=True, t=position, ro=rotation)
    mirrored = guides.mirror(arm)
    return source, guides.backend.guide_node(mirrored.instance_id, role)


def test_mirror_negates_world_x_and_leaves_yz(guides):
    source, target = _mirrored_pair(guides, "elbow", (7, 13, -2))
    assert round(target.world_position.x, 4) == -7.0
    assert round(target.world_position.y, 4) == 13.0
    assert round(target.world_position.z, 4) == -2.0
    assert round(source.world_position.x, 4) == 7.0  # source untouched


def test_mirror_matches_the_reflection_matrix(guides):
    """The property that makes a matrix implementation unnecessary."""
    source, target = _mirrored_pair(guides, "elbow", (7, 13, -2), (23, -41, 67))
    assert _matrices_match(_world(target), _reflected(source))


def test_mirror_is_exact_for_a_pure_rotation(guides):
    source, target = _mirrored_pair(guides, "hand", (5, 10, 0), (0, 90, 0))
    assert _matrices_match(_world(target), _reflected(source))


def test_mirror_is_its_own_inverse(guides):
    """Mirroring the mirror returns the original placement."""
    source, target = _mirrored_pair(guides, "elbow", (7, 13, -2), (23, -41, 67))
    before = list(_world(source))
    reflected_back = _REFLECT_YZ * _world(target) * _REFLECT_YZ
    assert _matrices_match(reflected_back, before)


def test_mirror_updates_an_existing_opposite_side(guides):
    body = guides.add("base", name="body")
    arm = guides.add("arm", side="L", name="arm", parent=body)
    source = guides.backend.guide_node(arm.instance_id, "elbow")
    cmds.xform(source.long_name, ws=True, t=(7, 13, -2), ro=(23, -41, 67))
    first = guides.mirror(arm)

    cmds.xform(source.long_name, ws=True, t=(9, 4, 3), ro=(-11, 52, 8))
    second = guides.mirror(arm)

    assert second.instance_id == first.instance_id
    target = guides.backend.guide_node(second.instance_id, "elbow")
    assert _matrices_match(_world(target), _reflected(source))


@pytest.mark.parametrize("rotate_order", [0, 1, 2, 3, 4, 5])
def test_mirror_holds_for_every_rotation_order(guides, rotate_order):
    """(rx, -ry, -rz) is order-independent; this proves it end to end.

    Only the source's order is changed. The comparison is between world
    matrices, which carry no rotation order, so a mirrored guide left on the
    default order must still land on the exact reflection.
    """
    body = guides.add("base", name="body")
    arm = guides.add("arm", side="L", name="arm", parent=body)
    source = guides.backend.guide_node(arm.instance_id, "elbow")
    cmds.setAttr(f"{source.long_name}.rotateOrder", rotate_order)
    cmds.xform(source.long_name, ws=True, t=(7, 13, -2), ro=(23, -41, 67))

    mirrored = guides.mirror(arm)
    target = guides.backend.guide_node(mirrored.instance_id, "elbow")

    assert _matrices_match(_world(target), _reflected(source))


# ------------------------------------------------------------ spaces storage