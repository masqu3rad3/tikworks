# Module References Engine — Implementation Plan (Phase 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A session can link another `.tr`'s modules, override anything a rigger authors on them, and build them alongside its own — through the Python API and the build, with no UI yet.

**Architecture:** `GuideDocument` gains a `references` list. Resolution **inserts referenced entries into the real `modules` list**, each carrying runtime-only `origin` and `source`, so every existing read and write in the guide layer works untouched. Overrides are never written imperatively: `to_dict()` skips referenced entries and emits each link's overrides by **diffing** the resolved entry against its source, with a pose tolerance so a draw/sync round-trip mints nothing.

**Tech Stack:** Python 3.10+, Maya 2024+ (`mayapy`), pytest. No third-party dependencies.

**Spec:** `docs/superpowers/specs/2026-09-06-module-referencing-design.md` — this plan implements §3, §4, §5.2's disabled-module rule, the reference-specific rows of §6.2, and §7.6. **Out of scope, deferred to Phase 3:** §7.1–7.4 (tree badges, graph frames, properties, gestures) and the kinematics module picker.

**Depends on:** Phase 1 (`docs/superpowers/plans/2026-09-06-kinematics-explicit-scope.md`), complete. `kinematics` already builds only what it names, which is what lets a referenced module build without any new build machinery.

## Global Constraints

- **No third-party deps.** Stdlib and Maya-bundled modules only.
- **`tik/trigger/core` stays pure** — no Maya, no Qt, no preferences, and (new in this phase) **no `tik.trigger.actions`**: `core/guide_reference.py` must write its own cycle check rather than reuse `Reference.expand`'s. Task 6 adds that rule to the boundary test.
- **Consume tik.maya.** No raw `maya.cmds` / `OpenMaya` / `pymel` in tool code.
- **One dialog surface.** Any user dialog goes through `tik.shared.ui.feedback.Feedback`.
- **Line length 88** (black), isort profile `black`, flake8 clean.
- **Docstrings on every public function**, imperative mood, matching the surrounding style.

## Running tests

```bash
MAYAPY="/c/Program Files/Autodesk/Maya2026/bin/mayapy"
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "$MAYAPY" -m pytest tests/unit -q
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "$MAYAPY" -m pytest tests/integration -q
```

Baseline entering this phase: **1659 unit+integration, 494 UI, lint clean.**

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `src/python/tik/trigger/core/guide_document.py` | `ModuleReference`; `ModuleEntry` gains `origin` / `source` / `enabled`; `frames`; schema 1 → 2; `to_dict` skips referenced entries and delegates override serialization. | 1, 3 |
| `src/python/tik/trigger/core/guide_reference.py` | **New, pure.** Load, recurse, dedup, cycle-check, apply overrides, and diff resolved-vs-source back into overrides. The one place that knows what a reference *is*. | 2, 3 |
| `src/python/tik/trigger/session.py` | Runs resolution when the document is replaced; reports resolution problems and the reference-specific checks. | 4 |
| `src/python/tik/trigger/guides/scene.py` | Structural refusals: `remove()` and `clear()` must not delete referenced entries; `snapshot_from_scene` refuses while references exist. | 5 |
| `tests/unit/test_guide_reference_trigger.py` | **New.** Everything pure: resolution, overrides, diffing, dedup, cycles, nesting, broken links. | 1–3 |
| `tests/unit/test_session_references_trigger.py` | **New.** Session integration, validation, structural refusals. | 4, 5 |
| `tests/integration/trigger/test_reference_build_trigger.py` | **New.** A referenced module builds, and a local module attaches to it. | 4 |
| `tests/unit/test_import_boundaries.py` | `trigger/core` may not import `tik.trigger.actions`. | 6 |

---

### Task 1: `ModuleReference` and the entry fields it needs

Storage only — no resolution yet. Establishes the schema so later tasks have something to write into.

**Files:**
- Modify: `src/python/tik/trigger/core/guide_document.py`
- Test: `tests/unit/test_guide_reference_trigger.py` (create)

**Interfaces:**
- Produces: `ModuleReference(ref_id, file, version="latest", overrides={})` with `to_dict()` / `from_dict()`. `GuideDocument.references: list`, `GuideDocument.frames: dict`, `GuideDocument.reference(ref_id)`. `ModuleEntry.origin: Optional[str]`, `.source: Optional[ModuleEntry]`, `.enabled: bool` — all three **runtime-only**, never serialized on the entry. `SCHEMA_VERSION = 2`.

- [x] **Step 1: Write the failing test**

Create `tests/unit/test_guide_reference_trigger.py`:

```python
"""Module references: storage, resolution and diff-derived overrides. No Maya."""

import pytest

from tik.trigger.core.guide_document import (
    GuideDocument,
    GuideRecord,
    ModuleEntry,
    ModuleReference,
)


def _entry(instance_id, name="spine", module_type="toy_root", side="C"):
    return ModuleEntry(
        instance_id=instance_id, module_type=module_type, name=name, side=side
    )


def test_reference_round_trips():
    ref = ModuleReference(
        ref_id="r1",
        file="base.tr",
        version="latest",
        overrides={"aaa": {"enabled": False}},
    )
    again = ModuleReference.from_dict(ref.to_dict())
    assert again.ref_id == "r1"
    assert again.file == "base.tr"
    assert again.overrides == {"aaa": {"enabled": False}}


def test_document_round_trips_references_and_frames():
    document = GuideDocument(
        modules=[_entry("aaa")],
        references=[ModuleReference(ref_id="r1", file="base.tr")],
        frames={"r1": {"position": [10.0, 20.0], "collapsed": True}},
    )
    again = GuideDocument.from_dict(document.to_dict())
    assert [item.ref_id for item in again.references] == ["r1"]
    assert again.frames["r1"]["collapsed"] is True
    assert again.reference("r1").file == "base.tr"


def test_entry_runtime_fields_are_not_serialized():
    """origin, source and enabled are resolution state, not file content."""
    entry = _entry("aaa")
    entry.origin = "r1"
    entry.source = _entry("aaa")
    entry.enabled = False
    stored = entry.to_dict()
    assert "origin" not in stored and "source" not in stored
    assert "enabled" not in stored
    assert ModuleEntry.from_dict(stored).origin is None
    assert ModuleEntry.from_dict(stored).enabled is True


def test_a_referenced_entry_is_not_written_to_the_file():
    """The link plus its overrides is the storage; the entries are derived."""
    local = _entry("aaa")
    borrowed = _entry("bbb", name="arm")
    borrowed.origin = "r1"
    borrowed.source = _entry("bbb", name="arm")
    document = GuideDocument(
        modules=[local, borrowed],
        references=[ModuleReference(ref_id="r1", file="base.tr")],
    )
    stored = document.to_dict()
    assert [item["instance_id"] for item in stored["modules"]] == ["aaa"]


def test_schema_2_rejects_a_newer_document():
    with pytest.raises(ValueError):
        GuideDocument.from_dict({"schema": 99})
```

- [x] **Step 2: Run it to verify it fails**

```bash
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_guide_reference_trigger.py -q
```

Expected: FAIL — `ModuleReference` does not exist.

- [x] **Step 3: Add the dataclass and the fields**

In `src/python/tik/trigger/core/guide_document.py`, set `SCHEMA_VERSION = 2`, then add to `ModuleEntry` (after `guides`):

```python
    #: Resolution state, never serialized on the entry itself. ``origin`` is
    #: the ``ref_id`` of the link this entry came through (None when local);
    #: ``source`` is a deep copy of it before overrides, so the difference
    #: between the two *is* the override set. ``enabled`` is False only for a
    #: referenced module the host deliberately left out of its rig.
    #: ``compare=False`` matters: these would otherwise join the generated
    #: ``__eq__`` and make comparing two entries recurse through ``source``.
    origin: Optional[str] = field(default=None, compare=False, repr=False)
    source: Optional["ModuleEntry"] = field(default=None, compare=False, repr=False)
    enabled: bool = field(default=True, compare=False)
```

`to_dict` and `from_dict` are already explicit about which keys they write and read, so neither needs changing for these three — but add the assertion in the test above to keep it that way.

Add the reference dataclass next to `SceneGroup`:

```python
@dataclass
class ModuleReference:
    """A link to another session's modules.

    The link and its overrides are the only things stored; the modules
    themselves are resolved from the referenced file every time the document is
    loaded, so an upstream change arrives without anything here being touched.
    """

    ref_id: str
    file: str
    version: str = "latest"
    #: ``{instance_id: {enabled, name, side, settings, inputs, guides}}``,
    #: where a guide key is ``"<role>:<index>"``. Produced by diffing, never
    #: written by hand -- see ``core.guide_reference.overrides_for``.
    overrides: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """The JSON form stored in the document."""
        return {
            "ref_id": self.ref_id,
            "file": self.file,
            "version": self.version,
            "overrides": copy.deepcopy(self.overrides),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModuleReference":
        """Rebuild a reference from its JSON form."""
        return cls(
            ref_id=data["ref_id"],
            file=data.get("file", ""),
            version=data.get("version", "latest"),
            overrides=copy.deepcopy(data.get("overrides") or {}),
        )
```

Add `import copy` at the top of the module.

On `GuideDocument`, add the two fields and the accessor:

```python
    references: list = field(default_factory=list)
    #: Graph frame placement per reference: ``{ref_id: {position, collapsed}}``.
    #: Deliberately *not* ``positions``/``collapse``: those two are projected
    #: through ``node_ids()`` and replaced wholesale by ``layout_from_keys``,
    #: so a frame stored there would be deleted by the first node drag.
    frames: dict = field(default_factory=dict)

    def reference(self, ref_id: str) -> Optional["ModuleReference"]:
        """The link with ``ref_id``, or None."""
        for entry in self.references:
            if entry.ref_id == ref_id:
                return entry
        return None
```

Update `to_dict` to skip referenced entries and carry the two new sections:

```python
            "modules": [
                entry.to_dict() for entry in self.modules if entry.origin is None
            ],
            "references": [entry.to_dict() for entry in self.references],
            "frames": copy.deepcopy(self.frames),
```

and `from_dict` to read them:

```python
            references=[
                ModuleReference.from_dict(item)
                for item in (data.get("references") or [])
            ],
            frames=copy.deepcopy(data.get("frames") or {}),
```

- [x] **Step 4: Run it to verify it passes**

```bash
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_guide_reference_trigger.py tests/unit/test_guide_document_trigger.py -q
```

Expected: PASS.

- [x] **Step 5: Run the full unit suite**

```bash
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit -q
```

Any test asserting `GuideDocument.from_dict` output shape may need the two new keys. Update those; do not remove the keys to keep an old assertion happy.

- [x] **Step 6: Commit**

```bash
git add -A
git commit -m "Add ModuleReference to the guide document

The link and its overrides are the storage; referenced entries are
derived and never written to the file. Frames get their own section
rather than positions/collapse, which layout_from_keys replaces wholesale.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015xVfPaN3fdKbLNYdVWYS5n"
```

---

### Task 2: Resolution — pulling referenced modules in

**Files:**
- Create: `src/python/tik/trigger/core/guide_reference.py`
- Test: `tests/unit/test_guide_reference_trigger.py` (extend)

**Interfaces:**
- Consumes: `Document.load` (`tik/trigger/core/document.py`), `versioning.resolve` (`tik/trigger/core/versioning.py`), `SessionError` (`tik/trigger/core/exceptions.py`).
- Produces: `resolve(document, base_dir, loader=None) -> list[str]` — mutates `document.modules` in place, returns problem strings. `apply_overrides(entry, override) -> None`.

- [x] **Step 1: Write the failing test**

Append to `tests/unit/test_guide_reference_trigger.py`:

```python
# ------------------------------------------------------------- resolution
def _document_with(*entries, references=()) -> GuideDocument:
    return GuideDocument(modules=list(entries), references=list(references))


def _loader(table):
    """A Document.load stand-in mapping a path to a GuideDocument."""

    class _Doc:
        def __init__(self, guides):
            self.guides = guides

    def load(path):
        key = str(path)
        for name, guides in table.items():
            if key.endswith(name):
                return _Doc(guides)
        raise FileNotFoundError(key)

    return load


def test_resolution_inserts_referenced_entries():
    from tik.trigger.core.guide_reference import resolve

    base = _document_with(_entry("bbb", name="arm"))
    host = _document_with(
        _entry("aaa"), references=[ModuleReference(ref_id="r1", file="base.tr")]
    )
    problems = resolve(host, "", loader=_loader({"base.tr": base}))
    assert problems == []
    assert [item.instance_id for item in host.modules] == ["aaa", "bbb"]
    borrowed = host.module("bbb")
    assert borrowed.origin == "r1"
    assert borrowed.source is not None and borrowed.source.name == "arm"


def test_resolution_is_idempotent():
    """Resolving twice must not duplicate anything."""
    from tik.trigger.core.guide_reference import resolve

    base = _document_with(_entry("bbb", name="arm"))
    host = _document_with(
        _entry("aaa"), references=[ModuleReference(ref_id="r1", file="base.tr")]
    )
    loader = _loader({"base.tr": base})
    resolve(host, "", loader=loader)
    resolve(host, "", loader=loader)
    assert [item.instance_id for item in host.modules] == ["aaa", "bbb"]


def test_source_is_a_deep_copy():
    """Editing the resolved entry must not touch what it is compared against."""
    from tik.trigger.core.guide_reference import resolve

    record = GuideRecord(role="root", position=(0.0, 0.0, 0.0))
    upstream = _entry("bbb", name="arm")
    upstream.guides = [record]
    host = _document_with(references=[ModuleReference(ref_id="r1", file="base.tr")])
    resolve(host, "", loader=_loader({"base.tr": _document_with(upstream)}))
    borrowed = host.module("bbb")
    borrowed.guides[0].position = (9.0, 9.0, 9.0)
    assert borrowed.source.guides[0].position == (0.0, 0.0, 0.0)
    assert record.position == (0.0, 0.0, 0.0)


def test_overrides_are_applied_on_resolution():
    from tik.trigger.core.guide_reference import resolve

    upstream = _entry("bbb", name="arm", side="L")
    upstream.guides = [GuideRecord(role="root", position=(0.0, 0.0, 0.0))]
    upstream.settings = {"segments": 3}
    host = _document_with(
        references=[
            ModuleReference(
                ref_id="r1",
                file="base.tr",
                overrides={
                    "bbb": {
                        "name": "wing",
                        "settings": {"segments": 5},
                        "inputs": {"root": "aaa.root"},
                        "guides": {"root:0": {"position": [1.0, 2.0, 3.0]}},
                        "enabled": False,
                    }
                },
            )
        ]
    )
    resolve(host, "", loader=_loader({"base.tr": _document_with(upstream)}))
    borrowed = host.module("bbb")
    assert borrowed.name == "wing"
    assert borrowed.settings["segments"] == 5
    assert borrowed.inputs["root"] == "aaa.root"
    assert borrowed.guides[0].position == (1.0, 2.0, 3.0)
    assert borrowed.enabled is False
    # the source keeps upstream's word
    assert borrowed.source.name == "arm"
    assert borrowed.source.guides[0].position == (0.0, 0.0, 0.0)


def test_the_same_uuid_arriving_twice_is_dropped():
    """A diamond brings the same instance ids down two paths."""
    from tik.trigger.core.guide_reference import resolve

    shared = _document_with(_entry("bbb", name="arm"))
    host = _document_with(
        references=[
            ModuleReference(ref_id="r1", file="base.tr"),
            ModuleReference(ref_id="r2", file="props.tr"),
        ]
    )
    problems = resolve(
        host, "", loader=_loader({"base.tr": shared, "props.tr": shared})
    )
    assert [item.instance_id for item in host.modules] == ["bbb"]
    assert host.module("bbb").origin == "r1"
    assert any("already" in item for item in problems)


def test_a_missing_file_is_reported_not_raised():
    """A broken link must not stop the session opening."""
    from tik.trigger.core.guide_reference import resolve

    host = _document_with(
        _entry("aaa"), references=[ModuleReference(ref_id="r1", file="gone.tr")]
    )
    problems = resolve(host, "", loader=_loader({}))
    assert [item.instance_id for item in host.modules] == ["aaa"]
    assert any("gone.tr" in item for item in problems)


def test_a_cycle_is_reported():
    from tik.trigger.core.guide_reference import resolve

    host = _document_with(references=[ModuleReference(ref_id="r1", file="self.tr")])
    # the referenced document references itself straight back
    inner = _document_with(references=[ModuleReference(ref_id="r2", file="self.tr")])
    problems = resolve(host, "", loader=_loader({"self.tr": inner}))
    assert any("cycle" in item for item in problems)


def test_nested_references_are_owned_by_the_top_link():
    """An entry arriving through a chain belongs to the link it came through."""
    from tik.trigger.core.guide_reference import resolve

    deep = _document_with(_entry("ccc", name="hand"))
    middle = _document_with(
        _entry("bbb", name="arm"),
        references=[ModuleReference(ref_id="inner", file="deep.tr")],
    )
    host = _document_with(references=[ModuleReference(ref_id="r1", file="middle.tr")])
    resolve(host, "", loader=_loader({"middle.tr": middle, "deep.tr": deep}))
    assert sorted(item.instance_id for item in host.modules) == ["bbb", "ccc"]
    assert {item.origin for item in host.modules} == {"r1"}
```

- [x] **Step 2: Run it to verify it fails**

```bash
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_guide_reference_trigger.py -q
```

Expected: FAIL — no `guide_reference` module.

- [x] **Step 3: Write the resolver**

Create `src/python/tik/trigger/core/guide_reference.py`:

```python
"""Resolve a guide document's module references, and derive their overrides.

Pure Python: no Maya, no Qt, and deliberately no ``tik.trigger.actions`` --
the cycle check here is its own, rather than a reuse of the action
reference's, because ``core`` may not import an action package.

Two directions, and they are inverses:

* :func:`resolve` pulls referenced modules **into** the document, applying the
  stored overrides as it goes and keeping an untouched ``source`` beside each.
* :func:`overrides_for` reads the difference back **out**, which is how
  ``GuideDocument.to_dict`` produces the overrides it stores. Nothing writes an
  override imperatively, so reverting one is a delete and moving a guide back
  to where upstream put it removes it rather than pinning an equal value.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Callable, Optional

from . import versioning
from .guide_document import GuideDocument, ModuleEntry


def _resolve_path(reference, base_dir: str) -> Path:
    """The referenced file, made absolute and version-resolved."""
    path = Path(reference.file)
    if not path.is_absolute() and base_dir:
        path = Path(base_dir) / path
    return versioning.resolve(path, reference.version or "latest")


def _load_guides(path: Path, loader: Callable) -> GuideDocument:
    """The ``GuideDocument`` inside a ``.tr``."""
    return loader(path).guides


def apply_overrides(entry: ModuleEntry, override: dict) -> None:
    """Apply one module's stored overrides to a freshly loaded entry."""
    if "enabled" in override:
        entry.enabled = bool(override["enabled"])
    if override.get("name"):
        entry.name = str(override["name"])
    if override.get("side"):
        entry.side = str(override["side"])
    for key, value in (override.get("settings") or {}).items():
        entry.settings[key] = value
    for key, value in (override.get("inputs") or {}).items():
        entry.inputs[key] = value
    for key, values in (override.get("guides") or {}).items():
        role, _sep, index = key.rpartition(":")
        record = entry.guide(role, int(index or 0))
        if record is None:
            continue
        for name, value in values.items():
            if name == "attrs":
                record.attrs.update(value or {})
            elif name in ("position", "rotation", "joint_orient"):
                setattr(record, name, tuple(float(item) for item in value))
            elif name == "rotate_order":
                record.rotate_order = int(value)
            elif name == "radius":
                record.radius = float(value)
            elif name == "color":
                record.color = int(value)


def _entries_from(
    document: GuideDocument,
    base_dir: str,
    loader: Callable,
    chain: tuple,
    problems: list,
) -> list:
    """Every module a document contributes, its own references included."""
    found = list(document.modules)
    for reference in document.references:
        found.extend(
            _borrowed(reference, base_dir, loader, chain, problems, owner=None)
        )
    return found


def _borrowed(
    reference, base_dir: str, loader: Callable, chain: tuple, problems: list, owner
) -> list:
    """The entries one link contributes, overrides applied, sources attached."""
    try:
        path = _resolve_path(reference, base_dir)
    except (OSError, ValueError) as error:
        problems.append(f"reference '{reference.file}': {error}")
        return []
    key = str(path)
    if key in chain:
        names = " > ".join(Path(item).name for item in chain)
        problems.append(f"reference cycle: {names} > {path.name}")
        return []
    try:
        guides = _load_guides(path, loader)
    except Exception as error:  # noqa: BLE001 - a broken link is reported, not fatal
        problems.append(f"reference '{reference.file}' could not be read: {error}")
        return []
    inner = _entries_from(
        guides, str(path.parent), loader, chain + (key,), problems
    )
    found = []
    for entry in inner:
        # Deep copy first: ``source`` must never be an object the loader's
        # cache owns, or capture()'s in-place edits would move it too.
        fresh = ModuleEntry.from_dict(entry.to_dict())
        fresh.source = ModuleEntry.from_dict(entry.to_dict())
        # An entry arriving through a chain belongs to the link it came
        # through, so a host override on it is stored on that link.
        fresh.origin = owner or reference.ref_id
        apply_overrides(fresh, (reference.overrides or {}).get(fresh.instance_id, {}))
        found.append(fresh)
    return found


def resolve(
    document: GuideDocument, base_dir: str, loader: Optional[Callable] = None
) -> list:
    """Insert every referenced module into ``document.modules``. In place.

    Returns problems rather than raising: a broken link must not stop a
    session opening, or the Designer could not render a document well enough
    to let anybody fix it.
    """
    if loader is None:
        from .document import Document

        loader = Document.load
    document.modules = [item for item in document.modules if item.origin is None]
    problems: list = []
    seen = {item.instance_id for item in document.modules}
    for reference in document.references:
        for entry in _borrowed(reference, base_dir, loader, (), problems, None):
            if entry.instance_id in seen:
                problems.append(
                    f"warning: {entry.key} is already in this rig; the copy from "
                    f"'{reference.file}' was dropped."
                )
                continue
            seen.add(entry.instance_id)
            document.modules.append(entry)
    return problems
```

- [x] **Step 4: Run it to verify it passes**

```bash
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_guide_reference_trigger.py -q
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add -A
git commit -m "Resolve module references into the guide document

Referenced entries are inserted into the real modules list carrying a
deep-copied source, so every existing read and write in the guide layer
works on them untouched. Broken links and cycles are reported, never
raised: the Designer has to be able to render a document well enough for
somebody to fix it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015xVfPaN3fdKbLNYdVWYS5n"
```

---

### Task 3: Overrides derived by diffing

The other direction. This is the task that makes every existing write path work without knowing references exist.

**Files:**
- Modify: `src/python/tik/trigger/core/guide_reference.py` (add `overrides_for`)
- Modify: `src/python/tik/trigger/core/guide_document.py` (`to_dict` delegates)
- Test: `tests/unit/test_guide_reference_trigger.py` (extend)

