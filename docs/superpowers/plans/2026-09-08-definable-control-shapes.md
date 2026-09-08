# Definable Control Shapes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a rigger choose the shape and relative size of every controller a tik.trigger module builds, per module instance, stored in the `.tr` and picked from a visual thumbnail library.

**Architecture:** The shape resolver and its 172 data files move down to `tik.core`, which both `tik.maya` (for `Controller.set_shape`) and `tik.shared.ui` (for a headless picker) may import — `tik/maya/__init__.py` requires a live Maya, so no home above core is reachable by both. Modules declare a default shape per control role in the manifest; `rig.controller` loses its `shape=` parameter and resolves override → manifest → `"Circle"` instead. The rigger's overrides are a sparse `TableField` on the `Module` base, edited through a per-control fold. The build resolves through a pinned library that excludes `~/TikWorks/user_control_shapes`, so a preference cannot change a rig.

**Tech Stack:** Python 3.10+, Maya 2024+ (`mayapy`), PySide via `tik.shared.ui.Qt`, pytest. No third-party dependencies.

**Spec:** `docs/superpowers/specs/2026-09-08-definable-control-shapes-design.md`

## Global Constraints

- **No third-party deps.** Standard library and Maya-bundled modules only.
- **Layering** (`tests/unit/test_import_boundaries.py`): `tik/core` may not import `maya`, `tik.maya`, `tik.trigger`, `tik.shared`, or Qt. `tik/maya` may not import `tik.trigger`, `tik.shared`, or Qt. `tik/trigger/core` may not import `maya`, `tik.maya`, `tik.trigger.actions`, Qt, the prefs packages, or `tik.trigger.vcs`.
- **Consume tik.maya** — no raw `maya.cmds` / `OpenMaya` in tool code outside `tik/maya` itself.
- **One dialog surface** — every dialog goes through `tik.shared.ui.feedback.Feedback` (`tests/unit/test_dialog_boundaries.py`).
- **`.tr` schema stays at 7.** Control-shape overrides are an ordinary module setting.
- **Commit after every task.** End each commit message with:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_016Pestf7onXtLxZJuC31yyF
  ```

## Commands

Run from the repository root (Git Bash):

```bash
# One unit test file
PYTHONPATH="$PWD/src/python" mayapy -m pytest tests/unit/test_x.py -q

# One UI test file (no Maya)
TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH="$PWD/src/python" \
  mayapy -m pytest tests/ui/test_x.py -q

# One integration test file
PYTHONPATH="$PWD/src/python" MAYA_PLUG_IN_PATH="$PWD/src/plugins/python" \
  mayapy -m pytest tests/integration/trigger/test_x.py -q

# Full suites
make tests-unit ; make tests-integration ; make tests-ui ; make lint
```

## File Structure

| File | Responsibility |
|------|----------------|
| `src/python/tik/core/control_shapes.py` | **New.** Pure resolver: search paths, name→file index, categories, thumbnail sibling, JSON load, save/normalise helpers |
| `src/python/tik/core/data/control_shapes/` | **New (moved).** 172 shape files, 86 shapes in 9 categories |
| `src/python/tik/maya/utils/control_shapes.py` | Keeps scene capture only; re-exports the resolver for back-compat |
| `src/python/tik/core/fields.py` | `Column` kinds `"shape"`/`"float"`; `TableField.rows_from` |
| `src/python/tik/trigger/core/shapes.py` | **New.** The pinned build library (no user path) |
| `src/python/tik/trigger/core/module.py` | `control_shapes`, `control_shape_defaults`, `SHAPES`, `control_shape_overrides`, two new `warnings()` checks |
| `src/python/tik/trigger/maya/rig.py` | `controller()` drops `shape=` and resolves it |
| `src/python/tik/trigger/systems/limb.py` | `limb_control_shapes`; no `shape=` at call sites |
| `src/python/tik/trigger/modules/{arm,base,fkchain,ribbon}` | Declare manifest defaults |
| `src/python/tik/shared/ui/shape_picker.py` | **New.** `ShapePicker`, `ShapeButton` |
| `src/python/tik/shared/ui/fields.py` | `_ControlShapeEditor` (the per-control fold) |
| `src/python/tik/tools/polish/ui/mcv/controller_shapes_mcv.py` | Rebuilt on `ShapePicker` |

---

## Task 1: Move the shape library to tik.core

Splits `tik/maya/utils/control_shapes.py` in two. The resolver and the data go to `tik.core`; the OpenMaya capture utilities stay. Also makes the user path opt-in and stops `__init__` creating directories.

**Files:**
- Create: `src/python/tik/core/control_shapes.py`
- Move: `src/python/tik/maya/data/control_shapes/` → `src/python/tik/core/data/control_shapes/`
- Modify: `src/python/tik/maya/utils/control_shapes.py`
- Test: `tests/unit/test_control_shapes.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `tik.core.control_shapes.ControlShapeLibrary(include_user_path: bool = True)` with `user_path`, `search_paths`, `get_instance()`, `add_path(path)`, `remove_path(path)`, `refresh()`, `list_shapes() -> list[str]`, `get_shape_data() -> dict`, `get_path(name) -> Path | None`, `load(name) -> dict | None`
  - `tik.core.control_shapes.get_home_dir() -> str`, `save_to_disk(data, name, folder_path, category=None) -> str`, `_resolve_folder_path`, `_normalize_ratio`, `_scale_data`
  - `tik.maya.utils.control_shapes` still exposes all of the above by re-export, plus `capture`, `capture_to_disk`, `capture_thumbnail`, `CAMERA_POSITIONS`, `_guess_camera_view`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_control_shapes.py`:

```python
def test_library_lives_in_core_and_needs_no_maya():
    """The resolver must import without Maya: the picker runs headless."""
    import ast
    from pathlib import Path

    import tik.core.control_shapes as core_shapes

    assert core_shapes.ControlShapeLibrary is ControlShapeLibrary

    source = Path(core_shapes.__file__).read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module)
    banned = [
        name
        for name in imported
        if name == "maya" or name.startswith(("maya.", "tik.maya", "tik.shared"))
    ]
    assert banned == [], f"core resolver imports {banned}"


def test_shipped_shapes_moved_to_core():
    from pathlib import Path

    import tik.core.control_shapes as core_shapes

    core_path = Path(core_shapes.__file__).parent / "data" / "control_shapes"
    assert core_path.is_dir()
    assert len(list(core_path.rglob("*.json"))) == 86
    assert (core_path / "basics" / "Circle.json").exists()
    assert (core_path / "animated" / "FkikSwitch.json").exists()


def test_user_path_is_opt_in(tmp_path, monkeypatch, clean_library):
    """The build pins its library by excluding the per-user folder."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    user_shapes = tmp_path / "TikWorks" / "user_control_shapes"
    user_shapes.mkdir(parents=True)
    (user_shapes / "OnlyMine.json").write_text('{"name": "OnlyMine", "curves": []}')

    with_user = ControlShapeLibrary(include_user_path=True)
    without_user = ControlShapeLibrary(include_user_path=False)

    assert "OnlyMine" in with_user.list_shapes()
    assert "OnlyMine" not in without_user.list_shapes()
    assert user_shapes not in without_user.search_paths


def test_construction_creates_no_directories(tmp_path, monkeypatch, clean_library):
    """Creating a directory as an import side effect is wrong."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    ControlShapeLibrary()
    assert not (tmp_path / "TikWorks").exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
PYTHONPATH="$PWD/src/python" mayapy -m pytest tests/unit/test_control_shapes.py -q
```
Expected: FAIL — `ModuleNotFoundError: No module named 'tik.core.control_shapes'`.

- [ ] **Step 3: Move the data files**

```bash
mkdir -p src/python/tik/core/data
git mv src/python/tik/maya/data/control_shapes src/python/tik/core/data/control_shapes
```

- [ ] **Step 4: Create the pure resolver**

Create `src/python/tik/core/control_shapes.py`. Move `get_home_dir`, `CURRENT_PLATFORM`, `ControlShapeLibrary`, `save_to_disk`, `_resolve_folder_path`, `_normalize_ratio` and `_scale_data` from `tik/maya/utils/control_shapes.py` verbatim, then apply exactly three changes:

```python
"""Control shape library: the name -> curve-data index.

Pure paths and JSON, so both ``tik.maya`` (which cannot import ``tik.shared``)
and the headless Qt picker (which cannot import ``tik.maya``, since importing
it requires a live Maya) can reach it. Curve capture lives in
``tik.maya.utils.control_shapes``; nothing here touches a scene.
"""

from __future__ import annotations

import json
import logging
import os
import platform
from pathlib import Path

LOG = logging.getLogger(__name__)

