# Trigger Workflow, UI and TD API — Design Spec (v2)

Date: 2026-08-28
Status: brainstormed with Arda Kutlu; awaiting spec review.
Supersedes the workflow/session/UI parts of
`2026-08-28-trigger-rebuild-design.md`. The tik.maya constructs and the typed
`tik.core.fields` from that spec stay; the scene-centric session, builder scope
and UI are replaced.

## 1. Goal

Trigger builds rigs from a **blueprint**: a `.tr` session is an ordered, nested
list of actions; pressing Build resets the scene and runs them. The product
must nail the *rebuild story* — open a session, Build from scratch, change one
action, Build again — with a UI a TD wants to use and a scripting handler that
reads like a script.

Non-goals for this spec: module feature parity (arm, leg, ...) beyond what the
pipeline needs to run; Build & Publish version control (publisher hook only);
old standalone utilities.

## 2. Principles

1. **The session is the rig.** Nothing in a session reads "whatever is in the
   scene". Every input is a file path or an explicit value stored in the
   action.
2. **Guides are an asset.** The Guide Designer authors a `.trg` file in the
   old Trigger joint-list format (compatible with existing files). The
   Kinematics action consumes a `.trg`. Test Build is a preview.
3. **Actions nest.** Any action can have children. Run order is depth-first:
   parent, then its children in order, then the next sibling. A disabled
   parent skips its subtree. Children are ordered steps, not callbacks.
4. **Sessions reference sessions.** A Reference action renders the referenced
   session's actions inline (dimmed, chain glyph). Ticking or editing a linked
   row writes an *override* into the referencing session; the referenced file
   is never modified. Every file builds on its own.
5. **Two-way with Maya** where it helps authoring (Guide Designer), never as a
   source of truth for the session.

## 3. Session document (`.tr`, schema 4)

```json
{
  "schema": 4,
  "meta": {"created_at": "...", "author": "...", "modified_at": "..."},
  "actions": [
    {"name": "import_model", "type": "import_model", "enabled": true,
     "settings": {"file": "geo/hero_muscle_v02.ma"},
     "children": [
       {"name": "rename_geo", "type": "script", "enabled": true,
        "settings": {"file": "scripts/rename_geo.py"}, "children": []}
     ]},
    {"name": "baseRig", "type": "reference", "enabled": true,
     "settings": {"file": "rigs/baseRig.tr", "version": "latest", "include": "all",
                  "overrides": {
                    "scripts/head_rotation": {"enabled": false},
                    "kinematics": {"settings": {"guides_file": "hero_muscle.trg"}}}},
     "children": []}
  ]
}
```

- Paths are stored relative to the session file when inside its tree;
  absolute otherwise. Resolved at run time from `ctx.paths["directory"]`.
- Action **path** = `/`-joined names from the root (`scripts/head_rotation`);
  names are unique among siblings.
- Old flat `.tr` (schema ≤ 3 or the original `{"actions": [...]}` list with
  `data`) is converted on load: `data → settings`, `children: []`.
- Versioned file names follow the old convention (`name_v###.tr`);
  `increment()` writes the next version; `version: "latest"` on a reference
  resolves the highest `_v###` sibling at run time.

## 4. Actions

```python
@register_action("weights", category="deform", icon="weights")
class Weights(Action):
    label = "Weights"
    file = FileField("", extensions=[".trw"], help="Weights file")
    deformers = ListField(item_type=str)
    create_deformers = BoolField(True)

    def run(self, ctx): ...
    def save_from_scene(self, ctx) -> list[str]: ...   # optional: writes side files
```

- `Action` = typed fields + `run(ctx)`; optional `save_from_scene`,
  `validate(ctx) -> list[str]` (pre-flight problems shown in the UI),
  `info` docstring shown by the "?" button.
- New field: `FileField(default, extensions, mode="open"|"save"|"dir")` →
  browse button, relative-path storage, "open in Guide Designer" affordance
  when `extensions == [".trg"]`.
- `ActionContext`: `paths` (session file/dir, resolve helper), `events`,
  `session` (the running `Session`), `backend` (Maya), `depth`.
- Categories drive the shelf grouping and icon colour token:
  `structure` (reference, script), `build` (import_model, kinematics),
  `deform` (weights, morph, correctives), `finish` (shapes, look, sets,
  cleanup).
- Built-in `reference` action: settings `file`, `version`, `include`
  (`all` | list of paths), `overrides` (path → `{enabled?, settings?}`).
  At run time it loads the referenced document, applies overrides, checks
  for cycles (path stack) and runs the resulting tree as its own children
  with the referenced file's directory as path base. Scene reset happens
  only at the top-level build.
- `kinematics` action: `guides_file` (.trg), `guide_roots` (list; empty =
  all roots in the file), `auto_switchers`, `after_build`
  (keep/hide/delete), `selection_sets` (single/per-module). It imports the
  guides, builds modules root by root, attaches to the nearest socket of the
  parent limb (old behaviour, later refinable to declared plugs), runs the
  master setup (rig_grp / trigger_grp / pref_cont, global vis, global scale).

## 5. Build engine

`Runner.run(session, until=None, reset_scene=True, only=None)`:

1. `backend.new_scene()` when `reset_scene` (top level only).
2. Flatten the tree depth-first honoring `enabled`; resolve references.
3. For each action: emit `step_started(path)`, run inside an undo chunk,
   emit `step_finished(path, seconds)` or `step_failed(path, error)` and
   stop. `until=path` stops after that step; `only=path` runs a single step
   without reset.
4. The event bus is the only channel to the UI (status colours, progress,
   log, timings).

Errors carry the action path and the referenced file chain
(`hero_muscle.tr > baseRig.tr > scripts/head_rotation`).

