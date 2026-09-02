Nodes and the registry
======================

A tik.maya node is a small Python object standing in for one Maya node. This
page explains what it holds, how the right class is chosen for it, the three
ways to make one, and how the ``cmds`` passthrough fits in.

What a wrapper holds
--------------------

.. code-block:: python

   cube = tm.resolve("pCube1")
   cube.m_obj        # an OpenMaya MObject -- the fast handle
   cube.uuid         # the node's UUID -- the durable identity
   cube.name         # "pCube1"           (short name, re-read from the scene)
   cube.long_name    # "|pCube1"          (full DAG path)
   cube.partial_name # shortest unique name, safe to hand to cmds
   cube.type         # "transform"        (the Maya node type)

Two things are cached: the ``MObject`` and the UUID. The name is never cached.
Every ``cube.name`` goes back to the scene, which is why a wrapper survives
renames and reparenting. If the ``MObject`` stops being valid, for example after
an undo re-created the node, the wrapper re-resolves it by UUID and carries on.
When the node is really gone, ``exists()`` returns ``False`` and name lookups log
a warning and return ``None``.

.. note::

   Two wrappers of the same node are two objects. ``tm.resolve("a") is
   tm.resolve("a")`` is ``False``, and ``==`` compares object identity too. To
   ask "same node?", compare ``uuid``.

The type hierarchy
------------------

.. code-block:: text

   Node                       any dependency node; the fallback for unregistered types
   ├── DagNode                parent / children / visibility / display colour
   │   ├── Transform          translate, rotate, scale, matrices, snap_to, aim_at...
   │   │   ├── Joint          radius, joint_orient, preferred_angle, chain(), mirror()
   │   │   └── IkHandle       start_joint, end_effector, pole_vector()
   │   └── ShapeNode          .transform, and resolves from a transform name too
   │       ├── Mesh           vertices(), vertex colours, normals
   │       ├── Curve          cvs(), line_width, scale_points()
   │       ├── Nurbs          cvs()
   │       ├── Locator
   │       ├── Camera         lens, aim, up, fit()
   │       └── Light
   └── Deformer               weight I/O shared by the deformer types
       ├── SkinCluster
       └── BlendShape

Each class is registered for one Maya node type with ``@register("joint")``.
Registration is what makes :func:`~tik.maya.core.registry.resolve` work.

How resolve() picks a class
---------------------------

``resolve(name)`` asks Maya for the node's type. If a wrapper is registered for
that exact type it is used. Otherwise the node's inheritance chain is walked from
the most specific type upwards until a registered one is found, and ``Node`` is
the last resort.

.. code-block:: python

   tm.resolve("perspShape")        # camera -> Camera
   tm.resolve("pCubeShape1")       # mesh -> Mesh
   tm.resolve("pCube1")            # transform -> Transform
   tm.resolve("multiplyDivide1")   # no wrapper -> Node, still fully usable

   # a light type nobody registered, say 'areaLight':
   # ['containerBase', 'entity', 'dagNode', 'shape', 'renderLight', 'light', 'areaLight']
   tm.resolve("areaLightShape1")   # walks up to 'light' -> Light

Passing a wrapper to ``resolve()`` returns it unchanged, which is why functions
in tik.maya accept "a node or a name" everywhere.

Three ways to create a node
---------------------------

**The type's own** ``create()`` is the most explicit and the most common:

.. code-block:: python

   grp = tm.Transform.create(name="rig_grp", parent="world_grp")
   jnt = tm.Joint.create(name="hip", parent=grp, position=(0, 10, 0), radius=2.0)
   loc = tm.Locator.create(name="aim")                    # cmds.spaceLocator
   sphere = tm.Mesh.create("polySphere", name="ball", radius=2)
   plane = tm.Nurbs.create("nurbsPlane", name="strip")
   cam = tm.Camera.create(name="shotCam")

Shape types take the Maya *command* that makes them (``"polySphere"``,
``"nurbsPlane"``) because that is what decides the shape. ``Curve.create``
forwards straight to ``cmds.curve``:

.. code-block:: python

   line = tm.Curve.create(point=[(0, 0, 0), (0, 5, 0)], degree=1, name="line")