**Interfaces:**
- Consumes: `reconcile.POSE_TOLERANCE`; `registry.get_module` for settings normalization (both in `core`).
- Produces: `overrides_for(entry) -> dict` (empty when nothing differs); `serialize_references(document) -> list`.

- [x] **Step 1: Write the failing test**

Append to `tests/unit/test_guide_reference_trigger.py`:

```python
# --------------------------------------------------------- diffed overrides
def _resolved_host(**override):
    """A host holding one referenced module, ready to be edited."""
    from tik.trigger.core.guide_reference import resolve

    upstream = _entry("bbb", name="arm", side="L")
    upstream.guides = [GuideRecord(role="root", position=(0.0, 0.0, 0.0))]
    host = _document_with(
        references=[
            ModuleReference(ref_id="r1", file="base.tr", overrides=dict(override))
        ]
    )
    resolve(host, "", loader=_loader({"base.tr": _document_with(upstream)}))
    return host


def test_an_untouched_reference_stores_no_overrides():
    from tik.trigger.core.guide_reference import overrides_for

    host = _resolved_host()
    assert overrides_for(host.module("bbb")) == {}
    assert host.to_dict()["references"][0]["overrides"] == {}


def test_moving_a_guide_produces_a_pose_override():
    host = _resolved_host()
    host.module("bbb").guides[0].position = (1.0, 2.0, 3.0)
    stored = host.to_dict()["references"][0]["overrides"]
    assert stored["bbb"]["guides"]["root:0"]["position"] == [1.0, 2.0, 3.0]


def test_moving_a_guide_back_removes_the_override():
    """Self-cleaning: an override must always mean a real difference."""
    host = _resolved_host()
    entry = host.module("bbb")
    entry.guides[0].position = (1.0, 2.0, 3.0)
    assert host.to_dict()["references"][0]["overrides"]
    entry.guides[0].position = (0.0, 0.0, 0.0)
    assert host.to_dict()["references"][0]["overrides"] == {}


def test_float_noise_does_not_mint_an_override():
    """A draw/sync round-trip carries noise; reconcile's tolerance applies."""
    host = _resolved_host()
    host.module("bbb").guides[0].position = (0.0, 1e-9, -1e-9)
    assert host.to_dict()["references"][0]["overrides"] == {}


def test_renaming_and_disabling_produce_overrides():
    host = _resolved_host()
    entry = host.module("bbb")
    entry.name = "wing"
    entry.enabled = False
    stored = host.to_dict()["references"][0]["overrides"]["bbb"]
    assert stored["name"] == "wing"
    assert stored["enabled"] is False


def test_an_input_rewire_produces_an_override():
    host = _resolved_host()
    host.module("bbb").inputs["root"] = "aaa.root"
    stored = host.to_dict()["references"][0]["overrides"]["bbb"]
    assert stored["inputs"] == {"root": "aaa.root"}


def test_overrides_survive_a_document_round_trip():
    """Store, reload, resolve again: the edit is still there."""
    from tik.trigger.core.guide_reference import resolve

    host = _resolved_host()
    host.module("bbb").name = "wing"
    stored = host.to_dict()

    upstream = _entry("bbb", name="arm", side="L")
    upstream.guides = [GuideRecord(role="root", position=(0.0, 0.0, 0.0))]
    reloaded = GuideDocument.from_dict(stored)
    resolve(reloaded, "", loader=_loader({"base.tr": _document_with(upstream)}))
    assert reloaded.module("bbb").name == "wing"
    assert reloaded.module("bbb").source.name == "arm"
```

- [x] **Step 2: Run it to verify it fails**

Expected: FAIL — `overrides_for` does not exist and `to_dict` writes the stored overrides untouched.

- [x] **Step 3: Implement the diff**

Append to `src/python/tik/trigger/core/guide_reference.py`:

```python
def _same_triple(one, two, tolerance: float) -> bool:
    """Whether two optional triples agree within ``tolerance``."""
    if one is None or two is None:
        return one is two
    return all(abs(a - b) <= tolerance for a, b in zip(one, two))


def _settings_diff(entry: ModuleEntry) -> dict:
    """Settings that differ, both sides normalized through the module class.

    ``write_settings`` stores a full value dict while an entry loaded from a
    file may be sparse -- and becomes sparse whenever a module class gains a
    field -- so a raw dict comparison would report every default as an
    override.
    """
    from . import registry

    def values(settings):
        try:
            module_cls = registry.get_module(entry.module_type)
        except Exception:  # noqa: BLE001 - unregistered: compare raw
            return dict(settings)
        return module_cls(settings=dict(settings)).values()

    mine, theirs = values(entry.settings), values(entry.source.settings)
    return {key: value for key, value in mine.items() if theirs.get(key) != value}


def _guides_diff(entry: ModuleEntry, tolerance: float) -> dict:
    """Per-guide differences, keyed ``"<role>:<index>"``."""
    sources = {record.pair: record for record in entry.source.guides}
    found: dict = {}
    for record in entry.guides:
        origin = sources.get(record.pair)
        if origin is None:
            continue  # structure is upstream's word; a new guide is not ours
        changed: dict = {}
        for name in ("position", "rotation", "joint_orient"):
            mine, theirs = getattr(record, name), getattr(origin, name)
            if not _same_triple(mine, theirs, tolerance):
                changed[name] = list(mine)
        if record.rotate_order != origin.rotate_order:
            changed["rotate_order"] = record.rotate_order
        if record.radius != origin.radius:
            changed["radius"] = record.radius
        if record.color != origin.color:
            changed["color"] = record.color
        if record.attrs != origin.attrs:
            changed["attrs"] = dict(record.attrs)
        if changed:
            found[f"{record.role}:{record.index}"] = changed
    return found


def overrides_for(entry: ModuleEntry, tolerance: Optional[float] = None) -> dict:
    """What ``entry`` differs from its source by. Empty when nothing does.

    This *is* the override set. Nothing stores one imperatively, which is why
    dragging a referenced guide back to where upstream put it removes the
    override rather than pinning it at a coincidentally equal value.
    """
    if entry.source is None:
        return {}
    if tolerance is None:
        from .reconcile import POSE_TOLERANCE

        tolerance = POSE_TOLERANCE
    override: dict = {}
    if entry.name != entry.source.name:
        override["name"] = entry.name
    if entry.side != entry.source.side:
        override["side"] = entry.side
    if not entry.enabled:
        override["enabled"] = False
    settings = _settings_diff(entry)
    if settings:
        override["settings"] = settings
    inputs = {
        key: value
        for key, value in entry.inputs.items()
        if entry.source.inputs.get(key) != value
    }
    if inputs:
        override["inputs"] = inputs
    guides = _guides_diff(entry, tolerance)
    if guides:
        override["guides"] = guides
    return override


def serialize_references(document: GuideDocument) -> list:
    """The document's links, each carrying freshly diffed overrides.

    An unresolved document (nothing was ever pulled in) keeps whatever
    overrides it was loaded with, so loading and saving without resolving
    cannot erase them.
    """
    by_origin: dict = {}
    for entry in document.modules:
        if entry.origin is not None and entry.source is not None:
            override = overrides_for(entry)
            if override:
                by_origin.setdefault(entry.origin, {})[entry.instance_id] = override
    resolved = {
        entry.origin for entry in document.modules if entry.origin is not None
    }
    stored = []
    for reference in document.references:
        data = reference.to_dict()
        if reference.ref_id in resolved:
            data["overrides"] = by_origin.get(reference.ref_id, {})
        stored.append(data)
    return stored
```

In `guide_document.py`, change `to_dict`'s references line to delegate:

```python
            "references": _serialize_references(self),
```

and add, near `_triple`:

```python
def _serialize_references(document) -> list:
    """Links with freshly diffed overrides. Local import: avoids a cycle."""
    from .guide_reference import serialize_references

    return serialize_references(document)
```

- [x] **Step 4: Run it to verify it passes**

```bash
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_guide_reference_trigger.py -q
```

Expected: PASS.

- [x] **Step 5: Run the whole unit suite, then commit**

```bash
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit -q
git add -A
git commit -m "Derive reference overrides by diffing at serialization

Every existing guide-layer write lands on the resolved entry unchanged;
to_dict reads the difference from source back out. Poses compare through
reconcile's tolerance, so a draw/sync round-trip mints nothing, and
settings are normalized through the module class so a default is never
mistaken for an override.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015xVfPaN3fdKbLNYdVWYS5n"
```

---

### Task 4: The session resolves, validates and builds

**Files:**
- Modify: `src/python/tik/trigger/session.py`
- Test: `tests/unit/test_session_references_trigger.py` (create)
- Test: `tests/integration/trigger/test_reference_build_trigger.py` (create)

