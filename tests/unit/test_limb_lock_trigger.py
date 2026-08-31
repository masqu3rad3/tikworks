"""Tests for the limb lock system."""

from maya import cmds

import tik.maya as tm
from tik.trigger.systems.limb_lock import build_limb_lock


class _FakeRig:
    """Minimal ModuleRig stand-in: naming plus the rig group."""

    def __init__(self):
        self.root = tm.Transform.create(name="rig_grp")
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
        control=control, target=target,
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
        control=control, target=target,
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
        control=control, target=target,
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
        control=control, target=target,
    )
    control["lockLength"].value = 10.0
    control["limbLock"].value = 1.0
    driver.translate = (40.0, 0, 0)
    assert abs(lock.push.distance_to(driver) - 10.0) < 1e-3


def test_output_mode_pushes_nothing():
    rig, socket, chain_root, driver, control, target = _setup()
    lock = build_limb_lock(
        rig, socket=socket, chain_root=chain_root, driver=driver,
        control=control, target=None,
    )
    assert lock.blend is None
    assert lock.push is not None
    assert not cmds.listConnections(
        target.long_name + ".translate", source=True, destination=False
    )


def test_no_cycle():
    """The regression guard: the measurement must never see its own push."""
    rig, socket, chain_root, driver, control, target = _setup()
    build_limb_lock(
        rig, socket=socket, chain_root=chain_root, driver=driver,
        control=control, target=target,
    )
    control["limbLock"].value = 1.0
    target.world_position  # force an evaluation
    assert (cmds.cycleCheck(all=True, list=True) or []) == []
