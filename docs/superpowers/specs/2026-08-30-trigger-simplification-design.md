# tik.trigger Simplification — Design Spec

Date: 2026-08-30
Status: brainstormed with Arda Kutlu; awaiting spec review.
Revises `2026-08-28-trigger-rebuild-design.md` (backend boundary, module
context) and `2026-08-29-trigger-ui-v3-and-io-graph-design.md` (§3 module I/O
stays; the UI file layout changes). Supersedes the DCC-agnostic backend
decision in both.

## 1. Goal

tik.trigger is hard to read and hard to edit. This pass makes it legible
without losing a feature, by deleting abstraction that does not pay for
itself and raising the vocabulary modules are written in.

The three specific complaints, and what is behind each:

**The backend abstraction is fiction.** `core/backend.py` declares a `Backend`
Protocol with 15 methods. `MayaBackend` has ~35. Undeclared: `connect_space`,
`read_layout`, `write_layout`, `settings_plug`, `rename_instance`,
`reparent_guides`, `make_observer`, `selected_guide`, `select_guides`,
`import_guide_instances`, `export_guide_records`, `apply_guide_poses`,
`holder`, `guide_nodes`, and more. Two declared signatures are wrong:
`create_guides` is missing `inputs`, `build_context` is missing `bind_parent`.
Nothing type-checks against it, nothing can rely on it, and it must be kept in
sync by hand for zero return.

**`ctx` is a god object living in three places.** `core/context.py` (protocol)
+ `backends/maya/context.py` (real) + `tests/helpers/trigger_fakes.py` (fake).
Adding one helper to a module's vocabulary means editing three files. And the
object does five unrelated jobs: naming service, controller factory, joint
factory, group holder, and output/attach registry.

**Wrapper over a wrapper.** Two stacked delegation layers exist:
`guides.handler.Guides` holds a `backend` and forwards to it
(`self._guides.backend.set_inputs(...)`), and module code reads
`tm.Transform.create(name=ctx.name("root", suffix="socket"),
parent=ctx.groups.socket.long_name)` — tik.maya wrapped in ctx-naming wrapped
in `.long_name` unwrapping, to say "a group called root_socket in my socket
group".

Non-goals: new modules, new actions, rig features, UI visual redesign. This is
a structural pass; behaviour is preserved except where §4 says otherwise.

## 2. Decisions (from brainstorming, 2026-08-30)

- **Maya-only.** The `Backend` Protocol, the `GuideContext`/`BuildContext`
  protocols and every fake are deleted. tik.trigger targets Maya. tik.maya
  remains the only way to touch the scene — no raw `maya.cmds` / `maya.api`
  outside tik.maya, except where tik.trigger already reaches for `cmds` for
  scene-scanning primitives that tik.maya does not expose (documented, §5.3).
- **Modules build through an injected `rig` object**, not `self`. The module
  class stays a clean declaration plus two methods; systems take `rig` as
  their first argument.
- **Boundary rule:** `rig` owns naming, tagging, group placement and
  registration. tik.maya owns mechanism. A helper that does not remove
  naming, tagging, placement or registration boilerplate does not go on `rig`.
- **Legacy `.trg` compatibility is dropped entirely.** Old Trigger files no
  longer import.
- **`instance.inputs` is the single source of truth** for wiring. The
  DAG-derived path is deleted.
- **Sockets are auto-materialized** from declared inputs, as Transforms.
- **Renames:** `core.manifest.Guides` → `GuideLayout`; `guides.handler.Guides`
  → `GuideScene`; `handler.py` → `session.py`; `backends/maya/` → `maya/`.
- **Scope is everything**, UI included.

## 3. Package shape

```
tik/trigger/
  core/                pure Python. No Maya, no Qt, no scene.
    fields, schemas, document, registry, runner, events, exceptions
    module.py          the declaration: fields, GuideLayout, Input, outputs
    manifest.py        GuideLayout, Input
  maya/                the Maya layer                      (was backends/maya/)
    rig.py             ModuleRig, GuideDraft, RigGroups    (was context.py)
    build.py           Builder, rig root, connect, spaces, afterlife
    tags.py, observer.py
  guides/
    scene.py           GuideScene + GuideHandle    (handler.py + backend.py's guide half)
    nodes.py           guide-joint create / read / tag primitives
    format.py          .trg read/write — pure Python, no Maya
  modules/, systems/
  session.py           Session, ActionHandle              (was handler.py)
  actions/
  ui/
```

