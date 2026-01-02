"""Unit tests for tikmaya.core.node module."""

# python
import pytest
from maya import cmds

from tik.maya.core.node import Node, Plug
from tik.maya.core.dagnode import DagNode


def test_node_init_raises_for_missing():
    """Test that Node initialization raises ValueError for non-existent nodes."""
    with pytest.raises(ValueError):
        Node("|doesNotExist")


def test_create_returns_registered_subclass_for_transform():
    """Test that creating a transform returns a DagNode instance."""
    node = Node.create("transform", name="createdX")
    assert isinstance(node, DagNode)
    assert node.exists()
    assert node.name == "createdX"


def test_create_commands_with_multiple_return_values():
    """Test creating a node with a command that returns multiple values."""
    node = Node.create("polySphere", name="polySphereX")
    assert isinstance(node, Node)
    assert node.exists()
    assert node.name == "polySphereX"


def test_uuid_constant_across_rename():
    """Test that UUID remains constant after renaming a node."""
    transform = cmds.createNode("transform", name="orig")
    node = Node(cmds.ls(transform, long=True)[0])
    old_uuid = node.uuid
    node.rename("renamed")
    assert node.uuid == old_uuid
    assert node.name == "renamed"


def test_name_and_long_name_refresh_after_external_rename():
    """Test that name and long_name properties refresh after external rename."""
    transform = cmds.createNode("transform", name="A")
    node = Node(cmds.ls(transform, long=True)[0])

    _ = node.name
    _ = node.long_name

    cmds.rename("A", "B")

    assert node.name == "B"
    assert node.long_name.endswith("|B")


def test_long_name_shows_full_dag_path():
    """Test that long_name returns the full DAG path."""
    parent = cmds.createNode("transform", name="grp")
    child = cmds.createNode("transform", name="child", parent=parent)
    node = Node(cmds.ls(child, long=True)[0])
    assert node.long_name.endswith("|grp|child")


def test_rename_invalidate_cache_and_returns_self():
    """Test that rename invalidates cache and returns the node instance."""
    transform = cmds.createNode("transform", name="toRename")
    node = Node(cmds.ls(transform, long=True)[0])
    result = node.rename("renamedX")
    assert result is node
    assert node.name == "renamedX"
    assert node.long_name.endswith("|renamedX")


def test_exists_true_then_false_after_delete_and_cache_invalidated():
    """Test exists() returns correct state before and after deletion."""
    transform = cmds.createNode("transform", name="toDelete")
    node = Node(cmds.ls(transform, long=True)[0])
    assert node.exists()
    node.delete()
    assert not cmds.objExists(transform)
    assert node.name is None
    assert node.long_name is None


def test_getitem_returns_plug_and_path_ends_with_attr():
    """Test __getitem__ returns a Plug with correct path."""
    transform = cmds.createNode("transform", name="holder")
    node = Node(cmds.ls(transform, long=True)[0])
    cmds.addAttr(node.name, longName="foo", dataType="string")
    plug = node["foo"]
    assert isinstance(plug, Plug)
    assert plug.attr == "foo"
    assert plug.path.split(".")[-1] == "foo"


def test_plug_getitem_returns_nested_plug():
    """Test __getitem__ on a Plug returns a nested Plug."""
    node = Node.create("blendShape", name="bs")
    # ensure the nested plug exists
    assert node["input[0]"]["inputGeometry"]


def test_plug_set_and_get_numeric_float_on_builtin_attr():
    """Test setting and getting a float value on a built-in attribute."""
    transform = cmds.createNode("transform", name="item")
    node = Node(cmds.ls(transform, long=True)[0])
    plug = node["rotateX"]
    plug.set(12.5)
    assert pytest.approx(plug.get(), rel=1e-6) == 12.5
    plug.value = 14.5
    assert pytest.approx(plug.value, rel=1e-6) == 14.5


def test_rshift_operator_returns_connected_plug():
    """Test >> operator connects plugs and returns the destination plug."""
    src_node = Node.create("transform", name="A_shift")
    dst_node = Node.create("transform", name="B_shift")
    src_node["tx"] >> dst_node["tx"]
    assert cmds.listConnections(dst_node.name) == [src_node.name]


