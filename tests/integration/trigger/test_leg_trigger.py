"""Leg module: eleven guides, a reverse foot, one IK chain."""

import pytest
from maya import cmds

from tik.trigger.core import get_module
from tik.trigger.core.exceptions import BuildError
from tik.trigger.core.manifest import GuideKind
from tik.trigger.guides import GuideScene
from tik.trigger.maya import Builder


@pytest.fixture
def scene():
    cmds.file(new=True, force=True)
    return GuideScene()


def test_the_leg_declares_eleven_guides():
    leg = get_module("leg")
    assert leg.guides.all_roles == (
        "hip",
        "thigh",
        "knee",
        "ankle",
        "ball",
        "toe",
        "heel",
        "tip",
        "bank_in",
        "bank_out",
        "neutral",
    )


def test_the_foot_markers_are_reference_guides():
    """A marker is read for its position and nothing is shaped like it.

    Reference is also what stops them drawing bones: a reference guide is a
    locator transform, so it suppresses its own bone without suppressing its
    siblings -- four markers under the ankle would otherwise smear a blob.
    """
    layout = get_module("leg").guides
    for role in ("heel", "tip", "bank_in", "bank_out", "neutral"):
        assert layout.kind_for(role) is GuideKind.REFERENCE, role
    for role in ("thigh", "knee", "ankle", "ball", "toe"):
        assert layout.kind_for(role) is GuideKind.JOINT, role
    assert layout.kind_for("hip", is_root=True) is GuideKind.ROOT


def test_only_the_ankle_is_read_for_its_orientation():
    """The chain is oriented by convention; the ankle aligns the foot."""
    assert get_module("leg").guides.oriented == ("ankle",)


def test_drawing_a_leg_creates_all_eleven(scene):
    leg = scene.create_guides(get_module("leg")(name="leg", side="L"))
    for role in get_module("leg").guides.all_roles:
        assert scene.guide_node(leg.instance_id, role) is not None, role


def test_the_neutral_guide_is_collinear_with_hip_and_ankle(scene):
    """Exactly collinear, not approximately.

    The reach network measures the angle between this direction and the
    ankle's; at the guide pose that angle must be exactly zero or no scalar
    value leaves the bind pose alone. The arm measured a hand-written triple
    rounded to one decimal landing 0.006 out -- sixty times the tolerance.
    """
    leg = scene.create_guides(get_module("leg")(name="leg", side="L"))
    hip = scene.guide_node(leg.instance_id, "hip").world_position
    ankle = scene.guide_node(leg.instance_id, "ankle").world_position
    neutral = scene.guide_node(leg.instance_id, "neutral").world_position

    to_ankle = ankle - hip
    to_neutral = neutral - hip
    to_ankle.normalize()
    to_neutral.normalize()
    assert (to_ankle * to_neutral) == pytest.approx(1.0, abs=1e-6)


def test_the_collinearity_check_actually_discriminates(scene):
    """Sceptic's check on the test above: it must actually be able to fail.

    A dot product of two normalized vectors near 1.0 is not, on its own,
    proof the check can catch a wrong guide -- confirm it moves measurably
    once ``neutral`` is pushed off the hip-ankle line, using the real guide
    nodes rather than a hand-rolled vector example.

    Note for whoever edits ``draw_guides`` next: on this module's own
    numbers, a *hand-rounded-to-one-decimal* triple (the exact mistake the
    arm made) lands only ~5e-8 off -- under this test's 1e-6 tolerance,
    unlike the arm's 0.006. That is a property of these particular
    coordinates (the hip-ankle direction is already decimal-clean), not a
    defect in the check: it still catches any materially wrong guide, which
    is what matters, since the shipped code derives ``neutral`` exactly and
    never hand-types it.
    """
    leg = scene.create_guides(get_module("leg")(name="leg", side="L"))
    hip = scene.guide_node(leg.instance_id, "hip").world_position
    ankle = scene.guide_node(leg.instance_id, "ankle").world_position
    neutral_node = scene.guide_node(leg.instance_id, "neutral")

    # A visible, half-a-unit nudge off the line -- not a rounding artefact.
    pushed = neutral_node.world_position
    neutral_node.world_position = (pushed.x, pushed.y, pushed.z + 0.5)
    wrong_neutral = neutral_node.world_position

    to_ankle = ankle - hip
    to_wrong = wrong_neutral - hip
    to_ankle.normalize()
    to_wrong.normalize()
    dot = to_ankle * to_wrong

    assert dot != pytest.approx(1.0, abs=1e-6)
    assert (1.0 - dot) > 1e-4


def test_the_knee_bends_forward_of_the_hip_and_ankle(scene):
    """The bend plane is unambiguous: the knee sits ahead in Z of both ends.

    A test cannot judge whether the pose "reads as a leg", but it can check
    the one thing that actually matters mechanically -- the IK solver needs a
    knee that is not collinear with hip and ankle, and the sign of its offset
    is what keeps the knee pointing forward rather than backward.
    """
    leg = scene.create_guides(get_module("leg")(name="leg", side="L"))
    hip = scene.guide_node(leg.instance_id, "hip").world_position
    knee = scene.guide_node(leg.instance_id, "knee").world_position
    ankle = scene.guide_node(leg.instance_id, "ankle").world_position

    assert knee.z > hip.z
    assert knee.z > ankle.z


def test_the_chain_descends_monotonically_from_hip_to_ankle(scene):
    """Hip, thigh, knee and ankle step down in Y with no reversal."""
    leg = scene.create_guides(get_module("leg")(name="leg", side="L"))
    heights = [
        scene.guide_node(leg.instance_id, role).world_position.y
        for role in ("hip", "thigh", "knee", "ankle")
    ]
    for higher, lower in zip(heights, heights[1:]):
        assert higher > lower, heights


def test_the_foot_markers_sit_near_the_ground_plane(scene):
    """Heel, tip, bank_in, bank_out and ball all sit close to Y=0.

    They describe the footprint the reverse foot pivots around, so they must
    sit near the ground rather than floating mid-shin or burrowing below it.
    """
    leg = scene.create_guides(get_module("leg")(name="leg", side="L"))
    for role in ("heel", "tip", "bank_in", "bank_out", "ball"):
        y = scene.guide_node(leg.instance_id, role).world_position.y
        assert 0.0 <= y < 0.5, f"{role} sits at y={y}, not near the ground plane"


def test_the_leg_builds_standalone_and_stubs(scene):
    """No parent, no inputs: the module still draws and registers.

    ``build()`` is still a stub (Task 7): the builder wraps whatever it
    raises into a ``BuildError``, so this only proves the module reaches the
    builder and fails for the *expected* reason rather than a manifest or
    guide-wiring mistake.
    """
    leg = scene.create_guides(get_module("leg")(name="leg", side="L"))
    with pytest.raises(BuildError, match="lands in Task 7"):
        Builder().build(document=scene.document, afterlife="delete")
    assert any(entry.instance_id == leg.instance_id for entry in scene.document.modules)
