# Version Control Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give tik.trigger a documented version control contract (provider + host + publish set + publish actions + external plugins + UI surface), and implement tik_manager4 against it as `dcc/trigger3` in the tik_manager4 repository.

**Architecture:** A pure `PublishSet` in `tik/trigger/core` collects what a session needs and writes deduplicated bundles through a content-addressed store. A `PublishAction` base runs at the tail of Build & Publish and hands the set to a `deliver` method; the generic `publish` action writes a versioned folder. `tik/trigger/vcs` holds the `VersionControl` provider contract, its registry, and the `host` object the outside world drives. Everything a VCS adds to the UI is additive and appears only when a provider is active. tik_manager4's side is an external Trigger plugin discovered through `TRIGGER_PLUGIN_PATH`.

**Tech Stack:** Python 3.10+, Maya 2024+ (`mayapy` for tests), Qt through `tik.shared.ui.Qt`, stdlib only (hashlib, json, shutil). tik_manager4 code lives in `D:\dev\tik_manager4` on branch `TW-trigger3-integration-test`.

**Spec:** `docs/superpowers/specs/2026-09-08-version-control-scaffold-design.md`

## Global Constraints

- Two repositories. Tikworks work happens in `D:\dev\tikworks` on branch `TW-29-trigger-version-control-scaffold`. tik_manager4 work happens in `D:\dev\tik_manager4` on branch `TW-trigger3-integration-test`. Never touch `D:\dev\tik_manager4\tik_manager4\dcc\trigger` (the old integration) or `D:\dev\trigger`.
- `tik/trigger/core` stays pure Python: no Maya, no Qt, no `tik.trigger.actions`, no preferences packages (`tests/unit/test_import_boundaries.py`).
- `tik.trigger.vcs` never imports `tik.trigger.config` or `tik.shared.prefs`; only `tik.trigger.ui`, `tik.trigger.actions.publish` and external plugins may import `tik.trigger.vcs`. `PublishAction` and the generic `publish` action do not import it.
- Nothing in tikworks imports `tik_manager4`.
- No third-party dependencies. Raw `maya.cmds` is allowed inside an action's `run` for scene file operations only (as `import_asset` already does).
- Every dialog goes through `tik.shared.ui.feedback.Feedback` (`tests/unit/test_dialog_boundaries.py`).
- Every action ships `<name>.svg` beside its `.py` (rules in `AI/icon_rules.md`; an action icon is full colour, never tinted, 24x24 viewBox).
- Tests: unit and integration run under `mayapy` (`make tests-unit`, `make tests-integration`); UI tests run with `TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen mayapy -m pytest tests/ui -q`. From PowerShell, set `$env:PYTHONPATH="D:\dev\tikworks\src\python"` first. Lint with `make lint` (ruff) before every commit.
- Commit messages end with the Co-Authored-By / Claude-Session trailer given in the session.
- The store is **flat**: `<store>/<sha1>_<name>`, not a two-character sub-folder as the spec first said. A nested referenced `.tr` is itself rewritten and stored, and its own paths must resolve relative to wherever it lands; with a flat store every stored file is a sibling, so the rewrite is deterministic before the hash is known. Task 4 updates the spec sentence.

---

## File map

Tikworks (create unless noted):

| File | Responsibility |
|---|---|
| `src/python/tik/core/fields.py` (modify) | `FileField(kind=)` |
| `src/python/tik/trigger/core/kinds.py` | the kind vocabulary and extension mapping (pure) |
| `src/python/tik/trigger/core/action.py` (modify) | `dependencies(ctx)`, `products(ctx)`, `file_fields()`; drop `save_from_scene` |
| `src/python/tik/trigger/core/publish_set.py` | `Artifact`, `Dependency`, `PublishSet`, `Store`, `write_bundle`, `clean` |
| `src/python/tik/trigger/core/exceptions.py` (modify) | `VersionControlError` |
| `src/python/tik/trigger/core/discovery.py` (modify) | `plugin_paths()`, `add_plugin_path()` |
| `src/python/tik/trigger/__init__.py` (modify) | `load_plugins` walks external paths; `add_plugin_path`; `VERSION` |
| `src/python/tik/trigger/vcs/__init__.py` | registry, `active()`, `set_preferred()`, `host`, headless verbs |
| `src/python/tik/trigger/vcs/provider.py` | `VersionControl`, `Context` |
| `src/python/tik/trigger/vcs/host.py` | `Host` |
| `src/python/tik/trigger/vcs/kinds.py` | re-export of `core.kinds` |
| `src/python/tik/trigger/vcs/folder.py` | `FolderProvider` reference implementation |
| `src/python/tik/trigger/actions/publish/publish.py` + `publish.svg` | `PublishAction`, `Publish` |
| `src/python/tik/trigger/config/pages/vcs.py` | the `vcs.provider` preference |
| `src/python/tik/shared/ui/versioned_field.py` (modify) | optional VCS button |
| `src/python/tik/shared/ui/fields.py` (modify) | `FormBuilder(file_vcs=)` |
| `src/python/tik/shared/ui/status.py` (modify) | `set_click`, `set_color` |
| `src/python/tik/trigger/ui/vcs_ui.py` | every Trigger-specific VCS UI piece |
| `src/python/tik/trigger/ui/settings_panel.py`, `session_view.py`, `main.py`, `designer/commands.py` (modify) | wiring |
| `docs/trigger/integrating-version-control.md` | the integrator's guide |
| `tests/unit/test_publish_set_trigger.py`, `test_vcs_trigger.py`, `test_plugin_path_trigger.py`, `test_integration_guide.py`, `tests/integration/trigger/test_publish_action_trigger.py`, `tests/ui/test_vcs_ui.py` | tests |

tik_manager4 (all new except `dcc/__init__.py`):

| File | Responsibility |
|---|---|
| `tik_manager4/dcc/__init__.py` (modify) | `"trigger3": [".tr"]` + one `elif` |
| `tik_manager4/dcc/trigger3/main.py` | `Dcc` over Trigger's host |
| `tik_manager4/dcc/trigger3/{extract,ingest,validate,extension}/__init__.py` | collectors (copied from `_TEMPLATE`) |
| `tik_manager4/dcc/trigger3/extract/{source,rig,guides}.py` | elements |
| `tik_manager4/dcc/trigger3/ingest/{source,guides}.py` | loading |
| `tik_manager4/dcc/trigger3/plugins/tik_manager/tik_manager.py` + `.svg` | the provider |
| `tik_manager4/dcc/trigger3/picker.py` | the version picker dialog |
| `tik_manager4/dcc/trigger3/plugins/tik_publish/tik_publish.py` + `.svg` | the publish action |
| `tik_manager4/dcc/trigger3/setup/how-to-install.txt`, `setup/icons/trigger3.png` | install |
| `tests/test_trigger3.py` | tests (run under mayapy with tikworks on PYTHONPATH) |

---

### Task 1: Kinds vocabulary and `FileField(kind=)`

**Files:**
- Create: `src/python/tik/trigger/core/kinds.py`
- Modify: `src/python/tik/core/fields.py:424-458`
- Modify: `src/python/tik/trigger/core/__init__.py` (export `kinds`)
- Test: `tests/unit/test_kinds_trigger.py`

**Interfaces:**
- Produces: `tik.trigger.core.kinds` with constants `SESSION="session"`, `GUIDES="guides"`, `RIG="rig"`, `SCRIPT="script"`, `MODEL="model"`, `FILE="file"`, `EXTENSIONS: dict[str, tuple[str, ...]]`, `ORDER: tuple[str, ...]`, `kind_for(extensions, declared="") -> str`.
- Produces: `FileField.kind: str` (default `""`), included in `to_schema()`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_kinds_trigger.py
"""The kind vocabulary a VCS provider maps, and how a field declares one."""

from tik.core.fields import FileField
from tik.trigger.core import kinds


def test_declared_kind_wins_over_extensions():
    assert kinds.kind_for([".mb"], declared="rig") == "rig"


def test_extensions_map_in_declared_order():
    assert kinds.kind_for([".tr"]) == kinds.SESSION
    assert kinds.kind_for([".trg"]) == kinds.GUIDES
    assert kinds.kind_for([".py"]) == kinds.SCRIPT
    # .mb is both a model and a rig; a bare field is more likely a model
    assert kinds.kind_for([".ma", ".mb", ".fbx"]) == kinds.MODEL
    assert kinds.kind_for([".mb"]) == kinds.MODEL


def test_unknown_extensions_are_a_generic_file():
    assert kinds.kind_for([".json"]) == kinds.FILE
    assert kinds.kind_for([]) == kinds.FILE


def test_file_field_carries_its_kind_into_the_schema():
    field = FileField("", extensions=[".mb"], kind="rig")
    field.name = "scene"
    assert field.kind == "rig"
    assert field.to_schema()["kind"] == "rig"
    plain = FileField("", extensions=[".py"])
    plain.name = "file_path"
    assert plain.kind == ""
    assert plain.to_schema()["kind"] == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mayapy -m pytest tests/unit/test_kinds_trigger.py -q`
Expected: FAIL with `ImportError: cannot import name 'kinds'` / `TypeError: unexpected keyword 'kind'`.

- [ ] **Step 3: Write `kinds.py`**

```python
# src/python/tik/trigger/core/kinds.py
"""The kind vocabulary shared by publishing, browsing and the publish set.

A kind is a plain string a version control provider maps to its own element
types. Actions may add their own (``"weights"``); a provider that does not
know a kind treats it as a generic file.
"""

from __future__ import annotations

from typing import Sequence

SESSION = "session"
GUIDES = "guides"
RIG = "rig"
SCRIPT = "script"
MODEL = "model"
FILE = "file"

#: The extensions each kind usually carries, for fields that declare none.
EXTENSIONS: dict[str, tuple[str, ...]] = {
    SESSION: (".tr",),
    GUIDES: (".trg",),
    SCRIPT: (".py",),
    MODEL: (".ma", ".mb", ".fbx", ".obj", ".abc", ".usd"),
    RIG: (".ma", ".mb"),
}

#: Resolution order when an extension belongs to more than one kind: a bare
#: ``.mb`` field is more likely a model an action imports than a rig.
ORDER: tuple[str, ...] = (SESSION, GUIDES, SCRIPT, MODEL, RIG)


def kind_for(extensions: Sequence[str], declared: str = "") -> str:
    """``declared`` when given; else the first kind sharing an extension; else FILE."""
    if declared:
        return declared
    wanted = {ext if ext.startswith(".") else f".{ext}" for ext in extensions}
    for kind in ORDER:
        if wanted & set(EXTENSIONS[kind]):
            return kind
    return FILE
```

- [ ] **Step 4: Add `kind` to `FileField`**

In `src/python/tik/core/fields.py`, change the `FileField.__init__` signature and body and `to_schema`:

```python
    def __init__(
        self,
        default: str = "",
        *,
        extensions: Sequence[str] = (),
        mode: str = "open",
        kind: str = "",
        **kwargs,
    ) -> None:
        if mode not in ("open", "save", "dir"):
            raise ValueError("mode must be 'open', 'save' or 'dir'")
        self.extensions = [
            ext if ext.startswith(".") else f".{ext}" for ext in extensions
        ]
        self.mode = mode
        #: What the file *is* to a version control system (``"script"``,
        #: ``"guides"``); empty means "work it out from the extensions".
        self.kind = kind
        super().__init__(default, **kwargs)
```

and in `to_schema` add `data["kind"] = self.kind` after the `mode` line.

Export `kinds` from `src/python/tik/trigger/core/__init__.py`: change `from . import icons, versioning` to `from . import icons, kinds, versioning` and add `"kinds"` to `__all__`.

- [ ] **Step 5: Run the tests and lint**

Run: `mayapy -m pytest tests/unit/test_kinds_trigger.py tests/unit/test_fields.py -q` then `make lint`
Expected: PASS, lint clean.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/core/fields.py src/python/tik/trigger/core/kinds.py src/python/tik/trigger/core/__init__.py tests/unit/test_kinds_trigger.py
git commit -m "Add the file kind vocabulary and FileField(kind=)"
```

---

### Task 2: External plugin paths

**Files:**
- Modify: `src/python/tik/trigger/core/discovery.py`
- Modify: `src/python/tik/trigger/__init__.py:34-40`
- Test: `tests/unit/test_plugin_path_trigger.py`

**Interfaces:**
- Produces: `tik.trigger.core.discovery.PLUGIN_PATH_VAR = "TRIGGER_PLUGIN_PATH"`, `discovery.plugin_paths() -> list[Path]` (env var split on `os.pathsep` plus paths added at runtime, deduplicated, existing folders only), `discovery.add_plugin_path(path) -> None`, `discovery.clear_plugin_paths() -> None`, `discovery.discover_external(paths) -> list[str]`.
- Produces: `tik.trigger.add_plugin_path(path)` re-export; `tik.trigger.load_plugins()` also discovers external paths.

External layout: `<root>/<name>/<name>.py`. The root is put on `sys.path` if not already there and the module is imported as `<name>.<name>` (each plugin folder is its own top-level package; an `__init__.py` is created in memory by importing the folder as a namespace package, so none is required on disk).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_plugin_path_trigger.py
"""External plugins: a folder on TRIGGER_PLUGIN_PATH registers like a built-in."""

from __future__ import annotations

import sys
import textwrap

import pytest

from tik.trigger.core import discovery, registry

ACTION = """
from tik.trigger.core import Action, StringField, register_action


@register_action("{name}", category="utility")
class Plugin(Action):
    label = "External"
    note = StringField("")

    def run(self, ctx):
        return None
"""


@pytest.fixture(autouse=True)
def _sandbox(monkeypatch):
    actions = dict(registry._ACTIONS)
    modules = list(sys.modules)
    discovery.clear_plugin_paths()
    monkeypatch.delenv(discovery.PLUGIN_PATH_VAR, raising=False)
    try:
        yield
    finally:
        registry._ACTIONS.clear()
        registry._ACTIONS.update(actions)
        for name in list(sys.modules):
            if name not in modules and name.startswith("ext_"):
                del sys.modules[name]
        discovery.clear_plugin_paths()


def _plugin(root, name, source=ACTION):
    folder = root / name
    folder.mkdir(parents=True)
    (folder / f"{name}.py").write_text(
        textwrap.dedent(source.format(name=name)), encoding="utf-8"
    )
    return folder


def test_env_var_paths_are_discovered(tmp_path, monkeypatch):
    _plugin(tmp_path, "ext_alpha")
    monkeypatch.setenv(discovery.PLUGIN_PATH_VAR, str(tmp_path))
    assert tmp_path in discovery.plugin_paths()
    imported = discovery.discover_external(discovery.plugin_paths())
    assert imported == ["ext_alpha.ext_alpha"]
    assert registry.is_action_registered("ext_alpha")


def test_add_plugin_path_is_deduplicated_and_skips_missing(tmp_path):
    discovery.add_plugin_path(tmp_path)
    discovery.add_plugin_path(str(tmp_path))
    discovery.add_plugin_path(tmp_path / "nope")
    assert discovery.plugin_paths() == [tmp_path]


def test_a_broken_plugin_does_not_stop_the_others(tmp_path):
    _plugin(tmp_path, "ext_bad", source="import nothing_of_the_sort\n")
    _plugin(tmp_path, "ext_good")
    discovery.add_plugin_path(tmp_path)
    imported = discovery.discover_external(discovery.plugin_paths())
    assert imported == ["ext_good.ext_good"]
    assert registry.is_action_registered("ext_good")


def test_load_plugins_walks_external_paths(tmp_path):
    import tik.trigger as trigger

    _plugin(tmp_path, "ext_loaded")
    trigger.add_plugin_path(tmp_path)
    trigger.load_plugins()
    assert registry.is_action_registered("ext_loaded")
```

- [ ] **Step 2: Run to verify failure**

Run: `mayapy -m pytest tests/unit/test_plugin_path_trigger.py -q`
Expected: FAIL with `AttributeError: module ... has no attribute 'clear_plugin_paths'`.

- [ ] **Step 3: Implement in `discovery.py`**

Append to `src/python/tik/trigger/core/discovery.py`:

```python
import os
import sys

#: ``os.pathsep``-separated folders, each holding ``<name>/<name>.py`` plugins.
PLUGIN_PATH_VAR = "TRIGGER_PLUGIN_PATH"

_added: list[Path] = []


def add_plugin_path(path) -> None:
    """Register ``path`` as an external plugin root for the next ``load_plugins``."""
    resolved = Path(path)
    if resolved not in _added:
        _added.append(resolved)


def clear_plugin_paths() -> None:
    """Forget every path added at runtime (tests)."""
    _added.clear()


def plugin_paths() -> list[Path]:
    """Existing external plugin roots: the env var first, then ``add_plugin_path``."""
    found: list[Path] = []
    raw = os.environ.get(PLUGIN_PATH_VAR, "")
    for item in raw.split(os.pathsep) if raw else []:
        if item.strip():
            found.append(Path(item.strip()))
    found.extend(_added)
    unique: list[Path] = []
    for path in found:
        if path.is_dir() and path not in unique:
            unique.append(path)
    return unique


def discover_external(paths: Iterable[Path]) -> list[str]:
    """Import ``<root>/<name>/<name>.py`` for every root; return module names.

    Each plugin folder is imported as its own top-level package, so the root
    goes on ``sys.path``. A plugin that fails to import is logged and skipped.
    """
    imported: list[str] = []
    for root in paths:
        root_str = str(root)
        if root_str not in sys.path:
            sys.path.append(root_str)
        for folder in sorted(Path(root).iterdir()):
            if not folder.is_dir() or folder.name.startswith("_"):
                continue
            if not (folder / f"{folder.name}.py").exists():
                continue
            module_name = f"{folder.name}.{folder.name}"
            try:
                module = importlib.import_module(module_name)
            except Exception as error:  # noqa: BLE001 - keep discovering others
                logger.error("Failed to import plugin %s: %s", module_name, error)
                continue
            imported.append(module_name)
            _ensure_registered(module)
            _apply_defaults(module, folder / "defaults.json")
    return imported
```

(`import os`, `import sys` go at the top with the other imports.)

- [ ] **Step 4: Wire `load_plugins` and the re-export**

In `src/python/tik/trigger/__init__.py` replace `load_plugins`:

```python
VERSION = "0.2.0"


def load_plugins() -> None:
    """Discover the built-in modules and actions, then every external plugin root."""
    import tik.trigger.actions as actions_pkg
    import tik.trigger.modules as modules_pkg
    from tik.trigger.core import discovery

    discovery.discover(modules_pkg.__name__, modules_pkg.__path__)
    discovery.discover(actions_pkg.__name__, actions_pkg.__path__)
    discovery.discover_external(discovery.plugin_paths())


def add_plugin_path(path) -> None:
    """Register an external plugin root (``<root>/<name>/<name>.py``)."""
    from tik.trigger.core import discovery

    discovery.add_plugin_path(path)
```

Add `"add_plugin_path"` and `"VERSION"` to `__all__`. In `src/python/tik/trigger/ui/main.py` replace `VERSION = "0.2.0"` with `from tik.trigger import VERSION` (keep the name used by the window).

- [ ] **Step 5: Run tests and lint**

Run: `mayapy -m pytest tests/unit/test_plugin_path_trigger.py tests/unit/test_discovery_trigger.py -q` and `make lint`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/core/discovery.py src/python/tik/trigger/__init__.py src/python/tik/trigger/ui/main.py tests/unit/test_plugin_path_trigger.py
git commit -m "Discover external plugins from TRIGGER_PLUGIN_PATH"
```

