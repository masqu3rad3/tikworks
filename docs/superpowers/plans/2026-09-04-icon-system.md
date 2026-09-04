# Icon System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every tik.trigger action and guide module a real icon, loaded from a file beside its `.py`, falling back to today's generated glyph when there is none.

**Architecture:** Three modules with one job each. `tik/trigger/core/icons.py` is pure path resolution (no Qt — `trigger/core` may not import it). `tik/shared/ui/pick.py` turns paths into Qt objects and recolours them. `tik/trigger/ui/iconography.py` holds the family rules: actions are full-colour and never tinted, guide modules are monochrome and tinted by side or category. Six existing call sites swap `glyph_icon(initials(...))` for an `iconography` call.

**Tech Stack:** Python 3.10+, Qt through `tik.shared.ui.Qt` (the vendored shim), SVG assets, pytest under `mayapy`.

**Spec:** `docs/superpowers/specs/2026-09-04-icon-system-design.md`

## Global Constraints

- **No third-party dependencies.** Stdlib and Maya-bundled modules only.
- **`tik/trigger/core` must stay pure Python** — no `maya`, no `tik.maya`, no Qt, no `tik.shared`. Enforced by `tests/unit/test_import_boundaries.py`, which treats `tik.shared.ui` as Qt.
- **Never call `maya.cmds` / `OpenMaya` / `pymel` directly** outside `tik.maya`. No task here touches Maya at all.
- **Qt is imported only via `from tik.shared.ui.Qt import ...`** — never `PySide2`/`PySide6` directly.
- **Authored SVGs must stay inside Qt's SVG Tiny 1.2 subset**: no `<filter>`, `<mask>`, `<text>`, `<foreignObject>`, `<use>`, `currentColor`, `@import`. Self-contained files only.
- **Line length 88 columns.** Public functions and classes get docstrings.
- Run unit tests: `make tests-unit` · UI tests: `make tests-ui` · a single file: `set PYTHONPATH=%CD%/src/python && mayapy -m pytest tests/unit/test_icons_trigger.py -v`

## File Structure

| File | Responsibility |
|---|---|
| `src/python/tik/trigger/core/icons.py` | **Create.** Pure: class → icon file path + family. |
| `src/python/tik/shared/ui/pick.py` | **Create.** Path → `QIcon`/`QPixmap`; tinting; theme file; caches. |
| `src/python/tik/trigger/ui/iconography.py` | **Create.** Family rules + both fallbacks. |
| `src/python/tik/trigger/core/registry.py` | **Modify.** `register_module` gains `category` + `icon`. |
| `src/python/tik/trigger/core/module.py` | **Modify.** `category` / `icon` class attributes. |
| `src/python/tik/trigger/modules/*/*.py` | **Modify.** Declare a category. |
| `src/python/tik/trigger/actions/import_asset/import_asset.py` | **Modify.** Drop dangling `icon="import_model"`. |
| `src/python/tik/trigger/{actions,modules}/*/<name>.svg` | **Create.** Nine assets. |
| `src/python/tik/trigger/ui/designer/widgets.py` | **Modify.** Delete `MODULE_CATEGORY`. |
| 5 live UI call sites | **Modify.** Use `iconography`. (`ui/shelf.py` is dead code — leave it.) |
| `pyproject.toml` | **Modify.** `package-data` so assets ship. |
| `AI/icon_rules.md` | **Create.** The drawing rules. |

**Task order is dependency order.** 1 and 2 are independent; 3 is independent; 4 needs 3 (categories); 5 needs 1, 2, 3, 4; 6 needs 5; 7 is independent.

---

### Task 1: Pure icon-file resolution

**Files:**
- Create: `src/python/tik/trigger/core/icons.py`
- Test: `tests/unit/test_icons_trigger.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ACTION`, `MODULE`, `SUFFIXES`, `IconFile(path: Path, family: str)` with property `is_raster: bool`, and `find(cls: type) -> Optional[IconFile]`. Task 5 calls `find()` and reads `.path`, `.family`, `.is_raster`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_icons_trigger.py`:

```python
"""Icon file resolution: PNG beats SVG, declared name beats registered type."""

import sys
import types

import pytest

from tik.trigger.core import icons


@pytest.fixture
def plugin(tmp_path):
    """Build a throwaway plugin folder plus a class that claims to live in it."""
    created = []

    def make(name, *, family="action", icon="", files=()):
        folder = tmp_path / name
        folder.mkdir(exist_ok=True)
        for file_name in files:
            (folder / file_name).write_bytes(b"x")
        module_name = f"_tik_icon_probe_{name}"
        module = types.ModuleType(module_name)
        module.__file__ = str(folder / f"{name}.py")
        sys.modules[module_name] = module
        created.append(module_name)
        namespace = {"__module__": module_name, "icon": icon}
        namespace["action_type" if family == "action" else "module_type"] = name
        return folder, type(name.title(), (), namespace)

    yield make
    for module_name in created:
        sys.modules.pop(module_name, None)


def test_finds_svg_beside_the_module(plugin):
    folder, cls = plugin("kinematics", files=["kinematics.svg"])
    found = icons.find(cls)
    assert found is not None
    assert found.path == folder / "kinematics.svg"
    assert found.family == icons.ACTION
    assert found.is_raster is False


def test_png_wins_over_svg(plugin):
    folder, cls = plugin("kinematics", files=["kinematics.svg", "kinematics.png"])
    found = icons.find(cls)
    assert found.path == folder / "kinematics.png"
    assert found.is_raster is True


def test_declared_icon_name_beats_registered_type(plugin):
    folder, cls = plugin("script", icon="terminal", files=["script.svg", "terminal.svg"])
    assert icons.find(cls).path == folder / "terminal.svg"


def test_falls_back_to_registered_type_when_declared_name_has_no_file(plugin):
    folder, cls = plugin("script", icon="terminal", files=["script.svg"])
    assert icons.find(cls).path == folder / "script.svg"


def test_returns_none_when_nothing_on_disk(plugin):
    _folder, cls = plugin("ribbon", family="module")
    assert icons.find(cls) is None


def test_reports_the_module_family(plugin):
    _folder, cls = plugin("arm", family="module", files=["arm.svg"])
    assert icons.find(cls).family == icons.MODULE


def test_unregistered_class_has_no_icon():
    class Loose:
        pass

    assert icons.find(Loose) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `set PYTHONPATH=%CD%/src/python && mayapy -m pytest tests/unit/test_icons_trigger.py -v`
Expected: FAIL — `ImportError: cannot import name 'icons' from 'tik.trigger.core'`

- [ ] **Step 3: Write minimal implementation**

Create `src/python/tik/trigger/core/icons.py`:

```python
"""Locate the icon file belonging to a registered action or module.

Pure path work: no Qt and no Maya, because ``tik/trigger/core`` may import
neither. Resolution lives here rather than in the UI layer so the rule that a
plugin is ``<folder>/<folder>.py`` is stated once, beside the ``discovery``
module that established it.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ACTION = "action"
MODULE = "module"

#: Tried in order; first hit wins. A PNG is an artist's finished artwork and
#: deliberately supersedes the authored SVG placeholder beside it.
SUFFIXES = (".png", ".svg")


@dataclass(frozen=True)
class IconFile:
    """An icon on disk and the family of plugin it belongs to."""

    path: Path
    family: str

    @property
    def is_raster(self) -> bool:
        """True for a PNG: finished art that must never be recoloured."""
        return self.path.suffix.lower() == ".png"


def plugin_folder(cls: type) -> Optional[Path]:
    """The folder holding the module that defines ``cls``."""
    module = sys.modules.get(getattr(cls, "__module__", ""))
    file_name = getattr(module, "__file__", None)
    if not file_name:
        return None
    return Path(file_name).resolve().parent


def family_of(cls: type) -> Optional[str]:
    """``ACTION``, ``MODULE``, or None when ``cls`` is neither."""
    if getattr(cls, "action_type", ""):
        return ACTION
    if getattr(cls, "module_type", ""):
        return MODULE
    return None


def icon_names(cls: type) -> tuple[str, ...]:
    """Names to try, most specific first: declared ``icon``, then the type."""
    registered = getattr(cls, "action_type", "") or getattr(cls, "module_type", "")
    declared = getattr(cls, "icon", "") or ""
    return tuple(dict.fromkeys(name for name in (declared, registered) if name))


def find(cls: type) -> Optional[IconFile]:
    """Return ``cls``'s icon file, or None when it has no artwork."""
    family = family_of(cls)
    folder = plugin_folder(cls)
    if family is None or folder is None:
        return None
    for name in icon_names(cls):
        for suffix in SUFFIXES:
            candidate = folder / f"{name}{suffix}"
            if candidate.is_file():
                return IconFile(candidate, family)
    return None
```

Then export it from `src/python/tik/trigger/core/__init__.py`, following the
pattern already used there for sibling modules:

```python
from . import icons  # noqa: F401
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `set PYTHONPATH=%CD%/src/python && mayapy -m pytest tests/unit/test_icons_trigger.py tests/unit/test_import_boundaries.py -v`
Expected: PASS — all seven icon tests, and the boundary test still green (proving `icons.py` pulled in no Qt).

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/core/icons.py src/python/tik/trigger/core/__init__.py tests/unit/test_icons_trigger.py
git commit -m "feat: resolve a plugin's icon file, png over svg"
```

---

### Task 2: Shared resource picking

**Files:**
- Create: `src/python/tik/shared/ui/pick.py`
- Test: `tests/ui/test_pick.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `icon(path) -> QIcon`, `pixmap(path, size=None) -> QPixmap`, `tinted_icon(path, colour, size) -> QIcon`, `style_file(file_name="theme.qss") -> QFile`, `clear_cache() -> None`. Task 5 calls `icon` and `tinted_icon`.

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_pick.py`:

```python
"""pick: paths in, Qt objects out, with an exact-colour tint."""

import pytest

from tik.shared.ui import pick
from tik.shared.ui.Qt import QtGui

MONO = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">'
    '<circle cx="12" cy="12" r="9" fill="#93a8c4"/></svg>'
)


@pytest.fixture
def mono_svg(tmp_path):
    path = tmp_path / "dot.svg"
    path.write_text(MONO, encoding="utf-8")
    pick.clear_cache()
    return path


def _first_opaque(image):
    for y in range(image.height()):
        for x in range(image.width()):
            colour = QtGui.QColor(image.pixelColor(x, y))
            if colour.alpha() > 200:
                return colour.name()
    return None


def test_renders_an_icon_at_the_requested_size(qapp, mono_svg):
    result = pick.pixmap(mono_svg, 16)
    assert not result.isNull()
    assert (result.width(), result.height()) == (16, 16)


def test_tint_replaces_every_opaque_pixel_exactly(qapp, mono_svg):
    tinted = pick.tinted_icon(mono_svg, "#5b8fd0", 22)
    assert _first_opaque(tinted.pixmap(22, 22).toImage()) == "#5b8fd0"


def test_tint_keeps_the_silhouette(qapp, mono_svg):
    plain = pick.pixmap(mono_svg, 22).toImage()
    tinted = pick.tinted_icon(mono_svg, "#d06a66", 22).pixmap(22, 22).toImage()

    def drawn(image):
        return sum(
            1
            for y in range(image.height())
            for x in range(image.width())
            if QtGui.QColor(image.pixelColor(x, y)).alpha() > 200
        )

    assert drawn(tinted) == drawn(plain)


def test_icons_are_cached_by_path(qapp, mono_svg):
    assert pick.icon(mono_svg) is pick.icon(mono_svg)


def test_tints_are_cached_per_colour_and_size(qapp, mono_svg):
    assert pick.tinted_icon(mono_svg, "#5b8fd0", 16) is pick.tinted_icon(
        mono_svg, "#5b8fd0", 16
    )
    assert pick.tinted_icon(mono_svg, "#5b8fd0", 16) is not pick.tinted_icon(
        mono_svg, "#d06a66", 16
    )


def test_style_file_opens_the_theme(qapp):
    handle = pick.style_file()
    try:
        assert handle.isOpen()
        assert b"QWidget" in bytes(handle.readAll())
    finally:
        handle.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make tests-ui`
Expected: FAIL — `ImportError: cannot import name 'pick' from 'tik.shared.ui'`

- [ ] **Step 3: Write minimal implementation**

Create `src/python/tik/shared/ui/pick.py`:

