"""
Attribute Math Networks - maya.cmds approach
============================================
This example demonstrates creating mathematical node networks
for driven setups - a core rigging technique.

Scenario: Create a "squash and stretch" setup where:
- A control's Y scale inversely affects X and Z scale
- The effect is multiplied by a user-controllable intensity

This shows how verbose maya.cmds becomes for math-heavy setups.

Run this in Maya's Script Editor to see the results.
"""
from maya import cmds
from tik.maya.core import benchmark


def create_squash_stretch_cmds():
    """Create a squash/stretch setup using maya.cmds."""

    # Create the control and driven object
    control = cmds.createNode("transform", name="squash_CTRL")
    cmds.addAttr(control, longName="stretchAmount", attributeType="float",
                 defaultValue=1, keyable=True)
    cmds.addAttr(control, longName="intensity", attributeType="float",
                 defaultValue=1, min=0, max=2, keyable=True)

    driven = cmds.polyCube(name="driven_GEO")[0]
    cmds.move(0, 2, 0, driven)

    # ========================================
    # BUILD THE MATH NETWORK
    # ========================================
    # Formula: inverse_scale = 1 / sqrt(stretchAmount)
    # Final scale = lerp(1, inverse_scale, intensity)

    # Step 1: Create power node for square root (power of 0.5)
    sqrt_node = cmds.createNode("multiplyDivide", name="stretch_sqrt")
    cmds.setAttr(f"{sqrt_node}.operation", 3)  # Power
    cmds.setAttr(f"{sqrt_node}.input2X", 0.5)  # Square root = power of 0.5
    cmds.connectAttr(f"{control}.stretchAmount", f"{sqrt_node}.input1X")

    # Step 2: Create divide node for inverse (1 / sqrt)
    inverse_node = cmds.createNode("multiplyDivide", name="stretch_inverse")
    cmds.setAttr(f"{inverse_node}.operation", 2)  # Divide
    cmds.setAttr(f"{inverse_node}.input1X", 1.0)
    cmds.connectAttr(f"{sqrt_node}.outputX", f"{inverse_node}.input2X")

    # Step 3: Calculate difference from 1 (inverse - 1)
    diff_node = cmds.createNode("plusMinusAverage", name="stretch_diff")
    cmds.setAttr(f"{diff_node}.operation", 2)  # Subtract
    cmds.connectAttr(f"{inverse_node}.outputX", f"{diff_node}.input1D[0]")
    cmds.setAttr(f"{diff_node}.input1D[1]", 1.0)

    # Step 4: Multiply difference by intensity
    intensity_mult = cmds.createNode("multiplyDivide", name="stretch_intensity")
    cmds.setAttr(f"{intensity_mult}.operation", 1)  # Multiply
    cmds.connectAttr(f"{diff_node}.output1D", f"{intensity_mult}.input1X")
    cmds.connectAttr(f"{control}.intensity", f"{intensity_mult}.input2X")

    # Step 5: Add back to 1 to get final scale
    final_add = cmds.createNode("plusMinusAverage", name="stretch_final")
    cmds.setAttr(f"{final_add}.operation", 1)  # Sum
    cmds.setAttr(f"{final_add}.input1D[0]", 1.0)
    cmds.connectAttr(f"{intensity_mult}.outputX", f"{final_add}.input1D[1]")

    # Step 6: Connect to driven object's X and Z scale
    cmds.connectAttr(f"{final_add}.output1D", f"{driven}.scaleX")
    cmds.connectAttr(f"{final_add}.output1D", f"{driven}.scaleZ")

    # Also connect Y scale directly to stretch amount
    cmds.connectAttr(f"{control}.stretchAmount", f"{driven}.scaleY")

    return control, driven


def create_complex_math_cmds():
    """Create a more complex mathematical relationship.

    Formula: output = (A + B) * C / D - E
    This requires 4 separate nodes with maya.cmds.
    """

    # Create a node with our input attributes
    node = cmds.createNode("transform", name="math_node")
    for attr in ["inputA", "inputB", "inputC", "inputD", "inputE"]:
        cmds.addAttr(node, longName=attr, attributeType="float",
                     defaultValue=1, keyable=True)
    cmds.addAttr(node, longName="result", attributeType="float")

    # Set some test values
    cmds.setAttr(f"{node}.inputA", 5)
    cmds.setAttr(f"{node}.inputB", 3)
    cmds.setAttr(f"{node}.inputC", 2)
    cmds.setAttr(f"{node}.inputD", 4)
    cmds.setAttr(f"{node}.inputE", 1)
    # Expected result: (5 + 3) * 2 / 4 - 1 = 8 * 2 / 4 - 1 = 16 / 4 - 1 = 4 - 1 = 3

    # Step 1: A + B
    add_node = cmds.createNode("plusMinusAverage", name="math_add")
    cmds.setAttr(f"{add_node}.operation", 1)
    cmds.connectAttr(f"{node}.inputA", f"{add_node}.input1D[0]")
    cmds.connectAttr(f"{node}.inputB", f"{add_node}.input1D[1]")

    # Step 2: (A + B) * C
    mult_node = cmds.createNode("multiplyDivide", name="math_mult")
    cmds.setAttr(f"{mult_node}.operation", 1)
    cmds.connectAttr(f"{add_node}.output1D", f"{mult_node}.input1X")
    cmds.connectAttr(f"{node}.inputC", f"{mult_node}.input2X")

    # Step 3: ((A + B) * C) / D
    div_node = cmds.createNode("multiplyDivide", name="math_div")
    cmds.setAttr(f"{div_node}.operation", 2)
    cmds.connectAttr(f"{mult_node}.outputX", f"{div_node}.input1X")
    cmds.connectAttr(f"{node}.inputD", f"{div_node}.input2X")

    # Step 4: (((A + B) * C) / D) - E
    sub_node = cmds.createNode("plusMinusAverage", name="math_sub")
    cmds.setAttr(f"{sub_node}.operation", 2)
    cmds.connectAttr(f"{div_node}.outputX", f"{sub_node}.input1D[0]")
    cmds.connectAttr(f"{node}.inputE", f"{sub_node}.input1D[1]")

    # Connect to result
    cmds.connectAttr(f"{sub_node}.output1D", f"{node}.result")

    # Verify
    result = cmds.getAttr(f"{node}.result")
    print(f"maya.cmds result: {result} (expected: 3.0)")

    return node


def run_benchmark(iterations=50):
    """Run the benchmark and report timing."""
    bm = benchmark.MayaBenchmark()
    bm.measure("create_squash_stretch_cmds", iterations=iterations, new_scene=True).run(
        create_squash_stretch_cmds)
    bm.measure("create_complex_math_cmds", iterations=iterations, new_scene=True).run(
        create_complex_math_cmds)


if __name__ == "__main__":
    run_benchmark()

