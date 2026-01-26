"""
Joint Chain Creation - maya.cmds approach
=========================================
This example demonstrates creating and manipulating a joint chain
using traditional maya.cmds API.

Run this in Maya's Script Editor to see the timing results.






"""
from maya import cmds
from tik.maya.core import benchmark

def create_joint_chain_cmds():
    """Create a joint chain and modify its properties using maya.cmds."""

    # Create joints
    cmds.select(clear=True)
    joints = []
    for index in range(5):
        joint = cmds.joint(
            position=(0, index * 2, 0),
            name=f"spine_{index:02d}_JNT"
        )
        joints.append(joint)

    for joint in joints:
        # Get current translation
        translation = cmds.getAttr(f"{joint}.translate")[0]

        # Set display size
        cmds.setAttr(f"{joint}.radius", 0.5)

        # Get/set visibility
        is_visible = cmds.getAttr(f"{joint}.visibility")
        cmds.setAttr(f"{joint}.visibility", True)

        # Lock attributes
        for attr in "XYZ":
            cmds.setAttr(f"{joint}.translate{attr}", lock=True)

    # Get parent/child relationships
    for joint in joints[1:]:
        parent = cmds.listRelatives(joint, parent=True)
        if parent:
            parent_name = parent[0]

    return joints


def run_benchmark(iterations=100):
    """Run the benchmark and report timing."""
    bm = benchmark.MayaBenchmark()
    bm.measure("create_joint_chain_cmds", iterations=iterations, new_scene=True).run(
        create_joint_chain_cmds)



if __name__ == "__main__":
    run_benchmark()