---

### Task 3: Action `dependencies` and `products`

**Files:**
- Modify: `src/python/tik/trigger/core/action.py`
- Create: `src/python/tik/trigger/core/publish_set.py` (the `Artifact` dataclass only; the rest comes in Task 4)
- Test: `tests/unit/test_action_files_trigger.py`

**Interfaces:**
- Produces: `Artifact(kind: str, path: Path, label: str = "")` frozen dataclass in `tik.trigger.core.publish_set`.
- Produces on `Action`: `file_fields() -> dict[str, FileField]` classmethod (every `FileField` whose `mode != "dir"`), `dependencies(ctx) -> list[Path]` (resolved values of those fields, non-empty only), `products(ctx) -> list[Artifact]` (default `[]`), `has_products()` classmethod (True when a subclass overrides `products`). `save_from_scene` is removed.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_action_files_trigger.py
"""What an action declares it needs (dependencies) and writes (products)."""

from pathlib import Path

from tik.trigger.core import Action, ActionContext, FileField, StringField
from tik.trigger.core.publish_set import Artifact


class Uses(Action):
    script = FileField("", extensions=[".py"], kind="script")
    folder = FileField("", mode="dir")
    name = StringField("")


class Writes(Uses):
    def products(self, ctx):
        return [Artifact("weights", ctx.resolve("weights/arm.json"))]


def test_file_fields_exclude_directories():
    assert list(Uses.file_fields()) == ["script"]


def test_dependencies_are_the_resolved_non_empty_file_fields(tmp_path):
    ctx = ActionContext(base_dir=str(tmp_path))
    assert Uses({"script": ""}).dependencies(ctx) == []
    assert Uses({"script": "scripts/a.py"}).dependencies(ctx) == [
        tmp_path / "scripts" / "a.py"
    ]


def test_products_default_to_nothing_and_subclasses_are_detected(tmp_path):
    ctx = ActionContext(base_dir=str(tmp_path))
    assert Uses().products(ctx) == []
    assert Uses.has_products() is False
    assert Writes.has_products() is True
    (product,) = Writes().products(ctx)
    assert product.kind == "weights" and product.path == Path(tmp_path, "weights/arm.json")


def test_save_from_scene_is_gone():
    assert not hasattr(Action, "save_from_scene")
```

- [ ] **Step 2: Run to verify failure**

Run: `mayapy -m pytest tests/unit/test_action_files_trigger.py -q`
Expected: FAIL (`publish_set` missing, `file_fields` missing).

- [ ] **Step 3: Create `publish_set.py` with `Artifact`**

```python
# src/python/tik/trigger/core/publish_set.py
"""What a session needs to be published: artifacts, dependencies, bundles.

Pure Python. Knows files and hashes; never Maya, Qt or a provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Artifact:
    """One file a publish carries as a named element."""

    kind: str
    path: Path
    label: str = ""
```

- [ ] **Step 4: Replace `save_from_scene` on `Action`**

In `src/python/tik/trigger/core/action.py` delete `save_from_scene` and add, after `run`:

```python
    # ------------------------------------------------------------ files
    @classmethod
    def file_fields(cls) -> dict:
        """Every ``FileField`` naming a file (directories are not dependencies)."""
        return {
            name: field_obj
            for name, field_obj in cls.fields().items()
            if field_obj.type_name == "file" and getattr(field_obj, "mode", "") != "dir"
        }

    def dependencies(self, ctx: ActionContext) -> list[Path]:
        """Files this action needs to build, absolute.

        The default is every non-empty file field resolved against the
        session folder. Override when the files are not fields.
        """
        found: list[Path] = []
        for name in self.file_fields():
            value = getattr(self, name)
            if value:
                found.append(ctx.resolve(value))
        return found

    def products(self, ctx: ActionContext) -> list:
        """Files this action writes during a run and wants published as elements.

        Returns ``Artifact`` objects. An action that captures scene data
        (weights, shapes) writes it here and returns what it wrote.
        """
        return []

    @classmethod
    def has_products(cls) -> bool:
        """True when a subclass overrides ``products``."""
        return cls.products is not Action.products
```

- [ ] **Step 5: Run tests and lint; run the whole unit suite once**

Run: `mayapy -m pytest tests/unit/test_action_files_trigger.py -q`, then `mayapy tests/unit/invoke.py -q`, then `make lint`
Expected: PASS (grep `save_from_scene` across `src/` and `tests/` returns nothing).

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/core/action.py src/python/tik/trigger/core/publish_set.py tests/unit/test_action_files_trigger.py
git commit -m "Actions declare their dependencies and products"
```

---

### Task 4: The publish set, the store and bundles

**Files:**
- Modify: `src/python/tik/trigger/core/publish_set.py`
- Modify: `docs/superpowers/specs/2026-09-08-version-control-scaffold-design.md` (the store layout sentence, section 5)
- Test: `tests/unit/test_publish_set_trigger.py`

**Interfaces (all in `tik.trigger.core.publish_set`):**

```python
MANIFEST = "manifest.json"
STORE_DIR = "_store"
INDEX = "index.json"           # the store's (size, mtime) -> hash cache

@dataclass(frozen=True)
class Dependency:
    path: Path        # absolute
    original: str     # the string as written in its document
    owner: str        # action path, "guides/<ref_id>", or "<owner>/…" for nested
    external: bool    # True when outside its session folder (absolute, not copied)

@dataclass
class PublishSet:
    session: Path                 # the .tr path (may not exist on disk yet)
    base_dir: Path
    document: Document
    artifacts: list[Artifact]     # session, guides, rig (when given), products
    dependencies: list[Dependency]
    name -> str                   # session.stem
    @classmethod collect(session_file, document, *, rig=None, guides=None, products=()) -> PublishSet

def is_external(path: Path, base_dir: Path) -> bool
def collect_dependencies(document, base_dir, owner_prefix="", seen=None) -> list[Dependency]

class Store:
    root: Path
    put(path: Path) -> Path            # copies once; returns the stored file
    put_bytes(data: bytes, name: str) -> Path
    hash_file(path: Path) -> str       # sha1, cached by (size, mtime) in index.json
    files() -> list[Path]

def relative(target: Path, from_dir: Path) -> str   # posix relpath
def rewrite_document(document, base_dir, store, location, entries, owner="") -> dict
def write_bundle(publish_set, target, store_root=None) -> Path   # returns target
def clean(store_root, bundle_roots) -> list[Path]   # removed files
```

`write_bundle` writes: the rewritten `.tr` as `<name>.tr`, every other artifact copied under its own file name, `manifest.json`, and fills the store. `store_root` defaults to `target.parent / STORE_DIR`. The manifest is:

```json
{"session": "hero.tr", "artifacts": [{"kind": "rig", "path": "hero_rig.mb", "label": ""}],
 "dependencies": [{"owner": "scripts/a", "original": "scripts/a.py", "hash": "…", "size": 12,
                   "store": "../_store/<hash>_a.py", "external": false}]}
```

Dependency discovery walks `document.walk(BUILD)` for enabled nodes, instantiates the registered action with `node.settings`, and calls `dependencies(ActionContext(base_dir=..., path=...))`. Unregistered types are skipped with a log line. A node of type `reference` recurses: the referenced `.tr` (resolved by `versioning.resolve(base/settings["file"], settings.get("version","latest"))`) is a dependency, and its own dependencies follow with `owner_prefix = "<path>/"`. `document.guides.references` (`ModuleReference.file`/`.version`) recurse the same way with owner `guides/<ref_id>`. `seen` (resolved `.tr` paths) breaks cycles.

Rewriting: `rewrite_document` returns `document.to_dict()` with every file field on every action (both phases), and every guides reference `file`, replaced. For a plain dependency: `store.put(abs)` then `relative(stored, location)`. External values are left unchanged. For a `reference` node or a guides reference: load the referenced document, `nested = rewrite_document(nested_doc, nested_base, store, location=store.root, entries, owner=...)`, `stored = store.put_bytes(json.dumps(nested, indent=2).encode(), original_name)`, value becomes `relative(stored, location)` and its `version` setting becomes `"pinned"`. Every replacement appends a manifest entry to `entries`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_publish_set_trigger.py
"""The publish set: what a session needs, and bundles that never copy twice."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import tik.trigger as trigger
from tik.trigger.core import ActionContext, Document, kinds, registry
from tik.trigger.core.document import ActionNode
from tik.trigger.core.guide_document import ModuleReference
from tik.trigger.core.publish_set import (
    MANIFEST,
    STORE_DIR,
    Artifact,
    PublishSet,
    Store,
    clean,
    collect_dependencies,
    is_external,
    write_bundle,
)


@pytest.fixture(autouse=True, scope="module")
def _plugins():
    trigger.load_plugins()


def _script(name, file_path):
    return ActionNode(name=name, type="script", settings={"file_path": file_path})


def _session(folder: Path, name="hero", scripts=("a.py",)):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "scripts").mkdir(exist_ok=True)
    document = Document()
    for script in scripts:
        (folder / "scripts" / script).write_text(f"# {script}\n", encoding="utf-8")
        document.actions.append(_script(Path(script).stem, f"scripts/{script}"))
    document.save(folder / f"{name}.tr")
    return document


def test_is_external_means_outside_the_session_folder(tmp_path):
    assert is_external(tmp_path / "work" / "a.py", tmp_path / "work") is False
    assert is_external(tmp_path / "lib" / "a.py", tmp_path / "work") is True


def test_dependencies_come_from_file_fields_of_enabled_actions(tmp_path):
    document = _session(tmp_path / "work", scripts=("a.py", "b.py"))
    document.actions[1].enabled = False
    found = collect_dependencies(document, tmp_path / "work")
    assert [(dep.owner, dep.original, dep.external) for dep in found] == [
        ("a", "scripts/a.py", False)
    ]
    assert found[0].path == tmp_path / "work" / "scripts" / "a.py"


def test_dependencies_recurse_through_references(tmp_path):
    _session(tmp_path / "base", name="base", scripts=("base.py",))
    hero = _session(tmp_path / "work", scripts=("a.py",))
    hero.actions.append(
        ActionNode(name="ref", type="reference", settings={"file": "../base/base.tr"})
    )
    hero.guides.references.append(
        ModuleReference(ref_id="r1", file="../base/base.tr", version="pinned")
    )
    found = collect_dependencies(hero, tmp_path / "work")
    owners = [(dep.owner, dep.path.name) for dep in found]
    assert ("a", "a.py") in owners
    assert ("ref", "base.tr") in owners
    assert ("ref/base", "base.py") in owners
    assert ("guides/r1", "base.tr") in owners
    # the same referenced file through two links is listed once per link,
    # but its own dependencies are walked once
    assert owners.count(("ref/base", "base.py")) == 1


def test_collect_builds_the_core_artifacts(tmp_path):
    document = _session(tmp_path / "work")
    rig = tmp_path / "work" / "hero_rig.mb"
    rig.write_bytes(b"rig")
    publish_set = PublishSet.collect(
        tmp_path / "work" / "hero.tr", document, rig=rig,
        products=[Artifact("weights", tmp_path / "work" / "w.json")],
    )
    assert publish_set.name == "hero"
    assert [item.kind for item in publish_set.artifacts] == [
        kinds.SESSION, kinds.RIG, "weights"
    ]
    assert [dep.original for dep in publish_set.dependencies] == ["scripts/a.py"]


def test_store_keeps_one_copy_per_content(tmp_path):
    store = Store(tmp_path / STORE_DIR)
    one = tmp_path / "one.py"
    two = tmp_path / "two.py"
    one.write_text("same", encoding="utf-8")
    two.write_text("same", encoding="utf-8")
    first = store.put(one)
    second = store.put(two)
    assert first.exists() and first.name.endswith("_one.py")
    assert second.name.endswith("_two.py")
    assert store.hash_file(one) == store.hash_file(two)
    assert store.put(one) == first
    assert len(store.files()) == 2


def test_hash_cache_is_keyed_by_size_and_mtime(tmp_path):
    store = Store(tmp_path / STORE_DIR)
    target = tmp_path / "f.txt"
    target.write_text("abc", encoding="utf-8")
    first = store.hash_file(target)
    index = json.loads((store.root / "index.json").read_text(encoding="utf-8"))
    assert list(index.values())[0]["hash"] == first
    target.write_text("abd", encoding="utf-8")
    import os
    os.utime(target, (1, 1))
    assert store.hash_file(target) != first


def test_bundle_rewrites_paths_and_reopens_on_its_own(tmp_path):
    document = _session(tmp_path / "work")
    rig = tmp_path / "work" / "hero_rig.mb"
    rig.write_bytes(b"rig")
    publish_set = PublishSet.collect(tmp_path / "work" / "hero.tr", document, rig=rig)
    target = tmp_path / "out" / "hero_v001"
    write_bundle(publish_set, target)
    bundled = Document.load(target / "hero.tr")
    value = bundled.actions[0].settings["file_path"]
    assert value.startswith(f"../{STORE_DIR}/") and value.endswith("_a.py")
    assert (target / value).resolve().exists()
    assert (target / "hero_rig.mb").read_bytes() == b"rig"
    manifest = json.loads((target / MANIFEST).read_text(encoding="utf-8"))
    assert manifest["session"] == "hero.tr"
    assert manifest["dependencies"][0]["owner"] == "a"
    assert manifest["dependencies"][0]["store"] == value


def test_second_bundle_reuses_unchanged_content(tmp_path):
    document = _session(tmp_path / "work")
    publish_set = PublishSet.collect(tmp_path / "work" / "hero.tr", document)
    write_bundle(publish_set, tmp_path / "out" / "hero_v001")
    write_bundle(publish_set, tmp_path / "out" / "hero_v002")
    store = Store(tmp_path / "out" / STORE_DIR)
    assert len(store.files()) == 1
    (tmp_path / "work" / "scripts" / "a.py").write_text("# changed\n", encoding="utf-8")
    write_bundle(publish_set, tmp_path / "out" / "hero_v003")
    assert len(store.files()) == 2


def test_external_paths_are_left_alone_and_flagged(tmp_path):
    library = tmp_path / "lib" / "model.mb"
    library.parent.mkdir()
    library.write_bytes(b"model")
    document = _session(tmp_path / "work", scripts=())
    document.actions.append(
        ActionNode(name="model", type="import_asset", settings={"file_path": str(library).replace("\\", "/")})
    )
    publish_set = PublishSet.collect(tmp_path / "work" / "hero.tr", document)
    target = tmp_path / "out" / "hero_v001"
    write_bundle(publish_set, target)
    bundled = Document.load(target / "hero.tr")
    assert Path(bundled.actions[0].settings["file_path"]) == library
    manifest = json.loads((target / MANIFEST).read_text(encoding="utf-8"))
    assert manifest["dependencies"][0]["external"] is True
    assert Store(tmp_path / "out" / STORE_DIR).files() == []


def test_referenced_sessions_are_bundled_recursively(tmp_path):
    _session(tmp_path / "base", name="base", scripts=("base.py",))
    hero = _session(tmp_path / "work", scripts=())
    hero.actions.append(
        ActionNode(name="ref", type="reference", settings={"file": "../base/base.tr", "version": "latest"})
    )
    publish_set = PublishSet.collect(tmp_path / "work" / "hero.tr", hero)
    target = tmp_path / "out" / "hero_v001"
    write_bundle(publish_set, target)
    bundled = Document.load(target / "hero.tr")
    ref = bundled.actions[0].settings
    assert ref["version"] == "pinned"
    nested_path = (target / ref["file"]).resolve()
    assert nested_path.parent == (tmp_path / "out" / STORE_DIR).resolve()
    nested = Document.load(nested_path)
    inner = nested.actions[0].settings["file_path"]
    assert "/" not in inner and inner.endswith("_base.py")
    assert (nested_path.parent / inner).exists()


def test_clean_removes_only_unreferenced_store_files(tmp_path):
    document = _session(tmp_path / "work")
    publish_set = PublishSet.collect(tmp_path / "work" / "hero.tr", document)
    write_bundle(publish_set, tmp_path / "out" / "hero_v001")
    store = Store(tmp_path / "out" / STORE_DIR)
    orphan = store.put_bytes(b"orphan", "orphan.txt")
    removed = clean(store.root, [tmp_path / "out" / "hero_v001"])
    assert removed == [orphan]
    assert len(store.files()) == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `mayapy -m pytest tests/unit/test_publish_set_trigger.py -q`
Expected: FAIL with ImportError on the new names.

- [ ] **Step 3: Implement `publish_set.py`**

Replace the file with:

```python
"""What a session needs to be published: artifacts, dependencies, bundles.

Pure Python. Knows files and hashes; never Maya, Qt or a provider.

A *bundle* is a folder holding the session's ``.tr`` with its file paths
rewritten, the other artifacts, and a manifest. Every dependency lives once in
a flat content-addressed *store* beside the bundles, so an unchanged file is
never copied twice however many versions are published.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from . import kinds, registry, versioning
from .action import ActionContext
from .document import BUILD, PHASES, Document

logger = logging.getLogger(__name__)

MANIFEST = "manifest.json"
STORE_DIR = "_store"
INDEX = "index.json"
REFERENCE_TYPE = "reference"


@dataclass(frozen=True)
class Artifact:
    """One file a publish carries as a named element."""

    kind: str
    path: Path
    label: str = ""


@dataclass(frozen=True)
class Dependency:
    """A file a document needs, and where it was written down."""

    path: Path
    original: str
    owner: str
    external: bool


@dataclass
class PublishSet:
    """Everything one publish delivers."""

    session: Path
    base_dir: Path
    document: Document
    artifacts: list = field(default_factory=list)
    dependencies: list = field(default_factory=list)

    @property
    def name(self) -> str:
        """The session's stem: ``hero`` for ``hero.tr``."""
        return self.session.stem

    @classmethod
    def collect(
        cls,
        session_file,
        document: Document,
        *,
        rig: Optional[Path] = None,
        guides: Optional[Path] = None,
        products: Iterable[Artifact] = (),
    ) -> "PublishSet":
        """The core artifacts plus every dependency the document names."""
        session = Path(session_file)
        base_dir = session.parent
        artifacts = [Artifact(kinds.SESSION, session)]
        if guides is not None:
            artifacts.append(Artifact(kinds.GUIDES, Path(guides)))
        if rig is not None:
            artifacts.append(Artifact(kinds.RIG, Path(rig)))
        artifacts.extend(products)
        return cls(
            session=session,
            base_dir=base_dir,
            document=document,
            artifacts=artifacts,
            dependencies=collect_dependencies(document, base_dir),
        )


# ------------------------------------------------------------ dependencies
def is_external(path: Path, base_dir: Path) -> bool:
    """True when ``path`` is not inside ``base_dir``."""
    try:
        Path(path).resolve().relative_to(Path(base_dir).resolve())
    except ValueError:
        return True
    return False


def _resolve_reference(value: str, version: str, base_dir: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = Path(base_dir) / path
    return versioning.resolve(path, version or "latest")


def _reference_links(document: Document, base_dir: Path):
    """``(owner, original, resolved path)`` for every session this one links."""
    for path, node, _parent in document.walk(BUILD):
        if node.type == REFERENCE_TYPE and node.enabled and node.settings.get("file"):
            yield path, node.settings["file"], _resolve_reference(
                node.settings["file"], node.settings.get("version", "latest"), base_dir
            )
    for link in document.guides.references:
        if link.file:
            yield f"guides/{link.ref_id}", link.file, _resolve_reference(
                link.file, link.version, base_dir
            )


def collect_dependencies(
    document: Document, base_dir, owner_prefix: str = "", seen: Optional[set] = None
) -> list[Dependency]:
    """Every file the document's enabled actions and links need, recursively."""
    base = Path(base_dir)
    seen = set() if seen is None else seen
    found: list[Dependency] = []
    for path, node, _parent in document.walk(BUILD):
        if not node.enabled or node.type == REFERENCE_TYPE:
            continue
        if not registry.is_action_registered(node.type):
            logger.warning("publish: unknown action type '%s' at %s", node.type, path)
            continue
        action = registry.get_action(node.type)(settings=node.settings)
        ctx = ActionContext(base_dir=str(base), path=path)
        values = {
            name: getattr(action, name)
            for name in action.file_fields()
            if getattr(action, name)
        }
        for dep in action.dependencies(ctx):
            original = next(
                (value for value in values.values() if ctx.resolve(value) == dep),
                str(dep).replace("\\", "/"),
            )
            found.append(
                Dependency(dep, original, owner_prefix + path, is_external(dep, base))
            )
    for owner, original, resolved in _reference_links(document, base):
        found.append(
            Dependency(resolved, original, owner_prefix + owner, is_external(resolved, base))
        )
        key = str(resolved.resolve())
        if key in seen or not resolved.exists():
            continue
        seen.add(key)
        nested = Document.load(resolved)
        found.extend(
            collect_dependencies(
                nested, resolved.parent, owner_prefix=f"{owner_prefix}{owner}/", seen=seen
            )
        )
    return found


# ------------------------------------------------------------------ store
class Store:
    """A flat content-addressed folder: ``<root>/<sha1>_<name>``."""

    def __init__(self, root) -> None:
        self.root = Path(root)
        self._index: Optional[dict] = None

    # cache -----------------------------------------------------------
    @property
    def _index_file(self) -> Path:
        return self.root / INDEX

    def _load_index(self) -> dict:
        if self._index is None:
            try:
                self._index = json.loads(self._index_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._index = {}
        return self._index

    def _save_index(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._index_file.write_text(
            json.dumps(self._load_index(), indent=2), encoding="utf-8"
        )

    @staticmethod
    def _digest(data: bytes) -> str:
        return hashlib.sha1(data).hexdigest()  # noqa: S324 - content id, not security

    def hash_file(self, path) -> str:
        """SHA-1 of the content, cached by ``(size, mtime)``."""
        path = Path(path)
        stat = path.stat()
        key = str(path.resolve())
        entry = self._load_index().get(key)
        if entry and entry["size"] == stat.st_size and entry["mtime"] == stat.st_mtime:
            return entry["hash"]
        digest = self._digest(path.read_bytes())
        self._load_index()[key] = {
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "hash": digest,
        }
        self._save_index()
        return digest

    # content ---------------------------------------------------------
    def _target(self, digest: str, name: str) -> Path:
        return self.root / f"{digest}_{name}"

    def put(self, path) -> Path:
        """Store the file once; return the stored path."""
        path = Path(path)
        target = self._target(self.hash_file(path), path.name)
        if not target.exists():
            self.root.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        return target

    def put_bytes(self, data: bytes, name: str) -> Path:
        """Store in-memory content once under ``name``; return the stored path."""
        target = self._target(self._digest(data), name)
        if not target.exists():
            self.root.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        return target

    def files(self) -> list[Path]:
        """Every stored file (the index excluded), sorted."""
        if not self.root.exists():
            return []
        return sorted(item for item in self.root.iterdir() if item.name != INDEX)


def relative(target, from_dir) -> str:
    """``target`` relative to ``from_dir`` with forward slashes."""
    return os.path.relpath(str(target), str(from_dir)).replace("\\", "/")


# --------------------------------------------------------------- bundles
def _entry(owner, original, dep_path, store_value, external, store=None) -> dict:
    entry = {
        "owner": owner,
        "original": original,
        "hash": "" if external or store is None else store.hash_file(dep_path),
        "size": 0 if external else Path(dep_path).stat().st_size,
        "store": store_value,
        "external": external,
    }
    return entry


def _rewrite_reference(value, version, base_dir, store, location, entries, owner) -> str:
    resolved = _resolve_reference(value, version, base_dir)
    if is_external(resolved, base_dir) or not resolved.exists():
        entries.append(_entry(owner, value, resolved, value, True))
        return value
    nested = rewrite_document(
        Document.load(resolved), resolved.parent, store, store.root, entries, owner=f"{owner}/"
    )
    stored = store.put_bytes(json.dumps(nested, indent=2).encode("utf-8"), resolved.name)
    store_value = relative(stored, location)
    entries.append(_entry(owner, value, stored, store_value, False, store))
    return store_value


def rewrite_document(
    document: Document, base_dir, store: Store, location, entries: list, owner: str = ""
) -> dict:
    """``document.to_dict()`` with every file path pointing into ``store``.

    ``location`` is the folder the rewritten document will be written to;
    paths are made relative to it. Nested references are rewritten with the
    store root as their location, since that is where they land.
    """
    base = Path(base_dir)
    data = document.to_dict()
    for phase in PHASES:
        for path, node, _parent in document.walk(phase):
            if not registry.is_action_registered(node.type):
                continue
            action_cls = registry.get_action(node.type)
            target = _find_node(data[phase if phase != BUILD else "actions"], path)
            settings = target["settings"]
            if node.type == REFERENCE_TYPE:
                if settings.get("file"):
                    settings["file"] = _rewrite_reference(
                        settings["file"], settings.get("version", "latest"), base,
                        store, location, entries, owner + path,
                    )
                    settings["version"] = "pinned"
                continue
            for name in action_cls.file_fields():
                value = settings.get(name)
                if not value:
                    continue
                resolved = Path(value) if Path(value).is_absolute() else base / value
                if is_external(resolved, base) or not resolved.exists():
                    entries.append(_entry(owner + path, value, resolved, value, True))
                    continue
                stored = store.put(resolved)
                store_value = relative(stored, location)
                settings[name] = store_value
                entries.append(_entry(owner + path, value, resolved, store_value, False, store))
    for index, link in enumerate(document.guides.references):
        if not link.file:
            continue
        link_data = data["guides"]["references"][index]
        link_data["file"] = _rewrite_reference(
            link.file, link.version, base, store, location, entries, f"{owner}guides/{link.ref_id}"
        )
        link_data["version"] = "pinned"
    return data


def _find_node(nodes: list, path: str) -> dict:
    """The dict for the action at ``path`` inside a ``to_dict`` tree."""
    from .document import split_path

    current = None
    for part in split_path(path):
        current = next(item for item in nodes if item["name"] == part)
        nodes = current["children"]
    return current


def write_bundle(publish_set: PublishSet, target, store_root=None) -> Path:
    """Write the bundle folder for ``publish_set`` at ``target``."""
    target = Path(target)
    store = Store(Path(store_root) if store_root else target.parent / STORE_DIR)
    target.mkdir(parents=True, exist_ok=True)
    entries: list = []
    data = rewrite_document(
        publish_set.document, publish_set.base_dir, store, target, entries
    )
    session_name = publish_set.session.name
    (target / session_name).write_text(json.dumps(data, indent=2), encoding="utf-8")
    artifacts = []
    for artifact in publish_set.artifacts:
        if artifact.kind == kinds.SESSION:
            artifacts.append({"kind": artifact.kind, "path": session_name, "label": artifact.label})
            continue
        shutil.copy2(artifact.path, target / artifact.path.name)
        artifacts.append(
            {"kind": artifact.kind, "path": artifact.path.name, "label": artifact.label}
        )
    manifest = {"session": session_name, "artifacts": artifacts, "dependencies": entries}
    (target / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return target


def clean(store_root, bundle_roots: Iterable) -> list[Path]:
    """Delete store files no manifest under ``bundle_roots`` references."""
    store = Store(store_root)
    referenced: set[Path] = set()
    for root in bundle_roots:
        for manifest in Path(root).rglob(MANIFEST):
            data = json.loads(manifest.read_text(encoding="utf-8"))
            for entry in data.get("dependencies", []):
                if entry.get("external") or not entry.get("store"):
                    continue
                referenced.add((manifest.parent / entry["store"]).resolve())
                # a nested session in the store references its own siblings
                nested = (manifest.parent / entry["store"]).resolve()
                if nested.suffix == ".tr" and nested.exists():
                    referenced |= _nested_references(nested)
    removed = []
    for item in store.files():
        if item.resolve() not in referenced:
            item.unlink()
            removed.append(item)
    return removed


def _nested_references(session_file: Path) -> set[Path]:
    """Store siblings a stored ``.tr`` points at, recursively."""
    found: set[Path] = set()
    document = Document.load(session_file)
    for phase in PHASES:
        for _path, node, _parent in document.walk(phase):
            if not registry.is_action_registered(node.type):
                continue
            names = ["file"] if node.type == REFERENCE_TYPE else list(
                registry.get_action(node.type).file_fields()
            )
            for name in names:
                value = node.settings.get(name)
                if value and not Path(value).is_absolute():
                    target = (session_file.parent / value).resolve()
                    found.add(target)
                    if target.suffix == ".tr" and target.exists() and target != session_file:
                        found |= _nested_references(target)
    for link in document.guides.references:
        if link.file and not Path(link.file).is_absolute():
            target = (session_file.parent / link.file).resolve()
            found.add(target)
            if target.exists() and target != session_file:
                found |= _nested_references(target)
    return found
```

- [ ] **Step 4: Update the spec sentence**

In the spec's section 5 bundle block replace `<target>/../_store/<sha1[:2]>/<sha1>_<name>` with `<target>/../_store/<sha1>_<name>` and add after the bullet list: "The store is flat: a nested referenced `.tr` is rewritten and stored too, and with every stored file a sibling its own paths are deterministic before its hash is known."

- [ ] **Step 5: Run tests and lint**

Run: `mayapy -m pytest tests/unit/test_publish_set_trigger.py -q`, `mayapy -m pytest tests/unit/test_import_boundaries.py -q`, `make lint`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/python/tik/trigger/core/publish_set.py tests/unit/test_publish_set_trigger.py docs/superpowers/specs/2026-09-08-version-control-scaffold-design.md
git commit -m "Add the publish set, the content store and bundle writing"
```

---

### Task 5: The `tik.trigger.vcs` package: provider, registry, host

**Files:**
- Create: `src/python/tik/trigger/vcs/__init__.py`, `provider.py`, `host.py`, `kinds.py`
- Modify: `src/python/tik/trigger/core/exceptions.py` (add `VersionControlError`)
- Modify: `tests/unit/test_import_boundaries.py` (new rules)
- Test: `tests/unit/test_vcs_trigger.py`

**Interfaces:**

```python
# tik.trigger.core.exceptions
class VersionControlError(TriggerError): ...

# tik.trigger.vcs.provider
@dataclass(frozen=True)
class Context:
    label: str
    version: Optional[int] = None
    is_latest: bool = True
    detail: str = ""

class VersionControl:
    name: str = ""      # stamped by @register_provider
    label: str = ""     # menu text; defaults to name.title()
    icon: str = ""      # icon file stem beside the provider's .py; defaults to name
    def available(self) -> bool: return False
    def context(self, session_path: str) -> Optional[Context]: return None
    def browse(self, kind: str, extensions: list, mode: str) -> str: return ""
    def new_version(self, host) -> str: return ""
    def open(self, host) -> str: return ""
    def publish_file(self, kind: str, path, host) -> None: return None
    def launch(self, host) -> None: return None
    def supports(self, verb: str) -> bool     # True when this class overrides verb
    def display_label(self) -> str
    def icon_path(self) -> Optional[Path]     # <icon>.png or <icon>.svg beside the class's file, or None

# tik.trigger.vcs.host
class Host:
    def attach(self, session=None, open=None, save_as=None, refresh=None, feedback=None) -> None
    def detach(self) -> None
    session -> Optional[Session]        # a callable given to attach is called each time
    session_path -> str
    is_modified -> bool
    def open(self, path) -> None        # opener callable, else session.load, else a new Session
    def save_as(self, path) -> Path     # saver callable, else session.save(path)
    def refresh(self) -> None
    feedback -> Feedback                # feedback callable, else Feedback() (lazy import)

# tik.trigger.vcs
register_provider(name) -> decorator     # DuplicateRegistrationError on a different class
providers() -> list[type]                # sorted by name
get_provider(name) -> type               # NotFoundError(kind="provider")
provider_names() -> list[str]
set_preferred(name: Optional[str]) -> None
preferred() -> Optional[str]
active() -> Optional[VersionControl]     # cached instance per class
clear_providers() -> None                # tests
host: Host                               # the module-level host
def open() -> str
def new_version() -> str
def publish_file(kind, path) -> None
def launch() -> None
def require() -> VersionControl          # active() or VersionControlError
```

`active()` rule: candidates = providers whose instance `.available()` is True. None: return None. One: it. Several: the one named by `preferred()` when it is a candidate; else the first by name, logging `"vcs: several providers available (%s); using %s"` once per change.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_vcs_trigger.py
"""The provider contract, its registry, and the host the outside world drives."""

from __future__ import annotations

import pytest

from tik.trigger import vcs
from tik.trigger.core.exceptions import (
    DuplicateRegistrationError,
    NotFoundError,
    VersionControlError,
)
from tik.trigger.session import Session
from tik.trigger.vcs.provider import Context, VersionControl


@pytest.fixture(autouse=True)
def _clean():
    vcs.clear_providers()
    vcs.set_preferred(None)
    vcs.host.detach()
    yield
    vcs.clear_providers()
    vcs.set_preferred(None)
    vcs.host.detach()


def _provider(name, is_available=True, **overrides):
    body = {"available": lambda self: is_available}
    body.update(overrides)
    cls = type(name.title(), (VersionControl,), body)
    return vcs.register_provider(name)(cls)


def test_register_stamps_name_and_refuses_a_second_class():
    cls = _provider("alpha")
    assert cls.name == "alpha"
    assert cls().display_label() == "Alpha"
    assert vcs.provider_names() == ["alpha"]
    with pytest.raises(DuplicateRegistrationError):
        vcs.register_provider("alpha")(type("Other", (VersionControl,), {}))
    with pytest.raises(NotFoundError):
        vcs.get_provider("missing")


def test_active_is_none_without_an_available_provider():
    assert vcs.active() is None
    _provider("off", is_available=False)
    assert vcs.active() is None


def test_active_picks_the_only_available_provider():
    _provider("off", is_available=False)
    _provider("on")
    assert vcs.active().name == "on"
    assert vcs.active() is vcs.active()  # one instance


def test_preference_breaks_ties_else_first_by_name():
    _provider("beta")
    _provider("alpha")
    assert vcs.active().name == "alpha"
    vcs.set_preferred("beta")
    assert vcs.active().name == "beta"
    vcs.set_preferred("nope")
    assert vcs.active().name == "alpha"


def test_defaults_are_detectable_no_ops():
    base = VersionControl()
    assert base.available() is False
    assert base.context("x.tr") is None
    assert base.browse("script", [".py"], "open") == ""
    assert base.new_version(vcs.host) == ""
    assert base.open(vcs.host) == ""
    assert base.publish_file("script", "a.py", vcs.host) is None
    assert base.launch(vcs.host) is None
    for verb in ("context", "browse", "new_version", "open", "publish_file", "launch"):
        assert base.supports(verb) is False
    cls = _provider("partial", browse=lambda self, kind, ext, mode: "picked.py")
    assert cls().supports("browse") is True
    assert cls().supports("open") is False


def test_context_is_a_plain_record():
    ctx = Context(label="hero / rig", version=3, is_latest=False, detail="…")
    assert ctx.version == 3 and ctx.is_latest is False


def test_headless_host_over_a_session(tmp_path):
    session = Session()
    assert vcs.host.session is None and vcs.host.session_path == ""
    vcs.host.attach(session=session)
    assert vcs.host.session is session
    assert vcs.host.is_modified is False
    saved = vcs.host.save_as(tmp_path / "hero.tr")
    assert saved == tmp_path / "hero.tr" and vcs.host.session_path.endswith("hero.tr")
    session.add("script", "a", code="pass")
    assert vcs.host.is_modified is True
    other = Session()
    other.save(tmp_path / "other.tr")
    vcs.host.open(tmp_path / "other.tr")
    assert vcs.host.session_path.endswith("other.tr")


def test_host_callables_win_over_the_session(tmp_path):
    calls = []
    vcs.host.attach(
        session=lambda: None,
        open=lambda path: calls.append(("open", str(path))),
        save_as=lambda path: calls.append(("save", str(path))) or path,
        refresh=lambda: calls.append(("refresh",)),
    )
    vcs.host.open("a.tr")
    vcs.host.save_as("b.tr")
    vcs.host.refresh()
    assert calls == [("open", "a.tr"), ("save", "b.tr"), ("refresh",)]


def test_headless_verbs_need_an_active_provider():
    with pytest.raises(VersionControlError):
        vcs.open()
    with pytest.raises(VersionControlError):
        vcs.publish_file("script", "a.py")
    seen = []
    _provider(
        "tm",
        open=lambda self, host: seen.append("open") or "x.tr",
        new_version=lambda self, host: seen.append("new") or "x_v002.tr",
        publish_file=lambda self, kind, path, host: seen.append((kind, str(path))),
        launch=lambda self, host: seen.append("launch"),
    )
    assert vcs.open() == "x.tr"
    assert vcs.new_version() == "x_v002.tr"
    vcs.publish_file("script", "a.py")
    vcs.launch()
    assert seen == ["open", "new", ("script", "a.py"), "launch"]


def test_kinds_are_re_exported():
    from tik.trigger.vcs import kinds

    assert kinds.SESSION == "session" and kinds.kind_for([".trg"]) == "guides"
```

- [ ] **Step 2: Run to verify failure**

Run: `mayapy -m pytest tests/unit/test_vcs_trigger.py -q`
Expected: FAIL with `ModuleNotFoundError: tik.trigger.vcs`.

- [ ] **Step 3: Add the exception**

In `src/python/tik/trigger/core/exceptions.py` add, next to `SessionError`:

```python
class VersionControlError(TriggerError):
    """A version control operation could not run (no provider, refused, failed)."""
```

Export it from `tik/trigger/core/__init__.py` (the `from .exceptions import (...)` list and `__all__`). Read `DuplicateRegistrationError` and `NotFoundError` in that file: both take `(name, kind=...)`; if their message enumerates known kinds, add `"provider"`.

- [ ] **Step 4: Write `provider.py`**

