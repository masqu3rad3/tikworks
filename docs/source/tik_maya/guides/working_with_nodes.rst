Working with Nodes
==================

In tik.maya, **nodes** are the fundamental building blocks. This guide explains how to create, access, and work with different node types.

What is a Node in tik.maya?
----------------------------

A **node** in tik.maya is a Python wrapper around a Maya scene node. Every node is tracked by its UUID and wrapped in a class that corresponds to its Maya type.

.. code-block:: python

   import tik.maya as tm

   # Resolve a node - returns the appropriate wrapper class
   cube = tm.resolve("pCube1")  # Returns Transform instance
   print(type(cube))  # <class 'tik.maya.types.transform.Transform'>

Understanding Node Types
-------------------------

tik.maya automatically wraps Maya nodes in type-specific classes. The ``type`` of a node in tik.maya context refers to the **Python wrapper class**, which corresponds to the Maya node type.

The registry system resolves the correct wrapper class based on Maya's node type:

.. code-block:: python

   import tik.maya as tm

   # Different Maya node types get different wrapper classes
   transform = tm.resolve("pCube1")       # Transform wrapper
   mesh = tm.resolve("pCubeShape1")       # Mesh wrapper
   joint = tm.resolve("joint1")           # Joint wrapper
   locator = tm.resolve("locatorShape1")  # Locator wrapper

   # Each type has specialized methods
   print(transform.translate)  # Transform-specific property
   print(mesh.vertices())      # Mesh-specific method
   print(joint.radius)         # Joint-specific property

Node Type Hierarchy
~~~~~~~~~~~~~~~~~~~~

tik.maya's type system mirrors Maya's node hierarchy:

.. code-block:: text

   Node (base wrapper)
   ├── DagNode (DAG hierarchy nodes)
   │   ├── Transform
   │   │   └── Joint
   │   └── ShapeNode
   │       ├── Mesh
   │       ├── Curve
   │       ├── Nurbs
   │       ├── Locator
   │       ├── Camera
   │       └── Light
   └── DependencyNode (DG-only nodes)
       ├── AnimCurve
       ├── BlendShape
       └── (other dependency nodes)

**Node** is the base class for all wrappers. It provides core functionality like UUID tracking, attribute access, and existence checking.

**DagNode** extends Node for nodes in the DAG (Directed Acyclic Graph) hierarchy. It adds parent/child relationships and world/local transformations.

**Transform** and **ShapeNode** are specialized DAG nodes. Transforms can have children and shapes, while ShapeNodes are the geometry/rendering components.

Creating Nodes
--------------

Creating New Nodes
~~~~~~~~~~~~~~~~~~

tik.maya offers three ways to create nodes, each with different use cases:

**Method 1: Type-Specific create() (Most Explicit)**

Use the ``create()`` class method on any type class for the most explicit approach:

.. code-block:: python

   import tik.maya as tm

   # Create a transform
   grp = tm.Transform.create(name="myGroup")

   # Create a joint
   jnt = tm.Joint.create(name="spine_01")

   # Create shape nodes (returns the shape wrapper)
   loc = tm.Locator.create(name="myLocator")
   print(type(loc))  # <class 'tik.maya.types.locator.Locator'>

   # Access the parent transform via .transform property
   loc.transform.translate = (5, 10, 0)

For geometry shapes, pass the Maya creation command as the first argument:

.. code-block:: python

   # Create a polygon sphere
   sphere = tm.Mesh.create("polySphere", name="mySphere", radius=2)
   sphere.transform.translate = (0, 5, 0)

   # Create a NURBS plane
   plane = tm.Nurbs.create("nurbsPlane", name="myPlane")

   # Create a curve
   curve = tm.Curve.create("circle", name="myCircle")

**Method 2: createNode() or create_node() (cmds-like)**

Use ``tm.createNode()`` or ``tm.create_node()`` for a familiar cmds-style interface:

.. code-block:: python

   import tik.maya as tm

   # Create using createNode (camelCase alias)
   transform = tm.createNode("transform", name="myTransform")

   # Or using create_node (snake_case)
   camera = tm.create_node("camera", name="myCamera")

   # Works with any Maya node type
   mult_node = tm.createNode("multiplyDivide", name="myMultiply")

This method automatically resolves the created node to the correct wrapper type.

**Method 3: Node.create() (Generic)**

Use ``tm.Node.create()`` for a generic creation that still resolves to the correct type:

.. code-block:: python

   import tik.maya as tm

   # Create a camera using Node.create()
   camera = tm.Node.create("camera", name="myCamera")
   print(type(camera))  # <class 'tik.maya.types.camera.Camera'>

   # Create a transform
   transform = tm.Node.create("transform", name="myTransform")
   print(type(transform))  # <class 'tik.maya.types.transform.Transform'>

Even though you're calling ``Node.create()``, tik.maya resolves the node type
and returns the appropriate wrapper class (Camera, Transform, etc.).

Wrapping Existing Nodes
~~~~~~~~~~~~~~~~~~~~~~~~

Use :func:`tm.resolve` to wrap nodes that already exist in the scene:

.. code-block:: python

   import tik.maya as tm

   # By name
   cube = tm.resolve("pCube1")

   # From a list of names
   nodes = tm.resolve(["pCube1", "pSphere1", "joint1"])

   # Works with any valid Maya node name
   persp_cam = tm.resolve("persp")  # Camera transform
   persp_shape = tm.resolve("perspShape")  # Camera shape

Node Type Resolution Order
~~~~~~~~~~~~~~~~~~~~~~~~~~~

When resolving nodes (either with ``tm.resolve()`` or creating with ``tm.createNode()``/
``tm.Node.create()``), tik.maya determines the wrapper class based on Maya's node
inheritance hierarchy.

Maya nodes inherit from multiple base types. For example, a camera node actually inherits
these Maya classes in order:

.. code-block:: text

   ['containerBase', 'entity', 'dagNode', 'shape', 'camera']

tik.maya resolves to the **most specific** (closest) available wrapper type in the
inheritance chain:

1. If a ``Camera`` wrapper exists, the node is wrapped as ``Camera``
2. If not, but a ``ShapeNode`` wrapper exists, it's wrapped as ``ShapeNode``
3. If not, but a ``DagNode`` wrapper exists, it's wrapped as ``DagNode``
4. If none match, it falls back to the base ``Node`` wrapper

.. code-block:: python

   import tik.maya as tm

   # Camera resolves to most specific type available
   camera = tm.resolve("perspShape")
   print(type(camera))  # <class 'tik.maya.types.camera.Camera'>

   # If Camera type didn't exist, it would resolve to ShapeNode
   # If ShapeNode didn't exist, it would resolve to DagNode
   # As a last resort, it would resolve to Node

This ensures you always get the most specific wrapper available for any node type.

Node Lifecycle
--------------

Existence Checking
~~~~~~~~~~~~~~~~~~

Nodes can be deleted, and references can become invalid. Always check existence when needed:

.. code-block:: python

   cube = tm.Transform.create(name="tempCube")

   # Check if node still exists in Maya
   if cube.exists():
       print(f"{cube.name} exists")

   # Delete the node
   cube.delete()

   # Now it doesn't exist
   print(cube.exists())  # False

.. tip::
   tik.maya tracks nodes primarily using :class:`maya.api.OpenMaya.MObject` handles
   for performance, with UUID as a backup for restoration when the MObject link breaks
   (such as after undo/redo operations). This means your Python reference stays valid
   even if the node is recreated.

Renaming Nodes
~~~~~~~~~~~~~~

Node wrappers survive renames because they track by MObject (with UUID backup), not name:

.. code-block:: python

   cube = tm.Transform.create(name="originalName")
   print(cube.name)  # "originalName"

   # Rename the node
   cube.rename("newName")
   print(cube.name)  # "newName"

   # The wrapper still works - UUID hasn't changed
   cube.translate_x = 10.0  # Works perfectly

