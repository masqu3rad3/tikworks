"""
Attribute Connections - maya.cmds approach
==========================================
This example demonstrates connecting attributes and building
node networks using traditional maya.cmds API.

A common rigging scenario: Create a control that drives
joint rotation with scaling and clamping.

Run this in Maya's Script Editor to see the results.


"""
from maya import cmds
from tik.maya.core import benchmark


def build_driven_setup_cmds():
    """Build a driven setup with multiply node using maya.cmds."""

    # Create a driver transform (simulating a control)
    driver = cmds.createNode("transform", name="driver_CTRL")
    cmds.addAttr(driver, longName="bendAmount", attributeType="float",
                 defaultValue=0, keyable=True)

    # Create a driven joint
    cmds.select(clear=True)
    driven = cmds.joint(name="driven_JNT")

    # Build the node network:
    # driver.bendAmount -> multiply by 2 -> driven.rotateZ

    # Create multiply node
    mult_node = cmds.createNode("multiplyDivide", name="bend_multiply")
    cmds.setAttr(f"{mult_node}.operation", 1)  # multiply
    cmds.setAttr(f"{mult_node}.input2X", 2.0)  # multiplier

    # Connect the network
    cmds.connectAttr(f"{driver}.bendAmount", f"{mult_node}.input1X")
    cmds.connectAttr(f"{mult_node}.outputX", f"{driven}.rotateZ")

    return driver, driven


def build_complex_network_cmds():
    """Build a more complex network: blending between two rotation sources."""

    # Create controls
    ctrl_a = cmds.createNode("transform", name="control_A")
    ctrl_b = cmds.createNode("transform", name="control_B")
    blend_ctrl = cmds.createNode("transform", name="blend_CTRL")
    cmds.addAttr(blend_ctrl, longName="blendWeight", attributeType="float",
                 min=0, max=1, defaultValue=0, keyable=True)

    # Create driven joint
    cmds.select(clear=True)
    driven = cmds.joint(name="driven_JNT")

    # Build blend network for each rotation axis
    for axis in "XYZ":
        # Create blend node
        blend_node = cmds.createNode("blendWeighted", name=f"rotate{axis}_blend")

        # Connect inputs
        cmds.connectAttr(f"{ctrl_a}.rotate{axis}", f"{blend_node}.input[0]")
        cmds.connectAttr(f"{ctrl_b}.rotate{axis}", f"{blend_node}.input[1]")

        # Create a reverse for the weight
        reverse_node = cmds.createNode("reverse", name=f"weight{axis}_reverse")
        cmds.connectAttr(f"{blend_ctrl}.blendWeight", f"{reverse_node}.inputX")

        # Connect weights
        cmds.connectAttr(f"{reverse_node}.outputX", f"{blend_node}.weight[0]")
        cmds.connectAttr(f"{blend_ctrl}.blendWeight", f"{blend_node}.weight[1]")

        # Connect output
        cmds.connectAttr(f"{blend_node}.output", f"{driven}.rotate{axis}")

    return ctrl_a, ctrl_b, blend_ctrl, driven


def run_benchmark(iterations=50):
    """Run the benchmark and report timing."""
    bm = benchmark.MayaBenchmark()
    bm.measure("build_driven_setup_cmds", iterations=iterations, new_scene=True).run(
        build_driven_setup_cmds)
    bm.measure("build_complex_network_cmds", iterations=iterations, new_scene=True).run(
        build_complex_network_cmds)


if __name__ == "__main__":
    run_benchmark()

