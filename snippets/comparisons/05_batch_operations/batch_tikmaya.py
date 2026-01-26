"""
Batch Operations - tik.maya approach
====================================
This example demonstrates batch processing of nodes and attributes
using tik.maya's pythonic API.

Key advantages:
- Property access is more readable
- Object-oriented iteration
- Cleaner parent/child traversal
- Returns wrapped objects that can be used directly

Run this in Maya's Script Editor to see the results.
"""
import tik.maya as tm
from tik.maya.core import benchmark


def setup_scene_tikmaya():
    """Create a test scene with many nodes."""

    # Create a bunch of transforms
    transforms = []
    for index in range(50):
        trans = tm.createNode("transform", name=f"transform_{index:03d}")
        transforms.append(trans)
        trans.translate_x = index * 0.5
        trans.translate_y = index * 0.3
        trans.rotate_z = index * 5

    # Create some joints
    tm.select(clear=True)
    joints = []
    for index in range(20):
        jnt = tm.joint(position=(index * 2, 0, 0), name=f"joint_{index:03d}")
        joints.append(jnt)

    return transforms, joints


def batch_query_tikmaya():
    """Query attributes from all transforms in scene."""
    transforms, joints = setup_scene_tikmaya()

    # Query all translate values - the tik.maya way
    # Using property access - much cleaner!
    results = []
    for trans in transforms:
        # translate property returns MVector - even more powerful!
        translation = trans.translate
        results.append((translation.x, translation.y, translation.z))

    return results


def batch_modify_tikmaya():
    """Modify attributes on multiple nodes."""
    transforms, joints = setup_scene_tikmaya()

    # Lock and hide attributes on all transforms
    for trans in transforms:
        for attr in ["scaleX", "scaleY", "scaleZ"]:
            trans[attr].locked = True
            trans[attr].keyable = False

        # Set visibility based on index - cleaner string parsing
        index = int(trans.name.split("_")[-1])
        if index % 2 == 0:
            trans.visibility = False

    return transforms


def batch_connect_tikmaya():
    """Create connections between many nodes."""

    # Create source and target pairs
    sources = []
    targets = []
    for index in range(30):
        src = tm.createNode("transform", name=f"source_{index:03d}")
        tgt = tm.createNode("transform", name=f"target_{index:03d}")
        sources.append(src)
        targets.append(tgt)

    # Connect them all using >> operator - more intuitive!
    for src, tgt in zip(sources, targets):
        src["translate"] >> tgt["translate"]
        src["rotate"] >> tgt["rotate"]

    return sources, targets


def find_and_process_tikmaya():
    """Find specific node types and process them."""
    transforms, joints = setup_scene_tikmaya()

    # Find all joints in the scene - returns wrapped objects!
    all_joints = tm.ls(type="joint")

    # Process each joint
    for jnt in all_joints:
        # Get world position - built-in property!
        world_pos = jnt.world_translation

        # Get parent - property access returns wrapped node
        parent = jnt.parent

        # Set radius based on hierarchy depth
        # Notice: parent property makes this much cleaner
        depth = 0
        current = jnt
        while current.parent is not None:
            current = current.parent
            depth += 1

        jnt["radius"].value = 1.0 / (depth + 1)

    return all_joints


def demonstrate_hierarchy_traversal():
    """Show off tik.maya's hierarchy traversal capabilities."""

    # Create a hierarchy
    root = tm.createNode("transform", name="root")

    children = []
    for index in range(5):
        child = tm.createNode("transform", name=f"child_{index}")
        child.parent = root
        children.append(child)

        # Create grandchildren
        for sub_idx in range(3):
            grandchild = tm.createNode("transform", name=f"grandchild_{index}_{sub_idx}")
            grandchild.parent = child

    # Now demonstrate traversal
    print("\n--- Hierarchy Traversal Demo ---")
    print(f"Root: {root.name}")
    print(f"Children: {[child.name for child in root.children]}")

    # Get all descendants using collect_hierarchy
    all_transforms = root.collect_hierarchy(node_types=["transform"], include_self=True)
    print(f"All transforms in hierarchy: {len(all_transforms)}")

    # Property access makes parent/child relationships clear
    some_grandchild = children[0].children[0]
    print(f"\nGrandchild: {some_grandchild.name}")
    print(f"Parent: {some_grandchild.parent.name}")
    print(f"Grandparent: {some_grandchild.parent.parent.name}")


def run_benchmark(iterations=20):
    """Run the benchmark and report timing."""
    bm = benchmark.MayaBenchmark()
    bm.measure("batch_query_tikmaya", iterations=iterations, new_scene=True).run(
        batch_query_tikmaya)
    bm.measure("batch_modify_tikmaya", iterations=iterations, new_scene=True).run(
        batch_modify_tikmaya)
    bm.measure("batch_connect_tikmaya", iterations=iterations, new_scene=True).run(
        batch_connect_tikmaya)
    bm.measure("find_and_process_tikmaya", iterations=iterations, new_scene=True).run(
        find_and_process_tikmaya)

    # Bonus demonstration
    demonstrate_hierarchy_traversal()


if __name__ == "__main__":
    run_benchmark()

