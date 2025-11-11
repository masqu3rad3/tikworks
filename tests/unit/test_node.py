# python
import pytest
from maya import cmds

from tikmaya.core.node import Node, Plug
from tikmaya.core.dagnode import DagNode


def test_node_init_raises_for_missing():
    with pytest.raises(ValueError):
        Node("|doesNotExist")


def test_create_returns_registered_subclass_for_transform():
    n = Node.create("transform", name="createdX")
    assert isinstance(n, DagNode)
    assert n.exists()
    assert n.name == "createdX"

def test_create_commands_with_multiple_return_values():
    n = Node.create("polySphere", name="polySphereX")
    assert isinstance(n, Node)
    assert n.exists()
    assert n.name == "polySphereX"

def test_uuid_constant_across_rename():
    t = cmds.createNode("transform", name="orig")
    node = Node(cmds.ls(t, long=True)[0])
    old_uuid = node.uuid
    node.rename("renamed")
    assert node.uuid == old_uuid
    assert node.name == "renamed"

def test_name_and_long_name_refresh_after_external_rename():
    t = cmds.createNode("transform", name="A")
    node = Node(cmds.ls(t, long=True)[0])

    _ = node.name
    _ = node.long_name

    cmds.rename("A", "B")

    assert node.name == "B"
    assert node.long_name.endswith("|B")


def test_long_name_shows_full_dag_path():
    parent = cmds.createNode("transform", name="grp")
    child = cmds.createNode("transform", name="child", parent=parent)
    node = Node(cmds.ls(child, long=True)[0])
    assert node.long_name.endswith("|grp|child")


def test_rename_invalidate_cache_and_returns_self():
    t = cmds.createNode("transform", name="toRename")
    node = Node(cmds.ls(t, long=True)[0])
    result = node.rename("renamedX")
    assert result is node
    assert node.name == "renamedX"
    assert node.long_name.endswith("|renamedX")


def test_exists_true_then_false_after_delete_and_cache_invalidated():
    t = cmds.createNode("transform", name="toDelete")
    node = Node(cmds.ls(t, long=True)[0])
    assert node.exists()
    node.delete()
    assert not cmds.objExists(t)
    assert node.name is None
    assert node.long_name is None

def test_getitem_returns_plug_and_path_ends_with_attr():
    t = cmds.createNode("transform", name="holder")
    node = Node(cmds.ls(t, long=True)[0])
    cmds.addAttr(node.name, longName="foo", dataType="string")
    plug = node["foo"]
    assert isinstance(plug, Plug)
    assert plug.attr == "foo"
    assert plug.path.split(".")[-1] == "foo"


def test_plug_getitem_returns_nested_plug():
    node = Node.create("blendShape", name="bs")
    # ensure the nested plug exists
    assert node["input[0]"]["inputGeometry"]


def test_plug_set_and_get_numeric_float_on_builtin_attr():
    t = cmds.createNode("transform", name="item")
    node = Node(cmds.ls(t, long=True)[0])
    plug = node["rotateX"]
    plug.set(12.5)
    assert pytest.approx(plug.get(), rel=1e-6) == 12.5
    plug.value = 14.5
    assert pytest.approx(plug.value, rel=1e-6) == 14.5


def test_rshift_operator_returns_connected_plug():
    a = Node.create("transform", name="A_shift")
    b = Node.create("transform", name="B_shift")
    a["tx"] >> b["tx"]
    assert cmds.listConnections(b.name) == [a.name]


def test_chain_rshift_operator_returns_final_connected_plug():
    a = Node.create("transform", name="A_chain")
    b = Node.create("transform", name="B_chain")
    c = Node.create("transform", name="C_chain")
    a["ty"] >> b["ty"] >> c["ty"]
    assert cmds.listConnections(c.name) == [b.name]
    assert cmds.listConnections(b.name) == [c.name, a.name]


def test_plug_set_with_list_single_value_on_builtin_attr():
    t = cmds.createNode("transform", name="item2")
    node = Node(cmds.ls(t, long=True)[0])
    plug = node["rotateY"]
    plug.set([42.0])
    assert pytest.approx(plug.get(), rel=1e-6) == 42.0


def test_plug_set_and_get_string_attribute():
    t = cmds.createNode("transform", name="strHolder")
    node = Node(cmds.ls(t, long=True)[0])
    cmds.addAttr(node.name, longName="label", dataType="string")
    p = node["label"]
    p.set("hello world")
    assert p.get() == "hello world"


def test_plug_set_and_get_matrix_attribute():
    t = cmds.createNode("transform", name="matrixHolder")
    node = Node(cmds.ls(t, long=True)[0])
    cmds.addAttr(node.name, longName="myMatrix", attributeType="matrix")
    p = node["myMatrix"]
    matrix_value = [1.0, 0.0, 0.0, 0.0,
                    0.0, 1.0, 0.0, 0.0,
                    0.0, 0.0, 1.0, 0.0,
                    5.0, 10.0, 15.0, 1.0]
    p.set(matrix_value)
    retrieved_value = p.get()
    assert all(pytest.approx(a, rel=1e-6) == b for a, b in zip(retrieved_value, matrix_value))


