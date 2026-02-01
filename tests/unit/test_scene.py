import pytest
from maya import cmds
from tik.maya.core.scene import (
    list_scene_nodes,
    select_nodes,
    _clean_input,
    _wrap_output,
    proxy_wrapper,
)
from tik.maya.types.transform import Transform

def test_list_scene_nodes_returns_wrappers():
    # Setup
    cmds.file(new=True, force=True)
    t1 = cmds.createNode("transform", name="testT1")
    t2 = cmds.createNode("transform", name="testT2")

    # Execute
    nodes = list_scene_nodes(type="transform")

    # Verify
    # Note: Maya creates default cameras and other transforms, so we filter by our names
    our_nodes = [n for n in nodes if n.name in ["testT1", "testT2"]]
    assert len(our_nodes) == 2
    assert all(isinstance(n, Transform) for n in our_nodes)
    assert {n.name for n in our_nodes} == {"testT1", "testT2"}

def test_list_scene_nodes_passes_args_to_cmds_ls():
    # Setup
    cmds.file(new=True, force=True)
    t1 = cmds.createNode("transform", name="selectedT")
    cmds.select(t1)

    # Execute: list selected
    nodes = list_scene_nodes(selection=True)

    # Verify
    assert len(nodes) == 1
    assert nodes[0].name == "selectedT"
    assert isinstance(nodes[0], Transform)

# def test_select_nodes_selects_given_nodes():
#     # Setup
#     cmds.file(new=True, force=True)
#     t1 = cmds.createNode("transform", name="selectMe1")
#     t2 = cmds.createNode("transform", name="selectMe2")
#
#     # Create wrappers
#     n1 = Transform(t1)
#     n2 = Transform(t2)
#
#     # Execute
#     select_nodes([n1, n2])
#
#     # Verify
#     selection = cmds.ls(selection=True)
#     assert len(selection) == 2
#     assert set(selection) == {"selectMe1", "selectMe2"}

# def test_select_nodes_passes_kwargs_to_cmds_select():
#     # Setup
#     cmds.file(new=True, force=True)
#     t1 = cmds.createNode("transform", name="first")
#     t2 = cmds.createNode("transform", name="second")
#
#     cmds.select(t1)
#
#     # Execute: add to selection
#     n2 = Transform(t2)
#     select_nodes([n2], add=True)
#
#     # Verify
#     selection = cmds.ls(selection=True)
#     assert len(selection) == 2
#     assert set(selection) == {"first", "second"}

# def test_select_nodes_handles_mixed_input():
#     # Setup
#     cmds.file(new=True, force=True)
#     t1 = cmds.createNode("transform", name="nodeA")
#     t2 = cmds.createNode("transform", name="nodeB")
#
#     n1 = Transform(t1)
#
#     # Execute: pass wrapper and string
#     select_nodes([n1, "nodeB"])
#
#     # Verify
#     selection = cmds.ls(selection=True)
#     assert len(selection) == 2
#     assert set(selection) == {"nodeA", "nodeB"}


def test_create_node_dag():
    from tik.maya.core.scene import create_node
    # Test creating a DAG node (transform)
    node = create_node("transform", name="myDag")
    assert node.exists()
    assert node.type == "transform"
    assert node.name == "myDag"


def test_create_node_dg():
    # make sure the factory default is set
    import tik.maya as tm
    # from tik.maya.core.scene import create_node
    # Test creating a DG node (multiplyDivide)
    # create_node_with_dag_modifier should fail (invalid node type for DAG mod?)
    # multiplyDivide is DG. MDagModifier.createNode MAY fail or create?
    # MDagModifier.createNode("multiplyDivide") raises TypeError: invalid node type
    # So it should fall back to create_node_with_dg_modifier.
    node = tm.create_node("multiplyDivide", name="myDG")
    assert node.exists()
    assert node.type == "multiplyDivide"
    assert node.name == "myDG"


def test_create_node_with_parent():
    from tik.maya.core.scene import create_node
    parent = create_node("transform", name="parentGrp")
    child = create_node("transform", name="childNode", parent=parent)

    assert child.parent.uuid == parent.uuid


def test_create_node_fallback_to_unknown_with_name():
    import tik.maya as tm
    # "invalidType_XYZ" fails DAG and DG modifiers, falls back to cmds.createNode.
    # We provide a name to test that kwargs are passed correctly in fallback.
    node = tm.create_node("invalidType_XYZ", name="unknownNode")
    assert node.exists()
    assert node.type == "unknown"
    assert node.name == "unknownNode"


# === Tests for _clean_input helper ===