```python
"""Pick shared UI resources: icons, pixmaps and the theme stylesheet.

Paths in, Qt objects out. This module knows nothing about actions or modules --
the tik.trigger side of that lives in ``tik/trigger/ui/iconography.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from tik.shared.ui.Qt import QtCore, QtGui

PathLike = Union[str, Path]

THEME_FOLDER = Path(__file__).parent / "theme"
RC_FOLDER = THEME_FOLDER / "rc"

_ICONS: dict[str, QtGui.QIcon] = {}
_TINTED: dict[tuple, QtGui.QIcon] = {}


def icon(path: PathLike) -> QtGui.QIcon:
    """A cached ``QIcon`` for ``path``."""
    key = str(path)
    if key not in _ICONS:
        _ICONS[key] = QtGui.QIcon(key)
    return _ICONS[key]


def pixmap(path: PathLike, size: Optional[int] = None) -> QtGui.QPixmap:
    """``path`` rendered at ``size`` square, or at its natural size."""
    if size is None:
        return QtGui.QPixmap(str(path))
    return icon(path).pixmap(QtCore.QSize(size, size))


def tinted_icon(path: PathLike, colour: str, size: int) -> QtGui.QIcon:
    """``path`` recoloured to ``colour``, keeping its alpha silhouette.

    Only ever call this on monochrome artwork: every opaque pixel becomes
    ``colour``. Tinting is done on the rendered pixmap rather than in the
    document because Qt's SVG renderer handles ``currentColor`` poorly.
    """
    key = (str(path), colour, size)
    if key in _TINTED:
        return _TINTED[key]
    base = pixmap(path, size)
    stamped = QtGui.QPixmap(base.size())
    stamped.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(stamped)
    painter.drawPixmap(0, 0, base)
    painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceIn)
    painter.fillRect(stamped.rect(), QtGui.QColor(colour))
    painter.end()
    _TINTED[key] = QtGui.QIcon(stamped)
    return _TINTED[key]


def style_file(file_name: str = "theme.qss") -> QtCore.QFile:
    """The theme stylesheet, open for reading, with ``css:``/``rc:`` paths set."""
    QtCore.QDir.addSearchPath("css", str(THEME_FOLDER))
    QtCore.QDir.addSearchPath("rc", str(RC_FOLDER))
    handle = QtCore.QFile(f"css:{file_name}")
    handle.open(QtCore.QFile.ReadOnly | QtCore.QFile.Text)
    return handle


def clear_cache() -> None:
    """Drop both caches. Primarily for tests."""
    _ICONS.clear()
    _TINTED.clear()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `make tests-ui`
Expected: PASS — six new `test_pick.py` tests, no existing UI test broken.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/shared/ui/pick.py tests/ui/test_pick.py
git commit -m "feat: shared pick helper for icons, tinting and the theme file"
```

---

### Task 3: Modules declare category and icon

**Files:**
- Modify: `src/python/tik/trigger/core/registry.py:30-45` (`register_module`)
- Modify: `src/python/tik/trigger/core/module.py:51` (class attributes)
- Modify: `src/python/tik/trigger/modules/{base,fkchain,arm,twist,ribbon}/*.py` (decorator lines)
- Modify: `src/python/tik/trigger/actions/import_asset/import_asset.py:11`
- Modify: `src/python/tik/trigger/ui/designer/widgets.py:18-30`
- Test: `tests/unit/test_core_trigger.py` (append)

**Interfaces:**
- Consumes: nothing.
- Produces: `register_module(name, category="generic", icon="")` stamping `cls.module_type`, `cls.category`, `cls.icon`. Tasks 4 and 5 rely on `cls.category` being present on every module class.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_core_trigger.py`:

```python
def test_register_module_stamps_category_and_icon():
    from tik.trigger.core import Module, register_module, registry

    @register_module("probe_limb", category="limbs")
    class ProbeLimb(Module):
        pass

    try:
        assert ProbeLimb.module_type == "probe_limb"
        assert ProbeLimb.category == "limbs"
        assert ProbeLimb.icon == "probe_limb"  # defaults to the registered name
    finally:
        registry.unregister_module("probe_limb")


def test_register_module_category_defaults_to_generic():
    from tik.trigger.core import Module, register_module, registry

    @register_module("probe_plain")
    class ProbePlain(Module):
        pass

    try:
        assert ProbePlain.category == "generic"
    finally:
        registry.unregister_module("probe_plain")


def test_shipped_modules_declare_a_category():
    from tik.trigger.core import registry

    expected = {
        "base": "body",
        "fkchain": "generic",
        "arm": "limbs",
        "twist": "generic",
        "ribbon": "generic",
    }
    for name, category in expected.items():
        assert registry.get_module(name).category == category


def test_import_asset_icon_defaults_to_its_own_name():
    from tik.trigger.core import registry

    assert registry.get_action("import_asset").icon == "import_asset"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `set PYTHONPATH=%CD%/src/python && mayapy -m pytest tests/unit/test_core_trigger.py -v -k "category or icon"`
Expected: FAIL — `TypeError: register_module() got an unexpected keyword argument 'category'`

- [ ] **Step 3: Write minimal implementation**

In `src/python/tik/trigger/core/registry.py`, replace `register_module` with:

```python
def register_module(
    name: str, category: str = "generic", icon: str = ""
) -> Callable[[Type[T]], Type[T]]:
    """Register a ``Module`` subclass under ``name``.

    Args:
        name: Unique module type name.
        category: Shelf/palette group (``body``, ``limbs``, ``generic``,
            ``face``). Drives the tile colour and the icon tint.
        icon: Icon file name beside the module's ``.py`` (defaults to ``name``).
    """

    def inner(cls: Type[T]) -> Type[T]:
        existing = _MODULES.get(name)
        if existing is not None and existing is not cls:
            raise DuplicateRegistrationError(name, kind="module")
        cls.module_type = name  # type: ignore[attr-defined]
        cls.category = category  # type: ignore[attr-defined]
        cls.icon = icon or name  # type: ignore[attr-defined]
        _MODULES[name] = cls
        logger.debug("Registered module: %s", name)
        return cls

    return inner
```

In `src/python/tik/trigger/core/module.py`, beside the existing
`module_type` attribute, add:

```python
    module_type: str = ""  # stamped by @register_module
    category: str = "generic"  # stamped by @register_module
    icon: str = ""  # stamped by @register_module
```

Update the five module decorators:

```python
@register_module("base", category="body")        # modules/base/base.py:9
@register_module("fkchain", category="generic")  # modules/fkchain/fkchain.py:9
@register_module("arm", category="limbs")        # modules/arm/arm.py:35
@register_module("twist", category="generic")    # modules/twist/twist.py:55
@register_module("ribbon", category="generic")   # modules/ribbon/ribbon.py:31
```

In `src/python/tik/trigger/actions/import_asset/import_asset.py:11`, drop the
dangling icon name — no `import_model` asset has ever existed:

```python
@register_action("import_asset", category="build")
```

In `src/python/tik/trigger/ui/designer/widgets.py`, delete the `MODULE_CATEGORY`
dict entirely and read the class attribute instead:

```python
MODULE_COLORS = {"body": "#c9a24a", "limbs": "#5b8fd0", "generic": "#7fa86a",
                 "face": "#b86b9a", "scene": "#8a93a0"}


def module_entries():
    tiles, palette = [], []
    for module_cls in registry.iter_modules():
        category = getattr(module_cls, "category", "generic")
        tiles.append(TileEntry(module_cls.module_type, module_cls.display_label(), category))
        palette.append(PaletteEntry(module_cls.module_type, module_cls.display_label(), category))
    tiles.append(TileEntry(SCENE_NODE, "Scene", "scene"))
    palette.append(PaletteEntry(SCENE_NODE, "Scene Nodes", "scene"))
    return tiles, palette
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `make tests-unit && make tests-ui`
Expected: PASS. The Guide Designer UI tests exercise `module_entries()`, so a
wrong category surfaces there.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/core/registry.py src/python/tik/trigger/core/module.py src/python/tik/trigger/modules src/python/tik/trigger/actions/import_asset/import_asset.py src/python/tik/trigger/ui/designer/widgets.py tests/unit/test_core_trigger.py
git commit -m "feat: modules declare category and icon on the decorator"
```

---

### Task 4: The nine icon assets, their lint, and packaging

**Files:**
- Create: `src/python/tik/trigger/actions/{kinematics,import_asset,script,reference}/<name>.svg`
- Create: `src/python/tik/trigger/modules/{base,fkchain,arm,twist,ribbon}/<name>.svg`
- Modify: `pyproject.toml`
- Test: `tests/unit/test_icon_assets.py`

**Interfaces:**
- Consumes: `tik.trigger.core.icons` from Task 1; module categories from Task 3.
- Produces: an SVG beside every registered plugin's `.py`. Task 5's tests assert each one resolves and renders.

Every file below was rendered in Maya 2027/PySide6 and verified: correct at
16/22/26px, action colour preserved (62–227 distinct colours at 64px), modules
monochrome and tinting to an exact colour. **Write them verbatim.**

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_icon_assets.py`:

```python
"""Every shipped plugin has artwork, and that artwork is Qt-safe.

Pure text checks -- no Qt here, so this runs in the plain unit suite.
"""

import pytest

from tik.trigger.core import icons, registry

# Qt renders SVG Tiny 1.2. These elements and attributes are silently ignored,
# so a file using them looks right in a browser and wrong (or blank) in Maya.
FORBIDDEN = ("<filter", "<mask", "<text", "<foreignObject", "<use", "currentColor", "@import")


def _plugins():
    return [(cls, "action") for cls in registry.iter_actions()] + [
        (cls, "module") for cls in registry.iter_modules()
    ]


@pytest.mark.parametrize("cls,family", _plugins(), ids=lambda item: getattr(item, "__name__", item))
def test_every_plugin_ships_an_icon(cls, family):
    found = icons.find(cls)
    assert found is not None, f"{cls.__name__} has no icon file beside its .py"
    assert found.family == family


@pytest.mark.parametrize("cls,_family", _plugins(), ids=lambda item: getattr(item, "__name__", item))
def test_icons_stay_inside_the_qt_svg_subset(cls, _family):
    found = icons.find(cls)
    if found is None or found.is_raster:
        pytest.skip("no icon, or a raster one the subset rules do not govern")
    text = found.path.read_text(encoding="utf-8")
    used = [token for token in FORBIDDEN if token in text]
    assert used == [], f"{found.path.name} uses {used}, which Qt will ignore"


@pytest.mark.parametrize("cls,_family", _plugins(), ids=lambda item: getattr(item, "__name__", item))
def test_icons_share_the_24_unit_grid(cls, _family):
    found = icons.find(cls)
    if found is None or found.is_raster:
        pytest.skip("no icon, or a raster one drawn on no grid")
    assert 'viewBox="0 0 24 24"' in found.path.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `set PYTHONPATH=%CD%/src/python && mayapy -m pytest tests/unit/test_icon_assets.py -v`
Expected: FAIL — every `test_every_plugin_ships_an_icon` case fails with "has no icon file beside its .py".

- [ ] **Step 3: Write the nine assets**

`src/python/tik/trigger/actions/kinematics/kinematics.svg` — the bone, from
`trigger/ui/icons/kinematics.png`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24"><g fill="#f2ead6" stroke="#f2ead6" stroke-width="2.3" stroke-linejoin="round" stroke-linecap="round"><path d="M8.5 13.2 L10.8 15.5 L15.5 10.8 L13.2 8.5 Z"/><circle cx="7.3" cy="14.4" r="2.7"/><circle cx="9.9" cy="17" r="2.7"/><circle cx="14.1" cy="7" r="2.7"/><circle cx="16.7" cy="9.6" r="2.7"/></g><g stroke="none"><path d="M8.5 13.2 L10.8 15.5 L15.5 10.8 L13.2 8.5 Z" fill="#e3cf9f"/><circle cx="7.3" cy="14.4" r="2.7" fill="#e3cf9f"/><circle cx="9.9" cy="17" r="2.7" fill="#e3cf9f"/><circle cx="14.1" cy="7" r="2.7" fill="#e3cf9f"/><circle cx="16.7" cy="9.6" r="2.7" fill="#e3cf9f"/></g></svg>
```

`src/python/tik/trigger/actions/import_asset/import_asset.svg` — arrow into crate:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24"><g fill="#e8f0dc" stroke="#e8f0dc" stroke-width="2.3" stroke-linejoin="round" stroke-linecap="round"><path d="M10.8 2.6 H13.2 V7.2 H16.1 L12 12.2 L7.9 7.2 H10.8 Z"/><path d="M3.4 13.2 L12 17.4 L20.6 13.2 L12 9 Z"/><path d="M3.4 13.2 V18.5 L12 22.7 V17.4 Z"/><path d="M20.6 13.2 V18.5 L12 22.7 V17.4 Z"/></g><g stroke="none"><path d="M10.8 2.6 H13.2 V7.2 H16.1 L12 12.2 L7.9 7.2 H10.8 Z" fill="#4d9fd6"/><path d="M3.4 13.2 L12 17.4 L20.6 13.2 L12 9 Z" fill="#a3c169"/><path d="M3.4 13.2 V18.5 L12 22.7 V17.4 Z" fill="#82a04c"/><path d="M20.6 13.2 V18.5 L12 22.7 V17.4 Z" fill="#6d8940"/></g></svg>
```

