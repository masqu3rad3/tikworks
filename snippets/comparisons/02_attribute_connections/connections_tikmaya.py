"""
Attribute Connections - tik.maya approach
=========================================
This example demonstrates connecting attributes and building
node networks using tik.maya's operator overloading.

Key features demonstrated:
- >> operator for connections (replaces connectAttr)
- Mathematical operators create nodes automatically
- Dramatic reduction in boilerplate code

Run this in Maya's Script Editor to see the results.
"""
import tik.maya as tm
from tik.maya.core import benchmark


def build_driven_setup_tikmaya():
    """Build a driven setup with multiply node using tik.maya."""

    # Create a driver transform (simulating a control)
    driver = tm.Transform.create(name="driver_CTRL")
    driver.add_attr("bendAmount", attributeType="float", defaultValue=0,
                    keyable=True)

    # Create a driven joint
    driven = tm.Joint.create(name="driven_JNT")

    # Build node network with mathematical operators
    # driver.bendAmount -> multiply by 2 -> driven.rotateZ

    # Multiply by 2 and connect directly
    (driver["bendAmount"] * 2.0) >> driven["rotateZ"]

    return driver, driven


def build_driven_setup_tikmaya_explicit():
    """Same setup but with explicit steps for clarity."""

    # Create nodes
    driver = tm.createNode("transform", name="driver_CTRL")
    driver.add_attr("bendAmount", attributeType="float", defaultValue=0, keyable=True)

    tm.select(clear=True)
    driven = tm.joint(name="driven_JNT")

    # Step by step for those who prefer explicit code:
    # 1. Get the plug and multiply it (creates a multiplyDivide node)
    multiplied = driver["bendAmount"] * 2.0

    # 2. Connect to the driven attribute
    multiplied >> driven["rotateZ"]

    return driver, driven


def build_complex_network_tikmaya():
    """Build the blend network - notice how much simpler this is!"""

    # Create controls
    ctrl_a = tm.Transform.create(name="control_A")
    ctrl_b = tm.Transform.create(name="control_B")
    blend_ctrl = tm.Transform.create(name="blend_CTRL")
    blend_ctrl.add_attr("blendWeight", attributeType="float",
                        min=0, max=1, defaultValue=0, keyable=True)

    # Create driven joint
    driven = tm.Joint.create(name="driven_JNT")

    # The blend can be expressed mathematically!
    # result = A * (1 - weight) + B * weight
    weight = blend_ctrl["blendWeight"]

    for axis in "XYZ":
        rot_a = ctrl_a[f"rotate{axis}"]
        rot_b = ctrl_b[f"rotate{axis}"]

        # This two lines creates the entire blend network:
        blended = (rot_a * (1.0 - weight)) + (rot_b * weight)
        blended >> driven[f"rotate{axis}"]

    return ctrl_a, ctrl_b, blend_ctrl, driven


def run_benchmark(iterations=50):
    """Run the benchmark and report timing."""

    bm = benchmark.MayaBenchmark()
    bm.measure("build_driven_setup_tikmaya", iterations=iterations, new_scene=True).run(
        build_driven_setup_tikmaya)
    bm.measure("build_complex_network_tikmaya", iterations=iterations, new_scene=True).run(
        build_complex_network_tikmaya)


if __name__ == "__main__":
    run_benchmark()

