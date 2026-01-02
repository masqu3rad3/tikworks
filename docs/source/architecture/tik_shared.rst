tik.shared
==========

Purpose
-------
Reusable infrastructure and shared UX utilities.

What lives here
---------------

- Cross-tool helpers
- Shared Maya-aware utilities
- Common Qt widgets
- Scene communication helpers
- Reusable UI patterns and components

Examples
--------

- ``tik.shared.scene_data`` (dict-like scene communication)
- feedback / messaging modules
- shared dialogs and panels
- scene_layout selectors
- selection helpers
- inspectors and common widgets

Rules
-----

- May depend on Maya
- May depend on Qt
- Must not define domain ownership or business logic
- Must not encode pipeline- or rig-specific intent

Mental model
------------

``Plumbing and furniture.`` If multiple tools would reimplement it otherwise, it belongs here.
