# Plan A — tik.maya Rigging Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the generic, Trigger-agnostic rigging building blocks to `tik.maya` (metadata tags, attribute helpers, naming mechanics, Joint/IkHandle, matrix constraints, measure, space switch, ribbon, IK/FK chain) so trigger modules can be thin orchestration.

**Architecture:** Every addition is a `tik.maya` type, role, or construct built on `Node`/`Plug`/`Transform`, with `create(...)` classmethods returning typed wrappers, undo-safe, and no Trigger vocabulary. Constructs expose their produced nodes as properties.

**Tech Stack:** Python 3.10+, Maya 2024+ (`maya.cmds`, `maya.api.OpenMaya`), pytest under `mayapy`.

**Spec:** `docs/superpowers/specs/2026-08-28-trigger-rebuild-design.md`

## Global Constraints

- No third-party deps; stdlib + Maya-bundled only.
- `tik.core` imports no Maya/Qt/tik.maya/tik.trigger. `tik.maya` imports only `tik.core`. Nothing imports `tik.trigger` from below.
- No `get_`/`set_` prefixed public API; properties for state, methods for actions. No single-letter names. Black line length 88.
- All scene-modifying operations undoable (use `cmds` or `undocommit` for API modifiers).
- Tests: `$env:PYTHONPATH="src/python"; & "C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe" -m pytest tests/unit/<file> -q -p no:cacheprovider`
- Commit after each task with the trailer:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_01ND5N8xQURwsbLSRpjfNoY4`

---

## File map

| File | Responsibility |
|---|---|
| `Makefile`, `make.bat`, `tests/integration/invoke.py` | resolve conflict markers |
| `CLAUDE.md` | fix `src/python/tik` paths |
| `tests/unit/test_import_boundaries.py` | layering lint |
| `src/python/tik/maya/core/meta.py` | `MetaStore`, `Node.meta`, `find_by_meta` |
| `src/python/tik/maya/core/attribute.py` | separator, lock/hide, proxy, drive, add_* helpers |
| `src/python/tik/maya/core/naming.py` | `unique_name`, `format_name` |
| `src/python/tik/maya/types/joint.py` | orient helpers, chain helpers |
| `src/python/tik/maya/types/ikhandle.py` | `IkHandle` |
| `src/python/tik/maya/types/transform.py` | `align_to`, `aim_at`, `between` |
| `src/python/tik/maya/constructs/matrix_constraint.py` | `MatrixConstraint` |
| `src/python/tik/maya/constructs/matrix_switch.py` | `MatrixSwitch` |
| `src/python/tik/maya/constructs/measure.py` | `Measure` |
| `src/python/tik/maya/constructs/space_switch.py` | `SpaceSwitch` |
| `src/python/tik/maya/constructs/ribbon.py` | `Ribbon` |
| `src/python/tik/maya/constructs/ikfk_chain.py` | `IkFkChain` |
| `src/python/tik/maya/__init__.py` | export new names |

---

### Task 0: Housekeeping and import-boundary lint

**Files:**
- Modify: `Makefile`, `make.bat`, `tests/integration/invoke.py`, `CLAUDE.md`
- Create: `tests/unit/test_import_boundaries.py`

- [x] **Step 1: Resolve conflict markers** keeping the `HEAD` side (`SRC_DIR := src/python`, cmake/build targets present) in `Makefile` and `make.bat`; in `invoke.py` both sides are identical — keep one.
- [x] **Step 2: Fix CLAUDE.md** — replace `src/tik/` with `src/python/tik/` in the tree and location lines; note `tests/integration/trigger/` and the spec/plan paths.
- [x] **Step 3: Write the boundary test**

```python
"""Layering rules: tik.core < tik.maya < tik.trigger; core/session of trigger are DCC-agnostic."""
import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "python" / "tik"

FORBIDDEN = {
    "core": ("maya", "tik.maya", "tik.trigger", "tik.shared", "PySide2", "PySide6", "tik.vendor.Qt"),
    "maya": ("tik.trigger", "tik.shared", "PySide2", "PySide6", "tik.vendor.Qt"),
    "trigger/core": ("maya", "tik.maya", "PySide2", "PySide6", "tik.vendor.Qt", "tik.shared.ui"),
    "trigger/session": ("maya", "tik.maya", "PySide2", "PySide6", "tik.vendor.Qt", "tik.shared.ui"),
}


def _imports(py_file: Path):
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module


def _violations(package: str, forbidden):
    found = []
    for py_file in (SRC / package).rglob("*.py"):
        for name in _imports(py_file):
            if any(name == bad or name.startswith(bad + ".") for bad in forbidden):
                found.append(f"{py_file.relative_to(SRC)} imports {name}")
    return found


@pytest.mark.parametrize("package,forbidden", FORBIDDEN.items())
def test_no_forbidden_imports(package, forbidden):
    if not (SRC / package).exists():
        pytest.skip(f"{package} not present")
    assert _violations(package, forbidden) == []
