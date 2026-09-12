"""Each guide kind renders as the one thing its kind says it is.

Against a real Maya. The kind vocabulary itself -- what is derived, what is
declared, and what is refused -- is unit-tested in
``tests/unit/test_guide_kinds_trigger.py``; this file is about what actually
appears in the scene.
"""

import pytest
from maya import cmds

import tik.maya as tm
import tik.trigger as trigger
from tik.trigger.core import (
    GuideKind,
    GuideLayout,
    Module,
    register_module,
    unregister_module,
)
from tik.trigger.guides import nodes


class ToyKinds(Module):
    """One guide of every kind, so each renders somewhere observable."""

    label = "Toy Kinds"
    guides = GuideLayout(
        "root",
        "tip",
        "aim",
        multi="rail",
        reference=("aim",),
        driven=("rail",),
    )
    inputs = ()
    outputs = ("root",)

    def draw_guides(self, guides) -> None:
        root = guides.joint("root", (0, 0, 0))
        guides.joint("tip", (5 * guides.side_mult, 0, 0), parent=root)
        guides.joint("aim", (0, 0, 8), parent=root)
        guides.joint("rail", (2 * guides.side_mult, 0, 0), index=0, parent=root)

    def build(self, rig) -> None:
        rig.output("root", rig.bind_joint("root", match=rig.guide("root")))


@pytest.fixture
def scene():
    """A session's guides. The session owns them; the scene renders them."""
    from tik.trigger.session import Session

    trigger.load_plugins()
    register_module("toy_kinds")(ToyKinds)
    cmds.file(new=True, force=True)
    try:
        yield Session().guides
    finally:
        cmds.file(new=True, force=True)
        unregister_module("toy_kinds")


def drawn(scene, side="L"):
    """Draw one ToyKinds and return ``{role: long name}``."""
    handle = scene.add("toy_kinds", side=side, name="toy")
    return {
        role: node.long_name
        for (role, _index), node in scene.guide_nodes(handle.instance_id).items()
    }


# --------------------------------------------------------------- node type
def test_reference_guide_is_not_a_joint(scene):
    found = drawn(scene)
    assert cmds.nodeType(found["aim"]) == "transform"
    assert cmds.nodeType(found["root"]) == "joint"


def test_reference_guide_carries_a_locator_shape(scene):
    found = drawn(scene)
    shapes = cmds.listRelatives(found["aim"], shapes=True, type="locator") or []
    assert len(shapes) == 1
    assert cmds.getAttr(f"{shapes[0]}.localScaleX") == nodes.REFERENCE_SCALE


def test_reference_guide_still_hangs_under_its_anchor(scene):
    """No constraint, no reparenting: the bone is gone because it is a
    transform, and nothing else about its place in the scene changed."""
    found = drawn(scene)
    parent = cmds.listRelatives(found["aim"], parent=True, fullPath=True)[0]
    assert parent == found["root"]


def test_driven_guide_stays_a_joint(scene):
    """DRIVEN is subordinate, not absent: it keeps its bone so the chain reads."""
    found = drawn(scene)
    assert cmds.nodeType(found["rail"]) == "joint"


# ----------------------------------------------------------------- the look
def test_radius_comes_from_the_kind(scene):
    found = drawn(scene)
    assert cmds.getAttr(f"{found['root']}.radius") == nodes.KIND_RADIUS[GuideKind.ROOT]
    assert cmds.getAttr(f"{found['tip']}.radius") == nodes.KIND_RADIUS[GuideKind.JOINT]
    assert (
        cmds.getAttr(f"{found['rail']}.radius") == nodes.KIND_RADIUS[GuideKind.DRIVEN]
    )


def test_colour_comes_from_the_kind(scene):
    found = drawn(scene, side="L")
    assert tm.resolve(found["root"]).color == nodes.SIDE_COLORS["L"]
    assert tm.resolve(found["aim"]).color == nodes.MARKER_COLOR
    assert tm.resolve(found["rail"]).color == nodes.DRIVEN_COLORS["L"]


# --------------------------------------------------------------- the scans
def test_a_reference_guide_is_still_found_by_the_scans(scene):
    """The five filters widened from type="joint" to type="transform"."""
    handle = scene.add("toy_kinds", side="L", name="toy")
    assert ("aim", 0) in scene.guide_nodes(handle.instance_id)
    instances = scene.find_instances([handle.instance_id])
    assert any(pose.role == "aim" for pose in instances[0].guides)


def test_sync_captures_a_reference_guide_pose(scene):
    handle = scene.add("toy_kinds", side="L", name="toy")
    node = scene.guide_nodes(handle.instance_id)[("aim", 0)]
    cmds.xform(node.long_name, worldSpace=True, translation=(1.0, 2.0, 3.0))
    scene.sync()
    entry = scene.document.module(handle.instance_id)
    pose = next(item for item in entry.guides if item.role == "aim")
    assert tuple(round(value, 3) for value in pose.position) == (1.0, 2.0, 3.0)


def test_draw_rebuilds_a_deleted_reference_guide(scene):
    handle = scene.add("toy_kinds", side="L", name="toy")
    cmds.delete(scene.guide_nodes(handle.instance_id)[("aim", 0)].long_name)
    assert ("aim", 0) not in scene.guide_nodes(handle.instance_id)
    scene.draw()
    rebuilt = scene.guide_nodes(handle.instance_id)[("aim", 0)]
    assert cmds.nodeType(rebuilt.long_name) == "transform"
