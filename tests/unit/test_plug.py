"""Unit tests for tikmaya.core.plug module."""

import pytest
from maya import cmds
from tik.maya.core.node import Node, Plug
from tik.maya.core.constants import NodeNames

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


class TestPlugCreate:
    """``Plug.create`` is the one typed attribute creator."""

    def test_returns_the_plug_so_it_can_be_assigned(self):
        node = Node.create("transform", name="holder")
        plug = node["stretch"].create("float", default=1.0)
        assert plug is not None
        assert plug.attr == "stretch"
        assert plug.value == 1.0

    def test_float_takes_hard_limits_and_is_keyable_by_default(self):
        """``addAttr`` defaults keyable to False; an animator attribute is not."""
        node = Node.create("transform", name="holder")
        plug = node["stretch"].create("float", default=1.0, min=0.0, max=2.0)
        assert cmds.attributeQuery("stretch", node=node.name, minimum=True) == [0.0]
        assert cmds.attributeQuery("stretch", node=node.name, maximum=True) == [2.0]
        assert plug.keyable

    def test_soft_range_slides_without_capping_the_value(self):
        """The slider spans the soft range; a typed value may go past it."""
        node = Node.create("transform", name="holder")
        plug = node["amount"].create(
            "float", default=0.0, min=-2.0, max=2.0, soft_min=0.0, soft_max=1.0
        )
        assert cmds.attributeQuery("amount", node=node.name, softMin=True) == [0.0]
        assert cmds.attributeQuery("amount", node=node.name, softMax=True) == [1.0]
        plug.value = 1.7
        assert plug.value == pytest.approx(1.7)
        plug.value = -1.4
        assert plug.value == pytest.approx(-1.4)

    def test_without_a_soft_range_none_is_authored(self):
        node = Node.create("transform", name="holder")
        node["plain"].create("float", default=1.0, min=0.0, max=2.0)
        assert not cmds.attributeQuery("plain", node=node.name, softMaxExists=True)

    def test_int_bool_and_enum(self):
        node = Node.create("transform", name="holder")
        assert node["count"].create("int", default=4).value == 4
        assert node["flag"].create("bool", default=True).value is True
        enum_plug = node["space"].create("enum", items=["world", "local"], default=1)
        assert enum_plug.value == 1
        assert cmds.attributeQuery("space", node=node.name, listEnum=True) == [
            "world:local"
        ]

    def test_string_default_is_applied_after_creation(self):
        """``addAttr`` cannot default a string, so ``create`` sets it."""
        node = Node.create("transform", name="holder")
        assert node["notes"].create("string", default="rev 2").value == "rev 2"
        assert node["blank"].create("string").value in (None, "")

    def test_proxy_mirrors_its_source_both_ways(self):
        source = Node.create("transform", name="source")
        holder = Node.create("transform", name="holder")
        src_plug = source["stretch"].create("float", default=0.25)
        proxy = holder["stretch"].create(proxy=src_plug)
        assert proxy.value == 0.25
        proxy.value = 0.75
        assert src_plug.value == 0.75

    def test_raw_addattr_flags_still_pass_through(self):
        node = Node.create("transform", name="holder")
        plug = node["raw"].create(attributeType="double", keyable=True)
        assert plug.exists()
        assert plug.keyable

    def test_unknown_type_is_rejected(self):
        node = Node.create("transform", name="holder")
        with pytest.raises(ValueError, match="Unknown attribute type"):
            node["oops"].create("vector3")

    def test_a_type_is_required(self):
        node = Node.create("transform", name="holder")
        with pytest.raises(ValueError, match="attr_type"):
            node["oops"].create(default=1.0)

    def test_channels_lock_and_hide_through_plug_state(self):
        node = Node.create("transform", name="holder")
        for channel in ("sx", "sy", "sz", "v"):
            plug = node[channel]
            plug.locked = True
            plug.visible = False
        assert node["sx"].locked
        assert not node["sx"].visible
        assert not node["tx"].locked
        node["sx"].locked = False
        node["sx"].visible = True
        assert not node["sx"].locked
        assert node["sx"].visible

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

    # By default, dynamic attributes are keyable/visible
    assert plug.visible is True

    plug.visible = False
    assert cmds.getAttr(plug.path, channelBox=True) is False
    # When not visible (not keyable and not in channelbox)
    assert plug.visible is False

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