```python
# src/python/tik/trigger/vcs/provider.py
"""The contract a version control system implements, from outside the repo.

Every verb has a working default, so a provider implements what it supports
and the UI shows only what the provider answers (``supports``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class Context:
    """What a session path is to the VCS, for the status chip and tooltips."""

    label: str
    version: Optional[int] = None
    is_latest: bool = True
    detail: str = ""


class VersionControl:
    """Base class for providers. Register with ``@register_provider(name)``."""

    name: str = ""
    label: str = ""
    icon: str = ""

    # ------------------------------------------------------------ verbs
    def available(self) -> bool:
        """Installed and configured? Only available providers are ever used."""
        return False

    def context(self, session_path: str) -> Optional[Context]:
        """What ``session_path`` is in the VCS; ``None`` when it is not a work."""
        return None

    def browse(self, kind: str, extensions: list, mode: str) -> str:
        """The VCS's own picker; the chosen path or ``""`` when cancelled."""
        return ""

    def new_version(self, host) -> str:
        """Save the host's session as the next version; the new path or ``""``."""
        return ""

    def open(self, host) -> str:
        """Pick a session in the VCS and open it through ``host``; the path or ``""``."""
        return ""

    def publish_file(self, kind: str, path, host) -> None:
        """Hand one file to the VCS's own publish/ingest dialog."""
        return None

    def launch(self, host) -> None:
        """Open the VCS's main window."""
        return None

    # ---------------------------------------------------------- helpers
    def supports(self, verb: str) -> bool:
        """True when this provider overrides ``verb``."""
        return getattr(type(self), verb) is not getattr(VersionControl, verb)

    def display_label(self) -> str:
        """The label shown in menus and tooltips."""
        return self.label or self.name.replace("_", " ").title() or type(self).__name__

    def icon_path(self) -> Optional[Path]:
        """``<icon>.png`` or ``<icon>.svg`` beside the provider's file, if any."""
        import inspect

        stem = self.icon or self.name
        if not stem:
            return None
        try:
            folder = Path(inspect.getfile(type(self))).parent
        except (TypeError, OSError):
            return None
        for suffix in (".png", ".svg"):
            candidate = folder / f"{stem}{suffix}"
            if candidate.exists():
                return candidate
        return None
```

- [ ] **Step 5: Write `host.py`**

```python
# src/python/tik/trigger/vcs/host.py
"""The one object Trigger exposes outward.

Providers never import the window. The window attaches itself here; a
headless script attaches a ``Session``. Both look the same from a provider.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional


class Host:
    """Session access, open and save, a refresh hook, and dialogs."""

    def __init__(self) -> None:
        self._session: Any = None
        self._open: Optional[Callable] = None
        self._save_as: Optional[Callable] = None
        self._refresh: Optional[Callable] = None
        self._feedback: Optional[Callable] = None

    def attach(
        self,
        session=None,
        open: Optional[Callable] = None,  # noqa: A002 - the verb is the name
        save_as: Optional[Callable] = None,
        refresh: Optional[Callable] = None,
        feedback: Optional[Callable] = None,
    ) -> None:
        """Bind the host. ``session`` may be a Session or a callable returning one."""
        self._session = session
        self._open = open
        self._save_as = save_as
        self._refresh = refresh
        self._feedback = feedback

    def detach(self) -> None:
        """Forget everything; the host answers as if nothing were open."""
        self.attach()

    # ---------------------------------------------------------- session
    @property
    def session(self):
        """The active ``Session`` or ``None``."""
        if callable(self._session):
            return self._session()
        return self._session

    @property
    def session_path(self) -> str:
        """The active session's file, or ``""``."""
        session = self.session
        if session is None or session.file_path is None:
            return ""
        return str(session.file_path).replace("\\", "/")

    @property
    def is_modified(self) -> bool:
        session = self.session
        return bool(session is not None and session.is_modified)

    # ------------------------------------------------------------ verbs
    def open(self, path) -> None:
        """Open a ``.tr``: through the window when attached, else on the session."""
        if self._open is not None:
            self._open(path)
            return
        session = self.session
        if session is None:
            from tik.trigger.session import Session

            self._session = Session(str(path))
            return
        session.load(str(path))

    def save_as(self, path) -> Path:
        """Save the active session at ``path``; returns where it went."""
        if self._save_as is not None:
            return Path(self._save_as(path))
        session = self.session
        if session is None:
            from tik.trigger.core.exceptions import VersionControlError

            raise VersionControlError("No session to save.")
        return session.save(str(path))

    def refresh(self) -> None:
        """Tell the window the VCS context may have changed."""
        if self._refresh is not None:
            self._refresh()

    @property
    def feedback(self):
        """A correctly parented ``Feedback`` for a provider's own questions."""
        if self._feedback is not None:
            return self._feedback()
        from tik.shared.ui.feedback import Feedback

        return Feedback()
```

- [ ] **Step 6: Write `kinds.py` and `__init__.py`**

```python
# src/python/tik/trigger/vcs/kinds.py
"""The kind vocabulary, re-exported for providers (defined in ``core.kinds``)."""

from tik.trigger.core.kinds import (  # noqa: F401 - re-export
    EXTENSIONS,
    FILE,
    GUIDES,
    MODEL,
    ORDER,
    RIG,
    SCRIPT,
    SESSION,
    kind_for,
)
```

```python
# src/python/tik/trigger/vcs/__init__.py
"""Version control for Trigger: the provider registry and the host.

A VCS integrates from outside the repository: it registers a
:class:`VersionControl` subclass with ``@register_provider`` from a plugin on
``TRIGGER_PLUGIN_PATH`` and drives Trigger through ``host``. Only the UI and
publish actions import this package; nothing on the build path does, and this
package never reads preferences (the window tells it which provider is
preferred through ``set_preferred``).
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from tik.trigger.core.exceptions import (
    DuplicateRegistrationError,
    NotFoundError,
    VersionControlError,
)

from . import kinds  # noqa: F401 - part of the public surface
from .host import Host
from .provider import Context, VersionControl

logger = logging.getLogger(__name__)

_PROVIDERS: dict[str, type] = {}
_INSTANCES: dict[str, VersionControl] = {}
_preferred: Optional[str] = None
_last_pick: Optional[str] = None

#: The one host. The window attaches itself; scripts attach a Session.
host = Host()


def register_provider(name: str) -> Callable[[type], type]:
    """Register a ``VersionControl`` subclass under ``name``."""

    def inner(cls: type) -> type:
        existing = _PROVIDERS.get(name)
        if existing is not None and existing is not cls:
            raise DuplicateRegistrationError(name, kind="provider")
        cls.name = name
        _PROVIDERS[name] = cls
        _INSTANCES.pop(name, None)
        logger.debug("Registered version control provider: %s", name)
        return cls

    return inner


def providers() -> list[type]:
    """Registered provider classes, by name."""
    return [_PROVIDERS[name] for name in provider_names()]


def provider_names() -> list[str]:
    return sorted(_PROVIDERS)


def get_provider(name: str) -> type:
    try:
        return _PROVIDERS[name]
    except KeyError:
        raise NotFoundError(name, kind="provider") from None


def clear_providers() -> None:
    """Drop every registration (tests)."""
    _PROVIDERS.clear()
    _INSTANCES.clear()


def set_preferred(name: Optional[str]) -> None:
    """Name the provider to use when several are available (the window sets it)."""
    global _preferred
    _preferred = name or None


def preferred() -> Optional[str]:
    return _preferred


def _instance(name: str) -> VersionControl:
    if name not in _INSTANCES:
        _INSTANCES[name] = _PROVIDERS[name]()
    return _INSTANCES[name]


def active() -> Optional[VersionControl]:
    """The provider in use, or ``None`` when no available provider exists."""
    global _last_pick
    candidates = []
    for name in provider_names():
        try:
            if _instance(name).available():
                candidates.append(name)
        except Exception as error:  # noqa: BLE001 - a broken provider is unavailable
            logger.error("vcs: provider %s failed availability check: %s", name, error)
    if not candidates:
        return None
    if len(candidates) == 1:
        pick = candidates[0]
    elif _preferred in candidates:
        pick = _preferred
    else:
        pick = candidates[0]
        if _last_pick != pick:
            logger.info(
                "vcs: several providers available (%s); using %s",
                ", ".join(candidates),
                pick,
            )
    _last_pick = pick
    return _instance(pick)


def require() -> VersionControl:
    """``active()`` or a ``VersionControlError``."""
    provider = active()
    if provider is None:
        raise VersionControlError("No version control provider is active.")
    return provider


# ------------------------------------------------------------ headless verbs
def open() -> str:  # noqa: A001 - the verb is the name
    """Pick and open a session through the active provider; the path or ``""``."""
    return require().open(host)


def new_version() -> str:
    """Save the active session as its next version in the VCS."""
    return require().new_version(host)


def publish_file(kind: str, path) -> None:
    """Hand one file to the VCS's own dialog."""
    require().publish_file(kind, path, host)


def launch() -> None:
    """Open the VCS's main window."""
    require().launch(host)


__all__ = [
    "Context",
    "Host",
    "VersionControl",
    "VersionControlError",
    "active",
    "clear_providers",
    "get_provider",
    "host",
    "kinds",
    "launch",
    "new_version",
    "open",
    "preferred",
    "provider_names",
    "providers",
    "publish_file",
    "register_provider",
    "require",
    "set_preferred",
]
```

- [ ] **Step 7: Extend the boundary test**

In `tests/unit/test_import_boundaries.py` add:

```python
VCS = ("tik.trigger.vcs",)
```

and add `+ VCS` to the `"trigger/core"`, `"trigger/modules"`, `"trigger/systems"`, `"trigger/maya"`, `"trigger/guides"` and `"trigger/anim"` entries of `FORBIDDEN`. Then add two tests:

```python
def test_only_the_publish_action_package_may_import_vcs():
    """Build actions never see the VCS; the publish base does not either."""
    offenders = []
    for py_file in (SRC / "trigger" / "actions").rglob("*.py"):
        if py_file.parent.name == "publish":
            continue
        for name in _imports(py_file):
            if name == "tik.trigger.vcs" or name.startswith("tik.trigger.vcs."):
                offenders.append(str(py_file.relative_to(SRC)))
    assert offenders == []


def test_vcs_never_reads_preferences_and_nothing_imports_tik_manager4():
    assert _violations("trigger/vcs", PREFS) == []
    assert _violations("", ("tik_manager4",)) == []
```

- [ ] **Step 8: Run tests and lint**

Run: `mayapy -m pytest tests/unit/test_vcs_trigger.py tests/unit/test_import_boundaries.py -q`, `make lint`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/python/tik/trigger/vcs src/python/tik/trigger/core/exceptions.py src/python/tik/trigger/core/__init__.py tests/unit/test_vcs_trigger.py tests/unit/test_import_boundaries.py
git commit -m "Add the version control provider contract, registry and host"
```

---

### Task 6: `FolderProvider`, the reference implementation

**Files:**
- Create: `src/python/tik/trigger/vcs/folder.py`
- Test: `tests/unit/test_folder_provider_trigger.py`

**Interfaces:**
- Produces: `tik.trigger.vcs.folder.FolderProvider`, registered as `"folder"`, `ROOT_VAR = "TRIGGER_FOLDER_VCS"`. `FolderProvider(root=None)`; `available()` True when the root exists. Layout: `<root>/sessions/<name>_v###.tr`; published files under `<root>/<kind>/<name>_v###<ext>`.

This is the file the integrator's guide quotes verbatim: keep it short and every verb exemplary (under ~90 lines of code).

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_folder_provider_trigger.py
"""FolderProvider: the shipped reference provider (a versioned folder tree)."""

import pytest

from tik.trigger import vcs
from tik.trigger.session import Session
from tik.trigger.vcs.folder import FolderProvider


@pytest.fixture
def provider(tmp_path, monkeypatch):
    monkeypatch.setenv("TRIGGER_FOLDER_VCS", str(tmp_path / "vcs"))
    (tmp_path / "vcs").mkdir()
    made = FolderProvider()
    vcs.host.detach()
    yield made
    vcs.host.detach()


def test_available_only_when_the_root_exists(tmp_path, monkeypatch):
    monkeypatch.delenv("TRIGGER_FOLDER_VCS", raising=False)
    assert FolderProvider().available() is False
    monkeypatch.setenv("TRIGGER_FOLDER_VCS", str(tmp_path / "missing"))
    assert FolderProvider().available() is False
    (tmp_path / "missing").mkdir()
    assert FolderProvider().available() is True


def test_context_reads_the_version_suffix(provider, tmp_path):
    folder = provider.root / "sessions"
    folder.mkdir()
    (folder / "hero_v001.tr").write_text("{}", encoding="utf-8")
    (folder / "hero_v002.tr").write_text("{}", encoding="utf-8")
    assert provider.context(str(tmp_path / "elsewhere.tr")) is None
    older = provider.context(str(folder / "hero_v001.tr"))
    assert older.label == "hero" and older.version == 1 and older.is_latest is False
    latest = provider.context(str(folder / "hero_v002.tr"))
    assert latest.version == 2 and latest.is_latest is True


def test_new_version_saves_the_next_number_under_sessions(provider, tmp_path):
    session = Session()
    session.save(tmp_path / "work" / "hero.tr")
    vcs.host.attach(session=session)
    first = provider.new_version(vcs.host)
    assert first.endswith("sessions/hero_v001.tr")
    second = provider.new_version(vcs.host)
    assert second.endswith("sessions/hero_v002.tr")
    assert (provider.root / "sessions" / "hero_v002.tr").exists()


def test_publish_file_copies_under_its_kind_versioned(provider, tmp_path):
    script = tmp_path / "a.py"
    script.write_text("x", encoding="utf-8")
    provider.publish_file("script", script, vcs.host)
    provider.publish_file("script", script, vcs.host)
    names = sorted(item.name for item in (provider.root / "script").iterdir())
    assert names == ["a_v001.py", "a_v002.py"]


def test_browse_and_open_go_through_the_host_feedback(provider, tmp_path):
    target = provider.root / "sessions" / "hero_v001.tr"
    target.parent.mkdir()
    Session().save(target)
    opened = []

    class _Feedback:
        def browse_open(self, caption, start, extensions):
            assert start.endswith("sessions") and extensions == (".tr",)
            return str(target)

    vcs.host.attach(session=lambda: None, open=opened.append, feedback=_Feedback)
    assert provider.browse("session", [".tr"], "open") == str(target)
    assert provider.open(vcs.host) == str(target)
    assert opened == [str(target)]
```

- [ ] **Step 2: Run to verify failure**

Run: `mayapy -m pytest tests/unit/test_folder_provider_trigger.py -q`
Expected: FAIL, module missing.

- [ ] **Step 3: Write `folder.py`**

```python
# src/python/tik/trigger/vcs/folder.py
"""A version control system that is only a folder tree.

The reference provider: every verb of the contract in the simplest form that
works, and the file the integrator's guide quotes. Point ``TRIGGER_FOLDER_VCS``
at a folder and Trigger versions sessions under ``sessions/`` and published
files under ``<kind>/``, ``_v###`` style.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from tik.trigger.core import versioning
from tik.trigger.vcs import kinds, register_provider
from tik.trigger.vcs.provider import Context, VersionControl

ROOT_VAR = "TRIGGER_FOLDER_VCS"


@register_provider("folder")
class FolderProvider(VersionControl):
    """Versioned folders, no server, no dialogs of its own."""

    label = "Folder"

    def __init__(self, root=None) -> None:
        self.root = Path(root or os.environ.get(ROOT_VAR, ""))

    def available(self) -> bool:
        return bool(str(self.root) != ".") and self.root.is_dir()

    def context(self, session_path: str) -> Optional[Context]:
        path = Path(session_path)
        if not session_path or self.root.resolve() not in path.resolve().parents:
            return None
        stem, version, _suffix = versioning.parse(path)
        latest = versioning.latest_version(path)
        latest_number = versioning.parse(latest)[1] if latest else version
        return Context(
            label=stem,
            version=version,
            is_latest=version is None or version >= (latest_number or 0),
            detail=str(path),
        )

    def browse(self, kind: str, extensions: list, mode: str) -> str:
        from tik.trigger.vcs import host

        folder = self.root / ("sessions" if kind == kinds.SESSION else kind)
        return host.feedback.browse_open("Pick a file", str(folder), tuple(extensions))

    def new_version(self, host) -> str:
        session = host.session
        if session is None:
            return ""
        folder = self.root / "sessions"
        folder.mkdir(parents=True, exist_ok=True)
        target = versioning.next_version(folder / f"{session.name}.tr")
        return str(host.save_as(target)).replace("\\", "/")

    def open(self, host) -> str:
        picked = self.browse(kinds.SESSION, [".tr"], "open")
        if picked:
            host.open(picked)
        return picked

    def publish_file(self, kind: str, path, host) -> None:
        source = Path(path)
        folder = self.root / kind
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, versioning.next_version(folder / source.name))

    def launch(self, host) -> None:
        from tik.shared.io import open_external

        open_external(self.root)
```

`Path("")` is `Path(".")`, hence the `!= "."` guard in `available`. `Session.name` (session.py:127) is the file stem. `versioning.next_version(folder / "hero.tr")` yields `hero_v001.tr` when none exist.

- [ ] **Step 4: Run tests and lint**

Run: `mayapy -m pytest tests/unit/test_folder_provider_trigger.py tests/unit/test_import_boundaries.py -q`, `make lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/vcs/folder.py tests/unit/test_folder_provider_trigger.py
git commit -m "Add FolderProvider, the reference version control provider"
```

---

### Task 7: `PublishAction` and the generic `publish` action

**Files:**
- Create: `src/python/tik/trigger/actions/publish/publish.py`, `publish.svg`
- Test: `tests/unit/test_publish_action_unit_trigger.py` (pure: fields, validate, the folder deliver over a prebuilt set)
- Test: `tests/integration/trigger/test_publish_action_trigger.py` (Maya)

**Interfaces:**

```python
# tik.trigger.actions.publish.publish
TEMP_DIR = "_publish_tmp"

class PublishAction(Action):          # not registered
    include_guides = BoolField(True, ...)
    include_products = BoolField(True, ...)
    def validate(self, ctx) -> list[str]   # + "<type>: save the session first" when ctx.session is None or has no file_path
    def run(self, ctx) -> None             # spec section 6 steps 1-5
    def deliver(self, publish_set, ctx) -> None    # subclasses; NotImplementedError here
    def collect(self, ctx, rig=None, guides=None) -> PublishSet

@register_action("publish", category="finish", icon="publish", scope="publish")
class Publish(PublishAction):
    folder = FileField("publish", mode="dir", label="Publish folder", help=...)
    def deliver(self, publish_set, ctx) -> None   # <folder>/<name>_v###/ + <folder>/_store
    def summary(self) -> str                     # the folder
```

- [ ] **Step 1: Write the pure unit tests**

```python
# tests/unit/test_publish_action_unit_trigger.py
"""PublishAction without Maya: fields, validation, and the folder delivery."""

import pytest

import tik.trigger as trigger
from tik.trigger.core import ActionContext, registry
from tik.trigger.core.publish_set import STORE_DIR, PublishSet
from tik.trigger.session import Session


@pytest.fixture(autouse=True, scope="module")
def _plugins():
    trigger.load_plugins()


def test_publish_is_registered_in_the_publish_scope():
    cls = registry.get_action("publish")
    assert cls.scope == "publish" and cls.category == "finish"
    assert "folder" in cls.fields() and "include_guides" in cls.fields()
    assert cls().include_guides is True and cls().include_products is True
    assert cls().folder == "publish"


def test_validate_needs_a_saved_session(tmp_path):
    cls = registry.get_action("publish")
    problems = cls().validate(ActionContext(session=None, base_dir=str(tmp_path)))
    assert problems == ["publish: save the session first"]
    session = Session()
    assert cls().validate(ActionContext(session=session, base_dir=str(tmp_path))) == [
        "publish: save the session first"
    ]
    session.save(tmp_path / "hero.tr")
    assert cls().validate(ActionContext(session=session, base_dir=str(tmp_path))) == []


def test_deliver_writes_a_versioned_bundle_beside_a_store(tmp_path):
    cls = registry.get_action("publish")
    session = Session()
    session.save(tmp_path / "hero.tr")
    publish_set = PublishSet.collect(session.file_path, session.document)
    ctx = ActionContext(session=session, base_dir=str(tmp_path))
    action = cls({"folder": "out"})
    action.deliver(publish_set, ctx)
    action.deliver(publish_set, ctx)
    assert (tmp_path / "out" / "hero_v001" / "hero.tr").exists()
    assert (tmp_path / "out" / "hero_v002" / "manifest.json").exists()
    assert (tmp_path / "out" / STORE_DIR).is_dir()
    assert action.summary() == "out"


def test_deliver_is_abstract_on_the_base():
    from tik.trigger.actions.publish.publish import PublishAction

    with pytest.raises(NotImplementedError):
        PublishAction().deliver(None, ActionContext())
```

- [ ] **Step 2: Write the Maya integration test**

```python
# tests/integration/trigger/test_publish_action_trigger.py
"""Build & Publish with the generic publish action writes a self-contained bundle."""

import json

import pytest
from maya import cmds

import tik.trigger as trigger
from tik.trigger.core.exceptions import SessionError
from tik.trigger.core.publish_set import MANIFEST, STORE_DIR, Store

MARK = "import maya.cmds as cmds\ncmds.createNode('transform', name='{name}')"


def _session(tmp_path):
    work = tmp_path / "work"
    (work / "scripts").mkdir(parents=True)
    (work / "scripts" / "mark.py").write_text(
        "import maya.cmds as cmds\n\n\ndef make():\n"
        "    cmds.createNode('transform', name='from_file')\n",
        encoding="utf-8",
    )
    rig = trigger.Session()
    rig.save(work / "hero.tr")
    rig.add("script", "lib", file_path="scripts/mark.py", code="mark.make()")
    rig.add("script", "inline", code=MARK.format(name="inline"))
    rig.publish.add("publish", "out", folder="publish")
    rig.save()
    return rig


def test_build_and_publish_writes_a_bundle_that_rebuilds_alone(tmp_path):
    rig = _session(tmp_path)
    rig.build(publish=True)
    bundle = tmp_path / "work" / "publish" / "hero_v001"
    assert (bundle / "hero.tr").exists()
    assert (bundle / "hero_rig.mb").exists()
    assert (bundle / "hero.trg").exists()
    manifest = json.loads((bundle / MANIFEST).read_text(encoding="utf-8"))
    assert [item["kind"] for item in manifest["artifacts"]] == ["session", "guides", "rig"]
    assert manifest["dependencies"][0]["original"] == "scripts/mark.py"
    assert not (tmp_path / "work" / "_publish_tmp").exists()

    # the published session builds on its own, from the store
    again = trigger.Session.open(str(bundle / "hero.tr"))
    again.build()
    assert cmds.objExists("from_file") and cmds.objExists("inline")


def test_second_publish_reuses_the_store(tmp_path):
    rig = _session(tmp_path)
    rig.build(publish=True)
    rig.build(publish=True)
    assert (tmp_path / "work" / "publish" / "hero_v002").exists()
    assert len(Store(tmp_path / "work" / "publish" / STORE_DIR).files()) == 1


def test_a_partial_build_still_refuses_to_publish(tmp_path):
    rig = _session(tmp_path)
    with pytest.raises(SessionError):
        rig.build(until="lib", publish=True)


def test_a_failing_delivery_keeps_the_temporaries(tmp_path, monkeypatch):
    from tik.trigger.actions.publish.publish import Publish
    from tik.trigger.core.exceptions import ActionExecutionError

    rig = _session(tmp_path)
    monkeypatch.setattr(Publish, "deliver", lambda self, s, c: 1 / 0)
    with pytest.raises(ActionExecutionError):
        rig.build(publish=True)
    assert (tmp_path / "work" / "_publish_tmp" / "hero_rig.mb").exists()
```

- [ ] **Step 3: Run both to verify failure**

Run: `mayapy -m pytest tests/unit/test_publish_action_unit_trigger.py -q` and `mayapy -m pytest tests/integration/trigger/test_publish_action_trigger.py -q`
Expected: FAIL with `NotFoundError: publish`.

- [ ] **Step 4: Write the action**

```python
# src/python/tik/trigger/actions/publish/publish.py
"""Publish the built rig: collect what the session needs, then deliver it.

