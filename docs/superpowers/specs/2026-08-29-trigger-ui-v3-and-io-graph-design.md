# Trigger UI v3 and Module I/O Graph — Design Spec

Date: 2026-08-29
Status: brainstormed with Arda Kutlu; awaiting spec review.

> **Superseded in part (2026-08-30):** the UI file layout is now
> `ui/designer/` and `ui/graph/` per
> `docs/superpowers/specs/2026-08-30-trigger-simplification-design.md`.
> The module I/O model in section 3 still stands.

Builds on `2026-08-28-trigger-workflow-and-ui-design.md` (session = blueprint,
reference action, `.trg` asset, `Session`/`Guides` handlers). Replaces its
§7 attachment rule (nearest socket / DAG-derived) and §8 UI details.
Mockups: artifact "Trigger UI v3 Mockups" (2026-08-28) with the two
corrections below.

## 1. Goal

Two things the current build lacks: (a) UI craft on par with the approved
mockups and the creature_kit face_control designer — real tool windows with
menus and status bars, correct typography/margins, elegant rows, a shelf that
reflows; (b) an explicit module connection model — modules declare inputs and
outputs, connections are data in the guides file, tree and node-graph views
edit the same model, and a build-then-connect pass replaces "nearest socket".

Non-goals: module feature parity, Build & Publish, remaining actions.

## 2. Decisions (from brainstorming, 2026-08-28/29)

- Windows: Trigger and Guide Designer are **dockable workspace tool windows**
  (MayaQWidgetDockableMixin) with menu bars and status bars; one instance each.
- Shelf = a **splitter pane** holding a reflowing tile grid (1…n columns by
  width); no custom collapse widget — drag the handle to hide.
- Rows: the earlier mockup's treatment (category icon, left stripe colours,
  linked rows dimmed + dashed stripe + chain glyph, checkboxes only on linked
  rows) **plus a status dot in the gutter**; selection = muted tint + 2px
  accent bar, never the solid orange fill.
- Versioning: **Nuke-style** on every versioned file field — green = latest,
  amber = older (tooltip/badge shows latest), **Alt+↑ / Alt+↓** while hovering
  steps versions. No explicit `version` setting anywhere; a path means that
  path. The session title/tab and the status bar use the same colours.
- Attachment: **explicit inputs/outputs**; connections stored in the `.trg`;
  source = `module.output` or any scene node name; build all, then connect;
  missing source → error naming the input. DAG parenting of guides is layout
  only, but parenting a new guide under another module's guide pre-fills the
  primary input.
- Guide Designer shows **Tree and Graph side by side** (collapsible panes in
  the splitter); both edit the same connections. Properties show an
  **Inputs** group first; that is sufficient for wiring in tree mode.

## 3. Module I/O model

```python
@register_module("arm")
class Arm(Module):
    guides = Guides("collar", "shoulder", "elbow", "hand")
    inputs = (
        Input("root", kind="transform", primary=True, help="Where the arm hangs"),
        Input("space", kind="transform", optional=True),
    )
    outputs = ("collar", "shoulder", "elbow", "hand")   # names of built nodes
    ...
    def build(self, ctx):
        ...
        ctx.output("collar", collar_jnt); ctx.output("hand", hand_jnt)
        ctx.attach("root", socket_group)      # node driven by the 'root' input
```

