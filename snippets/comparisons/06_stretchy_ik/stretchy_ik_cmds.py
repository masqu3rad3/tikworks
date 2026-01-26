"""
Stretchy IK Setup - maya.cmds approach
======================================
This is a REAL rigging scenario: Creating a stretchy IK limb.

The math involved:
1. Calculate distance between two points
2. Compare current distance to default distance
3. Apply stretch factor only when limb is extended beyond default
4. Optionally blend between stretchy and non-stretchy behavior

This example shows how verbose cmds becomes for math-heavy setups.

Run this in Maya's Script Editor to see the results.
"""
from maya import cmds
from tik.maya.core import benchmark


def create_stretchy_ik_cmds():
    """Create a stretchy two-bone IK chain using maya.cmds."""

    # ========================================
    # CREATE THE SKELETON
    # ========================================
    cmds.select(clear=True)
    shoulder = cmds.joint(position=(0, 10, 0), name="shoulder_JNT")
    elbow = cmds.joint(position=(5, 10, -1), name="elbow_JNT")
    wrist = cmds.joint(position=(10, 10, 0), name="wrist_JNT")

    # Orient joints
    cmds.joint(shoulder, edit=True, orientJoint="xyz",
               secondaryAxisOrient="yup", children=True)

    # Get default bone lengths
    upper_length = cmds.getAttr(f"{elbow}.translateX")
    lower_length = cmds.getAttr(f"{wrist}.translateX")
    total_length = upper_length + lower_length

    # ========================================
    # CREATE IK HANDLE
    # ========================================
    ik_handle, effector = cmds.ikHandle(
        startJoint=shoulder,
        endEffector=wrist,
        solver="ikRPsolver",
        name="arm_IKH"
    )

    # ========================================
    # CREATE CONTROL
    # ========================================
    ik_ctrl = cmds.circle(name="IK_CTRL", normal=(1, 0, 0), radius=1)[0]
    cmds.matchTransform(ik_ctrl, wrist)
    cmds.makeIdentity(ik_ctrl, apply=True, translate=True, rotate=True)
    cmds.parent(ik_handle, ik_ctrl)

    # Add stretch attribute
    cmds.addAttr(ik_ctrl, longName="stretch", attributeType="float",
                 min=0, max=1, defaultValue=1, keyable=True)

    # ========================================
    # BUILD STRETCH NETWORK
    # ========================================
    # This is where it gets verbose with cmds!

    # Create locator at shoulder (start point)
    start_loc = cmds.spaceLocator(name="stretch_start_LOC")[0]
    cmds.matchTransform(start_loc, shoulder)

    # Create distance node
    dist_node = cmds.createNode("distanceBetween", name="stretch_distance")

    # Connect start locator to distance node
    cmds.connectAttr(f"{start_loc}.worldMatrix[0]", f"{dist_node}.inMatrix1")

    # Connect IK control to distance node
    cmds.connectAttr(f"{ik_ctrl}.worldMatrix[0]", f"{dist_node}.inMatrix2")

    # Create divide node: current_distance / total_length
    stretch_ratio = cmds.createNode("multiplyDivide", name="stretch_ratio")
    cmds.setAttr(f"{stretch_ratio}.operation", 2)  # Divide
    cmds.connectAttr(f"{dist_node}.distance", f"{stretch_ratio}.input1X")
    cmds.setAttr(f"{stretch_ratio}.input2X", total_length)

    # Create condition: only stretch when extended (ratio > 1)
    stretch_condition = cmds.createNode("condition", name="stretch_condition")
    cmds.setAttr(f"{stretch_condition}.operation", 2)  # Greater than
    cmds.connectAttr(f"{stretch_ratio}.outputX", f"{stretch_condition}.firstTerm")
    cmds.setAttr(f"{stretch_condition}.secondTerm", 1)
    cmds.connectAttr(f"{stretch_ratio}.outputX", f"{stretch_condition}.colorIfTrueR")
    cmds.setAttr(f"{stretch_condition}.colorIfFalseR", 1)

    # Blend between stretch and no-stretch based on attribute
    # Formula: final = 1 + (stretch_ratio - 1) * blend_weight

    # stretch_ratio - 1
    minus_one = cmds.createNode("plusMinusAverage", name="stretch_minus_one")
    cmds.setAttr(f"{minus_one}.operation", 2)  # Subtract
    cmds.connectAttr(f"{stretch_condition}.outColorR", f"{minus_one}.input1D[0]")
    cmds.setAttr(f"{minus_one}.input1D[1]", 1)

    # (stretch_ratio - 1) * blend_weight
    blend_mult = cmds.createNode("multiplyDivide", name="stretch_blend_mult")
    cmds.connectAttr(f"{minus_one}.output1D", f"{blend_mult}.input1X")
    cmds.connectAttr(f"{ik_ctrl}.stretch", f"{blend_mult}.input2X")

    # 1 + (stretch_ratio - 1) * blend_weight
    final_stretch = cmds.createNode("plusMinusAverage", name="stretch_final")
    cmds.setAttr(f"{final_stretch}.operation", 1)  # Sum
    cmds.setAttr(f"{final_stretch}.input1D[0]", 1)
    cmds.connectAttr(f"{blend_mult}.outputX", f"{final_stretch}.input1D[1]")

    # Multiply by original bone lengths
    upper_final = cmds.createNode("multiplyDivide", name="upper_stretch_mult")
    cmds.connectAttr(f"{final_stretch}.output1D", f"{upper_final}.input1X")
    cmds.setAttr(f"{upper_final}.input2X", upper_length)

    lower_final = cmds.createNode("multiplyDivide", name="lower_stretch_mult")
    cmds.connectAttr(f"{final_stretch}.output1D", f"{lower_final}.input1X")
    cmds.setAttr(f"{lower_final}.input2X", lower_length)

    # Connect to joints
    cmds.connectAttr(f"{upper_final}.outputX", f"{elbow}.translateX")
    cmds.connectAttr(f"{lower_final}.outputX", f"{wrist}.translateX")

    print("maya.cmds: Created 9 utility nodes for stretch setup")
    return ik_ctrl, shoulder


def run_benchmark(iterations=30):
    """Run the benchmark and report timing."""
    bm = benchmark.MayaBenchmark()
    bm.measure("create_stretchy_ik_cmds", iterations=iterations, new_scene=True).run(
        create_stretchy_ik_cmds)



if __name__ == "__main__":
    run_benchmark()

