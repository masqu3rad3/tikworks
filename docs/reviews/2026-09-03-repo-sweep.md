# Repo sweep — 2026-09-03

Scope: `src/python/tik` (vendor excluded) and `tests/`. Branch `refactoring`.
Aim: readability and maintainability with **no behaviour change**. Nothing was edited; this is findings only.

Tools used for the baseline: black 26.1, isort 9.0 (profile black), flake8 7.3 (line length 88), pyflakes 3.4, vulture 2.16, plus an AST sweep for function length, nesting, docstrings, naming and duplicate definitions. Every dead-code candidate below was confirmed by grepping the whole tracked repo (src, tests, snippets, docs).

## 0. Outcome (applied the same day)

The approved fixes landed as eight commits on `refactoring`, in this order. Every suite (1,400 Maya tests, 151 UI tests) passed after each one, and `make lint` is clean at the end.

| Commit | What |
|---|---|
| `2e3e347` | Unused imports, the dead ternary, the unread `keep_graph` argument, the shadowed loop variable, the `auto_switchers` field, `.coverage` untracked |
| `bfd0b73` | Duplicated helpers folded (`ensure_node`, `world_matrix_plug`, `dependency_order`, `undo_chunk`, `get_main_window`, the layout API); `create_guide_joint` reused by `GuideDraft.joint`; shared test fixtures; lint config and `make lint` / `make format` |
| `e22d075` | `from __future__ import annotations` everywhere, builtin generics, `TYPE_CHECKING` forward refs, explicit re-exports instead of the star import, every broad except explained, `NodeSpec`, every single-letter variable renamed (src and tests) |
| `0f9857f` | black + isort, no code changes |
| `595048c` | flake8 baseline cleared: long lines, unused test locals, late imports; the deformer TODO closed by its audit |
| `d746858`, `0c38c18` | 441 docstrings for public functions and classes |
| `3243750` | `GuideScene` split into `exchange.py` and `scene_groups.py` mixins; `ActionHandle`/`PhaseView` moved to `tik.trigger.handles`; menu and pane builders split into one method each; `SkinCluster` influence helper; restating comments dropped |

Left as instructed: `feedback.py`, `scene_data.py`, `user_settings.py`, `tools/polish`, the dead methods in 2.2 (except `create_guide_joint`), the raw `cmds` calls in 3.1, `plug.py`. Left by judgement: the three `unique_name` helpers (different numbering semantics, merging would rename things), `print` in `core/benchmark.py` (its tests assert on stdout), and dataclass signatures for `build_reach` / `build_ikfk_limb` / `make_record` (keyword-only and documented; a dataclass would not read better). Two claims in the original findings were wrong and are corrected below: `Session.paths` was never a property, and `guides/scene.py:45` is a spec citation, not an unbalanced quote.

### Converter: recommendation is to drop it

`maya/utils/converter` (4,400 lines, 58 tests) was probed in both directions on a ten-line rig snippet. tik.maya to cmds left `Transform.create`, `Joint.create`, plug arithmetic, `>>`, `.create("float")` and `MatrixConstraint` untouched, and the one statement it did convert became invalid Python (`cmds.getAttr(...) = 5.0`). cmds to tik.maya reported "rule applied" on `setAttr` and `connectAttr` but emitted the same cmds calls, and turned `addAttr` into `'L_arm_ctrl'.add_attr(...)`, an API tik.maya does not have. The tests exercise the rule plumbing, not real conversions, so they pass while the output is unusable. A working version would have to track every tik.maya idiom by hand, which is the effort of maintaining a second API. `EXAMPLES.md` in that folder is worth keeping as documentation (the tik-maya skill points at it); the code is not.

## 1. At a glance

| Measure | Result |
|---|---|
| Source lines (src, no vendor) | 31,900 |
| Test lines | 21,800 |
| Files black would reformat | 160 of 268 |
| Files isort would reorder | 114 |
| flake8 hits | 1,307 (920 are lines over 88 chars) |
| Unused imports in src | 60 |
| Confirmed dead functions / methods / classes in src | 38 |
| Whole files with no consumer | 6 |
| Functions over 60 lines | 31 |
| Functions with cyclomatic complexity over 12 | 8 |