**Interfaces:**
- Produces: `Session.resolve_references() -> list[str]`, `Session.reference_problems` (the last resolution's problems), `Session.link_modules(file, version="latest") -> ModuleReference`, `Session.unlink_modules(ref_id, bake=False) -> None`.

- [x] **Step 1: Write the failing tests**

Create `tests/unit/test_session_references_trigger.py` covering:

- opening a `.tr` whose reference names a real file resolves its modules into `session.document.guides.modules`, each with `origin` set;
- `undo` and `redo` leave the referenced modules present (resolution reruns);
- a saved-then-reopened session keeps a rename override;
- a broken link does **not** raise on open, and `validate()` reports it;
- a module listed in `kinematics` that is `enabled: False` is a validation error;
- `link_modules` is idempotent for the same resolved file, and says so;
- `unlink_modules(bake=True)` turns referenced entries into local ones with **new** uuids, and `bake=False` removes them.

Write these against real files on `tmp_path` (build a base `.tr` with `Session`, save it, then reference it) rather than a loader stub — this task is about the session's wiring, and a stub would not exercise path resolution.

Create `tests/integration/trigger/test_reference_build_trigger.py` covering:

- a host session referencing a base `.tr` builds a referenced module by naming its uuid in `kinematics`;
- a **local** module whose input names a referenced module's output builds and attaches;
- a pose override on a referenced guide moves the built rig.

- [x] **Step 2: Run them to verify they fail**

- [x] **Step 3: Wire the session**

Add to `Session`:

```python
    def resolve_references(self) -> list:
        """Pull every linked module into this session's guides. Idempotent."""
        from tik.trigger.core.guide_reference import resolve

        self.reference_problems = resolve(self.document.guides, self.directory)
        return self.reference_problems
```

Initialise `self.reference_problems: list = []` in `__init__` **before** any `load`, and call `resolve_references()` at the end of `__init__`, `load`, `new`, `undo`, `redo` and `snapshot_guides_from_scene`.

Do **not** call it from `touch()`. `touch()` already clears `_reference_cache` on every edit, so resolving there would re-read every referenced `.tr` from disk on every guide drag.

Add the link verbs:

```python
    def link_modules(self, file_path: str, version: str = "latest"):
        """Link another session's modules into this rig."""
```

and `unlink_modules(ref_id, bake=False)`, which either drops the entries or re-creates them as local modules with fresh uuids (rewriting any input that named an old id).

Extend `_scope_problems` with the reference-specific rows: a listed uuid that is `enabled: False` is an error, and `self.reference_problems` are appended by `validate()`.

- [x] **Step 4: Run the tests to verify they pass**

- [x] **Step 5: Run everything, then commit**

---

### Task 5: Structural refusals

Referenced entries now live in the real `modules` list, so the operations that **reassign** that list have to say what they do with them.

**Files:**
- Modify: `src/python/tik/trigger/guides/scene.py` (`remove`, `clear`, `snapshot_from_scene`)
- Test: `tests/unit/test_session_references_trigger.py` (extend)

**Interfaces:**
- Consumes: `GuideError` / `SessionError` from `tik/trigger/core/exceptions.py`.

- [x] **Step 1: Write the failing tests**

Assert: `remove()` on a referenced module raises and names `enabled: False` as the alternative; `clear()` removes local modules and **keeps** referenced ones; `snapshot_from_scene()` raises while the document holds references, naming unlinking as the way out.

- [x] **Step 2: Run them to verify they fail** — today `clear()` reassigns `document.modules = []` and drops referenced entries silently.

- [x] **Step 3: Implement**

In `remove()`, before deleting: raise when `entry.origin is not None`. In `clear()`, keep referenced entries:

```python
            self.document.modules = [
                entry for entry in self.document.modules if entry.origin is not None
            ]
```

and only delete the guides of the local ones. In `snapshot_from_scene()`, raise when `self.document.references` is non-empty — recovery builds a fresh document with no links, so every referenced module would become a local entry carrying upstream's uuid, and re-linking would then collide.

- [x] **Step 4: Check that a `.trg` export writes referenced modules as plain ones**

Referenced entries live in ``document.modules``, so ``exchange.export`` already
treats them as ordinary modules -- which is what spec §8 asks for, since a link
inside a copy format would dangle. Add a test asserting it rather than assuming
it, then run everything and commit.

---

### Task 6: `core` may not import an action package

Small, and it locks in the rule Task 2 relies on.

**Files:**
- Modify: `tests/unit/test_import_boundaries.py`

- [x] **Step 1: Add `tik.trigger.actions` to the `trigger/core` forbidden tuple**

```python
    "trigger/core": ("maya", "tik.maya", "tik.trigger.actions") + QT + PREFS,
```

- [x] **Step 2: Run it** — it must pass, since `core/guide_reference.py` writes its own cycle check.

```bash
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "/c/Program Files/Autodesk/Maya2026/bin/mayapy" -m pytest tests/unit/test_import_boundaries.py -q
```

- [x] **Step 3: Commit**

---

## Done when

**Status: complete.** 1700 unit+integration and 494 UI tests pass, lint clean.

- [x] `tests/unit`, `tests/integration` and `tests/ui` are green.
- [x] `make lint` is clean.
- [x] A session can link a `.tr`, build one of its modules by naming its uuid, override a guide pose, save, reopen, and still have that override.
- [x] `GuideScene.document` was **not** changed — the seam holds.
- [ ] Phase 3 (tree badges, graph frames, properties, gestures, the kinematics module picker — spec §7.1–7.4) has its own plan and is not started here.
