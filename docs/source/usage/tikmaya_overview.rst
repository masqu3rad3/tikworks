tik.maya Overview
=================

tik.maya is a modern Python wrapper for ``maya.cmds`` that brings object-oriented
design, type safety, and robust node tracking to Maya scripting.

.. note::
   tik.maya is under active development. The API may evolve as features land.

What is tik.maya?
-----------------

tik.maya wraps Maya nodes in lightweight Python classes. Instead of passing strings
to ``cmds`` functions, you work with typed objects that understand Maya's DAG and
dependency graph.

.. code-block:: python

   import tik.maya as tm

   # Wrap an existing node - registry returns the correct class
   cube = tm.resolve("pCube1")  # Returns Transform

   # Attribute access is object-oriented
   cube["translateX"].value = 5.0
   cube["translateX"].locked = True

   # Connect with operators
   driver["translate"] >> cube["translate"]

   # Node references survive renames
   cube.rename("myNewCube")
   cube.translate_x = 10  # Still works!

Key Benefits
------------

**UUID-Based Node Tracking**
   tik.maya tracks nodes by their internal UUID, not string names. Your references
   stay valid even when nodes are renamed, re-parented, or namespaced.

**Less Code, More Clarity**
   Common operations that take multiple ``cmds`` calls become single property
   assignments or method calls.

**Type Safety**
   Get IDE autocomplete, type hints, and meaningful error messages instead of
   runtime string errors.

**Pythonic Design**
   Properties for state, methods for actions. Iteration, comprehensions, and
   operators work naturally.

For a detailed comparison with ``maya.cmds``, see :doc:`why_tikmaya`.

Core Components
---------------

**Node** (:class:`~tik.maya.Node`)
   Base wrapper for all Maya nodes. Handles existence validation, UUID tracking,
   name caching, and attribute access via ``[]``.

**Plug** (:class:`~tik.maya.core.node.Plug`)
   Represents an attribute on a node. Properties for ``value``, ``locked``,
   ``keyable``, ``visible``. Supports ``>>`` operator for connections.

**Transform** (:class:`~tik.maya.Transform`)
   DAG transform wrapper with ``translate``, ``rotate``, ``scale`` properties,
   plus ``freeze()``, ``snap_to()``, and matrix access.

**Shape Types** (Mesh, Curve, Nurbs, Light, Locator)
   Shape-specific wrappers with geometry methods like ``vertices()``, ``cvs()``.

**Roles** (Controller, etc.)
   Semantic wrappers that add meaning to nodes - Controller marks a transform
   as an animation control with shape management.

For architecture details, see :doc:`/architecture/core_concepts`.

Quick Example
-------------

.. code-block:: python

   import tik.maya as tm
   from tik.maya.roles.controller import Controller

   # Create a controller with a circle shape
   ctrl = Controller.create(name="arm_ctrl", shape="circle", size=2.0)

   # Position it
   ctrl.translate = (5, 10, 0)

   # Lock scale attributes
   for axis in ["scaleX", "scaleY", "scaleZ"]:
       ctrl.node[axis].locked = True
       ctrl.node[axis].visible = False

   # Create a joint and connect
   jnt = tm.Joint.create(name="arm_jnt")
   ctrl.node["translate"] >> jnt["translate"]

See :doc:`quickstart` for more examples.

The TikWorks Ecosystem
----------------------

tik.maya is the foundation layer of TikWorks. Future tools build on top of it:

- **tik.maya** - Core wrapper library (you are here)
- **tik.shared** - Cross-cutting utilities supporting all Tik packages
- **Trigger** - Rigging framework (coming soon)

By building on tik.maya, all TikWorks tools share:

- Consistent API patterns
- Robust node tracking
- Type-safe operations
- Pythonic design
