# Settings and Preferences — Design

**Date:** 2026-09-06
**Status:** Approved, pending implementation plan
**Scope:** `tik/shared/prefs`, `tik/shared/ui/prefs_dialog.py`, `tik/trigger/config`, `tik/trigger/ui`

---

## 1. Purpose

Trigger has no working preferences. Three half-built mechanisms exist, window
layout is lost on every close, and the recent-sessions list dies with the
process. This design replaces all of it with one declarative settings system,
reachable from **File › Settings…**, that carries a hard guarantee:

> **A user setting can never change the rig.** Given the same `.tr` session,
> any two artists build an identical result, whatever their preferences say.

The guarantee is enforced structurally, not by convention: the build layer
cannot import the settings package at all.

---

## 2. What exists today

| Mechanism | Location | State |
|---|---|---|
| `trigger_settings` JSON facade | `trigger/config/settings.py`, `defaults.py`, `defaults.json` | Full CRUD, tested; exactly **one** key ever read (`external_editor`) |
| `QSettings("tikworks", "trigger")` | `ui/designer/commands.py`, `ui/designer/window.py` | Live — persists `designer/auto_sync`, `designer/draw_on_create` |
| `SettingsManager` | `shared/user_settings.py` | Generic twin of the facade; used only by `tools/polish` |
| `TriggerWindow.recent_files` | `ui/main.py` | In-memory, `MAX_RECENT = 8`, never persisted |

Three defects the rewrite fixes:

1. **The store writes to the working directory.** `trigger/config/settings.py`
   builds its singleton *at import time* against a relative path, so under Maya
   it writes `tik_trigger_settings.json` into an often-unwritable cwd. This is
   why `tests/unit/test_import_boundaries.py` forbids `tik/trigger/ui` from
   importing `tik.trigger.config`, and why `script.py:editor_command()` wraps
   its read in a bare `try/except`.
2. **Defaults are maintained twice.** `defaults.py` states in its own docstring
   that it "should be kept in sync with defaults.json". Nothing enforces it.
3. **`FACTORY_DEFAULTS` violates the guarantee.** It declares `mirror_mapping`,
   `rig_build.side_suffixes`, `rig_build.center_prefix`,
   `rig_build.attribute_locking` and `default_units` — every one of which
   changes what gets built.

---

## 3. The guarantee, precisely

The line is **build determinism from a saved session**: given the same `.tr`,
two artists produce the same rig.

Settings *may* influence authoring — Auto Sync writes captured guide poses into
the document, and that is fine, because the change lands in the `.tr` where it
is visible, reviewable and version-controlled. Settings may *not* be read
anywhere on the path from a saved session to a built rig.

There is no tier system, no per-setting classification. One rule, one
enforcement point.

### Enforcement

`tests/unit/test_import_boundaries.py` gains prefs entries:

```python
PREFS = ("tik.trigger.config", "tik.shared.prefs")

FORBIDDEN = {
    ...
    "trigger/core":    ("maya", "tik.maya") + QT + PREFS,
    "trigger/modules": PREFS,
    "trigger/systems": PREFS,
    "trigger/maya":    PREFS,   # rig, build, runner, tags
    "trigger/actions": PREFS,
    "trigger/guides":  PREFS,   # the scene obeys flags the UI sets on it
}
```

Only `tik/trigger/ui` reads preferences. The build API takes no settings
argument and gains none.

`trigger/guides` is included deliberately. `GuideScene.auto_sync` and
`GuideScene.draw_on_create` stay plain attributes that the UI sets; the scene
never reaches for a preference itself. That keeps the existing shape — the UI
decides policy, the scene obeys.

### Rejected keys

`mirror_mapping`, `rig_build.*` and `default_units` are deleted, not migrated.
Anything genuinely needed belongs in the `.tr` session document.

`guide_display.size` is also rejected, for a subtler reason: guide `radius` is
captured into the document (`guides/format.py`), so a global display-size
preference would write per-artist noise into everyone's diffs. If a display
scale is wanted later it must be view-only and never written back.

---

## 4. Structure

### 4.1 The shared spine — `tik/shared/prefs/`