CURRENT_PLATFORM = platform.system()
```

1. `__init__` gains the flag and stops creating the directory:

```python
    def __init__(self, include_user_path: bool = True):
        """Initialize the shape library with default search paths.

        Args:
            include_user_path: Search ``~/TikWorks/user_control_shapes``.
                A rig build passes ``False``: a per-user folder is a
                preference, and a preference must never change a rig.
        """
        self._cache = {}
        self._custom_paths = []
        self._include_user_path = include_user_path

        # 1. Core Path -- the shipped catalogue, beside this module.
        self._core_path = Path(__file__).absolute().parent / "data" / "control_shapes"

        # 2. User Path (always *defined*, only conditionally searched). Not
        # created here: making a directory as an import side effect is wrong.
        self._user_path = Path(get_home_dir(), "TikWorks", "user_control_shapes")
```

2. `search_paths` honours the flag:

```python
        paths = [self._core_path]
        if self._include_user_path:
            paths.append(self._user_path)
```

3. Everything else — `user_path`, `get_instance`, `add_path`, `remove_path`, `refresh`, `list_shapes`, `get_shape_data`, `get_path`, `load`, `save_to_disk`, `_resolve_folder_path`, `_normalize_ratio`, `_scale_data` — moves unchanged.

- [ ] **Step 5: Reduce the Maya module to capture, re-exporting the rest**

Rewrite the head of `src/python/tik/maya/utils/control_shapes.py`:

```python
"""Capturing control shapes out of a Maya scene.

The library itself is pure and lives in :mod:`tik.core.control_shapes`; it is
re-exported here so existing call sites keep working. Only the capture
utilities below need a scene.
"""

from __future__ import annotations

import logging

import maya.api.OpenMaya as om
from maya import cmds

from tik.core.control_shapes import (  # noqa: F401 - re-exported for callers
    CURRENT_PLATFORM,
    ControlShapeLibrary,
    _normalize_ratio,
    _resolve_folder_path,
    _scale_data,
    get_home_dir,
    save_to_disk,
)

from ..constructs import Panel
from ..core.registry import resolve
from ..types.camera import Camera

LOG = logging.getLogger(__name__)

CAMERA_POSITIONS = {
    "front": (0, 0, 10),
    "back": (0, 0, -10),
    "left": (-10, 0, 0),
    "right": (10, 0, 0),
    "top": (0, 10, 0),
    "bottom": (0, -10, 0),
    "iso": (10, 10, 10),
    "oneThird": (10, 5, 5),
}
```

Delete the moved definitions (`get_home_dir`, `ControlShapeLibrary`, `save_to_disk`, `_resolve_folder_path`, `_normalize_ratio`, `_scale_data`) from this file. Keep `capture_to_disk`, `capture`, `capture_thumbnail` and `_guess_camera_view` exactly as they are.

**Note:** `tik/maya/utils/control_shapes.py` may import `tik.core` — only `tik.trigger`, `tik.shared` and Qt are forbidden there.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
PYTHONPATH="$PWD/src/python" mayapy -m pytest tests/unit/test_control_shapes.py tests/unit/test_controller.py tests/unit/test_import_boundaries.py -q
```
Expected: PASS. If `test_get_home_dir` fails, it monkeypatches `control_shapes.CURRENT_PLATFORM` — repoint that test at `tik.core.control_shapes`, since the re-export binds a copy of the value, not the module attribute.

- [ ] **Step 7: Commit**

```bash
git add -A src/python/tik/core src/python/tik/maya tests/unit/test_control_shapes.py
git commit -m "refactor: move the control shape library to tik.core

tik/maya/__init__.py imports maya.cmds, so importing anything under
tik.maya needs a live Maya -- and tik.maya may not import tik.shared.
A headless Qt picker and Controller.set_shape therefore have no shared
home above core. Splits the pure resolver and its 172 data files out of
the OpenMaya capture utilities and moves them down.

The user path becomes opt-in so a rig build can pin its library, and
construction no longer creates ~/TikWorks/user_control_shapes as an
import side effect.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016Pestf7onXtLxZJuC31yyF"
```

---

## Task 2: `rows_from` and the new Column kinds

Adds the two column kinds the shape row needs and the opt-in flag that swaps the table's editor. Pure `tik.core`, no Qt.

**Files:**
- Modify: `src/python/tik/core/fields.py`
- Test: `tests/unit/test_fields.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Column(name, kind="string"|"choice"|"shape"|"float", choices=(), choices_from="", label="")`
  - `TableField(default, *, columns=(), rows_from="", **kwargs)`; `TableField.rows_from` is `""` when not opted in; `to_schema()["rows_from"]` carries it
  - A `"float"` column coerces to `float`; an empty entry stays `""` (meaning "unset")

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_fields.py`:

```python
def test_table_field_rows_from_defaults_to_empty():
    from tik.core.fields import Column, TableField

    field = TableField([], columns=(Column("control", "choice"),))
    assert field.rows_from == ""
    assert field.to_schema()["rows_from"] == ""


def test_table_field_records_rows_from():
    from tik.core.fields import Column, TableField

    field = TableField(
        [], columns=(Column("control", "choice"),), rows_from="control_names"
    )
    assert field.rows_from == "control_names"
    assert field.to_schema()["rows_from"] == "control_names"


def test_float_column_coerces_numbers_and_keeps_unset_empty():
    from tik.core.fields import Column, Schema, TableField

    class Target(Schema):
        rows = TableField(
            [], columns=(Column("control"), Column("size", "float"))
        )

    target = Target()
    target.rows = [
        {"control": "ik", "size": "1.5"},
        {"control": "fk", "size": 2},
        {"control": "pole"},
    ]
    assert target.rows[0]["size"] == 1.5
    assert target.rows[1]["size"] == 2.0
    # Unset stays unset: 0.0 would be a real multiplier that collapses a shape.
    assert target.rows[2]["size"] == ""


def test_float_column_rejects_nonsense():
    from tik.core.fields import Column, FieldValidationError, Schema, TableField

    class Target(Schema):
        rows = TableField([], columns=(Column("size", "float"),))

    target = Target()
    with pytest.raises(FieldValidationError):
        target.rows = [{"size": "wide"}]


def test_shape_column_is_a_plain_string_column():
    """The kind only picks an editor; storage stays a name."""
    from tik.core.fields import Column, Schema, TableField

    class Target(Schema):
        rows = TableField([], columns=(Column("shape", "shape"),))

    target = Target()
    target.rows = [{"shape": "Cube"}]
    assert target.rows == [{"shape": "Cube"}]
    assert target.to_schema()["rows"]["columns"][0]["kind"] == "shape"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
PYTHONPATH="$PWD/src/python" mayapy -m pytest tests/unit/test_fields.py -q -k "rows_from or float_column or shape_column"
```
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'rows_from'`.

- [ ] **Step 3: Implement**

In `src/python/tik/core/fields.py`, update the `Column` docstring line and `TableField`:

```python
@dataclass(frozen=True)
class Column:
    """One column of a :class:`TableField`.
    ...
    """

    name: str
    kind: str = "string"  # "string" | "choice" | "shape" | "float"
```

`TableField.__init__` takes the flag:

```python
    def __init__(
        self,
        default=None,
        *,
        columns: Sequence[Column] = (),
        rows_from: str = "",
        **kwargs,
    ) -> None:
        """A table of records.

        ``rows_from`` names an attribute on the *target object* supplying the
        row set, the way ``Column.choices_from`` supplies a column's options.
        Naming it means the rows are fixed by the target rather than added by
        hand, and the stored value is a *sparse* set of overrides: a row exists
        only for an entry the user actually changed.
        """
        self.columns = tuple(columns)
        self.rows_from = rows_from
        super().__init__([dict(row) for row in default] if default else [], **kwargs)
```

In `coerce`, add the float branch beside the choice check:

```python
            filled = {}
            for column in self.columns:
                entry = row.get(column.name, "")
                if column.kind == "choice" and column.choices and entry:
                    if entry not in column.choices:
                        raise FieldValidationError(
                            self.name,
                            value,
                            f"'{column.name}' must be one of {list(column.choices)}",
                        )
                if column.kind == "float" and entry != "":
                    try:
                        entry = float(entry)
                    except (TypeError, ValueError):
                        raise FieldValidationError(
                            self.name, value, f"'{column.name}' must be a number"
                        ) from None
                filled[column.name] = entry
            rows.append(filled)
```

And carry the flag in `to_schema`:

```python
    def to_schema(self) -> dict:
        """The base schema plus the column definitions and the row source."""
        schema = super().to_schema()
        schema["rows_from"] = self.rows_from
        schema["columns"] = [
            ...unchanged...
        ]
        return schema
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
PYTHONPATH="$PWD/src/python" mayapy -m pytest tests/unit/test_fields.py -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/core/fields.py tests/unit/test_fields.py
git commit -m "feat(fields): add rows_from and the shape/float column kinds

rows_from names an attribute on the target that supplies the row set,
the way choices_from supplies a column's options -- which makes the
stored value a sparse set of overrides rather than a hand-added list.
An unset float column stays empty rather than coercing to 0.0, since
0.0 is a real multiplier that would collapse a shape.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016Pestf7onXtLxZJuC31yyF"
```

---

## Task 3: The pinned build library

One library the build and the picker share, excluding the per-user folder.

**Files:**
- Create: `src/python/tik/trigger/core/shapes.py`
- Create: `tests/unit/test_pinned_shapes_trigger.py`
- Modify: `src/python/tik/trigger/core/__init__.py`

**Interfaces:**
- Consumes: `tik.core.control_shapes.ControlShapeLibrary` (Task 1).
- Produces:
  - `tik.trigger.core.shapes.library() -> ControlShapeLibrary` (cached singleton)
  - `tik.trigger.core.shapes.shape_names() -> tuple[str, ...]` (sorted)
  - `tik.trigger.core.shapes.has_shape(name: str) -> bool`
  - `tik.trigger.core.shapes.reset()` — drops the cache, for tests
  - `tik.trigger.core.shapes.SHAPES_ENV = "TRIGGER_SHAPES_PATH"`
  - `tik.trigger.core.shapes.DEFAULT_SHAPE = "Circle"`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_pinned_shapes_trigger.py`:

```python
"""The build resolves shapes through a library a preference cannot reach."""

from __future__ import annotations

import pytest

from tik.trigger.core import shapes


@pytest.fixture(autouse=True)
def _reset():
    shapes.reset()
    yield
    shapes.reset()


def test_shipped_shapes_resolve():
    assert shapes.has_shape("Circle")
    assert shapes.has_shape("Cube")
    assert shapes.has_shape("FkikSwitch")
    assert not shapes.has_shape("NoSuchShape")


def test_shape_names_are_sorted_and_unique():
    names = shapes.shape_names()
    assert names == tuple(sorted(set(names)))
    assert "Diamond" in names


def test_the_user_path_is_not_searched(tmp_path, monkeypatch):
    """A personal folder is a preference; a preference cannot change a rig."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    user_shapes = tmp_path / "TikWorks" / "user_control_shapes"
    user_shapes.mkdir(parents=True)
    (user_shapes / "PersonalOnly.json").write_text('{"name": "x", "curves": []}')
    shapes.reset()

    assert not shapes.has_shape("PersonalOnly")
    assert user_shapes not in shapes.library().search_paths


def test_a_user_shape_cannot_shadow_a_shipped_one(tmp_path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    user_shapes = tmp_path / "TikWorks" / "user_control_shapes"
    user_shapes.mkdir(parents=True)
    (user_shapes / "Circle.json").write_text('{"name": "Circle", "curves": []}')
    shapes.reset()

    loaded = shapes.library().load("Circle")
    assert loaded["curves"], "the shipped Circle must win over a personal one"


def test_studio_paths_are_honoured(tmp_path, monkeypatch):
    """A deployed path is the same for everyone, so it may add shapes."""
    studio = tmp_path / "studio_shapes"
    studio.mkdir()
    (studio / "StudioPin.json").write_text('{"name": "StudioPin", "curves": []}')
    monkeypatch.setenv(shapes.SHAPES_ENV, str(studio))
    shapes.reset()

    assert shapes.has_shape("StudioPin")
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
PYTHONPATH="$PWD/src/python" mayapy -m pytest tests/unit/test_pinned_shapes_trigger.py -q
```
Expected: FAIL — `ImportError: cannot import name 'shapes'`.

- [ ] **Step 3: Implement**

Create `src/python/tik/trigger/core/shapes.py`:

```python
"""The shape library a rig build resolves through.

Pinned on purpose. ``tik.core``'s library searches
``~/TikWorks/user_control_shapes`` after the shipped set, so a personal
``Circle.json`` silently replaces the shipped one -- and two artists building
the same ``.tr`` get different rigs. A per-user folder is a preference by any
reasonable reading, and *a preference can never change a rig*, so the build
does not search it.

``TRIGGER_SHAPES_PATH`` is the escape hatch, and it is the right one: a studio
path is deployed and version-controlled, so it resolves the same for everyone.
A personal shape has to be promoted to such a path before a rig can use it.