def test_node_and_plug_repr_contain_identifiers_plug_part():
    """Test Plug __repr__."""
    transform = cmds.createNode("transform", name="reprPlugTest")
    node = Node(cmds.ls(transform, long=True)[0])
    cmds.addAttr(node.name, longName="attrA", attributeType="double", keyable=True)
    plug = node["attrA"]
    assert "Plug" in repr(plug)
    assert ".attrA" in repr(plug)

def test_plug_access_non_existent_raises_runtime_error():
    """Test accessing a non-existent plug raises RuntimeError."""
    transform = cmds.createNode("transform", name="nonExistentPlugTest")
    node = Node(cmds.ls(transform, long=True)[0])
    plug = node["nonExistentAttr"]

    # Accessing .mplug or .value or .type triggers the check
    with pytest.raises(RuntimeError) as excinfo:
        _ = plug.type
    assert "not found" in str(excinfo.value)

def test_plug_access_deleted_attr_raises_runtime_error_with_refresh_attempt():
    """Test accessing a plug after attribute deletion raises RuntimeError."""
    transform = cmds.createNode("transform", name="deletedPlugTest")
    node = Node(cmds.ls(transform, long=True)[0])
    node.add_attr("tempDel", attributeType="double")
    plug = node["tempDel"]

    # Ensure it works first
    assert plug.get() == 0.0

    # Delete the attribute
    node.delete_attr("tempDel")

    # Now access it again.
    # plug.get() calls cmds.getAttr directly, which raises ValueError immediately if attr is gone.
    with pytest.raises(ValueError):
        _ = plug.get()

    # To test the mplug re-fetch logic (lines 58-60), we need to access a property
    # that uses the .mplug property, like .type or .keyable or .locked.
    with pytest.raises(RuntimeError) as excinfo:
        _ = plug.type
    # The message in our code is "... acts invalid/deleted."
    # depending on where it fails. If _find_plug returns None, it raises "not found".
    assert "not found" in str(excinfo.value) or "acts invalid/deleted" in str(excinfo.value)

def test_lshift_operator_connects_plugs():
    """Test << operator connects plugs."""
    src_node = Node.create("transform", name="srcLShift")
    dst_node = Node.create("transform", name="dstLShift")

    # dst << src
    dst_node["tx"] << src_node["tx"]

    assert cmds.listConnections(dst_node.name) == [src_node.name]

def test_floordiv_operator_disconnects_plugs():
    """Test // operator disconnects plugs."""
    src_node = Node.create("transform", name="srcDiv")
    dst_node = Node.create("transform", name="dstDiv")

    src_node["tx"] >> dst_node["tx"]
    assert cmds.listConnections(dst_node.name) == [src_node.name]

    # src // dst
    src_node["tx"] // dst_node["tx"]
    assert cmds.listConnections(dst_node.name) is None

def test_lshift_operator_raises_typeerror_for_nonplug():
    """Test << operator raises TypeError for non-Plug RHS."""
    node = Node.create("transform", name="LShiftError")
    with pytest.raises(TypeError):
        node["tx"] << "notAPlug"

def test_floordiv_operator_raises_typeerror_for_nonplug():
    """Test // operator raises TypeError for non-Plug RHS."""
    node = Node.create("transform", name="DivError")
    with pytest.raises(TypeError):
        node["tx"] // "notAPlug"

def test_list_inputs_returns_nodes_and_plugs():
    """Test list_inputs returns nodes and plugs correctly."""
    src_node = Node.create("transform", name="srcListIn")
    dst_node = Node.create("transform", name="dstListIn")

    src_node["tx"] >> dst_node["tx"]

    dst_plug = dst_node["tx"]

    # Test returning nodes (default)
    inputs_nodes = dst_plug.list_inputs()
    assert len(inputs_nodes) == 1
    assert isinstance(inputs_nodes[0], Node)
    assert inputs_nodes[0].name == src_node.name

    # Test returning plugs
    inputs_plugs = dst_plug.list_inputs(plugs=True)
    assert len(inputs_plugs) == 1
    assert isinstance(inputs_plugs[0], Plug)
    # Maya listConnections usually returns the long name 'translateX' even if we connected 'tx'
    assert inputs_plugs[0].path == f"{src_node.name}.translateX"

    # Test empty
    unconnected = Node.create("transform", name="unconnected")
    assert unconnected["tx"].list_inputs() == []