Rule compliance in one line: the two structural rules (pure `tik/trigger/core`, modules never inherit modules) **pass** and are enforced by tests. The style rules (black, isort, flake8, no single-letter names) are **not enforced anywhere** and the codebase has drifted from all four.

Legend for every finding: **[S]** small, under an hour · **[M]** an afternoon · **[L]** a day or more · **[decide]** needs your call before anyone touches it.

## 2. Dead, stalled or redundant code

### 2.1 Whole files with no consumer

| File | Lines | Evidence |
|---|---|---|
| `src/python/tik/shared/ui/feedback.py` | 180 | `Feedback` class: zero references outside the file. |
| `src/python/tik/shared/ui/qtmaya.py` | 20 | zero references. `maya_window.py` has its own `OpenMayaUI` import. |
| `src/python/tik/shared/scene_data.py` | 30 | zero references. |
| `src/python/tik/trigger/ui/shelf.py` | 80 | `Shelf`, `ShelfTile`: zero references. Superseded by the menu bar and tabs. |
| `src/python/tik/shared/user_settings.py` | 411 | Only importer is `tools/polish/config.py`, which itself has no importer. It is a near copy of `trigger/config/settings.py` (same `get/set/keys/values/update/reset/is_changed/set_fallback/save` surface). |
| `src/python/tik/tools/polish/` (6 files) | 513 | No importer anywhere. `core.py` `PolishCore` is empty. `controller_shapes_mcv.py` ends with a `__main__` block that references an undefined `test_ui`. **[decide]** archive, or move to `snippets/`. |

**[decide]** `src/python/tik/maya/utils/converter/` (9 files, 3,700 lines) has no production consumer. It is reached only from its two unit tests, `snippets/converter_examples.py` and the Sphinx docs. `maya/utils/__init__.py` imports it eagerly. Inside it, vulture lists 20 unused functions and one unused class (`codegen.py` formatters, `codegen_tik.py` formatters, `parsing.TikMayaASTVisitor`, `helpers.UnsupportedMethod`, `helpers.check_method_support`, `get_variable_type` x4). If it is a developer tool, it belongs under `tools/` with a lazy import; if it is finished, delete the dead half.

### 2.2 Dead functions and methods (zero references, confirmed)

tik.trigger:
- `core/document.py:184` `path_of`
- `core/events.py:26` `unsubscribe`
- `core/steps.py:20` `STEP_SKIPPED` (imported by `maya/runner.py`, never used)
- `guides/format.py:102` `children_of`, `:120` `root_names`
- `guides/nodes.py:23` `INPUTS`; `:69` `create_guide_joint` — its body is duplicated by `maya/rig.py:66` `GuideDraft.joint`, which is what every `draw_guides` actually calls. Three comments still point at the dead one (`guides/regenerate.py:109`, `core/guide_document.py:16`, `tests/unit/test_regenerate_trigger.py:150`).
- `guides/scene.py:242` `make_observer` (only mirrored in `tests/ui/stub.py`), `:325` `apply_guide_poses`
- `maya/tags.py:16` `DOCUMENT`, `:18` `DISMISSED`
- `config/settings.py:305` `add_recent_session`
- `ui/graph/view.py:287` `add_scene_node`; `ui/designer/window.py:342` `set_owner`
- `ui/widgets.py:25` `NameEdit` (and `set_name`); `LogWidget` in the same file is live.

tik.shared:
- `ui/binding.py:253` `update_all`; `ui/versioned_field.py:109` `set_base_dir`; `ui/fields.py:203` `_FileEditor`; `ui/scene_watcher.py:120` `is_refreshing`
- `ui/theme/__init__.py`: `GROUND`, `PANEL`, `PANEL_ALT`, `ACCENT_HOVER`

