# tik.trigger Structural Organization Plan

## Context

`tik.trigger` is the next iteration of the Trigger rigging tool, to be built inside the `tikworks` repo. It will use `tik.maya` as its core DCC integration layer.

**Goal:** Create a well-structured foundation that avoids Trigger's mistakes while preserving what works.

**Key Influences:**
- **tik_manager4** settings/UI pattern: Declarative `ui_definition` dicts that auto-generate Qt UI
- **labelmatic_rig** config/core separation: Clean separation between user settings, config data, and core logic
- **tik.maya** registry pattern: Decorator-based plugin registration

---

## Part I: Analysis of Trigger Codebase

### What Works (Keep These Patterns)

| Pattern | Description |
|---------|-------------|
| **ActionCore + ACTION_DATA** | Data-driven actions with `feed()`, `action()`, `save_action()` interface |
| **ModuleCore + GuidesCore** | Clear separation between guide creation and rig building |
| **Dynamic Discovery** | Auto-discover action/module classes |
| **Session-based Workflow** | Separate guide sessions from action/build sessions |

### What to Improve (Avoid These Issues)

| Issue | Problem | Solution |
|-------|---------|----------|
| Mutable defaults | `limb_data = {"members": []}` shared across instances | Use `None` + `default_factory` |
| Bare `except:` | Catches everything, hides bugs | Specific exception types + proper chaining |
| Inconsistent `super()` | Old-style vs new-style | Mandatory new-style |
| No type hints | Unknown what functions expect | Enforce via mypy/pyright |
| Module-level logging | Issues in headless/import scenarios | Lazy `logging.getLogger(__name__)` |
| Single-file modules/actions | Doesn't scale to many modules | Folders with named .py files |
| Complex discovery logic | Current rglob is flawed | Folder-based discovery + registry helpers |

---

## Part II: Proposed tik.trigger Structure

```
tikworks/src/python/tik/
├── trigger/                          # tik.trigger package
│   ├── __init__.py                   # Public API entry point
│   │
│   ├── core/                         # Core framework (DCC-agnostic)
│   │   ├── __init__.py
│   │   ├── action_core.py           # ActionCore base
│   │   ├── module_core.py          # ModuleCore + GuidesCore bases
│   │   ├── session.py               # Session base class
│   │   ├── exceptions.py            # Custom exception hierarchy
│   │   ├── registry.py             # @register_action, @register_module decorators
│   │   └── schemas.py              # Dataclasses for structured data
│   │
│   ├── api/                          # Public facade layer
│   │   ├── __init__.py
│   │   ├── actions.py               # Action registry API
│   │   ├── modules.py              # Module registry API
│   │   └── session.py              # Session management API
│   │
│   ├── actions/                       # Rig build actions (folder per action)
│   │   ├── __init__.py             # Discovery + registry
│   │   ├── _base.py               # ActionCore base template
│   │   └── import_asset/         # Example action folder
│   │       ├── import_asset.py    # ImportAssetAction : ActionCore
│   │       ├── ui_definition.json
│   │       └── defaults.json
│   │
│   ├── modules/                      # Rig limb modules (folder per module)
│   │   ├── __init__.py            # Discovery + registry
│   │   ├── _base.py              # ModuleBase template
│   │   └── base/                 # Example module folder
│   │       ├── base.py           # Guides + Base classes
│   │       ├── ui_definition.json
│   │       └── data.json          # Module data
│   │
│   ├── session/                     # Session management
│   │   ├── __init__.py
│   │   ├── guide_session.py
│   │   ├── action_session.py
│   │   └── io.py
│   │
│   ├── ui/                          # Qt UI (decoupled from logic)
│   │   ├── ...
│   │
│   ├── config/                      # Configuration
│   │   ├── __init__.py
│   │   ├── defaults.json           # FACTORY_DEFAULTS (JSON)
│   │   ├── settings.py             # UserSettings + singleton
│   │   └── io.py                   # JSON I/O utility
│   │
│   └── tests/
│       └── ...
│
├── maya/                             # tik.maya (existing)
└── core/                             # tik.core (existing)
```