The picker reads this same library, so it is not possible to choose a shape the
build cannot resolve.
"""

from __future__ import annotations

import os
from typing import Optional

from tik.core.control_shapes import ControlShapeLibrary

SHAPES_ENV = "TRIGGER_SHAPES_PATH"
"""Deployed, version-controlled roots added to the pinned search order."""

DEFAULT_SHAPE = "Circle"
"""The shape a control falls back to when nothing declares one."""

_LIBRARY: Optional[ControlShapeLibrary] = None


def library() -> ControlShapeLibrary:
    """The pinned library: the shipped set plus ``TRIGGER_SHAPES_PATH``."""
    global _LIBRARY  # noqa: PLW0603 - one cached library per process
    if _LIBRARY is None:
        found = ControlShapeLibrary(include_user_path=False)
        for entry in os.environ.get(SHAPES_ENV, "").split(os.pathsep):
            if entry:
                found.add_path(entry)
        _LIBRARY = found
    return _LIBRARY


def reset() -> None:
    """Drop the cached library, so a changed environment is picked up."""
    global _LIBRARY  # noqa: PLW0603 - one cached library per process
    _LIBRARY = None


def shape_names() -> tuple[str, ...]:
    """Every resolvable shape name, sorted."""
    return tuple(sorted(library().list_shapes()))


def has_shape(name: str) -> bool:
    """Whether ``name`` resolves in the pinned library."""
    return bool(name) and name in set(library().list_shapes())
```

Export it from `src/python/tik/trigger/core/__init__.py` alongside the existing names:

```python
from . import shapes  # noqa: F401 - the pinned shape library
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
PYTHONPATH="$PWD/src/python" mayapy -m pytest tests/unit/test_pinned_shapes_trigger.py tests/unit/test_import_boundaries.py -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/core/shapes.py src/python/tik/trigger/core/__init__.py tests/unit/test_pinned_shapes_trigger.py
git commit -m "feat(trigger): add the pinned build shape library

~/TikWorks/user_control_shapes currently resolves after the shipped set,
so a personal Circle.json silently replaces the shipped one and two
artists building the same .tr get different rigs. The build now resolves
through a library that excludes it, applying the preferences guarantee to
shapes. TRIGGER_SHAPES_PATH stays open for deployed studio roots.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016Pestf7onXtLxZJuC31yyF"
```

---

## Task 4: The manifest declaration and the override table

Adds the module-side declaration, the sparse override table, the resolution helper both the build and the UI call, and the two `warnings()` checks. Pure — no Maya, no Qt.

**Files:**
- Modify: `src/python/tik/trigger/core/module.py`
- Modify: `src/python/tik/trigger/systems/limb.py`
- Test: `tests/unit/test_shape_resolution_trigger.py` (create), `tests/unit/test_core_trigger.py`

**Interfaces:**
- Consumes: `TableField(..., rows_from=)` and the `"shape"`/`"float"` kinds (Task 2); `tik.trigger.core.shapes.DEFAULT_SHAPE`, `has_shape` (Task 3).
- Produces:
  - `Module.control_shapes: dict[str, str]` — class attribute, `{}` by default
  - `Module.control_shape_defaults(cls, settings=None) -> dict[str, str]`
  - `Module.control_shape_overrides` — the sparse `TableField`
  - `Module.resolve_control_shape(self, role: str) -> tuple[str, float]` — the effective `(shape_name, size_multiplier)`
  - `Module.SHAPES` — the `FieldGroup`
  - `tik.trigger.systems.limb.limb_control_shapes(name="", labels=()) -> dict[str, str]`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_shape_resolution_trigger.py`:

```python
"""Shape resolution: rigger override -> module manifest -> the fallback."""

from __future__ import annotations

import pytest

from tik.trigger.core import shapes
from tik.trigger.core.module import Module


class Toy(Module):
    module_type = "toy"
    controls = ("ik", "fk", "pole")
    control_shapes = {"ik": "Cube", "fk": "Circle"}


def test_manifest_default_wins_when_nothing_is_overridden():
    toy = Toy()
    assert toy.resolve_control_shape("ik") == ("Cube", 1.0)
    assert toy.resolve_control_shape("fk") == ("Circle", 1.0)


def test_an_undeclared_control_falls_back():
    """'pole' is a control with no manifest default."""
    assert Toy().resolve_control_shape("pole") == (shapes.DEFAULT_SHAPE, 1.0)


def test_an_override_wins_over_the_manifest():
    toy = Toy()
    toy.control_shape_overrides = [{"control": "ik", "shape": "Diamond", "size": 2.0}]
    assert toy.resolve_control_shape("ik") == ("Diamond", 2.0)
    # Untouched controls keep their manifest default.
    assert toy.resolve_control_shape("fk") == ("Circle", 1.0)


def test_resolution_is_per_field_not_per_row():
    """A row setting only a size keeps the manifest shape, and vice versa."""
    toy = Toy()
    toy.control_shape_overrides = [
        {"control": "ik", "size": 3.0},
        {"control": "fk", "shape": "Diamond"},
    ]
    assert toy.resolve_control_shape("ik") == ("Cube", 3.0)
    assert toy.resolve_control_shape("fk") == ("Diamond", 1.0)


def test_deleting_a_row_reverts_to_the_module_default():
    toy = Toy()
    toy.control_shape_overrides = [{"control": "ik", "shape": "Diamond"}]
    assert toy.resolve_control_shape("ik") == ("Diamond", 1.0)
    toy.control_shape_overrides = []
    assert toy.resolve_control_shape("ik") == ("Cube", 1.0)


def test_an_unresolvable_override_falls_back_to_the_manifest():
    toy = Toy()
    toy.control_shape_overrides = [{"control": "ik", "shape": "NotAShape", "size": 2.0}]
    # The size still applies: only the unknown name is discarded.
    assert toy.resolve_control_shape("ik") == ("Cube", 2.0)


def test_the_table_is_sparse_and_round_trips():
    toy = Toy()
    toy.control_shape_overrides = [{"control": "ik", "shape": "Diamond"}]
    values = toy.values()
    assert values["control_shape_overrides"] == [
        {"control": "ik", "shape": "Diamond", "size": ""}
    ]
    other = Toy()
    other.apply(values, strict=False)
    assert other.resolve_control_shape("ik") == ("Diamond", 1.0)


def test_the_field_declares_its_row_source():
    assert Toy.control_shape_overrides.rows_from == "control_names"
    kinds = {c.name: c.kind for c in Toy.control_shape_overrides.columns}
    assert kinds == {"control": "choice", "shape": "shape", "size": "float"}


def test_defaults_follow_settings_when_a_module_overrides_them():
    class Chain(Module):
        module_type = "chain"

        @classmethod
        def control_names(cls, settings=None):
            count = int((settings or {}).get("segments", 2))
            return tuple(f"fk{index}" for index in range(count))

        @classmethod
        def control_shape_defaults(cls, settings=None):
            return {role: "Circle" for role in cls.control_names(settings)}

    assert Chain.control_shape_defaults({"segments": 3}) == {
        "fk0": "Circle",
        "fk1": "Circle",
        "fk2": "Circle",
    }


def test_limb_control_shapes_mirrors_limb_control_names():
    from tik.trigger.systems.limb import limb_control_names, limb_control_shapes

    labels = ("upperarm", "lowerarm", "hand")
    assert tuple(limb_control_shapes(labels=labels)) == limb_control_names(
        labels=labels
    )
    assert all(shapes.has_shape(name) for name in limb_control_shapes(labels=labels).values())
```

Add to `tests/unit/test_core_trigger.py`:

```python
def test_a_stale_control_shape_row_warns_but_does_not_invalidate():
    """Lowering a count leaves a row naming a control that is no longer built.

    Kept, not dropped: raising the count restores the setup intact -- the same
    rule anim_spaces and pivot_presets already follow.
    """
    from tik.trigger.core.module import Module

    class Chain(Module):
        module_type = "shapechain"

        @classmethod
        def control_names(cls, settings=None):
            count = int((settings or {}).get("segments", 1))
            return tuple(f"fk{index}" for index in range(count))

    chain = Chain()
    chain.control_shape_overrides = [{"control": "fk7", "shape": "Cube"}]
    warnings = chain.warnings()
    assert any("fk7" in text and "not built" in text for text in warnings)
    assert chain.validate() == []
    # The row survives, so raising the count restores it.
    assert chain.control_shape_overrides[0]["control"] == "fk7"


def test_an_unresolvable_shape_name_warns_but_does_not_invalidate():
    from tik.trigger.core.module import Module

    class Toy(Module):
        module_type = "shapetoy"
        controls = ("root",)

    toy = Toy()
    toy.control_shape_overrides = [{"control": "root", "shape": "NotAShape"}]
    assert any("NotAShape" in text for text in toy.warnings())
    assert toy.validate() == []
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
PYTHONPATH="$PWD/src/python" mayapy -m pytest tests/unit/test_shape_resolution_trigger.py -q
```
Expected: FAIL — `AttributeError: type object 'Toy' has no attribute 'control_shape_overrides'`.

- [ ] **Step 3: Implement the module side**

In `src/python/tik/trigger/core/module.py`, add the group beside `SPACES` and `PIVOTS`:

```python
SHAPES = FieldGroup("Shapes", collapsed=True)
"""Every module's control shapes fold away; declared here, not per module."""
```

Import the pinned library at the top (`tik.trigger.core.shapes` is pure, so this respects the layering):

```python
from . import shapes as shape_library
```

Add the declaration beside `controls` / `pivot_controls`:

```python
    #: Default shape per controller role, keyed by the names ``control_names``
    #: returns. The manifest is the only place a default lives -- which is why
    #: ``rig.controller`` has no ``shape`` argument to hide a second one in.
    control_shapes: dict[str, str] = {}
```

Add the classmethod beside `control_names`:

```python
    @classmethod
    def control_shape_defaults(cls, settings: Optional[dict] = None) -> dict[str, str]:
        """Default shape per control role.

        Override when a setting drives them -- exactly as ``control_names``
        and ``output_names`` are overridden.
        """
        return dict(cls.control_shapes)
```

Add the field beside `pivot_presets`:

```python
    control_shape_overrides = TableField(
        [],
        label="Control Shapes",
        group=SHAPES,
        help="Override the shape and relative size of one controller.",
        last=True,
        rows_from="control_names",
        columns=(
            Column("control", "choice", choices_from="control_names"),
            Column("shape", "shape"),
            Column("size", "float"),
        ),
    )
```

Add the resolution helper and the row lookup:

```python
    def shape_rows(self) -> dict[str, dict]:
        """The override rows, keyed by control role. Later rows win."""
        found = {}
        for row in self.control_shape_overrides:
            control = row.get("control", "")
            if control:
                found[control] = row
        return found

    def resolve_control_shape(self, role: str) -> tuple[str, float]:
        """The effective ``(shape, size multiplier)`` for one control role.

        Resolution is *per field*, not per row: a row that sets only a size
        keeps the manifest shape, and a row that sets only a shape keeps a
        multiplier of 1.0. An override naming a shape the library cannot
        resolve is discarded in favour of the manifest default -- the rigger
        gets a warning, not a broken build.
        """
        default = self.control_shape_defaults(self.values()).get(
            role, shape_library.DEFAULT_SHAPE
        )
        row = self.shape_rows().get(role, {})
        shape = row.get("shape", "")
        if not shape or not shape_library.has_shape(shape):
            shape = default
        size = row.get("size", "")
        return shape, float(size) if size != "" else 1.0
```

Extend `warnings()` — append before `return problems`:

```python
        known = type(self).control_names(self.values())
        for row in self.control_shape_overrides:
            control, shape = row.get("control", ""), row.get("shape", "")
            if not control:
                continue
            if control not in known:
                problems.append(
                    f"control shape '{control}': control is not built with the "
                    f"current settings"
                )
            elif shape and not shape_library.has_shape(shape):
                problems.append(
                    f"control shape '{control}': shape '{shape}' is not in the "
                    f"shape library"
                )
```

- [ ] **Step 4: Implement `limb_control_shapes`**

In `src/python/tik/trigger/systems/limb.py`, directly after `limb_control_names`:

```python
def limb_control_shapes(
    name: str = "", labels: Sequence[str] = ()
) -> dict[str, str]:
    """The default shape per role ``build_ikfk_limb`` creates.

    The mirror of ``limb_control_names``, and for the same reason: a module
    that hardcoded the names this system chose would drift the moment a role
    was renamed.
    """
    return {
        _role(name, "ik"): "Cube",
        **{_role(name, "fk", label): "Circle" for label in labels},
        _role(name, "pole"): "Diamond",
    }
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
PYTHONPATH="$PWD/src/python" mayapy -m pytest tests/unit/test_shape_resolution_trigger.py tests/unit/test_core_trigger.py tests/unit/test_import_boundaries.py -q
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/core/module.py src/python/tik/trigger/systems/limb.py tests/unit/test_shape_resolution_trigger.py tests/unit/test_core_trigger.py
git commit -m "feat(trigger): declare control shapes in the module manifest