Deleted files: `core/backend.py`, `core/context.py`, `backends/` (the whole
tree, contents redistributed), `tests/helpers/trigger_fakes.py`.

### 3.1 The Builder leaves `core`

Building a rig is a Maya operation. Keeping the builder in a "DCC-agnostic"
package only worked because it duck-typed a backend — the fiction being
deleted. `core/builder.py` moves to `maya/build.py` and imports tik.maya
directly.

What stays in `core` is what is genuinely pure: the document, the registry,
fields, schemas, events, and the ordering functions `order_instances` /
`order_by_connections` (already in `schemas.py`). The import-boundary test
keeps guarding `trigger/core`, and now guards something true.

`tests/unit/test_import_boundaries.py` drops its stale `trigger/session` entry
(that package never existed; the test silently skipped it) and keeps
`trigger/core`.

### 3.2 `ActionContext` sheds its backend

`ActionContext` is a good context — a small dataclass carrying paths, events
and the session. It loses only its `backend` field; actions that need the
scene construct a `GuideScene` themselves. `actions/kinematics` becomes:

```python
def run(self, ctx) -> None:
    scene = GuideScene(events=ctx.events)
    handles = scene.import_(ctx.resolve(self.guides_file))
    ...
    report = Builder(events=ctx.events).build(scope=scope, rig_name=self.rig_name, ...)
```

## 4. Deletions

### 4.1 Legacy `.trg` compatibility

Spread across five files today. All of it goes:

| What | Where |
|---|---|
| `legacy_types` class attribute | `core/module.py:43`, `modules/base`, `modules/fkchain` |
| `legacy_type()`, `legacy_table()` | `guides/format.py` |
| `Module.legacy_types` lookups in `legacy_type()` | `guides/format.py` |
| `_write_legacy_attrs()` — moduleName, upAxis/mirrorAxis/lookAxis float3s, useRefOri | `backends/maya/backend.py:239` |
| `_tag_legacy_joint()` — side + type 'Other' + otherType | `backends/maya/backend.py:284` |
| `ROOT_TYPE_ATTRS`, legacy recovery in `GuideFile` | `guides/format.py` |
| `PLUG = OUTPUT` legacy alias | `backends/maya/tags.py:25` |

The `.trg` format becomes purely tikworks': `module`, `role`, `index`,
`instance`, `settings`, plus geometry and `connections`. Files written by the
current build already carry these keys, so files authored with the current
code still load; files from the original Trigger do not.

**Kept, despite looking legacy:** two things.

`_sync_setting_attrs` is not compatibility — the Guide Designer's two-way
binding reads those plugs through `settings_plug()`. It survives with a
docstring saying so.

`Module.output_for_role()` is not compatibility either, despite its current
docstring ("legacy derivation"). It is the rule that decides which output a
new guide's primary input is pre-filled with when you draw it under another
module's guide (§4.2). It survives, renamed `output_at_role()` and
re-documented as the pre-fill rule: the output matching the parent's guide
role if one exists, else the parent's first output.

### 4.2 The dual wiring path

`ModuleInstance.parent` / `attach` plus `Builder.derive_inputs` exist so a rig
authored by guide DAG parenting still builds. With explicit inputs in the
`.trg`, that is a second, invisible wiring mechanism the builder consults, and
a recurring source of "why is this connected?".

`derive_inputs` is deleted. `instance.inputs` is read directly. Parenting
guides in the outliner stays a scene convenience — joints move together, and
creating a guide under another module's guide still pre-fills the primary
input at creation time, through `output_at_role()` (§4.1) — but the builder no
longer derives anything from the DAG. The pre-fill writes a real value into
`instance.inputs`, so what you see in the Inputs panel is what builds.

`ModuleInstance.parent` is retained: the Guide Designer tree and
`_descendants()` in the kinematics action both need to know the guide
hierarchy. `ModuleInstance.attach` is deleted; it exists only to override the
derived output name.

### 4.3 Fakes

`tests/helpers/trigger_fakes.py` (289 lines: `FakeBackend`,
`FakeBuildContext`, `FakeGuideContext`, `ToyRoot`, `ToyChain`) is deleted.