```

- [x] **Step 4: Run it** — expect `trigger/core` and `trigger/session` to FAIL (they import `maya.cmds`). That is the known debt Plan B removes; mark those two with `pytest.mark.xfail(strict=True, reason="removed in Plan B")` via a parametrize `marks` for now.
- [x] **Step 5: Run full unit suite**, commit `chore: resolve merge markers, fix docs paths, add import-boundary lint`.

---

### Task 1: `Node.meta` metadata store and `find_by_meta`

**Files:**
- Create: `src/python/tik/maya/core/meta.py`
- Modify: `src/python/tik/maya/core/node.py` (add `meta` property), `src/python/tik/maya/__init__.py`
- Test: `tests/unit/test_meta.py`

**Interfaces — Produces:**
- `node.meta[key] = value` / `node.meta[key]` / `key in node.meta` / `del node.meta[key]` / `node.meta.get(key, default)` / `node.meta.keys()` / `node.meta.items()` / `node.meta.update(mapping)` / `node.meta.clear()`
- Values: `str | int | float | bool | list | dict | None` (JSON-encoded into a string attr named `tikMeta_<key>`; keys must match `[A-Za-z_][A-Za-z0-9_]*`).
- `tik.maya.find_by_meta(key: str, value=_ANY, node_type: str | None = None) -> list[Node]`
- `META_PREFIX = "tikMeta_"`

- [x] **Step 1: Tests**

```python
import pytest
from maya import cmds

import tik.maya as tm
from tik.maya.core.meta import META_PREFIX, find_by_meta


def test_set_get_roundtrip_types():
    node = tm.Transform.create(name="meta_node")
    node.meta["kind"] = "guide"
    node.meta["index"] = 3
    node.meta["ratio"] = 0.5
    node.meta["flag"] = True
    node.meta["items"] = ["a", 1]
    node.meta["settings"] = {"segments": 3, "local": False}
    assert node.meta["kind"] == "guide"
    assert node.meta["index"] == 3 and isinstance(node.meta["index"], int)
    assert node.meta["ratio"] == 0.5
    assert node.meta["flag"] is True
    assert node.meta["items"] == ["a", 1]
    assert node.meta["settings"] == {"segments": 3, "local": False}


def test_attr_name_uses_prefix_and_is_hidden_string():
    node = tm.Transform.create(name="meta_node")
    node.meta["kind"] = "guide"
    assert cmds.attributeQuery(f"{META_PREFIX}kind", node=node.name, exists=True)
    assert cmds.getAttr(f"{node.name}.{META_PREFIX}kind", type=True) == "string"
    assert not cmds.getAttr(f"{node.name}.{META_PREFIX}kind", keyable=True)


def test_contains_get_del_keys():
    node = tm.Transform.create(name="meta_node")
    assert "kind" not in node.meta
    assert node.meta.get("kind", "none") == "none"
    node.meta["kind"] = "guide"
    node.meta["role"] = "root"
    assert "kind" in node.meta
    assert sorted(node.meta.keys()) == ["kind", "role"]
    del node.meta["kind"]
    assert "kind" not in node.meta
    with pytest.raises(KeyError):
        node.meta["kind"]


def test_overwrite_and_none():
    node = tm.Transform.create(name="meta_node")
    node.meta["kind"] = "guide"
    node.meta["kind"] = "rig"
    assert node.meta["kind"] == "rig"
    node.meta["empty"] = None
    assert node.meta["empty"] is None


def test_invalid_key_rejected():
    node = tm.Transform.create(name="meta_node")
    with pytest.raises(ValueError):
        node.meta["bad key"] = 1


def test_update_and_clear():
    node = tm.Transform.create(name="meta_node")
    node.meta.update({"a": 1, "b": 2})
    assert node.meta["b"] == 2
    node.meta.clear()
    assert node.meta.keys() == []


def test_survives_rename():
    node = tm.Transform.create(name="meta_node")
    node.meta["kind"] = "guide"
    node.rename("renamed_node")
    assert node.meta["kind"] == "guide"


def test_find_by_meta():
    first = tm.Transform.create(name="first")
    second = tm.Joint.create(name="second")
    third = tm.Transform.create(name="third")
    first.meta["kind"] = "guide"
    second.meta["kind"] = "guide"
    third.meta["kind"] = "rig"
    names = sorted(node.name for node in find_by_meta("kind", "guide"))
    assert names == ["first", "second"]
    assert [node.name for node in find_by_meta("kind", "guide", node_type="joint")] == ["second"]
    assert len(find_by_meta("kind")) == 3
    assert find_by_meta("missing") == []


def test_undoable():
    node = tm.Transform.create(name="meta_node")
    cmds.undoInfo(openChunk=True)
    node.meta["kind"] = "guide"
    cmds.undoInfo(closeChunk=True)
    cmds.undo()
    assert "kind" not in node.meta