# === Math Operator Tests ===

def test_math_add_single_value():
    """Test + operator for single value attributes."""
    node = Node.create("transform", name="mathAddSingle")
    node.add_attr("val1", attributeType="double", defaultValue=10.0)
    node.add_attr("val2", attributeType="double", defaultValue=5.0)

    # Plug + number
    res1 = node["val1"] + 5.0
    assert isinstance(res1, Plug)
    assert res1.get() == 15.0
    # Check node type
    # Node type created by cmds.createNode("addDL") is "addDL"
    assert cmds.nodeType(res1.node.name) == NodeNames.ADD_DOUBLE_LINEAR

    # Plug + Plug
    res2 = node["val1"] + node["val2"]
    assert res2.get() == 15.0

    # Reverse: number + Plug
    res3 = 5.0 + node["val1"]
    assert res3.get() == 15.0

def test_math_sub_single_value():
    """Test - operator for single value attributes."""
    node = Node.create("transform", name="mathSubSingle")
    node.add_attr("val1", attributeType="double", defaultValue=10.0)
    node.add_attr("val2", attributeType="double", defaultValue=4.0)

    # Plug - number
    res1 = node["val1"] - 4.0
    assert res1.get() == 6.0
    assert "subtract" in res1.node.name # check if we can guess node type from name logic

    # Plug - Plug
    res2 = node["val1"] - node["val2"]
    assert res2.get() == 6.0

    # Reverse: number - Plug
    res3 = 20.0 - node["val1"]
    assert res3.get() == 10.0

def test_math_mul_single_value():
    """Test * operator for single value attributes."""
    node = Node.create("transform", name="mathMulSingle")
    node.add_attr("val1", attributeType="double", defaultValue=3.0)
    node.add_attr("val2", attributeType="double", defaultValue=4.0)

    # Plug * number
    res1 = node["val1"] * 2.0
    assert res1.get() == 6.0
    assert cmds.nodeType(res1.node.name) == NodeNames.MULT_DOUBLE_LINEAR

    # Plug * Plug
    res2 = node["val1"] * node["val2"]
    assert res2.get() == 12.0

    # Reverse: number * Plug
    res3 = 2.0 * node["val1"]
    assert res3.get() == 6.0

def test_math_div_single_value():
    """Test / operator for single value attributes."""
    node = Node.create("transform", name="mathDivSingle")
    node.add_attr("val1", attributeType="double", defaultValue=10.0)
    node.add_attr("val2", attributeType="double", defaultValue=2.0)

    # Plug / number
    res1 = node["val1"] / 2.0
    assert res1.get() == 5.0
    assert "divide" in res1.node.name

    # Plug / Plug
    res2 = node["val1"] / node["val2"]
    assert res2.get() == 5.0

    # Reverse: number / Plug
    res3 = 20.0 / node["val1"]
    assert res3.get() == 2.0

def test_math_pow_single_value():
    """Test ** operator for single value attributes."""
    node = Node.create("transform", name="mathPowSingle")
    node.add_attr("val1", attributeType="double", defaultValue=2.0)
    node.add_attr("val2", attributeType="double", defaultValue=3.0)

    # Plug ** number
    res1 = node["val1"] ** 3.0
    assert res1.get() == 8.0

    # Plug ** Plug
    res2 = node["val1"] ** node["val2"]
    assert res2.get() == 8.0

    # Reverse: number ** Plug
    res3 = 3.0 ** node["val1"] # 3^2
    assert res3.get() == 9.0

