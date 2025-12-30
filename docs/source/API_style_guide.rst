Developer Style Guide
=====================

This guide defines coding conventions for contributing to TikMaya.
Following these patterns keeps the codebase consistent, predictable, and Pythonic.

Philosophy
----------

TikMaya's API should *feel like Python* but *behave like Maya*.

- APIs read naturally in Python
- Scene state remains the source of truth
- Semantic intent is explicit, not inferred
- Every abstraction has a clear responsibility

When designing an API:

- Think about what makes sense to the **user**, not just the implementer
- Prefer explicit intent over implicit magic
- Consistency across modules is more important than individual taste

Properties vs. Methods
----------------------

Use properties for state and methods for actions.
Be explicit when something performs work or has side effects.

**Use** ``@property`` **for:**

- Data-like access to state or computed values
- Simple queries with no side effects
- Booleans, numbers, or small objects representing current state

.. code-block:: python

    @property
    def locked(self) -> bool:
        """Whether the attribute is locked."""
        return cmds.getAttr(f"{self.path}.lock")

    @locked.setter
    def locked(self, state: bool):
        cmds.setAttr(f"{self.path}.lock", state)

    # Usage
    if not attr.locked:
        attr.locked = True

**Use methods for:**

- Operations or actions (verbs)
- Functions that take parameters
- Anything that performs significant work

.. code-block:: python

    def lock(self):
        """Lock the attribute."""
        self.locked = True

    def unlock(self):
        """Unlock the attribute."""
        self.locked = False

**Avoid:**

- Properties that perform heavy operations or cause side effects
- Mixing boolean state *and* action in one name (e.g., ``lock`` as both noun and verb)

Naming Conventions
------------------

- Use **noun-like** names for properties: ``visible``, ``matrix``, ``locked``
- Use **verb-like** names for methods: ``lock()``, ``connect()``, ``freeze()``
- Avoid ``get_`` and ``set_`` prefixes - they are unnecessary in Pythonic APIs
- Keep names short and consistent across modules

.. code-block:: python

    # Good
    @property
    def visible(self): ...

    def show(self): ...
    def hide(self): ...

    # Avoid
    def get_visibility(self): ...
    def set_visibility(self, state): ...

Class Structure
---------------

Classes should follow a consistent structure that reads top-down like a story.

**Recommended order:**

1. Docstring and class variables
2. ``__init__`` and lifecycle methods
3. Public properties (with setters)
4. Primary public methods (main user-facing verbs)
5. Secondary / helper methods
6. Private utilities (``_``-prefixed)
7. Static / class methods

Keep related properties and methods grouped together - not alphabetically.

.. code-block:: python

    class MayaAttribute:
        """Represents a Maya attribute."""

        # === Init / lifecycle ===
        def __init__(self, node, name):
            self.node = node
            self.name = name

        # === Properties ===
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

        # === Public methods ===
        def lock(self):
            self.locked = True

        def unlock(self):
            self.locked = False

        def connect(self, target):
            cmds.connectAttr(self.path, target.path, f=True)

        # === Private helpers ===
        def _exists(self):
            return cmds.objExists(self.path)

Section Headers
---------------

For large classes, group related parts visually with section headers:

.. code-block:: python

    # === Properties ===
    # === Public Methods ===
    # === Private Helpers ===

These are purely cosmetic but help navigation in editors.

Docstrings
----------

Follow PEP 257. Every public class, method, and property should have a docstring.

.. code-block:: python

    def snap_to(self, target, position=True, rotation=True, scale=False):
        """Snap this transform to another transform's position, rotation, and/or scale.

        Args:
            target: The transform to snap to (Transform or string name).
            position: Whether to match position. Defaults to True.
            rotation: Whether to match rotation. Defaults to True.
            scale: Whether to match scale. Defaults to False.

        Raises:
            TypeError: If target is not a Transform node.
        """

Type Hints
----------

Use type hints for function signatures. They enable IDE support and documentation.

.. code-block:: python

    def connect(self, other: "Plug", force: bool = True) -> None:
        """Connect this plug to another plug."""

    @property
    def locked(self) -> bool:
        """Check if the attribute is locked."""

Consistency Checklist
---------------------

+--------------------------------------+-----------------------------------+
| **Rule**                             | **Example**                       |
+======================================+===================================+
| Properties for state                 | ``ctrl.locked``, ``mesh.visible`` |
+--------------------------------------+-----------------------------------+
| Methods for actions                  | ``ctrl.lock()``, ``mesh.freeze()``|
+--------------------------------------+-----------------------------------+
| Group by purpose                     | Keep ``lock()`` near ``unlock()`` |
+--------------------------------------+-----------------------------------+
| Keep properties/setters together     | Avoid separating them             |
+--------------------------------------+-----------------------------------+
| Use section headers                  | For readability in large classes  |
+--------------------------------------+-----------------------------------+
| No ``get_`` / ``set_`` prefixes      | Use direct property syntax        |
+--------------------------------------+-----------------------------------+
| Same structure across all classes    | Predictability matters            |
+--------------------------------------+-----------------------------------+

For architectural concepts (Types, Roles, Constructs), see :doc:`/architecture/core_concepts`.
