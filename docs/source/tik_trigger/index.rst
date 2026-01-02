tik.trigger
===========

**tik.trigger** is a rigging and automation framework for Maya. It provides a
structured approach to building rigs with reusable components, blueprints, and
behavioral rules.

.. note::
   tik.trigger is currently under development. Documentation will be expanded as
   features land.

   For reference, the previous version of Trigger (as a standalone project) is
   documented at: https://trigger-maya.readthedocs.io/en/latest/

What Will Live Here
-------------------

- Rig blueprints and templates
- Rig components (limbs, spines, faces, etc.)
- Behavioral rules and relationships
- Automation graphs
- Authoring and execution logic for rigs

Design Philosophy
-----------------

tik.trigger is not a utility layer — it is a system. It builds on the foundation
of ``tik.maya`` to provide:

- **Intent-driven rigging**: Define what a rig should do, not how to wire it
- **Reusable components**: Build once, use everywhere
- **Non-destructive workflow**: Modify rigs without rebuilding from scratch

Dependencies
------------

tik.trigger may depend on:

- ``tik.maya`` — for Maya node manipulation
- ``tik.shared`` — for shared infrastructure and UI utilities
- Qt — for authoring, debugging, and visualization tools

tik.trigger must not leak its concepts downward into lower layers and must not
be required for basic Maya usage.

Coming Soon
-----------

Documentation for tik.trigger will include:

- Why tik.trigger?
- tik.trigger Overview
- Component Reference
- Blueprint System
- Quickstart Guide
