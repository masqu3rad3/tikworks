Tikmaya Developer Guidelines
============================

This document outlines the conventions and patterns used throughout **Tikmaya**.
It serves as a reference for contributors and maintainers to keep the codebase consistent, predictable, and Pythonic — while staying closely aligned with the way Maya works.

Each section below provides guidance on naming, structure, and API design philosophy, including:
- When to use properties versus methods
- Recommended ordering of functions inside a class
- Naming consistency and readability practices
- Shared expectations across all Tikmaya modules

Following these conventions helps ensure that Tikmaya modules remain intuitive, minimal, and maintainable — so that any user familiar with one class can quickly understand another.

API Style Guide (Tikmaya)
=========================

This guide defines conventions for writing clean, predictable, and consistent API code in **Tikmaya**.
It aims to make the library easy to read, maintain, and extend — both for you and for anyone using or contributing to it.

General Philosophy
------------------

Tikmaya’s API should *feel like Python*, but *behave like Maya*.
That means it should be expressive, explicit when needed, and avoid surprises.

When designing an API surface:

- Think about what makes the most sense to the **user**, not just the developer.
- Choose names and structures that read naturally::

    ctrl.locked = True      # feels like an attribute
    ctrl.lock()             # feels like an action

Consistency across modules is more important than personal style.

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
