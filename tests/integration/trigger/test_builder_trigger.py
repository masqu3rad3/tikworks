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
from toy_modules import ToyStill, ToyTiers


class ToyRoot(Module):
    """One controller driving one bind joint."""

    label = "Toy Root"
    sided = False
    guides = GuideLayout("root")
    inputs = ()
    outputs = ("root",)
    controls = ("root",)

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
    controls = ("fk",)
    segments = IntField(2, min=1)

    def guide_count(self) -> int:
        return self.segments

    def draw_guides(self, guides) -> None:
        previous = guides.joint("root", (0, 0, 0))
        for index in range(self.segments):
            previous = guides.joint(
                "segment", (index + 1, 0, 0), index=index, parent=previous
            )

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


class ToyFan(Module):
    """One controller per segment, so the manifest follows a setting."""

    label = "Toy Fan"
    sided = False
    guides = GuideLayout("root", multi="segment", min=1)
    inputs = ()
    outputs = ("root",)
    segments = IntField(2, min=1)

    @classmethod
    def control_names(cls, settings=None):
        count = int((settings or {}).get("segments", cls.segments.default))
        return tuple(f"fk{index}" for index in range(count))

    def guide_count(self) -> int:
        return self.segments

    def draw_guides(self, guides) -> None:
        previous = guides.joint("root", (0, 0, 0))
        for index in range(self.segments):
            previous = guides.joint(
                "segment", (index + 1, 0, 0), index=index, parent=previous
            )

    def build(self, rig) -> None:
        joint = rig.bind_joint("root", match=rig.guide("root"))
        for index in range(self.segments):
            rig.controller(f"fk{index}", match=joint)
        rig.output("root", joint)


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
    for name, cls in (
        ("toy_root", ToyRoot),
        ("toy_chain", ToyChain),
        ("toy_boom", ToyBoom),
        ("toy_fan", ToyFan),
        ("toy_tiers", ToyTiers),
        ("toy_still", ToyStill),
    ):
        register_module(name)(cls)
    yield GuideScene()
    for name in ("toy_root", "toy_chain", "toy_boom", "toy_fan", "toy_tiers", "toy_still"):
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

    report = Builder(events).build(
        document=scene.document, afterlife="hide"
    )

    assert report.built == [body.instance_id, tail.instance_id]
    assert seen == ["Building body", "Building tail"]
    assert report.connections == [("L_tail.root", "body.root")]
    # the socket really is driven by the producer's output
    socket = report.rigs[tail.instance_id].attachments["root"]
    assert tm.Transform(socket.long_name).parent.name.endswith("socket_grp")
    driver = (
        cmds.listConnections(
            socket.long_name, source=True, destination=False, type="decomposeMatrix"
        )
        or []
    )
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
        Builder().build(
            document=scene.document,
        )
    assert "some_jnt" in str(info.value) and "L_tail.space" in str(info.value)

    tm.Transform.create(name="some_jnt")
    report = Builder().build(document=scene.document, afterlife="keep")
    assert ("L_tail.space", "some_jnt") in report.connections

    tail.set_input("root", "body.nope")
    with pytest.raises(AttachError) as info:
        Builder().build(
            document=scene.document,
        )
    assert "not built" in str(info.value)

    tail.set_input("root", "")
    tail.set_input("space", "")
    with pytest.raises(AttachError) as info:
        Builder().build(
            document=scene.document,
        )
    assert "required input" in str(info.value)


def test_a_failing_module_is_named_in_the_error(toys):
    boom = toys.add("toy_boom", name="kaboom")
    errors = []
    events = EventBus()
    events.subscribe("error", lambda **kw: errors.append(kw["context"]))

    with pytest.raises(BuildError) as info:
        Builder(events).build(
            document=toys.document,
        )

    assert info.value.instance_id == boom.instance_id
    assert errors == ["building kaboom"]


def test_missing_guides_fail_validation(pair):
    scene, _body, tail = pair
    # the segments are a chain, so deleting the first takes the rest with it
    cmds.delete(scene.guide_node(tail.instance_id, "segment", 0).long_name)

    with pytest.raises(BuildError) as info:
        Builder().build(
            document=scene.document,
        )
    assert "needs at least" in str(info.value)


def test_empty_scene_and_bad_afterlife(toys):
    assert (
        Builder()
        .build(
            document=toys.document,
        )
        .count
        == 0
    )
    with pytest.raises(ValueError):
        Builder().build(document=toys.document, afterlife="burn")


# ------------------------------------------------------------- bind parent
def test_bind_parent_comes_from_the_producer(pair):
    """A connected module builds its bind joints inside the producer's."""
    scene, body, tail = pair
    report = Builder().build(document=scene.document, afterlife="keep")

    producer = report.rigs[body.instance_id]
    consumer = report.rigs[tail.instance_id]
    assert consumer.bind_parent.long_name == producer.outputs["root"].long_name
    # and the joints really are one hierarchy
    root_joint = consumer.deform_joints[0]
    assert root_joint.parent.long_name == producer.outputs["root"].long_name