```

- [x] **Step 2: Run, expect AttributeError on `.meta`.**
- [x] **Step 3: Implement `meta.py`**

```python
"""Typed metadata storage on Maya nodes.

Each key becomes a hidden string attribute ``tikMeta_<key>`` holding a JSON
payload. This keeps arbitrary, typed metadata on any node without inventing
node types, and survives renames because it is attribute-based.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterator

from maya import cmds

from .registry import resolve

META_PREFIX = "tikMeta_"
_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ANY = object()


class MetaStore:
    """Mapping-like access to a node's metadata attributes."""

    def __init__(self, node) -> None:
        self._node = node

    # ---- helpers ---------------------------------------------------------
    @staticmethod
    def _attr(key: str) -> str:
        if not _KEY_PATTERN.match(key):
            raise ValueError(f"Invalid meta key '{key}'.")
        return f"{META_PREFIX}{key}"

    def _plug_path(self, key: str) -> str:
        return f"{self._node.long_name}.{self._attr(key)}"

    def _exists(self, key: str) -> bool:
        return cmds.attributeQuery(self._attr(key), node=self._node.long_name, exists=True)

    # ---- mapping protocol ------------------------------------------------
    def __getitem__(self, key: str) -> Any:
        if not self._exists(key):
            raise KeyError(key)
        raw = cmds.getAttr(self._plug_path(key)) or "null"
        return json.loads(raw)

    def __setitem__(self, key: str, value: Any) -> None:
        attr = self._attr(key)
        if not self._exists(key):
            cmds.addAttr(self._node.long_name, longName=attr, dataType="string", hidden=True)
        cmds.setAttr(self._plug_path(key), json.dumps(value), type="string")

    def __delitem__(self, key: str) -> None:
        if not self._exists(key):
            raise KeyError(key)
        cmds.deleteAttr(self._plug_path(key))

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and bool(_KEY_PATTERN.match(key)) and self._exists(key)

    def __iter__(self) -> Iterator[str]:
        return iter(self.keys())

    def __len__(self) -> int:
        return len(self.keys())

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def keys(self) -> list[str]:
        attrs = cmds.listAttr(self._node.long_name, userDefined=True) or []
        return [attr[len(META_PREFIX):] for attr in attrs if attr.startswith(META_PREFIX)]

    def items(self) -> list[tuple[str, Any]]:
        return [(key, self[key]) for key in self.keys()]

    def update(self, mapping: dict) -> None:
        for key, value in mapping.items():
            self[key] = value

    def clear(self) -> None:
        for key in self.keys():
            del self[key]

    def __repr__(self) -> str:
        return f"MetaStore({dict(self.items())!r})"


def find_by_meta(key: str, value: Any = _ANY, node_type: str | None = None) -> list:
    """Return wrapped nodes carrying meta ``key`` (optionally equal to ``value``)."""
    attr = MetaStore._attr(key)
    kwargs = {"long": True}
    if node_type:
        kwargs["type"] = node_type
    candidates = cmds.ls(f"*.{attr}", objectsOnly=True, **kwargs) or []
    found = []
    for name in candidates:
        node = resolve(name)
        if value is _ANY or node.meta.get(key) == value:
            found.append(node)
    return found
```

In `node.py` add:

```python
    @property
    def meta(self):
        """Typed metadata stored as hidden string attributes (see core.meta)."""
        from .meta import MetaStore  # local import avoids a cycle
        return MetaStore(self)
```

Export `find_by_meta`, `META_PREFIX` from `tik/maya/__init__.py`.

- [x] **Step 4: Run tests → PASS. Commit `feat(tik.maya): Node.meta metadata store and find_by_meta`.**

---

### Task 2: Attribute helpers

**Files:**
- Create: `src/python/tik/maya/core/attribute.py`
- Test: `tests/unit/test_attribute.py`

**Produces (all take a Node or name and return `Plug` where sensible):**
- `add_separator(node, name="____") -> Plug` (enum attr, non-keyable, channel box, locked)
- `add_float(node, name, default=0.0, min=None, max=None, keyable=True) -> Plug`; `add_int`, `add_bool`, `add_enum(node, name, items: list[str], default=0, keyable=True)`, `add_string(node, name, default="")`
- `lock_and_hide(node, attrs: Iterable[str] | None = None, hide=True)`; default attrs = t/r/s xyz + v
- `unlock(node, attrs=None, show=True)`
- `drive(source: Plug, targets: Iterable[Plug], force=True)` connects one to many
- `add_proxy(node, source: Plug, name=None) -> Plug` — `cmds.addAttr(proxy=...)`
- `TRANSFORM_ATTRS = ("tx","ty","tz","rx","ry","rz","sx","sy","sz")`, `ALL_CHANNELS = TRANSFORM_ATTRS + ("v",)`

- [x] **Step 1: Tests**

```python
from maya import cmds

import tik.maya as tm
from tik.maya.core import attribute as attr


def test_add_separator_is_locked_and_visible():
    node = tm.Transform.create(name="node")
    plug = attr.add_separator(node, "settings")
    assert plug.exists()
    assert cmds.getAttr(plug.path, lock=True)
    assert cmds.getAttr(plug.path, channelBox=True)
    assert not cmds.getAttr(plug.path, keyable=True)


def test_add_float_with_limits():
    node = tm.Transform.create(name="node")
    plug = attr.add_float(node, "stretch", default=1.0, min=0.0, max=2.0)
    assert plug.value == 1.0
    assert cmds.attributeQuery("stretch", node=node.name, minimum=True) == [0.0]
    assert cmds.attributeQuery("stretch", node=node.name, maximum=True) == [2.0]
    assert cmds.getAttr(plug.path, keyable=True)


def test_add_bool_int_enum_string():
    node = tm.Transform.create(name="node")
    assert attr.add_bool(node, "flag", default=True).value is True
    assert attr.add_int(node, "count", default=4).value == 4
    enum_plug = attr.add_enum(node, "space", ["world", "local"], default=1)
    assert enum_plug.value == 1
    assert cmds.attributeQuery("space", node=node.name, listEnum=True) == ["world:local"]
    assert attr.add_string(node, "label", default="hi").value == "hi"


def test_lock_and_hide_defaults_and_unlock():
    node = tm.Transform.create(name="node")
    attr.lock_and_hide(node)
    assert cmds.getAttr(f"{node.name}.tx", lock=True)
    assert not cmds.getAttr(f"{node.name}.tx", keyable=True)
    assert cmds.getAttr(f"{node.name}.v", lock=True)
    attr.unlock(node, ["tx"])
    assert not cmds.getAttr(f"{node.name}.tx", lock=True)
    assert cmds.getAttr(f"{node.name}.tx", keyable=True)