def test_clean_input_with_node_object():
    """Test _clean_input converts tik objects to strings."""
    cmds.file(new=True, force=True)
    transform_name = cmds.createNode("transform", name="cleanInputTest")
    node = Transform(transform_name)
    result = _clean_input(node)
    assert result == "cleanInputTest"


def test_clean_input_with_list():
    """Test _clean_input recursively processes lists."""
    cmds.file(new=True, force=True)
    transform_name = cmds.createNode("transform", name="listNode")
    node = Transform(transform_name)
    result = _clean_input([node, "stringVal", 123])
    assert result == ["listNode", "stringVal", 123]


def test_clean_input_with_tuple():
    """Test _clean_input recursively processes tuples."""
    cmds.file(new=True, force=True)
    transform_name = cmds.createNode("transform", name="tupleNode")
    node = Transform(transform_name)
    result = _clean_input((node, "val"))
    assert result == ["tupleNode", "val"]


def test_clean_input_with_dict():
    """Test _clean_input recursively processes dictionaries."""
    cmds.file(new=True, force=True)
    transform_name = cmds.createNode("transform", name="dictNode")
    node = Transform(transform_name)
    result = _clean_input({"key": node, "other": "value"})
    assert result == {"key": "dictNode", "other": "value"}


def test_clean_input_with_primitive():
    """Test _clean_input passes through primitives unchanged."""
    assert _clean_input(42) == 42
    assert _clean_input("string") == "string"
    assert _clean_input(3.14) == 3.14


# === Tests for _wrap_output helper ===


def test_wrap_output_with_string():
    """Test _wrap_output resolves string to tik object."""
    cmds.file(new=True, force=True)
    transform_name = cmds.createNode("transform", name="wrapOutputTest")
    result = _wrap_output(transform_name)
    assert isinstance(result, Transform)
    assert result.name == "wrapOutputTest"


def test_wrap_output_with_list():
    """Test _wrap_output recursively processes lists."""
    cmds.file(new=True, force=True)
    cmds.createNode("transform", name="wrapList1")
    cmds.createNode("transform", name="wrapList2")
    result = _wrap_output(["wrapList1", "wrapList2"])
    assert len(result) == 2
    assert all(isinstance(item, Transform) for item in result)


def test_wrap_output_with_non_string():
    """Test _wrap_output passes through non-string values unchanged."""
    assert _wrap_output(None) is None
    assert _wrap_output(42) == 42


# === Tests for _proxy_wrapper ===


def test_proxy_wrapper_basic_command():
    """Test _proxy_wrapper executes Maya commands correctly."""
    cmds.file(new=True, force=True)
    # Use a non-factory command to test basic wrapping
    result = proxy_wrapper("ls")
    # Should return raw result for non-factory commands
    assert isinstance(result, (list, type(None)))


def test_proxy_wrapper_with_factory_command():
    """Test _proxy_wrapper wraps output for factory commands."""
    cmds.file(new=True, force=True)
    # Create a transform first, then use duplicate which is in NODE_FACTORIES
    cmds.createNode("transform", name="originalNode")
    result = proxy_wrapper("duplicate", "originalNode", name="duplicatedNode")
    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], Transform)


# === Tests for select_nodes ===


def test_select_nodes_selects_given_nodes():
    """Test select_nodes selects the given tik node objects."""
    cmds.file(new=True, force=True)
    transform1 = cmds.createNode("transform", name="selectMe1")
    transform2 = cmds.createNode("transform", name="selectMe2")

    node1 = Transform(transform1)
    node2 = Transform(transform2)

    select_nodes([node1, node2])

    selection = cmds.ls(selection=True)
    assert len(selection) == 2
    assert set(selection) == {"selectMe1", "selectMe2"}


def test_select_nodes_passes_kwargs():
    """Test select_nodes passes kwargs to cmds.select."""
    cmds.file(new=True, force=True)
    transform1 = cmds.createNode("transform", name="first")
    transform2 = cmds.createNode("transform", name="second")

    cmds.select(transform1)
    node2 = Transform(transform2)

    # Use add=True to add to existing selection
    select_nodes([node2], add=True)

    selection = cmds.ls(selection=True)
    assert len(selection) == 2
    assert set(selection) == {"first", "second"}


def test_select_nodes_handles_mixed_input():
    """Test select_nodes handles mixed tik objects and strings."""
    cmds.file(new=True, force=True)
    transform1 = cmds.createNode("transform", name="nodeA")
    cmds.createNode("transform", name="nodeB")

    node1 = Transform(transform1)

    # Pass wrapper and string
    select_nodes([node1, "nodeB"])

    selection = cmds.ls(selection=True)
    assert len(selection) == 2
    assert set(selection) == {"nodeA", "nodeB"}

