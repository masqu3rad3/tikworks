Overview
========

tik.trigger is the layer where a rig gets its *opinions*. ``tik.maya`` knows how
to wire a matrix constraint; tik.trigger knows that an arm has a collar, that
the IK control is world-mirrored, and that ``stretch`` is a checkbox an animator
may argue about.

The Animator-Opinion Rule
-------------------------

The split between the two packages has one test:

   If an average animator can understand it and might have an opinion about it,
   it belongs to **tik.trigger**, not ``tik.maya``.

``tik.maya`` owns *mechanism* (which nodes, wired how); tik.trigger owns *policy*
(what the rig is). A ``tik.maya`` construct never creates a controller, never
names a user-facing attribute, and never encodes a side convention.

Layers
------

.. code-block:: text

   nodes → types → roles → constructs → systems → modules
   └────────── tik.maya ──────────┘   └── tik.trigger ──┘

- **systems** (``tik/trigger/systems/``) compose ``tik.maya`` constructs *and*
  create controllers, naming the animator-facing attributes.
- **modules** (``tik/trigger/modules/``) compose systems.

.. important::
   **Modules never inherit from other modules.** A module's ``guides``,
   ``inputs``, ``outputs`` and ``Field``\ s are class attributes read by the
   registry and the UI form builder, so shared behaviour goes into a *system*
   instead of a base module.

What is in the package
----------------------

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Sub-package
     - Contents
   * - ``tik.trigger.core``
     - Pure Python. The session :class:`~tik.trigger.core.document.Document`,
       the :class:`~tik.trigger.core.guide_document.GuideDocument`, the
       :class:`~tik.trigger.core.module.Module` and
       :class:`~tik.trigger.core.action.Action` base classes, the manifest
       pieces (:class:`~tik.trigger.core.manifest.GuideLayout`,
       :class:`~tik.trigger.core.manifest.Input`,
       :class:`~tik.trigger.core.manifest.GuideAttr`), the registry,
       reconcile, discovery and versioning.
   * - ``tik.trigger.guides``
     - The guides in the Maya scene: ``GuideScene``, the joint primitives,
       capture / regenerate / snapshot, the checkout stamp, and the ``.trg``
       exchange format.
   * - ``tik.trigger.maya``
     - Building in Maya: ``ModuleRig`` and ``GuideDraft`` (what modules build
       and draw through), the ``Builder``, the action ``Runner``, scene tags
       and the scene observer.
   * - ``tik.trigger.modules``
     - Built-in modules: ``base``, ``fkchain``, ``arm``, ``twist``, ``ribbon``.
   * - ``tik.trigger.systems``
     - Shared rig sub-assemblies: ``limb`` (IK/FK), ``limb_lock``, ``reach``
       (auto-collar), ``twist`` (twist extraction).
   * - ``tik.trigger.actions``
     - Built-in actions: ``import_asset``, ``kinematics``, ``reference``,
       ``script``.
   * - ``tik.trigger.ui``
     - The Qt tool: the Trigger window, the pipeline view, the Guide Designer
       and its node graph.

Importing is cheap
------------------

``import tik.trigger`` does **not** import Maya. The Maya-touching names are
resolved on first use through a module-level ``__getattr__``:

.. code-block:: python

   import tik.trigger as trigger

   trigger.Module          # available immediately (pure core)
   trigger.GuideScene      # imports tik.trigger.guides.scene on first access
   trigger.Session         # imports tik.trigger.session on first access

Discovery
---------

Modules and actions opt in explicitly with
:func:`~tik.trigger.core.registry.register_module` and
:func:`~tik.trigger.core.registry.register_action` — there is no implicit
scanning of class hierarchies. ``load_plugins()`` imports the built-in
``modules`` and ``actions`` packages so their decorators run:

.. code-block:: python

   import tik.trigger as trigger

   trigger.load_plugins()
   trigger.list_modules()   # ['arm', 'base', 'fkchain', 'ribbon', 'twist']
   trigger.list_actions()   # ['import_asset', 'kinematics', 'reference', 'script']

Each module and action lives in its own folder with a named ``.py`` file
(``modules/arm/arm.py``), which is what makes a third-party pack a matter of
dropping a folder in and importing it.

.. seealso::
   :doc:`concepts` for the truth model, and
   :doc:`../architecture/tik_trigger` for the package boundary rules.
