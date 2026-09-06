# Settings and Preferences Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Trigger a persistent, declarative preferences system reachable from **File › Settings…**, where adding a setting is one field line and no setting can ever change a built rig.

**Architecture:** A pure-Python spine in `tik/shared/prefs` (a JSON `PrefStore`, a `PrefPage` built on `tik.core.fields.Schema`, a registry) plus a generic Qt dialog in `tik/shared/ui/prefs_dialog.py`. Trigger contributes four page declarations under `tik/trigger/config/pages/`. The guarantee is enforced by `tests/unit/test_import_boundaries.py`: no package on the build path may import the prefs package.

**Tech Stack:** Python 3.10+, `tik.core.fields` (Schema/Field/FieldGroup), `tik.shared.ui.fields.FormBuilder`, `tik.shared.ui.collapsible.CollapsibleGroup`, Qt via `tik.shared.ui.Qt`, pytest under `mayapy`.

**Spec:** `docs/superpowers/specs/2026-09-06-settings-and-preferences-design.md`

## Global Constraints

- **No third-party dependencies.** Standard library and Maya-bundled modules only.
- **`tik/shared/prefs` is pure Python.** No Qt, no Maya imports anywhere in it.
- **The guarantee:** no module under `trigger/core`, `trigger/modules`, `trigger/systems`, `trigger/maya`, `trigger/actions` or `trigger/guides` may import `tik.trigger.config` or `tik.shared.prefs`. Only `tik/trigger/ui` reads preferences.
- **No import-time file I/O.** Importing `tik.trigger.config` must not touch the disk; the store loads on first attribute access.
- **Every `Field` must declare `help=`.** It is the tooltip and the search corpus. Enforced by test.
- **Every dialog goes through `tik.shared.ui.feedback.Feedback`.** Raw `QMessageBox`/`QFileDialog`/`QInputDialog` outside `shared/ui/feedback.py` fails `tests/unit/test_dialog_boundaries.py`.
- **Naming:** all new code is `prefs_*`. `tik/trigger/ui/settings_panel.py` already exists and is the per-action settings form — do not touch it, do not name anything near it.
- **Style:** black, isort (profile black), flake8. `make lint` must pass.
- **Test commands** (from the repo root, Windows):
  - Unit: `set PYTHONPATH=%CD%/src/python;%PYTHONPATH% && mayapy -m pytest tests/unit/<file> -v`
  - UI: `set PYTHONPATH=%CD%/src/python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/<file> -v`
  - Full: `make tests-unit`, `make tests-ui`, `make lint`

---

### Task 1: `PrefStore` — the JSON file

**Files:**
- Create: `src/python/tik/shared/prefs/__init__.py`
- Create: `src/python/tik/shared/prefs/store.py`
- Test: `tests/unit/test_prefs_store.py`

**Interfaces:**
- Consumes: `tik.core.jsonio.load`, `tik.core.jsonio.save`
- Produces: `PrefStore(name: str, folder: Path | str | None = None)` with `.path -> Path`, `.read() -> dict`, `.write(data: dict) -> None`

`PrefStore` is deliberately dumb: it reads and writes one flat JSON dict. All staging, defaults and change-tracking live in `Preferences` (Task 2). This keeps the file hand-editable and the store trivially testable.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_prefs_store.py`:

```python
"""Tests for tik.shared.prefs.store."""

import json


class TestPrefStorePath:
    """Where the file lands."""

    def test_resolves_under_folder_with_json_suffix(self, tmp_path):
        from tik.shared.prefs.store import PrefStore

        store = PrefStore("trigger", folder=tmp_path)
        assert store.path == tmp_path / "trigger.json"

    def test_path_is_absolute(self, tmp_path):
        from tik.shared.prefs.store import PrefStore

        store = PrefStore("trigger", folder=tmp_path)
        assert store.path.is_absolute()

    def test_defaults_to_home_tikworks(self):
        from pathlib import Path

        from tik.shared.prefs.store import PrefStore

        store = PrefStore("trigger")
        assert store.path == Path.home() / "TikWorks" / "trigger.json"

    def test_constructing_writes_nothing(self, tmp_path):
        from tik.shared.prefs.store import PrefStore

        PrefStore("trigger", folder=tmp_path)
        assert list(tmp_path.iterdir()) == []


class TestPrefStoreRead:
    """Reading tolerates every kind of missing or broken file."""

    def test_missing_file_reads_empty(self, tmp_path):
        from tik.shared.prefs.store import PrefStore

        assert PrefStore("trigger", folder=tmp_path).read() == {}

    def test_reads_written_data(self, tmp_path):
        from tik.shared.prefs.store import PrefStore

        store = PrefStore("trigger", folder=tmp_path)
        store.write({"interface.log_max_lines": 500})
        assert store.read() == {"interface.log_max_lines": 500}

    def test_corrupt_file_reads_empty(self, tmp_path):
        from tik.shared.prefs.store import PrefStore

        (tmp_path / "trigger.json").write_text("{not json", encoding="utf-8")
        assert PrefStore("trigger", folder=tmp_path).read() == {}

    def test_non_dict_file_reads_empty(self, tmp_path):
        from tik.shared.prefs.store import PrefStore

        (tmp_path / "trigger.json").write_text("[1, 2, 3]", encoding="utf-8")
        assert PrefStore("trigger", folder=tmp_path).read() == {}


class TestPrefStoreWrite:
    """Writing creates the folder and stays human-readable."""

    def test_creates_missing_folder(self, tmp_path):
        from tik.shared.prefs.store import PrefStore

        store = PrefStore("trigger", folder=tmp_path / "nested" / "deeper")
        store.write({"a": 1})
        assert store.path.is_file()

    def test_written_file_is_sorted_and_indented(self, tmp_path):
        from tik.shared.prefs.store import PrefStore

        store = PrefStore("trigger", folder=tmp_path)
        store.write({"b": 2, "a": 1})
        text = store.path.read_text(encoding="utf-8")
        assert text.index('"a"') < text.index('"b"')
        assert "\n" in text

    def test_write_replaces_previous_content(self, tmp_path):
        from tik.shared.prefs.store import PrefStore

        store = PrefStore("trigger", folder=tmp_path)
        store.write({"a": 1})
        store.write({"b": 2})
        assert json.loads(store.path.read_text(encoding="utf-8")) == {"b": 2}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `set PYTHONPATH=%CD%/src/python;%PYTHONPATH% && mayapy -m pytest tests/unit/test_prefs_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tik.shared.prefs'`

- [ ] **Step 3: Write the implementation**

Create `src/python/tik/shared/prefs/store.py`:

```python
"""The preferences file: one flat, hand-editable JSON dict.

Deliberately dumb. Defaults, staging and change tracking live in
``Preferences``; this class only knows how to read and write the file, and
how to survive finding it missing or mangled.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Union

from tik.core import jsonio

LOG = logging.getLogger(__name__)

#: Everything tikworks writes for a user lives here.
DEFAULT_FOLDER = Path.home() / "TikWorks"


class PrefStore:
    """A named JSON preferences file under ``folder``."""

    def __init__(self, name: str, folder: Union[str, Path, None] = None) -> None:
        """
        Args:
            name: File stem, without the extension (e.g. ``"trigger"``).
            folder: Where the file lives. Defaults to ``~/TikWorks``.
        """
        base = Path(folder) if folder is not None else DEFAULT_FOLDER
        self._path = (base / name).with_suffix(".json")

    @property
    def path(self) -> Path:
        """The absolute path of the preferences file."""
        return self._path

    def read(self) -> dict:
        """The stored mapping, or ``{}`` when it is missing or unreadable.

        A broken preferences file must never stop a tool from opening, so
        every failure here degrades to "no preferences stored yet".
        """
        try:
            data = jsonio.load(self._path)
        except FileNotFoundError:
            return {}
        except Exception:  # noqa: BLE001 - corrupt, unreadable, wrong perms
            LOG.warning("Ignoring unreadable preferences file: %s", self._path)
            return {}
        if not isinstance(data, dict):
            LOG.warning("Preferences file is not an object: %s", self._path)
            return {}
        return data

    def write(self, data: dict) -> None:
        """Replace the file's contents with ``data``, creating the folder."""
        jsonio.save(self._path, dict(data))

    def __repr__(self) -> str:
        return f"PrefStore({self._path})"
```

Create `src/python/tik/shared/prefs/__init__.py`:

```python
"""User preferences: a JSON store, declarative pages, and a registry.

Pure Python by rule -- no Qt, no Maya. The Qt dialog that renders these pages
lives in ``tik.shared.ui.prefs_dialog``.
"""

from tik.shared.prefs.store import DEFAULT_FOLDER, PrefStore

__all__ = ["DEFAULT_FOLDER", "PrefStore"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `set PYTHONPATH=%CD%/src/python;%PYTHONPATH% && mayapy -m pytest tests/unit/test_prefs_store.py -v`
Expected: PASS — 11 passed

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/shared/prefs tests/unit/test_prefs_store.py
git commit -m "feat(prefs): add PrefStore, the JSON preferences file"
```

---

### Task 2: `PrefPage`, the registry, and `Preferences`

**Files:**
- Create: `src/python/tik/shared/prefs/page.py`
- Create: `src/python/tik/shared/prefs/registry.py`
- Create: `src/python/tik/shared/prefs/preferences.py`
- Modify: `src/python/tik/shared/prefs/__init__.py`
- Test: `tests/unit/test_prefs_pages.py`

**Interfaces:**
- Consumes: `PrefStore` (Task 1), `tik.core.fields.Schema`, `tik.core.fields.Field`
- Produces:
  - `PrefPage` — `Schema` subclass with class attributes `name: str`, `label: str`, `order: int`
  - `register_page(cls)` — decorator; `pages() -> list[type[PrefPage]]` ordered by `(order, name)`; `clear_pages()` for tests
  - `Preferences(store, page_classes)` with `.page(name)`, `.pages()`, `.__getattr__(name)`, `.snapshot() -> dict`, `.restore(snapshot)`, `.save()`, `.reset_page(name)`, `.store`
  - Snapshot keys are flat `"<page>.<field>"` strings

Values live on page instances; `snapshot`/`restore` give the dialog its Cancel. `Preferences` loads lazily on first page access.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_prefs_pages.py`:

```python
"""Tests for tik.shared.prefs page declarations, registry and Preferences."""

import pytest


@pytest.fixture
def clean_registry():
    """Give each test an empty page registry and restore it afterwards."""
    from tik.shared.prefs import registry

    saved = registry.pages()
    registry.clear_pages()
    yield registry
    registry.clear_pages()
    for page in saved:
        registry.register_page(page)


@pytest.fixture
def demo_pages(clean_registry):
    """Two registered pages covering ordering and every basic field type."""
    from tik.core.fields import BoolField, ChoiceField, FieldGroup, IntField
    from tik.shared.prefs import PrefPage, register_page

    @register_page
    class Beta(PrefPage):
        name, label, order = "beta", "Beta", 20

        mode = ChoiceField(
            "fast", ["fast", "slow"], help="How hard to think about it."
        )

    @register_page
    class Alpha(PrefPage):
        name, label, order = "alpha", "Alpha", 10

        LOOK = FieldGroup("Look")

        enabled = BoolField(True, group=LOOK, help="Whether the thing is on.")
        count = IntField(3, min=1, max=10, group=LOOK, help="How many things.")

    return Alpha, Beta


class TestRegistry:
    """Pages register and come back in a stable order."""

    def test_pages_are_ordered_by_order_then_name(self, demo_pages):
        from tik.shared.prefs import registry

        assert [page.name for page in registry.pages()] == ["alpha", "beta"]

    def test_duplicate_name_raises(self, demo_pages):
        from tik.shared.prefs import PrefPage, register_page

        with pytest.raises(ValueError):

            @register_page
            class Clash(PrefPage):
                name, label, order = "alpha", "Clash", 99

    def test_page_without_name_raises(self, clean_registry):
        from tik.shared.prefs import PrefPage, register_page

        with pytest.raises(ValueError):

            @register_page
            class Nameless(PrefPage):
                label, order = "Nameless", 1


class TestPreferencesDefaults:
    """A fresh Preferences reports declared defaults and touches no disk."""

    def test_reads_declared_defaults(self, demo_pages, tmp_path):
        from tik.shared.prefs import Preferences, PrefStore, registry

        prefs = Preferences(PrefStore("demo", folder=tmp_path), registry.pages())
        assert prefs.alpha.count == 3
        assert prefs.beta.mode == "fast"

    def test_construction_writes_nothing(self, demo_pages, tmp_path):
        from tik.shared.prefs import Preferences, PrefStore, registry

        Preferences(PrefStore("demo", folder=tmp_path), registry.pages())
        assert list(tmp_path.iterdir()) == []

    def test_unknown_page_raises_attribute_error(self, demo_pages, tmp_path):
        from tik.shared.prefs import Preferences, PrefStore, registry

        prefs = Preferences(PrefStore("demo", folder=tmp_path), registry.pages())
        with pytest.raises(AttributeError):
            prefs.nonexistent