def test_math_mod_single_value():
    """Test % operator for single value attributes."""
    node = Node.create("transform", name="mathModSingle")
    node.add_attr("val1", attributeType="double", defaultValue=10.0)
    node.add_attr("val2", attributeType="double", defaultValue=3.0)

    # Plug % number
    res1 = node["val1"] % 3.0
    assert res1.get() == 1.0 # 10 % 3 = 1

    # Plug % Plug
    res2 = node["val1"] % node["val2"]
    assert res2.get() == 1.0

    # Reverse: number % Plug
    res3 = 10.0 % node["val2"] # 10 % 3 = 1
    assert res3.get() == 1.0

def test_math_add_compound_value():
    """Test + operator for compound attributes (double3)."""
    node = Node.create("transform", name="mathAddCompound")
    # Translate is double3
    node["t"].set([1.0, 2.0, 3.0])

    # Plug + number (adds to all components)
    res1 = node["t"] + 1.0
    assert res1.get() == [(2.0, 3.0, 4.0)]
    assert cmds.nodeType(res1.node.name) == "plusMinusAverage"

    # Plug + list/tuple
    res2 = node["t"] + [1.0, 1.0, 1.0]
    assert res2.get() == [(2.0, 3.0, 4.0)]

    # Plug + Plug
    node["r"].set([1.0, 1.0, 1.0])
    res3 = node["t"] + node["r"]
    assert res3.get() == [(2.0, 3.0, 4.0)]

    # Reverse: number + Plug
    res4 = 1.0 + node["t"]
    assert res4.get() == [(2.0, 3.0, 4.0)]

def test_math_sub_compound_value():
    """Test - operator for compound attributes."""
    node = Node.create("transform", name="mathSubCompound")
    node["t"].set([10.0, 20.0, 30.0])

    # Plug - number
    res1 = node["t"] - 1.0
    assert res1.get() == [(9.0, 19.0, 29.0)]

    # Plug - list
    res2 = node["t"] - [1.0, 2.0, 3.0]
    assert res2.get() == [(9.0, 18.0, 27.0)]

    # Plug - Plug
    node["r"].set([1.0, 1.0, 1.0])
    res3 = node["t"] - node["r"]
    assert res3.get() == [(9.0, 19.0, 29.0)]

    # Reverse: number - Plug
    res4 = 20.0 - node["t"] # (20,20,20) - (10,20,30) = (10, 0, -10)
    assert res4.get() == [(10.0, 0.0, -10.0)]

    # Reverse: list - Plug
    res5 = [10.0, 20.0, 30.0] - node["r"]
    assert res5.get() == [(9.0, 19.0, 29.0)]

def test_math_mul_compound_value():
    """Test * operator for compound attributes."""
    node = Node.create("transform", name="mathMulCompound")
    node["t"].set([2.0, 3.0, 4.0])

    # Plug * number
    res1 = node["t"] * 2.0
    assert res1.get() == [(4.0, 6.0, 8.0)]
    assert cmds.nodeType(res1.node.name) == "multiplyDivide"

    # Plug * list
    res2 = node["t"] * [2.0, 0.5, 1.0]
    assert res2.get() == [(4.0, 1.5, 4.0)]

    # Plug * Plug
    node["r"].set([2.0, 2.0, 2.0])
    res3 = node["t"] * node["r"]
    assert res3.get() == [(4.0, 6.0, 8.0)]

    # Reverse: number * Plug
    res4 = 2.0 * node["t"]
    assert res4.get() == [(4.0, 6.0, 8.0)]

def test_math_div_compound_value():
    """Test / operator for compound attributes."""
    node = Node.create("transform", name="mathDivCompound")
    node["t"].set([10.0, 20.0, 30.0])

    # Plug / number
    res1 = node["t"] / 2.0
    assert res1.get() == [(5.0, 10.0, 15.0)]

    # Plug / list
    res2 = node["t"] / [1.0, 2.0, 3.0]
    val = res2.get()[0]
    assert pytest.approx(val[0]) == 10.0
    assert pytest.approx(val[1]) == 10.0
    assert pytest.approx(val[2]) == 10.0

    # Plug / Plug
    node["r"].set([2.0, 4.0, 5.0])
    res3 = node["t"] / node["r"]
    assert res3.get() == [(5.0, 5.0, 6.0)]

    # Reverse: number / Plug
    res4 = 100.0 / node["t"] # (100/10, 100/20, 100/30)
    val4 = res4.get()[0]
    assert pytest.approx(val4[0]) == 10.0
    assert pytest.approx(val4[1]) == 5.0
    assert pytest.approx(val4[2]) == 3.333333

    # Reverse: list / Plug
    res5 = [100.0, 100.0, 100.0] / node["t"]
    val5 = res5.get()[0]
    assert pytest.approx(val5[0]) == 10.0

