Quickstart
==========

Ten minutes, one Script Editor tab. Every snippet below runs as written in an
empty scene, in order.

.. code-block:: python

   import tik.maya as tm

Create and wrap nodes
---------------------

Type classes have a ``create()``. Existing nodes are wrapped with
:func:`~tik.maya.core.registry.resolve`, which looks at the Maya node type and
picks the most specific wrapper it knows.

.. code-block:: python

   grp = tm.Transform.create(name="rig_grp")           # Transform
   jnt = tm.Joint.create(name="hip_jnt", parent=grp)   # Joint, already parented
   loc = tm.Locator.create(name="aim_loc")             # Locator (the *shape*)

   cube = tm.polyCube(name="body_geo")[0]              # any cmds command, wrapped result
   same = tm.resolve("body_geo")                       # wrap something that exists
   print(type(same))                                   # <class 'tik.maya.types.transform.Transform'>

Two details are worth knowing on day one:

- Shape types (``Locator``, ``Mesh``, ``Curve``, ``Camera``...) wrap the shape
  node. Their parent transform is one property away: ``loc.transform``.
- ``resolve("body_geo")`` on a transform gives you a ``Transform``;
  ``resolve("body_geoShape")`` gives you a ``Mesh``. Ask for what you mean.

Read and write attributes
-------------------------

Square brackets give you a :class:`~tik.maya.core.plug.Plug`. The plug is where
values, lock state and connections live.

.. code-block:: python

   cube["translateX"].value = 5.0
   print(cube["translateX"].value)          # 5.0

   cube["translate"].value = (1, 2, 3)      # compound attributes take a tuple
   print(cube["translate"].value)           # [(1.0, 2.0, 3.0)]  -- cmds.getAttr's shape

   cube["scaleY"].locked = True
   cube["scaleY"].visible = False           # gone from the channel box
   print(cube["scaleY"].keyable)            # False

Transforms also expose the usual channels as properties. Long and short names
both work, and vectors come back as ``MVector``:

.. code-block:: python

   cube.translate = (0, 10, 0)
   cube.ty                                  # 10.0
   cube.rotate_z = 45
   cube.translate                           # MVector(0, 10, 0)

Connect things
--------------

``>>`` connects left to right and returns the right-hand plug, so connections
chain. ``<<`` goes the other way. ``//`` disconnects.

.. code-block:: python

   loc.transform["translate"] >> cube["translate"]
   loc.transform["rotateY"] >> cube["rotateY"] >> jnt["rotateY"]

   loc.transform["translate"] // cube["translate"]    # broken again (source // destination)

   cube["rotateY"].get_input(plug=True)                # <Plug 'aim_loc.rotateY'>

Do maths with plugs
-------------------

Arithmetic on plugs creates utility nodes and hands you the output plug. The
expression reads like the formula because it is the formula.

.. code-block:: python

   driver = tm.Transform.create(name="driver")
   follower = tm.Transform.create(name="follower")

   driver["tx"].value = 10
   (driver["tx"] * 2.0 + 5) >> follower["ty"]
   print(follower["ty"].value)                          # 25.0

   driver["tx"].value = 20
   print(follower["ty"].value)                          # 45.0  -- it is live

Vectors work too, component-wise, and a few helpers cover what operators cannot
express:

.. code-block:: python

   (driver["translate"] * (1, 1, 0)) >> follower["translate"]   # drop Z

   ratio = driver["tx"] / 10.0
   ratio.clamped(0.0, 1.0) >> follower["sx"]                    # min(max(x, 0), 1)
   driver["ty"].gt(5.0, 1.0, 0.0) >> follower["visibility"]     # if ty > 5 then 1 else 0

Build a hierarchy and place things
----------------------------------

.. code-block:: python

   jnt.parent = grp                 # reparent, world position preserved
   jnt.parent                       # <Transform 'rig_grp'>
   grp.children                     # [<Joint 'hip_jnt'>]

   jnt.snap_to(cube)                # position and rotation, world space
   jnt.aim_at(loc.transform)        # bake an aim, no constraint left behind
   jnt.freeze(translate=False, rotate=True, scale=False)   # cmds.makeIdentity, apply=True

   cube.world_position              # MVector, the rotate pivot in world space
   jnt.distance_to(cube)            # a float

Lifecycle
---------

.. code-block:: python

   cube.rename("torso_geo")         # the variable still works
   cube.exists()                    # True
   cube.duplicate()                 # a new wrapper for the copy
   cube.delete()
   cube.exists()                    # False

Scene queries
-------------

``tm.ls`` and ``tm.select`` are the ``cmds`` commands with wrapped results and
unwrapped arguments:

.. code-block:: python

   for node in tm.ls(type="joint"):
       node["radius"].value = 0.5

   tm.select(grp, jnt)              # tik.maya objects are fine as arguments

Where next
----------

- :doc:`guides/nodes` for what a wrapper is and how the registry chooses a class.
- :doc:`guides/plugs` for every operator, the compound rules, and how connections
  are queried.
- :doc:`guides/constructs` to stop building space switches by hand.
- :doc:`cheatsheet` when you know the ``cmds`` spelling and want the tik.maya one.
