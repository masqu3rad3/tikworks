import pytest
from maya import cmds
from tik.maya.types.joint import Joint

def test_create_joint():
    joint = Joint.create(name='testJoint')
    assert cmds.nodeType(joint.name) == 'joint'
    assert joint.name == 'testJoint'
    assert isinstance(joint, Joint)

def test_orient_joint():
    joint = Joint.create(name='orientJoint')
    joint.orient((10, 20, 30))
    jo = cmds.getAttr(f'{joint.name}.jointOrient')[0]
    assert jo == pytest.approx((10, 20, 30), abs=1e-6)


def test_create_joint_with_position():
    """Test creating a joint with a position."""
    joint = Joint.create(name='posJoint', position=(5, 10, 15))
    translate = cmds.getAttr(f'{joint.name}.translate')[0]
    assert translate == pytest.approx((5, 10, 15), abs=1e-6)


def test_create_joint_with_orientation():
    """Test creating a joint with orientation."""
    joint = Joint.create(name='orientedJoint', orientation=(15, 25, 35))
    jo = cmds.getAttr(f'{joint.name}.jointOrient')[0]
    assert jo == pytest.approx((15, 25, 35), abs=1e-6)


def test_create_joint_with_scale():
    """Test creating a joint with scale."""
    joint = Joint.create(name='scaledJoint', scale=(2, 3, 4))
    scale = cmds.getAttr(f'{joint.name}.scale')[0]
    assert scale == pytest.approx((2, 3, 4), abs=1e-6)


def test_create_joint_with_radius():
    """Test creating a joint with radius."""
    joint = Joint.create(name='radiusJoint', radius=5.0)
    assert joint.radius == pytest.approx(5.0, abs=1e-6)


def test_joint_radius_property():
    """Test getting and setting joint radius."""
    joint = Joint.create(name='radiusPropJoint')

    # Get default radius
    default_radius = joint.radius
    assert isinstance(default_radius, float)

    # Set new radius
    joint.radius = 3.5
    assert joint.radius == pytest.approx(3.5, abs=1e-6)
    assert cmds.getAttr(f'{joint.name}.radius') == pytest.approx(3.5, abs=1e-6)


def test_create_joint_with_parent():
    """Test creating a joint with a parent."""
    parent = Joint.create(name='parentJoint')
    child = Joint.create(name='childJoint', parent=parent)

    parents = cmds.listRelatives(child.name, parent=True)
    assert parents and parents[0] == parent.name

