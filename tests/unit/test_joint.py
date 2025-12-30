import pytest
from maya import cmds
from tik.maya.types.joint import Joint

def test_create_joint():
    j = Joint.create(name='testJoint')
    assert cmds.nodeType(j.name) == 'joint'
    assert j.name == 'testJoint'
    assert isinstance(j, Joint)

def test_orient_joint():
    j = Joint.create(name='orientJoint')
    j.orient((10, 20, 30))
    jo = cmds.getAttr(f'{j.name}.jointOrient')[0]
    assert jo == pytest.approx((10, 20, 30), abs=1e-6)
