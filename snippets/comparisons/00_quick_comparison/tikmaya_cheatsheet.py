"""
tik.maya Cheat Sheet
====================
A quick reference for the most common operations.
Copy-paste these snippets as needed!

Run this in Maya's Script Editor to see all examples in action.
"""
import tik.maya as tm


def setup():
    """Create a clean scene for examples."""
    tm.file(new=True, force=True)
    print("\n" + "="*60)
    print("tik.maya CHEAT SHEET")
    print("="*60 + "\n")


# ============================================================================
# NODE CREATION
# ============================================================================

def example_node_creation():
    """Creating nodes - works just like cmds!"""
    print("--- NODE CREATION ---")

    # Transform
    trans = tm.Transform.create(name="myTransform")
    # Or:
    # trans = tm.createNode("transform", name="myTransform")
    # or:
    # trans = tm.create_node("transform", name="myTransform")

    # Joint chain
    joint1 = tm.Joint.create(position=(0, 0, 0), name="joint1")
    joint2 = tm.Joint.create(position=(5, 0, 0), name="joint2")

    # Primitives - returns wrapped objects!
    cube_trans, cube_shape = tm.polyCube(name="myCube")
    sphere_trans, sphere_shape = tm.polySphere(name="mySphere")

    # NURBS curves
    ctrl = tm.circle(name="myControl", radius=2)[0]

    print(f"  Created: {trans.name}, {joint1.name}, {cube_trans.name}")


# ============================================================================
# ATTRIBUTE ACCESS
# ============================================================================

def example_attribute_access():
    """Getting and setting attributes."""
    print("\n--- ATTRIBUTE ACCESS ---")

    node = tm.createNode("transform", name="attrDemo")

    # Property access (for common attributes)
    node.translate_x = 10
    node.translate_y = 5
    node.visibility = True
    # or
    node["tx"].value = 10
    node["ty"].value = 5
    node["visibility"].value = True
    # or
    node["tx"].set(10)
    node["ty"].set(5)
    node["visibility"].set(True)

    # Full translate as MVector
    pos = node.translate
    print(f"  Position: ({pos.x}, {pos.y}, {pos.z})")

    # Bracket notation (for any attribute)
    node["rotateZ"].value = 45
    rotation = node["rotateZ"].value
    print(f"  Rotation Z: {rotation}")

    # Alternative: set via .value property
    node["scaleX"].value = 2


# ============================================================================
# ATTRIBUTE OPERATIONS
# ============================================================================

def example_attribute_operations():
    """Locking, hiding, and keyable states."""
    print("\n--- ATTRIBUTE OPERATIONS ---")

    ctrl = tm.circle(name="lockDemo")[0]

    # Lock attributes
    ctrl["translateX"].locked = True
    ctrl["translateX"].lock()  # Alternative method

    # Unlock
    ctrl["translateX"].unlock()
    ctrl["translateX"].locked = False

    # Hide from channel box
    ctrl["scaleX"].visible = False
    ctrl["scaleY"].keyable = False

    # Check state
    is_locked = ctrl["translateZ"].locked
    is_keyable = ctrl["rotateX"].keyable
    print(f"  translateZ locked: {is_locked}, rotateX keyable: {is_keyable}")


# ============================================================================
# CONNECTIONS
# ============================================================================

def example_connections():
    """Connecting attributes with >> operator."""
    print("\n--- CONNECTIONS ---")

    source = tm.createNode("transform", name="source")
    target = tm.createNode("transform", name="target")

    # Connect with >> operator
    source["translate"] >> target["translate"]
    source["rotateX"] >> target["rotateX"]

    # Reverse connection with <<
    target["rotateY"] << source["rotateY"]

    # Query connections
    inputs = target["translate"].list_inputs()
    print(f"  target.translate inputs: {[n.name for n in inputs]}")

    # Disconnect with //
    source["translate"] // target["translate"]
    print("  Disconnected translate")


# ============================================================================
# MATHEMATICAL OPERATORS
# ============================================================================