`src/python/tik/trigger/actions/script/script.svg` — paper, rule lines, pen:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24"><g fill="#f7efd8" stroke="#f7efd8" stroke-width="2.3" stroke-linejoin="round" stroke-linecap="round"><path d="M5.3 3.3 H11.8 L16 7.5 V19 A1.7 1.7 0 0 1 14.3 20.7 H5.3 A1.7 1.7 0 0 1 3.6 19 V5 A1.7 1.7 0 0 1 5.3 3.3 Z"/><path d="M11.8 3.3 V7.5 H16 Z"/><path d="M20.6 11.9 L14.2 18.3 L11.4 19.1 L12.2 16.3 L18.6 9.9 Z"/></g><g stroke="none"><path d="M5.3 3.3 H11.8 L16 7.5 V19 A1.7 1.7 0 0 1 14.3 20.7 H5.3 A1.7 1.7 0 0 1 3.6 19 V5 A1.7 1.7 0 0 1 5.3 3.3 Z" fill="#f0e1b4"/><path d="M11.8 3.3 V7.5 H16 Z" fill="#d3c08a"/><path d="M20.6 11.9 L14.2 18.3 L11.4 19.1 L12.2 16.3 L18.6 9.9 Z" fill="#4d9fd6"/></g><g stroke="#a3925e" stroke-width="1.25" stroke-linecap="round" fill="none"><path d="M6.5 11.4 H12"/><path d="M6.5 14.4 H10.2"/></g></svg>
```

`src/python/tik/trigger/actions/reference/reference.svg` — cube, inner edges
dashed to echo the dashed linked-row stripe in `delegates.py:72`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24"><g fill="#dff4fa" stroke="#dff4fa" stroke-width="2.3" stroke-linejoin="round" stroke-linecap="round"><path d="M12 2.7 L20.5 7.3 L12 11.9 L3.5 7.3 Z"/><path d="M3.5 7.3 L12 11.9 V21.2 L3.5 16.6 Z"/><path d="M20.5 7.3 V16.6 L12 21.2 V11.9 Z"/></g><g stroke="none"><path d="M12 2.7 L20.5 7.3 L12 11.9 L3.5 7.3 Z" fill="#a6e2ef"/><path d="M3.5 7.3 L12 11.9 V21.2 L3.5 16.6 Z" fill="#7cc9dd"/><path d="M20.5 7.3 V16.6 L12 21.2 V11.9 Z" fill="#5cadc6"/></g><g stroke="#2f7f96" stroke-width="1.1" fill="none" stroke-dasharray="2.4 2.1" stroke-linecap="round"><path d="M3.5 7.3 L12 11.9 L20.5 7.3"/><path d="M12 11.9 V21.2"/></g></svg>
```

`src/python/tik/trigger/modules/base/base.svg` — root: ring, axis ticks, hub:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24"><g fill="none" stroke="#93a8c4" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="7.4"/><path d="M12 2.4 V5"/><path d="M12 19 V21.6"/><path d="M2.4 12 H5"/><path d="M19 12 H21.6"/><circle cx="12" cy="12" r="2.6" fill="#93a8c4" stroke="none"/></g></svg>
```

`src/python/tik/trigger/modules/fkchain/fkchain.svg` — four joints in an arc:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24"><g fill="none" stroke="#93a8c4" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round"><path d="M5 18.6 L9.9 14.3 L14.8 10.7 L19.4 7.3"/><g fill="#93a8c4" stroke="none"><circle cx="5" cy="18.6" r="1.75"/><circle cx="9.9" cy="14.3" r="1.75"/><circle cx="14.8" cy="10.7" r="1.75"/><circle cx="19.4" cy="7.3" r="1.75"/></g></g></svg>
```

`src/python/tik/trigger/modules/arm/arm.svg` — three-joint bend:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24"><g fill="none" stroke="#93a8c4" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round"><path d="M5.6 5.4 L15.6 11.6 L7.6 19"/><g fill="#93a8c4" stroke="none"><circle cx="5.6" cy="5.4" r="1.9"/><circle cx="15.6" cy="11.6" r="1.9"/><circle cx="7.6" cy="19" r="1.9"/></g></g></svg>
```

`src/python/tik/trigger/modules/twist/twist.svg` — counter-rotating arrows:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24"><g fill="none" stroke="#93a8c4" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3.4 V20.6" opacity="0.45"/><path d="M6.9 8.7 C9 6.9 15 6.9 17.1 8.7"/><path d="M17.1 8.7 L14.6 8.25"/><path d="M17.1 8.7 L16.45 11.1"/><path d="M17.1 15.3 C15 17.1 9 17.1 6.9 15.3"/><path d="M6.9 15.3 L9.4 15.75"/><path d="M6.9 15.3 L7.55 12.9"/></g></svg>
```

`src/python/tik/trigger/modules/ribbon/ribbon.svg` — wavy band with a centre point:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24"><g fill="none" stroke="#93a8c4" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round"><path d="M3.3 9.2 C7.6 4.6 16.4 13.8 20.7 9.2"/><path d="M3.3 14.8 C7.6 10.2 16.4 19.4 20.7 14.8"/><path d="M3.3 9.2 V14.8"/><path d="M20.7 9.2 V14.8"/><circle cx="12" cy="12" r="1.4" fill="#93a8c4" stroke="none"/></g></svg>
```

Then make them ship. Append to `pyproject.toml`:

```toml
[tool.setuptools.package-data]
"*" = ["*.svg", "*.png", "*.qss", "*.json"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `set PYTHONPATH=%CD%/src/python && mayapy -m pytest tests/unit/test_icon_assets.py -v`
Expected: PASS — 27 cases (9 plugins × 3 checks).

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/actions src/python/tik/trigger/modules pyproject.toml tests/unit/test_icon_assets.py
git commit -m "feat: nine authored icons, their Qt-subset lint, and packaging"
```

---

### Task 5: Family rules and fallbacks

**Files:**
- Create: `src/python/tik/trigger/ui/iconography.py`
- Test: `tests/ui/test_iconography.py`

**Interfaces:**
- Consumes: `icons.find`, `icons.ACTION`, `icons.MODULE`, `IconFile.is_raster` (Task 1); `pick.icon`, `pick.tinted_icon` (Task 2); `cls.category` (Task 3); the nine assets (Task 4).
- Produces: `action_icon(cls, size=22) -> QIcon`, `module_icon(cls, side=None, size=22) -> QIcon`, `module_colour(cls, side=None) -> str`, `guide_count(cls) -> int`, `topology_icon(cls, colour, size) -> QIcon`, and `DEFAULT_SIZE = 22`. Task 6 calls `action_icon` and `module_icon`, and adds `icon_for_tile(entry, size)` to this same module.

- [ ] **Step 1: Write the failing test**

Create `tests/ui/test_iconography.py`:

```python
"""Family rules: actions keep their colour, modules take a tint."""

import pytest

from tik.shared.ui import theme
from tik.shared.ui.Qt import QtGui
from tik.trigger.core import registry
from tik.trigger.ui import iconography


def _drawn(icon, size):
    image = icon.pixmap(size, size).toImage()
    return sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if QtGui.QColor(image.pixelColor(x, y)).alpha() > 40
    )