def test_chain_rshift_operator_returns_final_connected_plug():
    """Test chaining >> operator connects multiple plugs."""
    node_a = Node.create("transform", name="A_chain")
    node_b = Node.create("transform", name="B_chain")
    node_c = Node.create("transform", name="C_chain")
    node_a["ty"] >> node_b["ty"] >> node_c["ty"]
    assert cmds.listConnections(node_c.name) == [node_b.name]
    assert cmds.listConnections(node_b.name) == [node_c.name, node_a.name]


def test_plug_set_with_list_single_value_on_builtin_attr():
    """Test setting a single value list on a built-in attribute."""
    transform = cmds.createNode("transform", name="item2")
    node = Node(cmds.ls(transform, long=True)[0])
    plug = node["rotateY"]
    plug.set([42.0])
    assert pytest.approx(plug.get(), rel=1e-6) == 42.0


def test_plug_set_and_get_string_attribute():
    """Test setting and getting a string attribute."""
    transform = cmds.createNode("transform", name="strHolder")
    node = Node(cmds.ls(transform, long=True)[0])
    cmds.addAttr(node.name, longName="label", dataType="string")
    plug = node["label"]
    plug.set("hello world")
    assert plug.get() == "hello world"


def test_plug_set_and_get_matrix_attribute():
    """Test setting and getting a matrix attribute."""
    transform = cmds.createNode("transform", name="matrixHolder")
    node = Node(cmds.ls(transform, long=True)[0])
    cmds.addAttr(node.name, longName="myMatrix", attributeType="matrix")
    plug = node["myMatrix"]
    matrix_value = [1.0, 0.0, 0.0, 0.0,
                    0.0, 1.0, 0.0, 0.0,
                    0.0, 0.0, 1.0, 0.0,
                    5.0, 10.0, 15.0, 1.0]
    plug.set(matrix_value)
    retrieved_value = plug.get()
    assert all(pytest.approx(a, rel=1e-6) == b for a, b in zip(retrieved_value, matrix_value))


def test_plug_set_unsupported_type_raises_typeerror():
    """Test setting an unsupported type raises TypeError."""
    transform = cmds.createNode("transform", name="badSet")
    node = Node(cmds.ls(transform, long=True)[0])
    with pytest.raises(TypeError):
        node["rotateZ"].set({"x": 1})


def test_connect_and_disconnect_specific_plugs():
    """Test connecting and disconnecting specific plugs."""
    node_a = cmds.createNode("transform", name="A")
    node_b = cmds.createNode("transform", name="B")
    wrapper_a = Node(cmds.ls(node_a, long=True)[0])
    wrapper_b = Node(cmds.ls(node_b, long=True)[0])
    cmds.addAttr(wrapper_a.name, longName="outA", attributeType="double", keyable=True)
    cmds.addAttr(wrapper_b.name, longName="inA", attributeType="double", keyable=True)

    src = wrapper_a["outA"]
    dst = wrapper_b["inA"]

    src.set(7.0)
    src.connect(dst, force=True)

    conns = cmds.listConnections(dst.path, plugs=True, source=True) or []
    assert any(c.endswith(".outA") for c in conns)

    src.disconnect(dst)

    conns = cmds.listConnections(dst.path, plugs=True, source=True) or []
    assert conns == []


def test_disconnect_without_target_unplugs_source_connection():
    """Test disconnecting without target unplugs source connection."""
    node_a = cmds.createNode("transform", name="A2")
    node_b = cmds.createNode("transform", name="B2")
    wrapper_a = Node(cmds.ls(node_a, long=True)[0])
    wrapper_b = Node(cmds.ls(node_b, long=True)[0])
    cmds.addAttr(wrapper_a.name, longName="outB", attributeType="double", keyable=True)
    cmds.addAttr(wrapper_b.name, longName="inB", attributeType="double", keyable=True)

    src = wrapper_a["outB"]
    dst = wrapper_b["inB"]
    src.connect(dst, force=True)

    dst.disconnect()

    conns = cmds.listConnections(dst.path, plugs=True, source=True) or []
    assert conns == []


