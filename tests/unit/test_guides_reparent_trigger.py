"""Maya backend: reparenting guides from the Guides handler (drag-parenting in the Designer)."""

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.core.exceptions import GuideError
from tik.trigger.guides import Guides


def test_reparent_moves_root_guide_and_updates_parent_ref():
    guides = Guides(trigger.maya_backend())
    body = guides.add("base", name="body")
    tail = guides.add("fkchain", name="tail")
    assert tail.parent is None
    guides.reparent(tail, body)
    assert tail.parent.instance_id == body.instance_id
    assert cmds.listRelatives(tail.root.long_name, parent=True)[0] == body.root.name
    guides.reparent(tail, None)
    assert tail.parent is None
    assert cmds.listRelatives(tail.root.long_name, parent=True)[0] == "trigger_guides_grp"
    with pytest.raises(GuideError):
        guides.reparent(tail, tail)
    guides.reparent(tail, body)
    with pytest.raises(GuideError):
        guides.reparent(body, tail)  # would create a cycle