- `Input(name, kind="transform", primary=False, optional=False, help="")`.
  Exactly one primary input per module (the first, if none flagged); it is
  what the Tree view shows as parenting. `kind` ∈ transform | joint |
  attribute (attribute inputs deferred; declared for the graph's validation).
- `outputs`: tuple of names; every built module must register each one via
  `ctx.output(name, node)` or the build fails ("module 'arm' did not produce
  output 'hand'").
- `ctx.attach(input_name, node)`: the node the framework will drive from the
  connected source (matrix constraint, maintain offset). One node per input.
- Legacy roles: the guide joint an instance is parented under maps to an
  output by role name when the module lists that role as an output; otherwise
  the module's first output. Used only to derive connections for old files.

### Connections in the guides file

```json
"connections": [
  {"input": "L_arm.root", "source": "body.root"},
  {"input": "tail.space", "source": "some_jnt"}
]
```

- The `.trg` stays a JSON list of joint records for compatibility; the new
  format wraps it: `{"joints": [...], "connections": [...], "meta": {...}}`.
  Loader accepts both; saver writes the wrapped form.
- `input` = `<instance name>.<input name>`; instance names unique per side
  (`L_arm`, `R_arm`, `body`). `source` = `<instance>.<output>` or a scene node
  name (anything containing no `.`, or not matching an instance).
- Scene storage: connections live as meta on the root guide
  (`trg_inputs`: `{input: source}`) so the live scene round-trips.

### Builder

1. Build every instance (order irrelevant except for determinism: by name).
2. Connect pass: for each instance input with a source: resolve module output
   node or scene node; missing → `AttachError("L_arm.root: source 'body.root'
   was not built" / "'some_jnt' does not exist")`. Required inputs without a
   source → error; optional → skipped.
3. Afterlife.

## 4. UI kit (`tik.shared.ui`)

- `MayaToolWindow(MayaQWidgetDockableMixin, QMainWindow)`: dockable, single
  instance by object name, scriptJob registry killed on close, `apply_theme()`
  called after the tree is built; headless-safe (no Maya → plain QMainWindow).
- `SceneWatcher`: scriptJob events → one debounced refresh (`QTimer.singleShot(0)`)
  with a re-entrancy guard; `mute()` context for self-caused changes.
- `VersionedFileField`: line edit + browse; parses `_v###`; colours border/badge
  green (latest) / amber (older) / neutral (unversioned); Alt+↑/↓ on hover
  steps to existing versions; emits `changed`. Used by `FormBuilder` for
  `FileField`.
- `TileGrid`: flow layout of tiles by category with headers; reflows to the
  pane width; click and drag-out.
- `CollapsibleGroup` (copied), status bar helpers (`StatusBar.set_activity`,
  separators), `theme.py` = house `theme.qss` + tool additions (status bar,
  tiles, list, badges).

## 5. Trigger window

Menus: File (New, Open…, Recent, Save, Save As…, Increment, Import Actions…,
Export Actions…, Close Tab, Quit) · Edit (Undo, Redo, Add Action… Tab, Add
Child Action…, Duplicate, Rename, Delete, Enable/Disable) · Session (Build,
Build Until Here, Run Step, Validate, Clear Statuses) · Tools (Guide
Designer, Settings…) · Help (Documentation, About).
Body: splitter [shelf pane | pipeline | properties] with stretch 0/1/1,
handle width 8, children not collapsible except the shelf. Status bar:
activity · references resolved · Maya version · tik.trigger version.
Undo/Redo: session-level command stack (add/remove/move/rename/settings).

Rows and properties as decided in §2; properties grouped by `Field.group`
with section captions; header with icon/name/type and "?".

## 6. Guide Designer window

Menus: File (New scene guides, Import .trg…, Export .trg…, Export selected…)
· Edit (Mirror, Delete, Rename, Connect input…, Disconnect) · View (Tree,
Graph, Both, Refresh F5) · Build (Test build selected, Test build all) ·
Help.
Body: [side + module tiles | Tree pane | Graph pane | properties]; Tree and
Graph are collapsible panes; selection is shared. Graph: QGraphicsView with
module nodes (input ports left, output ports right, primary port marked),
external dashed nodes for scene sources, wires (primary orange, secondary
blue), drag to connect, drop on empty = "scene node…" prompt, Delete on wire.
Tree: drag-parent writes the primary input; creating guides with a selected
guide joint pre-fills the primary input from that joint's role.
Properties: Inputs group (one row per input: source picker with "from
selection" and clear), Guides group (name, inherit orientation, axes), then
module fields. Status bar: modules · connections · external checks · file.
Scene sync: `SceneWatcher` (debounced), tree/graph → scene selection muted.

## 7. Testing

- Unit: `Input`/outputs manifest, connection resolution and errors, legacy
  derivation, `.trg` wrapped/list formats, versioning field logic (pure).
- Maya: build-then-connect with scene-node sources; reparent/pre-fill; export
  round trip with connections.
- UI (offscreen): window menus/status, tile grid reflow, versioned field
  colours + Alt stepping, tree ⇄ graph edits, graph wiring to external node.

## 8. Delivery order

1. UI kit + Trigger window rebuild (menus, status, shelf pane, rows, fields).
2. I/O model + connections in `.trg` + builder connect pass + legacy derivation.
3. Guide Designer rebuild: tree + graph + inputs properties + scene watcher.
4. Handler API additions (`guides.connect("L_arm.root", "body.root")`,
   `handle.inputs`), docs, screenshots.
