TikWorks Documentation
======================

**TikWorks** is an ecosystem of Python tools and frameworks for Autodesk Maya.
It is designed to grow with your needs — from a modern Maya wrapper to a complete
rigging infrastructure.

.. warning::
   TikWorks is actively being built. The API and documentation may change as features land.

The TikWorks Ecosystem
----------------------

TikWorks is not a single library. It is a layered ecosystem where each package builds
on the foundations below it. This strict dependency flow keeps the system maintainable
and predictable:

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
- **tik.trigger** is the rigging framework, building on the lower layers.
- **tik.tools** are concrete user-facing tools and workflows.

Each pillar has its own dedicated documentation section. Start with the one that
matches your needs.

.. tip::
   **Why TikWorks?** Maya scripting is powerful but verbose. TikWorks brings modern
   Python patterns to Maya — type safety, object-oriented design, and cleaner syntax
   — while keeping Maya's flexibility intact.

.. toctree::
   :maxdepth: 2
   :caption: tik.maya

   tik_maya/index

.. toctree::
   :maxdepth: 2
   :caption: tik.trigger

   tik_trigger/index

.. toctree::
   :maxdepth: 2
   :caption: tik.tools

   tik_tools/index

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