def test_lock_and_hide_subset_without_hide():
    node = tm.Transform.create(name="node")
    attr.lock_and_hide(node, ["sx", "sy", "sz"], hide=False)
    assert cmds.getAttr(f"{node.name}.sx", lock=True)
    assert cmds.getAttr(f"{node.name}.sx", keyable=True)
    assert not cmds.getAttr(f"{node.name}.tx", lock=True)


def test_drive_connects_one_to_many():
    source = tm.Transform.create(name="source")
    first = tm.Transform.create(name="first")
    second = tm.Transform.create(name="second")
    attr.drive(source["tx"], [first["ty"], second["tz"]])
    source["tx"].value = 3.0
    assert first["ty"].value == 3.0 and second["tz"].value == 3.0


def test_add_proxy():
    source = tm.Transform.create(name="source")
    holder = tm.Transform.create(name="holder")
    src_plug = attr.add_float(source, "stretch", default=0.25)
    proxy = attr.add_proxy(holder, src_plug)
    assert proxy.attr == "stretch"
    assert proxy.value == 0.25
    proxy.value = 0.75
    assert src_plug.value == 0.75
```

- [x] **Step 2: Run → ImportError.**
- [x] **Step 3: Implement**

```python
"""Attribute helpers shared by rig constructs and tools."""

from __future__ import annotations

from typing import Iterable, Optional

from maya import cmds

from .plug import Plug
from .registry import resolve

TRANSFORM_ATTRS = ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz")
ALL_CHANNELS = TRANSFORM_ATTRS + ("v",)


def _node(node):
    return node if hasattr(node, "long_name") else resolve(node)


def add_separator(node, name: str = "____") -> Plug:
    node = _node(node)
    cmds.addAttr(node.long_name, longName=name, attributeType="enum", enumName="----------", keyable=False)
    path = f"{node.long_name}.{name}"
    cmds.setAttr(path, channelBox=True)
    cmds.setAttr(path, lock=True)
    return Plug(node, name)


def _add_numeric(node, name, attribute_type, default, min_value, max_value, keyable) -> Plug:
    node = _node(node)
    kwargs = {"longName": name, "attributeType": attribute_type, "defaultValue": default, "keyable": keyable}
    if min_value is not None:
        kwargs["minValue"] = min_value
    if max_value is not None:
        kwargs["maxValue"] = max_value
    cmds.addAttr(node.long_name, **kwargs)
    return Plug(node, name)


def add_float(node, name, default=0.0, min=None, max=None, keyable=True) -> Plug:  # noqa: A002
    return _add_numeric(node, name, "double", float(default), min, max, keyable)


def add_int(node, name, default=0, min=None, max=None, keyable=True) -> Plug:  # noqa: A002
    return _add_numeric(node, name, "long", int(default), min, max, keyable)


def add_bool(node, name, default=False, keyable=True) -> Plug:
    node = _node(node)
    cmds.addAttr(node.long_name, longName=name, attributeType="bool", defaultValue=bool(default), keyable=keyable)
    return Plug(node, name)


def add_enum(node, name, items: Iterable[str], default=0, keyable=True) -> Plug:
    node = _node(node)
    cmds.addAttr(node.long_name, longName=name, attributeType="enum", enumName=":".join(items), defaultValue=default, keyable=keyable)
    return Plug(node, name)


def add_string(node, name, default="") -> Plug:
    node = _node(node)
    cmds.addAttr(node.long_name, longName=name, dataType="string")
    plug = Plug(node, name)
    if default:
        plug.value = default
    return plug


def lock_and_hide(node, attrs: Optional[Iterable[str]] = None, hide: bool = True) -> None:
    node = _node(node)
    for attr_name in attrs or ALL_CHANNELS:
        path = f"{node.long_name}.{attr_name}"
        cmds.setAttr(path, lock=True)
        if hide:
            cmds.setAttr(path, keyable=False, channelBox=False)


def unlock(node, attrs: Optional[Iterable[str]] = None, show: bool = True) -> None:
    node = _node(node)
    for attr_name in attrs or ALL_CHANNELS:
        path = f"{node.long_name}.{attr_name}"
        cmds.setAttr(path, lock=False)
        if show:
            cmds.setAttr(path, keyable=True)


def drive(source: Plug, targets: Iterable[Plug], force: bool = True) -> None:
    for target in targets:
        source.connect(target, force=force)


def add_proxy(node, source: Plug, name: Optional[str] = None) -> Plug:
    node = _node(node)
    name = name or source.attr
    cmds.addAttr(node.long_name, longName=name, proxy=source.path)
    return Plug(node, name)
```

- [x] **Step 4: Run → PASS. Commit `feat(tik.maya): attribute helpers`.**

---

### Task 3: Naming mechanics

**Files:** Create `src/python/tik/maya/core/naming.py`; Test `tests/unit/test_naming.py`

**Produces:**
- `unique_name(base: str, separator: str = "") -> str` — returns `base` if free, else `base1`, `base2`, … (respecting existing padded suffix e.g. `base01` → `base02` when `base01` exists).
- `format_name(*tokens, prefix=None, suffix=None, side=None, sep="_") -> str` — joins non-empty tokens; ordering: `side, prefix, *tokens, suffix`; ints allowed.

- [x] **Step 1: Tests**

```python
from maya import cmds

