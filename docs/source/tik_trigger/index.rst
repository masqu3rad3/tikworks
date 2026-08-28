tik.trigger
===========

Modular rigging framework built on ``tik.maya``.

Concepts
--------

* **Module** — declares the guides it needs, its plugs/sockets and its settings,
  and implements ``draw_guides(ctx)`` and ``build(ctx)``.
* **Guides** — tagged joints in the scene (``node.meta["trg_*"]``). The scene is
  the source of truth; a session file only stores a snapshot.
* **Builder** — reads the guide instances, builds them parents-first, attaches
  each child's socket to a parent plug, then keeps/hides/deletes the guides.
* **Actions** — an ordered, serializable pipeline (``kinematics`` is one of them).
* **RigSession** — the ``.trg`` document: guide snapshot + actions + metadata.

Write a module in 50 lines
--------------------------

.. code-block:: python

   import tik.maya as tm
   from tik.trigger.core import FloatField, Guides, IntField, Module, register_module


   @register_module("fkchain")
   class FkChain(Module):
       label = "FK Chain"
       guides = Guides("root", multi="segment", min=1, max=50)
       plugs = ("root", "end")
       sockets = ("root",)

       segments = IntField(3, min=1, max=50)
       spacing = FloatField(5.0, min=0.01)
       controller_size = FloatField(2.0, min=0.01)

       def guide_count(self):
           return self.segments

       def draw_guides(self, ctx):
           previous = ctx.joint("root", (0, 0, 0))
           for index in range(self.segments):
               offset = self.spacing * (index + 1) * ctx.side_mult
               previous = ctx.joint("segment", (offset, 0, 0), index=index, parent=previous)

       def build(self, ctx):
           guides = [ctx.guide("root"), *ctx.guides("segment")]
           joints = tm.Joint.chain(
               [tuple(node.world_position) for node in guides],
               name_pattern=ctx.name("{index}", suffix="jnt"),
               parent=ctx.groups.joints,
           )
           socket = tm.Transform.create(name=ctx.name("root", suffix="socket"),
                                        parent=ctx.groups.controllers.long_name)
           socket.align_to(joints[0])
           ctx.socket("root", socket)

           parent = socket
           for index, joint in enumerate(joints[:-1]):
               controller = ctx.controller(f"fk{index}", size=self.controller_size,
                                           parent=parent, match=joint)
               controller.transform.create_offset_group(name=ctx.name(f"fk{index}", suffix="offset"))
               tm.MatrixConstraint.create(controller.transform, joint, maintain_offset=True)
               parent = controller.transform

           for joint in joints:
               ctx.deform_joint(joint)
           ctx.plug("root", joints[0])
           ctx.plug("end", joints[-1])

The framework creates the groups, applies the naming convention, tags every
node, handles side mirroring, parents the module under the rig root and
attaches it to its parent module.

Scripting
---------

.. code-block:: python

   import tik.trigger as trigger
   from tik.trigger.core import ParentRef, get_module

   backend = trigger.maya_backend()
   body = backend.create_guides(get_module("base")(name="body"))
   arm = backend.create_guides(get_module("arm")(name="arm", side="L"),
                               parent=ParentRef(body.instance_id, "root"))
   # ... move the guides ...
   trigger.Builder(backend).build(rig_name="hero", afterlife="keep")

   session = trigger.RigSession(backend)
   session.snapshot_guides()
   session.add_action("kinematics")
   session.save("D:/rigs/hero.trg")

UI
--

.. code-block:: python

   import tik.trigger.ui
   tik.trigger.ui.show()

Tests
-----

``tests/unit/test_*_trigger.py`` (core with a fake backend, Maya backend),
``tests/integration/trigger`` (full pipeline), ``tests/ui`` (Qt, run with
``TIK_TESTS_NO_MAYA=1``).