class TestPreferencesPersistence:
    """Values survive a save/load round trip."""

    def test_save_then_reload(self, demo_pages, tmp_path):
        from tik.shared.prefs import Preferences, PrefStore, registry

        store = PrefStore("demo", folder=tmp_path)
        prefs = Preferences(store, registry.pages())
        prefs.alpha.count = 7
        prefs.save()

        reloaded = Preferences(PrefStore("demo", folder=tmp_path), registry.pages())
        assert reloaded.alpha.count == 7

    def test_stored_file_uses_flat_dotted_keys(self, demo_pages, tmp_path):
        from tik.shared.prefs import Preferences, PrefStore, registry

        store = PrefStore("demo", folder=tmp_path)
        prefs = Preferences(store, registry.pages())
        prefs.alpha.count = 7
        prefs.save()
        assert store.read()["alpha.count"] == 7

    def test_unknown_stored_keys_are_ignored(self, demo_pages, tmp_path):
        from tik.shared.prefs import Preferences, PrefStore, registry

        store = PrefStore("demo", folder=tmp_path)
        store.write({"alpha.count": 5, "alpha.gone": 1, "ghost.key": 2})
        prefs = Preferences(store, registry.pages())
        assert prefs.alpha.count == 5

    def test_invalid_stored_value_falls_back_to_default(self, demo_pages, tmp_path):
        from tik.shared.prefs import Preferences, PrefStore, registry

        store = PrefStore("demo", folder=tmp_path)
        store.write({"alpha.count": 999})  # above max=10
        prefs = Preferences(store, registry.pages())
        assert prefs.alpha.count == 3


class TestSnapshotRestore:
    """Snapshot and restore are the dialog's Cancel."""

    def test_snapshot_covers_every_field(self, demo_pages, tmp_path):
        from tik.shared.prefs import Preferences, PrefStore, registry

        prefs = Preferences(PrefStore("demo", folder=tmp_path), registry.pages())
        assert set(prefs.snapshot()) == {"alpha.enabled", "alpha.count", "beta.mode"}

    def test_restore_puts_values_back(self, demo_pages, tmp_path):
        from tik.shared.prefs import Preferences, PrefStore, registry

        prefs = Preferences(PrefStore("demo", folder=tmp_path), registry.pages())
        before = prefs.snapshot()
        prefs.alpha.count = 9
        prefs.restore(before)
        assert prefs.alpha.count == 3

    def test_reset_page_restores_declared_defaults(self, demo_pages, tmp_path):
        from tik.shared.prefs import Preferences, PrefStore, registry

        prefs = Preferences(PrefStore("demo", folder=tmp_path), registry.pages())
        prefs.alpha.count = 9
        prefs.reset_page("alpha")
        assert prefs.alpha.count == 3


class TestFieldDiscipline:
    """Rules every page must follow, checked across the whole registry."""

    def test_every_field_declares_help(self, demo_pages):
        from tik.shared.prefs import registry

        missing = [
            f"{page.name}.{name}"
            for page in registry.pages()
            for name, field in page.fields().items()
            if not field.help
        ]
        assert missing == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `set PYTHONPATH=%CD%/src/python;%PYTHONPATH% && mayapy -m pytest tests/unit/test_prefs_pages.py -v`
Expected: FAIL — `ImportError: cannot import name 'registry' from 'tik.shared.prefs'`

- [ ] **Step 3: Write the implementation**

Create `src/python/tik/shared/prefs/page.py`:

```python
"""A preferences page: a ``Schema`` with a name, a label and a sort order."""

from __future__ import annotations

from tik.core.fields import Schema


class PrefPage(Schema):
    """One page in the preferences dialog.

    Subclasses declare ``Field`` attributes exactly as a module declares its
    settings, so adding a preference is one line and the dialog needs no
    changes at all. Every field must carry ``help=``: it is the tooltip and
    the text that search matches against.
    """

    #: Stable key used in the stored file and in ``prefs.<name>``.
    name: str = ""
    #: What the category list shows.
    label: str = ""
    #: Sort order in the category list; ties break on ``name``.
    order: int = 100

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.name!r})"
```

Create `src/python/tik/shared/prefs/registry.py`:

```python
"""Explicit registry for preference pages.

Mirrors ``tik.trigger.core.registry``: pages opt in with ``@register_page``
rather than being discovered by scanning.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_PAGES: dict[str, type] = {}


def register_page(cls: type) -> type:
    """Register a ``PrefPage`` subclass under its own ``name``.

    Raises:
        ValueError: If ``name`` is empty, or another class already claims it.
    """
    name = getattr(cls, "name", "")
    if not name:
        raise ValueError(f"{cls.__name__} must declare a non-empty 'name'.")
    existing = _PAGES.get(name)
    if existing is not None and existing is not cls:
        raise ValueError(f"A preferences page named '{name}' is already registered.")
    _PAGES[name] = cls
    logger.debug("Registered preferences page: %s", name)
    return cls


def pages() -> list[type]:
    """Every registered page, ordered by ``order`` then ``name``."""
    return sorted(_PAGES.values(), key=lambda page: (page.order, page.name))


def page(name: str) -> type:
    """The page class registered under ``name``.

    Raises:
        KeyError: If no page is registered under that name.
    """
    return _PAGES[name]


def clear_pages() -> None:
    """Empty the registry. For tests."""
    _PAGES.clear()
```

Create `src/python/tik/shared/prefs/preferences.py`:

```python
"""The live preference values: page instances backed by a ``PrefStore``.

Values live on the page instances. ``snapshot`` and ``restore`` are what give
the dialog its Cancel: it snapshots on open, edits the live pages through a
``FormBuilder``, and either saves or puts the snapshot back.

Loading is lazy. Importing a module that holds a ``Preferences`` must never
touch the disk -- under Maya the working directory is often unwritable, and an
import-time read is how the previous settings system broke.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from tik.core.fields import FieldValidationError
from tik.shared.prefs.store import PrefStore

LOG = logging.getLogger(__name__)


class Preferences:
    """Live preference values for a set of pages."""

    def __init__(self, store: PrefStore, page_classes: Iterable[type]) -> None:
        """
        Args:
            store: Where values are read from and written to.
            page_classes: ``PrefPage`` subclasses, in display order.
        """
        self._store = store
        self._classes = list(page_classes)
        self._pages: dict[str, Any] = {}
        self._loaded = False

    # ------------------------------------------------------------- loading
    @property
    def store(self) -> PrefStore:
        """The backing file."""
        return self._store

    def _ensure_loaded(self) -> None:
        """Instantiate the pages and fill them from the file, once."""
        if self._loaded:
            return
        # Set first: a failure below must not leave us retrying on every read.
        self._loaded = True
        self._pages = {cls.name: cls() for cls in self._classes}
        stored = self._store.read()
        for key, value in stored.items():
            page_name, _, field_name = key.partition(".")
            page = self._pages.get(page_name)
            if page is None or field_name not in page.fields():
                # A key from a removed page or a renamed field. Dropping it
                # silently is the point: the file is hand-editable, and old
                # keys must never stop the tool from opening.
                continue
            try:
                setattr(page, field_name, value)
            except FieldValidationError:
                LOG.warning(
                    "Ignoring invalid stored preference %s=%r; using the default.",
                    key,
                    value,
                )

    # --------------------------------------------------------------- pages
    def pages(self) -> list:
        """Every page instance, in display order."""
        self._ensure_loaded()
        return [self._pages[cls.name] for cls in self._classes]

    def page(self, name: str):
        """The page instance registered under ``name``.

        Raises:
            KeyError: If there is no such page.
        """
        self._ensure_loaded()
        return self._pages[name]

    def __getattr__(self, name: str):
        """``prefs.interface`` returns the Interface page instance."""
        # Only reached for attributes not found normally, so the leading
        # underscore guard keeps __init__ and copy/pickle out of the lookup.
        if name.startswith("_"):
            raise AttributeError(name)
        self._ensure_loaded()
        try:
            return self._pages[name]
        except KeyError:
            raise AttributeError(f"No preferences page named '{name}'.") from None

    # ----------------------------------------------------------- snapshots
    def snapshot(self) -> dict:
        """Every value, keyed ``"<page>.<field>"``."""
        return {
            f"{page.name}.{field}": value
            for page in self.pages()
            for field, value in page.values().items()
        }

    def restore(self, snapshot: dict) -> None:
        """Put a previous :meth:`snapshot` back onto the pages."""
        self._ensure_loaded()
        for key, value in snapshot.items():
            page_name, _, field_name = key.partition(".")
            page = self._pages.get(page_name)
            if page is not None and field_name in page.fields():
                setattr(page, field_name, value)

    def changed_keys(self, snapshot: dict) -> list[str]:
        """Keys whose value differs from ``snapshot``."""
        current = self.snapshot()
        return sorted(
            key for key, value in current.items() if snapshot.get(key) != value
        )

    def reset_page(self, name: str) -> None:
        """Restore one page to its declared defaults."""
        self.page(name).reset()

    # --------------------------------------------------------------- write
    def save(self) -> None:
        """Write every page's values to the file."""
        self._store.write(self.snapshot())

    def __repr__(self) -> str:
        return f"Preferences({self._store.path.name}, {len(self._classes)} pages)"


class LazyPreferences:
    """A ``Preferences`` that builds itself on first use.

    Lets a package expose a module-level ``prefs`` object without doing any
    file I/O at import time.
    """

    def __init__(self, factory) -> None:
        """
        Args:
            factory: Zero-argument callable returning a ``Preferences``.
        """
        self._factory = factory
        self._wrapped: Optional[Preferences] = None

    def _resolve(self) -> Preferences:
        if self._wrapped is None:
            self._wrapped = self._factory()
        return self._wrapped

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._resolve(), name)

    def __repr__(self) -> str:
        if self._wrapped is None:
            return "LazyPreferences(unloaded)"
        return repr(self._wrapped)
```

Replace `src/python/tik/shared/prefs/__init__.py`:

```python
"""User preferences: a JSON store, declarative pages, and a registry.

Pure Python by rule -- no Qt, no Maya. The Qt dialog that renders these pages
lives in ``tik.shared.ui.prefs_dialog``.
"""

from tik.shared.prefs import registry
from tik.shared.prefs.page import PrefPage
from tik.shared.prefs.preferences import LazyPreferences, Preferences
from tik.shared.prefs.registry import clear_pages, page, pages, register_page
from tik.shared.prefs.store import DEFAULT_FOLDER, PrefStore

__all__ = [
    "DEFAULT_FOLDER",
    "LazyPreferences",
    "PrefPage",
    "PrefStore",
    "Preferences",
    "clear_pages",
    "page",
    "pages",
    "register_page",
    "registry",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `set PYTHONPATH=%CD%/src/python;%PYTHONPATH% && mayapy -m pytest tests/unit/test_prefs_pages.py -v`
Expected: PASS — 15 passed

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/shared/prefs tests/unit/test_prefs_pages.py
git commit -m "feat(prefs): add PrefPage, the page registry and Preferences"
```

---

### Task 3: Trigger's four pages, replacing the old config

**Files:**
- Create: `src/python/tik/trigger/config/pages/__init__.py`
- Create: `src/python/tik/trigger/config/pages/interface.py`
- Create: `src/python/tik/trigger/config/pages/guides.py`
- Create: `src/python/tik/trigger/config/pages/files.py`
- Create: `src/python/tik/trigger/config/pages/tools.py`
- Modify: `src/python/tik/trigger/config/__init__.py` (full rewrite)
- Delete: `src/python/tik/trigger/config/settings.py`
- Delete: `src/python/tik/trigger/config/defaults.py`
- Delete: `src/python/tik/trigger/config/defaults.json`
- Delete: `tests/unit/test_settings_trigger.py`
- Test: `tests/unit/test_trigger_prefs.py`

**Interfaces:**
- Consumes: `PrefPage`, `register_page`, `Preferences`, `LazyPreferences`, `PrefStore`, `registry.pages` (Task 2)
- Produces: `tik.trigger.config.prefs` — a `LazyPreferences` exposing `.interface`, `.guides`, `.files`, `.tools`. Field names are fixed here and consumed verbatim in Tasks 7–11.

