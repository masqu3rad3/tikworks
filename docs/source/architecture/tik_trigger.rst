tik.trigger
===========

Purpose
-------
A rigging and automation framework for Maya.

What lives here
---------------

- Rig blueprints
- Rig components
- Behavioral rules and relationships
- Automation graphs
- Abstractions over Maya mechanics
- Authoring and execution logic for rigs

This is not a utility layer. This is a system.

Rules
-----

- May depend on ``tik.maya``
- May depend on ``tik.shared``
- May use Qt for authoring, debugging, and visualization
- Must not leak its concepts downward
- Must not be required for basic Maya usage

Mental model
------------

``A rigging language and framework.`` This is intent, structure, and meaning, not infrastructure.

Layering inside the package
---------------------------

.. code-block:: text

   nodes → types → roles → constructs → systems → modules
   └────────── tik.maya ──────────┘   └── tik.trigger ──┘

- ``tik.trigger.core`` is **pure Python** — no Maya, no Qt. The boundary is
  enforced by ``tests/unit/test_import_boundaries.py``.
- Everything else in ``tik.trigger`` may use ``tik.maya``.
- A *system* composes ``tik.maya`` constructs and creates controllers, naming
  the animator-facing attributes; a *module* composes systems.
- **Modules never inherit from other modules.** Shared behaviour goes into a
  system, because a module's manifest is class attributes the registry and the
  UI read.

The Animator-Opinion Rule
-------------------------

The line between ``tik.maya`` and ``tik.trigger`` has one test:

   If an average animator can understand it and might have an opinion about it,
   it belongs to ``tik.trigger``.

``tik.maya`` owns *mechanism* (which nodes, wired how); ``tik.trigger`` owns
*policy* (what the rig is). A ``tik.maya`` construct never creates a controller,
never names a user-facing attribute, and never encodes a side convention.

Status
------

Under active development, and Maya-only: there is no backend abstraction layer.
The framework — the session document, guides, modules, systems, actions and the
Qt tool — is implemented and documented in :doc:`../tik_trigger/index`. APIs may
still change.
