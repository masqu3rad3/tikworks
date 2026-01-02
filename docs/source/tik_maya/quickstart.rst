Quickstart
==========

This guide gets you working with tik.maya in five minutes.

Installation
------------

tik.maya is part of the TikWorks repository. Add the ``src`` directory to your Maya Python path:

.. code-block:: python

   import sys
   sys.path.append("/path/to/tikworks/src")

   import tik.maya as tm

Wrapping Existing Nodes
-----------------------

Use :func:`tik.maya.resolve` to wrap any existing Maya node:

.. code-block:: python

   import tik.maya as tm

   # Wrap a node by name
   cube = tm.resolve("pCube1")

   # The returned object is typed — Transform, Mesh, Joint, etc.
   print(type(cube))  # <class 'tik.maya.types.transform.Transform'>

tik.maya automatically returns the correct wrapper class based on the Maya node type.

Working with Attributes
-----------------------

Access attributes using bracket notation:

.. code-block:: python

   # Get a Plug object for the attribute
   plug = cube["translateX"]

   # Read and write values
   plug.value = 5.0
   print(plug.value)  # 5.0

   # Or use the property shortcut on transforms
   cube.translate_x = 10.0

Attribute plugs have useful properties:

.. code-block:: python

   # Lock/unlock
   cube["translateX"].locked = True
   cube["translateX"].lock()    # equivalent

   # Visibility in channel box
   cube["translateX"].visible = False

   # Keyable state
   cube["translateX"].keyable = False

Connecting Attributes
---------------------

Use the ``>>`` operator for connections:

.. code-block:: python

   locator = tm.resolve("locator1")
   cube = tm.resolve("pCube1")

   # Connect translate
   locator["translate"] >> cube["translate"]

   # Chain connections
   a["output"] >> b["input"] >> c["input"]

Or use the explicit method:

.. code-block:: python

   locator["translateX"].connect(cube["translateX"])

Creating Nodes
--------------

Use the ``create()`` class method on type classes:

.. code-block:: python

   # Create a transform
   grp = tm.Transform.create(name="myGroup")

   # Create a joint
   jnt = tm.Joint.create(name="arm_jnt")

   # Create a locator (returns the shape node)
   loc = tm.Locator.create(name="myLocator")
   loc.transform.translate = (1, 2, 3)  # Access parent transform

   # Create geometry (pass the Maya command as first argument)
   sphere = tm.Mesh.create("polySphere", name="mySphere")
   plane = tm.Nurbs.create("nurbsPlane", name="myPlane")

.. note::
   Shape types like ``Locator``, ``Mesh``, and ``Curve`` return shape node wrappers.
   Access the parent transform via the ``.transform`` property.

DAG Hierarchy
-------------

Navigate the scene hierarchy:

.. code-block:: python

   transform = tm.resolve("pCube1")

   # Get parent
   parent = transform.parent

   # Set parent
   transform.parent = tm.resolve("group1")

   # Get children
   for child in transform.children:
       print(child.name)

   # Get shapes
   for shape in transform.shapes:
       print(shape.name, type(shape))

Transform Operations
--------------------

Common transform operations are built in:

.. code-block:: python

   # Read transforms
   print(cube.translate)    # MVector
   print(cube.rotate)       # MVector
   print(cube.scale)        # MVector

   # Write transforms
   cube.translate = (1, 2, 3)
   cube.rotate = (0, 45, 0)
   cube.scale = (2, 2, 2)

   # Snap to another transform
   cube.snap_to(target, position=True, rotation=True)

   # Freeze transformations
   cube.freeze(translate=True, rotate=True, scale=True)

   # Get matrices
   local_matrix = cube.matrix
   world_matrix = cube.world_matrix

Node Lifecycle
--------------

.. code-block:: python

   # Check existence
   if cube.exists():
       print("Node exists")

   # Rename (reference stays valid!)
   cube.rename("newCubeName")
   print(cube.name)  # "newCubeName"

   # Delete
   cube.delete()

Adding Custom Attributes
------------------------

.. code-block:: python

   # Add an attribute
   cube.add_attr("customFloat", attributeType="float", defaultValue=0.0)

   # Access it
   cube["customFloat"].value = 1.5

   # Delete it
   cube.delete_attr("customFloat")

Working with Shapes
-------------------

tik.maya provides shape-specific functionality:

.. code-block:: python

   # Mesh operations
   mesh = tm.resolve("pCubeShape1")
   vertices = mesh.vertices(space="world")
   nearby = mesh.vertices_in_radius((0, 0, 0), radius=1.0)
   mesh.unlock_normals(soften=True)

   # Curve operations
   curve = tm.resolve("curveShape1")
   cvs = curve.cvs(space="world")

Next Steps
----------

- Read :doc:`why_tik_maya` to understand the design philosophy
- Explore :doc:`/architecture/core_concepts` for the architecture
- Browse the :doc:`/autoapi/index` for complete API details