def example_math_operators():
    """Math operators that create Maya nodes automatically!"""
    print("\n--- MATH OPERATORS ---")

    node = tm.createNode("transform", name="mathDemo")
    node.add_attr("inputA", attributeType="float", defaultValue=10, keyable=True)
    node.add_attr("inputB", attributeType="float", defaultValue=5, keyable=True)
    node.add_attr("result", attributeType="float")

    input_a = node["inputA"]
    input_b = node["inputB"]

    # Addition (creates plusMinusAverage)
    added = input_a + input_b

    # Subtraction
    subtracted = input_a - input_b

    # Multiplication (creates multiplyDivide)
    multiplied = input_a * 2

    # Division
    divided = input_a / input_b

    # Power
    squared = input_a ** 2
    sqrt = input_a ** 0.5

    # Chain them together!
    result = (input_a + input_b) * 2 / input_b
    result >> node["result"]

    print(f"  (10 + 5) * 2 / 5 = {node['result'].value}")


# ============================================================================
# HIERARCHY
# ============================================================================

def example_hierarchy():
    """Working with parent/child relationships."""
    print("\n--- HIERARCHY ---")

    # Create hierarchy
    parent = tm.createNode("transform", name="parent")
    child = tm.createNode("transform", name="child")
    grandchild = tm.createNode("transform", name="grandchild")

    # Set parent with property
    child.parent = parent
    grandchild.parent = child

    # Query parent (returns wrapped node!)
    parent_node = grandchild.parent
    print(f"  grandchild's parent: {parent_node.name}")

    # Query children (returns list of wrapped nodes!)
    children = parent.children
    print(f"  parent's children: {[c.name for c in children]}")

    # Unparent to world
    child.parent = None


# ============================================================================
# TRANSFORM OPERATIONS
# ============================================================================

def example_transform_operations():
    """Transform-specific operations."""
    print("\n--- TRANSFORM OPERATIONS ---")

    source = tm.joint(name="source")
    source.translate = (5, 10, 3)
    source.rotate = (45, 0, 0)

    target = tm.createNode("transform", name="target")

    # Snap to another transform
    target.snap_to(source)
    print(f"  target snapped to position: {target.translate}")

    # Freeze transformations
    target.freeze()

    # Get world-space info
    world_pos = target.world_translation
    world_mtx = target.world_matrix
    print(f"  World position: {world_pos}")


# ============================================================================
# CUSTOM ATTRIBUTES
# ============================================================================

def example_custom_attributes():
    """Adding and working with custom attributes."""
    print("\n--- CUSTOM ATTRIBUTES ---")

    ctrl = tm.circle(name="customAttrDemo")[0]

    # Add attributes (takes the same args as cmds.addAttr)
    ctrl.add_attr("myFloat", attributeType="float", defaultValue=0, keyable=True)
    ctrl.add_attr("myBool", attributeType="bool", defaultValue=True, keyable=True)
    ctrl.add_attr("myEnum", attributeType="enum", enumName="A:B:C:", keyable=True)

    # Set and get values
    ctrl["myFloat"].value = 5.5
    ctrl["myBool"].value = False
    ctrl["myEnum"].value = 1  # "B"

    # Check existence
    has_attr = ctrl.has_attr("myFloat")
    # or
    has_attr = ctrl["myFloat"].exists()
    print(f"  Has myFloat: {has_attr}")

    # Delete attribute
    ctrl.delete_attr("myEnum")


# ============================================================================
# SCENE QUERIES
# ============================================================================

def example_scene_queries():
    """Querying the scene."""
    print("\n--- SCENE QUERIES ---")

    # Create some nodes to query
    tm.select(clear=True)
    for idx in range(3):
        tm.joint(name=f"queryJoint_{idx}")
    tm.createNode("transform", name="queryTransform")

    # List by type - returns wrapped objects!
    all_joints = tm.ls(type="joint")
    print(f"  Found {len(all_joints)} joints")

    # List by name pattern
    query_nodes = tm.ls("query*")
    print(f"  Nodes matching 'query*': {[n.name for n in query_nodes]}")

    # List selection
    tm.select("queryJoint_0", "queryJoint_1")
    selected = tm.ls(selection=True)
    print(f"  Selected: {[n.name for n in selected]}")


# ============================================================================
# RUN ALL EXAMPLES
# ============================================================================

def run_all():
    """Run all examples."""
    setup()
    example_node_creation()
    example_attribute_access()
    example_attribute_operations()
    example_connections()
    example_math_operators()
    example_hierarchy()
    example_transform_operations()
    example_custom_attributes()
    example_scene_queries()

    print("\n" + "="*60)
    print("CHEAT SHEET COMPLETE!")
    print("="*60 + "\n")


if __name__ == "__main__":
    run_all()

