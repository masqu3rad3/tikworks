"""
Twist Joint Setup - tik.maya approach
=====================================
This example creates a twist joint chain driven by math nodes.

With tik.maya, the mathematical blend formula becomes readable code!

The formula: joint_rotation = base_rotation * (1 - weight) + end_rotation * weight
becomes: (base["rotate"] * (1 - weight)) + (end["rotate"] * weight)

Run this in Maya's Script Editor to see the results.
"""
import tik.maya as tm
from tik.maya.core import benchmark


def create_twist_joints_tikmaya(joint_count=5):
    """Create a twist joint chain with rotation distribution using tik.maya."""

    # ========================================
    # CREATE BASE JOINTS
    # ========================================
    tm.select(clear=True)

    base_joint = tm.joint(position=(0, 0, 0), name="twist_base_JNT")

    twist_joints = []
    spacing = 2.0
    for index in range(joint_count):
        tm.select(clear=True)
        joint = tm.joint(
            position=(spacing * (index + 1), 0, 0),
            name=f"twist_{index:02d}_JNT"
        )
        twist_joints.append(joint)

    end_joint = tm.joint(
        position=(spacing * (joint_count + 1), 0, 0),
        name="twist_end_JNT"
    )

    # ========================================
    # CREATE CONTROLS
    # ========================================
    base_ctrl = tm.circle(name="base_CTRL", normal=(1, 0, 0), radius=1.5)[0]
    tm.matchTransform(base_ctrl, base_joint)

    end_ctrl = tm.circle(name="end_CTRL", normal=(1, 0, 0), radius=1.5)[0]
    tm.matchTransform(end_ctrl, end_joint)

    # Connect controls to base/end joints
    base_ctrl["rotate"] >> base_joint["rotate"]
    end_ctrl["rotate"] >> end_joint["rotate"]

    # ========================================
    # BUILD TWIST DISTRIBUTION NETWORK
    # ========================================
    # formula: result = base * (1 - weight) + end * weight

    for index, joint in enumerate(twist_joints):
        weight = (index + 1) / (joint_count + 1)

        # Per-axis blending with mathematical operators
        for axis in ["X", "Y", "Z"]:
            base_rot = base_ctrl[f"rotate{axis}"]
            end_rot = end_ctrl[f"rotate{axis}"]

            # entire blend in one line
            blended = (base_rot * (1.0 - weight)) + (end_rot * weight)
            blended >> joint[f"rotate{axis}"]

    return base_ctrl, end_ctrl, twist_joints


def create_twist_joints_compound(joint_count=5):
    """A bit more elegant: Use compound attribute math.

    This version operates on the entire rotate compound attribute
    instead of individual axes.
    """

    # Create joints
    tm.select(clear=True)
    base_joint = tm.joint(position=(0, 0, 0), name="twist_base_JNT")

    twist_joints = []
    spacing = 2.0
    for index in range(joint_count):
        tm.select(clear=True)
        joint = tm.joint(
            position=(spacing * (index + 1), 0, 0),
            name=f"twist_{index:02d}_JNT"
        )
        twist_joints.append(joint)

    end_joint = tm.joint(
        position=(spacing * (joint_count + 1), 0, 0),
        name="twist_end_JNT"
    )

    # Create controls
    base_ctrl = tm.circle(name="base_CTRL", normal=(1, 0, 0), radius=1.5)[0]
    tm.matchTransform(base_ctrl, base_joint)

    end_ctrl = tm.circle(name="end_CTRL", normal=(1, 0, 0), radius=1.5)[0]
    tm.matchTransform(end_ctrl, end_joint)

    base_ctrl["rotate"] >> base_joint["rotate"]
    end_ctrl["rotate"] >> end_joint["rotate"]

    # Build twist network - COMPOUND VERSION
    # Operating on double3/float3 attributes creates vector math nodes!
    for index, joint in enumerate(twist_joints):
        weight = (index + 1) / (joint_count + 1)

        # This creates multiplyDivide and plusMinusAverage nodes
        # that operate on all three components at once
        blended = (base_ctrl["rotate"] * (1.0 - weight)) + (end_ctrl["rotate"] * weight)
        blended >> joint["rotate"]

    return base_ctrl, end_ctrl, twist_joints


def run_benchmark(iterations=30):
    """Run the benchmark and report timing."""
    bm = benchmark.MayaBenchmark()
    bm.measure("create_twist_joints_cmds", iterations=iterations, new_scene=True).run(
        create_twist_joints_tikmaya)

    bm.measure("create_twist_joints_compound", iterations=iterations, new_scene=True).run(
        create_twist_joints_compound)


if __name__ == "__main__":
    run_benchmark()

