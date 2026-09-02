Transforms and joints
=====================

:class:`~tik.maya.types.transform.Transform` is the wrapper you will hold most
often, and :class:`~tik.maya.types.joint.Joint` extends it with the joint
channels and the chain operations rigging keeps needing.

Channels
--------

The nine transform channels and their short names are properties. Vectors read
back as ``OpenMaya.MVector``, which means you can do vector maths on them
directly.

.. code-block:: python

   node.translate = (0, 10, 0)            # or node.t
   node.rotate = (0, 90, 0)               # or node.r
   node.scale = (1, 1, 1)                 # or node.s
   node.translate_x = 5                   # or node.tx; likewise ty tz rx ry rz sx sy sz

   offset = node.translate - other.translate      # MVector arithmetic
   offset.length()

Matrices come back as ``OpenMaya.MMatrix``:

.. code-block:: python

   node.matrix            # local
   node.world_matrix      # worldMatrix[0]
   node.parent_matrix     # parentMatrix[0]

World-space position and direction
----------------------------------

``world_position`` is the rotate pivot in world space, readable and writable.
``world_axis`` gives a unit vector for one local axis in world space.

.. code-block:: python

   node.world_position                      # MVector
   node.world_position = (10, 0, 0)         # moves the node, whatever its parent does
   node.world_axis("x")                     # MVector, normalised

   node.distance_to(other)                  # float, world space
   tm.Transform.between(a, b, ratio=0.5)    # MVector halfway from a to b

Placing one node against another
--------------------------------

.. code-block:: python

   node.snap_to(target, position=True, rotation=True, scale=False)
   node.align_to(target)                    # snap_to without scale, spelled for reading
   node.aim_at(target, aim_vector=(1, 0, 0), up_vector=(0, 1, 0), world_up=(0, 1, 0))
   node.aim_at(target, world_up_object=up_locator)

``aim_at`` creates a temporary ``aimConstraint``, evaluates it and deletes it,
so what remains is plain rotate values. ``snap_to`` reads the target's world
matrix through OpenMaya, so it is exact and does not care about rotate orders.

Freezing and offset groups
--------------------------

.. code-block:: python

   node.freeze(translate=True, rotate=True, scale=True)   # cmds.makeIdentity apply=True
   offset = node.create_offset_group()                     # "<name>_OFFSET" above the node
   offset = node.create_offset_group(name="arm_ctrl_offset")

The offset group is created at the node's world transform, the node is parented
under it, and the group takes the node's old parent. The node's channels read
zero afterwards, which is the whole point of an offset group.

Walking the hierarchy
---------------------

.. code-block:: python

   node.parent, node.children, node.shapes

   root.collect_hierarchy()                                   # every descendant transform and shape
   root.collect_hierarchy(node_types=["joint"], include_self=True)
   root.collect_hierarchy(max_depth=1)                        # children only
   root.collect_shape_transforms(shape_types=["mesh"])        # transforms that own a mesh

``collect_hierarchy`` walks transforms and appends the shapes it meets; filter by
Maya type name.

Joints
------

.. code-block:: python

   jnt = tm.Joint.create(name="hip", parent=root, position=(0, 10, 0),
                         orientation=(0, 0, 90), radius=1.5)

   jnt.radius = 2.0
   jnt.joint_orient                # (0.0, 0.0, 90.0) in degrees
   jnt.joint_orient = (0, 0, 0)
   jnt.preferred_angle = (0, -30, 0)
   jnt.orient((0, 0, 90))          # cmds.joint -edit -orientation

``position`` in ``create`` is the *local* translation, so a chain built one joint
at a time reads naturally. For world positions use ``chain`` or set
``world_position`` afterwards.

Chains
~~~~~~

.. code-block:: python

   joints = tm.Joint.chain(
       [(0, 10, 0), (5, 10, -1), (10, 10, 0)],
       name_pattern="arm_{index}",       # arm_0, arm_1, arm_2
       parent=root_grp,
       radius=0.8,
       orient=True,                      # X down the chain, Y up, last joint zeroed
   )

   tm.Joint.orient_chain(joints, aim_axis="x", up_axis="y", world_up=(0, 1, 0))
   tm.Joint.orient_chain(joints, reverse_aim=True)      # a mirrored-behaviour side

   ik_joints = tm.Joint.duplicate_chain(joints, prefix="arm_ik", parent=rig_grp)

``duplicate_chain`` copies ``jointOrient``, ``translate``, ``rotate``, ``scale``,
``radius`` **and** ``preferredAngle``. That last one matters: an ``ikRPsolver``
chain with a zero preferred angle can solve onto a flat plane and flip, and
``cmds.duplicate`` is not the problem there, forgetting the angle is.

``reverse_aim`` is how the puppet chain of a right arm gets its "mirrored
behaviour" orientation: the aim axis points back up the chain, so the child's
``translateX`` is negative and the same rotate values pose both sides
symmetrically. Bind skeletons do *not* use it; they keep identical orients on
both sides. :doc:`/tik_trigger/guides/writing_modules` explains where each is
used.

Mirroring
~~~~~~~~~

.. code-block:: python

   right_root = left_root.mirror(mirror_axis="x", search="L_", replace="R_", behavior=True)

A thin wrapper over ``cmds.mirrorJoint``; ``mirror_axis`` picks the plane
(``"x"`` mirrors across YZ).

IK handles
----------

.. code-block:: python

   handle = tm.IkHandle.create(joints[0], joints[-1], solver="ikRPsolver", name="arm_ikh")
   handle.solver             # 'ikRPsolver'
   handle.start_joint        # <Joint 'arm_0'>
   handle.end_effector       # the effector node
   handle.twist              # the twist plug
   handle.pole_vector(pole_ctrl)   # a poleVectorConstraint, returned wrapped

``IkHandle`` is a ``Transform``, so ``handle.parent = ik_ctrl`` and
``handle.translate`` work as on any other node.

.. seealso::

   :doc:`constructs` for ``ChainLengths``, ``SoftIk`` and ``Measure``, which
   are what turn a chain like this into a stretchy limb.
