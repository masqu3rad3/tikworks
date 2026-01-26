"""
Batch Operations - maya.cmds approach
=====================================
This example demonstrates batch processing of nodes and attributes,
a common task in rigging and pipeline tools.

Scenarios:
1. Querying attributes from multiple nodes
2. Setting attributes on multiple nodes
3. Finding and processing specific node types
4. Building connections across many nodes

Run this in Maya's Script Editor to see the results.
"""
from maya import cmds
from tik.maya.core import benchmark


def setup_scene_cmds():
    """Create a test scene with many nodes."""

    # Create a bunch of transforms
    transforms = []
    for index in range(50):
        trans = cmds.createNode("transform", name=f"transform_{index:03d}")
        transforms.append(trans)
        cmds.setAttr(f"{trans}.translateX", index * 0.5)
        cmds.setAttr(f"{trans}.translateY", index * 0.3)
        cmds.setAttr(f"{trans}.rotateZ", index * 5)

    # Create some joints
    cmds.select(clear=True)
    joints = []
    for index in range(20):
        jnt = cmds.joint(position=(index * 2, 0, 0), name=f"joint_{index:03d}")
        joints.append(jnt)

    return transforms, joints


def batch_query_cmds():
    """Query attributes from all transforms in scene."""
    transforms, joints = setup_scene_cmds()

    # Query all translate values - the cmds way
    results = []
    for trans in transforms:
        translate_x = cmds.getAttr(f"{trans}.translateX")
        translate_y = cmds.getAttr(f"{trans}.translateY")
        translate_z = cmds.getAttr(f"{trans}.translateZ")
        results.append((translate_x, translate_y, translate_z))

    return results


def batch_modify_cmds():
    """Modify attributes on multiple nodes."""
    transforms, joints = setup_scene_cmds()

    # Lock and hide attributes on all transforms
    for trans in transforms:
        for attr in ["scaleX", "scaleY", "scaleZ"]:
            cmds.setAttr(f"{trans}.{attr}", lock=True)
            cmds.setAttr(f"{trans}.{attr}", keyable=False, channelBox=False)

        # Set visibility based on index
        index = int(trans.split("_")[-1])
        if index % 2 == 0:
            cmds.setAttr(f"{trans}.visibility", 0)

    return transforms


def batch_connect_cmds():
    """Create connections between many nodes."""

    # Create source and target pairs
    sources = []
    targets = []
    for index in range(30):
        src = cmds.createNode("transform", name=f"source_{index:03d}")
        tgt = cmds.createNode("transform", name=f"target_{index:03d}")
        sources.append(src)
        targets.append(tgt)

    # Connect them all
    for src, tgt in zip(sources, targets):
        cmds.connectAttr(f"{src}.translate", f"{tgt}.translate")
        cmds.connectAttr(f"{src}.rotate", f"{tgt}.rotate")

    return sources, targets


def find_and_process_cmds():
    """Find specific node types and process them."""
    transforms, joints = setup_scene_cmds()

    # Find all joints in the scene
    all_joints = cmds.ls(type="joint")

    # Process each joint
    for jnt in all_joints:
        # Get world position
        world_pos = cmds.xform(jnt, query=True, worldSpace=True, translation=True)

        # Get parent
        parent = cmds.listRelatives(jnt, parent=True)

        # Set radius based on hierarchy depth
        depth = 0
        current = jnt
        while True:
            parent = cmds.listRelatives(current, parent=True)
            if not parent:
                break
            current = parent[0]
            depth += 1

        cmds.setAttr(f"{jnt}.radius", 1.0 / (depth + 1))

    return all_joints


def run_benchmark(iterations=20):
    """Run the benchmark and report timing."""
    bm = benchmark.MayaBenchmark()
    bm.measure("batch_query_cmds", iterations=iterations, new_scene=True).run(
        batch_query_cmds)
    bm.measure("batch_modify_cmds", iterations=iterations, new_scene=True).run(
        batch_modify_cmds)
    bm.measure("batch_connect_cmds", iterations=iterations, new_scene=True).run(
        batch_connect_cmds)
    bm.measure("find_and_process_cmds", iterations=iterations, new_scene=True).run(
        find_and_process_cmds)


if __name__ == "__main__":
    run_benchmark()

