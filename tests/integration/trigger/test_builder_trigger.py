"""Builder: order, connections, bind parent, spaces, failures — against a real scene.

These used to run against a fake backend and a fake build context, which could
only prove that the builder called the methods the fake defined. Here the toy
modules build real nodes, so the assertions are about the rig.
"""

import pytest
from maya import cmds

import tik.maya as tm
import tik.trigger as trigger
from tik.trigger.core import (
    AttachError,
    BuildError,
    EventBus,
    GuideLayout,
    Input,
    IntField,
    Module,
    register_module,
    unregister_module,
)
from tik.trigger.guides import GuideScene
from tik.trigger.maya import Builder, tags


class ToyRoot(Module):
    """One controller driving one bind joint."""

    label = "Toy Root"
    sided = False
    guides = GuideLayout("root")
    inputs = ()
    outputs = ("root",)
    space_controls = ("root",)

    def draw_guides(self, guides) -> None:
        guides.joint("root", (0, 0, 0))

    def build(self, rig) -> None:
        joint = rig.bind_joint("root", match=rig.guide("root"))
        control = rig.controller("root", match=joint)
        tm.MatrixConstraint.create(control.transform, joint, maintain_offset=True)
        rig.output("root", joint)


class ToyChain(Module):
    """A root plus N segments, with one required and one optional input."""

    label = "Toy Chain"
    guides = GuideLayout("root", multi="segment", min=1)
    inputs = (Input("root", primary=True), Input("space", optional=True))
    outputs = ("root", "end")
    space_controls = ("fk",)
    segments = IntField(2, min=1)

    def guide_count(self) -> int:
        return self.segments

    def draw_guides(self, guides) -> None:
        previous = guides.joint("root", (0, 0, 0))
        for index in range(self.segments):
            previous = guides.joint("segment", (index + 1, 0, 0), index=index, parent=previous)

    def build(self, rig) -> None:
        guide_nodes = [rig.guide("root"), *rig.chain("segment")]
        rig.socket("root", match=guide_nodes[0])
        rig.socket("space", match=guide_nodes[0])

        joints, parent_joint = [], None
        for index, guide_node in enumerate(guide_nodes):
            joint = rig.bind_joint(str(index), parent=parent_joint, match=guide_node)
            joints.append(joint)
            parent_joint = joint
        rig.controller("fk", match=joints[0])
        rig.output("root", joints[0])
        rig.output("end", joints[-1])


class ToyBoom(Module):
    """Fails while building, to prove the builder reports which module broke."""

    sided = False
    guides = GuideLayout("root")
    inputs = ()
    outputs = ("root",)

    def draw_guides(self, guides) -> None:
        guides.joint("root", (0, 0, 0))

    def build(self, rig) -> None:
        raise RuntimeError("boom")


@pytest.fixture
def toys():
    cmds.file(new=True, force=True)
    trigger.load_plugins()
    for name, cls in (("toy_root", ToyRoot), ("toy_chain", ToyChain), ("toy_boom", ToyBoom)):
        register_module(name)(cls)
    yield GuideScene()
    for name in ("toy_root", "toy_chain", "toy_boom"):
        unregister_module(name)


@pytest.fixture
def pair(toys):
    """A root with a chain connected to it."""
    body = toys.add("toy_root", name="body")
    tail = toys.add("toy_chain", side="L", name="tail", segments=3, parent=body)
    return toys, body, tail


def _rows(handle, rows):
    handle.set(anim_spaces=rows)


# ------------------------------------------------------------------- build
def test_builds_in_order_and_connects(pair):
    scene, body, tail = pair
    events = EventBus()
    seen = []
    events.subscribe("progress", lambda **kw: seen.append(kw["label"]))

    report = Builder(events).build(document=scene.document, rig_name="rig", afterlife="hide")

    assert report.built == [body.instance_id, tail.instance_id]
    assert seen == ["Building body", "Building tail"]
    assert report.connections == [("L_tail.root", "body.root")]
    # the socket really is driven by the producer's output
    socket = report.rigs[tail.instance_id].attachments["root"]
    assert tm.Transform(socket.long_name).parent.name.endswith("socket_grp")
    driver = cmds.listConnections(socket.long_name, source=True, destination=False,
                                  type="decomposeMatrix") or []
    assert driver and driver[0].startswith("L_tail_attach_root")
    # afterlife="hide" leaves the guides in place but hidden
    assert not cmds.getAttr(f"{tags.GUIDE_HOLDER}.visibility")

    rig = report.rigs[tail.instance_id]
    assert len(rig.deform_joints) == 4  # root + 3 segments
    assert rig.name("upper", suffix="jnt") == "L_tail_upper_jnt"


