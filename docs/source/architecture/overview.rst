How the packages fit together
=============================

TikWorks is five packages in one repository, stacked so that each depends only
on the ones below it. The stack is the architecture; almost every other rule on
this page is a way of keeping it a stack.

.. code-block:: text

   tik.tools       concrete tools       may use everything below
   tik.trigger     rigging framework    may use tik.maya, tik.shared, tik.core
   tik.shared      UI and infrastructure may use tik.maya, tik.core, Qt
   tik.maya        Maya wrapper         may use tik.core, Maya. Never Qt.
   tik.core        pure Python          uses the standard library only

**Dependencies flow downward only.** tik.core does not know Maya exists.
tik.maya does not know Qt exists. tik.trigger's ``core`` sub-package is pure
Python and a test fails the build if it imports Maya or Qt. Nothing is allowed
to import from tik.tools.

One question decides where code goes
------------------------------------

Most placement decisions come down to the line between tik.maya and
tik.trigger, and that line has a single test, quoted in the code base as the
**animator-opinion rule**:

   If an average animator can understand it and might have an opinion about
   it, it belongs to tik.trigger, not tik.maya.

- tik.maya owns **mechanism**: which nodes exist and how they are wired. A
  ``blendMatrix`` between two matrices. An exponential falloff on a distance.
  Nobody has an opinion about ``multMatrix`` operand order.
- tik.trigger owns **policy**: what the rig *is*. "The wrist control carries the
  ``ikFk`` attribute." "The pole vector follows the shoulder by default."
  "Stretch is limited to 50 percent."

Practical test: could you name the thing in a note to an animator without
explaining it first? Then it is trigger's. The corollary is that a tik.maya
construct never creates a controller, never names a user-facing attribute, and
never encodes a side convention.

Inside tik.maya: types, roles, constructs
-----------------------------------------

.. code-block:: text

   ┌──────────────────────────────────────────────────────────┐
   │ Constructs   assemble several nodes into one thing       │  MatrixConstraint, SpaceSwitch, Ribbon
   ├──────────────────────────────────────────────────────────┤
   │ Roles        say what a node means                       │  Controller
   ├──────────────────────────────────────────────────────────┤
   │ Types        say what a node is                          │  Transform, Joint, Mesh, Curve
   ├──────────────────────────────────────────────────────────┤
   │ Nodes/plugs  identity, attributes, connections           │  Node, DagNode, Plug, resolve()
   └──────────────────────────────────────────────────────────┘

**Types** map one to one onto Maya node types and are registered with
``@register("joint")``. They expose structural behaviour (channels, geometry
data, hierarchy) and never semantic meaning. A ``Joint`` does not know whether it
is a bind joint or a guide.

**Roles** are semantic overlays. A role *holds* a type instance (composition,
not inheritance), validates that it holds a compatible one, and marks its
identity in the scene so it can be recovered after a reload: ``Controller``
tags its transform with an ``isController`` attribute. Roles never create new
Maya node kinds.

**Constructs** coordinate several nodes and roles into a pattern with a name:
build it, expose its plugs, delete it. They stay on the mechanism side of the
animator-opinion rule.

Inside tik.trigger: systems and modules
---------------------------------------

The stack continues upwards, and the layer names are used consistently across
the code and the design specs:

.. code-block:: text

   nodes → types → roles → constructs → systems → modules
   └──────────── tik.maya ────────────┘  └── tik.trigger ──┘

A **system** (``tik/trigger/systems/``) composes tik.maya constructs *and*
creates controllers and names animator attributes, which is exactly what a
construct may not do. A **module** composes systems and adds the declaration:
guides, inputs, outputs, settings.

**Modules never inherit from other modules.** A module's manifest is class
attributes read by the registry and by the form builder; a base module would
drag its own declarations into every subclass. Shared behaviour goes into a
system as a plain function.

Why tik.trigger.core is pure Python
-----------------------------------

The session document, the guide document, the reconcile algorithm, the module
and action base classes, the registry and the file versioning all live in
``tik.trigger.core`` and import neither Maya nor Qt. That is what lets a ``.tr``
be loaded, inspected, validated and edited by a script that never starts Maya,
and it is what makes the reconcile logic testable with plain ``pytest``. The
scene-touching code lives beside it in ``tik.trigger.guides`` and
``tik.trigger.maya``; the Qt code in ``tik.trigger.ui``.

Other rules that fall out of the stack
--------------------------------------

- **The scene is the source of truth for tik.maya.** Wrappers cache an
  ``MObject`` and a UUID, never a name or a value. Every read goes to Maya.
- **The session is the source of truth for tik.trigger.** The scene renders the
  session's guides and can be rebuilt from it. :doc:`/tik_trigger/concepts`
  spells out the consequences.
- **Everything is undoable.** API-level edits register with an undo bridge;
  multi-step operations are wrapped in one undo chunk.
- **No third-party dependencies.** The standard library and what Maya bundles.
  The Qt shim (``Qt.py``) and the undo bridge (``apiundo``) are vendored in
  ``tik.vendor``.

.. seealso::

   :doc:`packages` for what each package actually contains today, and
   ``AI/coding_rules.md`` in the repository for the same rules in the form the
   code review applies them.
