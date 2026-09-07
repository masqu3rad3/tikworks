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