def test_plug_set_unsupported_type_raises_typeerror():
    t = cmds.createNode("transform", name="badSet")
    node = Node(cmds.ls(t, long=True)[0])
    with pytest.raises(TypeError):
        node["rotateZ"].set({"x": 1})


def test_connect_and_disconnect_specific_plugs():
    a = cmds.createNode("transform", name="A")
    b = cmds.createNode("transform", name="B")
    an = Node(cmds.ls(a, long=True)[0])
    bn = Node(cmds.ls(b, long=True)[0])
    cmds.addAttr(an.name, longName="outA", attributeType="double", keyable=True)
    cmds.addAttr(bn.name, longName="inA", attributeType="double", keyable=True)

    src = an["outA"]
    dst = bn["inA"]

    src.set(7.0)
    src.connect(dst, force=True)

    conns = cmds.listConnections(dst.path, plugs=True, source=True) or []
    assert any(c.endswith(".outA") for c in conns)

    src.disconnect(dst)

    conns = cmds.listConnections(dst.path, plugs=True, source=True) or []
    assert conns == []


def test_disconnect_without_target_unplugs_source_connection():
    a = cmds.createNode("transform", name="A2")
    b = cmds.createNode("transform", name="B2")
    an = Node(cmds.ls(a, long=True)[0])
    bn = Node(cmds.ls(b, long=True)[0])
    cmds.addAttr(an.name, longName="outB", attributeType="double", keyable=True)
    cmds.addAttr(bn.name, longName="inB", attributeType="double", keyable=True)

    src = an["outB"]
    dst = bn["inB"]
    src.connect(dst, force=True)

    dst.disconnect()

    conns = cmds.listConnections(dst.path, plugs=True, source=True) or []
    assert conns == []


def test_node_and_plug_repr_contain_identifiers():
    t = cmds.createNode("transform", name="reprTest")
    node = Node(cmds.ls(t, long=True)[0])
    cmds.addAttr(node.name, longName="attrA", attributeType="double", keyable=True)
    plug = node["attrA"]
    assert "Node" in repr(node)
    assert "Plug" in repr(plug)
    assert ".attrA" in repr(plug)


def test_adding_and_deleting_attributes_from_node_level():
    t = cmds.createNode("transform", name="attrDelTest")
    node = Node(cmds.ls(t, long=True)[0])
    node.add_attr("tempAttr", attributeType="double", keyable=True)
    plug = node["tempAttr"]
    assert plug.get() == 0.0  # default value for double attribute
    node.delete_attr("tempAttr")
    with pytest.raises(ValueError):
        plug.get()


def test_adding_and_deleting_attributes_from_plug_level():
    t = cmds.createNode("transform", name="attrDelTest")
    node = Node(cmds.ls(t, long=True)[0])
    plug = node["attrDelTest"]
    plug.create(attributeType="double", keyable=True)
    assert plug.get() == 0.0  # default value for double attribute
    plug.delete()
    with pytest.raises(ValueError):
        plug.get()


def test_attribute_exists():
    t = cmds.createNode("transform", name="attrExistTest")
    node = Node(cmds.ls(t, long=True)[0])
    node.add_attr("existAttr", attributeType="double", keyable=True)
    plug = node["existAttr"]
    assert plug.exists() is True
    plug.delete()
    assert plug.exists() is False


def test_rename_attribute_updates_plug_attr_name():
    t = cmds.createNode("transform", name="attrRenameTest")
    node = Node(cmds.ls(t, long=True)[0])
    node.add_attr("oldAttr", attributeType="double", keyable=True)
    plug = node["oldAttr"]
    plug.rename("newAttr")
    assert plug.attr == "newAttr"
    assert cmds.objExists(f"{node.name}.newAttr")
    assert not cmds.objExists(f"{node.name}.oldAttr")


def test_lock_and_unlock_attribute():
    t = cmds.createNode("transform", name="attrLockTest")
    node = Node(cmds.ls(t, long=True)[0])
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
    t = cmds.createNode("transform", name="attrVisibleTest")
    node = Node(cmds.ls(t, long=True)[0])
    node.add_attr("visAttr", attributeType="double", keyable=True)
    plug = node["visAttr"]
    plug.visible = False
    assert cmds.getAttr(plug.path, channelBox=True) is False
    plug.visible = True
    assert cmds.getAttr(plug.path, channelBox=True) is True
    assert plug.visible is True


def test_keyable_property_and_setter():
    t = cmds.createNode("transform", name="attrKeyableTest")
    node = Node(cmds.ls(t, long=True)[0])
    node.add_attr("keyAttr", attributeType="double", keyable=True)
    plug = node["keyAttr"]
    plug.keyable = False
    assert cmds.getAttr(plug.path, keyable=True) is False
    plug.keyable = True
    assert cmds.getAttr(plug.path, keyable=True) is True
    assert plug.keyable is True

def test_rshift_operator_raises_typeerror_for_nonplug_rhs():
    a = Node.create("transform", name="A_invalid")
    with pytest.raises(TypeError):
        a["tx"] >> "notAPlug"