from tik.maya.core import naming


def test_unique_name_free():
    assert naming.unique_name("arm") == "arm"


def test_unique_name_increments():
    cmds.createNode("transform", name="arm")
    assert naming.unique_name("arm") == "arm1"
    cmds.createNode("transform", name="arm1")
    assert naming.unique_name("arm") == "arm2"


def test_unique_name_with_padding():
    cmds.createNode("transform", name="arm01")
    assert naming.unique_name("arm01") == "arm02"


def test_format_name():
    assert naming.format_name("upArm", 0, suffix="jnt", side="L") == "L_upArm_0_jnt"
    assert naming.format_name("root", prefix="trg") == "trg_root"
    assert naming.format_name("a", "", None, "b", sep="-") == "a-b"
```

- [x] **Step 2–4:** implement with `re.match(r"^(.*?)(\d+)$", base)` for padding, `cmds.objExists` loop; run; commit `feat(tik.maya): naming mechanics`.

---

### Task 4: Joint helpers, Transform alignment, IkHandle

**Files:**
- Modify: `src/python/tik/maya/types/joint.py`, `src/python/tik/maya/types/transform.py`
- Create: `src/python/tik/maya/types/ikhandle.py`
- Test: `tests/unit/test_joint.py` (extend), `tests/unit/test_ikhandle.py`, `tests/unit/test_transform.py` (extend)

**Produces:**
- `Transform.align_to(target, position=True, rotation=True)` (alias of `snap_to` semantics, name per spec), `Transform.aim_at(target, aim_vector=(1,0,0), up_vector=(0,1,0), world_up=(0,1,0))` (uses temporary aimConstraint then deletes), `Transform.world_position` property (MVector) setter/getter, `Transform.distance_to(other) -> float`, `Transform.between(a, b, ratio=0.5) -> MVector` (classmethod/static).
- `Joint.orient_chain(joints, aim_axis="x", up_axis="y", world_up=(0,1,0))` static; `Joint.joint_orient` property; `Joint.chain(positions, name_pattern="{index}", parent=None, radius=1.0) -> list[Joint]` classmethod creating a parented chain; `Joint.mirror(mirror_axis="x", search="L_", replace="R_", behavior=True) -> Joint`.
- `IkHandle.create(start: Joint, end: Joint, solver="ikRPsolver", name=None) -> IkHandle`; properties `start_joint`, `end_effector`, `solver`; `pole_vector(node)` creates poleVectorConstraint; `twist` plug shortcut.

- [x] **Step 1: Tests (ikhandle)**

```python
from maya import cmds

import tik.maya as tm
from tik.maya.types.ikhandle import IkHandle


def _chain():
    return tm.Joint.chain([(0, 0, 0), (2, 0, -1), (4, 0, 0)], name_pattern="ik_{index}")


def test_create_rp_handle():
    joints = _chain()
    handle = IkHandle.create(joints[0], joints[-1], name="arm_ikh")
    assert handle.type == "ikHandle"
    assert handle.name == "arm_ikh"
    assert handle.solver == "ikRPsolver"
    assert handle.start_joint.name == joints[0].name
    assert handle.end_effector.type == "ikEffector"


def test_pole_vector():
    joints = _chain()
    handle = IkHandle.create(joints[0], joints[-1], solver="ikRPsolver")
    pole = tm.Transform.create(name="pole")
    pole.translate = (2, 0, -5)
    constraint = handle.pole_vector(pole)
    assert constraint.type == "poleVectorConstraint"


def test_moving_handle_moves_chain():
    joints = _chain()
    handle = IkHandle.create(joints[0], joints[-1])
    handle.translate = (3, 1, 0)
    end_pos = joints[-1].world_translation
    assert abs(end_pos.x - 3) < 1e-3 and abs(end_pos.y - 1) < 1e-3
```

- [x] **Step 2: Tests (joint/transform additions)**

```python
def test_chain_creates_parented_joints():
    joints = tm.Joint.chain([(0, 0, 0), (1, 0, 0), (2, 0, 0)], name_pattern="c_{index}")
    assert [jnt.name for jnt in joints] == ["c_0", "c_1", "c_2"]
    assert joints[1].parent.name == "c_0"
    assert joints[2].world_translation.x == 2


def test_orient_chain_aims_x_down_chain():
    joints = tm.Joint.chain([(0, 0, 0), (0, 2, 0), (0, 4, 0)])
    tm.Joint.orient_chain(joints)
    # child should sit on +X in parent's local space
    assert abs(joints[1].translate.x - 2) < 1e-4
    assert abs(joints[1].translate.y) < 1e-4


def test_mirror_joint():
    joints = tm.Joint.chain([(1, 0, 0), (2, 0, 0)], name_pattern="L_j{index}")
    mirrored = joints[0].mirror(mirror_axis="x", search="L_", replace="R_")
    assert mirrored.name == "R_j0"
    assert mirrored.world_translation.x == -1


def test_transform_world_position_and_distance():
    first = tm.Transform.create(name="a")
    second = tm.Transform.create(name="b")
    second.world_position = (3, 4, 0)
    assert first.distance_to(second) == 5.0
    mid = tm.Transform.between(first, second)
    assert (mid.x, mid.y) == (1.5, 2.0)


