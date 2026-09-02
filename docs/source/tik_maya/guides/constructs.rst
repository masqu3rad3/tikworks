Rig constructs
==============

A construct is a small, named node network with a Python object in front of it.
``MatrixConstraint`` is one ``multMatrix`` and one ``decomposeMatrix`` wired a
particular way; ``SpaceSwitch`` is an enum attribute, an offset group and a
``blendMatrix`` with a ``condition`` per space. You could build each by hand. The
construct builds it the same way every time, gives it a name, and can delete it
again.

Constructs are *mechanism only*. None of them creates a controller, names an
animator-facing attribute, or knows about left and right. That is the
animator-opinion rule from :doc:`/architecture/overview`; policy lives in
tik.trigger's systems and modules.

Every construct follows the same shape:

.. code-block:: python

   thing = tm.SomeConstruct.create(...)   # builds the network, undoable as one step
   thing.some_plug                        # the plugs you wire onward
   thing.nodes                            # (where meaningful) every node it made
   thing.delete()                         # tears the network down, leaves your nodes

Arguments that expect a node accept a wrapper, a node name, or a
:class:`~tik.maya.roles.controller.Controller`. Arguments that expect a matrix
accept a node (its ``worldMatrix[0]`` is used) or a matrix plug.

MatrixConstraint
----------------

A matrix-based parent constraint: ``driver.worldMatrix`` through ``multMatrix``
and ``decomposeMatrix`` into the driven node's translate, rotate and scale.

.. code-block:: python

   tm.MatrixConstraint.create(ctrl, joint)                          # maintain offset by default
   tm.MatrixConstraint.create(ctrl, joint, maintain_offset=False)
   tm.MatrixConstraint.create(ctrl, joint, skip_scale="xyz")        # leave scale alone
   tm.MatrixConstraint.create([a, b], joint)                        # two drivers, averaged
   tm.MatrixConstraint.create(blend["outputMatrix"], joint)         # any matrix plug
   tm.MatrixConstraint.create(ctrl, joint, cutoff=rig_root)         # remove a parent's transform

What it does that a hand-rolled version usually forgets:

- **Joint orient compensation.** When the driven node is a joint, a second strand
  divides ``jointOrient`` and the parent's world matrix back out, so the joint's
  rotate channels stay clean and the offset is honoured.
- **Parent compensation, live.** The driven node's ``parent.worldInverseMatrix``
  is connected, not baked. This is why tik.trigger can create bind joints in
  their final hierarchy and never reparent them.
- **Per-axis skips**, ``skip_translate``, ``skip_rotate``, ``skip_scale``, each an
  iterable of ``"x"``, ``"y"``, ``"z"``.

MatrixSwitch and SpaceSwitch
----------------------------

``MatrixSwitch`` drives one transform from one of several targets, chosen by an
integer plug. ``SpaceSwitch`` is the animator-shaped version: an enum attribute,
an offset group inserted above the control, world space as index 0.

.. code-block:: python

   switch = tm.SpaceSwitch.create(
       hand_ctrl, [chest_ctrl, root_ctrl],
       labels=["chest", "root"],       # enum labels; defaults to the node names
       attr_name="space",              # on hand_ctrl unless control= says otherwise
       mode="parent",                  # or "point" / "orient"
       world=True,                     # index 0 is world
   )
   switch.attr.value = 1               # follow chest
   switch.labels                       # ['world', 'chest', 'root']
   switch.add_space(head_ctrl, label="head")
   switch.offset                       # the group the switch drives
   switch.delete()                     # network, offset group and enum all removed

.. figure:: /_static/screenshots/maya_space_switch.png
   :class: screenshot
   :alt: A space enum in the channel box

   The enum a ``SpaceSwitch`` leaves on the control.

Reach for ``MatrixSwitch`` directly when you want the mechanism without the enum
and offset group, for example to drive an intermediate group from an existing
attribute:

.. code-block:: python

   ms = tm.MatrixSwitch.create([a, b, None], driven, control=ctrl["follow"])   # None = world
   ms.add_target(c)
   ms.targets                          # [a, b, None, c]

MatrixBlend
-----------

A continuous, weighted blend of matrices, where ``MatrixSwitch`` is discrete.

.. code-block:: python

   blend = tm.MatrixBlend.create(base_node, [fk_joint, ik_joint], weights=[0.0, 1.0])
   ik_fk_plug >> blend.weight_plug(1)
   blend.output                        # blendMatrix.outputMatrix

Measure
-------

A ``distanceBetween`` node fed by two world matrices, plus the rest distance it
had when created.

.. code-block:: python

   measure = tm.Measure.create(shoulder, wrist)
   measure.distance                    # live distance plug
   measure.initial_distance            # float, captured at creation
   ratio = measure.ratio_plug()        # distance / initial_distance  -> 1.0 at rest
   ratio = measure.ratio_plug(global_scale_plug)   # ... / scale, for scalable rigs

ChainLengths
------------

Per-segment length drivers for a joint chain: ``translateX`` of every joint after
the root becomes ``side_sign * rest * factor1 * factor2 ...``.

.. code-block:: python

   lengths = tm.ChainLengths.create(ik_joints, side_sign=1, name="arm_ik")
   lengths.total_length                # sum of the rest lengths, a plug
   lengths.rest_plugs                  # one writable plug per segment
   lengths.add_factor(stretch_plug)    # multiply every segment
   lengths.add_override(pinned_lengths, weight_plug)   # blend towards explicit lengths

