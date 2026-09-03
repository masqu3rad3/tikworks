"""Tests for the limb lock system."""

from maya import cmds

import tik.maya as tm
from tik.trigger.maya.rig import ModuleRig
from tik.trigger.systems.limb_lock import build_limb_lock


class _FakeRig:
    """Minimal ModuleRig stand-in: naming, the rig group, and the separator."""

    #: Borrowed rather than reimplemented: ``separator`` touches no ModuleRig
    #: state, and a copy here is exactly what lets a stub drift from the rig
    #: whose contract it stands in for.
    separator = ModuleRig.separator

    def __init__(self):
        self.root = tm.Transform.create(name="rig_grp")
        self.rig_root = self.root
        self.groups = type("Groups", (), {"rig": self.root, "socket": self.root})()

    def name(self, *tokens, suffix=None):
        parts = [part for part in tokens if part] + ([suffix] if suffix else [])
        return "_".join(["L", "arm", *parts]) if parts else "L_arm"


def _setup(distance=10.0):
    rig = _FakeRig()
    socket = tm.Transform.create(name="socket")
    chain_root = tm.Transform.create(name="shoulder")
    chain_root.translate = (2, 0, 0)
    driver = tm.Transform.create(name="ik_ctrl")
    driver.translate = (2 + distance, 0, 0)
    control = tm.Transform.create(name="ik_main")
    target = tm.Transform.create(name="collar_offset")
    return rig, socket, chain_root, driver, control, target


def test_attribute_order_and_defaults():
    rig, socket, chain_root, driver, control, target = _setup(distance=10.0)
    build_limb_lock(
        rig, socket=socket, chain_root=chain_root, driver=driver,
        control=control, target=target, follows=socket,
    )
    added = cmds.listAttr(control.long_name, userDefined=True)
    ordered = [name for name in added
               if name in ("limbLock", "currentLength", "lockLength")]
    assert ordered == ["limbLock", "currentLength", "lockLength"]
    assert abs(control["lockLength"].value - 10.0) < 1e-4
    assert abs(control["currentLength"].value - 10.0) < 1e-4


def test_current_length_is_locked_visible_and_live():
    rig, socket, chain_root, driver, control, target = _setup(distance=10.0)
    build_limb_lock(
        rig, socket=socket, chain_root=chain_root, driver=driver,
        control=control, target=target, follows=socket,
    )
    path = control["currentLength"].path
    assert cmds.getAttr(path, lock=True)
    # locked but still shown, so an animator can read and copy it
    assert cmds.getAttr(path, keyable=True) or cmds.getAttr(path, channelBox=True)
    driver.translate = (2 + 14.0, 0, 0)
    assert abs(control["currentLength"].value - 14.0) < 1e-3


def test_locking_at_the_current_pose_moves_nothing():
    """The workflow the attributes exist for: copy currentLength, then lock."""
    rig, socket, chain_root, driver, control, target = _setup(distance=10.0)
    build_limb_lock(
        rig, socket=socket, chain_root=chain_root, driver=driver,
        control=control, target=target, follows=socket,
    )
    driver.translate = (2 + 13.0, 3.0, 0)
    before = target.world_position
    control["lockLength"].value = control["currentLength"].value
    control["limbLock"].value = 1.0
    after = target.world_position
    assert (after - before).length() < 1e-3


def test_lock_holds_the_length():
    rig, socket, chain_root, driver, control, target = _setup(distance=10.0)
    lock = build_limb_lock(
        rig, socket=socket, chain_root=chain_root, driver=driver,
        control=control, target=target, follows=socket,
    )
    control["lockLength"].value = 10.0
    control["limbLock"].value = 1.0
    driver.translate = (40.0, 0, 0)
    assert abs(lock.push.distance_to(driver) - 10.0) < 1e-3


def test_no_cycle():
    """The regression guard: the measurement must never see its own push."""
    rig, socket, chain_root, driver, control, target = _setup()
    build_limb_lock(
        rig, socket=socket, chain_root=chain_root, driver=driver,
        control=control, target=target, follows=socket,
    )
    control["limbLock"].value = 1.0
    target.world_position  # force an evaluation
    assert (cmds.cycleCheck(all=True, list=True) or []) == []


# ------------------------------------------------------------------ the arm
def test_arm_declares_the_lock_fields():
    from tik.trigger.modules.arm.arm import Arm

    assert Arm.limb_lock.default is True
    assert Arm.lock_from.default == "shoulder"
    assert set(Arm.lock_from.choices) == {"shoulder", "collar"}
    assert not hasattr(Arm, "lock_target")


def _armed(**settings):
    import tik.trigger as trigger
    from tik.trigger.guides import GuideScene
    from tik.trigger.maya import Builder

    # a fresh file, so a test may build more than one variant
    cmds.file(new=True, force=True)
    trigger.load_plugins()
    guides = GuideScene()
    guides.clear()
    body = guides.add("base", name="body")
    arm = guides.add("arm", side="L", name="arm", parent=body, **settings)
    report = Builder().build(document=guides.document, rig_name="hero", afterlife="keep")
    return report.rigs[arm.instance_id]