``PublishAction`` is the base every publish destination subclasses. It runs
only as the tail of Build & Publish (the runner guarantees that), saves the
scene, exports the guides, builds a ``PublishSet`` and calls ``deliver``,
which is the one method a subclass writes. The generic ``publish`` action
delivers to a versioned folder with no version control system at all.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from tik.trigger.core import (
    Action,
    BoolField,
    FileField,
    register_action,
    registry,
    versioning,
)
from tik.trigger.core.action import ActionContext
from tik.trigger.core.document import BUILD
from tik.trigger.core.exceptions import ActionExecutionError
from tik.trigger.core.publish_set import STORE_DIR, PublishSet, write_bundle

TEMP_DIR = "_publish_tmp"


class PublishAction(Action):
    """Base class for publish destinations. Subclasses implement ``deliver``."""

    include_guides = BoolField(
        True, label="Include guides", help="Export the guides as a .trg element."
    )
    include_products = BoolField(
        True,
        label="Include products",
        help="Ask every build action for the files it wrote and publish them too.",
    )

    # --------------------------------------------------------- contract
    def deliver(self, publish_set: PublishSet, ctx: ActionContext) -> None:
        """Send ``publish_set`` where this action publishes. Paths only."""
        raise NotImplementedError

    # ----------------------------------------------------------- steps
    def validate(self, ctx: ActionContext) -> list[str]:
        problems = super().validate(ctx)
        session = ctx.session
        if session is None or session.file_path is None:
            problems.append(f"{self.action_type or 'publish'}: save the session first")
        return problems

    def run(self, ctx: ActionContext) -> None:
        session = ctx.session
        if session is None or session.file_path is None:
            raise ActionExecutionError("save the session first")
        name = Path(session.file_path).stem
        temp = Path(ctx.base_dir) / TEMP_DIR
        temp.mkdir(parents=True, exist_ok=True)
        rig = temp / f"{name}_rig.mb"
        _save_scene(rig)
        guides: Optional[Path] = None
        if self.include_guides:
            guides = temp / f"{name}.trg"
            session.guides.export(guides)
        publish_set = self.collect(ctx, rig=rig, guides=guides)
        try:
            self.deliver(publish_set, ctx)
        except ActionExecutionError:
            raise
        except Exception as error:  # noqa: BLE001 - wrap with the action's name
            raise ActionExecutionError(f"{self.display_label()}: {error}") from error
        shutil.rmtree(temp, ignore_errors=True)
        ctx.log(f"Published {name}")

    def collect(
        self,
        ctx: ActionContext,
        rig: Optional[Path] = None,
        guides: Optional[Path] = None,
    ) -> PublishSet:
        """The publish set for the session, products included when asked."""
        session = ctx.session
        products = []
        if self.include_products:
            for path, node, _parent in session.document.walk(BUILD):
                if not node.enabled or not registry.is_action_registered(node.type):
                    continue
                action_cls = registry.get_action(node.type)
                if not action_cls.has_products():
                    continue
                node_ctx = ActionContext(
                    session=session,
                    events=ctx.events,
                    base_dir=ctx.base_dir,
                    path=path,
                    rig=ctx.rig,
                    scripts=ctx.scripts,
                )
                products.extend(action_cls(settings=node.settings).products(node_ctx))
        return PublishSet.collect(
            session.file_path,
            session.document,
            rig=rig,
            guides=guides,
            products=products,
        )


def _save_scene(target: Path) -> None:
    """Save the current scene as ``target`` (binary) and restore its name."""
    from maya import cmds

    original = cmds.file(query=True, sceneName=True) or ""
    cmds.file(rename=str(target))
    try:
        cmds.file(save=True, type="mayaBinary", force=True)
    finally:
        cmds.file(rename=original)


@register_action("publish", category="finish", icon="publish", scope="publish")
class Publish(PublishAction):
    """Publish into a versioned folder. No version control system needed.

    Writes ``<folder>/<session>_v###/`` holding the session with its paths
    rewritten, the guides, the rig scene and a manifest; unchanged files are
    shared through ``<folder>/_store``.
    """

    label = "Publish"

    folder = FileField(
        "publish",
        mode="dir",
        label="Publish folder",
        help="Where versions go, relative to the session folder when not absolute.",
    )

    def summary(self) -> str:
        return self.folder

    def deliver(self, publish_set: PublishSet, ctx: ActionContext) -> None:
        folder = ctx.resolve(self.folder)
        folder.mkdir(parents=True, exist_ok=True)
        target = versioning.next_version(folder / publish_set.name)
        write_bundle(publish_set, target, store_root=folder / STORE_DIR)
        ctx.log(f"Bundle written: {target}")
```

`versioning.next_version(folder / "hero")` has no suffix, so `versions()` globs `hero_v*` and matches the version folders; the unit test above proves it. If `tik.trigger.core` does not export `registry`, import it as `from tik.trigger.core import registry` on its own line (it does: see `core/__init__.py`).

- [ ] **Step 5: Draw `publish.svg`**

A box with an outbound arrow, full colour, per `AI/icon_rules.md`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24"><g fill="#f7efd8" stroke="#f7efd8" stroke-width="2.3" stroke-linejoin="round" stroke-linecap="round"><path d="M4 9.5 H15.5 V20 H4 Z"/><path d="M12 3.5 L20.5 3.5 L20.5 12"/><path d="M20.5 3.5 L13 11"/></g><g stroke="none"><path d="M4 9.5 H15.5 V20 H4 Z" fill="#6fb36a"/><path d="M4 9.5 H15.5 V12.2 H4 Z" fill="#4f8f4b"/></g><g fill="none" stroke="#f0b45c" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3.5 L20.5 3.5 L20.5 12"/><path d="M20.5 3.5 L13 11"/></g></svg>
```

Run `mayapy -m pytest tests/unit/test_icon_assets.py -q` and fix whatever the lint reports.

- [ ] **Step 6: Run tests and lint**

Run: `mayapy -m pytest tests/unit/test_publish_action_unit_trigger.py tests/unit/test_icon_assets.py tests/unit/test_import_boundaries.py -q`, then `mayapy -m pytest tests/integration/trigger/test_publish_action_trigger.py tests/integration/trigger/test_publish_phase_trigger.py -q`, then `make lint`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/python/tik/trigger/actions/publish tests/unit/test_publish_action_unit_trigger.py tests/integration/trigger/test_publish_action_trigger.py
git commit -m "Add PublishAction and the generic folder publish action"
```

---

### Task 8: The `vcs.provider` preference

**Files:**
- Create: `src/python/tik/trigger/config/pages/vcs.py`
- Modify: `src/python/tik/trigger/config/pages/__init__.py` (import the page)
- Test: `tests/unit/test_trigger_prefs.py` (extend)

**Interfaces:**
- Produces: page `vcs` (label "Version Control", order 50) with `provider = StringField("")`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_trigger_prefs.py`:

```python
def test_vcs_page_holds_the_preferred_provider():
    from tik.shared.prefs import registry as pages

    page = pages.page("vcs")
    assert page.label == "Version Control"
    assert page.fields()["provider"].default == ""
```

(Read the top of that test file first and use its existing fixtures for a clean registry if it has any.)

- [ ] **Step 2: Run to verify failure**

Run: `mayapy -m pytest tests/unit/test_trigger_prefs.py -q`
Expected: FAIL with `NotFoundError`/`KeyError: vcs`.

- [ ] **Step 3: Write the page**

```python
# src/python/tik/trigger/config/pages/vcs.py
"""Version control preferences: which provider to use when several are installed."""

from __future__ import annotations

from tik.core.fields import FieldGroup, StringField
from tik.shared.prefs import PrefPage, register_page


@register_page
class VcsPrefs(PrefPage):
    """Which version control system Trigger talks to."""

    name, label, order = "vcs", "Version Control", 50

    PROVIDER = FieldGroup("Provider")

    provider = StringField(
        "",
        group=PROVIDER,
        label="Preferred provider",
        help=(
            "The registered provider name to use when more than one is "
            "available (for example tik_manager). Empty picks the first."
        ),
    )
```

Import it in `config/pages/__init__.py` the same way the other pages are imported.

- [ ] **Step 4: Run tests, lint, commit**

Run: `mayapy -m pytest tests/unit/test_trigger_prefs.py tests/unit/test_import_boundaries.py -q`, `make lint`

```bash
git add src/python/tik/trigger/config/pages
git add tests/unit/test_trigger_prefs.py
git commit -m "Add the preferred version control provider preference"
```

---

### Task 9: Shared widgets: the VCS button on file fields, clickable status fields

**Files:**
- Modify: `src/python/tik/shared/ui/versioned_field.py`
- Modify: `src/python/tik/shared/ui/fields.py` (`FormBuilder`)
- Modify: `src/python/tik/shared/ui/status.py`
- Test: `tests/ui/test_vcs_widgets.py`

**Interfaces:**
- `VersionedFileField(..., vcs: Optional[tuple[str, Callable]] = None)`: `(tooltip, on_click)`; when given, a `QToolButton` named `VcsButton` with text `"⇩"` and that tooltip is added after Browse and `on_click(widget)` runs on click. Attribute `vcs_button` (None otherwise).
- `FormBuilder(..., file_vcs: Optional[tuple[str, Callable]] = None)`: `(tooltip, handler)` where `handler(field_name, field, widget)`; every file widget gets `vcs=(tooltip, lambda w: handler(name, field, w))`.
- `StatusFields.set_click(name, callback)` and `StatusFields.set_color(name, color: str)` (`""` resets the stylesheet).

- [ ] **Step 1: Write the failing tests**

```python
# tests/ui/test_vcs_widgets.py
"""The shared widgets only know they have a second button and a clickable field."""

from tik.core.fields import FileField, Schema
from tik.shared.ui.fields import FormBuilder
from tik.shared.ui.Qt import QtCore, QtGui, QtWidgets
from tik.shared.ui.status import StatusFields
from tik.shared.ui.versioned_field import VersionedFileField


class Settings(Schema):
    script = FileField("", extensions=[".py"], kind="script")


def test_versioned_field_has_no_vcs_button_by_default(qapp):
    field = VersionedFileField([".py"])
    assert field.vcs_button is None


def test_versioned_field_vcs_button_calls_back_with_the_widget(qapp):
    seen = []
    field = VersionedFileField([".py"], vcs=("From Tik Manager", seen.append))
    assert field.vcs_button.toolTip() == "From Tik Manager"
    assert field.vcs_button.objectName() == "VcsButton"
    field.vcs_button.click()
    assert seen == [field]


def test_form_builder_passes_field_name_and_field_to_the_handler(qapp):
    seen = []
    form = FormBuilder(
        Settings(),
        file_vcs=("From Tik Manager", lambda name, field, widget: seen.append((name, field.kind, widget))),
    )
    widget = form.widget("script")
    widget.vcs_button.click()
    assert seen[0][:2] == ("script", "script") and seen[0][2] is widget


def test_status_field_click_and_color(qapp):
    strip = QtWidgets.QWidget()
    status = StatusFields(strip, ("vcs",))
    seen = []
    status.set_click("vcs", lambda: seen.append("clicked"))
    status.set_color("vcs", "#f0b45c")
    assert "#f0b45c" in status.labels["vcs"].styleSheet()
    QtWidgets.QApplication.sendEvent(
        status.labels["vcs"],
        QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonPress,
            QtCore.QPointF(1, 1),
            QtCore.Qt.LeftButton,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        ),
    )
    assert seen == ["clicked"]
    status.set_color("vcs", "")
    assert status.labels["vcs"].styleSheet() == ""
```

- [ ] **Step 2: Run to verify failure**

Run: `$env:TIK_TESTS_NO_MAYA=1; $env:QT_QPA_PLATFORM="offscreen"; mayapy -m pytest tests/ui/test_vcs_widgets.py -q`
Expected: FAIL (`vcs_button` missing).

- [ ] **Step 3: Implement**

`versioned_field.py`: add the `vcs` keyword to `__init__` and, after the `extra_button` block:

```python
        self.vcs_button = None
        if vcs is not None:
            tooltip, on_click = vcs
            self.vcs_button = QtWidgets.QToolButton()
            self.vcs_button.setObjectName("VcsButton")
            self.vcs_button.setText("⇩")
            self.vcs_button.setToolTip(tooltip)
            self.vcs_button.clicked.connect(lambda: on_click(self))
            layout.addWidget(self.vcs_button)
```

`fields.py`: add `file_vcs: Optional[tuple] = None` to `FormBuilder.__init__` (document it in the docstring: "``(tooltip, handler(field_name, field, widget))``: a second button on every file field"), store `self.file_vcs = file_vcs`, and in the `kind == "file"` branch build the widget with:

```python
            vcs = None
            if self.file_vcs is not None:
                tooltip, handler = self.file_vcs
                vcs = (tooltip, lambda w, n=name, f=field: handler(n, f, w))
            widget = VersionedFileField(
                getattr(field, "extensions", ()),
                getattr(field, "mode", "open"),
                extra=extra,
                browser=self.file_browser,
                base_dir=self.base_dir,
                vcs=vcs,
            )
```

`status.py`: add

```python
    def set_click(self, name: str, callback) -> None:
        """Run ``callback`` when the field called ``name`` is clicked."""
        label = self.labels[name]
        label.setCursor(QtCore.Qt.PointingHandCursor)
        label.mousePressEvent = lambda _event: callback()  # type: ignore[assignment]

    def set_color(self, name: str, color: str) -> None:
        """Tint the field's text; ``""`` restores the theme colour."""
        self.labels[name].setStyleSheet(f"QLabel {{ color: {color}; }}" if color else "")
```

(import `QtCore` from `tik.shared.ui.Qt`).

- [ ] **Step 4: Run the UI suites touching these widgets, lint, commit**

Run: `$env:TIK_TESTS_NO_MAYA=1; $env:QT_QPA_PLATFORM="offscreen"; mayapy -m pytest tests/ui/test_vcs_widgets.py tests/ui/test_form_builder.py tests/ui/test_trigger_widgets.py -q`, `make lint`

```bash
git add src/python/tik/shared/ui/versioned_field.py src/python/tik/shared/ui/fields.py src/python/tik/shared/ui/status.py tests/ui/test_vcs_widgets.py
git commit -m "Give file fields an optional VCS button and status fields a click"
```

---

### Task 10: Trigger's VCS UI surface

**Files:**
- Create: `src/python/tik/trigger/ui/vcs_ui.py`
- Modify: `src/python/tik/trigger/ui/settings_panel.py:70-78` (pass `file_vcs`)
- Modify: `src/python/tik/trigger/ui/session_view.py:610-638` (the publish submenu)
- Modify: `src/python/tik/trigger/ui/main.py` (host attach, File submenu, status chip, preference push)
- Modify: `src/python/tik/trigger/ui/designer/commands.py` (`_pick` uses `vcs_ui.pick_file`)
- Test: `tests/ui/test_vcs_ui.py`

**Interfaces (`tik.trigger.ui.vcs_ui`):**

