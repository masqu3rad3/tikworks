Quickstart
==========

Everything below runs inside Maya (``mayapy`` or an interactive session).

Build a rig from scratch
------------------------

.. code-block:: python

   import tik.trigger as trigger

   trigger.load_plugins()

   session = trigger.Session()             # a new, unsaved .tr
   guides = session.guides                 # this session's guides

   body = guides.add("base", name="body")
   arm = guides.add("arm", side="L", name="arm", parent=body)
   guides.mirror(arm)                      # -> R_arm, inputs mirrored

   session.add("kinematics", "build_rig", rig_name="hero")
   session.save("rigs/hero.tr")
   session.build()

Three things happened that are worth naming:

- ``guides.add(...)`` wrote a module entry into the session's guide document
  **and** drew its guide joints. The document is the record; the joints are a
  rendering of it.
- ``session.add("kinematics", ...)`` appended an action to the pipeline. With no
  ``guides_file`` set it builds this session's own guides.
- ``session.build()`` captured the guide poses from the scene, reset the scene,
  and ran every enabled action in order.

Open, override, rebuild
-----------------------

.. code-block:: python

   from tik import trigger

   rig = trigger.Session.open("rigs/hero_muscle.tr")
   rig.add("import_asset", "import_model", file_path="geo/hero_v02.ma")

   base = rig.add("reference", "baseRig", file="rigs/baseRig.tr")
   base["scripts/head_rotation"].enabled = False       # stored as an override
   base["kinematics"].rig_name = "hero"                # here, not in baseRig.tr

   rig.add("script", "fix", parent=rig["import_model"], code="print(ctx.path)")

   rig.validate()                 # pre-flight problems, no scene changes
   rig.build()                    # reset the scene, run everything
   rig.build(until="kinematics")  # ...stopping after this step
   rig.run("fix")                 # one step, in the current scene, no reset
   rig.save(increment=True)       # hero_muscle_v002.tr

Author guides in the live scene
-------------------------------

.. code-block:: python

   guides = session.guides

   body = guides.add("base", name="body")
   arm = guides.add("arm", side="L", parent=body)

   arm.stretch = False                              # a setting; redraws at once
   arm.set(squash=False, pole_pin=True)             # several at once

   guides.connect("L_arm.root", "body.root")        # module output -> input
   guides.connect("tail.root", "some_jnt")          # any Maya node as a source

   guides.test_build(arm)                           # build just this module
   guides.export("guides/hero.trg")                 # export a guide *library*

.. note::
   Connections are **data**, not scene parenting. Guide joints are never
   parented into each other to express a connection.

Launch the tool
---------------

.. code-block:: python

   import tik.trigger.ui

   tik.trigger.ui.show()

.. seealso::
   :doc:`guides/sessions_and_actions`, :doc:`guides/guides_and_lockstep`,
   :doc:`guides/ui`.
