TikWorks Documentation
======================

**TikWorks** is a suite of Python tools for Autodesk Maya.
At its core is **TikMaya** (`tik.maya`) — a modern, namespaced Pythonic wrapper for ``maya.cmds`` that serves as the foundation for all TikWorks tools.

.. warning::
   TikMaya is actively being built. The API and documentation may change as features land.

.. tip::
   **Why TikWorks?** Maya scripting is powerful but verbose. TikWorks brings modern Python patterns to Maya — type safety, object-oriented design, and cleaner syntax — while keeping Maya's flexibility intact.

The TikWorks Ecosystem
----------------------

TikWorks follows a strict top-to-bottom dependency flow:

.. code-block:: text

   tik.core        # semantic primitives
   ↑
   tik.maya        # disciplined Maya wrapper
   ↑
   tik.shared      # reusable infrastructure and UX
   ↑
   tik.trigger     # rigging language and framework
   ↑
   tik.tools       # user-facing tools and workflows

- **tik.core** defines pure, domain-agnostic value objects.
- **tik.maya** wraps Maya mechanics while depending only on ``tik.core``.
- **tik.shared** hosts cross-tool helpers and shared UI utilities.
- **tik.trigger** (rigging framework) builds on the lower layers without leaking back down.
- **tik.tools** are concrete user experiences; nothing below should import them.

Getting Started
---------------

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   usage/why_tikmaya
   usage/tikmaya_overview
   usage/quickstart

.. toctree::
   :maxdepth: 2
   :caption: Architecture & Reference

   architecture/core_concepts
   API_style_guide

.. toctree::
   :maxdepth: 1
   :caption: API Reference

   autoapi/index


Indices and Tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