tik.maya public API with no caller **and no test** **[decide]** keep-and-test, or drop:
- `core/plug.py:465` `find_proxy_plugs` (+ `__collect_proxy_plugs`)
- `types/skincluster.py:121` `original_geometry`
- `constructs/soft_ik.py:163` `distance_plug`

tik package root:
- `src/python/tik/__init__.py`: the docstring says "Controller shape library UI widget", `sys` and three Qt names are imported and unused, and `__getattr__` guards names (`ShapeLibraryModel`, `HoverOverlay`, …) that the package never defines. The whole shim is a leftover of the polish tool. **[S]**

### 2.3 Duplicated helpers

| What | Where | Fix |
|---|---|---|
| `_node(item)` — byte-identical | 8 constructs: `aim_frame`, `chain_lengths`, `matrix_spline`, `matrix_switch`, `measure`, `ribbon`, `soft_ik`, `space_switch` | One helper in `maya/core/registry.py` (or let `resolve` accept a node). **[S]** |
| `_matrix_plug(item)` — identical | `constructs/matrix_blend.py:19`, `matrix_constraint.py:23`, `measure.py:19` | Same home as `_node`. **[S]** |
| DFS topological sort, three copies | `trigger/core/schemas.py:159` `order_instances`, `:184` `order_by_connections`, `guides/regenerate.py:140` `ordered` (a fourth variant in `ui/graph/view.py:224` `_depths`) | One `core/graph.py` walker. Note the behaviour difference to preserve: `order_by_connections` **raises** on a cycle, `regenerate.ordered` **breaks** it silently. **[M]** |
| `select_nodes` | `maya/core/scene.py:62`, `guides/nodes.py:293`, `guides/scene.py:239` | Keep tik.maya's, delegate the other two. **[S]** |
| `unique_name` | `maya/core/naming.py:18`, `trigger/core/document.py:190`, `guides/scene.py:663` | Different inputs; at least share the numbering loop. **[S]** |
| Undo chunking, three mechanisms | `maya/core/decorators.py:56` `undo`, `guides/nodes.py:34` `undo_chunk`, and the untracked `maya/core/undo.py` from TW-11 | Once TW-11 lands, `undo_chunk` should live in tik.maya next to the decorator. **[S]** |
| `Session` tree API duplicates `PhaseView` | `session.py`: `add/remove/move/rename/duplicate/find/walk/paths(phase=)` (lines 531-630) repeat `PhaseView` (lines 209-276). Both are used in src, six call sites each. | Pick `PhaseView` as the one tree API; `Session` keeps `view()`/`publish`. **[M]** |
| `GuideScene` layout API stacked twice | `guides/scene.py:387` `read_layout/write_layout` and `:695` `layout/set_layout/update_layout` (with two `# --- layout` and two `# --- authoring` banners) | Keep one pair. **[S]** |
| Test fixtures | `fresh_scene` byte-identical in 7 test files; `_close`/`_axes` in `test_matrix_spline.py` and `test_ribbon.py`; `guides` in `test_connections_trigger.py` and `test_guides_trigger.py`; `_setup`, `_registered`, `_chain`, `_pair` under the same name in 3-5 files each | Move to `tests/conftest.py` or `tests/helpers/`. **[S]** |

### 2.4 Leftovers and stale artefacts

- `trigger/ui/settings_panel.py:113` — `… if False else self._has_save(action_cls)`: a dead ternary. Replace with the `else` branch. **[S]**
- `trigger/ui/designer/window.py:381` — `refresh(keep_graph=)` is accepted and passed from `graph.edited` (line 253) but never read. **[decide]** was the graph meant to survive a refresh?
- `trigger/actions/kinematics/kinematics.py:41` — `auto_switchers` is a `BoolField` shown in the UI and never read by `run()`. A user-facing setting that does nothing. **[decide]** wire it or remove it; either is a behaviour change.
- `guides/scene.py:773` — loop variable `nodes` shadows the `nodes` module import.
- 60 unused imports in src, concentrated in `ui/graph/scene.py` (13), `ui/designer/window.py` (9), `ui/designer/properties.py` (8), `ui/graph/view.py` (7), `guides/scene.py` (4, including `regenerate_all` and `document_store`). **[S]**
- `.coverage` is tracked in git and `.gitignore` does not list it. **[S]**
- `tests/developer_notes.txt` describes a coverage workflow with `PYTHONPATH=src` (the package is under `src/python`); the Makefile already has `tests-cov`. Stale. **[S]** (`tests/unit/invoke.py` is live: the Makefile runs it.)
- Untracked on this branch: `src/python/tik/maya/core/undo.py`, `src/plugins/`, `tests/unit/test_undo.py`, `tests/unit/test_packaging.py`. They belong to TW-11 (commit b540b76) but were never added.
- `maya/core/deformer.py:1` — a three-line `TODO` banner above the module docstring; `types/skincluster.py:146,167` — TODOs phrased as questions. Turn into issues or drop.

