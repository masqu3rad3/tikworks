Tikmaya Developer Guidelines
============================

This document outlines the conventions and patterns used throughout **Tikmaya**.
It serves as a reference for contributors and maintainers to keep the codebase consistent, predictable, and Pythonic — while staying closely aligned with the way Maya works.

Tikmaya is intentionally opinionated: clarity and correctness are favored over cleverness or convenience.

The goal is that:
- APIs read naturally in Python
- Scene state remains the source of truth
- Semantic intent is explicit, not inferred
- Every abstraction has a clear responsibility

Following these guidelines ensures that Tikmaya remains:
- Easy to reason about
- Safe for production pipelines
- Extensible without refactoring existing code

Following these conventions helps ensure that Tikmaya modules remain intuitive, minimal, and maintainable — so that any user familiar with one class can quickly understand another.

API Style Guide (Tikmaya)
========================

This guide defines conventions for writing clean, predictable, and consistent API code in **Tikmaya**.

Tikmaya’s API should *feel like Python*, but *behave like Maya*.

That means it should be expressive, explicit when needed, and avoid surprises.

When designing an API surface:

- Think about what makes the most sense to the **user**, not just the implementer.
- Prefer explicit intent over implicit magic.
- Consistency across modules is more important than individual taste.

Example::

    ctrl.locked = True     # state
    ctrl.lock()            # action

---

Core Architectural Concepts
===========================

Tikmaya code is organized around three distinct concepts:

1. Types
2. Roles
3. Constructs

Each serves a different purpose and must not be conflated.

---

Types
-----

**Types describe what a node *is*.**

Types live in:

    tikmaya/core/types

A type is a thin, faithful wrapper around a Maya node type.

Examples:
- Transform
- Curve
- Mesh

Rules for Types:

- Each type maps 1:1 to a Maya node type
- Types are registered in the type registry
- Types may create nodes
- Types expose low-level, structural behavior
- Types never encode semantic meaning

A type should answer questions like:
- What attributes exist?
- How do I create this node?
- How do I query or manipulate its data?

A type should not answer:
- What is this node used for?
- What role does it play in a rig?

---

Roles
-----

**Roles describe what a node *means*.**

Roles live in:

    tikmaya/core/roles

A role is a semantic overlay applied to an existing node.

Examples:
- Controller
- DeformerDriver
- SpaceSwitcher

Rules for Roles:

- Roles are not Maya node types
- Roles are not registered as types
- Roles wrap an existing type instance
- Roles never create new Maya node kinds
- Roles validate that they wrap a compatible base type
- Roles encode their identity in the scene

Roles must always be recoverable from the scene.

---

Constructs
----------

**Constructs orchestrate multiple nodes.**

Constructs live in:

    tikmaya/core/constructs

A construct coordinates several nodes and roles and represents a pattern or setup.

---

Properties vs. Methods
----------------------

Use properties for state and methods for actions.
Be explicit when something performs work or has side effects.

**Use ``@property`` for:**

- Data-like access to state or computed values.
- Simple queries with no side effects.
- Booleans, numbers, or small objects that represent a current state.

Example::

    @property
    def locked(self) -> bool:
        """Whether the attribute is locked."""
        return cmds.getAttr(f"{self.path}.lock")

    @locked.setter
    def locked(self, state: bool):
        cmds.setAttr(f"{self.path}.lock", state)

Usage::

    if not attr.locked:
        attr.locked = True

**Use regular methods for:**

- Operations or actions (verbs).
- Functions that take parameters or perform significant work.
- Anything that changes internal state beyond a simple assignment.

Example::

    def lock(self):
        """Lock the attribute."""
        self.locked = True

    def unlock(self):
        """Unlock the attribute."""
        self.locked = False

**Avoid:**

- Properties that perform heavy operations or cause side effects.
- Mixing boolean state *and* action in one name (for example, using ``lock`` as both noun and verb).

Function and Property Naming
----------------------------

- Use **noun-like** names for properties: ``visible``, ``matrix``, ``locked``
- Use **verb-like** names for methods: ``lock()``, ``connect()``, ``freeze()``
- Avoid ``get_`` and ``set_`` prefixes — they are unnecessary in Pythonic APIs.
- Keep names short and consistent across modules.

Example pattern::

    @property
    def visible(self): ...
    @visible.setter
    def visible(self, state): ...

    def show(self): ...
    def hide(self): ...

Ordering Within a Class
-----------------------

Classes should follow a consistent structure that reads top-down like a story.

**Recommended order:**

1. Docstring / class variables
2. ``__init__`` and lifecycle methods
3. Public properties (with setters)
4. Primary public methods (main user-facing verbs)
5. Secondary / helper methods
6. Private utilities (``_``-prefixed)
7. Static / class methods

Keep related properties and methods grouped together — not alphabetically.

Example::

    class MayaAttribute:
        """Represents a Maya attribute."""

        # --- Init / lifecycle ---
        def __init__(self, node, name):
            self.node = node
            self.name = name

        # --- Properties ---
        @property
        def locked(self):
            return cmds.getAttr(f"{self.path}.lock")

        @locked.setter
        def locked(self, state):
            cmds.setAttr(f"{self.path}.lock", state)

        @property
        def value(self):
            return cmds.getAttr(self.path)

        @value.setter
        def value(self, val):
            cmds.setAttr(self.path, val)

        # --- Public methods ---
        def lock(self):
            self.locked = True

        def unlock(self):
            self.locked = False

        def connect(self, target):
            cmds.connectAttr(self.path, target.path, f=True)

        # --- Private helpers ---
        def _exists(self):
            return cmds.objExists(self.path)

Section Headers
---------------

For large classes, group related parts visually with section headers::

    # === Properties ===
    # === Public Methods ===
    # === Private Helpers ===

These are purely cosmetic but help navigation in editors and generated documentation.

Consistency Across Modules
--------------------------

- Use the same order and naming conventions across all Tikmaya classes.
- Keep public APIs **predictable** — users should be able to guess a method or property name by analogy with others.
- If you add a new module, model it after existing patterns (for example: ``MayaNode``, ``MayaAttribute``, ``MayaTransform``).

Summary Checklist
-----------------

+--------------------------------------+----------------------------------+
| **Rule**                             | **Example**                      |
+======================================+==================================+
| Properties for state                 | ``ctrl.locked``, ``mesh.visible``|
+--------------------------------------+----------------------------------+
| Methods for actions                  | ``ctrl.lock()``, ``mesh.freeze()``|
+--------------------------------------+----------------------------------+
| Group by purpose                     | Keep ``lock()`` near ``unlock()``|
+--------------------------------------+----------------------------------+
| Keep properties/setters together     | Avoid separating them            |
+--------------------------------------+----------------------------------+
| Use section headers                  | For readability in large classes |
+--------------------------------------+----------------------------------+
| No ``get_`` / ``set_`` prefixes      | Use direct property syntax       |
+--------------------------------------+----------------------------------+
| Same structure across all classes    | Predictability matters           |
+--------------------------------------+----------------------------------+

