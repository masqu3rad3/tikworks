"""
Twist Joint Setup - maya.cmds approach
======================================
This example creates a twist joint chain driven by math nodes.

Scenario: Distribute rotation from a control across multiple joints
(common for forearm twist, spine twist, etc.)

The twist is distributed with falloff - joints closer to the
twist source get more rotation.

Run this in Maya's Script Editor to see the results.
"""
from maya import cmds
from tik.maya.core import benchmark


def create_twist_joints_cmds(joint_count=5):
    """Create a twist joint chain with rotation distribution using maya.cmds."""

    # ========================================
    # CREATE BASE JOINTS
    # ========================================
    cmds.select(clear=True)

    base_joint = cmds.joint(position=(0, 0, 0), name="twist_base_JNT")

    twist_joints = []
    spacing = 2.0
    for index in range(joint_count):
        cmds.select(clear=True)
        joint = cmds.joint(
            position=(spacing * (index + 1), 0, 0),
            name=f"twist_{index:02d}_JNT"
        )
        twist_joints.append(joint)

    end_joint = cmds.joint(
        position=(spacing * (joint_count + 1), 0, 0),
        name="twist_end_JNT"
    )

    # ========================================
    # CREATE CONTROLS
    # ========================================
    base_ctrl = cmds.circle(name="base_CTRL", normal=(1, 0, 0), radius=1.5)[0]
    cmds.matchTransform(base_ctrl, base_joint)

    end_ctrl = cmds.circle(name="end_CTRL", normal=(1, 0, 0), radius=1.5)[0]
    cmds.matchTransform(end_ctrl, end_joint)

    # Connect controls to base/end joints
    cmds.connectAttr(f"{base_ctrl}.rotate", f"{base_joint}.rotate")
    cmds.connectAttr(f"{end_ctrl}.rotate", f"{end_joint}.rotate")

    # ========================================
    # BUILD TWIST DISTRIBUTION NETWORK
    # ========================================
    # Each twist joint gets a weighted blend between base and end rotation
    # Weight is based on position (linear falloff)

    for index, joint in enumerate(twist_joints):
        # Calculate weight (0 = fully base, 1 = fully end)
        weight = (index + 1) / (joint_count + 1)
        inverse_weight = 1.0 - weight

        # For each rotation axis, we need to blend
        for axis in ["X", "Y", "Z"]:
            # Multiply base rotation by inverse weight
            base_mult = cmds.createNode(
                "multiplyDivide",
                name=f"twist{index:02d}_{axis}_baseMult"
            )
            cmds.setAttr(f"{base_mult}.operation", 1)  # Multiply
            cmds.connectAttr(f"{base_ctrl}.rotate{axis}", f"{base_mult}.input1X")
            cmds.setAttr(f"{base_mult}.input2X", inverse_weight)

            # Multiply end rotation by weight
            end_mult = cmds.createNode(
                "multiplyDivide",
                name=f"twist{index:02d}_{axis}_endMult"
            )
            cmds.setAttr(f"{end_mult}.operation", 1)  # Multiply
            cmds.connectAttr(f"{end_ctrl}.rotate{axis}", f"{end_mult}.input1X")
            cmds.setAttr(f"{end_mult}.input2X", weight)

            # Add them together
            add_node = cmds.createNode(
                "plusMinusAverage",
                name=f"twist{index:02d}_{axis}_add"
            )
            cmds.setAttr(f"{add_node}.operation", 1)  # Sum
            cmds.connectAttr(f"{base_mult}.outputX", f"{add_node}.input1D[0]")
            cmds.connectAttr(f"{end_mult}.outputX", f"{add_node}.input1D[1]")

            # Connect to joint
            cmds.connectAttr(f"{add_node}.output1D", f"{joint}.rotate{axis}")

    # Count nodes created
    # Per joint: 3 axes × 3 nodes = 9 nodes
    # Total: joint_count × 9 nodes
    total_nodes = joint_count * 9

    return base_ctrl, end_ctrl, twist_joints


def run_benchmark(iterations=30):
    """Run the benchmark and report timing."""
    bm = benchmark.MayaBenchmark()
    bm.measure("create_twist_joints_cmds", iterations=iterations, new_scene=True).run(
        create_twist_joints_cmds)


if __name__ == "__main__":
    run_benchmark()

