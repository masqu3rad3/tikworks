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
   tik.maya        # disciplined Maya wrapper (ACTIVE)
   ↑
   tik.shared      # reusable infrastructure and UX
   ↑
   tik.trigger     # rigging language and framework (coming soon)
   ↑
   tik.tools       # user-facing tools and workflows (coming soon)

- **tik.core** defines pure, domain-agnostic value objects.
- **tik.maya** wraps Maya mechanics while depending only on ``tik.core``. **This is currently the active and primary component of TikWorks.**
- **tik.shared** hosts cross-tool helpers and shared UI utilities.
- **tik.trigger** is the rigging framework, building on the lower layers.
- **tik.tools** are concrete user-facing tools and workflows.

Currently, **tik.maya** is the fully developed and documented component. Future components
will build on this foundation as they are implemented.

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
