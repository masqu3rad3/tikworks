TikWorks Package Structure and Responsibilities
==============================================

This document defines the purpose, scope, and separation rules for the main
TikWorks packages. These boundaries keep dependencies flowing in one direction,
responsibilities clear, and the system maintainable as it grows.

tik.core
--------

**Purpose:** Semantic primitives and domain-agnostic concepts.

**What lives here**

- Pure Python value objects
- Semantic concepts that exist independently of Maya, Qt, or UI
- Deterministic, testable logic
- Small, foundational building blocks

**Examples**

- Color
- Axis
- Range
- UnitValue
- Enums and constants
- Lightweight math or comparison helpers

**Rules**

- No Maya
- No Qt
- No UI assumptions
- No filesystem or environment coupling
- No side effects

**Mental model**

``What things *are*.``

If it still makes sense in isolation, outside any DCC or UI, it belongs here.

tik.maya
--------

**Purpose:** A disciplined, boring wrapper around Autodesk Maya.

**What lives here**

- Node wrappers
- DAG traversal
- Attribute access
- Scene interaction
- OpenMaya integration
- Maya-specific abstractions

**Examples**

- Node
- DagNode
- ShapeNode
- Scene
- Registry and resolve logic
- Maya-specific decorators

**Rules**

- May depend on ``tik.core``
- Must not depend on Qt
- Must not depend on tools or UI
- Must mirror Maya behavior rather than reinterpret it
- Should remain predictable and mechanical

**Mental model**

``How things exist *inside Maya*.``

If it does not make sense without Maya, it belongs here.

tik.shared
----------

**Purpose:** Reusable infrastructure and shared UX utilities.

**What lives here**

- Cross-tool helpers
- Shared Maya-aware utilities
- Common Qt widgets
- Scene communication helpers
- Reusable UI patterns and components

**Examples**

- ``tik.shared.scene_data`` (dict-like scene communication)
- feedback / messaging modules
- shared dialogs and panels
- scene_layout selectors
- selection helpers
- inspectors and common widgets

**Rules**

- May depend on Maya
- May depend on Qt
- Must not define domain ownership or business logic
- Must not encode pipeline- or rig-specific intent

**Mental model**

``Plumbing and furniture.``

If multiple tools would reimplement it otherwise, it belongs here.

tik.trigger
-----------

**Purpose:** A rigging and automation framework for Maya.

**What lives here**

- Rig blueprints
- Rig components
- Behavioral rules and relationships
- Automation graphs
- Abstractions over Maya mechanics
- Authoring and execution logic for rigs

This is not a utility layer. This is a system.

**Rules**

- May depend on ``tik.maya``
- May depend on ``tik.shared``
- May use Qt for authoring, debugging, and visualization
- Must not leak its concepts downward
- Must not be required for basic Maya usage

**Mental model**

``A rigging language and framework.``

This is intent, structure, and meaning, not infrastructure.

tik.tools
---------

**Purpose:** Concrete, user-facing tools and workflows.

**What lives here**

- Actual tools users run
- UI-driven workflows
- Commands, menus, and panels
- Tool orchestration logic

**Examples**

- Rigging tools
- Controller builders
- Export/import tools
- Batch tools with UI
- Pipeline-facing utilities

**Rules**

- May depend on ``tik.maya``
- May depend on ``tik.shared``
- May depend on ``tik.trigger``
- Must not be depended on by lower layers

**Mental model**

``This does something.``

If it feels like a button, a menu item, or a workflow, it belongs here.

Dependency Direction
--------------------

Dependencies must flow downward only:

.. code-block:: text

   tik.core
   ↑
   tik.maya
   ↑
   tik.shared
   ↑
   tik.trigger
   ↑
   tik.tools

**Forbidden**

- Lower layers importing higher layers
- Qt leaking into ``tik.maya``
- Maya leaking into ``tik.core``
- Tools becoming libraries

One-line Cheat Sheet
--------------------

- ``tik.core``: what things *are*
- ``tik.maya``: how things exist *in Maya*
- ``tik.shared``: reusable *infrastructure and UX*
- ``tik.trigger``: *intent, behavior, and rig logic*
- ``tik.tools``: *actions users perform*

When in doubt, ask:

``Does this describe reality, infrastructure, intent, or action?``

Then put it where it can do the least damage.