def test_math_pow_compound_value():
    """Test ** operator for compound attributes."""
    node = Node.create("transform", name="mathPowCompound")
    node["t"].set([2.0, 3.0, 4.0])

    # Plug ** number
    res1 = node["t"] ** 2.0
    assert res1.get() == [(4.0, 9.0, 16.0)]

    # Plug ** list (unsupported by multiplyDivide usually? Wait, multiplyDivide has power operation)
    # Power operation in multiplyDivide: input1 ^ input2 (component wise)

    res2 = node["t"] ** [2.0, 1.0, 0.5]
    val2 = res2.get()[0]
    assert pytest.approx(val2[0]) == 4.0
    assert pytest.approx(val2[1]) == 3.0
    assert pytest.approx(val2[2]) == 2.0 # sqrt(4)

    # Plug ** Plug
    node["r"].set([2.0, 2.0, 2.0])
    res3 = node["t"] ** node["r"]
    assert res3.get() == [(4.0, 9.0, 16.0)]

    # Reverse: number ** Plug
    # 2.0 ** (2,3,4) = (4, 8, 16)
    res4 = 2.0 ** node["t"]
    val4 = res4.get()[0]
    assert pytest.approx(val4[0]) == 4.0
    assert pytest.approx(val4[1]) == 8.0
    assert pytest.approx(val4[2]) == 16.0

    # Reverse: list ** Plug
    # [2, 3, 4] ** (2,2,2) = 2^2, 3^3, 4^4? Wait.
    # [2, 3, 4] (base) ** (2,3,4) (exp from var)
    # Let's test [2,2,2] ** Plug([2,3,4])
    res5 = [2.0, 2.0, 2.0] ** node["t"]
    val5 = res5.get()[0]
    assert pytest.approx(val5[0]) == 4.0
    assert pytest.approx(val5[1]) == 8.0
    assert pytest.approx(val5[2]) == 16.0

def test_math_compound_invalid_operands():
    """Test compound math operations with invalid operands."""
    node = Node.create("transform", name="mathCompoundError")
    plug = node["translate"] # compound

    with pytest.raises(TypeError):
        plug + "string"

    with pytest.raises(TypeError):
        plug - "string"

    with pytest.raises(TypeError):
        plug * "string"

    with pytest.raises(TypeError):
        plug / "string"

    with pytest.raises(TypeError):
        plug ** "string"

def test_math_scalar_invalid_operands():
    """Test scalar math operations with invalid operands (lines 755-760, 861-866, 932-937)."""
    node = Node.create("transform", name="mathScalarError")
    node.add_attr("val", attributeType="double")
    plug = node["val"]  # scalar

    # Reverse ops with string

    # __rsub__
    with pytest.raises(TypeError):
        plug.__rsub__("string")

    # __rtruediv__
    with pytest.raises(TypeError):
        plug.__rtruediv__("string")

    # __rpow__
    with pytest.raises(TypeError):
        plug.__rpow__("string")