A module declares its default shape per control role beside controls and
pivot_controls, and the rigger overrides it through a sparse table that
stores only what actually changed -- so an improved module default still
propagates, and reverting is deleting a row.

Resolution is per field: a row setting only a size keeps the manifest
shape. A stale row is kept and warned about rather than dropped, for the
reason anim_spaces already documents -- raising the count restores it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016Pestf7onXtLxZJuC31yyF"
```

---

## Task 5: Resolve in `rig.controller` and migrate every module

The wide edit, done in one task so the manifests and the ground-rules test land together. Until the manifests exist, controls would silently fall back to `"Circle"` — which is why this is not split.

**Files:**
- Modify: `src/python/tik/trigger/maya/rig.py` (`controller()`, around line 262)
- Modify: `src/python/tik/trigger/systems/limb.py` (lines ~198, ~226, ~370)
- Modify: `src/python/tik/trigger/modules/base/base.py`, `fkchain/fkchain.py`, `ribbon/ribbon.py`, `arm/arm.py`
- Test: `tests/integration/trigger/test_module_ground_rules.py`

**Interfaces:**
- Consumes: `Module.resolve_control_shape(role)` and `Module.control_shape_defaults` (Task 4); `tik.trigger.core.shapes.has_shape` (Task 3).
- Produces: `ModuleRig.controller(name, *, size=1.0, parent=None, color=None, match=None, mirror="world", offset=True, tier="primary")` — **no `shape` parameter**. `tweak_control` keeps its own `shape="Circle"`.

- [ ] **Step 1: Write the failing test**

Add to `tests/integration/trigger/test_module_ground_rules.py`:

```python
@pytest.mark.parametrize("module_type", _shipped_module_types())
def test_every_declared_control_has_a_resolvable_default_shape(module_type):
    """Rule: the manifest names a shape the pinned library can resolve.

    A default that does not resolve means every rig using that module silently
    falls back to a circle, which is exactly the bug this manifest exists to
    prevent.
    """
    from tik.trigger.core import shapes

    module_cls = get_module(module_type)
    for settings in CONTROL_VARIATIONS.get(module_type, [{}]):
        module = module_cls(name=module_type)
        module.apply(settings, strict=False)
        defaults = module_cls.control_shape_defaults(module.values())
        for role in module_cls.control_names(module.values()):
            assert role in defaults, f"{module_type}: '{role}' declares no shape"
            assert shapes.has_shape(
                defaults[role]
            ), f"{module_type}: '{role}' names '{defaults[role]}', not in the library"


def test_no_module_or_system_passes_a_shape_to_rig_controller():
    """Rule: the manifest is the only place a default lives.

    ``rig.controller`` has no ``shape`` argument; this catches a call that
    tries to reintroduce one before it silently becomes a second source.
    """
    import inspect

    from tik.trigger.maya.rig import ModuleRig

    assert "shape" not in inspect.signature(ModuleRig.controller).parameters

    root = Path(__file__).resolve().parents[3] / "src" / "python" / "tik" / "trigger"
    offenders = []
    for folder in ("modules", "systems"):
        for py_file in (root / folder).rglob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            for node in ast.walk(ast.parse(source)):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not (
                    isinstance(func, ast.Attribute) and func.attr == "controller"
                ):
                    continue
                if any(kw.arg == "shape" for kw in node.keywords):
                    offenders.append(f"{py_file.name}:{node.lineno}")
    assert offenders == [], f"rig.controller(shape=) at {offenders}"
```

Add `import ast` and `from pathlib import Path` to that file's imports if absent.

- [ ] **Step 2: Run the test to verify it fails**

```bash
PYTHONPATH="$PWD/src/python" MAYA_PLUG_IN_PATH="$PWD/src/plugins/python" \
  mayapy -m pytest tests/integration/trigger/test_module_ground_rules.py -q \
  -k "default_shape or passes_a_shape"
```
Expected: FAIL — `'collar' declares no shape`, and `rig.controller(shape=) at ['arm.py:196', 'base.py:31', ...]`.

- [ ] **Step 3: Drop the parameter and resolve instead**

In `src/python/tik/trigger/maya/rig.py`, change `controller()`:

```python
    def controller(
        self,
        name: str,
        *,
        size: float = 1.0,
        parent: Any = None,
        color: Any = None,
        match: Any = None,
        mirror: str = "world",
        offset: bool = True,
        tier: Optional[str] = "primary",
    ) -> Controller:
        """A tagged controller with its offset group.

        The shape is *not* an argument: it comes from the module's manifest,
        which the rigger overrides per instance. Passing one here would keep a
        second place a default could hide, and the ground rules already require
        the manifest to equal what ``build()`` creates.

        ``match`` snaps it to a node; ``mirror`` is ``"behaviour"`` (FK-like,
        follows its joint) or ``"world"`` (IK/world-aligned), recorded for a
        pose-mirror tool. ``offset=False`` skips the offset group, for a
        controller that hangs under another one (a tweak). ``tier`` places the
        control in the rig's visibilities enum (one of ``TIERS``); ``None``
        leaves it untiered, which is what a tweak wants.
        """
        if tier is not None and tier not in TIERS:
            raise GuideError(
                f"'{name}': tier must be one of {TIERS} or None, got {tier!r}."
            )
        parent = parent if parent is not None else self.groups.control
        shape, size_multiplier = self.module.resolve_control_shape(name)
        controller = Controller.create(
            name=self.name(name, suffix="ctrl"),
            shape=shape,
            size=size * size_multiplier,
            color=color if color is not None else SIDE_COLORS[self.side.value],
            parent=(
                node_of(parent).long_name
                if hasattr(node_of(parent), "long_name")
                else parent
            ),
        )
```

The rest of the method is unchanged.

**Note:** `Controller.create` resolves the name through `ControlShapeLibrary.get_instance()`, which searches the user path. Pass the resolved curve *data* instead so the build stays pinned — replace the `shape=shape` argument with:

```python
        from tik.trigger.core import shapes as shape_library

        curve_data = shape_library.library().load(shape)
```

and pass `shape=curve_data if curve_data else shape`. Put the import at the top of `rig.py` rather than inline.

In `tweak_control`, leave `shape: str = "Circle"` and its `self.controller(...)` call — but that call must no longer pass `shape=`. Change it to set the tweak's shape after creation:

```python
        tweak = self.controller(
            f"{role}_tweak",
            size=size if size is not None else 1.0,
            parent=main,
            match=main,
            mirror=main.meta.get(tags.MIRROR, tags.WORLD),
            offset=False,
            tier=None,
        )
        tweak.set_shape(shape, size=size if size is not None else 1.0)
```

- [ ] **Step 4: Migrate the systems and modules**

`src/python/tik/trigger/systems/limb.py` — delete `shape="Cube"` (line ~198), `shape="Circle"` (line ~226) and `shape="Diamond"` (line ~370) from the three `rig.controller(...)` calls. Their defaults now live in `limb_control_shapes` (Task 4).

`src/python/tik/trigger/modules/base/base.py` — add the manifest, drop the argument:

```python
    controls = ("root",)
    control_shapes = {"root": "Circle"}
```
```python
        controller = rig.controller(
            "root",
            size=self.controller_size,
            match=root_guide,
            mirror="world",
        )
```

`src/python/tik/trigger/modules/fkchain/fkchain.py` — the count drives the roles, so override the classmethod beside `control_names`:

```python
    @classmethod
    def control_shape_defaults(cls, settings=None):
        """One circle per FK controller."""
        return {role: "Circle" for role in cls.control_names(settings)}
```
The `rig.controller(f"fk{index}", ...)` call already passes no `shape=`; leave it.

`src/python/tik/trigger/modules/ribbon/ribbon.py` — same shape:

```python
    @classmethod
    def control_shape_defaults(cls, settings=None):
        """A circle for every control the settings ask for."""
        return {role: "Circle" for role in cls.control_names(settings)}
```
Delete `shape="Circle"` from both `rig.controller(...)` calls (in `end_control` and the mid loop).

`src/python/tik/trigger/modules/arm/arm.py` — import the helper and declare:

```python
from tik.trigger.systems.limb import (
    _derive_size,
    build_ikfk_limb,
    limb_control_names,
    limb_control_shapes,
)
```
```python
    controls = ("collar", *limb_control_names(labels=LIMB_LABELS))
    control_shapes = {
        "collar": "CurvedCircle",
        **limb_control_shapes(labels=LIMB_LABELS),
    }
