Why not just cmds?
==================

``maya.cmds`` is fine for a ten-line script. The trouble starts when the script
grows into a tool: every node is a string, every attribute is a string with a
dot in it, and every connection is a function call with two of those strings.
tik.maya exists because three specific things kept going wrong.

Names are not identities
------------------------

``cmds`` gives you names, and names change. Rename a node, move it under a
namespace, reparent it so its long path changes, and every variable that held
the old string is now pointing at nothing.

.. tab-set::

   .. tab-item:: maya.cmds

      .. code-block:: python

         cube = cmds.polyCube(name="myCube")[0]
         cmds.rename(cube, "hip_geo")
         cmds.setAttr(f"{cube}.translateX", 10)   # RuntimeError: myCube does not exist

   .. tab-item:: tik.maya

      .. code-block:: python

         cube = tm.polyCube(name="myCube")[0]
         cube.rename("hip_geo")
         cube.translate_x = 10                     # fine: the wrapper follows the node

A wrapper holds an OpenMaya ``MObject`` and the node's UUID. The ``MObject`` is
the fast path; if it goes stale (undo can do that), the wrapper looks the node up
again by UUID. You get API-level speed with a safety net.

Every operation is three calls
------------------------------

Locking an attribute and hiding it from the channel box is a routine rigging
chore. In ``cmds`` it is repetitive enough that everyone writes a helper for it,
and every studio's helper is slightly different.

.. tab-set::

   .. tab-item:: maya.cmds

      .. code-block:: python

         for attr in ("scaleX", "scaleY", "scaleZ"):
             cmds.setAttr(f"{ctrl}.{attr}", lock=True)
             cmds.setAttr(f"{ctrl}.{attr}", keyable=False, channelBox=False)

   .. tab-item:: tik.maya

      .. code-block:: python

         for attr in ("sx", "sy", "sz"):
             ctrl[attr].locked = True
             ctrl[attr].visible = False

Node networks are invisible in the code
---------------------------------------

The maths of a rig lives in utility nodes. Written with ``cmds`` it is a wall of
``createNode``, ``setAttr`` and ``connectAttr`` in which the actual formula is
nowhere to be seen. tik.maya lets you write the formula and creates the nodes for
you.

.. tab-set::

   .. tab-item:: maya.cmds

      .. code-block:: python

         mult = cmds.createNode("multDoubleLinear")
         cmds.connectAttr(f"{driver}.translateX", f"{mult}.input1")
         cmds.setAttr(f"{mult}.input2", 2.0)
         add = cmds.createNode("addDoubleLinear")
         cmds.connectAttr(f"{mult}.output", f"{add}.input1")
         cmds.setAttr(f"{add}.input2", 5.0)
         cmds.connectAttr(f"{add}.output", f"{follower}.translateY")

   .. tab-item:: tik.maya

      .. code-block:: python

         (driver["tx"] * 2.0 + 5) >> follower["ty"]

The nodes are exactly the ones you would have made by hand, the graph is the
same, and the line says what it computes.

You can switch one import at a time
-----------------------------------

tik.maya does not ask you to rewrite anything. Every ``cmds`` function is
reachable through ``tm``: ``tm.polyCube``, ``tm.xform``, ``tm.skinCluster`` all
call the real command. Arguments that are tik.maya objects are turned into names
on the way in, and commands that create nodes hand you wrappers on the way out.

.. code-block:: python

   import tik.maya as tm      # was: import maya.cmds as cmds

   geo = tm.polyCylinder(radius=2, height=10, name="main_geo")[0]   # a Transform
   tm.xform(geo, translation=(0, 5, 0))                              # a cmds call, unchanged
   geo["visibility"].locked = True                                    # an object call, new

The repository's ``snippets/comparisons/08_cylinder_rig`` folder holds a spline
IK cylinder rig written once against ``cmds`` and once against ``tm`` with
nothing but the import changed. Migration is a decision you make per line, not
per project.

Where cmds still wins
---------------------

- **Raw speed in inner loops.** Wrapping has a cost. For a loop over 50,000
  vertices, drop to OpenMaya directly; tik.maya does the same internally where it
  matters, in ``Mesh.vertices()`` for example.
- **Commands tik.maya does not know return nodes for.** The passthrough wraps the
  output of a fixed list of node-creating commands (``polyCube``, ``duplicate``,
  ``listRelatives``, ``group``, and so on). Anything else returns whatever
  ``cmds`` returned. Pass a wrapper's ``.name`` or ``.long_name`` into ``cmds``
  when you need to.

The comparison in one table
---------------------------

.. list-table::
   :header-rows: 1
   :widths: 22 26 26 26

   * -
     - ``maya.cmds``
     - ``maya.api.OpenMaya``
     - ``tik.maya``
   * - Node identity
     - Strings. Break on rename.
     - ``MObject`` / ``MDagPath``. Robust, verbose.
     - ``MObject`` with a UUID fallback. Robust, one line.
   * - Attribute access
     - ``getAttr`` / ``setAttr`` with dotted strings
     - ``MPlug`` and function sets
     - ``node["attr"].value``
   * - Connections
     - ``connectAttr(a, b, force=True)``
     - ``MDGModifier.connect``
     - ``a >> b``
   * - Utility networks
     - Create, set, connect, repeat
     - The same, lower level
     - ``(a * 2 + b) >> c``
   * - Undo
     - Yes
     - Only if you write the command
     - Yes. API-level edits go through an undo bridge.
   * - Editor support
     - None. Typos surface at runtime.
     - Some
     - Completion, type hints, readable errors

Next: :doc:`quickstart`.
