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

**MObject-First Performance**
   tik.maya keeps an :class:`maya.api.OpenMaya.MObject` handle as the primary
   reference for fast API operations. If the handle becomes stale, it re-resolves
   it from the UUID, keeping wrappers safe across undo, delete, and rename
   operations.

**Less Code, More Clarity**
   Common operations that take multiple ``cmds`` calls become single property
   assignments or method calls.

**Type Safety**
   Get IDE autocomplete, type hints, and meaningful error messages instead of
   runtime string errors.

**Pythonic Design**
   Properties for state, methods for actions. Iteration, comprehensions, and
   operators work naturally.

For a detailed comparison with ``maya.cmds``, see :doc:`why_tik_maya`.

Core Components
---------------

**Node** (:class:`~tik.maya.Node`)
   Base wrapper for all Maya nodes. Handles existence validation, MObject tracking
   with UUID backup, name caching, and attribute access via ``[]``.

**Plug** (:class:`~tik.maya.core.node.Plug`)
   Represents an attribute on a node. Properties for ``value``, ``locked``,
   ``keyable``, ``visible``. Supports connection operators (``>>``, ``<<``, ``//``)
   and arithmetic operators (``+``, ``-``, ``*``, ``/``, ``**``, ``%``) that
   automatically create Maya utility nodes. Build procedural dependency networks
   using natural Python syntax.

**Transform** (:class:`~tik.maya.Transform`)
   DAG transform wrapper with ``translate``, ``rotate``, ``scale`` properties,
   plus ``freeze()``, ``snap_to()``, and matrix access.

**Shape Types** (Mesh, Curve, Nurbs, Light, Locator)
   Shape-specific wrappers with geometry methods like ``vertices()``, ``cvs()``.

**Roles** (Controller, etc.)
   Semantic wrappers that add meaning to nodes - Controller marks a transform
   as an animation control with shape management.

For architecture details, see :doc:`/architecture/core_concepts`.

Dynamic cmds Wrapping Architecture
----------------------------------

One of tik.maya's most powerful features is its **flexible dynamic wrapping structure** 
that makes it a drop-in replacement for ``maya.cmds`` while enabling fine-tuning and 
optimizations where needed.

How Dynamic Wrapping Works
~~~~~~~~~~~~~~~~~~~~~~~~~~~

tik.maya leverages **PEP 562** (module-level ``__getattr__``) to dynamically intercept 
attribute access:

.. code-block:: python

   def __getattr__(name):
       """Called when user asks for tm.something that isn't explicitly imported."""
       if hasattr(cmds, name):
           return partial(_proxy_wrapper, name)
       raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

When you call ``tm.polyCube()``, Python checks if ``polyCube`` is explicitly defined in 
the module. If not, it calls ``__getattr__("polyCube")``, which creates a wrapper that:

1. **Sanitizes inputs:** Converts tik.maya objects to strings
2. **Calls the real Maya command:** Executes ``maya.cmds.polyCube()``
3. **Wraps outputs:** Converts returned node names to typed tik.maya objects

This means **any cmds function works through tik.maya automatically**, even functions 
we haven't explicitly wrapped yet.

Selective Overrides for Performance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

While the dynamic wrapper handles most commands, tik.maya can **override specific 
functions** for better performance or enhanced functionality. For example, ``createNode`` 
is mapped to use Maya's OpenMaya API directly:

.. code-block:: python

   @alias("createNode")
   def create_node(node_type: str, name=None, parent=None):
       """Create a new node using optimized OpenMaya API."""
       # Try DAG modifier first (faster than cmds)
       full_name = apicommon.create_node_with_dag_modifier(
           node_type, name=name, parent=parent
       )
       return resolve(full_name)

This approach provides:

- **Speed:** API-level node creation is faster than cmds
- **Elegance:** Cleaner function signature without Maya's complex flags
- **Extensibility:** We can add custom logic without changing Maya

The Balance of Flexibility
~~~~~~~~~~~~~~~~~~~~~~~~~~~

This architecture brings together four key qualities:

**Fine-tuning**
   Override specific commands with custom implementations while leaving others untouched

**Speed**
   Use OpenMaya API for performance-critical operations (node creation, attribute queries)

**Elegance**
   Pythonic interfaces with properties, operators, and clean method signatures

**Extensibility**
   Add new functionality without modifying Maya or breaking existing code

.. code-block:: python

   # Example: This entire script works by changing the import
   import tik.maya as tm  # Instead of: import maya.cmds as cmds
   
   # All cmds functions work
   cube = tm.polyCube(name="myCube")[0]
   tm.xform(cube, translation=(1, 2, 3))
   
   # But you also get object-oriented benefits
   cube.translate = (5, 6, 7)
   cube["visibility"].locked = True
   
   # And mathematical operators for dependency graph
   driver = tm.spaceLocator()[0]
   (driver["translateX"] * 2.0 + 5) >> cube["translateY"]

.. note::
   The dynamic wrapping is transparent and opt-in. You can use ``tm.polyCube()`` 
   just like ``cmds.polyCube()``, or you can use ``tm.Mesh.create("polyCube")`` 
   for the object-oriented interface. Both work!

Next Steps
----------

- **New to tik.maya?** Start with :doc:`quickstart` for hands-on examples
- **Want deeper knowledge?** See :doc:`guides/working_with_nodes` and :doc:`guides/working_with_plugs`
- **Need API details?** Browse the :doc:`/autoapi/index`
