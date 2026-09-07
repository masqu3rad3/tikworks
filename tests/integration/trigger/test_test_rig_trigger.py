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
    assert cmds.objExists("|trigger_test:rig_grp|trigger_test:trigger_grp")
    assert cmds.objExists("|trigger_test:rig_grp|trigger_test:geo_grp")
    assert cmds.objExists(
        "|trigger_test:rig_grp|trigger_test:trigger_grp"
        "|trigger_test:preferences_ctrl"
    )
    assert cmds.objExists(
        "|trigger_test:rig_grp|trigger_test:trigger_grp"
        "|trigger_test:visibilities_ctrl"
    )
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
    assert len(cmds.ls(TEST_ROOT, recursive=True) or []) == 1


def test_the_two_rigs_coexist():
    cmds.file(new=True, force=True)
    real = ensure_rig()
    test = ensure_test_rig()
    assert real.root.long_name == "|rig_grp"
    assert test.root.long_name == f"|{TEST_ROOT}"
    assert real.is_test is False
    assert cmds.objExists("|rig_grp|trigger_grp|preferences_ctrl")
    assert cmds.objExists(
        "|trigger_test:rig_grp|trigger_test:trigger_grp"
        "|trigger_test:preferences_ctrl"
    )


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
    """A scaffold and one module container, both in the test namespace."""
    scaffold = ensure_test_rig()
    with sandbox.namespace(sandbox.TEST_NAMESPACE):
        container = sandbox.module_container(instance_id, key, scaffold.trigger)
    return scaffold, container


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
    with sandbox.namespace(sandbox.TEST_NAMESPACE), sandbox.current(container):
        group = tm.Transform.create(name="L_arm_grp", parent=container.long_name)
        node = cmds.createNode("multMatrix", name="L_arm_mmx")
    members = cmds.container(container.long_name, q=True, nodeList=True) or []
    assert group.name in members
    assert node in members


def test_current_restores_the_previous_container():
    """Nesting does not restore by itself; the context manager must."""
    cmds.file(new=True, force=True)
    scaffold, one = _module_container("id_a", "a")
    with sandbox.namespace(sandbox.TEST_NAMESPACE):
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
    with sandbox.namespace(sandbox.TEST_NAMESPACE):
        body = sandbox.module_container("id_body", "body", scaffold.trigger)
        with sandbox.current(arm):
            tm.Transform.create(name="L_arm_grp", parent=arm.long_name)
            cmds.createNode("multMatrix", name="L_arm_mmx")
        with sandbox.current(body):
            tm.Transform.create(name="body_grp", parent=body.long_name)
            cmds.createNode("multMatrix", name="body_mmx")

    removed = sandbox.teardown(["id_arm"], scaffold)

    assert removed == ["id_arm"]
    assert not cmds.objExists("trigger_test:L_arm_grp")
    assert not cmds.objExists("trigger_test:L_arm_mmx")  # the DG node goes too
    assert cmds.objExists("trigger_test:body_grp")
    assert cmds.objExists("trigger_test:body_mmx")
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
    with sandbox.namespace(sandbox.TEST_NAMESPACE), sandbox.current(arm):
        cmds.createNode("multMatrix", name="L_arm_mmx")
    ensure_rig()  # the real rig must survive

    assert sandbox.clear() is True

    assert not cmds.objExists(sandbox.TEST_ROOT)
    assert not cmds.objExists("trigger_test:L_arm_mmx")
    assert cmds.objExists("rig_grp")
    assert sandbox.clear() is False  # nothing left to clear


from tik.trigger.maya.build import Builder  # noqa: E402
from tik.trigger.session import Session  # noqa: E402


def _body_and_arm():
    """A base with an arm connected to it, drawn in a fresh scene."""
    cmds.file(new=True, force=True)
    session = Session()
    scene = session.guides
    body = scene.add("base", side="C", name="body")
    arm = scene.add("arm", side="L", name="arm", parent=body)
    scene.draw(None)
    return session, body, arm


def _build_real(session):
    """Build the real rig, the way the kinematics action does."""
    return Builder().build(
        scope="scene", document=session.guides.document, afterlife="keep"
    )


def test_a_test_build_leaves_the_real_rig_absent():
    session, _body, _arm = _body_and_arm()
    session.guides.test_build()
    assert cmds.objExists(sandbox.TEST_ROOT)
    assert not cmds.objExists("rig_grp")


def test_a_test_build_does_not_touch_a_built_real_rig():
    session, _body, _arm = _body_and_arm()
    _build_real(session)
    before = sorted(cmds.ls("|rig_grp", dag=True, long=True) or [])
    enums = sorted(cmds.listAttr("visibilities_ctrl", userDefined=True) or [])

    session.guides.test_build()

    assert sorted(cmds.ls("|rig_grp", dag=True, long=True) or []) == before
    assert sorted(cmds.listAttr("visibilities_ctrl", userDefined=True) or []) == enums


def test_building_the_same_selection_three_times_leaves_one_copy():
    """The bug this whole feature exists to kill."""
    session, _body, arm = _body_and_arm()
    counts = []
    for _ in range(3):
        session.guides.test_build(arm)
        counts.append(len(cmds.ls("trigger_test:L_arm_grp", long=True) or []))
    assert counts == [1, 1, 1]


def test_build_all_wipes_the_test_rig_first():
    session, _body, arm = _body_and_arm()
    session.guides.test_build()
    container = sandbox.find_module_container(arm.instance_id)
    with sandbox.namespace(sandbox.TEST_NAMESPACE), sandbox.current(container):
        cmds.createNode("transform", name="stray_marker")
    session.guides.test_build()
    assert not cmds.objExists("trigger_test:stray_marker")


def test_a_scoped_build_pulls_in_an_unbuilt_producer():
    session, body, arm = _body_and_arm()
    report = session.guides.test_build(arm)
    assert body.instance_id in report.built
    assert arm.instance_id in report.built


def test_a_scoped_build_leaves_a_sibling_alone():
    session, body, arm = _body_and_arm()
    session.guides.test_build()
    marker = sandbox.find_module_container(body.instance_id).long_name

    session.guides.test_build(arm)

    assert cmds.objExists(marker)
    assert sandbox.find_module_container(arm.instance_id) is not None


def test_a_scoped_build_rebuilds_a_built_consumer():
    """The arm's attach must not be left pointing at deleted nodes."""
    session, body, _arm = _body_and_arm()
    session.guides.test_build()
    session.guides.test_build(body)

    sockets = cmds.ls("trigger_test:L_arm_*socket*", long=True, type="transform") or []
    assert sockets
    drivers = cmds.listConnections(sockets[0], source=True, destination=False) or []
    assert drivers, "the rebuilt arm lost its attach"


def test_a_test_build_keeps_the_guides():
    session, _body, _arm = _body_and_arm()
    session.guides.test_build()
    assert cmds.objExists("trigger_guides_grp")


def test_a_modules_dg_nodes_are_in_its_container():
    session, _body, arm = _body_and_arm()
    session.guides.test_build()
    container = sandbox.find_module_container(arm.instance_id)
    members = cmds.container(container.long_name, q=True, nodeList=True) or []
    assert any(cmds.objectType(name) == "multMatrix" for name in members), members