def test_node_and_plug_repr_contain_identifiers():
    """Test __repr__ contains class name and identifiers."""
    transform = cmds.createNode("transform", name="reprTest")
    node = Node(cmds.ls(transform, long=True)[0])
    cmds.addAttr(node.name, longName="attrA", attributeType="double", keyable=True)
    plug = node["attrA"]
    assert "Node" in repr(node)
    assert "Plug" in repr(plug)
    assert ".attrA" in repr(plug)


def test_adding_and_deleting_attributes_from_node_level():
    """Test adding and deleting attributes from Node methods."""
    transform = cmds.createNode("transform", name="attrDelTest")
    node = Node(cmds.ls(transform, long=True)[0])
    node.add_attr("tempAttr", attributeType="double", keyable=True)
    plug = node["tempAttr"]
    assert plug.get() == 0.0  # default value for double attribute
    node.delete_attr("tempAttr")
    with pytest.raises(ValueError):
        plug.get()


def test_adding_and_deleting_attributes_from_plug_level():
    """Test adding and deleting attributes from Plug methods."""
    transform = cmds.createNode("transform", name="attrDelTest")
    node = Node(cmds.ls(transform, long=True)[0])
    plug = node["attrDelTest"]
    plug.create(attributeType="double", keyable=True)
    assert plug.get() == 0.0  # default value for double attribute
    plug.delete()
    with pytest.raises(ValueError):
        plug.get()


def test_attribute_exists():
    """Test checking if an attribute exists via Plug."""
    transform = cmds.createNode("transform", name="attrExistTest")
    node = Node(cmds.ls(transform, long=True)[0])
    node.add_attr("existAttr", attributeType="double", keyable=True)
    plug = node["existAttr"]
    assert plug.exists() is True
    plug.delete()
    assert plug.exists() is False


def test_rename_attribute_updates_plug_attr_name():
    """Test renaming an attribute updates the Plug's attribute name."""
    transform = cmds.createNode("transform", name="attrRenameTest")
    node = Node(cmds.ls(transform, long=True)[0])
    node.add_attr("oldAttr", attributeType="double", keyable=True)
    plug = node["oldAttr"]
    plug.rename("newAttr")
    assert plug.attr == "newAttr"
    assert cmds.objExists(f"{node.name}.newAttr")
    assert not cmds.objExists(f"{node.name}.oldAttr")


def test_lock_and_unlock_attribute():
    """Test locking and unlocking an attribute."""
    transform = cmds.createNode("transform", name="attrLockTest")
    node = Node(cmds.ls(transform, long=True)[0])
    node.add_attr("lockAttr", attributeType="double", keyable=True)
    plug = node["lockAttr"]
    plug.lock()
    assert cmds.getAttr(plug.path, lock=True) is True
    plug.unlock()
    assert cmds.getAttr(plug.path, lock=True) is False
    # test the property and setter
    plug.locked = True
    assert plug.locked is True
    plug.locked = False
    assert plug.locked is False

def test_visible_property_and_setter():
    """Test visible property and setter."""
    transform = cmds.createNode("transform", name="attrVisibleTest")
    node = Node(cmds.ls(transform, long=True)[0])
    node.add_attr("visAttr", attributeType="double", keyable=True)
    plug = node["visAttr"]
    plug.visible = False
    assert cmds.getAttr(plug.path, channelBox=True) is False
    plug.visible = True
    assert cmds.getAttr(plug.path, channelBox=True) is True
    assert plug.visible is True


def test_keyable_property_and_setter():
    """Test keyable property and setter."""
    transform = cmds.createNode("transform", name="attrKeyableTest")
    node = Node(cmds.ls(transform, long=True)[0])
    node.add_attr("keyAttr", attributeType="double", keyable=True)
    plug = node["keyAttr"]
    plug.keyable = False
    assert cmds.getAttr(plug.path, keyable=True) is False
    plug.keyable = True
    assert cmds.getAttr(plug.path, keyable=True) is True
    assert plug.keyable is True

def test_rshift_operator_raises_typeerror_for_nonplug_rhs():
    """Test >> operator raises TypeError for non-Plug RHS."""
    node = Node.create("transform", name="A_invalid")
    with pytest.raises(TypeError):
        node["tx"] >> "notAPlug"