```
Delete `shape="CurvedCircle"` from the collar's `rig.controller(...)` call (line ~196).

- [ ] **Step 5: Run the tests to verify they pass**

```bash
PYTHONPATH="$PWD/src/python" MAYA_PLUG_IN_PATH="$PWD/src/plugins/python" \
  mayapy -m pytest tests/integration/trigger/test_module_ground_rules.py -q
```
Expected: PASS.

Then the wider Maya suites, since this touches every build:

```bash
make tests-unit && make tests-integration
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger tests/integration/trigger/test_module_ground_rules.py
git commit -m "feat(trigger): resolve controller shapes from the manifest

rig.controller loses its shape parameter entirely -- not merely its call
sites. Keeping it would preserve a second place a default could hide,
and the ground rules already require the manifest to equal what build()
creates; removing it makes that true by construction.

The build loads curve data through the pinned library rather than
letting Controller.create resolve a name through the user path.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016Pestf7onXtLxZJuC31yyF"
```

---

## Task 6: The shared shape picker widget

**Files:**
- Create: `src/python/tik/shared/ui/shape_picker.py`
- Test: `tests/ui/test_shape_picker.py`

**Interfaces:**
- Consumes: `tik.core.control_shapes.ControlShapeLibrary` (Task 1); `tik.shared.ui.tile_grid.TileGrid`, `TileEntry`; `tik.shared.ui.filter_bar.FilterBar`.
- Produces:
  - `ShapePicker(library=None, parent=None)` — `shapeChosen = Signal(str)`, `names() -> tuple[str, ...]`, `visible_names() -> tuple[str, ...]`, `set_filter(text)`, `choose(name)`, `grid`, `filter_bar`
  - `ShapeButton(library=None, parent=None)` — `shapeChosen = Signal(str)`, `value() -> str`, `setValue(name)`, `setPlaceholder(name)`, `open_picker()`
  - `thumbnail_for(library, name) -> QIcon | None`

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_shape_picker.py`:

```python
"""The shape picker, offscreen. No Maya: it reads the pure core library."""

from __future__ import annotations

import pytest

from tik.shared.ui.shape_picker import ShapeButton, ShapePicker


def test_picker_lists_shipped_shapes(qapp):
    picker = ShapePicker()
    names = picker.names()
    assert "Circle" in names
    assert "Cube" in names
    assert "FkikSwitch" in names


def test_picker_never_imports_maya():
    import ast
    from pathlib import Path

    import tik.shared.ui.shape_picker as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module)
    assert not [
        name
        for name in imported
        if name == "maya" or name.startswith(("maya.", "tik.maya"))
    ]


def test_filtering_narrows_the_list(qapp):
    picker = ShapePicker()
    picker.set_filter("cub")
    assert "Cube" in picker.visible_names()
    assert "Circle" not in picker.visible_names()
    picker.set_filter("")
    assert "Circle" in picker.visible_names()


def test_choosing_emits_the_name(qapp):
    picker = ShapePicker()
    seen = []
    picker.shapeChosen.connect(seen.append)
    picker.choose("Diamond")
    assert seen == ["Diamond"]


def test_button_round_trips_a_value(qapp):
    button = ShapeButton()
    button.setValue("Cube")
    assert button.value() == "Cube"
    button.setValue("")
    assert button.value() == ""


def test_button_emits_when_the_picker_chooses(qapp):
    button = ShapeButton()
    seen = []
    button.shapeChosen.connect(seen.append)
    button.picker.choose("Star")
    assert seen == ["Star"]
    assert button.value() == "Star"


def test_button_shows_a_placeholder_when_unset(qapp):
    """An unset row draws the module default, greyed."""
    button = ShapeButton()
    button.setPlaceholder("CurvedCircle")
    assert button.value() == ""
    assert "CurvedCircle" in button.toolTip()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH="$PWD/src/python" \
  mayapy -m pytest tests/ui/test_shape_picker.py -q
```
Expected: FAIL — `ModuleNotFoundError: No module named 'tik.shared.ui.shape_picker'`.

- [ ] **Step 3: Implement**

Create `src/python/tik/shared/ui/shape_picker.py`:

```python
"""Choosing a control shape by looking at it.

Reads :mod:`tik.core.control_shapes` and never ``tik.maya`` -- importing
anything under ``tik.maya`` requires a live Maya, and this widget has to run
headless. Thumbnails are the ``.png`` sibling each shape ships beside its JSON.
"""

from __future__ import annotations

from typing import Optional

from tik.core.control_shapes import ControlShapeLibrary
from tik.shared.ui import theme
from tik.shared.ui.filter_bar import FilterBar
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.shared.ui.tile_grid import TileEntry, TileGrid


def thumbnail_for(library, name: str) -> Optional[QtGui.QIcon]:
    """The shape's ``.png`` sibling as an icon, or ``None`` when absent."""
    path = library.get_path(name)
    if not path:
        return None
    thumb = path.with_suffix(".png")
    if not thumb.exists():
        return None
    pixmap = QtGui.QPixmap(str(thumb))
    return QtGui.QIcon(pixmap) if not pixmap.isNull() else None


class ShapePicker(QtWidgets.QWidget):
    """A filterable grid of every shape the library resolves, by category."""

    shapeChosen = QtCore.Signal(str)  # noqa: N815 - matches the Qt widgets here

    def __init__(self, library=None, parent=None) -> None:
        super().__init__(parent)
        self.library = library or ControlShapeLibrary()
        self._filter = ""

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.filter_bar = FilterBar(placeholder="Filter shapes…")
        self.filter_bar.filter_changed.connect(self._render)
        layout.addWidget(self.filter_bar)

        self._holder = QtWidgets.QVBoxLayout()
        self._holder.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._holder, 1)

        self._entries = [
            TileEntry(
                key=name,
                label=name,
                category=(info.get("category") or "uncategorised"),
                tooltip=name,
            )
            for name, info in sorted(self.library.get_shape_data().items())
        ]
        self.grid = None
        self._render()

    # ------------------------------------------------------------- reading
    def names(self) -> tuple:
        """Every shape name the library offers, sorted."""
        return tuple(entry.key for entry in self._entries)

    def visible_names(self) -> tuple:
        """The names the current filter leaves showing."""
        model = self.filter_bar.model
        return tuple(
            entry.key
            for entry in self._entries
            if not model.is_active or model.matches(entry.key)
        )

    # ------------------------------------------------------------- writing
    def set_filter(self, text: str) -> None:
        """Narrow the grid to names matching ``text``.

        Drives the bar's own model rather than a private string, so typing and
        calling this land in the same place.
        """
        self.filter_bar.model.set_pending_text(text or "")

    def choose(self, name: str) -> None:
        """Announce ``name`` as the chosen shape."""
        self.shapeChosen.emit(name)

    def _render(self) -> None:
        """Rebuild the grid for the current filter.

        ``TileGrid`` takes its entries at construction and has no setter, so a
        filter change replaces the widget. 86 tiles rebuild imperceptibly, and
        reaching into its private ``_build`` to avoid that would be worse.
        """
        visible = set(self.visible_names())
        if self.grid is not None:
            self._holder.removeWidget(self.grid)
            self.grid.deleteLater()
        self.grid = TileGrid(
            [entry for entry in self._entries if entry.key in visible],
            "application/x-tik-shape",
            colors={},  # every category falls back to the neutral tint
            icon_provider=lambda key: thumbnail_for(self.library, key),
        )
        self.grid.activated.connect(self.choose)
        self._holder.addWidget(self.grid)


class ShapeButton(QtWidgets.QToolButton):
    """A thumbnail that opens a :class:`ShapePicker` popup.

    An empty value is not a missing one: it means *inherit*, and the button
    draws the placeholder the caller supplies -- the module's own default --
    so an unedited row still shows what the control looks like.
    """

    shapeChosen = QtCore.Signal(str)  # noqa: N815 - matches the Qt widgets here

    SIZE = 48

    def __init__(self, library=None, parent=None) -> None:
        super().__init__(parent)
        self.library = library or ControlShapeLibrary()
        self._value = ""
        self._placeholder = ""
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setIconSize(QtCore.QSize(self.SIZE - 8, self.SIZE - 8))
        self.setAutoRaise(True)
        self.clicked.connect(self.open_picker)

        self.picker = ShapePicker(self.library)
        self.picker.setWindowFlags(QtCore.Qt.Popup)
        self.picker.resize(420, 460)
        self.picker.shapeChosen.connect(self._on_chosen)

    # ------------------------------------------------------------- value
    def value(self) -> str:
        """The chosen shape, or ``""`` when the row inherits its default."""
        return self._value

    def setValue(self, name: str) -> None:  # noqa: N802 - matches the Qt widgets here
        """Set the chosen shape without emitting."""
        self._value = name or ""
        self._refresh()

    def setPlaceholder(  # noqa: N802 - matches the Qt widgets here
        self, name: str
    ) -> None:
        """The inherited default drawn when nothing is chosen."""
        self._placeholder = name or ""
        self._refresh()

    def open_picker(self) -> None:
        """Show the picker under the button."""
        self.picker.move(self.mapToGlobal(QtCore.QPoint(0, self.height())))
        self.picker.show()

    def _on_chosen(self, name: str) -> None:
        self.picker.hide()
        self.setValue(name)
        self.shapeChosen.emit(name)

    def _refresh(self) -> None:
        shown = self._value or self._placeholder
        icon = thumbnail_for(self.library, shown) if shown else None
        self.setIcon(icon or QtGui.QIcon())
        if not icon:
            self.setText(shown[:2] if shown else "-")
        else:
            self.setText("")
        if self._value:
            self.setToolTip(self._value)
        elif self._placeholder:
            self.setToolTip(f"{self._placeholder} (module default)")
        else:
            self.setToolTip("No shape")
        # An inherited value reads as inherited.
        self.setStyleSheet(
            "" if self._value else f"QToolButton {{ color: {theme.TEXT_DIM}; }}"
        )
```