`tests/unit/test_settings_trigger.py` tests the `UserSettings` class being deleted, so it goes with it; `tests/unit/test_trigger_prefs.py` replaces it.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_trigger_prefs.py`:

```python
"""Tests for Trigger's preference pages."""

import pytest


class TestPagesRegistered:
    """The four pages exist, in order, with the expected fields."""

    def test_four_pages_in_order(self):
        from tik.trigger.config import prefs

        assert [page.name for page in prefs.pages()] == [
            "interface",
            "guides",
            "files",
            "tools",
        ]

    def test_every_field_declares_help(self):
        from tik.trigger.config import prefs

        missing = [
            f"{page.name}.{name}"
            for page in prefs.pages()
            for name, field in type(page).fields().items()
            if not field.help
        ]
        assert missing == []

    def test_no_duplicate_field_names_within_a_page(self):
        from tik.trigger.config import prefs

        for page in prefs.pages():
            names = list(type(page).fields())
            assert len(names) == len(set(names))


class TestDefaults:
    """Defaults match what the code did before it was configurable."""

    @pytest.mark.parametrize(
        "key,expected",
        [
            ("interface.restore_geometry", True),
            ("interface.restore_dock_layout", True),
            ("interface.log_open_on_error", False),
            ("interface.log_max_lines", 2000),
            ("interface.log_verbosity", "Info"),
            ("interface.graph_snap", True),
            ("interface.graph_show_grid", True),
            ("interface.graph_collapse_mode", "Everything"),
            ("guides.auto_sync", True),
            ("guides.draw_on_create", True),
            ("guides.confirm_delete_all", True),
            ("guides.confirm_reset_scene", True),
            ("files.remember_recent", True),
            ("files.max_recent", 8),
            ("files.remember_last_folder", True),
            ("files.default_folder", ""),
            ("files.autosave", False),
            ("files.autosave_interval", 300),
            ("files.confirm_unsaved_close", True),
            ("tools.external_editor", ""),
        ],
    )
    def test_default(self, key, expected):
        from tik.trigger.config import prefs

        page_name, _, field = key.partition(".")
        assert getattr(prefs.page(page_name), field) == expected


class TestLaziness:
    """Importing the package must not touch the disk."""

    def test_import_does_not_resolve_preferences(self):
        import tik.trigger.config as config

        fresh = config.LazyPreferences(config._build_preferences)
        assert repr(fresh) == "LazyPreferences(unloaded)"


class TestRejectedKeys:
    """Nothing that could change a rig may be declared as a preference."""

    @pytest.mark.parametrize(
        "banned",
        ["mirror_mapping", "side_suffixes", "center_prefix", "attribute_locking",
         "linear", "angular", "guide_size", "guide_radius"],
    )
    def test_banned_field_name_absent(self, banned):
        from tik.trigger.config import prefs

        for page in prefs.pages():
            assert banned not in type(page).fields()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `set PYTHONPATH=%CD%/src/python;%PYTHONPATH% && mayapy -m pytest tests/unit/test_trigger_prefs.py -v`
Expected: FAIL — `ImportError: cannot import name 'prefs' from 'tik.trigger.config'`

- [ ] **Step 3: Write the page declarations**

Create `src/python/tik/trigger/config/pages/interface.py`:

```python
"""Window, log and graph preferences."""

from __future__ import annotations

from tik.core.fields import BoolField, ChoiceField, FieldGroup, IntField
from tik.shared.prefs import PrefPage, register_page

#: Log verbosity choices, in the order the combo box shows them.
VERBOSITY = ["Error", "Warning", "Info", "Debug"]

#: What a newly placed graph node collapses to.
COLLAPSE = ["Header Only", "Connected Plugs", "Everything"]


@register_page
class InterfacePrefs(PrefPage):
    """How the Trigger window looks and what it remembers."""

    name, label, order = "interface", "Interface", 10

    WINDOW = FieldGroup("Window")
    LOG = FieldGroup("Log")
    GRAPH = FieldGroup("Graph")

    restore_geometry = BoolField(
        True,
        group=WINDOW,
        label="Restore size and position",
        help="Reopen the Trigger window where you last left it.",
    )
    restore_dock_layout = BoolField(
        True,
        group=WINDOW,
        label="Restore dock layout",
        help="Reopen the Log and Script docks where and as they were.",
    )
    log_open_on_error = BoolField(
        False,
        group=LOG,
        label="Open log on error",
        help="Raise the Log dock automatically when a build reports an error.",
    )
    log_max_lines = IntField(
        2000,
        min=100,
        max=100000,
        group=LOG,
        label="Maximum lines",
        help="Lines kept in the Log dock before the oldest are dropped.",
    )
    log_verbosity = ChoiceField(
        "Info",
        VERBOSITY,
        group=LOG,
        label="Verbosity",
        help="Lowest message level the Log dock shows. Debug is the noisiest.",
    )
    graph_snap = BoolField(
        True,
        group=GRAPH,
        label="Snap to grid",
        help="Snap nodes to the grid while dragging them in the Guide Designer.",
    )
    graph_show_grid = BoolField(
        True,
        group=GRAPH,
        label="Show grid",
        help="Draw the background grid in the Guide Designer graph.",
    )
    graph_collapse_mode = ChoiceField(
        "Everything",
        COLLAPSE,
        group=GRAPH,
        label="New node collapse",
        help="How much of a node is shown when it first appears in the graph.",
    )
```

Create `src/python/tik/trigger/config/pages/guides.py`:

```python
"""Guide authoring preferences.

These change what you write into the session document, never what a build
makes from an already-saved one, so they stay inside the guarantee.
"""

from __future__ import annotations

from tik.core.fields import BoolField, FieldGroup
from tik.shared.prefs import PrefPage, register_page


@register_page
class GuidesPrefs(PrefPage):
    """Defaults for the Guide Designer's authoring toggles."""

    name, label, order = "guides", "Guides", 20

    AUTHORING = FieldGroup("Authoring")
    CONFIRMATIONS = FieldGroup("Confirmations")

    auto_sync = BoolField(
        True,
        group=AUTHORING,
        label="Auto Sync by default",
        help=(
            "Start new Guide Designers with Auto Sync on, capturing guide poses "
            "from the scene as you move them."
        ),
    )
    draw_on_create = BoolField(
        True,
        group=AUTHORING,
        label="Draw new modules",
        help="Draw a module's guides into the scene as soon as you create it.",
    )
    confirm_delete_all = BoolField(
        True,
        group=CONFIRMATIONS,
        label="Confirm Delete All Modules",
        help="Ask before deleting every module from the session document.",
    )
    confirm_reset_scene = BoolField(
        True,
        group=CONFIRMATIONS,
        label="Confirm Reset Scene",
        help="Ask before throwing the Maya scene away.",
    )
```

Create `src/python/tik/trigger/config/pages/files.py`:

```python
"""Session file preferences: recent list, browsing, autosave."""

from __future__ import annotations

from tik.core.fields import BoolField, FieldGroup, FileField, IntField
from tik.shared.prefs import PrefPage, register_page


@register_page
class FilesPrefs(PrefPage):
    """How Trigger opens, remembers and protects session files."""

    name, label, order = "files", "Files & Sessions", 30

    RECENT = FieldGroup("Recent")
    BROWSING = FieldGroup("Browsing")
    AUTOSAVE = FieldGroup("Autosave")
    CONFIRMATIONS = FieldGroup("Confirmations")

    remember_recent = BoolField(
        True,
        group=RECENT,
        label="Remember recent sessions",
        help="Keep the Open Recent list between launches.",
    )
    max_recent = IntField(
        8,
        min=1,
        max=30,
        group=RECENT,
        label="How many to keep",
        help="Length of the Open Recent list.",
    )
    remember_last_folder = BoolField(
        True,
        group=BROWSING,
        label="Remember last folder",
        help="Reopen file browsers in the folder you last used.",
    )
    default_folder = FileField(
        "",
        mode="dir",
        group=BROWSING,
        label="Default session folder",
        help=(
            "Where file browsers start when there is no last folder. "
            "Empty means your home folder."
        ),
    )
    autosave = BoolField(
        False,
        group=AUTOSAVE,
        label="Enable autosave",
        help=(
            "Periodically write a recovery copy beside the session file. "
            "Your own file is never written without you asking."
        ),
    )
    autosave_interval = IntField(
        300,
        min=30,
        max=3600,
        group=AUTOSAVE,
        label="Interval (seconds)",
        help="How often a recovery copy is written while the session is modified.",
    )
    confirm_unsaved_close = BoolField(
        True,
        group=CONFIRMATIONS,
        label="Warn on unsaved close",
        help="Ask before closing a tab that has unsaved changes.",
    )
```

Create `src/python/tik/trigger/config/pages/tools.py`:

```python
"""External tool preferences."""

from __future__ import annotations

from tik.core.fields import FieldGroup, StringField
from tik.shared.prefs import PrefPage, register_page


@register_page
class ToolsPrefs(PrefPage):
    """Programs Trigger hands files to."""

    name, label, order = "tools", "External Tools", 40

    EDITOR = FieldGroup("Editor")

    external_editor = StringField(
        "",
        group=EDITOR,
        label="External editor command",
        help=(
            "Command that opens a script file. Use {path} where the file goes, "
            "for example: code -g {path}. Empty uses your system's default."
        ),
    )
```

Create `src/python/tik/trigger/config/pages/__init__.py`:

```python
"""Trigger's preference pages.

Importing this package is what registers them, so ``tik.trigger.config``
imports it inside its lazy factory rather than at module level.
"""

from tik.trigger.config.pages.files import FilesPrefs
from tik.trigger.config.pages.guides import GuidesPrefs
from tik.trigger.config.pages.interface import InterfacePrefs
from tik.trigger.config.pages.tools import ToolsPrefs

__all__ = ["FilesPrefs", "GuidesPrefs", "InterfacePrefs", "ToolsPrefs"]
```

- [ ] **Step 4: Replace the package entry point and delete the old system**

Replace `src/python/tik/trigger/config/__init__.py`:

```python
"""Trigger's user preferences.

``prefs`` is lazy: importing this package performs no file I/O, so it is safe
to import at module level from the UI. The store is read the first time a page
is touched.

Nothing on the build path may import this package -- a preference must never
be able to change a rig. ``tests/unit/test_import_boundaries.py`` enforces it.
"""

from tik.shared.prefs import LazyPreferences, Preferences, PrefStore

#: The file under ``~/TikWorks``.
STORE_NAME = "trigger"


def _build_preferences() -> Preferences:
    """Register Trigger's pages and bind them to the store."""
    from tik.shared.prefs import registry
    from tik.trigger.config import pages  # noqa: F401 - importing registers

    return Preferences(PrefStore(STORE_NAME), registry.pages())


#: Application-wide preference values. Resolved on first attribute access.
prefs = LazyPreferences(_build_preferences)

__all__ = ["LazyPreferences", "STORE_NAME", "prefs"]
```

Delete the superseded system:

```bash
git rm src/python/tik/trigger/config/settings.py
git rm src/python/tik/trigger/config/defaults.py
git rm src/python/tik/trigger/config/defaults.json
git rm tests/unit/test_settings_trigger.py
```

- [ ] **Step 5: Run test to verify it passes**

Run: `set PYTHONPATH=%CD%/src/python;%PYTHONPATH% && mayapy -m pytest tests/unit/test_trigger_prefs.py tests/unit/test_prefs_pages.py -v`
Expected: PASS — all green.

Note: `tik/trigger/actions/script/script.py:editor_command()` still imports the deleted `trigger_settings` and will fail. Task 4 moves it; if you need the suite green before then, run only the two files above.

- [ ] **Step 6: Commit**

```bash
git add -A src/python/tik/trigger/config tests/unit/test_trigger_prefs.py tests/unit/test_settings_trigger.py
git commit -m "feat(prefs): declare Trigger's four preference pages, drop the old settings module"
```

---

### Task 4: Enforce the guarantee, move `editor_command` to the UI

**Files:**
- Modify: `tests/unit/test_import_boundaries.py:16-27`
- Modify: `src/python/tik/trigger/actions/script/script.py:160-173` (remove `editor_command`)
- Create: `src/python/tik/trigger/ui/prefs_access.py`
- Modify: `src/python/tik/trigger/ui/script_dock.py:15,114`
- Modify: `src/python/tik/trigger/ui/settings_panel.py:15,186`

**Interfaces:**
- Consumes: `tik.trigger.config.prefs` (Task 3)
- Produces: `tik.trigger.ui.prefs_access.editor_command() -> str` — the replacement every UI call site uses