Duplicating Nodes
~~~~~~~~~~~~~~~~~

Duplicate nodes and get new wrappers:

.. code-block:: python

   original = tm.Transform.create(name="original")
   original.translate = (1, 2, 3)

   # Duplicate returns a new wrapper
   duplicate = original.duplicate()
   print(duplicate.name)  # "original1"
   print(duplicate.translate)  # (1.0, 2.0, 3.0)

Working with Different Node Types
----------------------------------

Transform Nodes
~~~~~~~~~~~~~~~

Transforms are the most common node type. They support hierarchies and transformations:

.. code-block:: python

   import tik.maya as tm

   # Create transforms
   parent = tm.Transform.create(name="parent")
   child = tm.Transform.create(name="child")

   # Set hierarchy
   child.parent = parent

   # Transform operations
   parent.translate = (0, 5, 0)
   parent.rotate = (0, 45, 0)
   parent.scale = (2, 2, 2)

   # Matrices
   local_matrix = parent.matrix
   world_matrix = parent.world_matrix

   # Freeze transformations
   parent.freeze(translate=True, rotate=True, scale=True)

Joint Nodes
~~~~~~~~~~~

.. warning::
   **Work in Progress**: Joint-specific API is still being developed.

Joints extend Transform with rigging-specific features:

.. code-block:: python

   # Create a joint chain
   root = tm.Joint.create(name="spine_root")
   mid = tm.Joint.create(name="spine_mid", parent=root)
   tip = tm.Joint.create(name="spine_tip", parent=mid)

   # Joint-specific properties
   root.radius = 2.0
   root.draw_style = 2  # Bone drawing style

   # Position joints
   mid.translate = (0, 5, 0)
   tip.translate = (0, 5, 0)

Shape Nodes
~~~~~~~~~~~

Shape nodes contain geometry or visual data. They always have a parent transform:

.. code-block:: python

   # Create shapes
   mesh = tm.Mesh.create("polyCube", name="myCube")
   curve = tm.Curve.create("circle", name="myCircle")
   locator = tm.Locator.create(name="myLocator")

   # Access parent transforms
   mesh.transform.translate = (0, 0, 0)
   curve.transform.rotate = (0, 90, 0)

   # Shape-specific operations
   vertices = mesh.vertices(space="world")
   cvs = curve.cvs(space="object")

Mesh-Specific Operations
^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   mesh = tm.resolve("pCubeShape1")

   # Get vertex positions
   verts = mesh.vertices(space="world")
   print(f"Vertex count: {len(verts)}")

   # Find vertices in radius
   nearby = mesh.vertices_in_radius(center=(0, 0, 0), radius=5.0)

   # Unlock normals
   mesh.unlock_normals(soften=True)

Curve-Specific Operations
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   curve = tm.resolve("curveShape1")

   # Get CV positions
   cvs = curve.cvs(space="world")

   # Query curve properties
   degree = curve.degree
   form = curve.form

Camera Nodes
~~~~~~~~~~~~

.. code-block:: python

   # Create a camera (returns the shape)
   cam = tm.Camera.create(name="myCamera")

   # Camera-specific properties
   cam.focal_length = 50.0
   cam.horizontal_film_aperture = 1.417

   # Position the camera via its transform
   cam.transform.translate = (10, 10, 10)
   cam.transform.rotate = (0, 45, 0)

Dependency Graph Nodes
~~~~~~~~~~~~~~~~~~~~~~

Some nodes don't participate in the DAG hierarchy. They're pure dependency graph nodes:

.. code-block:: python

   import maya.cmds as cmds

   # Create a dependency node
   node_name = cmds.createNode("multiplyDivide")
   mult_node = tm.resolve(node_name)

   # Access as a generic Node wrapper
   mult_node["input1X"].value = 5.0
   mult_node["input2X"].value = 2.0
   print(mult_node["outputX"].value)  # 10.0

Node Selection and Queries
---------------------------