Pure Python. No Qt, no Maya. Trigger is the only consumer today; the package is
generic so a second tool can contribute pages later without a new mechanism.

| File | Responsibility |
|---|---|
| `store.py` | `PrefStore` — one JSON file; staged vs committed values; `is_changed()`, `apply()`, `revert()`, `reset()`. Resolves to `~/TikWorks/<name>.json`, always absolute. Loads lazily on first access, never at import. |
| `page.py` | `PrefPage` — a `tik.core.fields.Schema` subclass carrying `name`, `label`, `order`. Its `Field`s are the settings. |
| `registry.py` | `@register_page` and ordered lookup, following the existing `@register_action` / `@register_module` pattern. |

`tik.shared` may import `tik.core`, so `PrefPage` building on
`tik.core.fields.Schema` respects the existing layering.

### 4.2 The dialog — `tik/shared/ui/prefs_dialog.py`

Generic. Reads the registry, builds one `FormBuilder` per page, owns the search
index and the footer buttons. Knows nothing about Trigger.

### 4.3 Trigger's pages — `tik/trigger/config/`

`settings.py`, `defaults.py` and `defaults.json` are deleted. In their place:

```
trigger/config/
  __init__.py        # exposes the lazy `prefs` accessor
  pages/
    interface.py
    guides.py
    files.py
    tools.py
```

Each page is a declaration:

```python
@register_page
class InterfacePrefs(PrefPage):
    name, label, order = "interface", "Interface", 10

    WINDOW = FieldGroup("Window")
    LOG = FieldGroup("Log")

    restore_geometry = BoolField(
        True, group=WINDOW, label="Restore size and position"
    )
    log_max_lines = IntField(
        2000, min=100, max=100000, group=LOG, label="Maximum lines",
        help="Lines kept in the Log dock before the oldest are dropped.",
    )
```

**Adding a setting is one field line.** No defaults dict to keep in sync, no
dialog code to touch, no layout to author. Defaults live in the declaration and
nowhere else; `Schema.schema()` generates a JSON description if one is ever
needed.

**Every field must declare `help`.** It is the tooltip *and* the search corpus,
so a field without it is invisible to search on anything but its label. This is
a hard rule enforced by `tests/unit/test_prefs_pages.py`, not a style
preference.

Access is attribute-based and validated: `prefs.interface.log_max_lines`.
`prefs` is a lazy accessor — importing `tik.trigger.config` performs no file
I/O; the store loads on first attribute access.

---

## 5. Storage split

Two stores, one narrow rule:

> **Human-readable value → JSON. Opaque platform blob → `QSettings`.**

Everything a user might read or hand-edit lives in `~/TikWorks/trigger.json`.
Exactly two keys stay in `QSettings`: the `saveGeometry()` and `saveState()`
byte blobs, gated by the `restore_geometry` and `restore_dock_layout` booleans
in JSON.

Rationale: the JSON file stays legible and hand-editable — genuinely useful for
a TD pushing a studio default — instead of carrying base64 that varies by Qt
version and monitor arrangement.

*Alternative considered:* base64 the blobs into JSON for a single file. Rejected
as making the readable file unreadable for no functional gain.

---

## 6. Settings inventory (v1)

### Interface

| Group | Setting | Today |
|---|---|---|
| Window | Restore size and position | Not persisted; `resize(1180, 720)` hardcoded |
| Window | Restore dock layout | Not persisted |
| Log | Open log on error | Does not exist |
| Log | Maximum lines | Does not exist |
| Log | Verbosity | Replaces the unread boolean `debug_mode`. `ChoiceField` over `Error` / `Warning` / `Info` / `Debug`, default `Info`, mapped to the standard `logging` levels |
| Graph | Snap to grid | Per-window toggle, lost on close |
| Graph | Show grid | Per-window toggle, lost on close |
| Graph | Default collapse mode for new nodes | `MODE_FULL` hardcoded in `ui/graph/view.py` |

### Guides

| Group | Setting | Today |
|---|---|---|
| Authoring | Auto Sync by default | `QSettings designer/auto_sync` |
| Authoring | Draw new modules on create | `QSettings designer/draw_on_create` |
| Confirmations | Confirm Delete All Modules | Always asks |
| Confirmations | Confirm Reset Scene | Always asks |