The guarantee's enforcement point. `editor_command` currently lives in the action layer, which may no longer read preferences; its only callers are two UI files.

- [ ] **Step 1: Write the failing test**

Modify `tests/unit/test_import_boundaries.py`. Replace the `FORBIDDEN` block (currently lines 16-27) with:

```python
QT = ("PySide2", "PySide6", "tik.vendor.Qt", "tik.shared.ui")

#: A user preference must never be able to change a rig. The build path is
#: therefore forbidden from importing the preferences packages at all, which
#: is a stronger and cheaper guarantee than reviewing every read site.
#: Only ``tik/trigger/ui`` may read preferences.
PREFS = ("tik.trigger.config", "tik.shared.prefs")

FORBIDDEN = {
    "core": ("maya", "tik.maya", "tik.trigger", "tik.shared") + QT,
    "maya": ("tik.trigger", "tik.shared") + QT,
    "trigger/core": ("maya", "tik.maya") + QT + PREFS,
    "trigger/modules": PREFS,
    "trigger/systems": PREFS,
    "trigger/maya": PREFS,
    "trigger/actions": PREFS,
    "trigger/guides": PREFS,
}
```

Note the old `"trigger/ui": ("tik.trigger.config",)` entry is **removed**: it existed because the previous settings singleton wrote a file at import time, and `prefs` is lazy.

Also add to `tests/unit/test_trigger_prefs.py`:

```python
class TestEditorCommand:
    """The editor command reads the preference, from the UI layer."""

    def test_reads_the_preference(self, monkeypatch):
        from tik.trigger.config import prefs
        from tik.trigger.ui import prefs_access

        monkeypatch.setattr(prefs.tools, "external_editor", "code -g {path}")
        assert prefs_access.editor_command() == "code -g {path}"

    def test_empty_by_default(self, monkeypatch):
        from tik.trigger.config import prefs
        from tik.trigger.ui import prefs_access

        monkeypatch.setattr(prefs.tools, "external_editor", "")
        assert prefs_access.editor_command() == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `set PYTHONPATH=%CD%/src/python;%PYTHONPATH% && mayapy -m pytest tests/unit/test_import_boundaries.py tests/unit/test_trigger_prefs.py -v`
Expected: FAIL — `test_no_forbidden_imports[trigger/actions-...]` reports `actions/script/script.py imports tik.trigger.config`, and the `prefs_access` tests fail to import.

- [ ] **Step 3: Move the function**

In `src/python/tik/trigger/actions/script/script.py`, delete the whole `editor_command` function (the `def editor_command() -> str:` block and its docstring, roughly lines 160-173).

Create `src/python/tik/trigger/ui/prefs_access.py`:

```python
"""Preference reads that more than one UI file needs.

Lives in the UI layer deliberately: ``tik/trigger/actions`` may not import the
preferences package, because nothing on the path from a saved session to a
built rig may read a user setting.
"""

from __future__ import annotations

from tik.trigger.config import prefs


def editor_command() -> str:
    """The user's external editor command, or ``""`` for the OS default.

    ``tik.shared.io.open_external`` substitutes ``{path}`` into the command
    and otherwise appends the file, so a launcher with arguments needs no
    second setting.
    """
    return str(prefs.tools.external_editor or "")
```

In `src/python/tik/trigger/ui/script_dock.py`, replace the import on line 15:

```python
from tik.trigger.ui.prefs_access import editor_command
```

In `src/python/tik/trigger/ui/settings_panel.py`, replace the import on line 15 with the same line. Both call sites (`script_dock.py:114`, `settings_panel.py:186`) keep calling `editor_command()` unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `set PYTHONPATH=%CD%/src/python;%PYTHONPATH% && mayapy -m pytest tests/unit/test_import_boundaries.py tests/unit/test_trigger_prefs.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_import_boundaries.py tests/unit/test_trigger_prefs.py src/python/tik/trigger/actions/script/script.py src/python/tik/trigger/ui/prefs_access.py src/python/tik/trigger/ui/script_dock.py src/python/tik/trigger/ui/settings_panel.py
git commit -m "feat(prefs): forbid the build path from reading preferences"
```

---

### Task 5: `FormBuilder.set_visible_fields` — the hook search needs

**Files:**
- Modify: `src/python/tik/shared/ui/fields.py` (add a method to `FormBuilder`)
- Test: `tests/ui/test_form_builder.py` (append)

**Interfaces:**
- Consumes: `FormBuilder._widgets`, `FormBuilder._labels`, `FormBuilder._groups` (existing private state)
- Produces: `FormBuilder.set_visible_fields(names: Optional[Iterable[str]]) -> None` — `None` shows everything; a collection hides every field not in it and hides any group left with nothing visible

Task 6 renders search results by showing every page's form filtered to its matches. This is the one change the existing widget needs.

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_form_builder.py`:

```python
class TestVisibleFields:
    """Filtering a form down to a subset of its fields."""

    @staticmethod
    def _form(qapp):
        from tik.core.fields import BoolField, FieldGroup, IntField, Schema
        from tik.shared.ui.fields import FormBuilder

        class Demo(Schema):
            LOOK = FieldGroup("Look")
            SIZE = FieldGroup("Size")

            enabled = BoolField(True, group=LOOK, help="on")
            colour = IntField(1, group=LOOK, help="hue")
            width = IntField(2, group=SIZE, help="wide")

        return FormBuilder(Demo()), Demo

    def test_hides_unlisted_fields(self, qapp):
        form, _ = self._form(qapp)
        form.set_visible_fields({"enabled"})
        assert form.widget("enabled").isVisibleTo(form)
        assert not form.widget("colour").isVisibleTo(form)

    def test_hides_group_with_no_visible_fields(self, qapp):
        form, _ = self._form(qapp)
        form.set_visible_fields({"enabled"})
        assert not form.group_widget("Size").isVisibleTo(form)

    def test_keeps_group_with_a_visible_field(self, qapp):
        form, _ = self._form(qapp)
        form.set_visible_fields({"width"})
        assert form.group_widget("Size").isVisibleTo(form)

    def test_none_restores_everything(self, qapp):
        form, _ = self._form(qapp)
        form.set_visible_fields({"enabled"})
        form.set_visible_fields(None)
        assert form.widget("colour").isVisibleTo(form)
        assert form.group_widget("Size").isVisibleTo(form)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `set PYTHONPATH=%CD%/src/python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_form_builder.py -k VisibleFields -v`
Expected: FAIL — `AttributeError: 'FormBuilder' object has no attribute 'set_visible_fields'`

- [ ] **Step 3: Write the implementation**

Add to `FormBuilder` in `src/python/tik/shared/ui/fields.py`, immediately after `mark_overrides`:

```python
    def set_visible_fields(self, names: Optional[Iterable[str]] = None) -> None:
        """Show only ``names``; ``None`` shows every field again.

        A group whose fields are all hidden hides too, so a filtered form has
        no empty folds. Visibility only -- values are untouched, so restoring
        the full form loses nothing the user typed.
        """
        target = None if names is None else set(names)
        if self._target is None:
            return
        fields = type(self._target).fields()
        for name in self._widgets:
            visible = target is None or name in target
            self._widgets[name].setVisible(visible)
            label = self._labels.get(name)
            if label is not None:
                label.setVisible(visible)
        for group_label, group in self._groups.items():
            group.setVisible(
                target is None
                or any(
                    name in target
                    for name, field in fields.items()
                    if field.group and field.group.label == group_label
                )
            )
```

Add `Iterable` to the `typing` import at the top of the file if it is not already there.

- [ ] **Step 4: Run test to verify it passes**

Run: `set PYTHONPATH=%CD%/src/python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_form_builder.py -v`
Expected: PASS — the new class plus every pre-existing test.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/shared/ui/fields.py tests/ui/test_form_builder.py
git commit -m "feat(ui): let a FormBuilder show a subset of its fields"
```

---

### Task 6: The preferences dialog

**Files:**
- Create: `src/python/tik/shared/ui/prefs_dialog.py`
- Test: `tests/ui/test_prefs_dialog.py`

**Interfaces:**
- Consumes: `Preferences` (Task 2), `FormBuilder.set_visible_fields` (Task 5), `tik.shared.ui.theme`
- Produces: `PrefsDialog(preferences, parent=None, title="Settings")` with signal `applied(list)` carrying changed keys, and methods `search(text: str)`, `apply_changes()`, `accept()`, `reject()`, `restore_defaults()`

Search filters the settings themselves across every page (spec §7.1). `Restore Defaults` is disabled while a search is active.

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_prefs_dialog.py`:

```python
"""Tests for the generic preferences dialog."""

import pytest


@pytest.fixture
def preferences(tmp_path):
    """A two-page Preferences on a throwaway store."""
    from tik.core.fields import BoolField, FieldGroup, IntField
    from tik.shared.prefs import PrefPage, Preferences, PrefStore

    class Alpha(PrefPage):
        name, label, order = "alpha", "Alpha", 10
        LOOK = FieldGroup("Look")
        enabled = BoolField(True, group=LOOK, help="Whether the log is shown.")
        count = IntField(3, min=1, max=10, group=LOOK, help="How many things.")

    class Beta(PrefPage):
        name, label, order = "beta", "Beta", 20
        SPEED = FieldGroup("Speed")
        turbo = BoolField(False, group=SPEED, help="Go faster.")

    return Preferences(PrefStore("demo", folder=tmp_path), [Alpha, Beta])


@pytest.fixture
def dialog(qapp, preferences):
    from tik.shared.ui.prefs_dialog import PrefsDialog

    return PrefsDialog(preferences)


class TestStructure:
    """The dialog builds itself from the registry."""

    def test_one_category_row_per_page(self, dialog):
        assert dialog.categories.count() == 2

    def test_category_labels_come_from_pages(self, dialog):
        labels = [dialog.categories.item(i).text() for i in range(2)]
        assert labels == ["Alpha", "Beta"]

    def test_first_page_is_selected(self, dialog):
        assert dialog.categories.currentRow() == 0

    def test_a_form_exists_per_page(self, dialog):
        assert set(dialog.forms) == {"alpha", "beta"}


class TestApply:
    """Apply writes, Cancel discards."""

    def test_apply_writes_the_file(self, dialog, preferences):
        preferences.alpha.count = 7
        dialog.apply_changes()
        assert preferences.store.read()["alpha.count"] == 7

    def test_apply_emits_changed_keys(self, dialog, preferences):
        seen = []
        dialog.applied.connect(seen.append)
        preferences.alpha.count = 7
        dialog.apply_changes()
        assert seen == [["alpha.count"]]

    def test_apply_twice_reports_nothing_the_second_time(self, dialog, preferences):
        seen = []
        dialog.applied.connect(seen.append)
        preferences.alpha.count = 7
        dialog.apply_changes()
        dialog.apply_changes()
        assert seen == [["alpha.count"], []]

    def test_reject_restores_the_opening_values(self, dialog, preferences):
        preferences.alpha.count = 7
        dialog.reject()
        assert preferences.alpha.count == 3

    def test_reject_does_not_write(self, dialog, preferences):
        preferences.alpha.count = 7
        dialog.reject()
        assert preferences.store.read() == {}

    def test_reject_after_apply_keeps_applied_values(self, dialog, preferences):
        preferences.alpha.count = 7
        dialog.apply_changes()
        preferences.alpha.count = 9
        dialog.reject()
        assert preferences.alpha.count == 7


class TestRestoreDefaults:
    """Restore Defaults acts on the selected page and stages like any edit."""

    def test_resets_the_current_page_only(self, dialog, preferences):
        preferences.alpha.count = 7
        preferences.beta.turbo = True
        dialog.categories.setCurrentRow(0)
        dialog.restore_defaults()
        assert preferences.alpha.count == 3
        assert preferences.beta.turbo is True

    def test_is_cancellable(self, dialog, preferences):
        preferences.alpha.count = 7
        dialog.apply_changes()
        dialog.restore_defaults()
        dialog.reject()
        assert preferences.alpha.count == 7

    def test_disabled_while_searching(self, dialog):
        dialog.search("log")
        assert not dialog.defaults_button.isEnabled()
        dialog.search("")
        assert dialog.defaults_button.isEnabled()