Listing Scene Nodes
~~~~~~~~~~~~~~~~~~~

tik.maya provides ``tm.ls()`` (or ``tm.list_scene_nodes()``), a wrapper for ``cmds.ls()``
that returns resolved tik.maya objects:

.. code-block:: python

   import tik.maya as tm

   # List all transforms in the scene (returns tik.maya objects)
   transforms = tm.ls(type="transform")
   for transform in transforms:
       print(f"{transform.name} - {type(transform)}")

   # List all joints
   joints = tm.ls(type="joint")

   # You can use all cmds.ls arguments
   selected = tm.ls(selection=True)
   visible = tm.ls(visible=True)

   # Using the snake_case alias
   all_meshes = tm.list_scene_nodes(type="mesh")

Selecting Nodes
~~~~~~~~~~~~~~~

Use ``tm.select()`` (or ``tm.select_nodes()``) to select nodes:

.. code-block:: python

   import tik.maya as tm

   # Create some nodes
   cube = tm.Transform.create(name="myCube")
   sphere = tm.Transform.create(name="mySphere")

   # Select nodes
   tm.select([cube, sphere])

   # Using the snake_case alias
   tm.select_nodes([cube])

   # Supports cmds.select kwargs
   tm.select([cube], add=True)  # Add to selection

Hierarchy Navigation
--------------------

Working with Parents and Children
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   transform = tm.resolve("pCube1")

   # Get parent
   parent = transform.parent
   if parent:
       print(f"Parent: {parent.name}")

   # Set parent
   new_parent = tm.resolve("group1")
   transform.parent = new_parent

   # Get children
   for child in transform.children:
       print(f"Child: {child.name}")

   # Get all descendants recursively
   all_descendants = transform.collect_hierarchy(include_self=False)

Filtering Hierarchy
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   root = tm.resolve("rig_root")

   # Get only joints in hierarchy
   joints = root.collect_hierarchy(node_types=["joint"], include_self=True)

   # Get only transforms (excluding joints)
   transforms = root.collect_hierarchy(node_types=["transform"], include_self=False)

Working with Shapes
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   transform = tm.resolve("pCube1")

   # Get all shape nodes under this transform
   for shape in transform.shapes:
       print(f"Shape: {shape.name} - {type(shape)}")

   # Typically just one shape, but can be multiple
   if transform.shapes:
       mesh = transform.shapes[0]
       print(mesh.vertices())

Node Comparison and Identity
-----------------------------

.. code-block:: python

   cube1 = tm.resolve("pCube1")
   cube2 = tm.resolve("pCube1")

   # Same node, different wrapper instances
   print(cube1 == cube2)  # True (compares UUIDs)

   # Direct UUID comparison
   print(cube1.uuid == cube2.uuid)  # True

   # Check if it's the same type
   print(isinstance(cube1, tm.Transform))  # True

Common Patterns
---------------

Batch Operations on Nodes
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Get all selected transforms
   nodes = tm.ls(selection=True)

   # Lock all scale attributes
   for node in nodes:
       if isinstance(node, tm.Transform):
           for axis in ["scaleX", "scaleY", "scaleZ"]:
               node[axis].locked = True
               node[axis].visible = False

Summary
-------

- **Nodes** are Python wrappers around Maya scene nodes, tracked by MObject (with UUID backup)
- **Types** in tik.maya correspond to Maya node types (Transform, Joint, Mesh, etc.)
- The **registry** automatically returns the correct wrapper class based on inheritance order
- Three creation methods: ``Type.create()``, ``tm.createNode()``, and ``tm.Node.create()``
- Use ``tm.resolve()`` to wrap existing nodes
- Node wrappers survive renames and namespace changes
- Different node types have specialized properties and methods
- Navigate hierarchies with ``parent``, ``children``, and ``collect_hierarchy()``
- Use ``tm.ls()`` and ``tm.select()`` for scene queries and selection

For detailed information on working with node attributes, see :doc:`working_with_plugs`.