## 3. Rule compliance

| Rule (source) | Status |
|---|---|
| `tik/trigger/core` is pure Python (CLAUDE.md) | **Pass**, enforced by `tests/unit/test_import_boundaries.py`. |
| Modules never inherit from modules | **Pass**. |
| `@register_module` / `@register_action` discovery | **Pass**. |
| Consume tik.maya, no raw `cmds`/`OpenMaya` in tools | **Partial**: 12 files outside tik.maya import `cmds`; see 3.1. |
| black + flake8 + isort (`AI/coding_rules.md`) | **Not enforced**: no `[tool.black]`/`[tool.isort]`/flake8 config, no `make lint`, no hook. 160 files are not black-clean, 114 not isort-clean, 920 lines over 88 chars. |
| No single-letter variable names | 62 in src (`core/color.py` 22, `ui/delegates.py` 7), 209 in tests. |
| Type hints and docstrings on public API | See 3.2. |
| Tests run under Maya standalone; mocking is a last resort | `tests/conftest.py` builds a fake `maya` module when Maya is missing. Either document it as the headless-CI exception or remove it. |

`AI/coding_rules.md` itself is stale: it locates the library at `src/tik/maya` and calls it `tikmaya`; the package is `src/python/tik/maya`.

### 3.1 Raw `cmds` outside tik.maya, sorted by what to do

Note that `tik.maya.__getattr__` already proxies every `cmds` command (`tm.xform(...)`, `tm.ls(...)`) and wraps the result. That is undocumented in the package docstring and worth one paragraph, because it is the sanctioned route for anything without a dedicated wrapper.

Already covered by tik.maya today:
- `cmds.objExists` — `guides/nodes.py:54,61`, `guides/document_store.py:18`, `maya/build.py:122` → `Node.exists()` / `resolve`.
- `cmds.delete([...])` — `guides/scene.py:89,298`, `guides/regenerate.py:96` → `node.delete()`.
- `cmds.select` / `cmds.ls(selection=True)` — `guides/nodes.py:216,278,290-302` → `tm.select_nodes` / `tm.list_scene_nodes`.
- `cmds.xform(... translation)` get/set — `guides/nodes.py:177,268`, `snapshot.py:63`, `scene.py:417,527`, `regenerate.py:125` → `Transform.world_position`.
- `cmds.listAttr(userDefined)` + `getAttr` — `snapshot.py:30-34` → iterate `node.meta` / plugs.

Needs one small tik.maya addition (world rotation and rotate order on `Transform`), then the whole guides package drops its `cmds` import except file I/O:
- `cmds.xform(... rotation)` / `setAttr rotateOrder` — `nodes.py:178-179,271-272`, `snapshot.py:66-68`, `scene.py:533`, `regenerate.py:124-127`.

Legitimately raw (no tik.maya facility, keep but say so in a comment as `nodes.py:207` already does):
- `scriptJob` / `MMessage` callbacks — `maya/observer.py`, `shared/ui/scene_watcher.py`, `shared/ui/binding.py`.
- `cmds.file(new/import/reference)` — `guides/nodes.py:49`, `actions/import_asset`.
- `workspaceControl`, `about(version)` — `shared/ui/maya_window.py`, `ui/main.py:238`.
- `shared/ui/maya_window.py` imports `cmds` at module level (unused, `noqa`) and again inside two methods. Pick one.