class TestSearch:
    """Search filters settings across every page."""

    def test_matches_a_label(self, dialog):
        dialog.search("count")
        assert dialog.forms["alpha"].isVisibleTo(dialog)
        assert not dialog.forms["beta"].isVisibleTo(dialog)

    def test_matches_help_text_not_just_labels(self, dialog):
        # "log" appears only in Alpha.enabled's help, never in a label.
        dialog.search("log")
        assert dialog.visible_matches() == ["alpha.enabled"]

    def test_is_case_insensitive(self, dialog):
        assert dialog.search("COUNT") == dialog.search("count")

    def test_empty_search_restores_single_page_view(self, dialog):
        dialog.search("count")
        dialog.search("")
        assert dialog.categories.isEnabled()
        assert dialog.forms["alpha"].isVisibleTo(dialog)
        assert not dialog.forms["beta"].isVisibleTo(dialog)

    def test_no_match_shows_the_empty_message(self, dialog):
        dialog.search("zzzznothing")
        assert dialog.empty_label.isVisibleTo(dialog)
        assert dialog.visible_matches() == []

    def test_search_does_not_change_values(self, dialog, preferences):
        dialog.search("count")
        dialog.search("")
        assert preferences.alpha.count == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `set PYTHONPATH=%CD%/src/python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_prefs_dialog.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tik.shared.ui.prefs_dialog'`

- [ ] **Step 3: Write the implementation**

Create `src/python/tik/shared/ui/prefs_dialog.py`:

```python
"""The preferences dialog: a category list, a generated page, and a footer.

Generic by construction -- it renders whatever pages a ``Preferences`` holds
and knows nothing about any particular tool. Adding a setting anywhere never
requires touching this file.

Two display modes share one scroll area. Normally a single page's form is
visible and the others are hidden. While a search is active every form is
shown at once, each filtered to its matching fields and captioned with its
page label, so results read as one list across categories.
"""

from __future__ import annotations

from typing import Optional

from tik.shared.prefs import Preferences
from tik.shared.ui import theme
from tik.shared.ui.fields import FormBuilder
from tik.shared.ui.Qt import QtCore, QtWidgets


class PrefsDialog(QtWidgets.QDialog):
    """Edit a ``Preferences`` object.

    Signals:
        applied(list): keys that changed, emitted after Apply or OK writes.
    """

    applied = QtCore.Signal(list)

    def __init__(
        self,
        preferences: Preferences,
        parent=None,
        title: str = "Settings",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setObjectName("PrefsDialog")
        self.setModal(True)
        self.resize(720, 480)
        self.prefs = preferences
        # What the values were when the dialog opened, and what they were at
        # the last Apply. The first is what Cancel puts back; the second is
        # what Apply diffs against to report changed keys.
        self._opening = preferences.snapshot()
        self._last_applied = dict(self._opening)
        self.forms: dict[str, FormBuilder] = {}
        self._captions: dict[str, QtWidgets.QLabel] = {}
        self._searching = False
        self._build()
        theme.apply(self)

    # ---------------------------------------------------------------- build
    def _build(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        body = QtWidgets.QHBoxLayout()
        body.setSpacing(8)
        layout.addLayout(body, 1)
        body.addWidget(self._build_sidebar())
        body.addWidget(self._build_pages(), 1)
        layout.addWidget(self._build_footer())

        self.categories.setCurrentRow(0)
        self._show_page(0)

    def _build_sidebar(self) -> QtWidgets.QWidget:
        holder = QtWidgets.QWidget()
        holder.setFixedWidth(170)
        column = QtWidgets.QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)

        self.search_field = QtWidgets.QLineEdit()
        self.search_field.setPlaceholderText("Search settings…")
        self.search_field.setClearButtonEnabled(True)
        self.search_field.textChanged.connect(self.search)
        column.addWidget(self.search_field)

        self.categories = QtWidgets.QListWidget()
        self.categories.setObjectName("PrefsCategories")
        for page in self.prefs.pages():
            item = QtWidgets.QListWidgetItem(page.label or page.name)
            item.setData(QtCore.Qt.UserRole, page.name)
            self.categories.addItem(item)
        self.categories.currentRowChanged.connect(self._show_page)
        column.addWidget(self.categories, 1)
        return holder

    def _build_pages(self) -> QtWidgets.QWidget:
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        inner = QtWidgets.QWidget()
        self._page_layout = QtWidgets.QVBoxLayout(inner)
        self._page_layout.setContentsMargins(4, 4, 4, 4)
        self._page_layout.setSpacing(4)

        for page in self.prefs.pages():
            caption = QtWidgets.QLabel(page.label or page.name)
            caption.setObjectName("PrefsCaption")
            caption.hide()
            self._captions[page.name] = caption
            self._page_layout.addWidget(caption)

            form = FormBuilder(page)
            self.forms[page.name] = form
            self._page_layout.addWidget(form)

        self.empty_label = QtWidgets.QLabel("No settings match.")
        self.empty_label.setObjectName("PrefsEmpty")
        self.empty_label.setAlignment(QtCore.Qt.AlignCenter)
        self.empty_label.hide()
        self._page_layout.addWidget(self.empty_label)
        self._page_layout.addStretch(1)

        self.scroll.setWidget(inner)
        return self.scroll

    def _build_footer(self) -> QtWidgets.QWidget:
        holder = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)

        self.defaults_button = QtWidgets.QPushButton("Restore Defaults")
        self.defaults_button.clicked.connect(self.restore_defaults)
        row.addWidget(self.defaults_button)
        row.addStretch(1)

        cancel = QtWidgets.QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)

        self.apply_button = QtWidgets.QPushButton("Apply")
        self.apply_button.clicked.connect(self.apply_changes)
        row.addWidget(self.apply_button)

        ok = QtWidgets.QPushButton("OK")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        return holder

    # ----------------------------------------------------------- page view
    def _page_names(self) -> list[str]:
        return [page.name for page in self.prefs.pages()]

    def current_page(self) -> Optional[str]:
        """The selected page's name, or None while searching."""
        if self._searching:
            return None
        row = self.categories.currentRow()
        names = self._page_names()
        return names[row] if 0 <= row < len(names) else None

    def _show_page(self, row: int) -> None:
        """Show exactly one page's form, unfiltered."""
        if self._searching:
            return
        names = self._page_names()
        if not 0 <= row < len(names):
            return
        wanted = names[row]
        for name, form in self.forms.items():
            form.set_visible_fields(None)
            form.setVisible(name == wanted)
            self._captions[name].hide()
        self.empty_label.hide()

    # -------------------------------------------------------------- search
    def _index(self) -> list[tuple[str, str, str]]:
        """``(page_name, field_name, haystack)`` for every field."""
        entries = []
        for page in self.prefs.pages():
            for field_name, field in type(page).fields().items():
                haystack = f"{field.label or field_name} {field.help}".lower()
                entries.append((page.name, field_name, haystack))
        return entries

    def search(self, text: str) -> list[str]:
        """Filter every page down to fields matching ``text``.

        Returns the matching ``"<page>.<field>"`` keys, so a caller (and the
        tests) can see what a query resolved to.
        """
        term = (text or "").strip().lower()
        self._searching = bool(term)
        self.defaults_button.setEnabled(not self._searching)
        self.categories.setEnabled(not self._searching)

        if not self._searching:
            self._show_page(self.categories.currentRow())
            return []

        matches: dict[str, set] = {name: set() for name in self.forms}
        for page_name, field_name, haystack in self._index():
            if term in haystack:
                matches[page_name].add(field_name)

        for name, form in self.forms.items():
            found = matches[name]
            form.set_visible_fields(found)
            form.setVisible(bool(found))
            self._captions[name].setVisible(bool(found))

        keys = sorted(
            f"{page}.{field}" for page, fields in matches.items() for field in fields
        )
        self.empty_label.setVisible(not keys)
        return keys

    def visible_matches(self) -> list[str]:
        """The keys currently shown by a search, empty when not searching."""
        if not self._searching:
            return []
        return self.search(self.search_field.text())

    # --------------------------------------------------------------- verbs
    def apply_changes(self) -> None:
        """Write the values and announce what changed."""
        changed = self.prefs.changed_keys(self._last_applied)
        self.prefs.save()
        self._last_applied = self.prefs.snapshot()
        self.applied.emit(changed)

    def restore_defaults(self) -> None:
        """Reset the selected page. Staged like any edit, so Cancel undoes it."""
        name = self.current_page()
        if name is None:
            return
        self.prefs.reset_page(name)
        self.forms[name].refresh()

    def accept(self) -> None:
        """Apply, then close."""
        self.apply_changes()
        super().accept()

    def reject(self) -> None:
        """Put back whatever was last written, then close."""
        self.prefs.restore(self._last_applied)
        super().reject()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `set PYTHONPATH=%CD%/src/python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_prefs_dialog.py -v`
Expected: PASS — 20 passed

- [ ] **Step 5: Add the two dialog styles**

Append to `src/python/tik/shared/ui/theme/theme.qss`:

```css
/*-----Preferences-------------------------------------------------------------------------------------------------------------------------------*/
QLabel#PrefsCaption { color: #8f8f8f; font-size: 10px; text-transform: uppercase; padding: 6px 0px 2px 4px; }

QLabel#PrefsEmpty { color: #8f8f8f; padding: 24px; }
```

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/shared/ui/prefs_dialog.py src/python/tik/shared/ui/theme/theme.qss tests/ui/test_prefs_dialog.py
git commit -m "feat(ui): add the preferences dialog with cross-page search"
```

---

### Task 7: File › Settings… in the Trigger window

**Files:**
- Modify: `src/python/tik/trigger/ui/main.py:145-179` (File menu), `:412` (Tools menu), `:852-854` (`open_settings`)
- Test: `tests/ui/test_menus.py` (append)

**Interfaces:**
- Consumes: `PrefsDialog` (Task 6), `tik.trigger.config.prefs` (Task 3)
- Produces: `TriggerWindow.open_settings()` opening a live dialog; `TriggerWindow._on_prefs_applied(changed: list)` — the dispatch table Tasks 8–11 extend

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_menus.py`:

```python
def _menu(window, title):
    """The QMenu registered under ``title``."""
    return window._menus[title]


def _action(menu, text):
    """The action in ``menu`` whose text starts with ``text``."""
    for action in menu.actions():
        if action.text().startswith(text):
            return action
    return None


class TestSettingsMenuEntry:
    """Settings lives under File, not Tools."""

    def test_settings_is_in_the_file_menu(self, window):
        assert _action(_menu(window, "&File"), "Settings") is not None

    def test_settings_is_not_in_the_tools_menu(self, window):
        assert _action(_menu(window, "&Tools"), "Settings") is None

    def test_settings_has_the_standard_shortcut(self, window):
        action = _action(_menu(window, "&File"), "Settings")
        assert action.shortcut().toString() == "Ctrl+,"

    def test_opening_settings_builds_a_dialog(self, window):
        dialog = window.open_settings(exec_=False)
        assert dialog.categories.count() == 4
        dialog.close()
```

If `tests/ui/test_menus.py` has no `window` fixture, reuse the construction the existing tests in that file already do — check the top of the file and follow it exactly rather than inventing a second fixture.

- [ ] **Step 2: Run test to verify it fails**

Run: `set PYTHONPATH=%CD%/src/python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_menus.py -v`
Expected: FAIL — no Settings action under File.

- [ ] **Step 3: Move the menu entry**

In `src/python/tik/trigger/ui/main.py`, inside `_build_file_menu`, insert immediately before the `Close Tab` block:

```python
        file_menu.addSeparator()
        self._action(file_menu, "Settings…", self.open_settings, "Ctrl+,")
```

In `_build_tools_menu`, delete the last two lines:

```python
        tools_menu.addSeparator()
        self._action(tools_menu, "Settings…", self.open_settings)
```

- [ ] **Step 4: Replace the placeholder**

Replace `open_settings` (currently lines 852-854) with:

```python
    def open_settings(self, exec_: bool = True):
        """Open the preferences dialog.

        Args:
            exec_: Run the modal loop. Tests pass False to inspect the dialog.

        Returns:
            The dialog, so a caller can inspect it.
        """
        from tik.shared.ui.prefs_dialog import PrefsDialog
        from tik.trigger.config import prefs

        dialog = PrefsDialog(prefs, self)
        dialog.applied.connect(self._on_prefs_applied)
        if exec_:
            dialog.exec_()
        return dialog

    def _on_prefs_applied(self, changed: list) -> None:
        """Push applied preferences into the widgets that cache them.

        Only settings that a *live* widget holds a copy of need pushing.
        Everything else is read at the point of use and picks the new value
        up on its own, which is why this table stays short.
        """
        if "interface.log_max_lines" in changed:
            self.log.setMaximumBlockCount(prefs_value("interface", "log_max_lines"))