Build and module tests move to `tests/integration/trigger/` against real Maya —
where they belong, since a `FakeBuildContext` asserting that `controller()`
was called proves nothing about a rig. `tests/unit/test_core_trigger.py`,
`test_runner_trigger.py` and `test_handler_trigger.py` are rewritten against a
real `GuideScene`; the parts of them that test the document, the registry and
field validation need no scene at all and stay unit tests.

`tests/ui/` is the one exception: Maya standalone cannot host a QApplication,
which is why those tests run with `TIK_TESTS_NO_MAYA=1`. They keep a small
local stub (~30 lines, in `tests/ui/`) exposing only what the designer and
pipeline windows call. It is an ordinary Qt test double, not a src-level
abstraction.

## 5. The `rig` object

### 5.1 Two small classes, no protocols

```python
def draw_guides(self, guides):   # GuideDraft: joint(), side, side_mult
def build(self, rig):            # ModuleRig
```

`ModuleRig`'s complete vocabulary:

| Call | Replaces |
|---|---|
| `rig.guide(role, index=0)` | same |
| `rig.guides("shoulder", "elbow", "hand")` | one node per named role, in order |
| `rig.chain("segment")` | every index of a multi-role (the overloaded `ctx.guides`) |
| `rig.group("puppet", under="rig")` | `tm.Transform.create(name=ctx.name(..., suffix="grp"), parent=ctx.groups.rig.long_name)` |
| `rig.socket("root", match=guide)` | create + align + `ctx.attach` (3 lines) |
| `rig.controller(...)` | same, and creates the offset group — `ctrl.offset` |
| `rig.tweak_control(main, ...)` | same |
| `rig.controller_by_role(role)` | same |
| `rig.bind_joint(...)`, `rig.deform_joint(node)` | same |
| `rig.output(name, node)` | same |
| `rig.attach(name, node)` | escape hatch: re-point an input at your own node |
| `rig.groups`, `rig.side`, `rig.side_mult`, `rig.bind_parent`, `rig.module`, `rig.instance` | same |
| `rig.name(*tokens, suffix=)` | stays, for what the helpers do not cover |

There is deliberately **no** `rig.drive()` / `rig.constrain()`.
`tm.MatrixConstraint.create(a, b, maintain_offset=True)` already auto-names and
reads clearly; wrapping it would be exactly the wrapper-over-a-wrapper this
pass removes. Per the boundary rule, mechanism stays visible as tik.maya.

### 5.2 Three kinds of noise deleted from every module body

**`.long_name`.** Every `rig` helper takes and returns tik.maya nodes. The
unwrapping exists only because some tik.maya creators want a string; that is
absorbed inside `rig`.

**`.transform`.** `tik.maya`'s `Controller.__getattr__`
(`roles/controller.py:349`) already proxies attribute access to the underlying
node, so `controller.transform.align_to(x)` has always been writable as
`controller.align_to(x)`. Roughly 30 pointless hops across `systems/limb.py`
and the modules are removed. `.transform` stays available and is used where
the distinction genuinely matters.

**The offset-group ritual.** Every controller in the codebase is immediately
followed by `create_offset_group(name=ctx.name(...))`. `rig.controller()`
creates it and exposes `ctrl.offset`.

### 5.3 Auto-materialized sockets

A module already declares its inputs:

```python
inputs = (Input("root", primary=True, help="Where the collar hangs"),)
```

`ModuleRig.__init__` therefore creates one Transform per declared input in
`socket_grp`, named `<side>_<instance>_<input>_socket` and tagged
`trg_kind=input`. The module only positions it:

```python
socket = rig.socket("root", match=collar_guide)      # fetch + align, not create
```

Consequences:

- `ctx.attach()` is no longer required, and the builder's
  `AttachError: module did not call ctx.attach() for this input`
  (`builder.py:172`) is deleted — a failure mode that existed only because a
  module could forget three lines of boilerplate.
- Every module's socket is guaranteed to exist, be named consistently, and be
  tagged, with no per-module code.
- `rig.attach(name, node)` remains for the module that builds its own receiver.

Anim-space inputs (derived per `anim_spaces` row) do **not** get sockets — they
are consumed by `SpaceSwitch` on a controller, not by a matrix attach. Socket
materialization skips inputs with `kind="space"`.