### Files & Sessions

| Group | Setting | Today |
|---|---|---|
| Recent | Remember recent sessions | `recent_files` in-memory only |
| Recent | How many to keep | `MAX_RECENT = 8` hardcoded |
| Browsing | Remember last folder | Not remembered |
| Browsing | Default session folder | Does not exist (`FileField(mode="dir")`) |
| Autosave | Enable autosave | Declared, never implemented |
| Autosave | Interval | Declared, never implemented |
| Confirmations | Warn on unsaved close | Always asks |

### External Tools

| Group | Setting | Today |
|---|---|---|
| Editor | External editor command | The one live setting. Empty means "OS default handler" |

`shared/io.py:open_external(path, command)` already substitutes `{path}` into
the command string and otherwise appends the path, so a launcher with arguments
(`code -g {path}`) is expressible in the single command field. A separate
arguments-template setting was considered and dropped: it would invent a second
convention alongside a working one.

Confirmations sit on their domain page rather than in a shared page; search
makes the split cheap to live with.

---

## 7. The dialog

Modal, opened from **File › Settings…** (`Ctrl+,`). Flat category list with a
search field above it, page on the right, buttons along the bottom.

```
┌ Trigger Settings ───────────────────────────────────────────┐
│ ┌───────────────┬─────────────────────────────────────────┐ │
│ │ Search…       │  ▾ Window                                │ │
│ ├───────────────┤      Restore size and position    [x]    │ │
│ │ Interface   ◀ │      Restore dock layout          [x]    │ │
│ │ Guides        │  ▾ Log                                   │ │
│ │ Files & Sess. │      Open log on error            [ ]    │ │
│ │ External Tools│      Maximum lines             [ 2000 ]  │ │
│ │               │      Verbosity                 [ Info ▾] │ │
│ │               │  ▸ Graph — snap, grid, collapse mode      │ │
│ └───────────────┴─────────────────────────────────────────┘ │
│ [Restore Defaults]              [Cancel] [Apply] [   OK   ] │
└─────────────────────────────────────────────────────────────┘
```

Pages render through `FormBuilder`, so `FieldGroup` folds look and behave
exactly like every other form in Trigger.

### 7.1 Search

Typing filters **the settings themselves, across every page**. The page becomes
a results list: each matching field rendered in place under a
`Category › Group` caption, fully editable. The category list dims while a
search is active.

Matching runs over the field label **and** its `help` text, so a term finds
settings whose label never mentions it. The index is flat, built once from
`Schema.fields()` across the registry. A search matching nothing shows an
empty page with a "No settings match" line, not a blank panel.

### 7.2 Apply semantics

Edits stage in memory. **Apply** writes and pushes them live, **OK** does both
and closes, **Cancel** discards. **Restore Defaults** resets the currently
selected page to its declared defaults, staged like any other edit, so Cancel
still backs out; it is disabled while a search filter is active, since the
results list spans pages and "the current page" has no meaning there.

### 7.3 Delivering an applied setting

No observer framework. `PrefsDialog` emits `applied(changed_keys)`;
`TriggerWindow` is the single subscriber and dispatches through a small explicit
table (`log_max_lines` → `self.log.set_max_lines(...)`, `graph_snap` → each open
view). Everything else is read at point of use — `prefs.files.max_recent` is
read when the recent menu rebuilds, never cached.

One window, one subscriber, no widget-lifetime problems, and the dispatch table
is the single place documenting which settings need pushing versus which are
simply read next time.

### 7.4 Naming hazard

`tik/trigger/ui/settings_panel.py` already exists and is the **per-action
settings form**, not application settings. All new code is named `prefs_*` to
avoid the collision. Renaming the existing file is out of scope.

---

## 8. Migration

- **`QSettings designer/auto_sync` and `designer/draw_on_create`** — read once
  on the new store's first run, written into JSON, then never read from
  `QSettings` again. Worth the handful of lines: a rigger who turned Auto Sync
  off would be annoyed to find it back on.
- **Old `tik_trigger_settings.json`** — not migrated. It was written to the
  process's working directory, so copies are scattered and unfindable, and only
  `external_editor` was ever meaningful.