**APIs this leans on, already verified against the repo — use them exactly:**
- `TileGrid(entries, mime_type, parent=None, colors=None, columns_hint=2, icon_provider=None)` — entries are **positional and fixed at construction**; there is no setter, which is why `_render` replaces the widget. Its click signal is `activated = Signal(str)`.
- `TileEntry(key, label, category="", tooltip="")`.
- `FilterBar(parent=None, placeholder="…")` — its signal is `filter_changed` (**no arguments**); the matching lives on `bar.model`, a `FilterModel` with `set_pending_text(text)`, `is_active`, `matches(text) -> bool` and `keywords`.
- `tik.shared.ui.theme` exposes `TEXT_DIM = "#8f8f8f"`; there is no `MUTED`. `theme.CATEGORY` has no shape categories in it, so `colors={}` is passed and every tile falls back to `theme.CATEGORY["utility"]`.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH="$PWD/src/python" \
  mayapy -m pytest tests/ui/test_shape_picker.py -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/shared/ui/shape_picker.py tests/ui/test_shape_picker.py
git commit -m "feat(ui): add the shared shape picker

A filterable thumbnail grid over the shape library, and the button that
opens it. Reads tik.core.control_shapes and never tik.maya, so it runs
headless -- which is what forced the library down to core in the first
place. An empty value means inherit, and the button draws the module's
default greyed rather than nothing.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016Pestf7onXtLxZJuC31yyF"
```

---

## Task 7: The per-control fold in FormBuilder

**Files:**
- Modify: `src/python/tik/shared/ui/fields.py`
- Test: `tests/ui/test_shape_fold.py`

**Interfaces:**
- Consumes: `ShapeButton` (Task 6); `TableField.rows_from` (Task 2); `FormBuilder._resolve_choices`.
- Produces: `_ControlShapeEditor(columns, rows_resolver, defaults_resolver=None, parent=None)` with `valueChanged = Signal(object)`, `value() -> list[dict]`, `setValue(rows)`, `row_widgets(role) -> tuple[ShapeButton, QDoubleSpinBox]`. `FormBuilder` builds it for a `table` field whose `rows_from` is set.

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_shape_fold.py`:

```python
"""The per-control shape fold: every control listed, sparse storage beneath."""

from __future__ import annotations

import pytest

from tik.core.fields import Column, Schema, TableField
from tik.shared.ui.fields import FormBuilder


class Toy(Schema):
    rows = TableField(
        [],
        label="Control Shapes",
        rows_from="control_names",
        columns=(
            Column("control", "choice", choices_from="control_names"),
            Column("shape", "shape"),
            Column("size", "float"),
        ),
    )

    control_names = ("ik", "fk", "pole")
    control_shape_defaults = {"ik": "Cube", "fk": "Circle"}


@pytest.fixture
def form(qapp):
    builder = FormBuilder(Toy)
    builder.set_target(Toy())
    return builder


def test_one_row_per_control(form):
    editor = form.widget("rows")
    assert editor.roles() == ("ik", "fk", "pole")


def test_unset_rows_show_the_module_default_as_a_placeholder(form):
    button, _spin = form.widget("rows").row_widgets("ik")
    assert button.value() == ""
    assert "Cube" in button.toolTip()


def test_editing_writes_a_sparse_row(form):
    editor = form.widget("rows")
    button, _spin = editor.row_widgets("ik")
    button.picker.choose("Diamond")
    assert editor.value() == [{"control": "ik", "shape": "Diamond", "size": ""}]


def test_the_size_spinner_writes_its_own_field(form):
    editor = form.widget("rows")
    _button, spin = editor.row_widgets("fk")
    spin.setValue(2.5)
    assert editor.value() == [{"control": "fk", "shape": "", "size": 2.5}]


def test_clearing_removes_the_row(form):
    editor = form.widget("rows")
    button, spin = editor.row_widgets("ik")
    button.picker.choose("Diamond")
    assert editor.value()
    button.setValue("")
    spin.setValue(1.0)
    editor.refresh_value()
    assert editor.value() == []


def test_setValue_populates_the_matching_rows(form):
    editor = form.widget("rows")
    editor.setValue([{"control": "pole", "shape": "Star", "size": 0.5}])
    button, spin = editor.row_widgets("pole")
    assert button.value() == "Star"
    assert spin.value() == pytest.approx(0.5)
    # The others stay inherited.
    assert editor.row_widgets("ik")[0].value() == ""


def test_a_plain_table_still_gets_the_add_remove_editor(qapp):
    """rows_from is the opt-in; without it nothing changes."""
    from tik.shared.ui.fields import _TableEditor

    class Plain(Schema):
        rows = TableField([], columns=(Column("label"),))

    builder = FormBuilder(Plain)
    builder.set_target(Plain())
    assert isinstance(builder.widget("rows"), _TableEditor)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH="$PWD/src/python" \
  mayapy -m pytest tests/ui/test_shape_fold.py -q
```
Expected: FAIL — the widget is a `_TableEditor` with no `roles()`.

- [ ] **Step 3: Implement the editor**

Add to `src/python/tik/shared/ui/fields.py`, after `_TableEditor`:

```python
class _ControlShapeEditor(QtWidgets.QWidget):
    """One row per control, over sparse storage.

    A ``TableField`` naming ``rows_from`` has a row set fixed by the target
    rather than added by hand, so the rigger sees every control at once --
    including the ones they have never touched, drawn with the module's own
    default. Only the rows they actually changed are stored.
    """

    valueChanged = QtCore.Signal(object)  # noqa: N815 - matches the Qt widgets here

    def __init__(
        self, columns, rows_resolver, defaults_resolver=None, parent=None
    ) -> None:
        super().__init__(parent)
        self.columns = list(columns)
        self._rows_resolver = rows_resolver
        self._defaults_resolver = defaults_resolver or (lambda: {})
        self._rows: dict[str, tuple] = {}

        self._layout = QtWidgets.QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setHorizontalSpacing(6)
        self._layout.setVerticalSpacing(2)
        self._build_rows()

    # -------------------------------------------------------------- rows
    def roles(self) -> tuple:
        """The control roles the target currently offers, in its own order."""
        return tuple(self._rows)

    def row_widgets(self, role: str) -> tuple:
        """``(ShapeButton, QDoubleSpinBox)`` for ``role``."""
        return self._rows[role]

    def _build_rows(self) -> None:
        from tik.shared.ui.shape_picker import ShapeButton

        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rows = {}

        defaults = self._defaults_resolver()
        for index, role in enumerate(self._rows_resolver()):
            label = QtWidgets.QLabel(role.replace("_", " "))
            button = ShapeButton()
            button.setPlaceholder(defaults.get(role, ""))
            button.shapeChosen.connect(self.refresh_value)
            spin = QtWidgets.QDoubleSpinBox()
            spin.setDecimals(3)
            spin.setRange(0.001, 1000.0)
            spin.setValue(1.0)
            spin.valueChanged.connect(self.refresh_value)
            self._layout.addWidget(label, index, 0)
            self._layout.addWidget(button, index, 1)
            self._layout.addWidget(spin, index, 2)
            self._rows[role] = (button, spin)

    def rebuild(self) -> None:
        """Re-read the role list, keeping whatever is already stored."""
        stored = self.value()
        self._build_rows()
        self.setValue(stored)

    # ------------------------------------------------------------- value
    def value(self) -> list:
        """Only the rows that differ from the module's defaults."""
        rows = []
        for role, (button, spin) in self._rows.items():
            shape = button.value()
            size = spin.value()
            if not shape and abs(size - 1.0) < 1e-9:
                continue  # inherited: store nothing
            rows.append(
                {
                    "control": role,
                    "shape": shape,
                    "size": "" if abs(size - 1.0) < 1e-9 else size,
                }
            )
        return rows

    def setValue(self, rows) -> None:  # noqa: N802 - matches the Qt widgets here
        stored = {
            row.get("control", ""): row for row in (rows or []) if row.get("control")
        }
        for role, (button, spin) in self._rows.items():
            row = stored.get(role, {})
            for widget in (button, spin):
                widget.blockSignals(True)
            button.setValue(row.get("shape", "") or "")
            size = row.get("size", "")
            spin.setValue(float(size) if size != "" else 1.0)
            for widget in (button, spin):
                widget.blockSignals(False)

    def refresh_value(self, *_args) -> None:
        """Recompute and announce the sparse value."""
        self.valueChanged.emit(self.value())
```

