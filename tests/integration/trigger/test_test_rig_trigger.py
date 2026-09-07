"""The throwaway rig the Guide Designer builds into.

Spec: docs/superpowers/specs/2026-09-07-test-rig-sandbox-design.md
"""

from maya import cmds

from tik.trigger.maya.scaffold import (
    TEST_ROOT,
    ensure_rig,
    ensure_test_rig,
    find_test_rig,
)


def test_ensure_test_rig_creates_its_own_root():
    cmds.file(new=True, force=True)
    scaffold = ensure_test_rig()

    assert scaffold.is_test is True
    assert scaffold.root.long_name == f"|{TEST_ROOT}"
    assert cmds.objExists("|test_rig_grp|test_trigger_grp")
    assert cmds.objExists("|test_rig_grp|test_geo_grp")
    assert cmds.objExists("|test_rig_grp|test_trigger_grp|test_preferences_ctrl")
    assert cmds.objExists("|test_rig_grp|test_trigger_grp|test_visibilities_ctrl")
    # the real rig is not created as a side effect
    assert not cmds.objExists("|rig_grp")


def test_the_test_root_is_a_dag_container():
    """Membership is what makes teardown complete."""
    cmds.file(new=True, force=True)
    ensure_test_rig()
    assert cmds.nodeType(TEST_ROOT) == "dagContainer"


def test_ensure_test_rig_is_idempotent():
    cmds.file(new=True, force=True)
    first = ensure_test_rig()
    second = ensure_test_rig()
    assert first.root.long_name == second.root.long_name
    assert len(cmds.ls("test_rig_grp") or []) == 1


def test_the_two_rigs_coexist():
    cmds.file(new=True, force=True)
    real = ensure_rig()
    test = ensure_test_rig()
    assert real.root.long_name == "|rig_grp"
    assert test.root.long_name == "|test_rig_grp"
    assert real.is_test is False
    assert cmds.objExists("|rig_grp|trigger_grp|preferences_ctrl")
    assert cmds.objExists("|test_rig_grp|test_trigger_grp|test_preferences_ctrl")


def test_find_test_rig_creates_nothing():
    cmds.file(new=True, force=True)
    assert find_test_rig() is None
    assert not cmds.objExists(TEST_ROOT)
    ensure_test_rig()
    assert find_test_rig() is not None


def test_ensure_rig_is_unchanged():
    """The real scaffold keeps its exact names and shape."""
    cmds.file(new=True, force=True)
    scaffold = ensure_rig()
    assert scaffold.root.long_name == "|rig_grp"
    assert scaffold.is_test is False
    assert cmds.nodeType("rig_grp") == "transform"
    assert cmds.objExists("|rig_grp|trigger_grp|visibilities_ctrl")


import pytest  # noqa: E402 - grouped with the sandbox tests it serves

import tik.maya as tm  # noqa: E402
from tik.trigger.maya import sandbox  # noqa: E402


def _module_container(instance_id="id_arm", key="L_arm"):
    scaffold = ensure_test_rig()
    return scaffold, sandbox.module_container(instance_id, key, scaffold.trigger)


def test_a_module_container_is_tagged_and_parented():
    cmds.file(new=True, force=True)
    scaffold, container = _module_container()
    assert cmds.nodeType(container.long_name) == "dagContainer"
    assert container.long_name.startswith(scaffold.trigger.long_name + "|")
    assert sandbox.find_module_container("id_arm").long_name == container.long_name
    assert sandbox.built_instance_ids() == {"id_arm"}


def test_current_captures_dag_and_dg_nodes():
    """The whole point: the utility nodes go in too."""
    cmds.file(new=True, force=True)
    _scaffold, container = _module_container()
    with sandbox.current(container):
        group = tm.Transform.create(name="L_arm_grp", parent=container.long_name)
        node = cmds.createNode("multMatrix", name="L_arm_mmx")
    members = cmds.container(container.long_name, q=True, nodeList=True) or []
    assert group.name in members
    assert node in members


def test_current_restores_the_previous_container():
    """Nesting does not restore by itself; the context manager must."""
    cmds.file(new=True, force=True)
    scaffold, one = _module_container("id_a", "a")
    two = sandbox.module_container("id_b", "b", scaffold.trigger)
    with sandbox.current(one):
        with sandbox.current(two):
            assert cmds.container(q=True, current=True) == two.name
        assert cmds.container(q=True, current=True) == one.name
    assert (cmds.container(q=True, current=True) or "") == ""


def test_current_clears_when_the_body_raises():
    cmds.file(new=True, force=True)
    _scaffold, container = _module_container()
    with pytest.raises(RuntimeError):
        with sandbox.current(container):
            raise RuntimeError("boom")
    assert (cmds.container(q=True, current=True) or "") == ""


def test_teardown_removes_a_module_and_nothing_else():
    cmds.file(new=True, force=True)
    scaffold, arm = _module_container("id_arm", "L_arm")
    body = sandbox.module_container("id_body", "body", scaffold.trigger)
    with sandbox.current(arm):
        tm.Transform.create(name="L_arm_grp", parent=arm.long_name)
        cmds.createNode("multMatrix", name="L_arm_mmx")
    with sandbox.current(body):
        tm.Transform.create(name="body_grp", parent=body.long_name)
        cmds.createNode("multMatrix", name="body_mmx")

    removed = sandbox.teardown(["id_arm"], scaffold)

    assert removed == ["id_arm"]
    assert not cmds.objExists("L_arm_grp")
    assert not cmds.objExists("L_arm_mmx")  # the DG node goes too
    assert cmds.objExists("body_grp")
    assert cmds.objExists("body_mmx")
    assert sandbox.built_instance_ids() == {"id_body"}


def test_teardown_drops_the_modules_tier_enum():
    cmds.file(new=True, force=True)
    scaffold, _arm = _module_container("id_arm", "L_arm")
    enum = scaffold.visibilities.transform["L_arm"]
    enum.create("enum", items=["primary", "all"], default=1, keyable=False)
    assert enum.exists()

    sandbox.teardown(["id_arm"], scaffold)

    assert not scaffold.visibilities.transform["L_arm"].exists()


def test_teardown_of_an_unbuilt_module_is_a_no_op():
    cmds.file(new=True, force=True)
    scaffold = ensure_test_rig()
    assert sandbox.teardown(["id_ghost"], scaffold) == []


def test_clear_removes_the_whole_test_rig():
    cmds.file(new=True, force=True)
    _scaffold, arm = _module_container()
    with sandbox.current(arm):
        cmds.createNode("multMatrix", name="L_arm_mmx")
    ensure_rig()  # the real rig must survive

    assert sandbox.clear() is True

    assert not cmds.objExists(sandbox.TEST_ROOT)
    assert not cmds.objExists("L_arm_mmx")
    assert cmds.objExists("rig_grp")
    assert sandbox.clear() is False  # nothing left to clear
