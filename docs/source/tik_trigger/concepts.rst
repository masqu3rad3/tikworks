Concepts
========

Five ideas carry the whole framework. Everything else on these pages is a
consequence of one of them.

1. The session is the rig
-------------------------

A **session** is a ``.tr`` file: JSON, schema version 5. It holds two things.

.. code-block:: text

   Document
   ├── meta       author, timestamps, session_id
   ├── actions    an ordered, nestable tree of ActionNodes   -> the pipeline
   └── guides     a GuideDocument                            -> the rig's guides

The second field is the point. A ``.tr`` is a **self-contained rig
description**: the guides are not a side file the session points at, they live
inside it. Building resets the scene and runs every enabled action in order.
There is no separate "rig file"; the rig *is* what running the session produces,
and you can produce it again tomorrow from the same file.

2. The session is the truth; the scene only renders it
------------------------------------------------------

The guide document owns which modules exist, their settings, their connections,
the layout of the Guide Designer's graph, and every guide's pose and authored
attributes, all keyed by a per-instance UUID.

The guide joints you see in Maya are a **rendering** of that document. The
document can rebuild them at any time, which is what makes the failure modes
boring:

- Deleting the guide group does not delete a module.
- Opening a different Maya scene does not lose the rig.
- A session opened without Maya still has its guides.

.. warning::

   The corollary catches people out: deleting guide joints in the outliner does
   *not* remove a module. Use *Delete* in the Guide Designer, or
   ``guides.remove(handle)`` from Python, to remove it from the document.

**Display keys are not identities.** ``L_arm`` is what you read in the tree and
type into ``connect()``; the document stores the UUID. Keys are translated at
every read boundary, fresh, so a rename cannot leave a stale reference behind.

3. The scene is a checkout
--------------------------

The Maya scene is a working copy of **exactly one session at a time**, stamped
with that session's id on the guide holder group. Three verbs cross the line:

.. list-table::
   :header-rows: 1
   :widths: 30 20 50

   * - Verb
     - Direction
     - What it does
   * - ``session.capture_guides()``
     - scene → document
     - Reads poses and guide attributes back. Called by ``save()``, ``build()``
       and ``run()``, so a file can never lag the viewport.
   * - ``session.checkout_guides()``
     - document → scene
     - Clears the rendering and redraws the whole document. Refuses when the
       scene is stamped for another session unless ``force=True``.
   * - ``Session.hand_over(a, b)``
     - both
     - What switching session tabs does: capture from ``a``, then check out
       ``b``.

The refusal is deliberate. Discarding somebody else's working copy has to be a
decision, never a side effect of opening a tab.

4. Lockstep: capture, reconcile, regenerate
-------------------------------------------

``GuideScene.sync()`` runs three steps, and **the order is the point**:

.. code-block:: text

   1. capture      scene poses -> document          the scene wins for poses
   2. reconcile    document vs. what is drawn       what is structurally stale?
   3. regenerate   document -> scene joints         the document wins for structure

Two different kinds of difference are resolved by two different halves, and they
must never be confused:

- **Pose drift** (a guide has been dragged) is resolved by capture. The scene
  wins. A redraw here would teleport the guide the rigger just placed.
- **Structural staleness** (a guide missing, one too many, a parent wrong) is
  resolved by regenerate. The document wins, and only the modules that are stale
  are redrawn.
- **Orphans and duplicates** are reported, never deleted.

Capture runs first precisely so drift is absorbed *before* reconcile could mistake
it for a reason to redraw.

.. important::

   Nothing in Maya fires when a guide is dragged. The document only learns a
   pose when something reads it. That is why every structural edit, changing a
   setting, renaming, connecting, captures first, unconditionally, and then
   regenerates. The *Auto* sync toggle in the UI decides only whether a *scene
   event* may start a sync; it never gates that capture.

5. Two undo stacks, on purpose
------------------------------

.. list-table::
   :header-rows: 1
   :widths: 50 50

   * - Edit
     - Undone by
   * - Structural: add, remove, rename, connect, change a setting, in either
       sub-tab
     - Trigger's own :kbd:`Ctrl+Z`, the session's undo stack
   * - Moving a guide joint in the viewport
     - Maya's :kbd:`Ctrl+Z`

A structural edit is a *document* edit, so it belongs to the document's stack.
Posing is a scene edit and stays where Maya put it.

Where ``.trg`` fits
-------------------

A ``.trg`` is an **import/export format for guide libraries**: a way to move a
guide setup between sessions or ship a shared library of modules. It is not the
master copy of anything; the session is. The ``kinematics`` action reflects
this: leave its ``guides_file`` empty and it builds the session's own guides, set
a path and it builds that library instead.

The vocabulary
--------------

.. list-table::
   :widths: 22 78

   * - **Module**
     - A declarative class: which guides it needs, which inputs it accepts, which
       outputs it exposes, its typed settings, plus ``draw_guides()`` and
       ``build()``. ``arm``, ``fkchain``, ``twist`` are modules.
   * - **Instance**
     - One placed module with a name and a side: ``L_arm``. Identified by a UUID
       in the document, shown by its display key.
   * - **Guide**
     - One tagged joint of an instance, addressed by ``(role, index)``:
       ``("shoulder", 0)``, ``("segment", 3)``.
   * - **Input / output**
     - Named ports. An output is a bind joint another module can attach to; an
       input is where this module hangs. A connection is ``input ← source``,
       where the source is ``"<key>.<output>"`` or a bare scene node name.
   * - **Socket**
     - The transform created in the module's ``socket_grp`` for each declared
       input, driven by the producer's output at build time.
   * - **System**
     - A shared rig sub-assembly in ``tik/trigger/systems`` that composes
       tik.maya constructs *and* creates controllers. Modules compose systems;
       modules never inherit from other modules.
   * - **Action**
     - One step of the pipeline: typed fields plus ``run(ctx)``.
   * - **Reference**
     - An action that runs another session's actions inline, with local
       overrides stored in the referencing session.

.. seealso::

   The design specs behind these rules live in ``docs/superpowers/specs/``.
   ``2026-08-31-guide-ownership-and-lockstep-design.md`` is authoritative for
   anything touching guides; ``2026-09-01-optional-sync-and-snapshot-design.md``
   amends its sections 5 and 6.