- [ ] **Step 4: Dispatch to it in FormBuilder**

In `_make_widget`, replace the `elif kind == "table":` branch with:

```python
        elif kind == "table" and getattr(field, "rows_from", ""):
            source = field.rows_from
            widget = _ControlShapeEditor(
                getattr(field, "columns", ()),
                rows_resolver=lambda key=source: self._resolve_choices(key),
                defaults_resolver=self._resolve_shape_defaults,
            )
            widget.valueChanged.connect(
                lambda value, field_name=name: self._on_change(field_name, value)
            )
        elif kind == "table":
            widget = _TableEditor(
                getattr(field, "columns", ()),
                choices_resolver=self._resolve_choices,
            )
            widget.valueChanged.connect(
                lambda value, field_name=name: self._on_change(field_name, value)
            )
```

And add the defaults resolver beside `_resolve_choices`:

```python
    def _resolve_shape_defaults(self) -> dict:
        """The target's manifest shape defaults, for the greyed placeholders.

        Same shape as ``_resolve_choices``: a field is a class attribute and
        cannot know the subclass it will be edited on, so it resolves at render
        time.
        """
        if self._target is None:
            return {}
        found = getattr(self._target, "control_shape_defaults", {})
        if callable(found):
            found = found(self._target.values())
        return dict(found or {})
```

Finally, make the editor rebuild when the target's role set changes. In whichever method re-syncs widgets to the target (the one that calls `setValue` on each widget after `set_target`), call `widget.rebuild()` first for a `_ControlShapeEditor`:

```python
            if isinstance(widget, _ControlShapeEditor):
                widget.rebuild()
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH="$PWD/src/python" \
  mayapy -m pytest tests/ui/test_shape_fold.py -q && make tests-ui
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/shared/ui/fields.py tests/ui/test_shape_fold.py
git commit -m "feat(ui): render a rows_from table as a per-control fold

One row per control, each a thumbnail button and a size spinner, with the
module's default drawn greyed on rows the rigger has not touched -- so
the whole instance's appearance is visible without adding anything.
Storage stays sparse: a row that matches its default is not written, and
clearing one deletes it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016Pestf7onXtLxZJuC31yyF"
```

---

## Task 8: Rebuild polish on the shared picker

**Files:**
- Rewrite: `src/python/tik/tools/polish/ui/mcv/controller_shapes_mcv.py`
- Modify: `src/python/tik/tools/polish/core.py`

**Interfaces:**
- Consumes: `ShapePicker` (Task 6); `tik.core.control_shapes.ControlShapeLibrary` (Task 1).
- Produces: `ControllerShapesWidget(core=None, parent=None)` with `picker: ShapePicker`.

- [ ] **Step 1: Rewrite the widget**

Replace the whole of `src/python/tik/tools/polish/ui/mcv/controller_shapes_mcv.py`:

```python
"""The polish tool's controller-shape browser.

The library, the thumbnails and the filtering all live in
:class:`tik.shared.ui.shape_picker.ShapePicker`; this is the polish-side shell
around it. Polish keeps the *unpinned* library on purpose -- a cleanup tool
should see the artist's personal shapes. Only a rig build must not.
"""

from __future__ import annotations

from tik.shared.ui.Qt import QtWidgets
from tik.shared.ui.shape_picker import ShapePicker
from tik.tools.polish.core import PolishCore


class ControllerShapesWidget(QtWidgets.QWidget):
    """Browse the shape library and apply a shape to the selection."""

    def __init__(self, core=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Controller Shape Library")
        self.core = core or PolishCore()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.picker = ShapePicker(self.core.library)
        layout.addWidget(self.picker)
```

This deletes the hardcoded `D:/dev/tikworks/src` `sys.path` append, the `sys.modules` purge loop, the direct `PySide6` import, the private stylesheet, and the bespoke `ShapeLibraryModel` / `FlatLeafProxyModel` / `HoverOverlay` stack.

- [ ] **Step 2: Keep polish's library unpinned and explicit**

In `src/python/tik/tools/polish/core.py`, make the intent explicit:

```python
    def __init__(self):
        """Initialize the Polish core with library and custom paths.

        The library keeps its user path: a cleanup tool *should* see the
        artist's own shapes. Only a rig build resolves through the pinned
        library in ``tik.trigger.core.shapes``.
        """
        self.library = control_shapes.ControlShapeLibrary(include_user_path=True)
        for additional_path in settings.get("additional_library_paths", []):
            self.library.add_path(additional_path)
```

- [ ] **Step 3: Verify it imports headless and nothing regressed**

```bash
TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH="$PWD/src/python" \
  mayapy -c "import ast,pathlib; p=pathlib.Path('src/python/tik/tools/polish/ui/mcv/controller_shapes_mcv.py'); ast.parse(p.read_text()); print('parsed ok')"
make tests-ui && make lint
```
Expected: `parsed ok`, then PASS and a clean lint.

`PolishCore()` itself constructs a Maya-free library, but `tik/tools/polish/core.py` imports `tik.maya.utils.control_shapes`, so importing the widget still needs Maya. That is fine — polish is a Maya tool. The *shared* picker is what had to be headless.

- [ ] **Step 4: Commit**

```bash
git add src/python/tik/tools/polish
git commit -m "refactor(polish): rebuild the shape browser on the shared picker

Drops the hardcoded sys.path append, the sys.modules purge loop, the
direct PySide6 import, the private stylesheet and the bespoke model and
proxy stack -- TileGrid and ShapePicker already cover all of it.

Polish keeps the unpinned library on purpose: a cleanup tool should see
the artist's personal shapes; only a rig build must not.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016Pestf7onXtLxZJuC31yyF"
```

---

## Task 9: Documentation and the full run

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run everything**

```bash
make tests-unit && make tests-integration && make tests-ui && make lint
```
Expected: all PASS, lint clean. Fix any failure before continuing.

- [ ] **Step 2: Update the project context**

In `CLAUDE.md`, in the tik.trigger status paragraph, add after the pivot-presets sentence:

> Since the 2026-09-08 shapes pass, **every controller a module builds has a definable shape**. A module declares `control_shapes` (control role -> shape name) in its manifest — the only place a default lives, which is why `rig.controller` has no `shape` argument — and the rigger overrides shape and a size multiplier per control in a sparse `Shapes` table that stores only what changed, edited as a fold listing every control with its thumbnail. The shape library moved down to `tik/core/control_shapes.py` with its 86 shapes, because `tik/maya/__init__.py` needs a live Maya and `tik.maya` may not import `tik.shared`, so a headless picker and `Controller.set_shape` had no shared home above core. The build resolves through a **pinned** library (`tik/trigger/core/shapes.py`) that excludes `~/TikWorks/user_control_shapes`: a per-user folder is a preference, and a preference can never change a rig. `TRIGGER_SHAPES_PATH` adds deployed studio roots.

Add to the design-specs list:

> `2026-09-08-definable-control-shapes-design.md` (definable control shapes: the four things "the library" was bundling, the forced move to `tik.core`, the manifest declaration, the sparse override table and the pinned build library)

Add to the tests list:

> `tests/unit/test_shape_resolution_trigger.py` — the resolution chain and the sparse table; `tests/unit/test_pinned_shapes_trigger.py` — the pinned build library; `tests/ui/test_shape_picker.py`, `tests/ui/test_shape_fold.py` — the picker and the per-control fold

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: record the definable control shapes pass

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016Pestf7onXtLxZJuC31yyF"
```
