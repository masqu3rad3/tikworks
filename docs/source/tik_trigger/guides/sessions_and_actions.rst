Sessions and actions
====================

:class:`~tik.trigger.session.Session` is the object a TD scripts against: a
``.tr`` document plus the runner that builds it. Actions in it are addressed by
path and edited through :class:`~tik.trigger.session.ActionHandle`, which
exposes an action's settings as attributes.

Open, save, version
-------------------

.. code-block:: python

   from tik import trigger

   rig = trigger.Session()                       # new, unsaved
   rig = trigger.Session.open("rigs/hero.tr")    # or open one

   rig.name            # 'hero.tr', or 'untitled'
   rig.directory       # the folder relative paths resolve against
   rig.is_modified     # True once the document differs from the saved state

   rig.save()                    # to its own path
   rig.save("rigs/other.tr")     # elsewhere; the .tr suffix is enforced
   rig.save(increment=True)      # hero_v002.tr -- the same as rig.increment()

Versioning follows the ``name_v###`` convention. ``increment`` finds the highest
existing number next to the file and writes the next one. ``save`` also stamps
``author``, ``created_at`` and ``modified_at`` into the document's ``meta``.

.. note::

   ``save()`` captures the guide poses from the scene first, so the file can never
   lag the viewport. ``build()`` and ``run()`` do the same.

The action tree
---------------

Actions are addressed by ``/``-separated paths that read like the tree looks.

.. code-block:: python

   rig.add("import_asset", "import_model", file_path="geo/hero_v02.ma")
   rig.add("script", "fix", parent="import_model", code="...")     # nested
   rig.add("script", "later", after="import_model")                # the next sibling
   rig.add("kinematics", "build_rig", index=0)                     # at a position

   rig["import_model"]              # -> ActionHandle
   rig["import_model/fix"]          # nested
   rig.find("nope")                 # -> None instead of raising
   "import_model" in rig            # -> True
   rig.actions                      # the top-level handles
   rig.paths()                      # every path, depth-first
   rig.walk()                       # every handle, referenced ones included

   rig.move("fix", parent=None, index=0)
   rig.rename("fix", "fixup")
   rig.duplicate("fixup")           # 'fixup1' next to it
   rig.remove("fixup1")

Names are unique among siblings; adding a second ``script`` at the same level
gives you ``script1``. Every method accepts a path or a handle.

Settings are attributes
-----------------------

A handle exposes the action's typed fields directly. Writes are validated by the
field, so a bad value fails at assignment rather than at build time:

.. code-block:: python

   step = rig["build_rig"]
   step.rig_name = "hero"                     # validated by the StringField
   step.set(auto_switchers=False, after_build="delete")
   step.enabled = False
   step.settings                              # effective values: defaults + stored
   step.reset("rig_name")                     # back to the default
   step.reset()                               # every field

   step.name, step.type, step.path            # 'build_rig', 'kinematics', 'build_rig'
   step.children                              # nested handles
   step.add("script", "post", code="...")     # add a child

Unknown names raise ``AttributeError`` naming the action type. There is no silent
stash of arbitrary keys.

References and overrides
------------------------

The ``reference`` action runs another session's actions inline. Editing a
referenced action stores an **override in the referencing session**; the
referenced file is never modified.

.. code-block:: python

   base = rig.add("reference", "baseRig", file="rigs/baseRig.tr")

   base.children                    # the referenced rows first, then any local children
   base["kinematics"].is_linked     # True
   base["scripts/head_rotation"].enabled = False      # an override
   base["kinematics"].rig_name = "hero"               # an override
   base["kinematics"].reset()                         # drop this action's overrides

Two things follow from "overrides live here, not there":

- You cannot ``add`` an action inside a reference. Open the referenced session
  and add it there.
- ``version`` on the reference (``"latest"``, ``"pinned"`` or an explicit
  ``v003``) decides which file on disk is expanded. Relative paths inside the
  referenced session keep resolving against *its* folder.

Validate, build, run
--------------------

.. code-block:: python

   rig.validate()            # ['import_model: file_path: file not found (geo/hero_v02.ma)']
   rig.steps()               # the Steps a build would run, in order
   rig.build()               # reset the scene, run every enabled action
   rig.build(until="build_rig")
   rig.build(reset_scene=False)
   rig.run("fix")            # one action in the current scene, no reset

``validate()`` is pre-flight only: it plans the run, collects the planner's
problems (a missing referenced file, for instance) and asks every action for its
own. It never touches the scene. ``build()`` and ``run()`` return
``StepResult`` records with the path, status, duration and error message of each
step; the UI's status dots are drawn from those.

Events
------

A session has an :class:`~tik.trigger.core.events.EventBus`. The runner emits
``progress``, ``log`` and ``error`` events plus one per step
(``step_started``, ``step_finished``, ``step_failed``, ``step_skipped``); the
log widget and the progress bar in the window are subscribers.

.. code-block:: python

   rig.events.subscribe("log", lambda message, level="info": print(level, message))
   rig.events.subscribe("step_finished", lambda **payload: print(payload))

Undo
----

Structural edits go on the session's own stack, the one the Trigger window's
:kbd:`Ctrl+Z` uses. Guide edits land on the same stack, because a guide edit is
a document edit.

.. code-block:: python

   rig.can_undo
   rig.undo()
   rig.redo()

The stack keeps the last 50 states. ``Session.touch()`` is what records a step;
it is public because the guide layer calls it.

Guides from the session
-----------------------

``rig.guides`` is this session's :class:`~tik.trigger.guides.scene.GuideScene`,
bound to the session so every edit is recorded on its undo stack and saved with
its file. :doc:`guides_and_lockstep` covers it. The scene-boundary verbs live on
the session:

.. code-block:: python

   rig.capture_guides()             # scene -> document (poses and guide attrs)
   rig.checkout_guides()            # document -> scene; refuses another session's checkout
   rig.checkout_guides(force=True)
   rig.owns_scene_guides            # True when the scene's guides are ours, or there are none
   rig.session_id                   # the id stamped on the scene's guide holder
   trigger.Session.hand_over(old_session, new_session)

.. seealso::

   :doc:`actions_reference` for the built-in actions and their fields, and
   :doc:`writing_actions` to add your own.
