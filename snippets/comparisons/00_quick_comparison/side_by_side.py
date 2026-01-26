"""
Side-by-Side Comparison: The Same Task, Two Approaches
======================================================
This file shows the EXACT same rigging tasks implemented
with maya.cmds and tik.maya for direct comparison.

Run this in Maya's Script Editor to see both approaches
executed and their timing compared.

"""
from maya import cmds
import tik.maya as tm
from time import perf_counter


# ============================================================================
# EXAMPLE 1: ATTRIBUTE ACCESS
# ============================================================================

def example1_cmds():
    """Get and set a transform's translation using maya.cmds."""
    cmds.file(new=True, force=True)
    node = cmds.createNode("transform", name="myNode")

    # GET - returns a list of tuples: [(x, y, z)]
    translation = cmds.getAttr(f"{node}.translate")[0]
    pos_x = cmds.getAttr(f"{node}.translateX")

    # SET - need string concatenation
    cmds.setAttr(f"{node}.translateX", 10)
    cmds.setAttr(f"{node}.translateY", 5)
    cmds.setAttr(f"{node}.translateZ", 3)


def example1_tikmaya():
    """Get and set a transform's translation using tik.maya."""
    tm.file(new=True, force=True)
    node = tm.createNode("transform", name="myNode")

    # GET - returns MVector with x, y, z properties
    translation = node.translate
    pos_x = node.translate_x

    # SET - property assignment
    node.tx = 10
    node.ty = 5
    node.tz = 3


# ============================================================================
# EXAMPLE 2: ATTRIBUTE CONNECTIONS
# ============================================================================

def example2_cmds():
    """Connect attributes using maya.cmds."""
    cmds.file(new=True, force=True)
    source = cmds.createNode("transform", name="source")
    target = cmds.createNode("transform", name="target")

    # Connect - string-heavy
    cmds.connectAttr(f"{source}.translate", f"{target}.translate")
    cmds.connectAttr(f"{source}.rotateX", f"{target}.rotateX")
    cmds.connectAttr(f"{source}.rotateY", f"{target}.rotateY")
    cmds.connectAttr(f"{source}.rotateZ", f"{target}.rotateZ")


def example2_tikmaya():
    """Connect attributes using tik.maya."""
    tm.file(new=True, force=True)
    # source = tm.createNode("transform", name="source")
    source = tm.Transform.create(name="source")
    target = tm.Transform.create(name="target")

    # Connect - intuitive >> operator
    source["translate"] >> target["translate"]
    source["rotateX"] >> target["rotateX"]
    source["rotateY"] >> target["rotateY"]
    source["rotateZ"] >> target["rotateZ"]


# ============================================================================
# EXAMPLE 3: MATH OPERATIONS
# ============================================================================

def example3_cmds():
    """Create: output = input * 2 + 5, using maya.cmds."""
    cmds.file(new=True, force=True)
    node = cmds.createNode("transform", name="mathNode")
    cmds.addAttr(node, ln="inputVal", at="float", k=True, dv=10)
    cmds.addAttr(node, ln="outputVal", at="float")

    # Create multiply node
    mult = cmds.createNode("multiplyDivide", name="mult")
    cmds.setAttr(f"{mult}.operation", 1)  # multiply
    cmds.setAttr(f"{mult}.input2X", 2)
    cmds.connectAttr(f"{node}.inputVal", f"{mult}.input1X")

    # Create add node
    add = cmds.createNode("plusMinusAverage", name="add")
    cmds.setAttr(f"{add}.operation", 1)  # sum
    cmds.connectAttr(f"{mult}.outputX", f"{add}.input1D[0]")
    cmds.setAttr(f"{add}.input1D[1]", 5)

    # Connect output
    cmds.connectAttr(f"{add}.output1D", f"{node}.outputVal")

    return cmds.getAttr(f"{node}.outputVal")  # Should be 25


def example3_tikmaya():
    """Create: output = input * 2 + 5, using tik.maya."""
    tm.file(new=True, force=True)
    node = tm.Transform.create(name="mathNode")
    node.add_attr("inputVal", attributeType="float", keyable=True, defaultValue=10)
    node.add_attr("outputVal", attributeType="float")

    # The entire math operation in one line.
    (node["inputVal"] * 2 + 5) >> node["outputVal"]

    return node["outputVal"].value  # Should be 25


# ============================================================================
# EXAMPLE 4: PARENT/CHILD RELATIONSHIPS
# ============================================================================