def test_duplicate_node():
    """Test duplicating a node."""
    original = cmds.createNode("transform", name="original")
    node = Node(cmds.ls(original, long=True)[0])
    dup = node.duplicate(name="copy")
    assert dup.exists()
    assert dup.name == "copy"
    assert dup.type == "transform"
    assert dup.uuid != node.uuid


def test_has_attr():
    """Test checking if an attribute exists."""
    transform = cmds.createNode("transform", name="attrTest")
    node = Node(cmds.ls(transform, long=True)[0])
    assert node.has_attr("translateX")
    assert not node.has_attr("nonExistentAttr")


def test_node_str_representation():
    """Test string representation of a node."""
    transform = cmds.createNode("transform", name="strTest")
    node = Node(cmds.ls(transform, long=True)[0])
    assert str(node) == "strTest"


def test_plug_children_compound_attribute():
    """Test getting children of a compound attribute."""
    transform = cmds.createNode("transform", name="compoundTest")
    node = Node(cmds.ls(transform, long=True)[0])
    # translate is a compound attribute
    plug = node["translate"]
    children = plug.children
    assert len(children) == 3
    assert any(c.attr == "translateX" for c in children)
    assert any(c.attr == "translateY" for c in children)
    assert any(c.attr == "translateZ" for c in children)


def test_plug_children_empty_for_simple_attribute():
    """Test children property returns empty list for simple attribute."""
    transform = cmds.createNode("transform", name="simpleTest")
    node = Node(cmds.ls(transform, long=True)[0])
    plug = node["translateX"]
    assert plug.children == []


def test_plug_get_input_returns_node():
    """Test get_input returns the source node."""
    src_node = Node.create("transform", name="srcNode")
    dst_node = Node.create("transform", name="dstNode")
    src_node["tx"] >> dst_node["tx"]

    input_node = dst_node["tx"].get_input()
    assert isinstance(input_node, Node)
    assert input_node.name == src_node.name


def test_plug_get_input_returns_plug():
    """Test get_input returns the source plug."""
    src_node = Node.create("transform", name="srcNode2")
    dst_node = Node.create("transform", name="dstNode2")
    src_node["translateX"] >> dst_node["translateX"]

    input_plug = dst_node["translateX"].get_input(plug=True)
    assert isinstance(input_plug, Plug)
    assert input_plug.path == src_node["translateX"].path


def test_plug_list_outputs_returns_nodes():
    """Test list_outputs returns destination nodes."""
    src_node = Node.create("transform", name="outSrc")
    dst_node_1 = Node.create("transform", name="outDst1")
    dst_node_2 = Node.create("transform", name="outDst2")

    src_node["tx"] >> dst_node_1["tx"]
    src_node["tx"] >> dst_node_2["tx"]

    outputs = src_node["tx"].list_outputs()
    assert len(outputs) == 2
    names = sorted([n.name for n in outputs])
    assert names == ["outDst1", "outDst2"]


def test_plug_list_outputs_returns_plugs():
    """Test list_outputs returns destination plugs."""
    src_node = Node.create("transform", name="outSrc2")
    dst_node = Node.create("transform", name="outDst3")

    src_node["translateX"] >> dst_node["translateX"]

    outputs = src_node["translateX"].list_outputs(plugs=True)
    assert len(outputs) == 1
    assert isinstance(outputs[0], Plug)
    assert outputs[0].path == dst_node["translateX"].path


def test_plug_get_input_no_connection_returns_none():
    """Test get_input returns None when no connection exists."""
    node = Node.create("transform", name="noInput")
    assert node["tx"].get_input() is None


def test_plug_list_outputs_no_connection_returns_empty_list():
    """Test list_outputs returns empty list when no connection exists."""
    node = Node.create("transform", name="noOutput")
    assert node["tx"].list_outputs() == []


def test_plug_children_empty_multi_attr():
    """Test children property returns empty list for empty multi attribute."""
    transform = cmds.createNode("transform", name="multiTest")
    node = Node(cmds.ls(transform, long=True)[0])
    cmds.addAttr(node.name, longName="myArray", multi=True)
    plug = node["myArray"]
    assert plug.children == []