def _colours(icon, size):
    image = icon.pixmap(size, size).toImage()
    return {
        QtGui.QColor(image.pixelColor(x, y)).name()
        for y in range(image.height())
        for x in range(image.width())
        if QtGui.QColor(image.pixelColor(x, y)).alpha() > 200
    }


@pytest.mark.parametrize("action_cls", registry.iter_actions(), ids=lambda c: c.action_type)
def test_every_action_renders_at_tree_size(qapp, action_cls):
    assert _drawn(iconography.action_icon(action_cls, size=16), 16) > 20


@pytest.mark.parametrize("module_cls", registry.iter_modules(), ids=lambda c: c.module_type)
def test_every_module_renders_at_tree_size(qapp, module_cls):
    assert _drawn(iconography.module_icon(module_cls, size=16), 16) > 20


def test_actions_keep_their_own_colour(qapp):
    icon = iconography.action_icon(registry.get_action("import_asset"), size=64)
    assert len(_colours(icon, 64)) > 8, "an action must not be flattened to one tint"


def test_modules_take_the_side_tint(qapp):
    arm = registry.get_module("arm")
    assert _colours(iconography.module_icon(arm, side="L", size=22)) == {theme.SIDE["L"]}
    assert _colours(iconography.module_icon(arm, side="R", size=22)) == {theme.SIDE["R"]}


def test_module_without_a_side_takes_its_category_colour(qapp):
    from tik.trigger.ui.designer.widgets import MODULE_COLORS

    arm = registry.get_module("arm")
    expected = MODULE_COLORS[arm.category]
    assert _colours(iconography.module_icon(arm, size=22)) == {expected}


def test_a_raster_module_icon_is_never_tinted(qapp, tmp_path, monkeypatch):
    from tik.trigger.core import icons

    png = tmp_path / "fake.png"
    pixmap = QtGui.QPixmap(22, 22)
    pixmap.fill(QtGui.QColor("#ff00ff"))
    pixmap.save(str(png), "PNG")
    monkeypatch.setattr(
        icons, "find", lambda cls: icons.IconFile(png, icons.MODULE)
    )
    icon = iconography.module_icon(registry.get_module("arm"), side="L", size=22)
    assert _colours(icon, 22) == {"#ff00ff"}


def test_module_with_no_artwork_falls_back_to_its_topology(qapp, monkeypatch):
    from tik.trigger.core import icons

    monkeypatch.setattr(icons, "find", lambda cls: None)
    icon = iconography.module_icon(registry.get_module("fkchain"), side="L", size=22)
    assert _drawn(icon, 22) > 10
    assert _colours(icon, 22) == {theme.SIDE["L"]}


def test_action_with_no_artwork_falls_back_to_initials(qapp, monkeypatch):
    from tik.trigger.core import icons

    monkeypatch.setattr(icons, "find", lambda cls: None)
    icon = iconography.action_icon(registry.get_action("script"), size=22)
    assert _drawn(icon, 22) > 100, "the initials chip is a filled square"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make tests-ui`
Expected: FAIL — `ImportError: cannot import name 'iconography' from 'tik.trigger.ui'`

- [ ] **Step 3: Write minimal implementation**

Create `src/python/tik/trigger/ui/iconography.py`:

```python
"""Icons for actions and guide modules, and what to draw when there are none.

Two families, deliberately different. An action is a verb: it carries its own
colour and is never tinted, which is safe because ``delegates.py`` paints run
state as a separate status dot. A guide module is a noun: monochrome artwork
recoloured per side, so one ``arm.svg`` serves ``L_arm`` and ``R_arm``.
"""

from __future__ import annotations

from typing import Optional

from tik.shared.ui import pick, theme
from tik.shared.ui.icons import glyph_icon, initials
from tik.shared.ui.Qt import QtCore, QtGui
from tik.trigger.core import icons

from .designer.widgets import MODULE_COLORS

DEFAULT_SIZE = 22


def action_icon(action_cls: type, size: int = DEFAULT_SIZE) -> QtGui.QIcon:
    """An action's artwork, or the generated initials chip when it has none."""
    found = icons.find(action_cls)
    if found is not None:
        return pick.icon(found.path)
    category = getattr(action_cls, "category", "utility")
    colour = theme.CATEGORY.get(category, theme.CATEGORY["utility"])
    return glyph_icon(initials(action_cls.display_label()), colour, size=size)


def module_colour(module_cls: type, side: Optional[str] = None) -> str:
    """The tint for a module: its side if it has one, else its category."""
    if side:
        # ``Side`` is a str-mixin enum, so a plain dict lookup accepts both
        # ``Side.LEFT`` and ``"L"``. Do not wrap this in ``str()``: what that
        # returns for a mixin enum varies by Python version.
        return theme.SIDE.get(side, theme.SIDE["C"])
    category = getattr(module_cls, "category", "generic")
    return MODULE_COLORS.get(category, MODULE_COLORS["generic"])


def module_icon(
    module_cls: type, side: Optional[str] = None, size: int = DEFAULT_SIZE
) -> QtGui.QIcon:
    """A module's artwork, tinted, or a sketch of its guide topology."""
    colour = module_colour(module_cls, side)
    found = icons.find(module_cls)
    if found is None:
        return topology_icon(module_cls, colour, size)
    if found.is_raster:
        return pick.icon(found.path)  # finished art: never recoloured
    return pick.tinted_icon(found.path, colour, size)


def guide_count(module_cls: type) -> int:
    """How many guides the module declares, counting one for a multi role."""
    layout = getattr(module_cls, "guides", None)
    roles = len(getattr(layout, "roles", ()) or ())
    if getattr(layout, "multi", None):
        roles += max(getattr(layout, "min_count", 1), 1)
    return max(roles, 1)


def topology_icon(module_cls: type, colour: str, size: int) -> QtGui.QIcon:
    """A joint chain drawn from the module's declared ``GuideLayout``.

    A module with no artwork still knows its own shape, so the fallback says
    something true -- four stacked joints for a spine -- rather than two
    letters. Different modules with the same joint count look alike, which is
    why this never substitutes for authored art.
    """
    count = min(guide_count(module_cls), 5)
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    pen = QtGui.QPen(QtGui.QColor(colour), max(size * 0.06, 1.0))
    painter.setPen(pen)
    painter.setBrush(QtGui.QColor(colour))
    margin = size * 0.18
    span = size - margin * 2
    radius = max(size * 0.09, 1.2)
    points = []
    for index in range(count):
        fraction = index / (count - 1) if count > 1 else 0.5
        points.append(QtCore.QPointF(margin + span * fraction, size - margin - span * fraction))
    for start, end in zip(points, points[1:]):
        painter.drawLine(start, end)
    for point in points:
        painter.drawEllipse(point, radius, radius)
    painter.end()
    return QtGui.QIcon(pixmap)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `make tests-ui`
