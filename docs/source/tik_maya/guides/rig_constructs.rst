Rig Constructs
==============

``tik.maya`` ships generic rigging building blocks. None of them know about
guides, modules or sessions — they are plain Maya setups any tool can use.

Metadata (``Node.meta``)
------------------------

Typed metadata stored as hidden ``tikMeta_<key>`` string attributes:

.. code-block:: python

   import tik.maya as tm

   joint = tm.Joint.create(name="root")
   joint.meta["kind"] = "guide"
   joint.meta["settings"] = {"segments": 3}
   tm.find_by_meta("kind", "guide", node_type="joint")

Attribute helpers
-----------------

.. code-block:: python

   from tik.maya import attribute

   attribute.add_separator(ctrl, "settings")
   stretch = attribute.add_float(ctrl, "stretch", default=1.0, min=0.0, max=2.0)
   attribute.lock_and_hide(ctrl, ["sx", "sy", "sz", "v"])
   attribute.add_proxy(other_ctrl, stretch)

Naming mechanics
----------------

.. code-block:: python

   from tik.maya import naming

   naming.unique_name("arm")                      # "arm1" if "arm" exists
   naming.format_name("upArm", 0, suffix="jnt", side="L")   # "L_upArm_0_jnt"

Joints and IK handles
---------------------

.. code-block:: python

   joints = tm.Joint.chain([(0, 0, 0), (3, 0, -1), (6, 0, 0)], name_pattern="arm_{index}")
   handle = tm.IkHandle.create(joints[0], joints[-1], solver="ikRPsolver")
   handle.pole_vector(pole_ctrl)
   mirrored = joints[0].mirror(mirror_axis="x", search="L_", replace="R_")

MatrixConstraint
----------------

Matrix based parent constraint with joint-orient compensation, parent
compensation and per-axis skips. Accepts a node, a matrix plug, or a list of
drivers (averaged).

.. code-block:: python

   tm.MatrixConstraint.create(ctrl, joint, maintain_offset=True, skip_scale="xyz")

MatrixSwitch / SpaceSwitch
--------------------------

.. code-block:: python

   switch = tm.SpaceSwitch.create(hand_ctrl, [chest_ctrl, root_ctrl], labels=["chest", "root"])
   switch.attr.value = 1          # follow chest
   switch.add_space(head_ctrl, label="head")

``MatrixSwitch`` is the lower level building block (``blendMatrix`` + condition
nodes) when you need a switch without the enum/offset-group conveniences.

Measure
-------

.. code-block:: python

   measure = tm.Measure.create(shoulder, wrist)
   ratio = measure.ratio_plug(global_scale_plug)   # 1.0 at rest length
   ratio >> up_arm["scaleX"]

Ribbon
------

.. code-block:: python

   ribbon = tm.Ribbon.create(shoulder, elbow, name="upArm", joint_count=5, controller_count=1)
   ribbon.pin_start(shoulder_ctrl)
   ribbon.pin_end(elbow_ctrl)
   ribbon.deformer_joints      # skin to these
   ribbon.scale_switch.value = 0.0   # disable stretch scaling

IkFkChain
---------

.. code-block:: python

   chain = tm.IkFkChain.create(joints, name="arm")
   chain.switch.value = 0.0    # FK
   chain.fk_joints[0].rotate = (0, 0, 45)
   chain.switch.value = 1.0    # IK
   chain.ik_handle.translate = (4, 2, 0)
   chain.pole_vector(pole_ctrl)
   chain.fk_visibility >> fk_ctrl_group["visibility"]