```

Add this helper just above the `TriggerWindow` class in the same file:

```python
def prefs_value(page: str, field: str):
    """One preference value, read lazily so imports stay cheap."""
    from tik.trigger.config import prefs

    return getattr(prefs.page(page), field)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `set PYTHONPATH=%CD%/src/python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_menus.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/ui/main.py tests/ui/test_menus.py
git commit -m "feat(prefs): open the settings dialog from File > Settings"
```

---

### Task 8: Consume the Interface preferences

**Files:**
- Modify: `src/python/tik/trigger/ui/main.py` (`__init__`, `closeEvent`, `_on_prefs_applied`, `_on_log`)
- Modify: `src/python/tik/trigger/ui/widgets.py` (`LogWidget`)
- Test: `tests/ui/test_prefs_interface.py`

**Interfaces:**
- Consumes: `prefs.interface.*` (Task 3), `prefs_value` (Task 7)
- Produces: `TriggerWindow.save_window_state()`, `TriggerWindow.restore_window_state()`, `LogWidget.set_level(name: str)`

Geometry and dock state are opaque Qt blobs and stay in `QSettings` (spec §5), gated by the JSON booleans.

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_prefs_interface.py`:

```python
"""Interface preferences reach the widgets that hold them."""

import pytest

from tik.shared.ui.Qt import QtCore


@pytest.fixture
def window(qapp):
    from tik.trigger.ui.main import TriggerWindow

    made = TriggerWindow()
    yield made
    made.close()


class TestWindowState:
    """Geometry blobs round-trip through QSettings, gated by the preference."""

    def test_save_writes_geometry(self, window):
        window.save_window_state()
        stored = QtCore.QSettings("tikworks", "trigger").value("window/geometry")
        assert stored is not None

    def test_restore_is_a_no_op_when_disabled(self, window, monkeypatch):
        from tik.trigger.config import prefs

        window.save_window_state()
        monkeypatch.setattr(prefs.interface, "restore_geometry", False)
        monkeypatch.setattr(prefs.interface, "restore_dock_layout", False)
        # Must not raise, and must leave the window usable.
        window.restore_window_state()
        assert window.isEnabled()

    def test_restore_accepts_a_missing_blob(self, window):
        QtCore.QSettings("tikworks", "trigger").remove("window/geometry")
        window.restore_window_state()
        assert window.isEnabled()


class TestLogPreferences:
    """The log widget follows its preferences."""

    def test_max_lines_pushed_on_apply(self, window):
        window._on_prefs_applied(["interface.log_max_lines"])
        from tik.trigger.config import prefs

        assert window.log.maximumBlockCount() == prefs.interface.log_max_lines

    def test_set_level_filters_lower_messages(self, qapp):
        from tik.trigger.ui.widgets import LogWidget

        widget = LogWidget()
        widget.set_level("Error")
        widget.append_message("chatty", "info")
        assert widget.toPlainText().strip() == ""

    def test_set_level_keeps_higher_messages(self, qapp):
        from tik.trigger.ui.widgets import LogWidget

        widget = LogWidget()
        widget.set_level("Error")
        widget.append_message("broken", "error")
        assert "broken" in widget.toPlainText()

    def test_default_level_shows_info(self, qapp):
        from tik.trigger.ui.widgets import LogWidget

        widget = LogWidget()
        widget.append_message("hello", "info")
        assert "hello" in widget.toPlainText()

    def test_debug_hidden_at_info_level(self, qapp):
        from tik.trigger.ui.widgets import LogWidget

        widget = LogWidget()
        widget.set_level("Info")
        widget.append_message("noisy", "debug")
        assert widget.toPlainText().strip() == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `set PYTHONPATH=%CD%/src/python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_prefs_interface.py -v`
Expected: FAIL — `AttributeError: 'TriggerWindow' object has no attribute 'save_window_state'`

- [ ] **Step 3: Give LogWidget a level**

In `src/python/tik/trigger/ui/widgets.py`, replace the `LogWidget` class body with:

```python
class LogWidget(QtWidgets.QPlainTextEdit):
    """Read-only log fed by the event bus."""

    LEVEL_COLORS = {"warning": "#d9a400", "error": "#e05555"}

    #: Ranked low to high, matching the ``interface.log_verbosity`` choices.
    LEVELS = ("debug", "info", "warning", "error")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("LogWidget")
        self.setReadOnly(True)
        self.setMaximumBlockCount(2000)
        self._threshold = self.LEVELS.index("info")

    def set_level(self, name: str) -> None:
        """Drop messages below ``name`` (an ``interface.log_verbosity`` value)."""
        try:
            self._threshold = self.LEVELS.index(str(name).strip().lower())
        except ValueError:
            self._threshold = self.LEVELS.index("info")

    def append_message(self, message: str, level: str = "info") -> None:
        """Append a line, coloured by ``level``, unless the level is filtered."""
        try:
            rank = self.LEVELS.index(str(level).strip().lower())
        except ValueError:
            rank = self.LEVELS.index("info")
        if rank < self._threshold:
            return
        color = self.LEVEL_COLORS.get(level)
        text = message if not color else f'<span style="color:{color}">{message}</span>'
        self.appendHtml(text)
```

- [ ] **Step 4: Wire the window**

In `src/python/tik/trigger/ui/main.py`, add these methods to `TriggerWindow`:

```python
    # ------------------------------------------------------- window state
    #: Opaque Qt blobs, kept out of the readable JSON file on purpose.
    STATE_ORG, STATE_APP = "tikworks", "trigger"

    def save_window_state(self) -> None:
        """Store geometry and dock layout as Qt blobs."""
        settings = QtCore.QSettings(self.STATE_ORG, self.STATE_APP)
        settings.setValue("window/geometry", self.saveGeometry())
        settings.setValue("window/state", self.saveState())

    def restore_window_state(self) -> None:
        """Put back whatever the preferences allow, tolerating missing blobs."""
        settings = QtCore.QSettings(self.STATE_ORG, self.STATE_APP)
        if prefs_value("interface", "restore_geometry"):
            blob = settings.value("window/geometry")
            if blob:
                self.restoreGeometry(blob)
        if prefs_value("interface", "restore_dock_layout"):
            blob = settings.value("window/state")
            if blob:
                self.restoreState(blob)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt style
        """Remember the layout on the way out."""
        self.save_window_state()
        super().closeEvent(event)
```

At the end of `__init__`, after `self._sync_menu_state()`, add:

```python
        self.log.set_level(prefs_value("interface", "log_verbosity"))
        self.log.setMaximumBlockCount(prefs_value("interface", "log_max_lines"))
        self.restore_window_state()
```

Extend `_on_prefs_applied` from Task 7 to its full form:

```python
    def _on_prefs_applied(self, changed: list) -> None:
        """Push applied preferences into the widgets that cache them.

        Only settings that a *live* widget holds a copy of need pushing.
        Everything else is read at the point of use and picks the new value
        up on its own, which is why this table stays short.
        """
        if "interface.log_max_lines" in changed:
            self.log.setMaximumBlockCount(prefs_value("interface", "log_max_lines"))
        if "interface.log_verbosity" in changed:
            self.log.set_level(prefs_value("interface", "log_verbosity"))
        if "files.max_recent" in changed:
            del self.recent_files[prefs_value("files", "max_recent") :]
            self._update_recent_menu()
```

Finally, make errors raise the dock. Find `_on_error` and add as its first statement:

```python
        if prefs_value("interface", "log_open_on_error"):
            self.log_dock.show()
            self.log_action.setChecked(True)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `set PYTHONPATH=%CD%/src/python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_prefs_interface.py -v`
Expected: PASS — 8 passed

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/ui/main.py src/python/tik/trigger/ui/widgets.py tests/ui/test_prefs_interface.py
git commit -m "feat(prefs): remember window layout and honour the log preferences"
```

---

### Task 9: Consume the Files & Sessions preferences (recent, browsing, confirmations)

**Files:**
- Modify: `src/python/tik/trigger/ui/main.py` (`__init__`, `_remember`, `_update_recent_menu`, the unsaved-close prompt at `:686` and `:833`), remove `MAX_RECENT` at `:37`
- Test: `tests/ui/test_prefs_files.py`

**Interfaces:**
- Consumes: `prefs.files.*` (Task 3), `prefs_value` (Task 7)
- Produces: `TriggerWindow._load_recent()`, `TriggerWindow._save_recent()`, `TriggerWindow.browse_folder() -> str`

Autosave is Task 10; this task covers the recent list, the remembered folder and the close confirmation.

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_prefs_files.py`:

```python
"""Files & Sessions preferences."""

import pytest


@pytest.fixture
def window(qapp, tmp_path):
    from tik.shared.prefs import PrefStore
    from tik.trigger.config import prefs
    from tik.trigger.ui.main import TriggerWindow

    # Keep the recent list off the developer's real preferences file.
    prefs._resolve()._store = PrefStore("test_trigger", folder=tmp_path)
    made = TriggerWindow()
    yield made
    made.close()


class TestRecentSessions:
    """The recent list persists and respects its length preference."""

    def test_remember_appends_to_the_front(self, window):
        window._remember("D:/one.tr")
        window._remember("D:/two.tr")
        assert window.recent_files[0].endswith("two.tr")

    def test_remember_deduplicates(self, window):
        window._remember("D:/one.tr")
        window._remember("D:/one.tr")
        assert len(window.recent_files) == 1

    def test_list_is_trimmed_to_the_preference(self, window, monkeypatch):
        from tik.trigger.config import prefs

        monkeypatch.setattr(prefs.files, "max_recent", 3)
        for index in range(6):
            window._remember(f"D:/file{index}.tr")
        assert len(window.recent_files) == 3

    def test_remember_persists_to_the_store(self, window):
        from tik.trigger.config import prefs

        window._remember("D:/one.tr")
        assert prefs.store.read()["files.recent_sessions"]

    def test_disabled_preference_stores_nothing(self, window, monkeypatch):
        from tik.trigger.config import prefs

        monkeypatch.setattr(prefs.files, "remember_recent", False)
        window._remember("D:/one.tr")
        assert prefs.store.read().get("files.recent_sessions", []) == []

    def test_load_restores_the_list(self, window):
        from tik.trigger.config import prefs

        prefs.files.recent_sessions = ["D:/kept.tr"]
        window._load_recent()
        assert window.recent_files == ["D:/kept.tr"]


class TestBrowseFolder:
    """Where a file browser opens."""

    def test_prefers_the_last_folder(self, window, monkeypatch):
        from tik.trigger.config import prefs

        monkeypatch.setattr(prefs.files, "last_folder", "D:/last")
        assert window.browse_folder() == "D:/last"

    def test_falls_back_to_the_default_folder(self, window, monkeypatch):
        from tik.trigger.config import prefs

        monkeypatch.setattr(prefs.files, "last_folder", "")
        monkeypatch.setattr(prefs.files, "default_folder", "D:/projects")
        assert window.browse_folder() == "D:/projects"

    def test_ignores_the_last_folder_when_disabled(self, window, monkeypatch):
        from tik.trigger.config import prefs

        monkeypatch.setattr(prefs.files, "remember_last_folder", False)
        monkeypatch.setattr(prefs.files, "last_folder", "D:/last")
        monkeypatch.setattr(prefs.files, "default_folder", "D:/projects")
        assert window.browse_folder() == "D:/projects"

    def test_empty_when_nothing_is_configured(self, window, monkeypatch):
        from tik.trigger.config import prefs

        monkeypatch.setattr(prefs.files, "last_folder", "")
        monkeypatch.setattr(prefs.files, "default_folder", "")
        assert window.browse_folder() == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `set PYTHONPATH=%CD%/src/python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_prefs_files.py -v`
Expected: FAIL — `AttributeError: 'FilesPrefs' object has no attribute 'recent_sessions'`

- [ ] **Step 3: Add the two stored-state fields**

The recent list and the last folder are *state*, not settings: they persist in the same file but never appear in the dialog. `Field(hidden=True)` is exactly that. Add to `FilesPrefs` in `src/python/tik/trigger/config/pages/files.py`:

```python
    recent_sessions = ListField(
        [],
        hidden=True,
        label="Recent sessions",
        help="Session files opened recently. Managed by the window, not edited here.",
    )
    last_folder = StringField(
        "",
        hidden=True,
        label="Last folder",
        help="The folder a file browser last used. Managed by the window.",
    )
```

Update the import line in that file to:

```python
from tik.core.fields import (
    BoolField,
    FieldGroup,
    FileField,
    IntField,
    ListField,
    StringField,
)
```

- [ ] **Step 4: Wire the window**

In `src/python/tik/trigger/ui/main.py`, delete the `MAX_RECENT = 8` constant (line 37).

Replace `_remember` and add its neighbours:

```python
    def _remember(self, path: str) -> None:
        """Put ``path`` at the top of the recent list and persist it."""
        path = str(Path(path))
        if path in self.recent_files:
            self.recent_files.remove(path)
        self.recent_files.insert(0, path)
        del self.recent_files[prefs_value("files", "max_recent") :]
        self._save_recent()
        self._update_recent_menu()

    def _load_recent(self) -> None:
        """Fill the recent list from the preferences file."""
        if not prefs_value("files", "remember_recent"):
            self.recent_files = []
        else:
            stored = prefs_value("files", "recent_sessions") or []
            self.recent_files = [str(item) for item in stored]
            del self.recent_files[prefs_value("files", "max_recent") :]
        self._update_recent_menu()

    def _save_recent(self) -> None:
        """Persist the recent list, unless the user asked us not to."""
        from tik.trigger.config import prefs

        prefs.files.recent_sessions = (
            list(self.recent_files) if prefs_value("files", "remember_recent") else []
        )
        prefs.save()

    def browse_folder(self) -> str:
        """Where a file browser should open."""
        if prefs_value("files", "remember_last_folder"):
            last = prefs_value("files", "last_folder")
            if last:
                return str(last)
        return str(prefs_value("files", "default_folder") or "")

    def _remember_folder(self, path: str) -> None:
        """Store ``path``'s folder as the one browsers reopen in."""
        if not prefs_value("files", "remember_last_folder"):
            return
        from tik.trigger.config import prefs

        prefs.files.last_folder = str(Path(path).parent)
        prefs.save()
```

At the end of `__init__`, after `self.restore_window_state()`, add:

```python
        self._load_recent()
```

In `_remember`, the caller already knows the path, so also record the folder — add `self._remember_folder(path)` as the last line of `_remember`.

Gate the unsaved-close prompts. At **both** line 686 and line 833 (the two `Feedback(self).pop_question(` blocks that ask about unsaved changes), wrap the prompt:

```python
        if not prefs_value("files", "confirm_unsaved_close"):
            answer = True
        else:
            answer = Feedback(self).pop_question(
                ...  # leave the existing arguments exactly as they are
            )
```

Read each call site before editing and keep its existing arguments and its handling of `answer` unchanged — the two prompts differ.

- [ ] **Step 5: Run test to verify it passes**

Run: `set PYTHONPATH=%CD%/src/python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_prefs_files.py -v`
Expected: PASS — 10 passed

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/ui/main.py src/python/tik/trigger/config/pages/files.py tests/ui/test_prefs_files.py
git commit -m "feat(prefs): persist recent sessions, remembered folder and close confirmation"
```

---

### Task 10: Autosave as a recovery sidecar

**Files:**
- Create: `src/python/tik/trigger/ui/autosave.py`
- Modify: `src/python/tik/trigger/ui/main.py` (`__init__`, `_on_prefs_applied`, `open_session`)
- Test: `tests/ui/test_autosave.py`

**Interfaces:**
- Consumes: `prefs.files.autosave`, `prefs.files.autosave_interval` (Task 3)
- Produces: `AutosaveTimer(window, interval_seconds)` with `.start()`, `.stop()`, `.reconfigure()`, `.tick()`; `sidecar_path(session_path) -> Path`; `recoverable(session_path) -> Optional[Path]`

**Autosave never writes the user's own file.** It writes `<name>.tr.autosave` beside it, and only while the session is modified and has a path. A manual save deletes the sidecar. Opening a session whose sidecar is newer offers recovery. This is why the preference's help text promises "your own file is never written without you asking".

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_autosave.py`:

```python
"""Autosave writes a recovery sidecar, never the user's own file."""

import pytest


class TestSidecarPath:
    """Naming."""

    def test_appends_the_suffix(self, tmp_path):
        from tik.trigger.ui.autosave import sidecar_path

        assert sidecar_path(tmp_path / "rig.tr").name == "rig.tr.autosave"

    def test_sits_beside_the_session(self, tmp_path):
        from tik.trigger.ui.autosave import sidecar_path

        assert sidecar_path(tmp_path / "rig.tr").parent == tmp_path


class TestRecoverable:
    """When a sidecar is worth offering."""

    def test_none_when_no_sidecar(self, tmp_path):
        from tik.trigger.ui.autosave import recoverable

        session = tmp_path / "rig.tr"
        session.write_text("{}", encoding="utf-8")
        assert recoverable(session) is None

    def test_none_when_sidecar_is_older(self, tmp_path):
        import os
        import time

        from tik.trigger.ui.autosave import recoverable, sidecar_path

        session = tmp_path / "rig.tr"
        sidecar_path(session).write_text("{}", encoding="utf-8")
        time.sleep(0.01)
        session.write_text("{}", encoding="utf-8")
        os.utime(session, None)
        assert recoverable(session) is None

    def test_found_when_sidecar_is_newer(self, tmp_path):
        import os
        import time

        from tik.trigger.ui.autosave import recoverable, sidecar_path

        session = tmp_path / "rig.tr"
        session.write_text("{}", encoding="utf-8")
        time.sleep(0.01)
        side = sidecar_path(session)
        side.write_text("{}", encoding="utf-8")
        os.utime(side, None)
        assert recoverable(session) == side

    def test_none_for_an_unsaved_session(self):
        from tik.trigger.ui.autosave import recoverable

        assert recoverable("") is None


class FakeWindow:
    """The two things AutosaveTimer asks a window for."""

    def __init__(self, path="", modified=True):
        self.path = path
        self.modified = modified
        self.written = []

    def autosave_target(self):
        return self.path

    def is_modified(self):
        return self.modified

    def write_autosave(self, target):
        self.written.append(target)


class TestAutosaveTimer:
    """Ticking writes only when it should."""

    def test_tick_writes_the_sidecar(self, qapp, tmp_path):
        from tik.trigger.ui.autosave import AutosaveTimer, sidecar_path

        window = FakeWindow(path=str(tmp_path / "rig.tr"))
        AutosaveTimer(window, 300).tick()
        assert window.written == [sidecar_path(tmp_path / "rig.tr")]

    def test_tick_skips_an_unmodified_session(self, qapp, tmp_path):
        from tik.trigger.ui.autosave import AutosaveTimer

        window = FakeWindow(path=str(tmp_path / "rig.tr"), modified=False)
        AutosaveTimer(window, 300).tick()
        assert window.written == []

    def test_tick_skips_a_session_with_no_path(self, qapp):
        from tik.trigger.ui.autosave import AutosaveTimer

        window = FakeWindow(path="")
        AutosaveTimer(window, 300).tick()
        assert window.written == []

    def test_reconfigure_stops_when_disabled(self, qapp, tmp_path, monkeypatch):
        from tik.trigger.config import prefs
        from tik.trigger.ui.autosave import AutosaveTimer

        monkeypatch.setattr(prefs.files, "autosave", False)
        timer = AutosaveTimer(FakeWindow(path=str(tmp_path / "rig.tr")), 300)
        timer.reconfigure()
        assert not timer.isActive()

    def test_reconfigure_starts_when_enabled(self, qapp, tmp_path, monkeypatch):
        from tik.trigger.config import prefs
        from tik.trigger.ui.autosave import AutosaveTimer

        monkeypatch.setattr(prefs.files, "autosave", True)
        monkeypatch.setattr(prefs.files, "autosave_interval", 60)
        timer = AutosaveTimer(FakeWindow(path=str(tmp_path / "rig.tr")), 300)
        timer.reconfigure()
        assert timer.isActive()
        assert timer.interval() == 60000
        timer.stop()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `set PYTHONPATH=%CD%/src/python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_autosave.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tik.trigger.ui.autosave'`

- [ ] **Step 3: Write the implementation**

Create `src/python/tik/trigger/ui/autosave.py`:

```python
"""Periodic recovery copies of the open session.

Autosave never touches the file the user is working on. It writes a sidecar
next to it -- ``rig.tr.autosave`` -- and only while the session is modified
and already has a path. Opening a session whose sidecar is newer than the
session offers recovery; saving the session for real clears the sidecar.

Writing the user's own file on a timer would make an accidental edit
permanent without anyone asking for it, which is exactly the failure autosave
is supposed to prevent.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Union

from tik.shared.ui.Qt import QtCore

LOG = logging.getLogger(__name__)

#: Appended to the session file's full name, so ``rig.tr`` keeps its suffix
#: and the sidecar can never be mistaken for a session by a file browser.
SUFFIX = ".autosave"


def sidecar_path(session_path: Union[str, Path]) -> Path:
    """The recovery file that belongs to ``session_path``."""
    path = Path(session_path)
    return path.with_name(path.name + SUFFIX)


def recoverable(session_path: Union[str, Path]) -> Optional[Path]:
    """The sidecar for ``session_path`` when it is newer than the session.

    Returns None when there is no session path, no sidecar, or the sidecar is
    older -- meaning the user saved after the last autosave and there is
    nothing to recover.
    """
    if not session_path:
        return None
    session = Path(session_path)
    side = sidecar_path(session)
    if not side.is_file():
        return None
    if session.is_file() and side.stat().st_mtime <= session.stat().st_mtime:
        return None
    return side


def clear(session_path: Union[str, Path]) -> None:
    """Delete the sidecar for ``session_path`` if there is one."""
    if not session_path:
        return
    side = sidecar_path(session_path)
    try:
        side.unlink()
    except FileNotFoundError:
        pass
    except OSError:  # noqa: PERF203 - a locked file must not break saving
        LOG.warning("Could not remove the autosave file: %s", side)


class AutosaveTimer(QtCore.QTimer):
    """Writes a recovery sidecar for ``window``'s session on an interval.

    ``window`` must provide ``autosave_target() -> str``,
    ``is_modified() -> bool`` and ``write_autosave(path)``.
    """

    def __init__(self, window, interval_seconds: int = 300) -> None:
        super().__init__(window if isinstance(window, QtCore.QObject) else None)
        self._window = window
        self.setInterval(max(1, int(interval_seconds)) * 1000)
        self.timeout.connect(self.tick)

    def tick(self) -> None:
        """Write the sidecar, if there is anything worth writing."""
        target = self._window.autosave_target()
        if not target or not self._window.is_modified():
            return
        try:
            self._window.write_autosave(sidecar_path(target))
        except Exception:  # noqa: BLE001 - autosave must never interrupt work
            LOG.warning("Autosave failed for %s", target, exc_info=True)

    def reconfigure(self) -> None:
        """Match the timer to the current preferences."""
        from tik.trigger.config import prefs

        self.setInterval(max(1, int(prefs.files.autosave_interval)) * 1000)
        if prefs.files.autosave:
            self.start()
        else:
            self.stop()
```

- [ ] **Step 4: Wire it into the window**

In `src/python/tik/trigger/ui/main.py`, add these methods to `TriggerWindow`:

```python
    # ---------------------------------------------------------- autosave
    def autosave_target(self) -> str:
        """The active session's file path, or ``""`` when it has none."""
        session = self.session
        return str(getattr(session, "file_path", "") or "") if session else ""

    def is_modified(self) -> bool:
        """True when the active session has unsaved changes."""
        view = self.current_view
        return bool(view and view.is_modified())

    def write_autosave(self, target) -> None:
        """Write the active session to ``target`` without changing its path."""
        session = self.session
        if session is not None:
            session.save_as(str(target))
```

Before using `is_modified` and `save_as`, **check the real names** on `SessionView` and `Session` (`src/python/tik/trigger/session.py`, `ui/session_view.py`) and use whatever those classes actually expose — the surrounding save/close code in `main.py` already calls them, so copy from there rather than guessing. `write_autosave` must not mutate the session's own path; if `save_as` does, use the lower-level document write the session's `save` calls.

At the end of `__init__`, after `self._load_recent()`:

```python
        self.autosave = AutosaveTimer(self, prefs_value("files", "autosave_interval"))
        self.autosave.reconfigure()
```

Import it at the top: `from .autosave import AutosaveTimer`.

Add to `_on_prefs_applied`:

```python
        if any(key.startswith("files.autosave") for key in changed):
            self.autosave.reconfigure()
```

In `open_session`, before loading, offer recovery:

```python
        from .autosave import recoverable

        found = recoverable(file_path)
        if found is not None:
            recover = Feedback(self).pop_question(
                "Recover Autosave",
                f"A newer autosave exists for this session:\n{found}\n\n"
                "Open the autosave instead?",
            )
            if recover:
                file_path = str(found)
```

Match `pop_question`'s real signature and its return convention by copying an existing call in the same file. After a successful manual save, call `autosave.clear(path)` — add `from .autosave import clear as clear_autosave` and call it in `save_session` once the write succeeds.