def test_aim_at():
    first = tm.Transform.create(name="a")
    target = tm.Transform.create(name="b")
    target.translate = (0, 0, 5)
    first.aim_at(target, aim_vector=(1, 0, 0), up_vector=(0, 1, 0))
    assert abs(first.rotate.y + 90) < 1e-3
    assert not cmds.ls(type="aimConstraint")
```

- [x] **Step 3: Implement** — `Joint.chain` uses `Joint.create(name, parent=prev)` then `world_position` set; `orient_chain` via `cmds.joint(edit=True, orientJoint=..., secondaryAxisOrient=..., zeroScaleOrient=True)` per joint with last joint `orientation=(0,0,0)`; `mirror` via `cmds.mirrorJoint(mirrorYZ/XZ/XY, mirrorBehavior, searchReplace)`; `IkHandle` registered `@register("ikHandle")` subclass of `Transform`, `create` via `cmds.ikHandle(startJoint, endEffector, solver, name)`.
- [x] **Step 4: Run → PASS. Commit `feat(tik.maya): joint chain/orient/mirror helpers, Transform aim/between, IkHandle type`.**

---

### Task 5: MatrixConstraint construct

**Files:** Create `src/python/tik/maya/constructs/matrix_constraint.py`; Test `tests/unit/test_matrix_constraint.py`

**Produces:**
```python
class MatrixConstraint:
    @classmethod
    def create(cls, driver, driven, *, maintain_offset=True, skip_translate=(), skip_rotate=(), skip_scale=(), name=None) -> "MatrixConstraint"
    mult_matrix: Node; decompose: Node; driver: Transform; driven: Transform
    def delete(self)  # removes created nodes, restores driven inputs disconnected
```
Rules: `driver` may be a single node or a list (averaged via `wtAddMatrix` with equal weights — exposes `.average` node); joint driven gets jointOrient compensation (as old code); parent inverse matrix appended when driven has a parent; skips are iterables of `"x"/"y"/"z"`.

- [x] **Step 1: Tests**

```python
import pytest
from maya import cmds

import tik.maya as tm
from tik.maya.constructs.matrix_constraint import MatrixConstraint


def test_follows_driver_without_offset():
    driver = tm.Transform.create(name="driver")
    driven = tm.Transform.create(name="driven")
    driven.translate = (5, 0, 0)
    MatrixConstraint.create(driver, driven, maintain_offset=False)
    driver.translate = (1, 2, 3)
    assert driven.world_translation == driver.world_translation


def test_maintain_offset():
    driver = tm.Transform.create(name="driver")
    driven = tm.Transform.create(name="driven")
    driven.translate = (5, 0, 0)
    MatrixConstraint.create(driver, driven, maintain_offset=True)
    driver.translate = (1, 0, 0)
    assert abs(driven.world_translation.x - 6) < 1e-6


def test_respects_driven_parent():
    parent = tm.Transform.create(name="parent")
    parent.translate = (10, 0, 0)
    driver = tm.Transform.create(name="driver")
    driven = tm.Transform.create(name="driven", parent=parent.name)
    MatrixConstraint.create(driver, driven, maintain_offset=False)
    driver.translate = (2, 0, 0)
    assert abs(driven.world_translation.x - 2) < 1e-6
    assert abs(driven.translate.x + 8) < 1e-6


def test_skip_channels():
    driver = tm.Transform.create(name="driver")
    driven = tm.Transform.create(name="driven")
    MatrixConstraint.create(driver, driven, maintain_offset=False, skip_translate=("y",), skip_rotate=("x", "y", "z"), skip_scale=("x", "y", "z"))
    assert cmds.listConnections(f"{driven.name}.ty", source=True, destination=False) is None
    assert cmds.listConnections(f"{driven.name}.tx", source=True, destination=False)
    assert cmds.listConnections(f"{driven.name}.rx", source=True, destination=False) is None
    assert cmds.listConnections(f"{driven.name}.sx", source=True, destination=False) is None


def test_joint_orientation_compensation():
    driver = tm.Transform.create(name="driver")
    driver.rotate = (0, 45, 0)
    joint = tm.Joint.create(name="jnt")
    joint.joint_orient = (0, 45, 0)
    MatrixConstraint.create(driver, joint, maintain_offset=False)
    assert abs(joint.rotate.y) < 1e-4  # orientation absorbed by jointOrient
    driver.rotate = (0, 90, 0)
    assert abs(joint.rotate.y - 45) < 1e-4


def test_multiple_drivers_average():
    first = tm.Transform.create(name="first")
    second = tm.Transform.create(name="second")
    second.translate = (4, 0, 0)
    driven = tm.Transform.create(name="driven")
    constraint = MatrixConstraint.create([first, second], driven, maintain_offset=False)
    assert constraint.average is not None
    assert abs(driven.world_translation.x - 2) < 1e-6


def test_delete_cleans_nodes():
    driver = tm.Transform.create(name="driver")
    driven = tm.Transform.create(name="driven")
    constraint = MatrixConstraint.create(driver, driven, name="test")
    constraint.delete()
    assert not cmds.ls("test_multMatrix")
    assert cmds.listConnections(f"{driven.name}.t", source=True, destination=False) is None
