"""
Joint Chain Creation - tik.maya approach
========================================
This example demonstrates creating and manipulating a joint chain
using tik.maya's pythonic API.

Notice:
- Property access instead of getAttr/setAttr
- No string concatenation for attribute paths
- Clean parent/child traversal
- Object-oriented approach

Run this in Maya's Script Editor to see the timing results.
"""
import tik.maya as tm
from tik.maya.core import benchmark


def create_joint_chain_tikmaya():
    """Create a joint chain and modify its properties using tik.maya."""

    # Create joints
    # tm.select(clear=True)
    joints = []
    for index in range(5):
        joint = tm.Joint.create(
            position = (0, index * 2, 0),
            name = f"spine_{index:02d}_JNT"
        )
        joints.append(joint)

    for joint in joints:
        # Get translation as a property - returns MVector!
        translation = joint.translate

        # Set display size using bracket notation for any attribute
        joint.radius = 0.5

        # Visibility is a built-in property
        is_visible = joint.visibility
        joint.visibility = True

        # Lock attributes with clean syntax
        for attr in "XYZ":
            joint[f"translate{attr}"].lock()

    # Get parent/child relationships - property access!
    for joint in joints[1:]:
        parent = joint.parent  # Returns wrapped node or None
        if parent:
            parent_name = parent.name

    return joints


def run_benchmark(iterations=100):
    """Run the benchmark and report timing."""
    bm = benchmark.MayaBenchmark()
    bm.measure("create_joint_chain_tikmaya", iterations=iterations, new_scene=True).run(
        create_joint_chain_tikmaya)


if __name__ == "__main__":
    run_benchmark()