def example4_cmds():
    """Work with hierarchy using maya.cmds."""
    cmds.file(new=True, force=True)

    # Create hierarchy
    parent = cmds.createNode("transform", name="parent")
    child = cmds.createNode("transform", name="child")
    cmds.parent(child, parent)

    # Query parent
    parent_node = cmds.listRelatives(child, parent=True)
    if parent_node:
        parent_name = parent_node[0]

    # Query children
    children = cmds.listRelatives(parent, children=True)

    # Reparent to world
    cmds.parent(child, world=True)


def example4_tikmaya():
    """Work with hierarchy using tik.maya."""
    tm.file(new=True, force=True)

    # Create hierarchy - property assignment!
    parent = tm.Transform.create(name="parent")
    child = tm.Transform.create(name="child")
    child.parent = parent

    # Query parent - returns wrapped node!
    parent_node = child.parent
    if parent_node:
        parent_name = parent_node.name

    # Query children - returns list of wrapped nodes!
    children = parent.children

    # Reparent to world
    child.parent = None


# ============================================================================
# EXAMPLE 5: LOCKING/UNLOCKING ATTRIBUTES
# ============================================================================

def example5_cmds():
    """Lock/unlock attributes using maya.cmds."""
    cmds.file(new=True, force=True)
    node = cmds.createNode("transform", name="ctrl")

    # Lock - verbose
    cmds.setAttr(f"{node}.translateX", lock=True)
    cmds.setAttr(f"{node}.translateY", lock=True)
    cmds.setAttr(f"{node}.translateZ", lock=True)

    # Hide from channelbox
    cmds.setAttr(f"{node}.scaleX", keyable=False, channelBox=False)
    cmds.setAttr(f"{node}.scaleY", keyable=False, channelBox=False)
    cmds.setAttr(f"{node}.scaleZ", keyable=False, channelBox=False)


def example5_tikmaya():
    """Lock/unlock attributes using tik.maya."""
    tm.file(new=True, force=True)
    node = tm.Transform.create(name="ctrl")

    # Lock - property setter
    node["translateX"].locked = True
    node["translateY"].locked = True
    node["translateZ"].locked = True

    # Hide from channelbox - property setter
    node["scaleX"].visible = False
    node["scaleY"].visible = False
    node["scaleZ"].visible = False


# ============================================================================
# RUN COMPARISONS
# ============================================================================

def run_all_comparisons():
    """Run all examples and compare timing."""
    iterations = 100

    print("\n" + "=" * 60)
    print("SIDE-BY-SIDE COMPARISON: maya.cmds vs tik.maya")
    print("=" * 60)

    examples = [
        ("Attribute Access", example1_cmds, example1_tikmaya),
        ("Attribute Connections", example2_cmds, example2_tikmaya),
        ("Math Operations", example3_cmds, example3_tikmaya),
        ("Parent/Child", example4_cmds, example4_tikmaya),
        ("Lock/Hide Attrs", example5_cmds, example5_tikmaya),
    ]

    for name, cmds_func, tm_func in examples:
        # Time cmds version
        start = perf_counter()
        for _ in range(iterations):
            cmds_func()
        cmds_time = perf_counter() - start

        # Time tik.maya version
        start = perf_counter()
        for _ in range(iterations):
            tm_func()
        tm_time = perf_counter() - start

        # Calculate difference
        diff = ((cmds_time - tm_time) / cmds_time) * 100
        winner = "tik.maya" if tm_time < cmds_time else "cmds"

        print(f"\n{name}:")
        print(f"  maya.cmds:  {cmds_time*1000/iterations:.2f} ms/iter")
        print(f"  tik.maya:   {tm_time*1000/iterations:.2f} ms/iter")
        print(f"  Winner: {winner} ({abs(diff):.1f}% {'faster' if diff > 0 else 'slower'})")

    print("\n" + "=" * 60)
    print("KEY TAKEAWAYS:")
    print("=" * 60)
    print("""
1. READABILITY: tik.maya uses properties and operators that read
   like natural Python code.

2. CODE LENGTH: Mathematical operations that take 10+ lines with
   cmds can be done in 1 line with tik.maya.

3. SAFETY: Wrapped objects track validity and provide better
   error messages.

4. PYTHONIC: >> for connections, properties for state, methods
   for actions - follows Python conventions.

5. PERFORMANCE: API-based operations can be faster than cmds
   string parsing, especially for batch operations.
""")


if __name__ == "__main__":
    run_all_comparisons()

