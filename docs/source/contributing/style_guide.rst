API style guide
===============

The conventions tik.maya and TikWorks code follow. The one-line version is the
project motto: **feel like Python, behave like Maya.**

- APIs read naturally in Python.
- Scene state remains the source of truth; nothing caches what could go stale.
- Intent is explicit, never inferred.
- Every abstraction has one clear responsibility.

When designing an API, think about what makes sense to the *user* rather than to
the implementer, prefer explicit intent over implicit magic, and value
consistency across modules over individual taste.

Properties for state, methods for actions
-----------------------------------------

Use ``@property`` for data-like access to state or computed values, simple
queries with no side effects, and booleans, numbers or small objects describing
the current state. Use methods for operations (verbs), anything that takes
parameters, and anything that performs significant work.

.. code-block:: python

   @property
   def locked(self) -> bool:
       """Whether the attribute is locked."""
       return self.mplug.isLocked

   @locked.setter
   def locked(self, state: bool) -> None:
       cmds.setAttr(self.path, edit=True, lock=state)

   def lock(self) -> None:
       """Lock the attribute."""
       self.locked = True

Avoid properties that perform heavy operations or cause side effects, and avoid
one name serving as both noun and verb.

Naming
------

- Noun-like names for properties: ``visible``, ``matrix``, ``locked``.
- Verb-like names for methods: ``lock()``, ``connect()``, ``freeze()``.
- No ``get_`` and ``set_`` prefixes; a property says the same thing in less.
- Short, consistent names across modules. ``create()`` is always the class
  method that makes a node; ``delete()`` always removes one.
- No single-letter variable names, even in comprehensions.

Class structure
---------------

Classes read top-down like a story:

1. Docstring and class variables
2. ``__init__`` and lifecycle methods
3. Public properties, each setter right under its getter
4. Primary public methods
5. Secondary helpers
6. Private utilities (``_``-prefixed)
7. Static and class methods

Group related members together, not alphabetically: ``lock()`` sits next to
``unlock()``. Large classes may use comment banners
(``# === Properties ===``) to make the sections visible in an editor.

Docstrings and type hints
-------------------------

Every public class, method and property has a PEP 257 docstring in the Google
style the repository uses: a one-line summary ending in a period, then
``Args:``, ``Returns:`` and ``Raises:`` sections where they add something.

.. code-block:: python

   def snap_to(self, target, position=True, rotation=True, scale=False):
       """Snap this transform to another transform's position, rotation and/or scale.

       Args:
           target: The transform to snap to (Transform or node name).
           position: Match the world position. Defaults to True.
           rotation: Match the world rotation. Defaults to True.
           scale: Match the scale. Defaults to False.

       Raises:
           TypeError: If ``target`` is not a Transform node.
       """

Type hints go on function signatures. Attribute lists belong in an
``Attributes:`` section of the class docstring, which the documentation build
renders as instance variables.

Undo
----

All scene-modifying operations must be undoable. API-level operations register
with the vendored ``apiundo`` bridge (``tik.maya.core.apicommon.undocommit``);
sequences of ``cmds`` calls are wrapped in a single chunk with the ``@undo``
decorator or ``cmds.undoInfo(openChunk=True)`` / ``closeChunk=True``.

Dependencies and compatibility
------------------------------

- Standard library plus what Maya ships: ``cmds``, OpenMaya 2.0, PySide2 or
  PySide6. No third-party packages without explicit approval.
- Maya 2024 and newer, Python 3.10 and newer.
- ``black`` formatting at the default 88 columns, ``flake8``, ``isort``
  (stdlib, third party, local).

Where code goes
---------------

The architectural rules, the layering and the animator-opinion rule, are in
:doc:`/architecture/overview`. Tools consume tik.maya and do not call ``cmds`` or
OpenMaya directly; when tik.maya lacks something, the fix goes into tik.maya
first.

Consistency checklist
---------------------

.. list-table::
   :header-rows: 1
   :widths: 46 54

   * - Rule
     - Example
   * - Properties for state
     - ``plug.locked``, ``node.visibility``
   * - Methods for actions
     - ``plug.lock()``, ``node.freeze()``
   * - Group by purpose
     - keep ``lock()`` next to ``unlock()``
   * - Getter and setter together
     - never separated by other members
   * - No ``get_`` / ``set_`` prefixes
     - ``node.color = 17``, not ``node.set_color_index(17)``
   * - Same structure in every class
     - learning one type teaches all of them