---

## Part III: Key Architectural Decisions

### 1. Modules and Actions as Folders with Named .py Files

```
actions/import_asset/
├── import_asset.py    # Main action class
├── ui_definition.json # UI definition (optional)
└── defaults.json       # Default values (optional)

modules/base/
├── base.py           # Guides + Base classes
├── ui_definition.json # (optional)
└── data.json          # Module data
```

### 2. Registry Decorator

Explicit registration via decorator for actions and modules:

```python
# core/registry.py
_ACTIONS_REGISTRY: dict[str, type] = {}
_MODULES_REGISTRY: dict[str, type] = {}

def register_action(name: str) -> Callable[[Type[T]], Type[T]]:
    """Decorator to register an action class."""
    def inner(cls: Type[T]) -> Type[T]:
        _ACTIONS_REGISTRY[name] = cls
        return cls
    return inner

def register_module(name: str) -> Callable[[Type[T]], Type[T]]:
    """Decorator to register a module class."""
    def inner(cls: Type[T]) -> Type[T]:
        _MODULES_REGISTRY[name] = cls
        return cls
    return inner

def get_action(name: str) -> Type["ActionCore"]:
    return _ACTIONS_REGISTRY.get(name)

def get_module(name: str) -> Type["ModuleCore"]:
    return _MODULES_REGISTRY.get(name)

# actions/jointify/jointify.py
from tik.trigger.core import register_action

@register_action("jointify")
class JointifyAction(ActionCore):
    pass
```

**Why this approach:**
- Explicit registration - no discovery ambiguity
- No circular import issues
- Easy to override/replace for testing
- Clear contract: this class implements this action/module

### 3. Folder-Based Discovery

Discovery scans child folders and validates each folder contains a valid ActionCore/ModuleCore subclass:

```python
# actions/__init__.py
from pathlib import Path
from tik.trigger.core.registry import _ACTIONS_REGISTRY, _find_action_subclass

def discover_actions():
    """Discover action folders and register valid ActionCore subclasses."""
    actions_base = Path(__file__).parent
    excluded = {"_base", "__pycache__"}

    for action_dir in actions_base.iterdir():
        if not action_dir.is_dir() or action_dir.name in excluded:
            continue

        # Look for .py file matching folder name OR any .py with ActionCore subclass
        main_py = action_dir / f"{action_dir.name}.py"
        if main_py.exists():
            py_file = main_py
        else:
            # Fallback: scan for any .py containing ActionCore subclass
            py_file = _find_action_class(action_dir)
            if not py_file:
                continue  # No valid action class found

        # Import and find the ActionCore subclass
        module = importlib.import_module(
            f"tik.trigger.actions.{action_dir.name}.{py_file.stem}"
        )
        action_cls = _find_action_subclass(module, ActionCore)
        if action_cls:
            _ACTIONS_REGISTRY[action_dir.name] = action_cls

        # Validate optional JSON files exist (warn if missing)
        _validate_json_files(action_dir, ["ui_definition.json", "defaults.json"])
```

### 4. Dataclasses for Structured Data (schemas.py)

Use dataclasses for clean, typed data structures:

```python
# core/schemas.py
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class GuideData:
    """Data for a single guide joint."""
    name: str
    position: tuple[float, float, float]
    rotation: tuple[float, float, float]
    side: str = "C"
    parent: Optional[str] = None
    children: list[str] = field(default_factory=list)

@dataclass
class ModuleInstanceData:
    """Data for an instantiated module in a session."""
    module_type: str  # e.g., "bipedArm"
    instance_id: str  # unique identifier
    guides: list[GuideData] = field(default_factory=list)
    settings: dict = field(default_factory=dict)

@dataclass
class ActionInstanceData:
    """Data for an instantiated action in a session."""
    action_type: str  # e.g., "jointify"
    order: int
    settings: dict = field(default_factory=dict)
    enabled: bool = True

@dataclass
class SessionData:
    """Root session data structure."""
    version: str = "2.0"
    modules: list[ModuleInstanceData] = field(default_factory=list)
    actions: list[ActionInstanceData] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
```

