# TikWorks

A modern Python toolkit for Autodesk Maya.

> **Note:** This repository is under active development. APIs may change.

## Overview

TikWorks is a suite of Python tools for Maya, built around **TikMaya** (`tik.maya`) — a namespaced, Pythonic wrapper for `maya.cmds` that brings:

- **UUID-based node tracking** — References stay valid after renames
- **Object-oriented API** — Work with typed objects, not strings
- **Less code, more clarity** — Common operations in fewer lines
- **Type safety** — IDE autocomplete and meaningful errors

## Quick Example

```python
import tik.maya as tm

# Wrap existing nodes with automatic type resolution
cube = tm.resolve("pCube1")  # Returns Transform

# Properties for state
cube.translate = (1, 2, 3)
cube["visibility"].value = False

# Methods for actions
cube.freeze(translate=True, rotate=True)

locator = tm.Locator.create(name="locator1")

# Attribute connections with operators
locator["translate"] >> cube["translate"]

# Node references survive renames!
cube.rename("myNewCube")
cube.translate_x = 10  # Still works
```

## Documentation

Full documentation is available at [Read the Docs](https://tikworks.readthedocs.io/).

- [Why TikMaya?](https://tikworks.readthedocs.io/en/latest/usage/why_tikmaya.html) — Benefits over raw `cmds`
- [Quickstart](https://tikworks.readthedocs.io/en/latest/usage/quickstart.html) — Get started in 5 minutes
- [API Reference](https://tikworks.readthedocs.io/en/latest/autoapi/index.html) — Full class and method docs

## The TikWorks Ecosystem

```
┌─────────────────────────────────────────────────────┐
│                  Future Tools                       │
│      (Trigger, Animation, Pipeline, etc.)           │
├─────────────────────────────────────────────────────┤
│                      TikMaya                        │
│        Core Maya wrapper (builds on cmds/API)       │
├─────────────────────────────────────────────────────┤
│                    tik.shared                       │
│    Cross-cutting utilities used across packages     │
├─────────────────────────────────────────────────────┤
│                 maya.cmds / OpenMaya                │
└─────────────────────────────────────────────────────┘
```

- **TikMaya** — Core wrapper library (active)
- **tik.shared** — Shared utilities for all Tik packages
- **Trigger** — Rigging framework (coming soon)

## Requirements

- Autodesk Maya 2026+
- Python 3.11+

## License

See LICENSE file for details.