def test_reverse_math_compound_with_tuple():
    """Test reverse math ops on compound plugs with valid list/tuple inputs."""
    node = Node.create("transform", name="compoundReverseMath")
    plug = node["translate"]  # compound double3

    # __rsub__ with list/tuple of 3 elements
    result_rsub = plug.__rsub__([10.0, 20.0, 30.0])
    assert isinstance(result_rsub, Plug)
    # Set plug translate to (1, 2, 3) and verify subtraction result
    plug.set([1.0, 2.0, 3.0])
    result_value = result_rsub.get()
    # result_value is [(x, y, z)] for compound attrs, or (x, y, z) for output3D
    # Flatten if nested
    if isinstance(result_value, list) and len(result_value) == 1:
        result_value = result_value[0]
    # [10, 20, 30] - [1, 2, 3] = [9, 18, 27]
    assert result_value[0] == pytest.approx(9.0, rel=1e-6)
    assert result_value[1] == pytest.approx(18.0, rel=1e-6)
    assert result_value[2] == pytest.approx(27.0, rel=1e-6)

    # __rtruediv__ with list/tuple of 3 elements
    node2 = Node.create("transform", name="compoundReverseMath2")
    plug2 = node2["translate"]
    plug2.set([2.0, 4.0, 5.0])
    result_rdiv = plug2.__rtruediv__([10.0, 20.0, 25.0])
    assert isinstance(result_rdiv, Plug)
    result_value = result_rdiv.get()
    if isinstance(result_value, list) and len(result_value) == 1:
        result_value = result_value[0]
    # [10, 20, 25] / [2, 4, 5] = [5, 5, 5]
    assert result_value[0] == pytest.approx(5.0, rel=1e-6)
    assert result_value[1] == pytest.approx(5.0, rel=1e-6)
    assert result_value[2] == pytest.approx(5.0, rel=1e-6)

    # __rpow__ with list/tuple of 3 elements
    node3 = Node.create("transform", name="compoundReverseMath3")
    plug3 = node3["translate"]
    plug3.set([2.0, 3.0, 2.0])
    result_rpow = plug3.__rpow__([2.0, 2.0, 3.0])
    assert isinstance(result_rpow, Plug)
    result_value = result_rpow.get()
    if isinstance(result_value, list) and len(result_value) == 1:
        result_value = result_value[0]
    # [2, 2, 3] ** [2, 3, 2] = [4, 8, 9]
    assert result_value[0] == pytest.approx(4.0, rel=1e-6)
    assert result_value[1] == pytest.approx(8.0, rel=1e-6)
    assert result_value[2] == pytest.approx(9.0, rel=1e-6)


def test_reverse_math_compound_invalid_operand():
    """Test reverse math ops on compound plugs with invalid operands (lines 738-741, 844-847, 914-917)."""
    node = Node.create("transform", name="compoundReverseInvalid")
    plug = node["translate"]  # compound double3

    # __rsub__ with invalid type on compound plug (line 738-741)
    with pytest.raises(TypeError):
        plug.__rsub__("string")

    # __rtruediv__ with invalid type on compound plug (line 844-847)
    with pytest.raises(TypeError):
        plug.__rtruediv__("string")

    # __rpow__ with invalid type on compound plug (line 914-917)
    with pytest.raises(TypeError):
        plug.__rpow__("string")


def test_reverse_math_on_non_numeric_attribute():
    """Test reverse math ops on non-numeric attributes (lines 755-760, 861-866, 932-937)."""
    node = Node.create("transform", name="nonNumericReverseMath")
    node.add_attr("strAttr", dataType="string")
    plug = node["strAttr"]  # string attribute, non-numeric

    # __rsub__ on non-numeric attribute (lines 755-760)
    with pytest.raises(TypeError):
        plug.__rsub__(5.0)

    # __rtruediv__ on non-numeric attribute (lines 861-866)
    with pytest.raises(TypeError):
        plug.__rtruediv__(5.0)

    # __rpow__ on non-numeric attribute (lines 932-937)
    with pytest.raises(TypeError):
        plug.__rpow__(5.0)