def test_bind_parent_defaults_to_the_modules_own_group_when_unconnected(toys):
    solo = toys.add("toy_root", name="solo")
    report = Builder().build(document=toys.document, afterlife="keep")
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

    report = Builder().build(document=toys.document, afterlife="keep")
    assert report.count == 2


def test_space_connections_are_grouped_by_control_and_mode(toys):
    toys.add("toy_root", name="body")
    toys.add("toy_root", name="head")
    arm = toys.add("toy_root", name="arm")
    _rows(
        arm,
        [
            {"control": "root", "mode": "parent", "label": "body"},
            {"control": "root", "mode": "parent", "label": "head"},
        ],
    )
    arm.set_input("root_body", "body.root")
    arm.set_input("root_head", "head.root")

    report = Builder().build(document=toys.document, afterlife="keep")

    control = report.rigs[arm.instance_id].controller_by_role("root")
    assert control.transform.has_attr("parentSwitch")
    listed = cmds.attributeQuery(
        "parentSwitch", node=control.transform.long_name, listEnum=True
    )[0]
    assert listed.split(":") == ["body", "head"]
    assert sorted(report.spaces) == [
        ("arm.root_body", "body.root"),
        ("arm.root_head", "head.root"),
    ]


def test_row_order_is_enum_order(toys):
    toys.add("toy_root", name="body")
    toys.add("toy_root", name="head")
    arm = toys.add("toy_root", name="arm")
    _rows(
        arm,
        [
            {"control": "root", "mode": "parent", "label": "head"},
            {"control": "root", "mode": "parent", "label": "body"},
        ],
    )
    arm.set_input("root_body", "body.root")
    arm.set_input("root_head", "head.root")

    report = Builder().build(document=toys.document, afterlife="keep")

    control = report.rigs[arm.instance_id].controller_by_role("root")
    listed = cmds.attributeQuery(
        "parentSwitch", node=control.transform.long_name, listEnum=True
    )[0]
    assert listed.split(":") == ["head", "body"]


def test_an_unconnected_space_row_is_skipped(toys):
    arm = toys.add("toy_root", name="arm")
    _rows(arm, [{"control": "root", "mode": "parent", "label": "ghost"}])

    report = Builder().build(document=toys.document, afterlife="keep")

    control = report.rigs[arm.instance_id].controller_by_role("root")
    assert not control.transform.has_attr("parentSwitch")
    assert report.spaces == []


def test_a_space_on_a_dynamic_control_builds_a_switch(toys):
    """A control the manifest computes from a setting is a real space target."""
    toys.add("toy_root", name="anchor")
    fan = toys.add("toy_fan", name="fan", segments=3)
    _rows(fan, [{"control": "fk2", "mode": "parent", "label": "anchor"}])
    fan.set_input("fk2_anchor", "anchor.root")

    report = Builder().build(document=toys.document, afterlife="keep")

    control = report.rigs[fan.instance_id].controller_by_role("fk2")
    assert control is not None
    assert control.transform.has_attr("parentSwitch")


def test_a_space_on_a_removed_control_warns_and_still_builds(toys):
    """Lowering a count must cost a warning, never the rig."""
    toys.add("toy_root", name="anchor")
    fan = toys.add("toy_fan", name="fan", segments=1)
    _rows(fan, [{"control": "fk2", "mode": "parent", "label": "anchor"}])
    fan.set_input("fk2_anchor", "anchor.root")

    events = EventBus()
    logged = []
    events.subscribe("log", lambda **kw: logged.append((kw["level"], kw["message"])))
    report = Builder(events).build(
        document=toys.document, afterlife="keep"
    )

    assert fan.instance_id in report.built
    assert report.rigs[fan.instance_id].controller_by_role("fk2") is None
    assert any("fk2" in message for level, message in logged if level == "warning")


def test_a_guide_with_no_document_entry_is_not_built(toys):
    """An orphan used to build as a phantom module named after its type, with
    default settings and no connections. Orphans are reported, never built."""
    handle = toys.add("toy_root", name="body")
    assert toys.guide_nodes(handle.instance_id) != {}
    # the joints stay, the entry goes: exactly what an orphan is
    toys.document.modules = [
        entry
        for entry in toys.document.modules
        if entry.instance_id != handle.instance_id
    ]
    assert toys.find_instances("scene") == []
    assert toys.diff().orphans