An unbuilt factor is ``1.0``, so stretch and squash can be added independently
and never interact.

SoftIk
------

The exponential approach curve that keeps an IK chain from snapping straight.

.. code-block:: python

   soft = tm.SoftIk.create(root_grp, ik_ctrl, lengths.total_length, name="arm")
   soft.soft_plug                      # softIk distance; 0 disables
   soft.stretch_plug                   # 0 = goal sits at the soft point, 1 = at the control
   soft.goal_matrix                    # world matrix for the ikHandle
   soft.gap_plug                       # stretch * (distance - softened distance)

.. warning::

   ``root`` must be *upstream* of the IK solve. An ``ikRPsolver`` rotates the
   chain's root joint, so passing that joint as ``root`` creates a dependency
   cycle. Pass the group the chain hangs under.

AimFrame
--------

An ``aimMatrix`` that aims one axis at a target and aligns the up axis to
*another* node's axis, so rolling the up target rolls the frame. A static offset
cannot reproduce that.

.. code-block:: python

   frame = tm.AimFrame.create(base, aim_target, up_target, twist_axis="Y", parent=rig_grp)
   frame.matrix                        # aimMatrix.outputMatrix
   frame.transform                     # a transform riding the frame via offsetParentMatrix

AngleBetween and Remap
----------------------

.. code-block:: python

   angle = tm.AngleBetween.create(vector_plug_a, (1, 0, 0))
   angle.angle                         # degrees

   remap = tm.Remap.create(
       angle.angle, input_min=0.0, input_max=90.0, output_min=0.0, output_max=1.0,
       interpolation="smooth",         # none / linear / smooth / spline
       points=[(0.0, 0.0), (0.5, 0.0), (1.0, 1.0)],   # optional ramp shape, 0..1 space
   )
   remap.output

MatrixSpline
------------

A spline of transforms with no geometry at all. Each output rides a
B-spline-weighted blend of the driver matrices through ``offsetParentMatrix``,
oriented by an ``aimMatrix``, with twist interpolated as a plain float so it is
unbounded.

.. code-block:: python

   spline = tm.MatrixSpline.create(
       [start, mid, end], parameters=[0.1, 0.3, 0.5, 0.7, 0.9],
       name="spine", degree=2, twists=[start["twist"], None, end["twist"]],
       up_matrix=up_frame_plug,
   )
   for output in spline.outputs:
       output.transform, output.twist, output.weights

Ribbon
------

A strip of deformer joints between two ends, built on ``MatrixSpline``: start
and end *plug* transforms you pin to your controls, optional mid plugs, and flat
joints with live translate, rotate and scale.

.. code-block:: python

   ribbon = tm.Ribbon.create(shoulder_loc, elbow_loc, name="upArm",
                             joint_count=5, mid_count=1, scaleable=True, preserve_volume=False)
   ribbon.pin_start(shoulder_ctrl)     # MatrixConstraint onto the start plug
   ribbon.pin_end(elbow_ctrl)
   ribbon.pin_mid(0, mid_ctrl)
   ribbon.deformer_joints              # skin to these
   ribbon.start_twist, ribbon.end_twist   # twist plugs on the end plugs
   ribbon.scale_switch.value = 0.0     # stretch scaling off (present when scaleable=True)

.. figure:: /_static/screenshots/maya_ribbon.png
   :class: screenshot
   :alt: A ribbon between two locators

   A five-joint ribbon with one mid plug.

Panel
-----

The odd one out: not a rig network but a torn-off model panel with a camera,
for previews and thumbnail captures.

.. code-block:: python

   panel = tm.Panel(camera="persp", resolution=(1280, 720), title="Rig Preview")
   panel.display_textures = True
   panel.grid = False
   panel.isolate(controls)             # isolate-select these nodes
   panel.fit_view()
   panel.revert()                      # restore the camera's display attributes
   panel.close()

``Panel`` is importable from ``tik.maya.constructs``; it is not re-exported at
the package top level.

Putting three together
----------------------

A stretchy IK arm from the pieces above, with soft IK. This is roughly what
tik.trigger's ``limb`` system does before it adds controllers and the
animator-facing attributes:

.. code-block:: python

   import tik.maya as tm

   joints = tm.Joint.chain([(0, 10, 0), (5, 10, -1), (10, 10, 0)], name_pattern="arm_ik_{index}")
   rig_grp = tm.Transform.create(name="arm_rig_grp")
   joints[0].parent = rig_grp

   ik_ctrl = tm.Transform.create(name="arm_ik_ctrl")
   ik_ctrl.snap_to(joints[-1], rotation=False)
   handle = tm.IkHandle.create(joints[0], joints[-1], name="arm_ikh")

   lengths = tm.ChainLengths.create(joints, name="arm")
   soft = tm.SoftIk.create(rig_grp, ik_ctrl, lengths.total_length, name="arm")
   tm.MatrixConstraint.create(soft.goal_matrix, handle, maintain_offset=False)

   stretch = (soft.gap_plug / lengths.total_length + 1.0)
   lengths.add_factor(stretch)
   soft.soft_plug.value = 1.0
   soft.stretch_plug.value = 1.0

Move ``arm_ik_ctrl`` past the chain's reach: the wrist eases into the limit
instead of popping, then the bones stretch. Every attribute involved is a plain
plug you can expose on a controller however your rig wants.
