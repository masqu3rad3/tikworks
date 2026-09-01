tik.trigger
===========

**tik.trigger** is the modular rigging framework of TikWorks. It is built on
``tik.maya`` and adds the layer that ``tik.maya`` deliberately refuses to own:
*what a rig is*. Modules, guides, build order and the pipeline that runs them
all live here.

.. warning::
   tik.trigger is under active development. The APIs on these pages match the
   sources in ``src/python/tik/trigger``; both may still change.

.. note::
   tik.trigger is Maya-only. There is no backend abstraction: ``tik/trigger/core``
   is pure Python (no Maya, no Qt, enforced by
   ``tests/unit/test_import_boundaries.py``), and every other sub-package may
   use ``tik.maya`` directly.

The one-paragraph version
-------------------------

A rig is a **session**: a ``.tr`` file holding an ordered, nestable list of
**actions** *and* the rig's **guides**. Building resets the scene and runs the
actions in order; one of them (``kinematics``) turns the guides into modules
and connects them. The session is the truth — the Maya scene is a working copy
of exactly one session at a time, and guide joints in it are a *rendering* the
session owns and can rebuild.

.. toctree::
   :maxdepth: 2
   :caption: Getting Started

   overview
   quickstart
   concepts

.. toctree::
   :maxdepth: 2
   :caption: Guides

   Sessions and Actions <guides/sessions_and_actions>
   Guides and Lockstep <guides/guides_and_lockstep>
   Writing a Module <guides/writing_modules>
   Writing an Action <guides/writing_actions>
   The Trigger Window <guides/ui>
