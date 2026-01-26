"""
Attribute Math Networks - tik.maya approach
===========================================
This example demonstrates creating mathematical node networks
using tik.maya's operator overloading.

THE KILLER FEATURE: Mathematical operators on plugs automatically
create the appropriate Maya nodes!

- plug + plug  -> plusMinusAverage node
- plug - plug  -> plusMinusAverage node (subtract)
- plug * plug  -> multiplyDivide node
- plug / plug  -> multiplyDivide node (divide)
- plug ** n    -> multiplyDivide node (power)

This is where tik.maya REALLY shines.

Run this in Maya's Script Editor to see the results.
"""
import tik.maya as tm
from tik.maya.core import benchmark


def create_squash_stretch_tikmaya():
    """Create a squash/stretch setup using tik.maya.

    Compare with the cmds version - this is DRAMATICALLY simpler!
    """

    # Create the control and driven object
    control = tm.createNode("transform", name="squash_CTRL")
    control.add_attr("stretchAmount", attributeType="float",
                     defaultValue=1, keyable=True)
    control.add_attr("intensity", attributeType="float",
                     defaultValue=1, min=0, max=2, keyable=True)

    driven = tm.polyCube(name="driven_GEO")[0]
    tm.move(0, 2, 0, driven)

    # ========================================
    # BUILD THE MATH NETWORK
    # ========================================
    # Formula: inverse_scale = 1 / sqrt(stretchAmount)
    # Final scale = lerp(1, inverse_scale, intensity)

    stretch = control["stretchAmount"]
    intensity = control["intensity"]

    # THE ENTIRE MATH NETWORK IN 3 LINES!
    # Compare with the 30+ lines in the cmds version!

    # Step 1-2: inverse = 1 / sqrt(stretch) = stretch^(-0.5)
    inverse_scale = stretch ** -0.5

    # Step 3-5: lerp from 1 to inverse based on intensity
    # lerp(a, b, t) = a + (b - a) * t = 1 + (inverse - 1) * intensity
    final_scale = 1.0 + (inverse_scale - 1.0) * intensity

    # Step 6: Connect outputs
    final_scale >> driven["scaleX"]
    final_scale >> driven["scaleZ"]
    stretch >> driven["scaleY"]

    return control, driven


def create_complex_math_tikmaya():
    """Create a more complex mathematical relationship.

    Formula: output = (A + B) * C / D - E

    With tik.maya, this is literally ONE LINE of math!
    """

    # Create a node with our input attributes
    node = tm.createNode("transform", name="math_node")
    for attr in ["inputA", "inputB", "inputC", "inputD", "inputE"]:
        node.add_attr(attr, attributeType="float", defaultValue=1, keyable=True)
    node.add_attr("result", attributeType="float")

    # Set some test values
    node["inputA"].value = 5
    node["inputB"].value = 3
    node["inputC"].value = 2
    node["inputD"].value = 4
    node["inputE"].value = 1
    # Expected result: (5 + 3) * 2 / 4 - 1 = 3

    # THE ENTIRE CALCULATION IN ONE LINE!
    # Compare with the 20+ lines in the cmds version!
    input_a = node["inputA"]
    input_b = node["inputB"]
    input_c = node["inputC"]
    input_d = node["inputD"]
    input_e = node["inputE"]

    result = (input_a + input_b) * input_c / input_d - input_e
    result >> node["result"]

    # Verify
    result_value = node["result"].value
    print(f"tik.maya result: {result_value} (expected: 3.0)")

    return node


def demonstrate_operator_power():
    """Show off more mathematical operations."""

    node = tm.createNode("transform", name="demo_node")
    node.add_attr("input", attributeType="float", defaultValue=10, keyable=True)
    node.add_attr("doubled", attributeType="float")
    node.add_attr("halved", attributeType="float")
    node.add_attr("squared", attributeType="float")
    node.add_attr("sqrt", attributeType="float")
    node.add_attr("negated", attributeType="float")

    inp = node["input"]

    # All these create the appropriate Maya nodes automatically
    (inp * 2) >> node["doubled"]      # multiplyDivide
    (inp / 2) >> node["halved"]       # multiplyDivide (divide)
    (inp ** 2) >> node["squared"]     # multiplyDivide (power)
    (inp ** 0.5) >> node["sqrt"]      # multiplyDivide (power)
    (inp * -1) >> node["negated"]     # multiplyDivide

    print("\nOperator demonstration:")
    print(f"  Input: {node['input'].value}")
    print(f"  Doubled: {node['doubled'].value}")
    print(f"  Halved: {node['halved'].value}")
    print(f"  Squared: {node['squared'].value}")
    print(f"  Square root: {node['sqrt'].value}")
    print(f"  Negated: {node['negated'].value}")

    return node


def run_benchmark(iterations=50):
    """Run the benchmark and report timing."""
    bm = benchmark.MayaBenchmark()
    bm.measure("create_squash_stretch_tikmaya", iterations=iterations, new_scene=True).run(
        create_squash_stretch_tikmaya)
    bm.measure("create_complex_math_tikmaya", iterations=iterations, new_scene=True).run(
        create_complex_math_tikmaya)

    # Bonus demonstration
    demonstrate_operator_power()


if __name__ == "__main__":
    run_benchmark()