def test_scene_node_sources_must_exist_and_optional_inputs_may_be_empty(pair):
    scene, _body, tail = pair
    tail.set_input("space", "some_jnt")
    with pytest.raises(AttachError) as info:
        Builder().build(document=scene.document, )
    assert "some_jnt" in str(info.value) and "L_tail.space" in str(info.value)

    tm.Transform.create(name="some_jnt")
    report = Builder().build(document=scene.document, afterlife="keep")
    assert ("L_tail.space", "some_jnt") in report.connections

    tail.set_input("root", "body.nope")
    with pytest.raises(AttachError) as info:
        Builder().build(document=scene.document, )
    assert "not built" in str(info.value)

    tail.set_input("root", "")
    tail.set_input("space", "")
    with pytest.raises(AttachError) as info:
        Builder().build(document=scene.document, )
    assert "required input" in str(info.value)


def test_a_failing_module_is_named_in_the_error(toys):
    boom = toys.add("toy_boom", name="kaboom")
    errors = []
    events = EventBus()
    events.subscribe("error", lambda **kw: errors.append(kw["context"]))

    with pytest.raises(BuildError) as info:
        Builder(events).build(document=toys.document, )

    assert info.value.instance_id == boom.instance_id
    assert errors == ["building kaboom"]


def test_missing_guides_fail_validation(pair):
    scene, _body, tail = pair
    # the segments are a chain, so deleting the first takes the rest with it
    cmds.delete(scene.guide_node(tail.instance_id, "segment", 0).long_name)

    with pytest.raises(BuildError) as info:
        Builder().build(document=scene.document, )
    assert "needs at least" in str(info.value)


def test_empty_scene_and_bad_afterlife(toys):
    assert Builder().build(document=toys.document, ).count == 0
    with pytest.raises(ValueError):
        Builder().build(document=toys.document, afterlife="burn")


# ------------------------------------------------------------- bind parent
def test_bind_parent_comes_from_the_producer(pair):
    """A connected module builds its bind joints inside the producer's."""
    scene, body, tail = pair
    report = Builder().build(document=scene.document, rig_name="rig", afterlife="keep")

    producer = report.rigs[body.instance_id]
    consumer = report.rigs[tail.instance_id]
    assert consumer.bind_parent.long_name == producer.outputs["root"].long_name
    # and the joints really are one hierarchy
    root_joint = consumer.deform_joints[0]
    assert root_joint.parent.long_name == producer.outputs["root"].long_name


def test_bind_parent_defaults_to_the_modules_own_group_when_unconnected(toys):
    solo = toys.add("toy_root", name="solo")
    report = Builder().build(document=toys.document, rig_name="rig", afterlife="keep")
    rig = report.rigs[solo.instance_id]
    assert rig.bind_parent.long_name == rig.groups.bind.long_name


# ------------------------------------------------------------------ spaces
def test_space_inputs_do_not_feed_build_order(toys):
    """An arm in head space while the head is in arm space is a normal rig."""
    first = toys.add("toy_root", name="a")
    second = toys.add("toy_root", name="b")
    _rows(first, [{"control": "root", "mode": "parent", "label": "b"}])
    _rows(second, [{"control": "root", "mode": "parent", "label": "a"}])
    first.set_input("root_b", "b.root")
    second.set_input("root_a", "a.root")

    report = Builder().build(document=toys.document, rig_name="rig", afterlife="keep")
    assert report.count == 2


def test_space_connections_are_grouped_by_control_and_mode(toys):
    toys.add("toy_root", name="body")
    toys.add("toy_root", name="head")
    arm = toys.add("toy_root", name="arm")
    _rows(arm, [
        {"control": "root", "mode": "parent", "label": "body"},
        {"control": "root", "mode": "parent", "label": "head"},
    ])
    arm.set_input("root_body", "body.root")
    arm.set_input("root_head", "head.root")

    report = Builder().build(document=toys.document, rig_name="rig", afterlife="keep")

    control = report.rigs[arm.instance_id].controller_by_role("root")
    assert control.transform.has_attr("parentSwitch")
    listed = cmds.attributeQuery("parentSwitch", node=control.transform.long_name, listEnum=True)[0]
    assert listed.split(":") == ["body", "head"]
    assert sorted(report.spaces) == [("arm.root_body", "body.root"), ("arm.root_head", "head.root")]


def test_row_order_is_enum_order(toys):
    toys.add("toy_root", name="body")
    toys.add("toy_root", name="head")
    arm = toys.add("toy_root", name="arm")
    _rows(arm, [
        {"control": "root", "mode": "parent", "label": "head"},
        {"control": "root", "mode": "parent", "label": "body"},
    ])
    arm.set_input("root_body", "body.root")
    arm.set_input("root_head", "head.root")

    report = Builder().build(document=toys.document, rig_name="rig", afterlife="keep")

    control = report.rigs[arm.instance_id].controller_by_role("root")
    listed = cmds.attributeQuery("parentSwitch", node=control.transform.long_name, listEnum=True)[0]
    assert listed.split(":") == ["head", "body"]


def test_an_unconnected_space_row_is_skipped(toys):
    arm = toys.add("toy_root", name="arm")
    _rows(arm, [{"control": "root", "mode": "parent", "label": "ghost"}])

    report = Builder().build(document=toys.document, rig_name="rig", afterlife="keep")

    control = report.rigs[arm.instance_id].controller_by_role("root")
    assert not control.transform.has_attr("parentSwitch")
    assert report.spaces == []