Expected: PASS — 9 parametrised render cases plus 6 rule tests.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/trigger/ui/iconography.py tests/ui/test_iconography.py
git commit -m "feat: action and module icons with topology and glyph fallbacks"
```

---

### Task 6: Wire the six call sites

**Files:**
- Modify: `src/python/tik/shared/ui/tile_grid.py:23-32,63-70` (`Tile`, `TileGrid`)
- Modify: `src/python/tik/trigger/ui/palette.py:38-56,105` (`SearchPalette`)
- Modify: `src/python/tik/trigger/ui/session_view.py:182-183,248` (construction)
- Modify: `src/python/tik/trigger/ui/designer/window.py:169,241,418,669`
- Modify: `src/python/tik/trigger/ui/delegates.py:13,87`
- Modify: `src/python/tik/trigger/ui/settings_panel.py:9,106`
- Modify: `src/python/tik/trigger/ui/iconography.py` (add `icon_for_tile`)
- Test: `tests/ui/test_iconography.py` (append)

**Interfaces:**
- Consumes: `action_icon`, `module_icon`, `DEFAULT_SIZE` (Task 5); `registry.is_action_registered`, `registry.is_module_registered`, `registry.get_action`, `registry.get_module`.
- Produces: `iconography.icon_for_tile(entry, size=22) -> QIcon`, and an
  `icon_provider` keyword on `Tile`, `TileGrid` and `SearchPalette`.

**Do not touch `src/python/tik/trigger/ui/shelf.py`.** The spec counted it as a
sixth call site, but `Shelf` and `ShelfTile` are dead code — neither is imported
or constructed anywhere in `src/` or `tests/`. There are five live call sites.
Editing it would be churn; deleting it is a separate decision, not this change.

`TileGrid` and `SearchPalette` build entries from a `key` and a `category`, not
from a class, so they take an injectable icon provider rather than importing the
trigger registry. `tile_grid.py` lives in `tik/shared/` and **must not** import
`tik.trigger` at all — `tests/unit/test_import_boundaries.py` does not police
that direction, so it is on you.

- [ ] **Step 1: Write the failing test**

Append to `tests/ui/test_iconography.py`:

```python
def test_tile_grid_uses_an_injected_icon_provider(qapp):
    from tik.shared.ui.tile_grid import TileEntry, TileGrid

    calls = []

    def provider(entry, size):
        calls.append((entry.key, size))
        return QtGui.QIcon()

    grid = TileGrid(
        [TileEntry("kinematics", "Kinematics", "build")],
        "application/x-test",
        icon_provider=provider,
    )
    assert calls and calls[0][0] == "kinematics"
    assert grid.tiles["kinematics"] is not None


def test_tile_grid_without_a_provider_still_draws_the_glyph(qapp):
    from tik.shared.ui.tile_grid import TileEntry, TileGrid

    grid = TileGrid([TileEntry("kinematics", "Kinematics", "build")], "application/x-test")
    assert not grid.tiles["kinematics"].icon().isNull()


def test_session_shelf_tiles_show_the_authored_action_art(qapp):
    from tik.trigger.ui.session_view import tile_entries
    from tik.trigger.ui import iconography

    entry = next(item for item in tile_entries() if item.key == "import_asset")
    icon = iconography.icon_for_tile(entry, 22)
    assert len(_colours(icon, 22)) > 4, "should be the colour crate, not a flat chip"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `make tests-ui`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'icon_provider'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/python/tik/trigger/ui/iconography.py` a resolver that maps a shelf
or palette entry back to its class:

```python
def icon_for_tile(entry, size: int = DEFAULT_SIZE) -> QtGui.QIcon:
    """Icon for a shelf/palette entry, whichever family its key belongs to.

    Entries carry a key and a category rather than a class, so the shared
    widgets stay ignorant of the registry; this is the trigger-side adapter.
    """
    from tik.trigger.core import registry

    if registry.is_action_registered(entry.key):
        return action_icon(registry.get_action(entry.key), size=size)
    if registry.is_module_registered(entry.key):
        return module_icon(registry.get_module(entry.key), size=size)
    colour = theme.CATEGORY.get(entry.category, theme.CATEGORY["utility"])
    return glyph_icon(initials(entry.label), colour, size=size)
```

In `src/python/tik/shared/ui/tile_grid.py`, give `Tile` and `TileGrid` an
optional provider, defaulting to today's behaviour:

```python
class Tile(QtWidgets.QToolButton):
    WIDTH = 66
    HEIGHT = 58

    def __init__(self, entry, color, mime_type, parent=None, icon_provider=None):
        super().__init__(parent)
        ...
        icon = icon_provider(entry, 22) if icon_provider else glyph_icon(
            initials(entry.label), color, size=22
        )
        self.setIcon(icon)
```

`TileGrid.__init__` takes `icon_provider=None`, stores it as
`self.icon_provider`, and passes it to every `Tile` it builds in `_build`:

```python
    def __init__(self, entries, mime_type, parent=None, colors=None,
                 columns_hint: int = 2, icon_provider=None) -> None:
        ...
        self.icon_provider = icon_provider
        ...

    def _build(self) -> None:
        ...
            tile = Tile(entry, self.colors.get(entry.category, theme.CATEGORY["utility"]),
                        self.mime_type, icon_provider=self.icon_provider)
```

In `src/python/tik/trigger/ui/palette.py`, `SearchPalette.__init__` gains the
same keyword (store as `self.icon_provider`), and `_add_entry` uses it:

```python
    def __init__(self, entries, parent=None, colors=None, icon_provider=None) -> None:
        ...
        self.icon_provider = icon_provider
        ...

    def _add_entry(self, entry: PaletteEntry) -> None:
        if self.icon_provider is not None:
            icon = self.icon_provider(entry, 18)
        else:
            icon = glyph_icon(
                initials(entry.label),
                self.colors.get(entry.category, theme.CATEGORY["utility"]),
            )
        item = QtWidgets.QListWidgetItem(icon, entry.label)
        item.setData(QtCore.Qt.UserRole, entry.key)
        item.setToolTip(f"{entry.key} · {entry.category}")
        self.list.addItem(item)
```

Then pass the provider at all four construction sites:

```python
# ui/session_view.py — add `from .iconography import icon_for_tile` at the top
# :182-183
            BUILD: TileGrid(tile_entries(BUILD), MIME_TYPE, icon_provider=icon_for_tile),
            PUBLISH: TileGrid(tile_entries(PUBLISH), MIME_TYPE, icon_provider=icon_for_tile),
# :248
        self.palette = SearchPalette(action_entries(BUILD), self,
                                     icon_provider=icon_for_tile)