**Sockets are Transforms, not joints.** The socket's only job is receiving a
matrix from the producer's output: no skinning role, no orientation payload, no
radius. The ground rules declare two skeletons (puppet in `rig_grp`, deform in
`bind_grp`); joint-ness is load-bearing in this codebase — guide scanning
filters `type="joint"` (`backend.py:151`, `find_by_meta(node_type="joint")`) —
so joints in `socket_grp` would form a third joint set landing in every
skin-bind dialog, export scan and "select all joints" sweep, for no gain. The
`trg_kind=input` tag makes them findable without it.

### 5.4 Before and after

```python
# now
socket = tm.Transform.create(
    name=ctx.name("root", suffix="socket"), parent=ctx.groups.socket.long_name
)
socket.align_to(collar_guide)
ctx.attach("root", socket)

collar_ctrl = ctx.controller("collar", shape="CurvedCircle", size=size,
                             match=collar_jnt, mirror="behaviour")
collar_offset = collar_ctrl.transform.create_offset_group(
    name=ctx.name("collar", suffix="offset")
)
tm.MatrixConstraint.create(socket, collar_offset, maintain_offset=True)
tm.MatrixConstraint.create(collar_ctrl.transform, collar_jnt, maintain_offset=True)
attribute.lock_and_hide(collar_ctrl.transform, ("sx", "sy", "sz", "v"))
```

```python
# after
socket = rig.socket("root", match=collar_guide)

collar_ctrl = rig.controller("collar", shape="CurvedCircle", size=size,
                             match=collar_jnt, mirror="behaviour")
tm.MatrixConstraint.create(socket, collar_ctrl.offset, maintain_offset=True)
tm.MatrixConstraint.create(collar_ctrl, collar_jnt, maintain_offset=True)
attribute.lock_and_hide(collar_ctrl, ("sx", "sy", "sz", "v"))
```

### 5.5 Systems

`systems/limb.py` and `systems/reach.py` take `rig` as their first parameter
instead of `ctx`. `build_ikfk_limb(rig, guides, ...)`. No signature change
beyond the rename and the `.transform` / `.long_name` cleanups; `LimbResult`
is unchanged except that its controller fields are used without `.transform`
at call sites.

## 6. Builder

`maya/build.py`. Four simplifications beyond the move:

- `derive_inputs` deleted (§4.2); `instance.inputs` read directly.
- `_resolve_source` and `_resolve_space_source` merge into one
  `resolve(source, strict=...)`; they differ only in whether a miss raises or
  warns.
- `_connect_one`'s attach-check branch deleted (§5.3).
- `BuildReport.contexts` → `BuildReport.rigs` (instance id → `ModuleRig`).

Unchanged, and deliberately so:

- **Two ordering passes.** `order_instances` then `order_by_connections` on
  structural inputs only. Producers must build before consumers because
  `rig.bind_parent` resolves from the producer's output, so bind joints are
  created in their final hierarchy position and never reparented.
- **Spaces connect in a separate pass** after every module exists. Space
  connections are legitimately mutually referential — an arm in head space
  while the head sits in arm space is a normal rig — so they must not reach
  the topological sort. The existing comment survives verbatim.
- **Scope warning.** A source outside the build scope logs a warning and is
  left unattached rather than failing.

## 7. GuideScene absorbs the backend

`guides.handler.Guides` currently holds a `backend` and forwards to it. The two
merge into `GuideScene`, removing a whole delegation layer. `MayaBackend`'s 541
lines split by topic, not by layer:

- `guides/scene.py` — `GuideScene` (authoring, listing, settings, layout,
  import/export, selection) and `GuideHandle`.
- `guides/nodes.py` — the primitives `GuideScene` builds on: guide-joint
  creation and tagging, `find_instances`' single-pass scene scan,
  `_instance_from_nodes`, pose apply/read, the holder.
- `guides/format.py` — `.trg` read/write, pure Python, minus §4.1.
- `maya/build.py` — `ensure_rig_root`, `finalize`, `connect`, `connect_space`,
  `afterlife`, `Builder`.
- `maya/rig.py` — `ModuleRig`, `GuideDraft`, `RigGroups`.
- `maya/tags.py`, `maya/observer.py` — unchanged but for the `PLUG` alias.