### 5. UI Definition Pattern (from tik_manager4)

Actions and modules declare their UI via `ui_definition.json`:

```json
{
  "cameras": {
    "display_name": "Cameras",
    "type": "list",
    "value": []
  },
  "start_frame": {
    "display_name": "Start Frame",
    "type": "integer",
    "value": 1
  },
  "resolution": {
    "display_name": "Resolution",
    "type": "vector2Int",
    "value": [1920, 1080]
  }
}
```

**Supported types** (from `DataTypes` in tik_manager4):
- `boolean`, `string`, `integer`, `float`
- `spinnerInt`, `spinnerFloat`
- `combo` (with `items` array)
- `vector2Int`, `vector3Int`, `vector2Float`, `vector3Float`
- `pathBrowser`, `fileBrowser`
- `multi` (nested group)
- `separator`, `group`

### 6. Config/Core Separation (from labelmatic)

JSON for defaults, Python class for settings:

```json
// config/defaults.json
{
  "debug_mode": false,
  "mirror_mapping": {"L_*": "R_*", "*_L": "*_R"},
  "recent_sessions": [],
  "max_number_of_recent_sessions": 10
}
```

```python
# config/settings.py
class UserSettings:
    """Dict-like settings with file persistence."""
    def __init__(self, file_name: str) -> None:
        self._file_path = Path.home() / file_name
        self._data: dict = {}
        self._load()

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        self._data[key] = value
        self._save()

settings_facade = UserSettings("tik_trigger_settings.json")
```

### 7. Session Management

Separate session types with typed data:

```python
# session/guide_session.py
from dataclasses import asdict
from tik.trigger.core.schemas import SessionData, ModuleInstanceData, GuideData

class GuideSession:
    """Session for guide/skeleton data."""

    def __init__(self, file_path: Optional[Path] = None) -> None:
        self.file_path = file_path
        self.data = SessionData()

    def add_module(self, module_type: str, instance_id: str) -> ModuleInstanceData:
        mod = ModuleInstanceData(module_type=module_type, instance_id=instance_id)
        self.data.modules.append(mod)
        return mod

    def save(self, file_path: Optional[Path] = None) -> Path:
        io.write(file_path or self.file_path, asdict(self.data))
        return file_path

    def load(self, file_path: Path) -> None:
        self.data = SessionData(**io.read(file_path))
        self.file_path = file_path
```

---

## Part IV: Discovery Implementation Details

### Current Issues with rglob Discovery

```python
# WRONG - current approach
for _file in _actions_base.rglob("*.py"):  # Finds ALL nested files
    _module_name = f"{_file.parent.name}.{_file.stem}"  # Wrong paths
    _module = importlib.import_module(f"{__name__}.{_module_name}")  # Broken
```

**Problems:**
1. `rglob` finds ALL `.py` files recursively, including nested ones
2. Module path construction doesn't match actual package structure
3. For `actions/jointify/jointify.py`, correct import is `tik.trigger.actions.jointify.jointify`

### Corrected Discovery Logic

```python
# Corrected approach
for action_dir in actions_base.iterdir():  # Only direct children
    if not action_dir.is_dir() or action_dir.name.startswith("_"):
        continue

    # Try main file named after folder
    main_file = action_dir / f"{action_dir.name}.py"
    if not main_file.exists():
        continue  # Folder must contain matching .py file

    # Import using full path
    module = importlib.import_module(
        f"tik.trigger.actions.{action_dir.name}.{main_file.stem}"
    )

    # Find ActionCore subclass
    for name, obj in inspect.getmembers(module, inspect.isclass):
        if issubclass(obj, ActionCore) and obj is not ActionCore:
            _ACTIONS_REGISTRY[action_dir.name] = obj
            break
```