### 3.2 Docstring coverage of public functions

| Package | Coverage |
|---|---|
| maya/utils, maya/core, maya/roles, maya/types | 87–100% |
| maya/constructs | 78% |
| trigger/maya | 61% |
| trigger/guides | 53% |
| trigger/core | 47% |
| trigger/session.py | 31% |
| tik/core/fields.py | 25% |
| shared/ui | 21% |
| trigger/ui | 17% |
| trigger/modules | 5% (`build`/`draw_guides` are documented on the base class; fine if that is stated once) |

Only one docstring style is in use (Google `Args:`), which is good. Four modules lack a module docstring: `core/benchmark.py`, `maya/core/benchmark.py`, `maya/utils/control_shapes.py`, `shared/ui/feedback.py`.

## 4. Best practice and modern Python

- **Typing**: 100 of 162 src files use `from __future__ import annotations`; 62 do not. Old `typing.List/Dict/Tuple` aliases survive mostly in `maya/utils` (68), `maya/core` (37) and `maya/types` (17), against 246 builtin generics elsewhere. Pick builtin generics everywhere (Python 3.10 target). **[S, mechanical]**
- **String forward references without an import**: `constructs/matrix_constraint.py:20` `"Transform"`, `guides/handle.py:30` `"GuideScene"`. Pyflakes reports them as undefined; add `if TYPE_CHECKING:` imports so editors resolve them. **[S]**
- **`from .core.scene import *`** in `maya/__init__.py` next to explicit imports, with `noqa`. Replace with the names actually re-exported. **[S]**
- **Broad `except Exception`**: 27 sites, mostly UI guards (`scene_watcher.py` 5, `ui/main.py` 4). Check each logs; the ones in `trigger/maya/runner.py`, `build.py` and `core/discovery.py` deserve a narrower type or a comment. **[S]**
- **`print`** in `core/benchmark.py` (8) and the converter engines (4) while 16 files already use `logging`. **[S]**
- **Leftover `%` formatting**: 4 sites (`shared/scene_data.py`, `converter/helpers.py`, `types/joint.py`, `core/color.py`). `os.path` only in `utils/control_shapes.py` (2); everything else is `pathlib`. **[S]**
- **`# noqa`** 90 times, mostly `F401` on re-exports. An `__all__` in those `__init__` files removes the need. **[S]**
- **Long parameter lists** (`guides/format.py:177` `make_record` 15 params, `systems/reach.py:162` `build_reach` 14, `systems/limb.py:53` `build_ikfk_limb` 12, `ui/graph/scene.py:67` `add_node` 11, `ui/graph/items.py:74` 10). A small dataclass per call keeps the signature readable without changing behaviour. **[M]**
- **Lint config to add** (behaviour-neutral, one commit): `[tool.black] line-length = 88`, `[tool.isort] profile = "black"`, a `.flake8` with `max-line-length = 88, extend-ignore = E203,W503`, `requirements-dev.txt` additions, a `make lint` target, and then one format-only commit so future diffs stay clean.

## 5. Simplification for readability

Largest files and what makes them hard to read:

| File | Lines | What to split out |
|---|---|---|
| `maya/core/plug.py` | 1,308 | One class, 65 methods, one section comment. Lines 550–1,300 are arithmetic operators and their node factories. Move them to a `PlugMath` mixin in `plug_math.py`; `Plug` stays the attribute wrapper. |
| `trigger/guides/scene.py` | 949 | `GuideScene` mixes lockstep sync, authoring, layout, `.trg` import/export (398–610), scene groups (714–777), connections, mirror/duplicate, test build and file I/O. The `.trg` record code and scene groups are separable modules. |
| `maya/types/skincluster.py`, `maya/core/deformer.py` | 812 / 779 | `get_influence_weights` (88 lines) and `set_influence_weights` (81) carry the TODO about `DeformerWeights`/`WeightsIO`; resolving that TODO is the simplification. |
| `trigger/ui/designer/window.py`, `trigger/session.py`, `trigger/ui/main.py` | 712 / 710 / 669 | `_build_menus` (117 lines) and `_build_central` (117) are long lists of widget wiring; a table of menu entries reads better. `session.py` shrinks by the `PhaseView` de-duplication above. |