def test_modules_build_under_the_scaffold(pair):
    scene, body, tail = pair
    report = Builder().build(document=scene.document, afterlife="keep")
    assert report.scaffold.trigger.long_name == "|rig_grp|trigger_grp"
    for ctx in report.rigs.values():
        assert ctx.groups.limb.parent.long_name == "|rig_grp|trigger_grp"
        assert ctx.rig_root.long_name == "|rig_grp|trigger_grp"
        assert ctx.scaffold is report.scaffold
    # a second build reuses the same scaffold rather than making another
    Builder().build(document=scene.document, afterlife="keep")
    assert len(cmds.ls("rig_grp")) == 1


def test_preferences_drive_module_visibility(pair):
    scene, body, tail = pair
    report = Builder().build(document=scene.document, afterlife="keep")
    prefs = report.scaffold.preferences.transform
    groups = [ctx.groups for ctx in report.rigs.values()]
    assert all(group.control.visibility for group in groups)
    prefs["controls"].value = False
    assert not any(group.control.visibility for group in groups)
    assert not any(group.rig.visibility for group in groups)  # default off
    prefs["rig"].value = True
    assert all(group.rig.visibility for group in groups)
    prefs["joints"].value = False
    assert not any(group.bind.visibility for group in groups)
    # the module-level switches are now owned by the preferences
    for group in groups:
        for attr in ("controlVisibility", "rigVisibility", "bindVisibility"):
            assert group.limb[attr].locked, f"{group.limb.name}.{attr}"


def test_preferences_drive_module_display_mode(pair):
    scene, body, tail = pair
    report = Builder().build(document=scene.document, afterlife="keep")
    prefs = report.scaffold.preferences.transform
    for ctx in report.rigs.values():
        assert ctx.groups.rig["overrideEnabled"].value
        assert ctx.groups.bind["overrideEnabled"].value
    prefs["rigDisplay"].value = 1
    prefs["jointsDisplay"].value = 2
    for ctx in report.rigs.values():
        assert ctx.groups.rig["overrideDisplayType"].value == 1
        assert ctx.groups.bind["overrideDisplayType"].value == 2


# ------------------------------------------------------------------- tiers
def _shape_visible(controller):
    return [shape.visibility for shape in controller.transform.shapes]


def test_visibilities_control_has_one_enum_per_module_with_controls(toys):
    toys.add("toy_tiers", name="tiers")
    toys.add("toy_root", name="body")
    report = Builder().build(document=toys.document, afterlife="keep")
    vis = report.scaffold.visibilities.transform
    assert vis["tiers"].exists() and vis["body"].exists()
    assert cmds.attributeQuery("tiers", node=vis.long_name, listEnum=True) == [
        "primary:secondary:tertiary:all"
    ]
    assert vis["tiers"].value == 3
    assert not vis["tiers"].keyable and vis["tiers"].visible


def test_tiers_are_exclusive_and_all_shows_everything(toys):
    handle = toys.add("toy_tiers", name="tiers")
    report = Builder().build(document=toys.document, afterlife="keep")
    ctx = report.rigs[handle.instance_id]
    vis = report.scaffold.visibilities.transform["tiers"]
    by_tier = {
        controller.transform.meta[tags.TIER]: controller
        for controller in ctx.controllers
        if tags.TIER in controller.transform.meta
    }
    assert set(by_tier) == {"primary", "secondary", "tertiary"}
    for index, tier in enumerate(("primary", "secondary", "tertiary")):
        vis.value = index
        for other, controller in by_tier.items():
            expected = other == tier
            assert all(
                state == expected for state in _shape_visible(controller)
            ), f"{other} at enum={tier}"
    vis.value = 3
    for controller in by_tier.values():
        assert all(_shape_visible(controller))


def test_tier_enum_hides_shapes_not_transforms(toys):
    handle = toys.add("toy_tiers", name="tiers")
    report = Builder().build(document=toys.document, afterlife="keep")
    ctx = report.rigs[handle.instance_id]
    report.scaffold.visibilities.transform["tiers"].value = 1  # secondary only
    primary = ctx.controller_by_role("primary")
    assert primary.transform.visibility
    assert not any(_shape_visible(primary))


def test_tweak_shapes_ignore_the_tier_enum(toys):
    handle = toys.add("toy_tiers", name="tiers")
    report = Builder().build(document=toys.document, afterlife="keep")
    ctx = report.rigs[handle.instance_id]
    tweak = ctx.controller_by_role("primary_tweak")
    report.scaffold.visibilities.transform["tiers"].value = 1
    assert all(_shape_visible(tweak))
    # the tweak's own switch is untouched
    ctx.controller_by_role("primary").transform["tweakVis"].value = True
    assert tweak.transform.visibility


def test_module_without_controls_adds_no_enum(toys):
    toys.add("toy_root", name="body")
    toys.add("toy_still", name="still")
    report = Builder().build(document=toys.document, afterlife="keep")
    vis = report.scaffold.visibilities.transform
    assert vis["body"].exists()
    assert not vis["still"].exists()