---

## Part V: Implementation Phases

### Phase 1: Foundation
- [x] Create `tik/trigger/` package structure
- [x] Implement `core/exceptions.py`
- [x] Implement `core/registry.py` - @register_action, @register_module decorators
- [x] Implement `core/schemas.py` - dataclasses
- [x] Implement `core/action_core.py` - ActionCore base
- [x] Implement `core/module_core.py` - ModuleCore + GuidesCore

**Completed:** April 2026
- All core files implemented with full type hints and docstrings
- Unit tests created in `tests/unit/test_*_trigger.py` (124 tests, all passing)

### Phase 2: Config System
- [x] Implement `config/defaults.json` - FACTORY_DEFAULTS (JSON)
- [x] Implement `config/settings.py`
- [x] Implement `config/io.py`

**Completed:** April 2026
- `config/io.py` - ConfigIO class for JSON I/O with error handling
- `config/defaults.py` - FACTORY_DEFAULTS dictionary (synced with defaults.json)
- `config/settings.py` - UserSettings class and trigger_settings singleton facade
- Unit tests: `tests/unit/test_io_trigger.py` (18 tests), `tests/unit/test_settings_trigger.py` (35 tests)

### Phase 3: Plugin System
- [x] Implement `actions/_base.py`
- [x] Implement `actions/__init__.py` with corrected folder-based discovery
- [x] Implement `modules/__init__.py` with same pattern
- [x] Wire JSON file loading

**Completed:** April 2026
- Corrected folder-based discovery (scans direct child directories only)
- Each action/module folder must contain matching .py file (e.g., `jointify/jointify.py`)
- Auto-discovers and registers actions/modules on import
- Loads optional `ui_definition.json` and `defaults.json`/`data.json`
- Unit tests: `tests/unit/test_discovery_trigger.py` (24 tests)

### Example Action: import_asset
- **Location:** `actions/import_asset/`
- **Class:** `ImportAssetAction` (inherits ActionCore)
- **Purpose:** Imports external files (.ma, .mb, .obj, .fbx, .abc, .usd) into Maya
- **Settings:** file_path, scale, root_suffix, parent_under
- **Pattern:** feed() validates file path, action() performs import

### Example Module: base
- **Location:** `modules/base/`
- **Classes:** `Guides` (GuidesCore), `Base` (ModuleCore)
- **Purpose:** Simplest module - creates a single root joint
- **Settings:** build_controls
- **Note:** Guides registered as `base_guide`, Module registered as `base`

### Phase 4: Session Management
- [ ] Implement `session/io.py`
- [ ] Implement `session/guide_session.py`
- [ ] Implement `session/action_session.py`

### Phase 5: API Layer
- [ ] Implement `api/actions.py`
- [ ] Implement `api/modules.py`
- [ ] Implement `api/session.py`

---

## Key Files to Reference

| File | Purpose |
|------|---------|
| `tikworks/src/python/tik/maya/core/registry.py` | Registry pattern reference |
| `tikworks/src/python/tik/trigger/actions/__init__.py` | Current (flawed) discovery |
| `tik_manager4/ui/layouts/settings_layout.py` | SettingsLayout auto-UI |
| `labelmatic/scripts/labelmatic_rig/user_settings.py` | UserSettings pattern |
| `labelmatic/scripts/labelmatic_rig/defaults.json` | FACTORY_DEFAULTS pattern (JSON) |

---

## Verification

1. `from tik.trigger.core import ActionCore, ModuleCore, GuidesCore`
2. Actions/modules auto-discovered from folders
3. `ui_definition.json` generates Qt UI via SettingsLayout
4. Session saves/loads with dataclass schema
