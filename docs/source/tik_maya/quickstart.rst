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

Dynamic cmds Wrapping
---------------------

**tik.maya dynamically wraps the entire maya.cmds module**, allowing you to use it as a 
drop-in replacement for ``maya.cmds`` with minimal changes to existing scripts:

.. code-block:: python

   # Traditional approach
   import maya.cmds as cmds
   
   # Simply change the import!
   import tik.maya as tm
   
   # Now all your cmds calls work through tik.maya
   tm.polyCube(name="myCube")
   tm.xform("myCube", translation=(1, 2, 3))
   tm.setAttr("myCube.translateX", 5.0)

Under the hood, tik.maya uses `PEP 562 <https://peps.python.org/pep-0562/>`_ (module-level 
``__getattr__``) to intercept attribute access. When you call ``tm.polyCube()``, it 
dynamically proxies to ``maya.cmds.polyCube()`` while intelligently wrapping inputs and outputs.

**Key benefits:**

- **Seamless migration:** Existing scripts can switch namespaces with minimal changes
- **Automatic type resolution:** Commands that return nodes automatically return typed tik.maya wrappers
- **Selective overrides:** Critical functions like ``createNode`` use optimized OpenMaya API implementations for better performance
- **Input cleaning:** tik.maya objects are automatically converted to strings for Maya commands
- **Output wrapping:** Maya node names are automatically wrapped as tik.maya objects when appropriate

.. code-block:: python

   # Example: This returns a tik.maya.Transform object, not a string
   cube = tm.polyCube(name="myCube")[0]
   print(type(cube))  # <class 'tik.maya.types.transform.Transform'>
   
   # You can immediately use object-oriented methods
   cube.translate = (1, 2, 3)
   cube["visibility"].value = False

.. tip::
   **Want to see more?** Check out the ``snippets/comparisons/`` folder in the repository 
   for many side-by-side examples comparing ``maya.cmds`` and ``tik.maya`` approaches. 
   Example ``08_cylinder_rig`` demonstrates how an entire rigging script can work by 
   simply changing ``import maya.cmds as cmds`` to ``import tik.maya as tm``!

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

Plugs also support mathematical operators to create dependency graph nodes:

.. code-block:: python

   # Arithmetic operations create Maya nodes automatically
   driver = tm.Transform.create(name="driver")
   follower = tm.Transform.create(name="follower")
   
   driver["tx"].value = 10.0
   
   # Create addDL and multDL nodes, then connect to follower
   (driver["tx"] * 2.0 + 5) >> follower["ty"]
   print(follower["ty"].value)  # 25.0

.. tip::
   For comprehensive coverage of plug operations including all mathematical operators,
   connections, and advanced patterns, see :doc:`guides/working_with_plugs`.

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

Advanced Example: Controllers and Panels
----------------------------------------

This example combines a controller role, the control shape library, hierarchy
utilities, and a panel construct to build a small rig preview setup. The shape
library returns a list of available shape names that you can pass into
``Controller.create``. The panel accepts a camera name, camera shape, or wrapper
(``"persp"`` refers to Maya's default perspective camera) along with a window
resolution in pixels.

.. code-block:: python

   import tik.maya as tm
   from tik.maya.roles.controller import Controller
   from tik.maya.utils.control_shapes import ControlShapeLibrary
   from tik.maya.constructs import Panel

   # Build a simple joint chain
   root_joint = tm.Joint.create(name="spine_root")
   mid_joint = tm.Joint.create(name="spine_mid", parent=root_joint)
   end_joint = tm.Joint.create(name="spine_end", parent=mid_joint)

   # Browse available shapes in the library
   shape_library = ControlShapeLibrary.get_instance()
   available_shapes = shape_library.list_shapes()
   print(available_shapes)  # ["Circle", "Square", "CubePin", ...]

   # Create a controller with a library shape
   if not available_shapes:
       raise RuntimeError("No control shapes found in the library.")
   shape_name = available_shapes[0]
   ctrl = Controller.create(name="spine_ctrl", shape=shape_name, size=2.0)
   ctrl.color = (0.9, 0.2, 0.2)

   # Align and connect to the joint chain
   ctrl.transform.snap_to(root_joint, position=True, rotation=True)
   ctrl.transform["translate"] >> root_joint["translate"]
   ctrl.transform["rotate"] >> root_joint["rotate"]

   # Lock scale attributes to prevent unintended joint scaling
   # collect_hierarchy returns wrapped DAG nodes under the root.
   for joint in root_joint.collect_hierarchy(node_types=["joint"], include_self=True):
       for axis in ["scaleX", "scaleY", "scaleZ"]:
           joint[axis].locked = True
           joint[axis].visible = False

   # Spawn a dedicated preview panel
   panel = Panel(camera="persp", resolution=(1280, 720), title="Rig Preview")
   panel.display_textures = True
   panel.grid = False

Next Steps
----------

- Read :doc:`why_tik_maya` to understand the design philosophy
- Explore :doc:`/architecture/core_concepts` for the architecture
- Browse the :doc:`/autoapi/index` for complete API details
