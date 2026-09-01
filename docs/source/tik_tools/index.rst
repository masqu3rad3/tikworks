:orphan:

tik.tools
=========

**tik.tools** contains concrete, user-facing tools and workflows built on top of
the TikWorks ecosystem. Each tool has its own dedicated section below.

.. note::
   tik.tools is currently under development. Tool documentation will be added as
   tools are implemented.

What Will Live Here
-------------------

- Individual tool documentation (some may be single pages, others more extensive)
- UI-driven workflows
- Commands, menus, and panels
- Tool orchestration logic

Examples of Future Tools
------------------------

- Rigging utilities
- Controller builders
- Export/import tools
- Batch processing tools
- Pipeline-facing utilities

Dependencies
------------

tik.tools may depend on:

- ``tik.maya`` — for Maya node manipulation
- ``tik.shared`` — for shared infrastructure and UI utilities
- ``tik.trigger`` — for rigging framework integration

Tools are the top of the dependency stack — nothing below should import from
tik.tools.

Available Tools
---------------

*No tools have been documented yet. Check back as development progresses.*

.. This section will contain a toctree for individual tool pages as they are added.
.. Example structure when tools are added:
..
.. .. toctree::
..    :maxdepth: 1
..
..    polish/index
..    controller_builder/index
