Guides and lockstep
===================

Guides are the rig's skeleton-to-be: tagged joints a rigger places, belonging to
module instances connected into a graph. This page covers the guide document,
the :class:`~tik.trigger.guides.scene.GuideScene` API, how the scene and the
document stay in step, and the ``.trg`` exchange format.

.. seealso::

   :doc:`../concepts` states the model these APIs implement. Read it first; the
   rules there explain why several methods refuse to do the obvious thing.

The guide document
------------------

:class:`~tik.trigger.core.guide_document.GuideDocument` is pure data living at
``session.document.guides``. It holds:

.. code-block:: text

   GuideDocument
   ├── modules       [ModuleEntry, ...]    one per instance, keyed by uuid
   ├── scene_groups  [SceneGroup, ...]     named bags of arbitrary Maya nodes
   ├── positions     designer node positions
   ├── collapse      designer collapse modes
   └── dismissed     True while a build has deliberately cleared the rendering

A :class:`~tik.trigger.core.guide_document.ModuleEntry` carries the identity
(``instance_id``, ``module_type``, ``name``, ``side``), the ``settings``, the
``inputs`` (``{input name: source}``) and one
:class:`~tik.trigger.core.guide_document.GuideRecord` per guide: role, index,
position, rotation, rotate order, joint orient, radius, colour, authored
attributes and the intra-module parent.

``None`` means "never authored"
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

On a record, ``position``, ``rotation``, ``joint_orient``, ``radius`` and
``color`` are optional. ``None`` is not zero: it means the rigger has never
authored that value, so regenerate leaves whatever the module's own
``draw_guides`` chose (its per-side colour included) instead of stamping a
default over it.

GuideScene
----------

The guides *in the current Maya scene*. Reach it through the session; the
free-standing constructor exists for scripting and is bound to no session, so
nothing it does is saved or undoable through a session.

.. code-block:: python

   guides = session.guides            # bound: edits go on the session's undo stack

   body = guides.add("base", name="body")
   arm = guides.add("arm", side="L", name="arm", parent=body, stretch=False)
   tail = guides.add("fkchain", name="tail", inputs={"root": "body.root"}, segments=5)

   guides.instances()                 # every GuideHandle
   guides.roots()                     # those with nothing feeding their primary input
   guides["arm"]                      # by module name (first match)
   guides.find("arm", side="L")       # disambiguated by side
   guides.by_key("L_arm")             # by display key
   guides.get(instance_id)            # by uuid
   guides.mirror(arm)                 # -> R_arm, poses and inputs mirrored
   guides.duplicate(arm)              # -> L_arm1, same settings and poses
   guides.reparent(arm, body)         # sets the primary input; never the DAG
   guides.remove(arm)                 # entry, joints and layout
   guides.clear()                     # every module

Names are unique per side: adding a second ``arm`` on ``L`` gives ``arm1``.
``parent=`` hangs the new joints under the parent's root guide *and* pre-fills
the primary input; ``inputs=`` sets connections explicitly with no scene
parenting, which is what the Guide Designer does.

GuideHandle
~~~~~~~~~~~

A :class:`~tik.trigger.guides.handle.GuideHandle` is a *view* onto one entry,
not a copy. It holds nothing itself, so it stays valid across a regenerate and
even after its guide joints are deleted.

.. code-block:: python

   arm.name = "arm_upper"       # renames; joint names follow on regenerate
   arm.key                      # 'L_arm_upper'
   arm.side                     # Side.LEFT
   arm.module_type              # 'arm'
   arm.stretch = False          # a module setting; redraws immediately
   arm.set(squash=False)
   arm.settings                 # effective values
   arm.inputs                   # {'root': 'body.root'}
   arm.input_names, arm.outputs # ['root'], ('collar', 'upperarm', 'lowerarm', 'hand')
   arm.set_input("root", None)  # disconnect
   arm.parent                   # the module feeding the primary input, or None
   arm.root                     # its root guide joint, or None when not drawn
   arm.select()                 # select its guides in Maya

Connections are data
--------------------

A connection is ``input ← source``, where a source is another module's output
(``"L_arm.hand"``) or a bare Maya node name. Guide joints are **never** parented
into each other to express one.

