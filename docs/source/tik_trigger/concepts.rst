Core Concepts
=============

Five ideas carry the whole framework. Everything else is detail.

1. The session is the rig
-------------------------

A **session** is a ``.tr`` file (JSON, schema 5). It holds two things:

.. code-block:: text

   Document
   ├── meta       author, timestamps, session_id
   ├── actions    ordered, nestable ActionNode tree  → the pipeline
   └── guides     a GuideDocument                    → the rig's guides

That second field is the point of the current design: **a ``.tr`` is a
self-contained rig description**. Guides are not a side file the session points
at — they live in it.

Building resets the scene and runs every enabled action in order. There is no
separate "rig file"; the rig *is* what running the session produces.

2. The session is the truth; the scene only renders it
------------------------------------------------------

The :class:`~tik.trigger.core.guide_document.GuideDocument` owns which modules
exist, their settings, their connections, the Guide Designer's layout, and every
guide's pose and authored attributes — all keyed by instance uuid.

Guide joints in Maya are a **rendering** of that document. The document can
rebuild them at any time, which is what makes the failure modes boring:

- Deleting the guide group does not delete a module.
- Opening a different Maya scene does not lose the rig.
- A session opened headlessly still has its guides.

.. warning::
   The corollary is the rule that catches people out: deleting guide joints does
   *not* remove a module. Use ``GuideScene.remove(handle)`` (or Delete in the
   Guide Designer) to remove it from the document.

**Display keys are not identities.** ``L_arm`` is what a rigger reads; the
document stores the uuid. Keys are translated fresh at every read boundary so a
rename cannot leave a stale reference behind.

3. The scene is a checkout
--------------------------

The Maya scene is a working copy of **exactly one session at a time**, stamped
with that session's ``session_id`` on the guide holder.

.. list-table::
   :header-rows: 1
   :widths: 28 20 52

   * - Verb
     - Direction
     - What it does
   * - ``session.capture_guides()``
     - scene → document
     - Reads poses and guide attrs back. Called by ``save()`` and ``build()``,
       so a file never lags the viewport.
   * - ``session.checkout_guides()``
     - document → scene
     - Clears the rendering and redraws the whole document. Refuses when the
       scene is stamped for another session, unless ``force=True``.
   * - ``Session.hand_over(a, b)``
     - both
     - Switching session tabs: capture from ``a``, then check out ``b``.

Refusing is deliberate. Discarding somebody else's working copy has to be a
decision, never a side effect.

4. Lockstep: capture, reconcile, regenerate
-------------------------------------------

``GuideScene.sync()`` runs three steps, and **the order is the point**:

.. code-block:: text

   1. capture     scene poses  → document      (the scene wins for poses)
   2. reconcile   document vs. what is drawn   (what is structurally stale?)
   3. regenerate  document     → scene joints  (the document wins for structure)

Pose drift and structural staleness are resolved by *different* halves and must
never be confused:

- **Pose drift** — a guide has been dragged. Resolved by **capture**: the scene
  wins. A redraw here would teleport the guide the rigger just placed.
- **Missing or unexpected guides** — resolved by **regenerate**: the document
  wins, and only the modules that are actually stale are redrawn.
- **Orphans and duplicates** — reported, never deleted.

Capture runs first precisely so that drift is absorbed *before* reconcile could
mistake it for a reason to redraw.

.. important::
   Nothing in Maya fires when a guide is dragged. The document only learns a
   pose when something goes and reads it — which is why every structural write
   captures first, unconditionally, before it regenerates.

5. Two undo stacks, on purpose
------------------------------

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Edit
     - Undone by
   * - Structural (add / remove / rename / connect / settings)
     - Trigger's own Ctrl+Z — the session's undo stack
   * - Moving a guide in the viewport
     - Maya's Ctrl+Z

A structural edit is a *document* edit, so it belongs on the document's stack.
Posing is a scene edit and stays where Maya put it.

Where ``.trg`` fits
-------------------

``.trg`` is an **import/export format for guide libraries** — a way to move a
guide setup between sessions or ship a shared library. It is not the master
copy of anything: the session is.

The ``kinematics`` action reflects this. Leave ``guides_file`` empty and it
builds this session's own guides; set a path and it builds that library instead.

.. seealso::
   The design specs behind these rules live in ``docs/superpowers/specs/`` —
   ``2026-08-31-guide-ownership-and-lockstep-design.md`` is authoritative for
   anything touching guides, and ``2026-09-01-optional-sync-and-snapshot-design.md``
   amends its sections 5 and 6.