**The generic** ``create_node()`` mirrors ``cmds.createNode`` and is the way to
make utility nodes. It goes through OpenMaya's modifiers (DAG first, then DG),
falls back to ``cmds.createNode`` for the odd type that needs it, and returns the
right wrapper:

.. code-block:: python

   mult = tm.create_node("multiplyDivide", name="stretch_mult")   # Node
   grp = tm.createNode("transform", name="offset")                # camelCase alias, Transform

**The** ``cmds`` **passthrough** is there for everything else. Node-producing
commands come back wrapped:

.. code-block:: python

   cube = tm.polyCube(name="box")[0]            # Transform
   copies = tm.duplicate(cube)                  # [Transform]
   shapes = tm.listRelatives(cube, shapes=True) # [Mesh]

How the passthrough works
-------------------------

``tik.maya`` defines a module-level ``__getattr__`` (PEP 562). Any name you ask
for that the package does not define itself is looked up on ``maya.cmds``. The
call is then proxied:

1. **Arguments are cleaned.** tik.maya objects, including those nested in lists
   and dicts, are replaced by their names.
2. **The real command runs.** Nothing is intercepted or reinterpreted.
3. **Results are wrapped, for a known list of commands.** ``polyCube``,
   ``duplicate``, ``group``, ``listRelatives``, ``listConnections``,
   ``spaceLocator``, ``joint``, ``skinCluster``, ``ikHandle`` and about 120
   others (the ``NODE_FACTORIES`` list in ``tik.maya.core.constants``) return
   wrappers. Anything else returns exactly what ``cmds`` returned.

So ``tm.xform(cube, query=True, translation=True)`` returns a list of floats and
``tm.setAttr(f"{cube}.tx", 5)`` works because ``str(cube)`` is its name. A
handful of commands are overridden rather than proxied so they can do better:
``createNode`` (API modifiers, undoable), ``ls`` (wrapped output) and
``select`` (cleaned input).

Lifecycle
---------

.. code-block:: python

   node.exists()                 # True while the node is in the scene
   node.rename("new_name")       # undoable, returns the wrapper
   node.duplicate(**cmds_kwargs) # a wrapper for the copy
   node.delete()
   node.delete_history()         # cmds.delete(constructionHistory=True)

   node.add_attr("stretch", attributeType="double", defaultValue=1.0, keyable=True)
   node.has_attr("stretch")      # True
   node.delete_attr("stretch")

``rename`` refuses to run on a node that no longer exists (it raises
``RuntimeError``). Most other methods simply pass the name through and let Maya
report the error.

DAG nodes
---------

Anything in the outliner is a ``DagNode`` and gets hierarchy and display
helpers:

.. code-block:: python

   child.parent                       # wrapper or None at world level
   child.parent = grp                 # keep the world position (default)
   child.set_parent(grp, relative=True)   # keep the local values instead
   child.parent = None                # to world
   grp.children                       # [wrappers]
   grp.visibility = False             # alias: grp.v
   grp.bounding_box                   # OpenMaya.MBoundingBox, world space
   grp.color = 17                     # index colour ...
   grp.color = (1.0, 0.5, 0.0)        # ... or RGB (overrideRGBColors)
   grp.color = None                   # drawing override off
   grp.select()

Reparenting goes through ``MDagModifier`` and compensates the local transform so
the node stays where it was in world space, the same result as
``cmds.parent`` without ``relative``.

Shape nodes
-----------

``ShapeNode`` wrappers know about their transform, and accept either name when
constructed:

.. code-block:: python

   mesh = tm.resolve("pCubeShape1")
   mesh.transform            # <Transform 'pCube1'>
   mesh.shape                # itself, so transform-or-shape code reads the same

   tm.Mesh("pCube1")         # given the transform, wraps its first shape

Setting ``shape.parent`` moves the shape under another transform (``cmds.parent
-shape`` in spirit); a shape cannot be parented to the world.

Listing and selection
---------------------

.. code-block:: python

   tm.ls(type="joint")                     # [Joint, Joint, ...]
   tm.ls(selection=True)                   # whatever is selected, wrapped
   tm.list_scene_nodes(type="mesh")        # the snake_case name of the same thing

   tm.select(jnt, grp)                     # arguments are cleaned to names
   tm.select(clear=True)

For metadata-based lookups (``find_by_meta``) see :doc:`metadata_and_helpers`.
