Sessions and Actions
====================

A session is a ``.tr`` document plus the runner that builds it. This page covers
the TD-facing API: :class:`~tik.trigger.session.Session` and
:class:`~tik.trigger.session.ActionHandle`.

Opening and saving
------------------

.. code-block:: python

   from tik import trigger

   rig = trigger.Session()                       # new, unsaved
   rig = trigger.Session.open("rigs/hero.tr")    # or open one

   rig.name          # 'hero.tr'  (or 'untitled')
   rig.directory     # the folder relative paths resolve against
   rig.is_modified   # True once the document differs from the saved state

   rig.save()                    # to file_path
   rig.save("rigs/other.tr")     # elsewhere; the .tr suffix is enforced
   rig.save(increment=True)      # hero_v002.tr — same as rig.increment()

.. note::
   ``save()`` calls ``capture_guides()`` first, so the file can never lag the
   viewport. ``build()`` and ``run()`` do the same.

The action tree
---------------

Actions are addressed by ``/``-separated paths, which read like the tree looks:

.. code-block:: python

   rig.add("import_asset", "import_model", file_path="geo/hero_v02.ma")
   rig.add("script", "fix", parent="import_model", code="...")   # nested
   rig.add("script", "later", after="import_model")              # next sibling

   rig["import_model"]              # -> ActionHandle
   rig["import_model/fix"]          # nested
   rig.find("nope")                 # -> None instead of raising
   "import_model" in rig            # -> True
   rig.paths()                      # every path, depth-first
   rig.walk()                       # every handle, referenced ones included

   rig.move("fix", parent=None, index=0)
   rig.rename("fix", "fixup")
   rig.duplicate("fixup")
   rig.remove("fixup")

Settings are attributes
-----------------------

An :class:`~tik.trigger.session.ActionHandle` exposes the action's typed fields
directly. Writes are validated by the field, so a bad value fails at assignment
rather than at build time:

.. code-block:: python

   step = rig["build_rig"]
   step.rig_name = "hero"          # validated by StringField
   step.set(auto_switchers=False, after_build="delete")
   step.enabled = False
   step.settings                   # effective values: defaults + stored
   step.reset("rig_name")          # back to the default
   step.reset()                    # every field

Unknown names raise ``AttributeError`` naming the action type — there is no
silent stash of arbitrary keys.

References and overrides
------------------------

The ``reference`` action runs another session's actions inline. Editing a
referenced action stores an **override in the referencing session**; the
referenced file is never modified:

.. code-block:: python

   base = rig.add("reference", "baseRig", file="rigs/baseRig.tr")

   base["scripts/head_rotation"].enabled = False   # override
   base["kinematics"].rig_name = "hero"            # override
   base["kinematics"].reset()                      # drop this action's overrides

   base.children          # referenced rows first, then locally added ones
   base["kinematics"].is_linked   # True

Two things follow from "overrides live here, not there":

- You cannot ``add`` an action inside a reference. Open the referenced session
  and add it there.
- ``version`` on the reference (``"latest"``, ``"pinned"`` or an explicit
  ``v###``) decides which file on disk is expanded.

Validating, building, running
-----------------------------

.. code-block:: python

   rig.validate()          # ['import_model: file not found (geo/hero_v02.ma)']
   rig.steps()             # what Build would run, in order
   rig.build()             # reset the scene, run every enabled action
   rig.build(until="kinematics")
   rig.build(reset_scene=False)
   rig.run("fix")          # a single action in the current scene, no reset

``validate()`` is pre-flight only: it plans the run, collects the planner's
problems (a missing referenced file, for instance), and asks every action for
its own. It never touches the scene.

Undo
----

Structural edits go on the session's own stack — this is the Ctrl+Z the Trigger
window uses:

.. code-block:: python

   rig.can_undo
   rig.undo()
   rig.redo()

``Session.touch()`` is what records a step. It is public because the guide layer
calls it: a guide edit is a document edit.

Built-in actions
----------------

.. list-table::
   :header-rows: 1
   :widths: 18 14 68

   * - Type
     - Category
     - What it does
   * - ``import_asset``
     - build
     - Import (or reference) a ``.ma``/``.mb``/``.fbx``/``.obj``/``.abc``/``.usd``
       into the build scene, optionally under a namespace.
   * - ``kinematics``
     - build
     - Build every module. Empty ``guides_file`` builds this session's own
       guides; a path builds that ``.trg`` library instead. ``guide_roots``
       narrows the scope, ``after_build`` says what happens to the guides.
   * - ``reference``
     - structure
     - Run another ``.tr``'s actions here, with local overrides.
   * - ``script``
     - structure
     - Run Python from a file and/or inline, with ``ctx`` in scope.

.. seealso::
   :doc:`writing_actions` to add your own.
