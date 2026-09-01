Guides and Lockstep
===================

Guides are the rig's skeleton-to-be: tagged joints a rigger places, connected
into a graph of module instances. This page covers the guide document, the
``GuideScene`` API, how the scene and the document stay in step, and the
``.trg`` exchange format.

.. seealso::
   :doc:`../concepts` states the model these APIs implement. Read it first —
   the rules there explain why several methods refuse to do the obvious thing.

The guide document
------------------

:class:`~tik.trigger.core.guide_document.GuideDocument` is pure data living on
``Session.document.guides``. It holds:

.. code-block:: text

   GuideDocument
   ├── modules       [ModuleEntry, ...]   keyed by instance uuid
   ├── scene_groups  [SceneGroup, ...]    arbitrary Maya nodes as sources
   ├── positions     designer node positions
   └── collapse      designer collapse modes

A :class:`~tik.trigger.core.guide_document.ModuleEntry` carries the identity
(``instance_id``, ``module_type``, ``name``, ``side``), the module's
``settings``, its ``inputs`` (``{input name: source}``) and its
:class:`~tik.trigger.core.guide_document.GuideRecord` list.

``None`` means "never authored"
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

On a ``GuideRecord``, ``position``, ``rotation``, ``joint_orient``, ``radius``
and ``color`` are ``Optional``. ``None`` is not "zero" — it means the rigger has
never authored that value, so regenerate leaves whatever the module's own
``draw_guides`` chose (its per-side colour included) instead of stamping a
default over it.

``GuideScene``
--------------

:class:`~tik.trigger.guides.scene.GuideScene` is the guides *in the current Maya
scene*. Reach it through the session — the free-standing constructor exists for
scripting and is bound to no session at all:

.. code-block:: python

   guides = session.guides          # bound: edits go on the session's undo stack

   body = guides.add("base", name="body")
   arm = guides.add("arm", side="L", parent=body, stretch=False)

   guides.instances()               # every GuideHandle
   guides.roots()                   # those with no primary source
   guides["arm"]                    # by module name
   guides.find("arm", side="L")     # ...disambiguated by side
   guides.by_key("L_arm")           # by display key
   guides.get(instance_id)          # by uuid
   guides.mirror(arm)               # -> R_arm, inputs mirrored
   guides.reparent(arm, body)
   guides.remove(arm)               # entry + joints + layout
   guides.clear()                   # every module

Names are unique per side: adding a second ``arm`` on ``L`` gives ``arm1``.

A :class:`~tik.trigger.guides.handle.GuideHandle` is a *view*, not a copy. It
holds nothing itself, so it stays valid across a regenerate and even after its
guide joints are deleted:

.. code-block:: python

   arm.name = "arm_upper"       # renames; joint names follow on regenerate
   arm.stretch = False          # a module setting; redraws immediately
   arm.set(squash=False)
   arm.settings                 # effective values
   arm.inputs                   # {'root': 'body.root'}
   arm.outputs                  # ('collar', 'upperarm', 'lowerarm', 'hand')
   arm.parent                   # the module feeding the primary input
   arm.root                     # its root guide joint, or None when not drawn
   arm.select()                 # select its guides in Maya

Connections are data
--------------------

A connection is ``input ← source``, where a source is another module's output
(``"L_arm.hand"``) or a bare Maya node name. Guide joints are **never** parented
into each other to express one:

.. code-block:: python

   guides.connect("L_arm.root", "body.root")
   guides.connect("tail.space", "some_locator")   # any scene node
   guides.disconnect("tail.space")
   guides.connections()      # [{'input': 'L_arm.root', 'source': 'body.root'}]

Arbitrary Maya nodes are grouped so the designer can offer them as sources:

.. code-block:: python

   name = guides.add_scene_group("props", ["prop_ctrl", "prop_jnt"])
   guides.scene_groups()          # {'props': ['prop_ctrl', 'prop_jnt']}
   guides.rename_scene_group("props", "gear")
   guides.remove_scene_group("gear")

The build order falls out of the connections: everything is built first, then
connected, and a module's bind joints are created directly under the producer's
bind joint, in final position.

Staying in step
---------------

.. code-block:: python

   diff = guides.sync()                       # capture, reconcile, redraw stale
   diff = guides.sync(regenerate_stale=False) # report only; touches no joints
   diff = guides.diff()                       # read-only reconcile

The returned :class:`~tik.trigger.core.reconcile.GuideDiff` reports
``structural`` (modules needing a redraw), ``drifted`` (poses the document has
not been told about), ``orphans`` and ``duplicates``. Orphans and duplicates are
*reported*, never deleted.

``sync()`` rescans after a redraw, so the diff it returns describes the scene as
it now stands rather than staleness the same call has just fixed.

Optional sync
~~~~~~~~~~~~~

``GuideScene.auto_sync`` (default ``True``) governs **exactly one thing**:
whether a scene event may start a ``sync()``. With it off, a scene event only
computes a ``diff()``, and the document is untouched until ``Sync`` is pressed.

.. warning::
   ``auto_sync`` does **not** gate capture-before-regenerate. Every structural
   write captures, records undo, then regenerates, at every setting. Putting a
   condition in front of that capture reintroduces the bug where editing any
   property threw the rigger's posing away — nothing in Maya fires when a guide
   is dragged.

Recovering a session from a scene
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Guide joints carry their module entry, so a scene whose ``.tr`` was never saved
is not a dead end:

.. code-block:: python

   document, report = guides.snapshot_from_scene()   # commits nothing
   session.snapshot_guides_from_scene(document)      # one undo step

``snapshot_from_scene()`` deliberately commits nothing: replacing the module
list is destructive, so the caller shows the report first. Nothing is redrawn
afterwards either — the joints in the scene already *are* the rendering.

After a build
~~~~~~~~~~~~~

A build may take the guides away (``after_build`` is ``keep``, ``hide`` or
``delete``). ``GuideScene.dismissed`` marks that as deliberate, so lockstep does
not treat the missing rendering as damage; ``restore()`` draws them again.

.. code-block:: python

   guides.dismissed        # True while a build has cleared them
   guides.restore()        # draw them again

``.trg`` files
--------------

``.trg`` is the **exchange format for guide libraries**, not the master copy:

.. code-block:: python

   guides.export("guides/hero.trg")            # everything
   guides.export("guides/arm.trg", arm)        # just these modules
   handles = guides.import_("guides/arm.trg")  # merge in
   guides.import_("guides/hero.trg", reset=True)   # replace

A file is JSON with a ``joints`` list, a ``connections`` list and optional
``meta``/``designer`` dicts. Each joint record carries its transform plus
``module``, ``role``, ``index`` and ``instance``; root records also carry the
module's ``settings`` and ``module_name``. Records with no ``module``/``role``
pair belong to no registered module and are reported in ``GuideFile.unknown``
rather than being silently dropped.

Importing reassigns names and rewires connections, so importing the same library
twice gives ``L_arm`` and ``L_arm1``, each wired to its own modules.

Test builds
-----------

.. code-block:: python

   guides.test_build(arm)              # just this module
   guides.test_build()                 # everything in the scene

A test build syncs poses first, then builds with ``afterlife="keep"`` so the
guides survive it. It is the same ``Builder`` the ``kinematics`` action runs.