```

- [x] **Step 2–4:** implement following the old `matrixConstraint` reference (nodes: `{name}_multMatrix`, `{name}_decomposeMatrix`, joint strand `{name}_rotateComposeMatrix` etc.), using `Plug` `>>` connections; run; commit `feat(tik.maya): MatrixConstraint construct`.

---

### Task 6: MatrixSwitch and SpaceSwitch constructs

**Files:** Create `constructs/matrix_switch.py`, `constructs/space_switch.py`; Tests `test_matrix_switch.py`, `test_space_switch.py`

**Produces:**
- `MatrixSwitch.create(drivers: list, driven, control: Plug | None = None, *, maintain_offset=True, name=None)` — `blendMatrix` (Maya 2020+) with one target per driver; `control` (enum plug, created on driven's parent-less holder if None) drives target weights via `condition`/setDrivenKey-free math: weight_i = (control == i) using `condition` nodes. Properties: `blend`, `control`, `constraint` (the MatrixConstraint on the blend output).
- `SpaceSwitch.create(node, spaces: list, *, control=None, attr_name="space", mode="parent", labels=None, default=0, name=None)` — creates offset group `{node}_space` above `node`, enum attr on `control or node` with labels (world + spaces), and a `MatrixSwitch` driving the offset group with skip based on mode (`point` skips rotate, `orient` skips translate). Properties `attr: Plug`, `offset: Transform`, `switch: MatrixSwitch`. `add_space(target, label)`.

- [x] **Step 1: Tests (space switch)**

```python
from maya import cmds

import tik.maya as tm
from tik.maya.constructs.space_switch import SpaceSwitch


def _setup():
    ctrl = tm.Transform.create(name="ctrl")
    ctrl.translate = (1, 0, 0)
    space_a = tm.Transform.create(name="A")
    space_b = tm.Transform.create(name="B")
    space_b.translate = (10, 0, 0)
    return ctrl, space_a, space_b


def test_creates_enum_and_offset():
    ctrl, space_a, space_b = _setup()
    switch = SpaceSwitch.create(ctrl, [space_a, space_b])
    assert switch.attr.attr == "space"
    assert cmds.attributeQuery("space", node=ctrl.name, listEnum=True) == ["world:A:B"]
    assert ctrl.parent.name == switch.offset.name


def test_switching_follows_target_keeping_offset():
    ctrl, space_a, space_b = _setup()
    switch = SpaceSwitch.create(ctrl, [space_a, space_b])
    switch.attr.value = 2
    assert abs(ctrl.world_translation.x - 1) < 1e-6  # offset maintained at switch creation
    space_b.translate = (12, 0, 0)
    assert abs(ctrl.world_translation.x - 3) < 1e-6
    switch.attr.value = 1
    space_a.translate = (0, 5, 0)
    assert abs(ctrl.world_translation.y - 5) < 1e-6


def test_orient_mode_skips_translate():
    ctrl, space_a, space_b = _setup()
    switch = SpaceSwitch.create(ctrl, [space_a, space_b], mode="orient")
    switch.attr.value = 2
    space_b.translate = (50, 0, 0)
    assert abs(ctrl.world_translation.x - 1) < 1e-6
    space_b.rotate = (0, 0, 90)
    assert abs(ctrl.world_translation.y - 1) < 1e-4 or abs(ctrl.rotate.z - 90) < 1e-4


def test_add_space_extends_enum():
    ctrl, space_a, space_b = _setup()
    switch = SpaceSwitch.create(ctrl, [space_a])
    switch.add_space(space_b, label="hand")
    assert cmds.attributeQuery("space", node=ctrl.name, listEnum=True) == ["world:A:hand"]
```

- [x] **Step 2: Tests (matrix switch)** — two drivers, enum control 0/1, driven follows selected; `maintain_offset` verified; skip through constraint kwargs.
- [x] **Step 3–4:** implement, run, commit `feat(tik.maya): MatrixSwitch and SpaceSwitch constructs`.

---

### Task 7: Measure construct

**Files:** Create `constructs/measure.py`; Test `test_measure.py`

**Produces:** `Measure.create(start, end, name=None) -> Measure` using `distanceBetween` fed by `worldMatrix` plugs; `distance: Plug` (`.distance`), `node`, `start`, `end`, `initial_distance: float`, `ratio_plug(scale_plug=None) -> Plug` (distance / initial [/ global scale]) built with Plug arithmetic.

- [x] Tests: distance equals 5 for (0,0,0)-(3,4,0); moving end updates plug; `ratio_plug().value == 2.0` after doubling; with `scale_plug` set to 2 ratio returns 1.0. Implement, run, commit `feat(tik.maya): Measure construct`.

---

### Task 8: Ribbon construct

**Files:** Create `constructs/ribbon.py`; Test `test_ribbon.py`

**Produces:**
```python
Ribbon.create(start, end, *, name, joint_count=5, controller_count=1, up_vector=(0,1,0), scaleable=True, parent=None) -> Ribbon
properties: group, scale_group, nonscale_group, surface (Nurbs), deformer_joints: list[Joint], controllers: list[Controller], start_plug: Transform, end_plug: Transform, start_aim: Transform, end_aim: Transform, scale_switch: Plug|None
methods: pin_start(node, maintain_offset=True) -> MatrixConstraint; pin_end(...); orient_start(node) -> MatrixConstraint (rotation only)
```
Implementation follows old `Ribbon`: nurbsPlane along X of length `distance(start,end)`, rebuilt to spans 5, follicles (`createNode follicle` + connect `outTranslate/outRotate`, `inputSurface`, `inputWorldMatrix`) at u = (i + 0.5) / joint_count, a `Joint` under each follicle transform; start/end plug locators with aim setup pointing to each other using the up locators; middle controllers (`Controller.create`) bound to the surface via a `skinCluster` of start/mid/end joints (`cmds.skinCluster(..., maximumInfluences=2)`) — controllers drive those bind joints; whole ribbon group aligned to `start` and aimed at `end`. Hidden helpers get `visibility=False`. Scaleable: per-joint distance-based `sx/sy/sz` driven by measure ratio with `scale_switch` blend.

- [x] **Step 1: Tests**

```python
import tik.maya as tm
from tik.maya.constructs.ribbon import Ribbon


