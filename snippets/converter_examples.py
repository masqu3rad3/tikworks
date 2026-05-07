"""
Example: Using the tik.maya → maya.cmds converter.

This script demonstrates how to use the converter inside a Maya session.
It shows basic conversion scenarios and how to interpret the results.

Run this inside Maya's Script Editor or as a shelf button.
"""

# =============================================================================
# Example 1: Basic Conversion
# =============================================================================

from tik.maya.utils.converter import convert

# Sample tik.maya code
tik_code = '''
from tik.maya import Transform, Joint

# Create a simple hierarchy
root = Transform.create(name='root_grp')
joint1 = Joint.create(name='joint1')
joint2 = Joint.create(name='joint2')

# Set some transforms
root.translate = (0, 5, 0)
joint1['rotateX'].set(45)

# Connect attributes
root['translateX'].connect(joint1['translateX'])

# Alternative connection syntax
root['translateY'] >> joint2['translateY']
'''

# Convert to cmds
result = convert(tik_code)

# Print the converted code
print("=" * 60)
print("CONVERTED CODE:")
print("=" * 60)
print(result.converted_code)

# Print the conversion summary
print(result.summary())


# =============================================================================
# Example 2: Using the Converter Class Directly
# =============================================================================

from tik.maya.utils.converter import Converter

# Create a converter with custom options
converter = Converter(
    add_imports=True,    # Add 'from maya import cmds' at top
    add_header=True,     # Add documentation header
    preserve_comments=True,  # Keep original comments
)

# More complex example
complex_code = '''
from tik.maya import Transform, Mesh

# Create geometry
sphere_node = Mesh.create('polySphere', radius=2)
cube_node = Mesh.create('polyCube', width=3, height=3, depth=3)

# Create groups
geo_grp = Transform.create(name='geo_grp')

# Manipulate attributes
geo_grp.visibility = True
geo_grp['scaleX'].set(1.5)
geo_grp['scaleY'].set(1.5)
geo_grp['scaleZ'].set(1.5)

# Lock attributes
geo_grp['translateX'].lock()
geo_grp['translateY'].lock()
geo_grp['translateZ'].lock()

# Node operations
geo_grp.rename('geometry_group')
geo_grp.select()
'''

result2 = converter.convert(complex_code)
print("\n" + "=" * 60)
print("COMPLEX EXAMPLE - CONVERTED:")
print("=" * 60)
print(result2.converted_code)


# =============================================================================
# Example 3: Handling Unsupported Operations
# =============================================================================

# Code with some unsupported operations
mixed_code = '''
from tik.maya import Mesh, Transform

# Supported: creation
mesh = Mesh.create('polySphere')
grp = Transform.create(name='grp')

# Unsupported: OpenMaya-based operations
# These will be flagged in the report
verts = mesh.vertices()
mesh.unlock_normals(soften=True)

# Supported: attribute operations
grp['visibility'].set(True)
'''

result3 = convert(mixed_code)

print("\n" + "=" * 60)
print("MIXED CODE - CHECKING UNSUPPORTED:")
print("=" * 60)

if result3.unsupported_operations:
    print("\nThe following operations could not be converted:")
    for entry in result3.unsupported_operations:
        print(f"  Line {entry.line_number}: {entry.message}")
        print(f"    Original: {entry.original_code.strip()}")
else:
    print("All operations were successfully converted!")

print(result3.summary())


# =============================================================================
# Example 4: Working with the Conversion Report
# =============================================================================

print("\n" + "=" * 60)
print("DETAILED REPORT ANALYSIS:")
print("=" * 60)

# Access individual report components
print(f"\nTotal rules applied: {len(result.rules_applied)}")
for entry in result.rules_applied:
    print(f"  - {entry.rule_name} at line {entry.line_number}")

print(f"\nTotal helpers expanded: {len(result.helpers_expanded)}")

print(f"\nTotal unsupported: {len(result.unsupported_operations)}")

print(f"\nSuccess rate: {result.success_count} / {result.success_count + result.failure_count}")


# =============================================================================
# Example 5: Runtime Validation (Optional)
# =============================================================================

def execute_and_validate(converted_code):
    """Execute converted code and validate results.

    This is optional runtime validation that can be used to verify
    the conversion produced working cmds code.

    Args:
        converted_code: The converted maya.cmds code string.

    Returns:
        bool: True if execution succeeded.
    """
    from maya import cmds

    # Create a new scene to test in isolation
    cmds.file(new=True, force=True)

    try:
        # Execute the converted code
        exec(converted_code)
        print("Execution successful!")
        return True
    except Exception as exc:
        print(f"Execution failed: {exc}")
        return False


# Uncomment to test execution (requires Maya session):
# execute_and_validate(result.converted_code)