Functions to break up (longest first): `systems/reach.py:162` `build_reach` 168 lines, `systems/limb_lock.py:87` `build_limb_lock` 121, `ui/main.py:113` `_build_menus` 117, `ui/designer/window.py:150` `_build_central` 117, `ui/session_view.py:162` `_build_ui` 116, `modules/arm/arm.py:138` `build` 103, `ui/designer/window.py:381` `refresh` 88, `core/reconcile.py:109` `reconcile` 87. The rig builders already carry phase comments; each phase is a natural private function.

Most complex by mccabe: `ui/model.py:138` `PipelineModel.data` (19, a role-dispatch chain → a dict of role handlers), `GuideDesigner.refresh` (19), `reconcile` (17), `ui/graph/view.py:80` `GraphView.rebuild` (16), `guides/regenerate.py:84` (14), `shared/ui/fields.py:406` `FormBuilder._make_widget` (14, nesting depth 10 → a field-type-to-factory table).

Smaller readability wins: `shared/ui/binding.py` declares seven adapter classes that each define `widget_value`/`set_widget_value`/`widget_signal`; a table of `(widget type, getter, setter, signal)` says the same in a screen. `tik/core/fields.py` has eleven `coerce` and `validate` overrides with 25% docstrings; a one-line docstring per field type would carry the schema.

## 6. Comments and docstrings

What is working: the tik.trigger code comments explain *why* and cite spec sections (`guides/regenerate.py:104-110`, `guides/scene.py:43`, `systems/limb.py:147`). Keep that voice; it is the best part of the codebase to read.

To fix:
- **Wrong**: `src/python/tik/__init__.py` docstring describes a widget that is not there.
- **Stale**: three comments name the dead `create_guide_joint` (2.2). `deformer.py:1` TODO banner. (An earlier draft flagged `guides/scene.py:45` for an unbalanced quote; it is a two-line spec citation and is fine.)
- **Restating the code**: `converter/engine_reverse.py` (9), `converter/engine.py` (7), `constructs/panel.py` (6), `core/dagnode.py` (3) — comments like `# Copy settings`, `# Build the set() call`. Delete or turn into a "why".
- **Two banner styles**: `# ======` blocks only in `converter/*` and `polish/*`; everywhere else uses `# ---- name` section rules. Standardize on the rule style.
- **Missing**: `trigger/ui` (17%) and `shared/ui` (21%) public methods. One-liners are enough for Qt overrides; the custom methods (`GraphView.rebuild`, `PipelineModel.dropMimeData`, `GuideDesigner.refresh`) need the "what state does this reconcile" sentence.

## 7. Suggested order of work

1. **Mechanical, zero-risk** [S]: unused imports; dead files and methods in 2.1/2.2 (excluding the `[decide]` rows); `settings_panel.py:113`; stale comments; `.coverage` in `.gitignore`; remove `developer_notes.txt`; commit the TW-11 files.
2. **Tooling** [S]: lint config + `make lint`, then one format-only commit. Everything after this stays clean.
3. **Consolidate** [S–M]: `_node`/`_matrix_plug`; topological sort; test fixtures; undo helpers; `Session` vs `PhaseView`; `GuideScene` layout API; `tik.__init__` shim.
4. **Move raw `cmds` behind tik.maya** [M]: add `Transform.world_rotation` and `rotate_order`, then rewrite the guides package calls; comment the legitimate remainder.
5. **Structure** [L]: split `plug.py`, `guides/scene.py`, the menu builders; break up the eight long functions.
6. **Decisions for you**: converter package fate; polish tool fate; `auto_switchers`; `keep_graph`; untested public tik.maya API; the conftest Maya mock.
