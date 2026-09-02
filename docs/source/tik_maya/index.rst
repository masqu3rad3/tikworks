tik.maya
========

``tik.maya`` is a wrapper around ``maya.cmds`` and the OpenMaya API that lets
you write Maya code the way you write Python: objects instead of strings,
properties instead of ``getAttr``/``setAttr`` pairs, operators instead of
``connectAttr``.

.. code-block:: python

   import tik.maya as tm

   joints = tm.Joint.chain([(0, 10, 0), (5, 10, -1), (10, 10, 0)], name_pattern="arm_{index}")
   handle = tm.IkHandle.create(joints[0], joints[-1], solver="ikRPsolver", name="arm_ikh")

   measure = tm.Measure.create(joints[0], handle)
   stretch = measure.ratio_plug().maximum(1.0)            # never shorter than rest
   for joint in joints[1:]:
       (joint["tx"].value * stretch) >> joint["tx"]        # live stretch, one line per bone

Three ideas carry the whole package. Everything else is detail.

**A node is an object that tracks the node, not its name.** Wrappers hold an
OpenMaya handle backed by the node's UUID, so ``cube.rename("hip")`` does not
break ``cube``. You stop threading strings through your code.

**An attribute is a Plug.** ``node["translateX"]`` gives you an object with a
``value``, lock and keyable state, and connection methods. ``a >> b`` connects,
``a + b`` creates the node that adds them and hands you its output plug.

**Types describe, roles mean, constructs assemble.** ``Transform``, ``Joint`` and
``Mesh`` say what a Maya node *is*. ``Controller`` says what a transform *means*.
``MatrixConstraint``, ``SpaceSwitch`` and ``Ribbon`` assemble several nodes into
one thing you can name.

.. figure:: /_static/screenshots/maya_plug_math_network.png
   :class: screenshot
   :alt: Node Editor view of the network created by a plug arithmetic expression

   What ``(driver["tx"] * 2.0 + 5) >> follower["ty"]`` leaves in the Node Editor.

Where to start
--------------

.. grid:: 1 1 2 2
   :gutter: 3

   .. grid-item-card:: Why not just cmds?
      :link: why_tik_maya
      :link-type: doc

      What breaks in string-based code, and what tik.maya does about it.

   .. grid-item-card:: Quickstart
      :link: quickstart
      :link-type: doc

      The core moves in ten minutes.

   .. grid-item-card:: Guides
      :link: guides/nodes
      :link-type: doc

      Nodes, plugs, transforms and joints, shapes, controllers, constructs,
      deformers, metadata.

   .. grid-item-card:: Cheat sheet
      :link: cheatsheet
      :link-type: doc

      ``cmds`` on the left, tik.maya on the right.

What is in the box
------------------

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Where
     - What
   * - ``tik.maya.core``
     - ``Node``, ``DagNode``, ``ShapeNode``, ``Plug``, the type registry,
       ``resolve()``, the ``cmds`` passthrough, metadata (``node.meta``), the
       ``attribute`` and ``naming`` helpers, decorators (``undo``,
       ``keepselection``), deformer weight containers.
   * - ``tik.maya.types``
     - ``Transform``, ``Joint``, ``IkHandle``, ``Mesh``, ``Curve``, ``Nurbs``,
       ``Locator``, ``Camera``, ``Light``, ``SkinCluster``, ``BlendShape``.
   * - ``tik.maya.roles``
     - ``Controller``: a transform with curve shapes, a colour and a tag.
   * - ``tik.maya.constructs``
     - ``MatrixConstraint``, ``MatrixSwitch``, ``SpaceSwitch``, ``MatrixBlend``,
       ``Measure``, ``SoftIk``, ``ChainLengths``, ``AimFrame``, ``AngleBetween``,
       ``Remap``, ``MatrixSpline``, ``Ribbon``, ``Panel``.
   * - ``tik.maya.utils``
     - The controller shape library and a two-way tik.maya / ``cmds`` code
       converter.
   * - ``tik.maya.data``
     - The shipped controller shapes, one JSON file and one thumbnail each.

The public surface is re-exported from ``tik.maya`` itself, so
``import tik.maya as tm`` is all most scripts need. Roles and utilities are
imported from their modules: ``from tik.maya.roles.controller import Controller``.
