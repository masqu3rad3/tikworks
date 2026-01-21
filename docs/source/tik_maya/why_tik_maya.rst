Why tik.maya?
=============

Maya scripting with ``maya.cmds`` is powerful but has pain points that compound in
larger projects. tik.maya addresses these directly while maintaining Maya's flexibility.

The Problem with ``maya.cmds``
------------------------------

**String-based node references break easily**

.. code-block:: python

   # Using maya.cmds
   import maya.cmds as cmds

   cube = cmds.polyCube(name="myCube")[0]
   cmds.setAttr(f"{cube}.translateX", 5)

   # If something renames the node...
   cmds.rename(cube, "renamedCube")

   # Your reference is now broken
   cmds.setAttr(f"{cube}.translateX", 10)  # Error! "myCube" doesn't exist

**Verbose, repetitive code**

.. code-block:: python

   # Lock and hide attributes requires multiple calls
   cmds.setAttr("pCube1.scaleX", lock=True)
   cmds.setAttr("pCube1.scaleX", keyable=False)
   cmds.setAttr("pCube1.scaleX", channelBox=False)

**No type safety**

.. code-block:: python

   # Typos only discovered at runtime
   cmds.setAttr("pCube1.tranlsateX", 5)  # Misspelled!

How tik.maya Solves This
-------------------------

UUID-Based Tracking
~~~~~~~~~~~~~~~~~~~

tik.maya tracks nodes by UUID, not names. References stay valid through renames,
namespacing, and re-parenting.

.. code-block:: python

   import tik.maya as tm

   cube = tm.resolve("myCube")
   cube.translate_x = 5

   # Rename works seamlessly
   cube.rename("renamedCube")
   cube.translate_x = 10  # Still works!

Under the hood, tik.maya uses :class:`maya.api.OpenMaya.MObject` as the primary
handle for performance, with UUID fallback for safety.

Concise, Readable Code
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Lock and hide in one line
   cube["scaleX"].locked = True
   cube["scaleX"].visible = False

   # Or batch operations
   for attr in ["scaleX", "scaleY", "scaleZ"]:
       cube[attr].locked = True
       cube[attr].visible = False

   # Connect with operators
   driver["translate"] >> cube["translate"]

Pythonic and Type-Safe
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Properties for state, methods for actions
   cube.visibility = False
   cube.freeze(translate=True, rotate=True)

   # Automatic type resolution
   mesh = tm.resolve("pCubeShape1")  # Returns Mesh
   joint = tm.resolve("joint1")      # Returns Joint

   # IDE autocomplete and type hints work
   cube.  # Shows: translate, rotate, freeze(), snap_to(), etc.

Procedural Math Networks
~~~~~~~~~~~~~~~~~~~~~~~~

Build dependency graphs using Python operators:

.. code-block:: python

   driver = tm.Transform.create(name="driver")
   follower = tm.Transform.create(name="follower")

   # Arithmetic creates and connects utility nodes automatically
   (driver["tx"] * 2.0 + 5) >> follower["ty"]

Side-by-Side Comparison
-----------------------

**Connecting attributes:**

.. code-block:: python

   # maya.cmds
   cmds.connectAttr("driver.translateX", "driven.translateX", force=True)
   cmds.connectAttr("driver.translateY", "driven.translateY", force=True)
   cmds.connectAttr("driver.translateZ", "driven.translateZ", force=True)

   # tik.maya
   driver["translate"] >> driven["translate"]

**Creating and positioning:**

.. code-block:: python

   # maya.cmds
   loc = cmds.spaceLocator(name="myLocator")[0]
   cmds.setAttr(f"{loc}.translate", 1, 2, 3, type="double3")

   # tik.maya
   loc = tm.Locator.create(name="myLocator")
   loc.transform.translate = (1, 2, 3)

When to Use What
----------------

**Use tik.maya when:**

- Building tools that manipulate scene objects
- Writing rigging scripts needing reliable references
- You want maintainable, readable code

**Consider raw API when:**

- Performance-critical inner loops (though tik.maya is fast)
- Operations tik.maya doesn't wrap yet

.. note::
   tik.maya and ``cmds`` coexist. Use ``node.name`` to pass tik.maya objects
   to ``cmds`` functions.

Summary
-------

tik.maya combines the simplicity of ``maya.cmds`` with the robustness of
``maya.api.OpenMaya``, wrapped in a Pythonic interface. Write less code,
catch errors earlier, and stop worrying about node names.