def test_mplug_refetch_logic():
    """Test explicit mplug refetching logic."""
    transform = cmds.createNode("transform", name="refetchTest")
    node = Node(cmds.ls(transform, long=True)[0])
    node.add_attr("temp", attributeType="double", keyable=True)
    plug = node["temp"]

    # 1. Force cache population
    assert plug.keyable is True # accesses mplug
    assert plug._mplug is not None

    # 2. Simulate stale plug by assigning a Null MPlug or forcing it
    # We can't easily create a "stale but not null" plug that becomes null.
    # But the code path is: if self._mplug.isNull: refetch.
    # So let's force _mplug to be a Null MPlug (created via default constructor?)
    # OpenMaya.MPlug() creates a null plug? No, constructor needs valid params usually?
    # Actually MPlug() default constructor creates a null plug? Let's try.
    # Or assign checks .isNull property.

    # To hit lines 58-60:
    # if self._mplug.isNull: (TRUE)
    #    self._mplug = self._find_plug()
    #    if self._mplug is None or self._mplug.isNull: (TRUE) -> Raise

    # So we need:
    # 1. Set plug._mplug to something that has .isNull == True.
    # 2. Ensure _find_plug() returns None or Null (e.g. delete attr first).

    # Delete real attribute so _find_plug returns None
    # Better yet, delete the whole node to be absolutely sure _find_plug fails
    cmds.delete(node.name)

    # Manually set _mplug to a dummy object that behaves like Null MPlug
    # so we enter the "if self._mplug.isNull" block.
    class MockNullPlug:
        @property
        def isNull(self):
            return True

    plug._mplug = MockNullPlug()

    # 3. Access again.
    # It checks _mplug.isNull -> True.
    # Calls _find_plug() -> None (since plug/node gone).
    # Checks if None -> raises RuntimeError.

    with pytest.raises(RuntimeError) as excinfo:
        _ = plug.keyable

    assert "acts invalid/deleted" in str(excinfo.value) or "not found" in str(excinfo.value)

def test_explicit_reverse_math_ops():
    """Test explicit calls to reverse math operators to ensure coverage."""
    node = Node.create("transform", name="reverseMath")
    node.add_attr("val", attributeType="double", defaultValue=2.0)
    plug = node["val"]

    # __radd__
    res = plug.__radd__(5.0)
    assert res.get() == 7.0

    # __rmul__
    res = plug.__rmul__(3.0)
    assert res.get() == 6.0

    # __rtruediv__ is already covered by 20.0 / plug, but why not
    res = plug.__rtruediv__(10.0)
    assert res.get() == 5.0

def test_math_raises_typeerror_for_invalid_operands():
    """Test math operators raise TypeError when given invalid inputs."""
    node = Node.create("transform", name="mathError")

    # String is invalid for math
    with pytest.raises(TypeError):
        node["tx"] + "string"

    with pytest.raises(TypeError):
        node["tx"] - "string"

    with pytest.raises(TypeError):
        node["tx"] * "string"

    with pytest.raises(TypeError):
        node["tx"] / "string"

    with pytest.raises(TypeError):
        node["tx"] ** "string"

    with pytest.raises(TypeError):
        node["tx"] % "string"

    # Reverse
    with pytest.raises(TypeError):
        "string" + node["tx"]
        # Actually this might raise TypeError from python string side first,
        # or fall into __radd__ which raises it.
        # But string + Plug calls Plug.__radd__ if string doesn't handle Plug.
        # String concat might try? "string" + object -> error.
        # But generally we want to ensure our code raises it if called.
        node["tx"].__radd__("string")

    with pytest.raises(TypeError):
         node["tx"].__rsub__("string")

    with pytest.raises(TypeError):
        node["tx"].__rmul__("string")

    with pytest.raises(TypeError):
        node["tx"].__rtruediv__("string")

    with pytest.raises(TypeError):
        node["tx"].__rpow__("string")

    with pytest.raises(TypeError):
        node["tx"].__rmod__("string")

def test_math_unsupported_ops_on_unsupported_attribute_types():
    """Test that math operations raise TypeError on non-numeric attributes."""
    node = Node.create("transform", name="mathTypeCheck")
    node.add_attr("strAttr", dataType="string")

    plug = node["strAttr"]

    with pytest.raises(TypeError):
        plug + 1

    with pytest.raises(TypeError):
        plug - 1

    with pytest.raises(TypeError):
        plug * 1

    with pytest.raises(TypeError):
        plug / 1

    with pytest.raises(TypeError):
        plug ** 1


# === Tests for floatMath fallback paths (Maya < 2025 compatibility) ===


