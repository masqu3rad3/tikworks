TikWorks Documentation
======================

**TikWorks** is a suite of Python tools for Autodesk Maya.
At its core is **Tikmaya** — a modern, Pythonic wrapper for ``maya.cmds`` that serves as the foundation for all TikWorks tools.

.. warning::
   Tikmaya is actively being built. The API and documentation may change as features land.

.. raw:: html

   <div style="padding: 1em; margin-bottom: 1em; background: #f8f9fa; border-radius: 4px;">

**Why TikWorks?** Maya scripting is powerful but verbose. TikWorks brings modern Python patterns to Maya — type safety, object-oriented design, and cleaner syntax — while keeping Maya's flexibility intact.

.. raw:: html

   </div>

The TikWorks Ecosystem
----------------------

TikWorks is designed as a layered ecosystem:

.. code-block:: text

      ┌──────────────────────────────────────────┐
      │           Future Tools                   │
      │    (Trigger, Animation Tools, etc.)      │
      ├──────────────────────────────────────────┤
      │                Tikmaya                   │
      │     (The Core Wrapper Library)           │
      ├──────────────────────────────────────────┤
      │           maya.cmds / OpenMaya           │
      └──────────────────────────────────────────┘

- **Tikmaya** is the spine — a robust wrapper that all other tools build upon
- **Future tools** (like Trigger for rigging) consume Tikmaya's API
- This layered approach ensures consistency across all TikWorks tools

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