`GuideScene()` takes no backend and constructs nothing; it is the Maya scene's
guides. `trigger.maya_backend()` is replaced by `trigger.load_plugins()` plus
direct construction. `tik/trigger/__init__.py`'s quick-start docstring is
rewritten accordingly.

## 8. UI

Two files carry the UI; both become packages. No visual redesign — this is a
split plus rewiring to the new API.

`ui/guide_designer.py` (1179 lines; `GuideDesigner` alone has ~60 methods) →
`ui/designer/`:

- `window.py` — the window: panes, menus, status bar, signal wiring, refresh.
- `tree.py` — `GuideTree`, population, filtering, selection sync.
- `properties.py` — `InputRow`, property binding, plug adapters, inherit toggle.
- `scene_nodes.py` — `SceneNodesPanel`.
- `commands.py` — the verbs: create, duplicate, mirror, delete, reparent,
  connect, sever, import, export, test-build.

`ui/graph_view.py` (915 lines) → `ui/graph/`:

- `items.py` — `Port`, `NodeItem`, `WireItem`.
- `scene.py` — `GraphScene`: wire drag, slice, selection.
- `view.py` — `GraphView`: navigation, zoom, auto-layout, commands.

`ui/main.py` and `ui/session_view.py` stay as files. They lose their `backend`
parameters: `show(backend=None, dockable=True)` → `show(dockable=True)`;
`TriggerWindow` and `GuideDesigner` construct the `GuideScene` they need.
`SessionView` builds its `ActionContext` without a backend (§3.2).

## 9. Testing

`tests/integration/trigger/test_module_ground_rules.py` is the load-bearing
contract: it asserts the four-group structure and the single bind hierarchy.
It must stay green through every phase, and gains cases for auto-materialized
sockets (one Transform per non-space declared input, tagged, in `socket_grp`).

Per phase:

- Phase 1 — existing tests prove nothing regressed once legacy assertions are
  removed; `test_io_trigger.py` loses its legacy-recovery cases.
- Phase 2 — the rewritten unit tests run against a real `GuideScene`.
- Phase 3 — `test_arm_trigger.py`, `test_limb_system.py`,
  `test_reach_system.py` and `test_module_ground_rules.py` are the proof the
  `rig` rewrite preserved behaviour. They are rewritten to the new API but
  their assertions do not change.
- Phase 4 — `tests/ui/` against the local stub.

## 10. Phases

Each phase lands independently and green.

| Phase | Work |
|---|---|
| **0** | Fix the merge-conflict markers committed in `Makefile` (10, from the `TW-4-deformer-and-weights-workflows` merge — `make tests` cannot run). Confirm the suite is green. Baseline commit. |
| **1** | Delete legacy `.trg` compat (§4.1) and the dual wiring path (§4.2). |
| **2** | Collapse Protocol + backend + handler into `maya/` and `guides/` (§3, §7). Renames. Delete the fakes (§4.3). |
| **3** | `ModuleRig` / `GuideDraft`, auto-sockets, automatic offset groups, `.transform` / `.long_name` cleanup. Rewrite modules and systems (§5). |
| **4** | UI splits and rewiring (§8). |
| **5** | Docs: this spec's outcome folded into `CLAUDE.md`, `AGENTS.md`, `AI/coding_rules.md`; the stale `core/module.py` docstring (it still teaches `plugs` / `sockets`, which no longer exist); boundary test update. |

Phase 3 delivers the readability payoff; 1 and 2 clear the ground it needs.

## 11. Risks

- **Phase 3 is a wide rewrite.** Every module, both systems and every build
  test change at once. Mitigation: phases 1 and 2 land first and keep the
  suite green, so phase 3 starts from a known-good tree; the integration
  tests' assertions are held constant while their API calls change.
- **No going back to another DCC without real work.** Accepted deliberately:
  the boundary was not being honoured, and its cost was paid on every edit.
  `core` stays pure, so the data model, document, registry and ordering — the
  parts that would actually transfer — remain portable.
- **Old Trigger `.trg` files stop importing.** Accepted (§2). Files written by
  the current tikworks build still load.
- **UI split risk.** `GuideDesigner` has heavy internal state (selection sync
  between tree, graph and Maya). The split follows existing method clusters
  rather than inventing new seams, and `tests/ui/` guards it.
