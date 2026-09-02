"""Scanning guide joints into pure RenderedGuide records."""

import pytest
from maya import cmds

import tik.maya as tm
import tik.trigger as trigger
from tik.trigger.guides import snapshot
from tik.trigger.maya import tags


@pytest.fixture(autouse=True)
def fresh_scene():
    trigger.load_plugins()
    cmds.file(new=True, force=True)
    yield
    cmds.file(new=True, force=True)


def tagged_joint(name, instance, role, index=0, parent=None, position=(0, 0, 0)):
    cmds.select(clear=True)
    if parent:
        cmds.select(parent)
    joint = cmds.joint(name=name)
    cmds.xform(joint, worldSpace=True, translation=position)
    tm.Joint(joint).meta.update({
        tags.KIND: tags.GUIDE, tags.MODULE: "fkchain", tags.INSTANCE: instance,
        tags.ROLE: role, tags.INDEX: index, tags.SIDE: "C",
    })
    return joint


def test_empty_scene_snapshots_nothing():
    assert snapshot.snapshot() == []


def test_snapshot_reports_identity_and_pose():
    tagged_joint("root_guide", "id1", "root", position=(1.0, 2.0, 3.0))
    found = snapshot.snapshot()
    assert len(found) == 1
    guide = found[0]
    assert guide.instance_id == "id1"
    assert guide.pair == ("root", 0)
    assert guide.position == pytest.approx((1.0, 2.0, 3.0))
    assert guide.parent is None


def test_snapshot_reports_the_dag_parent_as_a_guide_triple():
    root = tagged_joint("root_guide", "id1", "root")
    tagged_joint("seg_guide", "id1", "segment", 0, parent=root, position=(5.0, 0.0, 0.0))
    by_pair = {guide.pair: guide for guide in snapshot.snapshot()}
    assert by_pair[("segment", 0)].parent == ("id1", "root", 0)


def test_snapshot_reports_an_inter_module_parent():
    root = tagged_joint("spine_guide", "producer", "root")
    tagged_joint("arm_guide", "child", "root", parent=root)
    by_instance = {guide.instance_id: guide for guide in snapshot.snapshot()}
    assert by_instance["child"].parent == ("producer", "root", 0)


def test_untagged_joints_are_ignored():
    cmds.joint(name="just_a_joint")
    assert snapshot.snapshot() == []


def test_guide_attrs_are_reported():
    joint = tagged_joint("root_guide", "id1", "root")
    cmds.addAttr(joint, longName="twistWeight", attributeType="double", defaultValue=0.0)
    cmds.setAttr(f"{joint}.twistWeight", 0.75)
    guide = snapshot.snapshot()[0]
    assert guide.attrs["twistWeight"] == pytest.approx(0.75)


def test_meta_attributes_are_not_reported_as_guide_attrs():
    tagged_joint("root_guide", "id1", "root")
    guide = snapshot.snapshot()[0]
    assert not any(name.startswith(tm.META_PREFIX) for name in guide.attrs)