- **Rig-affecting keys** — deleted (§3).
- **`tik/shared/user_settings.py`** — left in place, still serving
  `tools/polish`. It is now the odd one out, and migrating Polish onto the spine
  is a clean follow-up. This is deliberate: `user_settings` and `polish` are
  parked areas under a standing decision not to disturb them.

---

## 9. Cleanup phase

The work ends with a dedicated cleanup pass. There are no backward
dependencies to preserve, so nothing superseded is kept "just in case". The
pass is a scheduled step, not a best-effort afterthought, and it has its own
verification.

**Known leftovers to remove:**

| Item | Why it goes |
|---|---|
| `trigger/config/settings.py` | Duplicate `UserSettings` + facade, superseded by `PrefStore` |
| `trigger/config/defaults.py` | Defaults now live in field declarations |
| `trigger/config/defaults.json` | Same |
| `editor_command()` in `actions/script/script.py` | Moves to the UI layer; the action layer may no longer read prefs |
| Its `try/except` guard | Guards a failure mode the lazy, absolute-pathed store removes |
| `"trigger/ui": ("tik.trigger.config",)` in `FORBIDDEN` | The import-time write it existed to prevent is gone |
| `MAX_RECENT` in `ui/main.py` | Becomes a setting |
| `QSettings` reads in `ui/designer/window.py`, `ui/designer/commands.py` | Replaced by prefs, post-migration |
| `tests/unit/test_settings_trigger.py` | Tests a deleted class; rewritten against `PrefStore` |
| `QSettings` assertions in `tests/ui/test_guide_designer.py` | Assert a storage location that no longer holds those keys |

The `QSettings` sandbox in `tests/ui/conftest.py` **stays** — geometry and dock
state still use `QSettings`, and the sandbox still needs to keep them off a
developer's real machine.

**Sweep, not just a checklist.** The listed items are what is known now; the
pass also searches for orphans the implementation itself leaves behind:

1. `grep` for every deleted symbol (`trigger_settings`, `FACTORY_DEFAULTS`,
   `SETTINGS_FILE_NAME`, `MAX_RECENT`, `debug_mode`, `editor_command`,
   `mirror_mapping`, `rig_build`, `default_units`, `guide_display`) across
   `src`, `tests` and `docs` — zero hits outside the spec history.
2. `grep` for `QSettings` — hits only in the geometry path and the test sandbox.
3. Delete stale `.pyc`/`__pycache__` entries for removed modules.
4. `make lint` clean, full test suite green.
5. Update `CLAUDE.md` and `AI/coding_rules.md` with the settings rule and the
   new layering entries.

---

## 10. Testing

| Test | Covers |
|---|---|
| `tests/unit/test_prefs_store.py` | Lazy load (no I/O at import), `~/TikWorks` resolution, staged/apply/revert/reset, unknown keys ignored, corrupt file tolerated, first-run defaults |
| `tests/unit/test_prefs_pages.py` | Every registered page validates; defaults round-trip through JSON; no duplicate field names across pages; every field carries `help` text |
| `tests/unit/test_import_boundaries.py` | **The guarantee** — extended `FORBIDDEN` |
| `tests/ui/test_prefs_dialog.py` | Dialog builds from the registry; search filters across pages and matches `help`; Apply writes; Cancel discards; Restore Defaults stages |
| `tests/ui/test_menus.py` | `Settings…` present under File |
| `tests/unit/test_settings_trigger.py` | Rewritten against `PrefStore` |

Unit tests run headless; UI tests run under `TIK_TESTS_NO_MAYA=1`,
`QT_QPA_PLATFORM=offscreen` (`make tests-ui`). No test in this feature needs
Maya — the settings system is Maya-free by construction, which is itself a
consequence of the guarantee.

---

## 11. Out of scope

- Migrating `tools/polish` onto the shared spine.
- Renaming `ui/settings_panel.py`.
- Studio-level or project-level preference layering (a machine-wide default
  file beneath the user's). The store's fallback mechanism leaves room for it;
  nothing implements it here.
- Per-setting "don't ask again" checkboxes inside the confirmation dialogs
  themselves. The preferences exist; wiring a dialog to toggle its own
  preference is a later convenience.