def _endpoints():
    start = tm.Transform.create(name="start")
    end = tm.Transform.create(name="end")
    end.translate = (10, 0, 0)
    return start, end


def test_ribbon_creates_expected_nodes():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="upArm", joint_count=4, controller_count=1)
    assert len(ribbon.deformer_joints) == 4
    assert len(ribbon.controllers) == 1
    assert ribbon.surface.type == "nurbsSurface"
    assert ribbon.group.name == "upArm_ribbon_grp"
    assert ribbon.start_plug.parent.name == ribbon.scale_group.name


def test_joints_are_distributed_between_endpoints():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", joint_count=3)
    xs = sorted(jnt.world_translation.x for jnt in ribbon.deformer_joints)
    assert 0 < xs[0] < xs[1] < xs[2] < 10


def test_pinning_end_stretches_ribbon():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", joint_count=3)
    ribbon.pin_start(start)
    ribbon.pin_end(end)
    end.translate = (20, 0, 0)
    xs = sorted(jnt.world_translation.x for jnt in ribbon.deformer_joints)
    assert xs[-1] > 10


def test_scaleable_switch_exists():
    start, end = _endpoints()
    ribbon = Ribbon.create(start, end, name="rbn", scaleable=True)
    assert ribbon.scale_switch is not None
    assert ribbon.scale_switch.value == 1.0
```

- [x] **Step 2–4:** implement, run, commit `feat(tik.maya): Ribbon construct`.

---

### Task 9: IkFkChain construct

**Files:** Create `constructs/ikfk_chain.py`; Test `test_ikfk_chain.py`

**Produces:**
```python
IkFkChain.create(joints: list[Joint], *, name, switch: Plug | None = None, solver="ikRPsolver", parent=None) -> IkFkChain
properties: ik_joints, fk_joints, blend_joints (the input joints, now driven), ik_handle: IkHandle, switch: Plug (0=fk … 1=ik), group
methods: pole_vector(node) -> Node; ik_visibility: Plug; fk_visibility: Plug (reverse) 
```
Blend via one `blendMatrix` per joint: input = fk joint worldMatrix, target = ik joint worldMatrix, weight = switch; output through `MatrixConstraint`-style decompose with parent-inverse (reuse `MatrixConstraint.create(blend_output_node, joint)` is not possible — implement small internal decompose). Simpler and robust: per joint `pairBlend`? No — use `blendMatrix` → `multMatrix(parentInverse)` → `decomposeMatrix` → joint t/r/s with jointOrient compensation reused from `MatrixConstraint` by giving `MatrixConstraint.create` an optional `driver_matrix_plug`. Add that kwarg in Task 5 (`driver` may be a `Plug` of matrix type).

- [x] **Step 1: Tests**

```python
import tik.maya as tm
from tik.maya.constructs.ikfk_chain import IkFkChain


def _chain():
    return tm.Joint.chain([(0, 0, 0), (3, 0, -1), (6, 0, 0)], name_pattern="arm_{index}")


def test_creates_duplicate_chains_and_switch():
    joints = _chain()
    chain = IkFkChain.create(joints, name="arm")
    assert len(chain.ik_joints) == 3 and len(chain.fk_joints) == 3
    assert chain.ik_handle.type == "ikHandle"
    assert chain.switch.attr == "ikFk"
    assert chain.switch.value == 1.0


def test_fk_drives_when_switch_zero():
    joints = _chain()
    chain = IkFkChain.create(joints, name="arm")
    chain.switch.value = 0.0
    chain.fk_joints[0].rotate = (0, 0, 45)
    assert abs(joints[0].rotate.z - 45) < 1e-4


def test_ik_drives_when_switch_one():
    joints = _chain()
    chain = IkFkChain.create(joints, name="arm")
    chain.switch.value = 1.0
    chain.ik_handle.translate = (4, 2, 0)
    end = joints[-1].world_translation
    assert abs(end.x - 4) < 1e-3 and abs(end.y - 2) < 1e-3


def test_visibility_plugs_are_inverse():
    joints = _chain()
    chain = IkFkChain.create(joints, name="arm")
    chain.switch.value = 0.25
    assert abs(chain.ik_visibility.value - 0.25) < 1e-6
    assert abs(chain.fk_visibility.value - 0.75) < 1e-6
```

- [x] **Step 2–4:** implement, run, commit `feat(tik.maya): IkFkChain construct`.

---

### Task 10: Exports, docs, full-suite verification

- [x] Export `IkHandle`, `MatrixConstraint`, `MatrixSwitch`, `SpaceSwitch`, `Measure`, `Ribbon`, `IkFkChain`, `find_by_meta`, `attribute`, `naming` from `tik/maya/__init__.py` and `constructs/__init__.py`.
- [x] Add `docs/source/tik_maya/guides/rig_constructs.rst` with one example per construct.
- [x] Run `tests/unit` full; all pass. Commit `feat(tik.maya): export rigging constructs, docs`.
