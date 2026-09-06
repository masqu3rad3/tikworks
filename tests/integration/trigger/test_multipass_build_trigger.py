"""Several kinematics passes build one rig, and later passes reach earlier ones.

Explicit build scope means a rig can be split across passes with other actions
between them. A consumer built in a later pass has to attach to a producer that
is already built -- and whose guides may already be deleted -- so the builder
resolves it from the scene's output tags rather than from this pass's map.
"""

import pytest
from maya import cmds

from tik.trigger.session import Session


def _body_and_arm():
    """A base with an arm connected to it, in one unsaved session."""
    cmds.file(new=True, force=True)
    session = Session()
    scene = session.guides
    body = scene.add("base", side="C", name="body")
    arm = scene.add("arm", side="L", name="arm", parent=body)
    return session, body, arm


def _socket_drivers(pattern: str) -> list:
    """Incoming connections of every socket transform matching ``pattern``."""
    found = []
    for name in cmds.ls(pattern, long=True, type="transform") or []:
        found.extend(cmds.listConnections(name, source=True, destination=False) or [])
    return found


def test_second_pass_attaches_to_the_first_passs_output():
    """The whole point: a later pass finds an earlier pass's output."""
    session, body, arm = _body_and_arm()
    session.add(
        "kinematics", name="pass_one", modules=[body.instance_id], after_build="delete"
    )
    session.add(
        "kinematics", name="pass_two", modules=[arm.instance_id], after_build="delete"
    )
    session.build()

    assert cmds.objExists("rig_grp")
    built = cmds.ls("*arm*", long=True) or []
    assert any("|rig_grp|trigger_grp|" in name for name in built), built
    # the arm's socket is driven by something -- the body's output, built in
    # the pass before it and with its guides already deleted
    assert _socket_drivers("L_arm_*socket*"), cmds.ls("*socket*")


def test_one_pass_keeping_its_guides_survives_the_next_pass():
    """A pass must not clear or re-consume guides outside its own scope."""
    session, body, arm = _body_and_arm()
    session.add(
        "kinematics", name="pass_one", modules=[body.instance_id], after_build="keep"
    )
    session.add(
        "kinematics", name="pass_two", modules=[arm.instance_id], after_build="delete"
    )
    session.build()

    kept = cmds.ls("*body*guide*", long=True) or []
    assert kept, "pass one asked to keep its guides; pass two deleted them"


def test_a_single_pass_still_builds_the_whole_rig():
    """The ordinary case keeps working: one action naming both modules."""
    session, body, arm = _body_and_arm()
    session.add("kinematics", modules=[body.instance_id, arm.instance_id])
    session.build()
    assert cmds.objExists("rig_grp")
    assert _socket_drivers("L_arm_*socket*")


def test_duplicate_display_key_raises():
    """Two modules resolving to one key would silently overwrite by_key."""
    from tik.trigger.core.exceptions import SessionError

    cmds.file(new=True, force=True)
    session = Session()
    scene = session.guides
    one = scene.add("base", side="C", name="body")
    two = scene.add("base", side="C", name="body")
    # the scene hands out unique names, so force the collision the way a
    # referenced module colliding with a local one would
    session.document.guides.module(two.instance_id).name = "body"

    session.add("kinematics", modules=[one.instance_id, two.instance_id])
    # caught before the scene is touched at all; the Builder keeps its own
    # guard for anyone driving it directly
    with pytest.raises(SessionError, match="display key"):
        session.build()
