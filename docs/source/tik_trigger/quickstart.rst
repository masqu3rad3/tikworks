Quickstart
==========

One rig, two ways: first through the window, then the same thing from Python.
Both need Maya; the Python version also runs under ``mayapy``.

In the window
-------------

.. code-block:: python

   import tik.trigger.ui
   tik.trigger.ui.show()

**1. Add a couple of modules.** Open the *Guide Designer* sub-tab. Click *Base*
on the module shelf on the left, then set *Side* to ``L`` and click *Arm*. The
arm's ``root`` input is pre-filled with ``body.root`` because you added it while
``body`` was selected, and its guide joints appear in the viewport, coloured for
the left side.

.. figure:: /_static/screenshots/maya_guides_arm.png
   :class: screenshot
   :alt: Arm guides in the Maya viewport

   The arm's guides: collar, shoulder, elbow, hand and the neutral guide that
   anchors the auto-collar.

**2. Place the guides.** Drag the joints in the viewport. This is ordinary Maya
work, undone with Maya's :kbd:`Ctrl+Z`. Nothing needs to be told about it; the
session reads the poses back whenever it saves or builds.

**3. Mirror.** With ``L_arm`` selected, press *Mirror* on the action bar (or
:kbd:`Ctrl+M`). ``R_arm`` appears with mirrored poses and its connection
rewired to the right-hand equivalents.

**4. Add the build step.** Switch to the *Session* sub-tab and click
*Kinematics* on the action shelf. Leave its ``GuideLayout file`` empty: that
means "build this session's own guides". Set *Rig name* if you like.

**5. Build.** Press *Build rig* (:kbd:`Ctrl+B`). The scene is reset, the actions
run in order, and the arms come out under ``<rig name>_rig``. Press
:kbd:`Ctrl+S` to save the session, guides included.

.. figure:: /_static/screenshots/maya_built_arm.png
   :class: screenshot
   :alt: A built arm in the Maya viewport

   The built arm: collar, IK and pole controllers, the ``ikFk`` and ``limbLock``
   attributes on the IK control.

From Python
-----------

.. code-block:: python

   import tik.trigger as trigger

   trigger.load_plugins()

   session = trigger.Session()                 # new, unsaved
   guides = session.guides                     # this session's guides, in this scene

   body = guides.add("base", name="body")
   arm = guides.add("arm", side="L", name="arm", parent=body)
   guides.mirror(arm)                          # -> R_arm, inputs mirrored

   session.add("kinematics", "build_rig", rig_name="hero")
   session.save("rigs/hero.tr")
   session.build()

Three things happened that are worth naming:

- ``guides.add(...)`` wrote a module entry into the session's guide document
  **and** drew its joints. The document is the record; the joints are a
  rendering of it. ``parent=body`` hangs the joints under the body's root guide
  and pre-fills the arm's primary input with ``body.root``.
- ``session.add("kinematics", ...)`` appended an action to the pipeline. With no
  ``guides_file`` it builds this session's own guides.
- ``session.build()`` captured the guide poses from the scene into the document,
  reset the scene, and ran every enabled action in order.

Change a setting, connect, rebuild
----------------------------------

.. code-block:: python

   arm.stretch = False                      # a module setting; the guides redraw at once
   arm.set(squash=False, pole_pin=True)     # several at once
   arm.settings                             # every effective value

   tail = guides.add("fkchain", name="tail", segments=5)
   guides.connect("tail.root", "body.root")           # module output -> input
   guides.connect("tail.root", "some_locator")        # or any Maya node as a source

   guides.test_build(arm)                   # build only this module, keep the guides
   session.build()                          # the whole pipeline again

Open an existing session, override, rebuild
-------------------------------------------

.. code-block:: python

   from tik import trigger

   rig = trigger.Session.open("rigs/hero_muscle.tr")
   rig.add("import_asset", "import_model", file_path="geo/hero_v02.ma", index=0)

   base = rig.add("reference", "baseRig", file="rigs/baseRig.tr")
   base["scripts/head_rotation"].enabled = False      # stored here as an override
   base["kinematics"].rig_name = "hero"               # baseRig.tr is not touched

   rig.add("script", "fix", parent="import_model", code="print(ctx.path)")

   rig.validate()                  # pre-flight problems, no scene changes
   rig.build()                     # reset the scene, run everything
   rig.build(until="kinematics")   # ...stopping after this step
   rig.run("fix")                  # one step, in the current scene, no reset
   rig.save(increment=True)        # hero_muscle_v002.tr

.. note::

   Connections are **data**, not scene parenting. Guide joints are never parented
   into each other to express a connection; the tree and the graph are two views
   of the same connection list.

Next
----

- :doc:`guides/trigger_window` and :doc:`guides/guide_designer` for everything the
  window does.
- :doc:`guides/sessions_and_actions` and :doc:`guides/guides_and_lockstep` for the
  Python API.
- :doc:`guides/modules_reference` for what each built-in module builds and what
  its settings mean.