## 6. Guides (`tik.trigger.guides`)

- `.trg` format = old Trigger joint list (name, position, rotation,
  joint_orient, scale, parent, side, type, color, radius, user_attributes).
  `GuideFile.load/save`, `roots()`.
- `Guides` handler (live scene): `add(module, side="L", name=None, parent=None,
  segments=None)`, `remove`, `mirror`, `select`, `roots()`, `instances()`,
  `test_build(roots=None)`, `export(path, roots=None)`, `import_(path,
  reset=False)`. Module properties are attributes on the root guide (typed
  fields declared by the module, written through `guides.attr`), so the Guide
  Designer property panel is a straight two-way binding.
- Module manifest stays declarative (`Guides(...)` roles, `plugs`,
  `sockets`, fields) with `draw_guides(ctx)` / `build(ctx)`; the build
  context regains old `ModuleCore` outputs: `limb_plug`, `sockets`, `anchors`,
  `scale_constraints`, `deformer_joints`, `controllers`, `post_connect()`.

## 7. TD API (`from tik import trigger`)

```python
rig = trigger.Session.open("hero_muscle.tr")      # or trigger.Session()
rig.add("import_model", file="hero_muscle_v02.ma")      # append at root
base = rig.add("reference", file="baseRig.tr")
base["scripts/head_rotation"].enabled = False            # override
base["kinematics"].guides_file = "hero_muscle.trg"       # override
rig.add("script", file="fix.py", parent=rig["import_model"])   # nest
rig.add("weights", file="hero_body.trw", after=base)
rig["weights"].deformers = ["skin_body"]
rig.move("weights", index=2); rig.remove("cleanup"); rig.duplicate("weights")
rig.build()                     # reset + run all
rig.build(until="weights"); rig.run("weights")
rig.save(); rig.save(increment=True); rig.increment()
rig.actions                     # tree of ActionHandle (name, type, enabled, path, settings, children)

guides = trigger.Guides()
body = guides.add("base", name="body")
arm = guides.add("arm", side="L", parent=body); arm.local_joints = True
guides.mirror(arm); guides.test_build(arm); guides.export("hero_muscle.trg")
```

`ActionHandle` exposes settings as attributes (validated by the fields),
`enabled`, `children`, `add/remove/move`, and for linked (referenced) handles
`is_linked`, `reset(field)`; setting an attribute on a linked handle writes an
override.

## 8. UI (`tik.trigger.ui`)

Theme: `tik.shared.ui.theme` = a copy of creature_kit `theme.qss`
(ground #242424, panels #353535, inputs #0f0f0f, text #c0c0c0, accent
#FE7E00, Roboto) plus tokens for status (done green, running amber, failed
red, linked blue-grey) and side colours (L blue, R red, C gold).

**Main window** (mockup 1): tabs = open `.tr` files; toolbar New/Open/Save/
Increment + "Guide Designer"; left = pipeline tree (icon, name, summary of
key setting, status stripe, collapse, checkbox only on linked rows); right =
settings of the selected action generated by `FormBuilder` + "?" info +
Run step / Run until here / Save from scene; bottom bar = Build rig, Build &
Publish (publisher hook), progress, step counter; log dock.

Interactions: collapsible icon **shelf** (click → after selection; drag → any
position, drop on a row → nest), **Tab** search palette (recent + categories;
Enter sibling, Shift+Enter child), drag & drop reorder/nest, right-click
Rename/Duplicate/Delete/Run/Run until/Toggle, double-click Run, F5 refresh.
Rows recolour live from runner events; failed step shows the error inline.

**Reference rows** (mockup 2): dimmed, chain glyph, checkbox; settings show
referenced values greyed; editing creates an override (accent border, reset);
"Open in tab".

**Guide Designer** (mockup 4): separate window; left module tiles (Tab
palette, segment count where the module has a multi role) + side control
(L/R/C/Both/Auto); middle scene guide tree with drag-parenting (reparents
Maya guides), Select/Mirror/Delete; right properties bound two-way to the root
guide attributes (`tik.shared.ui.binding`, ported from creature_kit); bottom
Import .trg / Export .trg / Test build. Selection syncs both ways.

## 9. Two-way binding (`tik.shared.ui.binding`)

Port of creature_kit `binding.py` onto `tik.maya` plugs: attribute observers
(scriptJob), typed binders (int/float/bool/string/choice), `BindingManager`
with reconnect polling. Plus `SceneObserver`: selection changed, DAG created/
deleted/reparented → tree refresh; guarded against feedback loops.

## 10. Testing

- `tests/unit`: document schema + old-format conversion; runner ordering,
  nesting, `until`, `only`, reference resolution, overrides, cycle detection
  (fake backend/actions); `Session` handler API; `.trg` load/save roundtrip
  against a real old file in `tests/data`.
- `tests/integration/trigger`: import_model → kinematics(.trg) → script →
  cleanup end to end; reference of a second session with an override; guides
  handler add/mirror/export/import.
- `tests/ui` (offscreen Qt, no Maya): pipeline model (tree, nesting, DnD
  moves), palette filtering, reference rows + override editing, Guide
  Designer tree/property panel with a fake scene.

## 11. Delivery order

1. Document + runner + reference + Session API (core, no UI).
2. Guides handler + `.trg` compatibility + kinematics action on it.
3. UI: theme, pipeline window, shelf + palette, reference rows.
4. Guide Designer + binding.
5. Remove the v1 scene-centric pieces (`RigSession` snapshot/restore, scene
   scope, old panels).

## 12. Open items (later specs)

Build & Publish / tik_manager; module feature parity (arm, leg, spine...);
remaining actions (weights, morph, correctives, shapes, look, sets...).