- [ ] **Step 5: Run test to verify it passes**

Run: `set PYTHONPATH=%CD%/src/python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_autosave.py -v`
Expected: PASS — 11 passed

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/ui/autosave.py src/python/tik/trigger/ui/main.py tests/ui/test_autosave.py
git commit -m "feat(prefs): autosave a recovery sidecar beside the session"
```

---

### Task 11: Consume the Guides preferences, migrating off QSettings

**Files:**
- Modify: `src/python/tik/trigger/ui/designer/window.py:145-159`
- Modify: `src/python/tik/trigger/ui/designer/commands.py:291-299,336-360`
- Modify: `tests/ui/test_guide_designer.py:119,178-196`
- Test: `tests/ui/test_prefs_guides.py`

**Interfaces:**
- Consumes: `prefs.guides.*` (Task 3)
- Produces: a one-shot migration from `QSettings designer/*` into the JSON store

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_prefs_guides.py`:

```python
"""Guide authoring preferences, and the migration off QSettings."""

import pytest

from tik.shared.ui.Qt import QtCore


@pytest.fixture
def store(tmp_path):
    """Point the preferences at a throwaway file."""
    from tik.shared.prefs import PrefStore
    from tik.trigger.config import prefs

    made = PrefStore("test_trigger", folder=tmp_path)
    prefs._resolve()._store = made
    return made


class TestMigration:
    """The two live QSettings keys move into the JSON store, once."""

    def test_migrates_auto_sync_false(self, store, monkeypatch):
        from tik.trigger.config import prefs
        from tik.trigger.ui.designer.commands import migrate_designer_settings

        QtCore.QSettings("tikworks", "trigger").setValue("designer/auto_sync", False)
        monkeypatch.setattr(prefs.guides, "auto_sync", True)
        migrate_designer_settings()
        assert prefs.guides.auto_sync is False

    def test_migrates_draw_on_create_false(self, store):
        from tik.trigger.config import prefs
        from tik.trigger.ui.designer.commands import migrate_designer_settings

        QtCore.QSettings("tikworks", "trigger").setValue(
            "designer/draw_on_create", False
        )
        migrate_designer_settings()
        assert prefs.guides.draw_on_create is False

    def test_normalises_qsettings_strings(self, store):
        from tik.trigger.config import prefs
        from tik.trigger.ui.designer.commands import migrate_designer_settings

        # QSettings hands back strings on some platforms.
        QtCore.QSettings("tikworks", "trigger").setValue("designer/auto_sync", "false")
        migrate_designer_settings()
        assert prefs.guides.auto_sync is False

    def test_runs_only_once(self, store):
        from tik.trigger.config import prefs
        from tik.trigger.ui.designer.commands import migrate_designer_settings

        QtCore.QSettings("tikworks", "trigger").setValue("designer/auto_sync", False)
        migrate_designer_settings()
        prefs.guides.auto_sync = True
        migrate_designer_settings()
        assert prefs.guides.auto_sync is True

    def test_no_qsettings_leaves_defaults(self, store):
        from tik.trigger.config import prefs
        from tik.trigger.ui.designer.commands import migrate_designer_settings

        QtCore.QSettings("tikworks", "trigger").remove("designer/auto_sync")
        QtCore.QSettings("tikworks", "trigger").remove("designer/draw_on_create")
        migrate_designer_settings()
        assert prefs.guides.auto_sync is True
        assert prefs.guides.draw_on_create is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `set PYTHONPATH=%CD%/src/python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_prefs_guides.py -v`
Expected: FAIL — `ImportError: cannot import name 'migrate_designer_settings'`

- [ ] **Step 3: Add the migration and switch the reads**

Add to `src/python/tik/trigger/config/pages/guides.py`, inside `GuidesPrefs`:

```python
    migrated_from_qsettings = BoolField(
        False,
        hidden=True,
        label="Migrated",
        help="Set once the old QSettings designer toggles have been imported.",
    )
```

Add to `src/python/tik/trigger/ui/designer/commands.py`, at module level:

```python
def _as_bool(value, fallback: bool) -> bool:
    """QSettings hands back strings on some platforms; normalise rather than cast."""
    if value is None:
        return fallback
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in ("false", "0", "")


def migrate_designer_settings() -> None:
    """Import the old ``QSettings`` designer toggles, once.

    The Designer used to persist Auto Sync and Draw New Modules under
    ``QSettings("tikworks", "trigger")``. Both are preferences now. A rigger
    who turned Auto Sync off would be annoyed to find it back on, so the old
    values are read once and written into the preferences file.
    """
    from tik.trigger.config import prefs

    if prefs.guides.migrated_from_qsettings:
        return
    settings = QtCore.QSettings("tikworks", "trigger")
    prefs.guides.auto_sync = _as_bool(
        settings.value("designer/auto_sync"), prefs.guides.auto_sync
    )
    prefs.guides.draw_on_create = _as_bool(
        settings.value("designer/draw_on_create"), prefs.guides.draw_on_create
    )
    prefs.guides.migrated_from_qsettings = True
    prefs.save()
```

In `commands.py`, replace the two `QSettings(...).setValue(...)` writes. In `set_draw_on_create` (around line 297):

```python
        self.guides.draw_on_create = bool(on)
        from tik.trigger.config import prefs

        prefs.guides.draw_on_create = bool(on)
        prefs.save()
```

In `set_auto_sync` (around line 360), replace the `QSettings` line with:

```python
        from tik.trigger.config import prefs

        prefs.guides.auto_sync = bool(on)
        prefs.save()
```

In `src/python/tik/trigger/ui/designer/window.py`, replace the restore block at lines 145-159 with:

```python
        # Restored via _apply_auto_sync, not set_auto_sync: the latter runs a
        # full sync(), which captures, and construction must not.
        from tik.trigger.config import prefs
        from .commands import migrate_designer_settings

        migrate_designer_settings()
        self._apply_auto_sync(bool(prefs.guides.auto_sync))
        self.guides.draw_on_create = bool(prefs.guides.draw_on_create)
```

- [ ] **Step 4: Gate the two confirmations**

In `commands.py`, the `pop_question` at line 268 is the Delete All Modules prompt. Wrap it:

```python
        from tik.trigger.config import prefs

        if not prefs.guides.confirm_delete_all:
            answer = True
        else:
            answer = Feedback(self).pop_question(
                ...  # leave the existing arguments exactly as they are
            )
```

In `main.py`, do the same for `reset_scene` using `prefs.guides.confirm_reset_scene`. Read each site first and preserve its arguments and its handling of `answer`.

- [ ] **Step 5: Update the tests that assert the old storage**

In `tests/ui/test_guide_designer.py`, the assertions at lines 119 and 183-196 read and write `QSettings("tikworks","trigger").value("designer/auto_sync")`. Replace each with the preference:

```python
    from tik.trigger.config import prefs

    assert prefs.guides.auto_sync is False
```

and for the setup at line 183, set `prefs.guides.auto_sync = False` plus `prefs.guides.migrated_from_qsettings = True` (so the migration does not overwrite the value the test just set). Read the surrounding test before editing so its intent survives the change.

- [ ] **Step 6: Run tests to verify they pass**

Run: `set PYTHONPATH=%CD%/src/python;%PYTHONPATH% && set TIK_TESTS_NO_MAYA=1 && set QT_QPA_PLATFORM=offscreen && mayapy -m pytest tests/ui/test_prefs_guides.py tests/ui/test_guide_designer.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/ui/designer src/python/tik/trigger/config/pages/guides.py src/python/tik/trigger/ui/main.py tests/ui/test_prefs_guides.py tests/ui/test_guide_designer.py
git commit -m "feat(prefs): migrate the designer toggles off QSettings and gate confirmations"
```

---

### Task 12: Cleanup sweep

**Files:**
- Modify: `CLAUDE.md`, `AI/coding_rules.md`
- Delete: any orphan found by the sweep

No new behaviour. This task proves nothing superseded was left behind (spec §9).

- [ ] **Step 1: Sweep for dead symbols**

Run each of these from the repo root. Every one must return **no hits** outside `docs/superpowers/specs/`:

```bash
grep -rn "trigger_settings" --include=*.py src tests
grep -rn "FACTORY_DEFAULTS" --include=*.py src tests
grep -rn "SETTINGS_FILE_NAME" --include=*.py src tests
grep -rn "MAX_RECENT" --include=*.py src/python/tik/trigger/ui/main.py
grep -rn "debug_mode" --include=*.py src tests
grep -rn "mirror_mapping\|rig_build\|default_units\|guide_display" --include=*.py src tests
grep -rn "from tik.trigger.actions.script.script import editor_command" --include=*.py src tests
```

Note `SearchPalette.MAX_RECENT` in `ui/palette.py` is a *different* constant (the palette's recent-entries count) and must survive — scope the `MAX_RECENT` grep to `main.py` as written above.

Fix anything that turns up, then re-run.

- [ ] **Step 2: Sweep for QSettings**

```bash
grep -rn "QSettings" --include=*.py src tests
```

Expected hits only in: `ui/main.py` (the geometry blobs), `ui/designer/commands.py` (the one-shot migration), `tests/ui/conftest.py` (the sandbox, which stays), `tests/ui/test_prefs_guides.py` (the migration tests), and `tik/vendor/Qt/__init__.py` (the vendored name list). Anything else is an orphan.

- [ ] **Step 3: Remove stale bytecode**

```bash
find src/python/tik -name "__pycache__" -type d -prune -exec rm -rf {} +
```

- [ ] **Step 4: Verify the whole suite**

```bash
make lint
make tests-unit
make tests-ui
```

All three must pass. Do not proceed past a failure — fix it.

- [ ] **Step 5: Update the project docs**

In `CLAUDE.md`, add to the **tik.trigger** status paragraph, after the sentence about the script action:

```
User preferences live in `tik/shared/prefs` (a JSON store under `~/TikWorks`,
declarative pages built on `tik.core.fields.Schema`, a page registry) and are
edited from **File > Settings...**. Adding a setting is one field line in
`tik/trigger/config/pages/`. **A preference can never change a rig**: the
build path may not import the preferences packages at all, enforced by
`tests/unit/test_import_boundaries.py`.
```

Add to the **Quick Rules** list:

```
6. **Preferences never change the rig** - only `tik/trigger/ui` may read
   preferences. Given the same `.tr`, two artists build the same result.
```

Add the spec to the design-specs list:
`docs/superpowers/specs/2026-09-06-settings-and-preferences-design.md` (the
preferences system: the shared spine, the guarantee and its enforcement, the
dialog).

In `AI/coding_rules.md`, add the same guarantee under the layering rules, in
that file's existing voice.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore(prefs): sweep the superseded settings code and document the rule"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §4.1 shared spine (`store`, `page`, `registry`) | 1, 2 |
| §4.2 the dialog | 6 |
| §4.3 Trigger's pages, one-field-line expandability, `help` rule | 3 |
| §3 the guarantee and its enforcement | 4 |
| §5 storage split (JSON vs QSettings blobs) | 8 |
| §6 inventory — Interface | 8 |
| §6 inventory — Guides | 11 |
| §6 inventory — Files & Sessions | 9, 10 |
| §6 inventory — External Tools | 4 |
| §7 dialog shape, §7.1 search, §7.2 apply semantics | 5, 6 |
| §7.3 applied dispatch | 7, 8 |
| §7.4 naming hazard | Global Constraints |
| §8 migration | 11 (QSettings), 3 (old file dropped) |
| §9 cleanup | 12 |
| §10 testing | every task |

**Type consistency:** `PrefStore.read/write` (Task 1) is used verbatim by `Preferences` (Task 2). `Preferences.snapshot/restore/changed_keys/reset_page/save/store` (Task 2) are used verbatim by `PrefsDialog` (Task 6) and the tests in Tasks 9 and 11. `FormBuilder.set_visible_fields` (Task 5) is called in Task 6. `prefs_value(page, field)` (Task 7) is used in Tasks 8, 9 and 10. Field names declared in Task 3 are the exact strings used in Tasks 7–11 and in the `changed` keys.

**Known soft spots, flagged for the implementer rather than guessed:**

- Task 7's `window` fixture in `tests/ui/test_menus.py` — follow the file's existing construction rather than adding a second fixture.
- Task 9 and 11's `pop_question` wrapping — the call sites differ in arguments and in how they read `answer`; read each before editing.
- Task 10's `autosave_target` / `is_modified` / `write_autosave` — the real `Session` and `SessionView` method names must be copied from the neighbouring save/close code in `main.py`, and `write_autosave` must not mutate the session's own path.