# ui/designer/window.py — add `from ..iconography import icon_for_tile, module_icon`
# :169
        self.shelf = TileGrid(tiles, MIME_MODULE, colors=MODULE_COLORS,
                              icon_provider=icon_for_tile)
# :241
        self.palette = SearchPalette(palette_entries, self, colors=MODULE_COLORS,
                                     icon_provider=icon_for_tile)
```

The three class-aware sites call `iconography` directly:

```python
# ui/delegates.py:87
from tik.trigger.ui.iconography import action_icon
icon = action_icon(registry.get_action(index.data(TypeRole)), size=16)
# keep the existing glyph_icon call as the branch for an unregistered type

# ui/settings_panel.py:106
self.icon.setPixmap(action_icon(action_cls, size=26).pixmap(26, 26))

# ui/designer/window.py:418 and :669
item.setIcon(0, module_icon(module_cls, side=entry.side, size=16))
self.icon.setPixmap(module_icon(module_cls, side=entry.side, size=24).pixmap(24, 24))
```

Leave `designer/window.py:553` (the `"SN"` scene-nodes chip) on `glyph_icon` —
it is a pseudo-module with no class and no artwork.

- [ ] **Step 4: Run tests to verify they pass**

Run: `make tests-ui && make tests-unit`
Expected: PASS, including the pre-existing designer and pipeline UI suites.

- [ ] **Step 5: Commit**

```bash
git add src/python/tik/shared/ui/tile_grid.py src/python/tik/trigger/ui tests/ui/test_iconography.py
git commit -m "feat: draw authored icons across tile grid, palette, tree and panels"
```

---

### Task 7: The drawing rules, and the checklists that point at them

**Files:**
- Create: `AI/icon_rules.md`
- Modify: `AI/coding_rules.md` (tik.trigger section + Related Files)
- Modify: `AI/developer_commands.md:129-143`
- Modify: `AGENTS.md` (Related Files)
- Modify: `CLAUDE.md` (tik.trigger section)

**Interfaces:** documentation only.

- [ ] **Step 1: Write `AI/icon_rules.md`**

Cover, with the spec (`docs/superpowers/specs/2026-09-04-icon-system-design.md`)
as the source:

- **The two families.** Actions are verbs: full colour, pictorial, never
  tinted. Guide modules are nouns: monochrome, diagrammatic, tinted at runtime
  by side or category.
- **Canvas.** `viewBox="0 0 24 24"` for everything, so weights stay comparable.
- **Action rules.** Full colour. The rim is a **pale tint of that icon's own
  hue, never black** — the old art's near-black outline was drawn for a light UI
  and disappears into the `#242424` ground. Draw the rim as an *underlay*: one
  group with `stroke-width="2.3"` in the rim colour, then the same shapes filled
  on top. That yields a clean outer edge with no seams where shapes overlap.
  Depth comes from tonal steps between faces. It must hold at 16px.
- **Module rules.** One flat colour; `stroke-width="1.35"`; the bone-and-joint
  grammar of thin bones with filled joint dots. **The glyph must depict the
  module's actual hierarchy** — the joint count and arrangement of its
  `GuideLayout`. `fkchain` is a four-joint arc; `arm` is a three-joint bend. A
  module icon that does not describe its topology is wrong.
- **The Qt SVG Tiny 1.2 subset**, with the reason attached so it is not
  "improved" away: Qt silently ignores `<filter>`, `<mask>`, `<text>`,
  `<foreignObject>`, `<use>`, `currentColor` and `@import`, so a file using them
  looks right in a browser and blank in Maya. Self-contained files only.
  Tinting happens on the rendered pixmap, so `currentColor` is never needed.
  `tests/unit/test_icon_assets.py` enforces this.
- **Placement and precedence.** `<plugin folder>/<name>.svg`, beside the `.py`.
  A `.png` of the same name wins — it is an artist's finished work. Deliver
  PNGs at 64px minimum, since the settings header renders at 26 and there is no
  vector to fall back on.
- **Two copy-paste templates**, one per family — lift `arm.svg` and
  `reference.svg` verbatim from this repo as the worked examples.
- **The obligation**, stated as a rule: *a new action or module folder ships a
  first-pass `<name>.svg` beside its `.py`.* Not optional, not a follow-up.

- [ ] **Step 2: Correct the stale authoring checklists**

`AI/developer_commands.md:129-143` names classes and files that do not exist.
Replace both checklists with the current shape, adding the icon step:

```markdown
### Implement New Action in tik.trigger
1. Create folder: `src/python/tik/trigger/actions/my_action/`
2. Create `my_action.py` with a class inheriting from `Action`
3. Apply `@register_action("my_action", category="build")` decorator
4. Create `my_action.svg` beside it — see `AI/icon_rules.md` (required)
5. Create `defaults.json` (optional; overrides field defaults only)
6. Write tests under `tests/unit/test_action_<name>.py`

### Implement New Module in tik.trigger
1. Create folder: `src/python/tik/trigger/modules/my_module/`
2. Create `my_module.py` with a class inheriting from `Module`
3. Apply `@register_module("my_module", category="generic")` decorator
4. Create `my_module.svg` beside it — must depict the module's guide
   topology; see `AI/icon_rules.md` (required)
5. Create `defaults.json` (optional)
6. Write tests under `tests/unit/test_module_<name>.py`
```

- [ ] **Step 3: Add the pointers**

- `AI/coding_rules.md`: a short subsection under the tik.trigger guidelines
  stating that every action and module ships an icon and pointing at
  `AI/icon_rules.md`; add it to the Related Files list at the file's end.
- `AGENTS.md`: add `AI/icon_rules.md` to the Related Files section.
- `CLAUDE.md`: one line in the tik.trigger section noting icons live beside each
  plugin (`<name>.svg`, PNG wins) with the rules in `AI/icon_rules.md`.

- [ ] **Step 4: Verify the docs are consistent with the code**

Run: `make tests-unit && make tests-ui`
Expected: PASS. Then confirm by hand that every class name, decorator signature
and file name written in the new docs matches the code as built in Tasks 1–6 —
in particular `@register_module("my_module", category="generic")` against the
signature from Task 3.

- [ ] **Step 5: Commit**

```bash
git add AI/icon_rules.md AI/coding_rules.md AI/developer_commands.md AGENTS.md CLAUDE.md
git commit -m "docs: icon drawing rules, and fix the stale authoring checklists"
```

---

## Verification

After Task 7, confirm the whole feature end to end:

```bash
make tests-unit
make tests-integration
make tests-ui
make lint
```

Then load the tool in Maya and look at it — the shelf, the pipeline tree at
16px, and an `L`/`R` module pair in the Guide Designer, which is the one
behaviour no offscreen test really proves.
