"""
Stretchy IK Setup - tik.maya approach
=====================================
This is a REAL rigging scenario: Creating a stretchy IK limb.

With tik.maya's mathematical operators, the complex node network
becomes readable Python math expressions!

Compare the code length and readability with the cmds version.

Run this in Maya's Script Editor to see the results.
"""
import tik.maya as tm
from tik.maya.core import benchmark


def create_stretchy_ik_tikmaya():
    """Create a stretchy two-bone IK chain using tik.maya.

    Notice how the mathematical expressions read like actual math!
    """

    # ========================================
    # CREATE THE SKELETON
    # ========================================
    tm.select(clear=True)
    shoulder = tm.joint(position=(0, 10, 0), name="shoulder_JNT")
    elbow = tm.joint(position=(5, 10, -1), name="elbow_JNT")
    wrist = tm.joint(position=(10, 10, 0), name="wrist_JNT")

    # Orient joints
    tm.joint(shoulder, edit=True, orientJoint="xyz",
             secondaryAxisOrient="yup", children=True)

    # Get default bone lengths
    upper_length = elbow["translateX"].value
    lower_length = wrist["translateX"].value
    total_length = upper_length + lower_length

    # ========================================
    # CREATE IK HANDLE
    # ========================================
    ik_handle, effector = tm.ikHandle(
        startJoint=shoulder,
        endEffector=wrist,
        solver="ikRPsolver",
        name="arm_IKH"
    )

    # ========================================
    # CREATE CONTROL
    # ========================================
    ik_ctrl = tm.circle(name="IK_CTRL", normal=(1, 0, 0), radius=1)[0]
    tm.matchTransform(ik_ctrl, wrist)
    tm.makeIdentity(ik_ctrl, apply=True, translate=True, rotate=True)
    ik_handle.parent = ik_ctrl

    # Add stretch attribute
    ik_ctrl.add_attr("stretch", attributeType="float",
                     min=0, max=1, defaultValue=1, keyable=True)

    # ========================================
    # BUILD STRETCH NETWORK
    # ========================================
    # This is where tik.maya SHINES!

    # Create locator at shoulder (start point)
    start_loc = tm.spaceLocator(name="stretch_start_LOC")[0]
    tm.matchTransform(start_loc, shoulder)

    # Create distance node
    dist_node = tm.createNode("distanceBetween", name="stretch_distance")

    # Connect matrices
    start_loc["worldMatrix[0]"] >> dist_node["inMatrix1"]
    ik_ctrl["worldMatrix[0]"] >> dist_node["inMatrix2"]

    # Get the stretch attribute for cleaner code
    stretch_blend = ik_ctrl["stretch"]
    current_distance = dist_node["distance"]

    # Calculate stretch ratio: current / default
    stretch_ratio = current_distance / total_length

    # Create condition for stretch (only when extended)
    # We need to handle the condition manually, but the math is cleaner
    stretch_condition = tm.createNode("condition", name="stretch_condition")
    stretch_condition["operation"].value = 2  # Greater than
    stretch_ratio >> stretch_condition["firstTerm"]
    stretch_condition["secondTerm"].value = 1
    stretch_ratio >> stretch_condition["colorIfTrueR"]
    stretch_condition["colorIfFalseR"].value = 1

    # THE MAGIC: Blend formula as readable math!
    # final = 1 + (ratio - 1) * blend
    cond_output = stretch_condition["outColorR"]
    final_stretch = 1.0 + (cond_output - 1.0) * stretch_blend

    # Apply to joints with multiplication
    (final_stretch * upper_length) >> elbow["translateX"]
    (final_stretch * lower_length) >> wrist["translateX"]

    print("tik.maya: Created equivalent nodes with ~50% less code")
    return ik_ctrl, shoulder


def create_stretchy_ik_simplified():
    """Even simpler version without the condition node.

    This version always allows stretch in both directions
    (squash when compressed, stretch when extended).
    """

    # Create skeleton
    tm.select(clear=True)
    shoulder = tm.joint(position=(0, 10, 0), name="shoulder_JNT")
    elbow = tm.joint(position=(5, 10, -1), name="elbow_JNT")
    wrist = tm.joint(position=(10, 10, 0), name="wrist_JNT")
    tm.joint(shoulder, edit=True, orientJoint="xyz",
             secondaryAxisOrient="yup", children=True)

    upper_length = elbow["translateX"].value
    lower_length = wrist["translateX"].value
    total_length = upper_length + lower_length

    # Create IK
    ik_handle, _ = tm.ikHandle(
        startJoint=shoulder, endEffector=wrist,
        solver="ikRPsolver", name="arm_IKH"
    )

    # Create control
    ik_ctrl = tm.circle(name="IK_CTRL", normal=(1, 0, 0), radius=1)[0]
    tm.matchTransform(ik_ctrl, wrist)
    tm.makeIdentity(ik_ctrl, apply=True, translate=True, rotate=True)
    ik_handle.parent = ik_ctrl
    ik_ctrl.add_attr("stretch", attributeType="float",
                     min=0, max=1, defaultValue=1, keyable=True)

    # Distance setup
    start_loc = tm.spaceLocator(name="stretch_start_LOC")[0]
    tm.matchTransform(start_loc, shoulder)
    dist_node = tm.createNode("distanceBetween", name="stretch_distance")
    start_loc["worldMatrix[0]"] >> dist_node["inMatrix1"]
    ik_ctrl["worldMatrix[0]"] >> dist_node["inMatrix2"]

    # THE ENTIRE STRETCH MATH IN 4 LINES:
    stretch_ratio = dist_node["distance"] / total_length
    blended = 1.0 + (stretch_ratio - 1.0) * ik_ctrl["stretch"]
    (blended * upper_length) >> elbow["translateX"]
    (blended * lower_length) >> wrist["translateX"]

    return ik_ctrl, shoulder


def run_benchmark(iterations=30):
    """Run the benchmark and report timing."""
    bm = benchmark.MayaBenchmark()
    bm.measure("create_stretchy_ik_tikmaya", iterations=iterations, new_scene=True).run(
        create_stretchy_ik_tikmaya)



if __name__ == "__main__":
    run_benchmark()