```python
def provider() -> Optional[VersionControl]                    # vcs.active()
def kind_of(field) -> str                                     # kinds.kind_for(field.extensions, field.kind)
def field_actions(field_name, field, widget, session_dir: str) -> list[tuple[str, Callable]]
    # "Browse <label>…" when provider.supports("browse");
    # "Publish <file name> to <label>…" when the widget holds a value that resolves to an existing file and provider.supports("publish_file")
def show_field_menu(field_name, field, widget, session_dir) -> None
    # one entry: call it; several: QMenu popup under the button
def form_vcs_slot(session_dir: Callable[[], str]) -> Optional[tuple[str, Callable]]
    # None without a provider; else ("From <label>", handler) for FormBuilder(file_vcs=)
def publishable_files(handle, session) -> list[tuple[str, Path]]
    # (kind, absolute path) per non-empty file field of the handle's action, plus (FILE, path) for extra dependencies
def add_publish_submenu(menu, handle, session) -> Optional[QMenu]
    # "Publish to <label>" submenu, one entry per publishable file; None without provider/entries
def pick_file(parent, kind, extensions, mode, start="", caption="") -> str
    # provider with browse: a two-item popup (Browse… / From <label>…); else the Feedback dialog for mode
def build_file_submenu(window, file_menu) -> Optional[QMenu]
    # File > <label>: "Open from <label>…", "Save New Version", "Publish…", "Open <label>"; entries only for supported verbs
def chip(context: Optional[Context], provider) -> tuple[str, str]
    # (text, color): ("hero / rig_main · v003", "#9fd8b3") latest, "#f0b45c" older, ("Not a <label> work", "#f0b45c") for None; ("", "") without provider
def refresh_chip(window) -> None
```

The window:
- In `__init__` after `_build_shell`: `vcs.set_preferred(prefs_value("vcs", "provider") or None)`; then `vcs.host.attach(session=lambda: self.session, open=self.open_session, save_as=self._save_current_as, refresh=lambda: vcs_ui.refresh_chip(self), feedback=lambda: Feedback(self))`. `_save_current_as(path)` calls `self.save_session_as(str(path))` and returns the session's new `file_path`.
- `teardown()` calls `vcs.host.detach()`.
- `_build_file_menu`: after the "Reference Modules…" separator, `self.vcs_menu = vcs_ui.build_file_submenu(self, file_menu)`.
- `_build_status`: fields become `("references", "maya", "version", "vcs")`; `self.status.set_click("vcs", lambda: vcs.launch() if vcs.active() and vcs.active().supports("launch") else None)`.
- `_update_title` ends with `vcs_ui.refresh_chip(self)`.
- `_on_prefs_applied`: `if "vcs.provider" in changed: vcs.set_preferred(prefs_value("vcs", "provider") or None); vcs_ui.refresh_chip(self)`.

The menu entry "Publish…" calls `self._view_call("build_and_publish")` and is enabled only when the current session has at least one action in its publish list (`len(session.publish) > 0`); re-evaluated in `_sync_menu_state`.

Settings panel: `FormBuilder(..., file_vcs=vcs_ui.form_vcs_slot(base_dir))` where `base_dir` is the callable it already receives.

Session view: in `context_menu_actions`, after the Disable/Enable entry, `vcs_ui.add_publish_submenu(menu, handle, self.session)`.

Designer `_pick(mode)`: keep the `file_browser` branch; replace the `Feedback` branch with `return vcs_ui.pick_file(self, kinds.GUIDES, [GUIDE_EXTENSION], mode, self.last_guide_file, "Export guides" if mode == "save" else "Import guides")`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/ui/test_vcs_ui.py
"""Everything a provider adds to the window, driven with a stub provider."""

from pathlib import Path

import pytest
from test_pipeline_ui import _stub_designer

from tik.trigger import vcs
from tik.trigger.core.document import BUILD
from tik.trigger.ui import vcs_ui
from tik.trigger.ui.main import TriggerWindow
from tik.trigger.vcs.provider import Context, VersionControl


class Stub(VersionControl):
    label = "Stub VCS"
    calls: list = []
    picked = "D:/vcs/picked.py"
    ctx = None

    def available(self):
        return True

    def context(self, session_path):
        return self.ctx

    def browse(self, kind, extensions, mode):
        self.calls.append(("browse", kind, list(extensions), mode))
        return self.picked

    def new_version(self, host):
        self.calls.append(("new_version", host.session_path))
        return host.session_path

    def open(self, host):
        self.calls.append(("open",))
        return ""

    def publish_file(self, kind, path, host):
        self.calls.append(("publish_file", kind, Path(path).name))

    def launch(self, host):
        self.calls.append(("launch",))


@pytest.fixture
def stub():
    vcs.clear_providers()
    vcs.set_preferred(None)
    Stub.calls = []
    Stub.ctx = None
    vcs.register_provider("stub")(Stub)
    yield Stub
    vcs.clear_providers()
    vcs.host.detach()


@pytest.fixture
def window(qapp, stub):
    win = TriggerWindow(designer_factory=_stub_designer)
    win.show()
    yield win
    win.close()


def _menu(window, title):
    for action in window.menu_bar.actions():
        if action.text() == title:
            return action.menu()
    raise AssertionError(title)


def _entries(menu):
    return [a.text() for a in menu.actions() if not a.isSeparator()]


def test_without_a_provider_nothing_is_added(qapp):
    vcs.clear_providers()
    win = TriggerWindow(designer_factory=_stub_designer)
    try:
        assert win.vcs_menu is None
        assert win.status.text("vcs") == ""
        assert vcs_ui.form_vcs_slot(lambda: "") is None
    finally:
        win.close()


def test_the_window_attaches_itself_as_the_host(window):
    assert vcs.host.session is window.session
    window.close()
    window.teardown()
    assert vcs.host.session is None


def test_file_menu_gets_the_provider_submenu(window, stub):
    file_menu = _menu(window, "&File")
    assert "Stub VCS" in _entries(file_menu)
    entries = _entries(window.vcs_menu)
    assert entries == ["Open from Stub VCS…", "Save New Version", "Publish…", "Open Stub VCS"]
    publish = next(a for a in window.vcs_menu.actions() if a.text() == "Publish…")
    assert publish.isEnabled() is False  # no publish action in the session
    window.session.publish.add("publish", "out")
    window._sync_menu_state()
    assert publish.isEnabled() is True
    next(a for a in window.vcs_menu.actions() if a.text() == "Open from Stub VCS…").trigger()
    next(a for a in window.vcs_menu.actions() if a.text() == "Open Stub VCS").trigger()
    assert ("open",) in stub.calls and ("launch",) in stub.calls


def test_status_chip_follows_the_context(window, stub, tmp_path):
    stub.ctx = None
    window.session.save(tmp_path / "hero.tr")
    vcs_ui.refresh_chip(window)
    assert window.status.text("vcs") == "Not a Stub VCS work"
    stub.ctx = Context(label="hero / rig", version=3, is_latest=False)
    vcs_ui.refresh_chip(window)
    assert window.status.text("vcs") == "hero / rig · v003"
    assert "#f0b45c" in window.status.labels["vcs"].styleSheet()
    stub.ctx = Context(label="hero / rig", version=4, is_latest=True)
    vcs_ui.refresh_chip(window)
    assert "#9fd8b3" in window.status.labels["vcs"].styleSheet()


def test_field_actions_browse_and_publish(window, stub, tmp_path):
    from tik.core.fields import FileField
    from tik.shared.ui.versioned_field import VersionedFileField

    field = FileField("", extensions=[".py"], kind="script")
    widget = VersionedFileField([".py"])
    entries = vcs_ui.field_actions("file_path", field, widget, str(tmp_path))
    assert [text for text, _ in entries] == ["Browse Stub VCS…"]
    entries[0][1]()
    assert widget.value() == "D:/vcs/picked.py"
    assert stub.calls[-1] == ("browse", "script", [".py"], "open")

    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    widget.setValue("a.py")
    entries = vcs_ui.field_actions("file_path", field, widget, str(tmp_path))
    assert [text for text, _ in entries] == ["Browse Stub VCS…", "Publish a.py to Stub VCS…"]
    entries[1][1]()
    assert stub.calls[-1] == ("publish_file", "script", "a.py")


def test_settings_panel_file_fields_carry_the_button(window, stub, tmp_path):
    window.session.save(tmp_path / "hero.tr")
    handle = window.session.add("script", "lib", file_path="a.py")
    view = window.current_view
    view.select_path(handle.path) if hasattr(view, "select_path") else view.settings.set_handle(handle)
    widget = view.settings.form.widget("file_path")
    assert widget.vcs_button is not None
    assert widget.vcs_button.toolTip() == "From Stub VCS"


def test_pipeline_right_click_lists_the_publishable_files(window, stub, tmp_path):
    window.session.save(tmp_path / "hero.tr")
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    handle = window.session.add("script", "lib", file_path="a.py")
    view = window.current_view
    labels = [a.text() for a in view.context_menu_actions(BUILD, handle)]
    assert "Publish to Stub VCS" in labels
    submenu = next(a for a in view._menu.actions() if a.text() == "Publish to Stub VCS").menu()
    assert _entries(submenu) == ["a.py"]
    submenu.actions()[0].trigger()
    assert stub.calls[-1] == ("publish_file", "script", "a.py")
    inline = window.session.add("script", "inline", code="pass")
    labels = [a.text() for a in view.context_menu_actions(BUILD, inline)]
    assert "Publish to Stub VCS" not in labels


def test_pick_file_offers_the_provider(window, stub, monkeypatch):
    stub.picked = "D:/vcs/guides.trg"
    monkeypatch.setattr(vcs_ui, "_popup", lambda parent, entries: entries[1][1]())
    assert vcs_ui.pick_file(window, "guides", [".trg"], "open") == "D:/vcs/guides.trg"
    assert stub.calls[-1] == ("browse", "guides", [".trg"], "open")
```

Read `tests/ui/test_pipeline_ui.py` for how a handle is selected in the view (the settings panel method name) and fix the one line in `test_settings_panel_file_fields_carry_the_button` accordingly.

- [ ] **Step 2: Run to verify failure**

Run: `$env:TIK_TESTS_NO_MAYA=1; $env:QT_QPA_PLATFORM="offscreen"; mayapy -m pytest tests/ui/test_vcs_ui.py -q`
Expected: FAIL (`vcs_ui` missing).

- [ ] **Step 3: Write `vcs_ui.py`**

```python
# src/python/tik/trigger/ui/vcs_ui.py
"""Everything a version control provider adds to Trigger's windows.

Each piece appears only when ``vcs.active()`` returns a provider, and reads
with the provider's own label: "from Tik Manager…", never "from VCS". The
shared widgets know nothing of this; they only expose a second button.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from tik.shared.ui.feedback import Feedback
from tik.shared.ui.Qt import QtGui, QtWidgets
from tik.trigger import vcs
from tik.trigger.core import ActionContext, kinds
from tik.trigger.vcs.provider import Context, VersionControl

LATEST = "#9fd8b3"
OLDER = "#f0b45c"


def provider() -> Optional[VersionControl]:
    """The active provider, or None."""
    return vcs.active()


def kind_of(field) -> str:
    """The kind a file field browses and publishes as."""
    return kinds.kind_for(getattr(field, "extensions", ()), getattr(field, "kind", ""))


# ------------------------------------------------------------ file fields
def _resolve(value: str, session_dir: str) -> Optional[Path]:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute() and session_dir:
        path = Path(session_dir) / path
    return path


def field_actions(field_name, field, widget, session_dir: str) -> list:
    """``(text, callable)`` entries for a file field's VCS button."""
    active = provider()
    if active is None:
        return []
    label = active.display_label()
    entries = []
    if active.supports("browse"):

        def _browse():
            picked = active.browse(kind_of(field), list(field.extensions), field.mode)
            if picked:
                widget.setValue(picked)
                widget.changed.emit(picked)

        entries.append((f"Browse {label}…", _browse))
    resolved = _resolve(widget.value(), session_dir)
    if resolved is not None and resolved.exists() and active.supports("publish_file"):
        entries.append(
            (
                f"Publish {resolved.name} to {label}…",
                lambda: vcs.publish_file(kind_of(field), resolved),
            )
        )
    return entries


def _popup(parent, entries) -> None:
    menu = QtWidgets.QMenu(parent)
    for text, callback in entries:
        menu.addAction(text, callback)
    menu.exec_(QtGui.QCursor.pos())


def show_field_menu(field_name, field, widget, session_dir: str) -> None:
    """Run the one entry, or pop a menu when there are several."""
    entries = field_actions(field_name, field, widget, session_dir)
    if len(entries) == 1:
        entries[0][1]()
    elif entries:
        _popup(widget, entries)


def form_vcs_slot(session_dir: Callable[[], str]) -> Optional[tuple]:
    """The ``FormBuilder(file_vcs=)`` argument, or None without a provider."""
    active = provider()
    if active is None:
        return None
    return (
        f"From {active.display_label()}",
        lambda name, field, widget: show_field_menu(name, field, widget, session_dir()),
    )


# ---------------------------------------------------------- pipeline rows
def publishable_files(handle, session) -> list:
    """``(kind, path)`` for every existing file the handle's action names."""
    action = handle.action_class(settings=dict(handle.settings))
    ctx = ActionContext(session=session, base_dir=session.directory, path=handle.path)
    found = []
    seen = set()
    for name, field in action.file_fields().items():
        value = getattr(action, name)
        if not value:
            continue
        path = ctx.resolve(value)
        if path.exists():
            found.append((kind_of(field), path))
            seen.add(path)
    for path in action.dependencies(ctx):
        if path not in seen and path.exists():
            found.append((kinds.FILE, path))
    return found


def add_publish_submenu(menu, handle, session):
    """Add "Publish to <label>" with one entry per file; None when nothing applies."""
    active = provider()
    if active is None or handle is None or not active.supports("publish_file"):
        return None
    files = publishable_files(handle, session)
    if not files:
        return None
    submenu = menu.addMenu(f"Publish to {active.display_label()}")
    for kind, path in files:
        submenu.addAction(path.name, lambda k=kind, p=path: vcs.publish_file(k, p))
    return submenu


# ------------------------------------------------------------- pickers
def pick_file(parent, kind, extensions, mode, start: str = "", caption: str = "") -> str:
    """A path from the plain dialog or, when a provider browses, from either."""
    active = provider()
    dialog = Feedback(parent)

    def _plain() -> str:
        if mode == "save":
            return dialog.browse_save(caption or "Save", start, tuple(extensions))
        if mode == "dir":
            return dialog.browse_dir(caption or "Choose folder", start)
        return dialog.browse_open(caption or "Open", start, tuple(extensions))

    if active is None or not active.supports("browse"):
        return _plain()
    result = {"path": ""}

    def _from_vcs():
        result["path"] = active.browse(kind, list(extensions), mode)

    def _from_disk():
        result["path"] = _plain()

    _popup(parent, [("Browse…", _from_disk), (f"From {active.display_label()}…", _from_vcs)])
    return result["path"]


# ----------------------------------------------------------------- window
def build_file_submenu(window, file_menu):
    """File > <label>, or None without a provider."""
    active = provider()
    if active is None:
        return None
    label = active.display_label()
    submenu = file_menu.addMenu(label)
    icon = active.icon_path()
    if icon is not None:
        submenu.setIcon(QtGui.QIcon(str(icon)))
    if active.supports("open"):
        submenu.addAction(f"Open from {label}…", lambda: vcs.open())
    if active.supports("new_version"):
        submenu.addAction("Save New Version", lambda: vcs.new_version())
    window.vcs_publish_action = submenu.addAction(
        "Publish…", lambda: window._view_call("build_and_publish")
    )
    window.vcs_publish_action.setToolTip(
        "Runs Build & Publish. Add a publish action to the publish list first."
    )
    if active.supports("launch"):
        submenu.addAction(f"Open {label}", lambda: vcs.launch())
    return submenu


def sync_publish_entry(window) -> None:
    """Enable "Publish…" only when the session has something in its publish list."""
    action = getattr(window, "vcs_publish_action", None)
    if action is None:
        return
    session = window.session
    action.setEnabled(session is not None and len(session.publish) > 0)


def chip(context: Optional[Context], active: Optional[VersionControl]) -> tuple:
    """``(text, color)`` for the status chip."""
    if active is None:
        return "", ""
    if context is None:
        return f"Not a {active.display_label()} work", OLDER
    text = context.label
    if context.version is not None:
        text += f" · v{context.version:03d}"
    return text, (LATEST if context.is_latest else OLDER)


def refresh_chip(window) -> None:
    """Re-read the provider's context for the active session and paint the chip."""
    active = provider()
    context = None
    if active is not None and active.supports("context"):
        context = active.context(vcs.host.session_path)
    text, color = chip(context, active)
    window.status.set("vcs", text)
    window.status.set_color("vcs", color)
    if context is not None:
        window.status.labels["vcs"].setToolTip(context.detail)
```

- [ ] **Step 4: Wire the window, panel, view and designer** as listed under Interfaces. In `_sync_menu_state` add `vcs_ui.sync_publish_entry(self)` at the end. `PhaseView.__len__` exists (handles.py:288), so `len(session.publish)` works.

- [ ] **Step 5: Run the UI suite, lint, commit**

Run: `$env:TIK_TESTS_NO_MAYA=1; $env:QT_QPA_PLATFORM="offscreen"; mayapy -m pytest tests/ui -q` and `mayapy -m pytest tests/unit/test_import_boundaries.py tests/unit/test_dialog_boundaries.py -q`, `make lint`
Expected: PASS (all of `tests/ui`, since `test_menus.py` asserts the File menu entries and may need the new submenu title accounted for).

```bash
git add src/python/tik/trigger/ui tests/ui/test_vcs_ui.py
git commit -m "Add the version control UI surface: field button, menu, chip, right-click"
```

---

### Task 11: The integrator's guide and CLAUDE.md

**Files:**
- Create: `docs/trigger/integrating-version-control.md`
- Test: `tests/unit/test_integration_guide.py`
- Modify: `CLAUDE.md` (the tik.trigger status paragraph and the tests list)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_integration_guide.py
"""The integrator's guide compiles, and quotes the shipped FolderProvider verbatim."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "trigger" / "integrating-version-control.md"
FOLDER = ROOT / "src" / "python" / "tik" / "trigger" / "vcs" / "folder.py"


def _blocks():
    text = GUIDE.read_text(encoding="utf-8")
    return re.findall(r"```python\n(.*?)```", text, flags=re.S)


def test_the_guide_exists_and_covers_every_section():
    text = GUIDE.read_text(encoding="utf-8")
    for heading in (
        "## 1. What Trigger asks of a version control system",
        "## 2. Getting your code loaded",
        "## 3. The provider contract",
        "## 4. Kinds",
        "## 5. Writing a publish action",
        "## 6. Making an action publishable",
        "## 7. A complete minimal provider",
        "## 8. The tik_manager4 integration",
    ):
        assert heading in text, heading


def test_every_python_block_compiles():
    blocks = _blocks()
    assert len(blocks) >= 6
    for index, block in enumerate(blocks):
        compile(block, f"<guide block {index}>", "exec")


def test_the_folder_provider_is_quoted_verbatim():
    shipped = FOLDER.read_text(encoding="utf-8").strip()
    assert any(block.strip() == shipped for block in _blocks())
```

- [ ] **Step 2: Write the guide**

Write `docs/trigger/integrating-version-control.md` with exactly these eight `##` headings (numbered as in the test), for a reader who has never opened Trigger's source. Content per section, with real code blocks:

1. **What Trigger asks of a version control system**: the three flows (rig publish at the tail of Build & Publish; element publish through the VCS's own dialog; loading through browse and the status chip); the guarantee that a `.tr` stores plain paths and builds without any VCS.
2. **Getting your code loaded**: the `<root>/<name>/<name>.py` layout, `TRIGGER_PLUGIN_PATH`, `tik.trigger.add_plugin_path()`, `@register_provider("name")` and `@register_action("name", scope="publish")`, and that `tik.trigger.load_plugins()` (which `tik.trigger.ui.main.show()` calls) imports them. A code block showing a userSetup snippet.
3. **The provider contract**: the `VersionControl` class with every verb, its default, and what the UI does when the verb is left alone (`supports`); `Context`; the `host` object with every attribute; that a provider is instantiated once and `available()` is called often, so keep it cheap.
4. **Kinds**: the vocabulary, `EXTENSIONS`, `kind_for`, `FileField(kind=)`.
5. **Writing a publish action**: `PublishAction`, `deliver(publish_set, ctx)`, the `PublishSet` fields, the bundle layout, the manifest JSON, `write_bundle`, `Store`, `clean`, and a code block of a minimal subclass that copies the bundle somewhere.
6. **Making an action publishable**: `FileField(kind=)`, `dependencies(ctx)`, `products(ctx)` with a skinweights-shaped example.
7. **A complete minimal provider**: one sentence, then `src/python/tik/trigger/vcs/folder.py` quoted verbatim (copy the whole file, including its module docstring, as one ```python block; the test compares the stripped text).
8. **The tik_manager4 integration**: a walk through `tik_manager4/dcc/trigger3` naming each file and which piece of the contract it implements (from the plan's file map for Tasks 12-14).

- [ ] **Step 3: Update CLAUDE.md**

In the tik.trigger status paragraph, add one sentence group after the test-rig sentences: "Since the 2026-09-08 pass Trigger has a **version control scaffold** (`tik/trigger/vcs`): a `VersionControl` provider contract implemented from outside the repo (`TRIGGER_PLUGIN_PATH` plugins, `@register_provider`), a `host` object the outside world drives, a pure `PublishSet` in `core/publish_set.py` that bundles a session with its dependencies through a flat content-addressed `_store`, a `PublishAction` base whose subclasses only write `deliver`, the generic `publish` action (versioned folder, no VCS), and an additive UI surface (a second button on file fields, **File > <provider>**, a status chip, a right-click publish submenu). Fields store plain paths; nothing on the build path imports `vcs`. tik_manager4 implements it as `dcc/trigger3` in its own repository. Integrators start at `docs/trigger/integrating-version-control.md`." Add the spec to the design specs list and the new test files to the tests list.

- [ ] **Step 4: Run, lint, commit**

Run: `mayapy -m pytest tests/unit/test_integration_guide.py -q`, `make lint`

```bash
git add docs/trigger/integrating-version-control.md tests/unit/test_integration_guide.py CLAUDE.md
git commit -m "Write the version control integrator's guide"
```

---

## tik_manager4 side

The next three tasks work in `D:\dev\tik_manager4` on branch `TW-trigger3-integration-test` (`git -C D:\dev\tik_manager4 branch --show-current` must print that; do not switch branches). tikworks must be importable: set `$env:PYTHONPATH="D:\dev\tikworks\src\python;D:\dev\tik_manager4"` and run the tests with `mayapy -m pytest tests/test_trigger3.py -q` from `D:\dev\tik_manager4` (mayapy so `import maya` works without a running scene; Maya standalone is never initialised). Commit in that repository with the same trailer.

`Main.dcc = dcc.Dcc()` is a class attribute created when `tik_manager4.objects.main` is imported, which is why `tik_manager4.initialize("trigger3")` reloads that module: it sets `TIK_DCC`, and `tik_manager4/dcc/__init__.py` imports the `Dcc` class for that name at import time.

### Task 12: `dcc/trigger3`: the DCC adapter, extractors and ingests

**Files (in tik_manager4):**
- Modify: `tik_manager4/dcc/__init__.py`
- Create: `tik_manager4/dcc/trigger3/__init__.py`, `main.py`, `_host.py`
- Create: `tik_manager4/dcc/trigger3/{extract,ingest,validate,extension}/__init__.py` (copy the collector code from `tik_manager4/dcc/trigger/<same>/__init__.py`)
- Create: `tik_manager4/dcc/trigger3/extract/source.py`, `rig.py`, `guides.py`
- Create: `tik_manager4/dcc/trigger3/ingest/source.py`, `guides.py`
- Create: `tik_manager4/dcc/trigger3/setup/how-to-install.txt`, `setup/icons/trigger3.png` (copy `dcc/trigger/setup/icons/trigger.png`)
- Test: `tests/test_trigger3.py`

**Interfaces:**
- `tik_manager4.dcc.trigger3._host.host()` returns `tik.trigger.vcs.host` (one import site, so the tikworks import lives in one file).
- `Dcc(MainCore)`: `name = "trigger3"`, `formats = [".tr"]`, `preview_enabled = False`; forwards to the host as spec section 9 says; `get_dcc_version()` returns `tik.trigger.VERSION`; `generate_thumbnail(path, w, h)` delegates to `tik_manager4.dcc.standalone.main.Dcc.text_to_image("TR", path, w, h)`; `get_main_window()` returns `tik.shared.ui.qtmaya.get_main_window()` inside a try (None on failure).
- Extractors carry `publish_set = None`; `set_publish_set(publish_set)` sets it. `Source` is `bundled = True`, `bundle_match_id = 31`; `Rig` extension `.mb`; `Guides` extension `.trg`. Without a set they fall back to the host session (`Source` collects `PublishSet.collect(session.file_path, session.document, guides=<temp .trg>)`; `Rig` builds and saves; `Guides` exports).
- Ingests: `Source` (`bundle = True`, `bundle_match_id = 31`, `valid_extensions = [".tr"]`) opens the `.tr` inside the bundle folder through the host; `Guides` (`valid_extensions = [".trg"]`) imports into `host.session.guides`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_trigger3.py
"""The trigger3 DCC: Trigger through its version control host.

Run under mayapy with tikworks on PYTHONPATH:
    $env:PYTHONPATH="D:\dev\tikworks\src\python;D:\dev\tik_manager4"
    mayapy -m pytest tests/test_trigger3.py -q
"""

import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("tik.trigger", reason="tikworks is not on PYTHONPATH")

from tik.trigger import vcs  # noqa: E402
from tik.trigger.core.publish_set import PublishSet  # noqa: E402
from tik.trigger.session import Session  # noqa: E402


@pytest.fixture
def tik3(tmp_path):
    """tik_manager4 initialised for trigger3 with a throwaway project and user."""
    import tik_manager4

    common = tmp_path / "common"
    common.mkdir()
    user_path = Path.home() / "TikManager4"
    backup = tmp_path / "user_backup"
    if user_path.exists():
        shutil.copytree(str(user_path), str(backup))
        shutil.rmtree(str(user_path))
    user_path.mkdir(parents=True, exist_ok=True)
    tik = tik_manager4.initialize("trigger3", common_folder=str(common))
    tik.user.set("Admin", "1234")
    project = tmp_path / "project"
    tik.create_project(str(project), structure_template="empty")
    tik.set_project(str(project))
    yield tik
    vcs.host.detach()
    shutil.rmtree(str(user_path), ignore_errors=True)
    if backup.exists():
        shutil.copytree(str(backup), str(user_path))


def _rig_work(tik3, tmp_path, name="hero"):
    sub = tik3.project.create_sub_project("assets", mode="asset", parent_path="")
    task = tik3.project.create_task("hero", categories=["Rig"], parent_path=sub.path)
    definitions = tik3.project.category_definitions
    rig = dict(definitions.get_property("Rig"))
    rig["extracts"] = ["source", "rig", "guides"]
    definitions.edit_property("Rig", rig)
    definitions.apply_settings(force=True)
    session = Session()
    vcs.host.attach(session=session)
    work = task.categories["Rig"].create_work(name)
    assert work != -1
    return task, work, session


def test_dcc_forwards_to_the_host(tik3, tmp_path):
    session = Session()
    vcs.host.attach(session=session)
    dcc = tik3.dcc
    assert dcc.name == "trigger3" and dcc.formats == [".tr"]
    assert dcc.get_scene_file() == ""
    assert dcc.is_modified() is False
    saved = dcc.save_as(str(tmp_path / "hero.tr"))
    assert Path(saved).name == "hero.tr"
    assert dcc.get_scene_file().endswith("hero.tr")
    other = Session()
    other.save(tmp_path / "other.tr")
    dcc.open(str(tmp_path / "other.tr"))
    assert dcc.get_scene_file().endswith("other.tr")
    assert dcc.get_dcc_version()


def test_create_work_saves_the_session_as_a_tik_version(tik3, tmp_path):
    _task, work, session = _rig_work(tik3, tmp_path)
    assert session.file_path is not None and session.file_path.suffix == ".tr"
    assert work.versions[-1].file_format == ".tr"
    found, version = tik3.project.find_work_by_absolute_path(str(session.file_path))
    assert found.name == "hero" and version == 1


def test_extractors_write_from_a_prebuilt_publish_set(tik3, tmp_path):
    from tik_manager4.dcc.trigger3.extract.guides import Guides
    from tik_manager4.dcc.trigger3.extract.rig import Rig
    from tik_manager4.dcc.trigger3.extract.source import Source

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    session = Session()
    session.save(work_dir / "hero.tr")
    rig = work_dir / "hero_rig.mb"
    rig.write_bytes(b"rig")
    trg = work_dir / "hero.trg"
    trg.write_text("{}", encoding="utf-8")
    publish_set = PublishSet.collect(session.file_path, session.document, rig=rig, guides=trg)
    out = tmp_path / "out"
    for cls, suffix in ((Source, ""), (Rig, ".mb"), (Guides, ".trg")):
        extractor = cls()
        extractor.set_publish_set(publish_set)
        extractor.extract_folder = str(out)
        extractor.extract_name = "hero"
        extractor.version_string = "v001"
        extractor.extract()
        assert extractor.state == "success", extractor.message
        assert Path(extractor.resolve_output()).exists()
        assert extractor.resolve_output().endswith(suffix)
    bundle = Path(Source().resolve_output_for(out, "hero", "v001"))
    assert (bundle / "hero.tr").exists() and (bundle / "manifest.json").exists()


def test_source_ingest_opens_the_bundled_session(tik3, tmp_path):
    from tik_manager4.dcc.trigger3.ingest.source import Source

    bundle = tmp_path / "SOURCE_hero_v001"
    bundle.mkdir()
    Session().save(bundle / "hero.tr")
    session = Session()
    vcs.host.attach(session=session)
    ingest = Source()
    ingest.ingest_path = str(bundle)
    ingest.bring_in()
    assert ingest.state == "success"
    assert vcs.host.session_path.endswith("hero.tr")
```

`resolve_output_for(folder, name, version)` is a small helper on `Source` (bundled paths have no extension): it returns `Path(folder) / f"SOURCE_{name}_{version}"`, the same string `resolve_output()` produces once the properties are set. Check `ingest_path`'s setter: it demands a file for non-bundle ingests; with `bundle = True` set the folder path through the setter only if it accepts folders, else set `_file_path` directly in `Source.__init__`-adjacent code (read `ingest_core.py`: the setter always requires `is_file()`, so the trigger3 `Source` ingest overrides the `ingest_path` property to accept a folder).

- [ ] **Step 2: Run to verify failure**

Run (from `D:\dev\tik_manager4`): `mayapy -m pytest tests/test_trigger3.py -q`
Expected: FAIL with `ValueError: ... TIK_DCC ... trigger3`.

- [ ] **Step 3: Register the DCC name**

In `tik_manager4/dcc/__init__.py` add `"trigger3": [".tr"]` to `EXTENSION_DICT` (after `"trigger"`) and, before the final `else`:

```python
elif NAME == "trigger3":
    from tik_manager4.dcc.trigger3.main import Dcc
```

- [ ] **Step 4: Write `_host.py` and `main.py`**

```python
# tik_manager4/dcc/trigger3/_host.py
"""The one place trigger3 imports Trigger: its version control host."""


def host():
    """``tik.trigger.vcs.host``: the session, open, save and refresh."""
    from tik.trigger import vcs

    return vcs.host
```

```python
# tik_manager4/dcc/trigger3/main.py
"""Tik Manager's view of tik.trigger (workflow v3), through Trigger's VCS host."""

import logging

from tik_manager4.dcc.main_core import MainCore
from tik_manager4.dcc.trigger3 import extension, extract, ingest, validate
from tik_manager4.dcc.trigger3._host import host

LOG = logging.getLogger(__name__)


class Dcc(MainCore):
    """tik.trigger as a DCC. Every verb forwards to ``tik.trigger.vcs.host``."""

    name = "trigger3"
    formats = [".tr"]
    preview_enabled = False
    validations = validate.classes
    extracts = extract.classes
    ingests = ingest.classes
    extensions = extension.classes

    def post_save(self):
        host().refresh()

    def post_publish(self):
        host().refresh()

    def save_scene(self):
        current = host().session_path
        if current:
            host().save_as(current)

    def save_as(self, file_path, **extra_arguments):
        return str(host().save_as(file_path)).replace("\\", "/")

    def save_prompt(self):
        self.save_scene()
        return True  # anything falsy loops the caller

    def open(self, file_path, force=True, **extra_arguments):
        host().open(file_path)

    def is_modified(self):
        return host().is_modified

    def get_scene_file(self):
        return host().session_path

    def get_dcc_version(self):
        from tik.trigger import VERSION

        return VERSION

    def get_main_window(self):
        try:
            from tik.shared.ui.qtmaya import get_main_window

            return get_main_window()
        except Exception:  # noqa: BLE001 - headless
            return None

    def generate_thumbnail(self, file_path, width, height):
        from tik_manager4.dcc.standalone.main import Dcc as Standalone

        Standalone.text_to_image("TR", file_path, width, height)
        return file_path
```

`tik_manager4/dcc/trigger3/__init__.py` is empty. Copy the four collector `__init__.py` files from `dcc/trigger` (they glob the folder for subclasses of the matching core class) so `validate` and `extension` are empty collections.

- [ ] **Step 5: Write the extractors**

```python
# tik_manager4/dcc/trigger3/extract/source.py
"""Extract the Trigger session as a self-contained bundle (folder)."""

from pathlib import Path

from tik_manager4.dcc.extract_core import ExtractCore
from tik_manager4.dcc.trigger3._host import host

BUNDLE_MATCH_ID = 31
STORE_DIR = "_store"


class Source(ExtractCore):
    """The ``.tr`` with its paths rewritten, its dependencies deduplicated."""

    nice_name = "Trigger Session"
    color = (255, 255, 255)
    bundled = True
    bundle_match_id = BUNDLE_MATCH_ID

    def __init__(self):
        super().__init__()
        self.extension = ""
        self.publish_set = None

    def set_publish_set(self, publish_set):
        """Use a set the publish action already built instead of collecting."""
        self.publish_set = publish_set

    @staticmethod
    def resolve_output_for(folder, name, version):
        return (Path(folder) / f"SOURCE_{name}_{version}").as_posix()

    def _collect(self):
        from tik.trigger.core.publish_set import PublishSet

        session = host().session
        if session is None or session.file_path is None:
            raise RuntimeError("No saved Trigger session to publish.")
        guides = Path(self.extract_folder) / f"{self.extract_name}_{self.version_string}.trg"
        session.guides.export(guides)
        return PublishSet.collect(session.file_path, session.document, guides=guides)

    def _extract_default(self):
        from tik.trigger.core.publish_set import write_bundle

        publish_set = self.publish_set or self._collect()
        target = Path(self.resolve_output())
        write_bundle(publish_set, target, store_root=Path(self.extract_folder) / STORE_DIR)
```

```python
# tik_manager4/dcc/trigger3/extract/rig.py
"""Extract the built rig as a Maya binary scene."""

import shutil
from pathlib import Path

from tik_manager4.dcc.extract_core import ExtractCore
from tik_manager4.dcc.trigger3._host import host


class Rig(ExtractCore):
    """The rig scene: copied from the publish set, or built and saved."""

    nice_name = "Rig"
    color = (0, 50, 255)

    def __init__(self):
        super().__init__()
        self.extension = ".mb"
        self.publish_set = None

    def set_publish_set(self, publish_set):
        self.publish_set = publish_set

    def _extract_default(self):
        target = Path(self.resolve_output())
        if self.publish_set is not None:
            rig = next(item for item in self.publish_set.artifacts if item.kind == "rig")
            shutil.copy2(rig.path, target)
            return
        from maya import cmds

        session = host().session
        if session is None:
            raise RuntimeError("No Trigger session to build.")
        session.build()
        original = cmds.file(query=True, sceneName=True) or ""
        cmds.file(rename=str(target))
        try:
            cmds.file(save=True, type="mayaBinary", force=True)
        finally:
            cmds.file(rename=original)
```

```python
# tik_manager4/dcc/trigger3/extract/guides.py
"""Extract the guides as a .trg library file."""

import shutil
from pathlib import Path

from tik_manager4.dcc.extract_core import ExtractCore
from tik_manager4.dcc.trigger3._host import host


class Guides(ExtractCore):
    """The session's guides as a ``.trg``."""

    nice_name = "Guides"
    color = (212, 176, 74)

    def __init__(self):
        super().__init__()
        self.extension = ".trg"
        self.publish_set = None

    def set_publish_set(self, publish_set):
        self.publish_set = publish_set

    def _extract_default(self):
        target = Path(self.resolve_output())
        if self.publish_set is not None:
            guides = next(
                (item for item in self.publish_set.artifacts if item.kind == "guides"), None
            )
            if guides is None:
                raise RuntimeError("The publish set carries no guides.")
            shutil.copy2(guides.path, target)
            return
        session = host().session
        if session is None:
            raise RuntimeError("No Trigger session to export guides from.")
        session.guides.export(target)
```

- [ ] **Step 6: Write the ingests**

```python
# tik_manager4/dcc/trigger3/ingest/source.py
"""Open a published Trigger session bundle."""

from pathlib import Path

from tik_manager4.dcc.ingest_core import IngestCore
from tik_manager4.dcc.trigger3._host import host

BUNDLE_MATCH_ID = 31


class Source(IngestCore):
    """Open the ``.tr`` inside a published bundle folder."""

    nice_name = "Open Trigger Session"
    valid_extensions = [".tr"]
    bundle = True
    bundle_match_id = BUNDLE_MATCH_ID
    referencable = False

    @property
    def ingest_path(self):
        return self._file_path

    @ingest_path.setter
    def ingest_path(self, ingest_path):
        path = Path(ingest_path)
        if not path.exists():
            raise ValueError(f"Path does not exist: {ingest_path}")
        self._file_path = str(path)

    def _bring_in_default(self):
        path = Path(self.ingest_path)
        if path.is_dir():
            found = sorted(path.glob("*.tr"))
            if not found:
                raise ValueError(f"No .tr inside {path}")
            path = found[0]
        host().open(str(path))
```

```python
# tik_manager4/dcc/trigger3/ingest/guides.py
"""Import a published .trg into the active Trigger session's guides."""

from tik_manager4.dcc.ingest_core import IngestCore
from tik_manager4.dcc.trigger3._host import host


class Guides(IngestCore):
    """Add the modules of a ``.trg`` to the active session."""

    nice_name = "Import Guides"
    valid_extensions = [".trg"]
    referencable = False

    def _bring_in_default(self):
        session = host().session
        if session is None:
            raise RuntimeError("No Trigger session to import guides into.")
        session.guides.import_(self.ingest_path)
```

- [ ] **Step 7: Install notes**

`setup/how-to-install.txt`:

```
Tik Manager 4 - trigger3 (tik.trigger workflow v3)

1. Put tikworks on PYTHONPATH:  D:/dev/tikworks/src/python
2. Put this folder's plugins on TRIGGER_PLUGIN_PATH:
       <tik_manager4>/tik_manager4/dcc/trigger3/plugins
   or call tik.trigger.add_plugin_path(<that folder>) from userSetup.py before
   opening Trigger. Trigger then shows a "Tik Manager" submenu under File, a
   Tik Manager button on every file field, and a tik_publish action.
3. In the project's category definitions, the Rig category must list
   ["source", "rig", "guides"] under "extracts" for tik_publish to work.
4. Works of this DCC are .tr files; a publish is a SOURCE_ bundle folder, a
   rig .mb and a guides .trg, with shared dependencies under _store/.
```

- [ ] **Step 8: Run tests, commit (in tik_manager4)**

Run: `mayapy -m pytest tests/test_trigger3.py -q`
Expected: PASS. Then verify the old integration is untouched: `git -C D:\dev\tik_manager4 status --short tik_manager4/dcc/trigger` prints nothing.

```bash
git -C D:\dev\tik_manager4 add tik_manager4/dcc/__init__.py tik_manager4/dcc/trigger3 tests/test_trigger3.py
git -C D:\dev\tik_manager4 commit -m "Add the trigger3 DCC over tik.trigger's version control host"
```

---

### Task 13: The Tik Manager provider and its picker

**Files (in tik_manager4):**
- Create: `tik_manager4/dcc/trigger3/picker.py`
- Create: `tik_manager4/dcc/trigger3/plugins/tik_manager/tik_manager.py`, `tik_manager.png` (copy `setup/icons/trigger3.png`)
- Test: append to `tests/test_trigger3.py`

**Interfaces:**
- `picker.TikPickerDialog(tik, kind, extensions, parent=None)` with `pick() -> str` (exec, then the chosen path or `""`) and `chosen_path() -> str` (the path the current selection resolves to, no exec; what the tests drive). Assembled from `TikSubProjectWidget(tik.project)`, `TikTaskWidget()`, `TikCategoryWidget()`, `TikVersionWidget(tik.project)` wired as `MainUI.initialize_mcv` wires them (subproject → tasks, task → categories, work → versions). A work version resolves to `work.get_abs_project_path(version.scene_path)`; a publish version resolves to `version.get_element_path(element, relative=False)` for the selected element (`get_selected_element_type()`), and when that is a folder, to the first file inside it matching `extensions`. The Use button is enabled only when the resolved path exists and its suffix is in `extensions` (or `extensions` is empty).
- `TikManagerProvider` registered as `"tik_manager"`, label "Tik Manager", icon `tik_manager`; verbs per spec section 9.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_trigger3.py`:

```python
def test_provider_registers_and_reads_context(tik3, tmp_path):
    import tik.trigger as trigger

    trigger.add_plugin_path(Path(__file__).resolve().parents[1] / "tik_manager4" / "dcc" / "trigger3" / "plugins")
    trigger.load_plugins()
    provider = vcs.get_provider("tik_manager")()
    assert provider.available() is True
    assert provider.display_label() == "Tik Manager"
    assert provider.icon_path() is not None
    assert provider.context(str(tmp_path / "loose.tr")) is None
    _task, work, session = _rig_work(tik3, tmp_path)
    context = provider.context(str(session.file_path))
    assert context.label.endswith("hero") and context.version == 1 and context.is_latest


def test_provider_new_version_iterates_the_work(tik3, tmp_path):
    # never import the plugin by its dotted tik_manager4 path: the plugin
    # loader imports it as ``tik_manager.tik_manager`` and a second module
    # object would register the provider twice
    import tik.trigger as trigger

    trigger.add_plugin_path(Path(__file__).resolve().parents[1] / "tik_manager4" / "dcc" / "trigger3" / "plugins")
    trigger.load_plugins()
    provider = vcs.get_provider("tik_manager")()
    _task, work, session = _rig_work(tik3, tmp_path)
    path = provider.new_version(vcs.host)
    assert path.endswith("_v002.tr")
    work.reload()
    assert work.version_count == 2


def test_picker_resolves_a_work_version(tik3, tmp_path, qapp):
    from tik_manager4.dcc.trigger3.picker import TikPickerDialog

    _task, work, session = _rig_work(tik3, tmp_path)
    dialog = TikPickerDialog(tik3, "session", [".tr"])
    dialog.select_work(work)
    assert dialog.chosen_path().endswith("hero_v001.tr")
    assert dialog.use_button.isEnabled()
```

Add at the top of the test file, after the imports, a `qapp` fixture:

```python
@pytest.fixture(scope="session")
def qapp():
    from tik_manager4.ui.Qt import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
```

`dialog.select_work(work)` is a test seam on the picker: it selects the work's subproject, task and category in the widgets and sets the version widget's base to the work (`self.versions.set_base(work)`), so the resolution path is exercised without mouse events. Read `TikVersionWidget.set_base` and `populate_versions` (`ui/mcv/version_mcv.py:678-716`) for the exact call.

- [ ] **Step 2: Run to verify failure**

Run: `mayapy -m pytest tests/test_trigger3.py -q`
Expected: the three new tests FAIL (`NotFoundError: tik_manager`, module missing).

- [ ] **Step 3: Write the picker**

```python
# tik_manager4/dcc/trigger3/picker.py
"""A version picker for Trigger: the main window's four trees, one Use button."""

from pathlib import Path

from tik_manager4.ui.Qt import QtWidgets
from tik_manager4.ui.mcv.category_mcv import TikCategoryWidget
from tik_manager4.ui.mcv.subproject_mcv import TikSubProjectWidget
from tik_manager4.ui.mcv.task_mcv import TikTaskWidget
from tik_manager4.ui.mcv.version_mcv import TikVersionWidget


class TikPickerDialog(QtWidgets.QDialog):
    """Pick a work or publish version; ``pick()`` returns its file path."""

    def __init__(self, tik, kind, extensions, parent=None):
        super().__init__(parent)
        self.tik = tik
        self.kind = kind
        self.extensions = [ext if ext.startswith(".") else f".{ext}" for ext in extensions]
        self.setWindowTitle(f"Tik Manager - pick {kind}")
        self.resize(1100, 600)
        self._chosen = ""
        layout = QtWidgets.QVBoxLayout(self)
        trees = QtWidgets.QHBoxLayout()
        layout.addLayout(trees, 1)
        self.subprojects = TikSubProjectWidget(tik.project, parent=self)
        self.tasks = TikTaskWidget()
        self.tasks.task_view.hide_columns(["id", "path"])
        self.categories = TikCategoryWidget()
        self.categories.work_tree_view.hide_columns(["id", "path"])
        self.versions = TikVersionWidget(tik.project, parent=self)
        for widget in (self.subprojects, self.tasks, self.categories, self.versions):
            trees.addWidget(widget)
        self.subprojects.sub_view.item_selected.connect(self.tasks.task_view.set_tasks)
        self.subprojects.sub_view.add_item.connect(self.tasks.task_view.add_tasks)
        self.tasks.task_view.item_selected.connect(self.categories.set_task)
        self.categories.work_tree_view.item_selected.connect(self.versions.set_base)
        self.categories.work_tree_view.item_selected.connect(lambda _b: self._refresh())
        self.versions.version.combo.currentIndexChanged.connect(lambda _i: self._refresh())
        buttons = QtWidgets.QHBoxLayout()
        layout.addLayout(buttons)
        self.path_label = QtWidgets.QLabel("")
        buttons.addWidget(self.path_label, 1)
        self.use_button = QtWidgets.QPushButton("Use")
        self.use_button.setEnabled(False)
        self.use_button.clicked.connect(self._accept)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(self.use_button)
        buttons.addWidget(cancel)
        self.tasks.task_view.refresh()

    # ------------------------------------------------------------ seams
    def select_work(self, base):
        """Point the version widget at ``base`` (a Work or Publish) directly."""
        self.versions.set_base(base)
        self._refresh()

    # ------------------------------------------------------- resolution
    def _base(self):
        item = self.categories.work_tree_view.get_selected_item()
        if item is not None:
            return item.tik_obj
        return getattr(self.versions, "base", None)

    def chosen_path(self) -> str:
        base = self._base()
        version = self.versions.get_selected_version()
        if base is None or version is None:
            return ""
        if hasattr(version, "scene_path"):  # a work version
            path = Path(base.get_abs_project_path(version.scene_path))
        else:  # a publish version
            element = self.versions.get_selected_element_type() or "source"
            relative = version.get_element_path(element)
            if not relative:
                return ""
            path = Path(version.get_resolved_path(relative))
            if path.is_dir():
                inside = sorted(
                    child for child in path.iterdir()
                    if not self.extensions or child.suffix in self.extensions
                )
                if not inside:
                    return ""
                path = inside[0]
        return path.as_posix()

    def _acceptable(self, path: str) -> bool:
        if not path or not Path(path).exists():
            return False
        return not self.extensions or Path(path).suffix in self.extensions

    def _refresh(self):
        path = self.chosen_path()
        self.path_label.setText(path)
        self.use_button.setEnabled(self._acceptable(path))

    def _accept(self):
        self._chosen = self.chosen_path()
        self.accept()

    def pick(self) -> str:
        """Show the dialog; the chosen path or ``""``."""
        self._chosen = ""
        self.exec_()
        return self._chosen
```

Verify against the real widgets: `TikVersionWidget.set_base` stores the base under some attribute name (read `version_mcv.py:678`); adjust `_base()` to that name. `TikVersionWidget.version.combo` is the version combo (`VersionWidgets`), read `build_ui` to confirm the attribute path.

- [ ] **Step 4: Write the provider**

```python
# tik_manager4/dcc/trigger3/plugins/tik_manager/tik_manager.py
"""Tik Manager as a Trigger version control provider."""

from pathlib import Path

from tik.trigger.vcs import kinds, register_provider
from tik.trigger.vcs.provider import Context, VersionControl

DCC_NAME = "trigger3"


def _tik():
    """A tik_manager4 main object bound to the trigger3 DCC.

    ``initialize`` sets the global DCC and reloads ``objects.main``, so inside a
    Maya that also runs tik_manager's Maya integration this is re-done before
    every operation, as the old integration did.
    """
    import tik_manager4

    return tik_manager4.initialize(DCC_NAME)


@register_provider("tik_manager")
class TikManagerProvider(VersionControl):
    """Works, versions and publishes of a Tik Manager project."""

    label = "Tik Manager"
    icon = "tik_manager"

    def available(self) -> bool:
        try:
            import tik_manager4  # noqa: F401
        except ImportError:
            return False
        return True

    def context(self, session_path: str):
        if not session_path:
            return None
        tik = _tik()
        work, version = tik.project.find_work_by_absolute_path(session_path)
        if not work:
            return None
        latest = work.versions[-1].version if work.versions else version
        return Context(
            label=f"{work.task_name} / {work.name}",
            version=version,
            is_latest=version == latest,
            detail=work.path,
        )

    def browse(self, kind: str, extensions: list, mode: str) -> str:
        from tik_manager4.dcc.trigger3.picker import TikPickerDialog

        tik = _tik()
        dialog = TikPickerDialog(tik, kind, extensions, parent=tik.dcc.get_main_window())
        return dialog.pick()

    def new_version(self, host) -> str:
        tik = _tik()
        work, _version = tik.project.find_work_by_absolute_path(host.session_path)
        if not work:
            host.feedback.pop_error(
                "Tik Manager",
                "The session is not a Tik Manager work.",
                "Save it as a new work from the Tik Manager window first.",
            )
            return ""
        made = work.new_version(file_format=".tr", notes="Saved from Trigger")
        if made == -1:
            return ""
        return host.session_path

    def open(self, host) -> str:
        picked = self.browse(kinds.SESSION, [".tr"], "open")
        if picked:
            host.open(picked)
        return picked

    def publish_file(self, kind: str, path, host) -> None:
        from tik_manager4.ui import main

        tik = _tik()
        window = main.MainUI(tik, parent=tik.dcc.get_main_window(), window_name="Tik Manager - trigger3")
        window.show()
        window.on_save_any_file(file_path=str(Path(path)))

    def launch(self, host) -> None:
        from tik_manager4.ui import main

        tik = _tik()
        window = main.MainUI(tik, parent=tik.dcc.get_main_window(), window_name="Tik Manager - trigger3")
        window.show()
```

`work.new_version` calls `dcc_handler.save_as(output_path)`, which is `Dcc.save_as` from Task 12, which saves the host's session at the versioned path; so after it returns `host.session_path` is the new file. Check `WorkVersion.version` is the attribute name for the number (`objects/version.py:660+`).

- [ ] **Step 5: Run tests, commit (in tik_manager4)**

Run: `mayapy -m pytest tests/test_trigger3.py -q`

```bash
git -C D:\dev\tik_manager4 add tik_manager4/dcc/trigger3 tests/test_trigger3.py
git -C D:\dev\tik_manager4 commit -m "Add the Tik Manager provider for Trigger and its version picker"
```

---

### Task 14: The `tik_publish` action

**Files (in tik_manager4):**
- Create: `tik_manager4/dcc/trigger3/plugins/tik_publish/tik_publish.py`, `tik_publish.svg`
- Test: append to `tests/test_trigger3.py`

**Interfaces:**
- `@register_action("tik_publish", category="finish", icon="tik_publish", scope="publish")`, `class TikPublish(PublishAction)`, label "Tik Publish". `validate` adds `"tik_publish: Tik Manager is not installed"` or `"tik_publish: the session is not saved in a Tik Manager work"`. `deliver` per spec section 9.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_trigger3.py`:

```python
def test_tik_publish_registers_a_publish_version_with_three_elements(tik3, tmp_path):
    import tik.trigger as trigger
    from tik.trigger.core import ActionContext, registry

    trigger.add_plugin_path(Path(__file__).resolve().parents[1] / "tik_manager4" / "dcc" / "trigger3" / "plugins")
    trigger.load_plugins()
    cls = registry.get_action("tik_publish")
    assert cls.scope == "publish"

    loose = Session()
    loose.save(tmp_path / "loose.tr")
    ctx = ActionContext(session=loose, base_dir=str(tmp_path))
    assert cls().validate(ctx) == ["tik_publish: the session is not saved in a Tik Manager work"]

    _task, work, session = _rig_work(tik3, tmp_path)
    rig = tmp_path / "hero_rig.mb"
    rig.write_bytes(b"rig")
    trg = tmp_path / "hero.trg"
    trg.write_text("{}", encoding="utf-8")
    publish_set = PublishSet.collect(session.file_path, session.document, rig=rig, guides=trg)
    ctx = ActionContext(session=session, base_dir=str(session.directory))
    action = cls({"notes": "first"})
    assert action.validate(ctx) == []
    action.deliver(publish_set, ctx)

    work.publish.scan_publish_versions()
    published = work.publish.get_last_version()
    assert published == 1
    version = work.publish.get_version(1)
    assert sorted(version.element_types) == ["guides", "rig", "source"]
    assert version.notes == "first"
    bundle = Path(version.get_resolved_path(version.get_element_path("source")))
    assert (bundle / "hero_v001.tr").exists() or any(bundle.glob("*.tr"))
```

- [ ] **Step 2: Run to verify failure**

Run: `mayapy -m pytest tests/test_trigger3.py -q -k tik_publish`
Expected: FAIL with `NotFoundError: tik_publish`.

- [ ] **Step 3: Write the action**

```python
# tik_manager4/dcc/trigger3/plugins/tik_publish/tik_publish.py
"""Publish the built rig into the Tik Manager work the session lives in."""

from tik.trigger.actions.publish.publish import PublishAction
from tik.trigger.core import register_action
from tik.trigger.core.exceptions import ActionExecutionError

DCC_NAME = "trigger3"
ELEMENTS = ("source", "rig", "guides")


def _tik():
    import tik_manager4

    return tik_manager4.initialize(DCC_NAME)


def _installed() -> bool:
    try:
        import tik_manager4  # noqa: F401
    except ImportError:
        return False
    return True


@register_action("tik_publish", category="finish", icon="tik_publish", scope="publish")
class TikPublish(PublishAction):
    """Publish to Tik Manager: the session bundle, the rig scene and the guides.

    The session must be saved as a version of a Tik Manager work, and the
    work's category must list source, rig and guides among its extracts.
    """

    label = "Tik Publish"

    def _work(self, ctx):
        session = ctx.session
        if session is None or session.file_path is None:
            return None
        work, _version = _tik().project.find_work_by_absolute_path(str(session.file_path))
        return work or None

    def validate(self, ctx):
        problems = super().validate(ctx)
        if problems:
            return problems
        if not _installed():
            return ["tik_publish: Tik Manager is not installed"]
        if self._work(ctx) is None:
            return ["tik_publish: the session is not saved in a Tik Manager work"]
        return []

    def deliver(self, publish_set, ctx):
        from tik.trigger import vcs
        from tik_manager4.objects.publisher import Publisher

        if vcs.host.session is None:
            vcs.host.attach(session=ctx.session)
        tik = _tik()
        publisher = Publisher(tik.project)
        if not publisher.resolve():
            raise ActionExecutionError("the session is not saved in a Tik Manager work")
        missing = [name for name in ELEMENTS if name not in publisher._resolved_extractors]
        if missing:
            raise ActionExecutionError(
                "the work's category definition must list these extracts: "
                + ", ".join(missing)
            )
        publisher.reserve()
        for extractor in publisher._resolved_extractors.values():
            extractor.set_publish_set(publish_set)
        publisher.extract()
        failed = [
            name
            for name, extractor in publisher._resolved_extractors.items()
            if extractor.state == "failed"
        ]
        if failed:
            raise ActionExecutionError(
                "extract failed: " + "; ".join(
                    f"{name}: {publisher._resolved_extractors[name].message}" for name in failed
                )
            )
        published = publisher.publish(notes=self.notes or "Published by Trigger")
        ctx.log(f"Published to Tik Manager: {published.name} v{published.version:03d}")
```

`Publisher.extract()` calls `dcc.save_scene()` first, which saves the session at its current path through the host; `Publisher.publish()` writes elements, a thumbnail through `Dcc.generate_thumbnail`, and calls `post_publish`. If `Publisher.resolve` also needs a validator list, an empty one is fine.

- [ ] **Step 4: Draw `tik_publish.svg`**

The generic `publish.svg` from Task 7 with the arrow recoloured to Tik Manager's orange `#e8792b` and a small "T" in the box. Keep the 24x24 viewBox and the outer 2.3 stroke.

- [ ] **Step 5: Run tests, commit (in tik_manager4)**

Run: `mayapy -m pytest tests/test_trigger3.py -q`, then confirm `git -C D:\dev\tik_manager4 status --short tik_manager4/dcc/trigger` is empty.

```bash
git -C D:\dev\tik_manager4 add tik_manager4/dcc/trigger3
git -C D:\dev\tik_manager4 add tests/test_trigger3.py
git -C D:\dev\tik_manager4 commit -m "Add the tik_publish action for Trigger"
```

Then, back in tikworks, run the full suites once more: `make tests-unit`, `make tests-integration`, `$env:TIK_TESTS_NO_MAYA=1; $env:QT_QPA_PLATFORM="offscreen"; mayapy -m pytest tests/ui -q`, `make lint`.
