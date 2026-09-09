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


def test_the_test_root_is_a_plain_transform():
    """A dagContainer root would take over the Channel Box for the rig."""
    cmds.file(new=True, force=True)
    ensure_test_rig()
    assert cmds.nodeType(TEST_ROOT) == "transform"


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


def _record(instance_id="id_arm", key="L_arm"):
    """A scaffold and one module record set, both in the test namespace."""
    scaffold = ensure_test_rig()
    with sandbox.namespace(sandbox.TEST_NAMESPACE):
        record = sandbox.module_record(instance_id, key)
    return scaffold, record


def test_a_module_record_is_a_tagged_set():
    cmds.file(new=True, force=True)
    _scaffold, record = _record()
    assert cmds.nodeType(record.long_name) == "objectSet"
    assert sandbox.find_module_record("id_arm").long_name == record.long_name
    assert sandbox.built_instance_ids() == {"id_arm"}


def test_capturing_records_dag_and_dg_nodes():
    """The whole point: the utility nodes go in too."""
    cmds.file(new=True, force=True)
    scaffold = ensure_test_rig()
    with sandbox.namespace(sandbox.TEST_NAMESPACE):
        with sandbox.capturing("id_arm", "L_arm") as record:
            group = tm.Transform.create(
                name="L_arm_grp", parent=scaffold.trigger.long_name
            )
            cmds.createNode("multMatrix", name="L_arm_mmx")
    held = sandbox.members(record)
    assert cmds.ls(group.long_name, long=True)[0] in held
    assert ":trigger_test:L_arm_mmx" in held


def test_capturing_makes_no_container():
    """A container would take over the Channel Box for everything inside it."""
    cmds.file(new=True, force=True)
    ensure_test_rig()
    with sandbox.namespace(sandbox.TEST_NAMESPACE):
        with sandbox.capturing("id_arm", "L_arm"):
            cmds.createNode("multMatrix", name="L_arm_mmx")
    assert cmds.ls(type="dagContainer") == []
    assert cmds.container(q=True, findContainer=[":trigger_test:L_arm_mmx"]) is None


def test_capturing_leaves_an_unconnected_node_alone():
    """A container drops one on the way out; the census must not."""
    cmds.file(new=True, force=True)
    ensure_test_rig()
    with sandbox.namespace(sandbox.TEST_NAMESPACE):
        with sandbox.capturing("id_arm", "L_arm") as record:
            cmds.createNode("multMatrix", name="L_arm_lone")
    assert cmds.objExists(":trigger_test:L_arm_lone")
    assert ":trigger_test:L_arm_lone" in sandbox.members(record)


def test_capturing_twice_adds_to_the_same_record():
    """A module is captured once for its build and again for its spaces."""
    cmds.file(new=True, force=True)
    ensure_test_rig()
    with sandbox.namespace(sandbox.TEST_NAMESPACE):
        with sandbox.capturing("id_arm", "L_arm"):
            cmds.createNode("multMatrix", name="L_arm_one")
        with sandbox.capturing("id_arm", "L_arm") as record:
            cmds.createNode("multMatrix", name="L_arm_two")
    held = sandbox.members(record)
    assert len(cmds.ls(f":{sandbox.TEST_NAMESPACE}:*", type="objectSet")) == 1
    assert ":trigger_test:L_arm_one" in held
    assert ":trigger_test:L_arm_two" in held


def test_capturing_records_what_a_failed_build_made():
    """A half-built module must still be tearable-down."""
    cmds.file(new=True, force=True)
    ensure_test_rig()
    with pytest.raises(RuntimeError):
        with sandbox.namespace(sandbox.TEST_NAMESPACE):
            with sandbox.capturing("id_arm", "L_arm"):
                cmds.createNode("multMatrix", name="L_arm_half")
                raise RuntimeError("boom")
    record = sandbox.find_module_record("id_arm")
    assert ":trigger_test:L_arm_half" in sandbox.members(record)


def test_teardown_removes_a_module_and_nothing_else():
    cmds.file(new=True, force=True)
    scaffold = ensure_test_rig()
    with sandbox.namespace(sandbox.TEST_NAMESPACE):
        with sandbox.capturing("id_arm", "L_arm"):
            tm.Transform.create(name="L_arm_grp", parent=scaffold.trigger.long_name)
            cmds.createNode("multMatrix", name="L_arm_mmx")
        with sandbox.capturing("id_body", "body"):
            tm.Transform.create(name="body_grp", parent=scaffold.trigger.long_name)
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
    scaffold, _arm = _record("id_arm", "L_arm")
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
    ensure_test_rig()
    with sandbox.namespace(sandbox.TEST_NAMESPACE):
        with sandbox.capturing("id_arm", "L_arm"):
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
    with sandbox.namespace(sandbox.TEST_NAMESPACE):
        with sandbox.capturing(arm.instance_id, "L_arm"):
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
    marker = sandbox.find_module_record(body.instance_id).long_name

    session.guides.test_build(arm)

    assert cmds.objExists(marker)
    assert sandbox.find_module_record(arm.instance_id) is not None


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


def test_a_modules_dg_nodes_are_in_its_record():
    session, _body, arm = _body_and_arm()
    session.guides.test_build()
    record = sandbox.find_module_record(arm.instance_id)
    held = sandbox.members(record)
    assert any(cmds.objectType(name) == "multMatrix" for name in held), held


def test_a_test_built_controller_belongs_to_no_container():
    """The Channel Box shows a container in place of any node inside one.

    A controller left inside a container therefore shows the container's
    transform channels instead of the rig's attributes -- the attributes are
    built, they are simply never displayed. Nothing the test build leaves
    behind may be a container member.
    """
    session, _body, _arm = _body_and_arm()
    session.guides.test_build()

    for node in (
        "trigger_test:L_arm_ik_ctrl",
        "trigger_test:C_body_root_ctrl",
        "trigger_test:preferences_ctrl",
        "trigger_test:visibilities_ctrl",
    ):
        assert cmds.objExists(node), node
        assert cmds.container(q=True, findContainer=[node]) is None, node


def test_a_test_build_leaves_no_containers_at_all():
    session, _body, _arm = _body_and_arm()
    session.guides.test_build()
    assert cmds.ls(type="dagContainer") == []
    assert cmds.ls(type="container") == []


def _two_arms():
    """A base with an arm on each side, drawn in a fresh scene."""
    cmds.file(new=True, force=True)
    session = Session()
    scene = session.guides
    body = scene.add("base", side="C", name="body")
    left = scene.add("arm", side="L", name="arm", parent=body)
    right = scene.add("arm", side="R", name="arm", parent=body)
    scene.draw(None)
    return session, left, right


def test_the_ik_solvers_are_recorded_against_no_module():
    """Maya makes one solver on demand and every ikHandle shares it.

    The census sees it appear during whichever module happened to need IK
    first. Recording it there would make that module's teardown delete the
    solver every other module's ikHandle is pointing at.
    """
    session, _left, _right = _two_arms()
    session.guides.test_build()

    for name in cmds.ls(f":{sandbox.TEST_NAMESPACE}:*", type="objectSet"):
        held = cmds.sets(name, query=True) or []
        assert not cmds.ls(held, type="ikSolver"), name


def test_rebuilding_one_arm_leaves_the_others_ik_alone():
    session, _left, right = _two_arms()
    session.guides.test_build()

    session.guides.test_build(right)

    assert cmds.ls("trigger_test:L_arm_ikHandle", long=True), "the left arm lost its IK"
    assert cmds.ls("trigger_test:R_arm_ikHandle", long=True)