.. code-block:: python

   guides.connect("L_arm.root", "body.root")
   guides.connect("tail.root", "some_locator")    # any scene node
   guides.disconnect("tail.root")
   guides.connections()      # [{'input': 'L_arm.root', 'source': 'body.root'}, ...]

Arbitrary Maya nodes are grouped so the designer can offer them as sources:

.. code-block:: python

   name = guides.add_scene_group("props", ["prop_ctrl", "prop_jnt"])
   guides.scene_groups()          # {'props': ['prop_ctrl', 'prop_jnt']}
   guides.set_scene_group("props", ["prop_ctrl"])
   guides.rename_scene_group("props", "gear")
   guides.remove_scene_group("gear")

The build order falls out of the connections: every module is built first, then
connected, and a module's bind joints are created directly under the producer's
bind joint, in final position.

Staying in step
---------------

.. code-block:: python

   diff = guides.sync()                        # capture, reconcile, redraw the stale
   diff = guides.sync(regenerate_stale=False)  # report only; touches no joints
   diff = guides.diff()                        # read-only reconcile

The returned :class:`~tik.trigger.core.reconcile.GuideDiff` lists
``structural`` (modules needing a redraw), ``drifted`` (poses the document has
not been told about), ``orphans`` (joints tagged with an unknown instance) and
``duplicates``. Orphans and duplicates are *reported*, never deleted.

``sync()`` rescans after a redraw, so the diff it returns describes the scene as
it now stands rather than staleness the same call has just fixed.

Optional sync
~~~~~~~~~~~~~

``guides.auto_sync`` (default ``True``) governs exactly one thing: whether a
scene event may start a ``sync()``. With it off, a scene event only computes a
``diff()``, and the document is untouched until ``sync()`` is called.

.. warning::

   ``auto_sync`` does **not** gate capture-before-regenerate. Every structural
   write captures, records undo, then regenerates, at every setting. Putting a
   condition in front of that capture reintroduces the bug where editing any
   property threw the rigger's posing away.

Recovering a session from a scene
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Guide joints carry their module entry, so a scene whose ``.tr`` was never saved
is not a dead end:

.. code-block:: python

   document, report = guides.snapshot_from_scene()   # reads; commits nothing
   report.complete, report.partial, report.is_lossless
   session.snapshot_guides_from_scene(document)      # replaces the modules, one undo step

``snapshot_from_scene()`` deliberately commits nothing: replacing the module list
is destructive, so the caller shows the report first. Nothing is redrawn
afterwards either; the joints in the scene already *are* the rendering.

After a build
~~~~~~~~~~~~~

A build may take the guides away (``after_build`` is ``keep``, ``hide`` or
``delete``). ``guides.dismissed`` marks that as deliberate so lockstep does not
treat the missing rendering as damage; ``restore()`` draws them again.

.. code-block:: python

   guides.dismissed        # True while a build has cleared them
   guides.restore()        # draw them again and return the diff

Test builds
-----------

.. code-block:: python

   report = guides.test_build(arm)              # just this module
   report = guides.test_build(arm, tail)        # several
   report = guides.test_build()                 # everything, rig_name="test"

A test build captures poses first, then builds with ``afterlife="keep"`` so the
guides survive it. It is the same ``Builder`` the ``kinematics`` action runs,
and it returns the same :class:`~tik.trigger.maya.build.BuildReport`: the
instance ids built, one ``ModuleRig`` per instance, the connections made.

``.trg`` files
--------------

``.trg`` is the **exchange format for guide libraries**, not the master copy:

.. code-block:: python

   guides.export("guides/hero.trg")              # everything
   guides.export("guides/arm.trg", arm)          # just these modules
   handles = guides.import_("guides/arm.trg")    # merge in; guides.load is an alias
   guides.import_("guides/hero.trg", reset=True) # replace

A file is JSON with a ``joints`` list, a ``connections`` list and optional
``meta`` and ``designer`` dicts; :doc:`file_formats` has the record layout.
Importing mints new instance ids, reassigns names and rewires connections, so
importing the same library twice gives ``L_arm`` and ``L_arm1``, each wired to
its own modules. A module that has gained a guide role since a file was written
gets that guide drawn at its default position on import, so old libraries keep
building.