class TestFloatMathFallbackPaths:
    """Tests for floatMath fallback code paths used in Maya < 2025.

    These tests mock uses_native_math_nodes to return False to cover
    the floatMath code paths that would otherwise only run in older Maya.
    """

    def test_subtract_uses_floatmath_when_native_unavailable(self):
        """Test __sub__ uses floatMath node when native subtract unavailable."""
        from unittest.mock import patch, PropertyMock

        node = Node.create("transform", name="subFloatMath")
        node["tx"].value = 10.0

        # Mock uses_native_math_nodes to return False
        with patch.object(
            type(NodeNames), "uses_native_math_nodes", new_callable=PropertyMock
        ) as mock_native:
            mock_native.return_value = False
            result = node["tx"] - 3.0

        # Verify floatMath node was created
        assert "floatMath" in result._node.type
        # Verify operation is set to 1 (subtract)
        assert cmds.getAttr(f"{result._node.name}.operation") == 1
        # Verify the result value
        assert pytest.approx(result.value, rel=1e-5) == 7.0

    def test_subtract_plug_uses_floatmath_when_native_unavailable(self):
        """Test __sub__ with Plug operand uses floatMath when native unavailable."""
        from unittest.mock import patch, PropertyMock

        node_a = Node.create("transform", name="subFloatMathA")
        node_b = Node.create("transform", name="subFloatMathB")
        node_a["tx"].value = 15.0
        node_b["tx"].value = 5.0

        with patch.object(
            type(NodeNames), "uses_native_math_nodes", new_callable=PropertyMock
        ) as mock_native:
            mock_native.return_value = False
            result = node_a["tx"] - node_b["tx"]

        assert "floatMath" in result._node.type
        assert pytest.approx(result.value, rel=1e-5) == 10.0

    def test_divide_uses_floatmath_when_native_unavailable(self):
        """Test __truediv__ uses floatMath node when native divide unavailable."""
        from unittest.mock import patch, PropertyMock

        node = Node.create("transform", name="divFloatMath")
        node["tx"].value = 20.0

        with patch.object(
            type(NodeNames), "uses_native_math_nodes", new_callable=PropertyMock
        ) as mock_native:
            mock_native.return_value = False
            result = node["tx"] / 4.0

        # Verify floatMath node was created
        assert "floatMath" in result._node.type
        # Verify operation is set to 3 (divide)
        assert cmds.getAttr(f"{result._node.name}.operation") == 3
        assert pytest.approx(result.value, rel=1e-5) == 5.0

    def test_divide_plug_uses_floatmath_when_native_unavailable(self):
        """Test __truediv__ with Plug operand uses floatMath when native unavailable."""
        from unittest.mock import patch, PropertyMock

        node_a = Node.create("transform", name="divFloatMathA")
        node_b = Node.create("transform", name="divFloatMathB")
        node_a["tx"].value = 30.0
        node_b["tx"].value = 6.0

        with patch.object(
            type(NodeNames), "uses_native_math_nodes", new_callable=PropertyMock
        ) as mock_native:
            mock_native.return_value = False
            result = node_a["tx"] / node_b["tx"]

        assert "floatMath" in result._node.type
        assert pytest.approx(result.value, rel=1e-5) == 5.0

    def test_rsub_scalar_uses_floatmath_when_native_unavailable(self):
        """Test __rsub__ (scalar - plug) uses floatMath when native unavailable."""
        from unittest.mock import patch, PropertyMock

        node = Node.create("transform", name="rsubFloatMath")
        node["tx"].value = 3.0

        with patch.object(
            type(NodeNames), "uses_native_math_nodes", new_callable=PropertyMock
        ) as mock_native:
            mock_native.return_value = False
            # 10.0 - plug (rsub)
            result = 10.0 - node["tx"]

        assert "floatMath" in result._node.type
        assert cmds.getAttr(f"{result._node.name}.operation") == 1
        assert pytest.approx(result.value, rel=1e-5) == 7.0

    def test_rtruediv_scalar_uses_floatmath_when_native_unavailable(self):
        """Test __rtruediv__ (scalar / plug) uses floatMath when native unavailable."""
        from unittest.mock import patch, PropertyMock

        node = Node.create("transform", name="rdivFloatMath")
        node["tx"].value = 5.0

        with patch.object(
            type(NodeNames), "uses_native_math_nodes", new_callable=PropertyMock
        ) as mock_native:
            mock_native.return_value = False
            # 20.0 / plug (rtruediv)
            result = 20.0 / node["tx"]

        assert "floatMath" in result._node.type
        assert cmds.getAttr(f"{result._node.name}.operation") == 3
        assert pytest.approx(result.value, rel=1e-5) == 4.0
