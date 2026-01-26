import pytest
from maya import cmds
# from tik.maya.core.scene import list_scene_nodes, select_nodes
from tik.maya.core.scene import list_scene_nodes
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


