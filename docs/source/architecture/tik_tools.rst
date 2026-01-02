tik.tools
=========

Purpose
-------
Concrete, user-facing tools and workflows.

What lives here
---------------

- Actual tools users run
- UI-driven workflows
- Commands, menus, and panels
- Tool orchestration logic

Examples
--------

- Rigging tools
- Controller builders
- Export/import tools
- Batch tools with UI
- Pipeline-facing utilities

Rules
-----

- May depend on ``tik.maya``
- May depend on ``tik.shared``
- May depend on ``tik.trigger``
- Must not be depended on by lower layers

Mental model
------------

``This does something.`` If it feels like a button, a menu item, or a workflow, it belongs here.
