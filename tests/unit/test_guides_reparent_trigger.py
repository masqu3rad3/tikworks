"""Reparenting guides through the scene handler (drag-parenting in the Designer)."""

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.core.exceptions import GuideError
from tik.trigger.guides import GuideScene


def test_reparent_updates_the_parent_ref_and_the_dag_follows_on_draw():
    """The joint hierarchy is a *rendering* of the connection, so reparenting
    writes the document and the DAG catches up at the next Draw -- not before."""
    trigger.load_plugins()
    guides = GuideScene()
    body = guides.add("base", name="body")
    tail = guides.add("fkchain", name="tail")
    assert tail.parent is None
    guides.reparent(tail, body)
    assert tail.parent.instance_id == body.instance_id
    # the scene has not moved yet, and says so
    assert (
        cmds.listRelatives(tail.root.long_name, parent=True)[0] == "trigger_guides_grp"
    )
    assert tail.instance_id in guides.diff().stale
    guides.draw([tail.instance_id])
    assert cmds.listRelatives(tail.root.long_name, parent=True)[0] == body.root.name
    guides.reparent(tail, None)
    assert tail.parent is None
    guides.draw([tail.instance_id])
    assert (
        cmds.listRelatives(tail.root.long_name, parent=True)[0] == "trigger_guides_grp"
    )
    with pytest.raises(GuideError):
        guides.reparent(tail, tail)
    guides.reparent(tail, body)
    with pytest.raises(GuideError):
        guides.reparent(body, tail)  # would create a cycle
