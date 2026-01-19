Why tik.maya?
=============

Maya scripting with ``maya.cmds`` works, but it has pain points that compound in larger projects.
tik.maya addresses these directly.

The Problem with ``maya.cmds``
------------------------------

**String-based node references are fragile**

In vanilla Maya scripting, everything is a string:

.. code-block:: python

   # Using maya.cmds
   import maya.cmds as cmds

   cube = cmds.polyCube(name="myCube")[0]
   cmds.setAttr(f"{cube}.translateX", 5)

   # Later, something renames the node...
   cmds.rename(cube, "renamedCube")

   # Now your original reference is broken!
   cmds.setAttr(f"{cube}.translateX", 10)  # Error! "myCube" doesn't exist

This is a constant source of bugs in production scripts. Nodes get renamed:

- By users working in the scene
- By programmatic operations (parenting, namespacing)
- Internally by Maya during operations

**Verbose, repetitive code**

Common tasks require multiple ``cmds`` calls:

.. code-block:: python

   # Lock and hide an attribute (cmds)
   cmds.setAttr("pCube1.scaleX", lock=True)
   cmds.setAttr("pCube1.scaleX", keyable=False)
   cmds.setAttr("pCube1.scaleX", channelBox=False)

   # Connect two attributes (cmds)
   cmds.connectAttr("locator1.translate", "pCube1.translate", force=True)

**No type safety**

You only discover typos at runtime:

.. code-block:: python

   # This typo won't be caught until the script runs
   cmds.setAttr("pCube1.tranlsateX", 5)  # Misspelled!

How tik.maya Solves These Problems
----------------------------------

1. UUID-Based Tracking
~~~~~~~~~~~~~~~~~~~~~~

**tik.maya tracks nodes by UUID, not names.**

.. code-block:: python

   import tik.maya as tm

   cube = tm.resolve("myCube")
   cube.translate_x = 5

   # Rename the node - in Maya or programmatically
   cube.rename("renamedCube")

   # Your reference still works!
   cube.translate_x = 10  # No error - tik.maya tracks by UUID

Under the hood, tik.maya stores the node's UUID when you wrap it. When you access
properties, it resolves the current name from the UUID. Renames, re-parenting,
namespace changes — none of them break your reference.

tik.maya now keeps the :class:`maya.api.OpenMaya.MObject` as its primary handle
for speed. Each access verifies that the handle still points at the same UUID.
If it does not, tik.maya reconstructs the handle from the stored UUID, giving
you a fast path with a safe fallback.

.. code-block:: python

   import tik.maya as tm
   from maya.api import OpenMaya

   cube = tm.resolve("pCube1")
   m_object = cube.m_obj  # Validated MObject handle
   print(OpenMaya.MFnDependencyNode(m_object).typeName)

   # If the handle becomes stale, tik.maya re-resolves from UUID.
   if cube.exists():
       print(cube.long_name)

2. Less Code, More Readable
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The same operations become concise and clear:

.. code-block:: python

   # Lock and hide an attribute (tik.maya)
   cube["scaleX"].locked = True
   cube["scaleX"].visible = False

   # Or chain multiple attributes
   for attr in ["scaleX", "scaleY", "scaleZ"]:
       cube[attr].locked = True
       cube[attr].visible = False

   # Connect two attributes with the >> operator
   locator["translate"] >> cube["translate"]

3. Pythonic and Object-Oriented
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

tik.maya uses Python conventions:

.. code-block:: python

   # Properties for state
   cube.visibility = False
   print(cube.translate)

   # Methods for actions
   cube.freeze(translate=True, rotate=True)
   cube.snap_to(target)

   # Iteration and comprehensions work naturally
   children = [child for child in transform.children if child.visibility]

4. Type Support and IDE Completion
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Because tik.maya uses classes with defined properties and methods:

- Your IDE provides autocomplete suggestions
- Type hints catch errors before runtime
- Docstrings are always available

Assuming ``import tik.maya as tm``:

.. code-block:: python

   cube = tm.resolve("pCube1")  # Returns Transform
   cube.  # IDE shows: translate, rotate, scale, freeze(), snap_to(), etc.

5. Automatic Type Resolution
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

tik.maya's registry system automatically wraps nodes with the correct class:

.. code-block:: python

   mesh = tm.resolve("pCubeShape1")  # Returns Mesh
   joint = tm.resolve("joint1")      # Returns Joint
   curve = tm.resolve("curveShape1") # Returns Curve

Each type exposes methods relevant to that node type. A ``Mesh`` has ``vertices()``,
a ``Curve`` has ``cvs()``, a ``Transform`` has ``freeze()``.

Side-by-Side Comparison
-----------------------

**Creating and positioning a locator:**

Assuming ``import tik.maya as tm``:

.. code-block:: python

   # maya.cmds
   loc = cmds.spaceLocator(name="myLocator")[0]
   cmds.setAttr(f"{loc}.translate", 1, 2, 3, type="double3")
   cmds.setAttr(f"{loc}.visibility", False)

.. code-block:: python

   import tik.maya as tm
   # tik.maya (loc is the shape, .transform is its parent)
   loc = tm.Locator.create(name="myLocator")
   loc.transform.translate = (1, 2, 3)
   loc.transform.visibility = False

**Connecting attributes:**

.. code-block:: python

   # maya.cmds
   cmds.connectAttr("driver.translateX", "driven.translateX", force=True)
   cmds.connectAttr("driver.translateY", "driven.translateY", force=True)
   cmds.connectAttr("driver.translateZ", "driven.translateZ", force=True)

   # tik.maya
   driver["translate"] >> driven["translate"]

**Working with transforms after renaming:**

.. code-block:: python

   # maya.cmds - fragile
   cube_name = cmds.polyCube()[0]
   # ... 100 lines later, cube_name might be invalid ...

.. code-block:: python

   import tik.maya as tm
   # tik.maya - robust
   cube = tm.resolve(cmds.polyCube()[0])
   # ... 100 lines later, cube still works even if renamed ...

When to Use tik.maya
--------------------

**Use tik.maya (``import tik.maya as tm``) when:**

- Building tools that manipulate existing scene objects
- Writing rigging scripts that need reliable node references
- Creating pipelines where nodes may be renamed or re-parented
- You want cleaner, more maintainable code

**Consider raw ``cmds`` or `OpenMaya`` when:**

- Performance-critical inner loops with thousands of iterations. tik.maya is still faster than cmds in most cases, but raw API calls can be quicker.
- One-off scripts where readability doesn't matter
- Operations that tik.maya doesn't wrap yet. Flag them for future support!

.. note::
   tik.maya and ``cmds`` can coexist. Use ``node.name`` or ``node.long_name`` to pass
   tik.maya objects to ``cmds`` functions when needed.

Summary
-------

+---------------------------+----------------------------------+-------------------------------------+-------------------------------------------+
| Pain Point                | ``maya.cmds``                    | ``maya.api.OpenMaya``               | **tik.maya**                              |
+===========================+==================================+=====================================+===========================================+
| Node references           | Strings — break on rename        | MObject/MDagPath handles — robust   | MObj/UUID-backed — survives renames       |
+---------------------------+----------------------------------+-------------------------------------+-------------------------------------------+
| Code verbosity            | Multiple calls per operation     | Verbose boilerplate (fn sets, plugs)| Concise properties and methods            |
+---------------------------+----------------------------------+-------------------------------------+-------------------------------------------+
| Performance               | Moderate                         | Fastest (No Undo / Not crash safe   | Fast (With Undo support and more stable   |
+---------------------------+----------------------------------+-------------------------------------+-------------------------------------------+
| Type safety               | None — errors at runtime         | Stronger typing via API classes     | IDE completion, type hints                |
+---------------------------+----------------------------------+-------------------------------------+-------------------------------------------+
| API style                 | Procedural, flag-heavy           | Low-level, explicit, handle-based   | Pythonic, object-oriented                 |
+---------------------------+----------------------------------+-------------------------------------+-------------------------------------------+
| Debugging                 | String matching errors           | Object inspection via function sets | Object inspection, clear errors           |
+---------------------------+----------------------------------+-------------------------------------+-------------------------------------------+

Tik.maya aims to bring the best parts of both ``maya.cmds`` (simple, quick workflows) and
``maya.api.OpenMaya`` (speed, robust handles) into one Pythonic API.

Tik.maya lets you write less code, catch errors earlier, and stop worrying about node names.