def test_arm_builds_with_the_lock_and_no_cycle():
    ctx = _armed(limb_lock=True)
    control = ctx.controller_by_role("ik").transform
    for attr in ("limbLock", "currentLength", "lockLength"):
        assert cmds.objExists(f"{control.long_name}.{attr}")
    assert control["lockLength"].value > 0.0
    control["limbLock"].value = 1.0
    ctx.outputs["hand"].world_position  # force evaluation
    assert (cmds.cycleCheck(all=True, list=True) or []) == []


def test_arm_lock_off_adds_nothing():
    ctx = _armed(limb_lock=False)
    control = ctx.controller_by_role("ik").transform
    assert not cmds.objExists(f"{control.long_name}.limbLock")


def test_arm_lock_actually_moves_the_shoulder():
    """The test that was missing: engaging the lock must DO something.

    With the hand pulled away and the lock on, the shoulder is dragged out so
    the shoulder-to-hand distance stays at lockLength. Must hold with
    auto_collar at its default (on), which is what made this fail before.
    """
    ctx = _armed(limb_lock=True)
    control = ctx.controller_by_role("ik").transform
    shoulder = ctx.outputs["upperarm"]

    control.world_position = (30, 15, 0)
    before = shoulder.world_position
    control["limbLock"].value = 1.0
    after = shoulder.world_position
    assert (after - before).length() > 1.0, "the lock moved nothing"


def test_arm_lock_holds_shoulder_to_hand_at_lock_length():
    ctx = _armed(limb_lock=True)
    control = ctx.controller_by_role("ik").transform
    shoulder = ctx.outputs["upperarm"]
    hand = ctx.controller_by_role("ik_tweak").transform

    rest = control["lockLength"].value
    control["limbLock"].value = 1.0
    for target in ((30, 15, 0), (25, -8, 6), (18, 2, -11)):
        control.world_position = target
        held = (hand.world_position - shoulder.world_position).length()
        assert abs(held - rest) < 1e-2, f"at {target}: {held} != {rest}"


def test_arm_lock_is_inert_when_off():
    """limbLock = 0 must change nothing, at any hand pose."""
    ctx = _armed(limb_lock=True)
    control = ctx.controller_by_role("ik").transform
    shoulder = ctx.outputs["upperarm"]

    control["limbLock"].value = 0.0
    rest = shoulder.world_position
    for target in ((30, 15, 0), (25, -8, 6), (-4, 2, 9)):
        control.world_position = target
        assert (shoulder.world_position - rest).length() < 1e-3, (
            f"the shoulder drifted at {target} with the lock off"
        )


def test_shoulder_mode_moves_the_shoulder_but_not_the_collar():
    """The default: a shoulder-to-wrist lock leaves the clavicle on the chest."""
    ctx = _armed(limb_lock=True, lock_from="shoulder")
    control = ctx.controller_by_role("ik").transform
    collar = ctx.outputs["collar"]
    shoulder = ctx.outputs["upperarm"]

    control.world_position = (30, 15, 0)
    collar_before, shoulder_before = collar.world_position, shoulder.world_position
    control["limbLock"].value = 1.0

    assert (shoulder.world_position - shoulder_before).length() > 1.0
    assert (collar.world_position - collar_before).length() < 1e-3, (
        "the collar should not move in shoulder mode"
    )


def test_collar_mode_carries_the_collar_along():
    ctx = _armed(limb_lock=True, lock_from="collar")
    control = ctx.controller_by_role("ik").transform
    collar = ctx.outputs["collar"]
    shoulder = ctx.outputs["upperarm"]

    control.world_position = (30, 15, 0)
    collar_before, shoulder_before = collar.world_position, shoulder.world_position
    control["limbLock"].value = 1.0

    assert (shoulder.world_position - shoulder_before).length() > 1.0
    assert (collar.world_position - collar_before).length() > 1.0, (
        "the collar should travel with the push in collar mode"
    )


def test_both_modes_hold_the_shoulder_to_hand_length():
    for mode in ("shoulder", "collar"):
        ctx = _armed(limb_lock=True, lock_from=mode)
        control = ctx.controller_by_role("ik").transform
        shoulder = ctx.outputs["upperarm"]
        hand = ctx.controller_by_role("ik_tweak").transform
        rest = control["lockLength"].value
        control["limbLock"].value = 1.0
        for pose in ((30, 15, 0), (24, -9, 7)):
            control.world_position = pose
            held = (hand.world_position - shoulder.world_position).length()
            assert abs(held - rest) < 1e-2, f"{mode} at {pose}: {held} != {rest}"


def test_both_modes_are_cycle_free():
    for mode in ("shoulder", "collar"):
        ctx = _armed(limb_lock=True, lock_from=mode)
        control = ctx.controller_by_role("ik").transform
        control["limbLock"].value = 1.0
        control.world_position = (28, 9, 4)
        for node in ctx.outputs.values():
            node.world_position
        assert (cmds.cycleCheck(all=True, list=True) or []) == [], mode
