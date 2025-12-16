# TikWorks

A modern Python toolkit for Autodesk Maya.

> **Note:** This repository is under active development. APIs may change.

## Overview

TikWorks is a suite of Python tools for Maya, built around **Tikmaya** — a Pythonic wrapper for `maya.cmds` that brings:

- **UUID-based node tracking** — References stay valid after renames
- **Object-oriented API** — Work with typed objects, not strings
- **Less code, more clarity** — Common operations in fewer lines
- **Type safety** — IDE autocomplete and meaningful errors

## Quick Example

```python
import tikmaya

# Wrap existing nodes with automatic type resolution
cube = tikmaya.resolve("pCube1")  # Returns Transform

# Properties for state
cube.translate = (1, 2, 3)
cube["visibility"].value = False

# Methods for actions
cube.freeze(translate=True, rotate=True)

# Attribute connections with operators
locator["translate"] >> cube["translate"]

# Node references survive renames!
cube.rename("myNewCube")
cube.translate_x = 10  # Still works
```

## Documentation

Full documentation is available at [Read the Docs](https://tikworks.readthedocs.io/).

- [Why Tikmaya?](https://tikworks.readthedocs.io/en/latest/usage/why_tikmaya.html) — Benefits over raw `cmds`
- [Quickstart](https://tikworks.readthedocs.io/en/latest/usage/quickstart.html) — Get started in 5 minutes
- [API Reference](https://tikworks.readthedocs.io/en/latest/autoapi/index.html) — Full class and method docs

## The TikWorks Ecosystem

```
┌──────────────────────────────────────────┐
│           Future Tools                   │
│    (Trigger, Animation Tools, etc.)      │
├──────────────────────────────────────────┤
│                Tikmaya                   │
│     (The Core Wrapper Library)           │
├──────────────────────────────────────────┤
│           maya.cmds / OpenMaya           │
└──────────────────────────────────────────┘
```

- **Tikmaya** — Core wrapper library (active)
- **Trigger** — Rigging framework (coming soon)

## Requirements

- Autodesk Maya 2026+
- Python 3.11+

## License

See LICENSE file for details.