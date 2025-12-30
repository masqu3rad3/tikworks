import pytest
from maya import cmds
from tik.maya.types.light import Light
from tik.maya.core.shapenode import ShapeNode

def test_create_default_light():
    """Test creating a default light (pointLight)."""
    light = Light.create()
    assert isinstance(light, Light)
    assert isinstance(light, ShapeNode)
    assert cmds.objExists(light.name)
    assert cmds.nodeType(light.name) == "pointLight"

    # Verify it has a transform
    assert light.transform is not None
    assert cmds.nodeType(light.transform.name) == "transform"

@pytest.mark.parametrize("light_type", [
    "pointLight",
    "directionalLight",
    "spotLight",
    "areaLight",
    "ambientLight"
])
def test_create_specific_light_types(light_type):
    """Test creating specific light types."""
    light = Light.create(light_type=light_type)
    assert isinstance(light, Light)
    assert cmds.objExists(light.name)
    assert cmds.nodeType(light.name) == light_type

def test_create_light_with_name():
    """Test creating a light with a specific name."""
    name = "my_test_light"
    light = Light.create(name=name)
    # cmds.createNode("pointLight", name="foo") creates a node named "foo".
    assert light.name == name
    assert cmds.objExists(name)

def test_create_light_invalid_type_non_dag():
    """Test creating a light with a non-DAG node type."""
    # Using a non-DAG node type should fail because Light inherits ShapeNode which expects a DAG path
    # OpenMaya.MSelectionList().getDagPath(0) raises TypeError for non-DAG nodes
    with pytest.raises(TypeError):
        Light.create(light_type="multiplyDivide")

def test_create_light_invalid_type_transform_no_shape():
    """Test creating a light with a transform type (no shape)."""
    # ShapeNode raises ValueError if initialized with a transform that has no shape
    with pytest.raises(ValueError, match="has no shape"):
        Light.create(light_type="transform")

def test_light_repr():
    """Test the string representation of the Light object."""
    light = Light.create(name="repr_light")
    assert "repr_light" in repr(light)
    # The default repr for Node usually includes the class name and node name
    # We assume Node or DagNode implements __repr__

