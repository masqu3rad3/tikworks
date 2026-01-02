tik.core
========

Purpose
-------
Semantic primitives and domain-agnostic concepts that stand alone outside any DCC or UI.

What lives here
---------------

- Pure Python value objects
- Semantic concepts that exist independently of Maya, Qt, or UI
- Deterministic, testable logic
- Small, foundational building blocks

Examples
--------

- Color
- Axis
- Range
- UnitValue
- Enums and constants
- Lightweight math or comparison helpers

Rules
-----

- No Maya
- No Qt
- No UI assumptions
- No filesystem or environment coupling
- No side effects

Mental model
------------

``What things *are*.`` If it still makes sense in isolation, outside any DCC or UI, it belongs here.
