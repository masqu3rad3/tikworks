# Icons for actions and guide modules

**Date:** 2026-09-04
**Status:** Design approved, ready for an implementation plan
**Area:** `tik.trigger` — registry, plugin folders, pipeline and Guide Designer UI; `tik.shared.ui`

## 1. The problem

Every action and module in the current UI is drawn as a coloured rounded square
with one or two letters in it (`tik/shared/ui/icons.py`). It is honest and it
never fails, but it carries almost no information: `Kinematics` and `Ribbon` are
two chips that differ only in a letter pair, and a shelf of them reads as a wall
of colour swatches. The previous Trigger had 23 hand-drawn PNGs in a single
folder (`trigger/ui/icons/`) which were far more legible, and a rigger could find
an action by shape before reading its label.

Three things need fixing at once:

- **Actions have no artwork.** `@register_action` already stamps `cls.icon`
  (`registry.py:67`) and nothing has ever read it. The hook exists; the resolver
  and the assets do not.
- **Guide modules have no icon concept at all.** `@register_module` takes only a
  name. The Guide Designer colours module tiles from a hardcoded
  `MODULE_CATEGORY` dict in `ui/designer/widgets.py:18-19`, six of whose nine
  entries name modules that do not exist.
- **A single icons folder does not fit the plugin layout.** Everything else
  about an action or module lives in `<package>/<name>/`; its picture should too,
  so that adding a plugin stays a one-folder operation.

## 2. Decisions

Eight decisions were settled during design. The rest of this document follows
from them.

1. **Icons are authored SVG, hand-drawn, one file per plugin folder.** Not
   scripted from the plugin name: a script can only emit geometric abstraction,
   so it would hand a future artist nothing to build on. Hand-authored art
   carries the metaphor, the grid and the optical weight across the handoff.
2. **PNG wins over SVG.** The lookup order is `<name>.png`, then `<name>.svg`,
   then the generated fallback. A PNG is an artist's finished work; the SVG is
   the placeholder it supersedes. The SVG stays in the repo as the source of
   record, and the swap is reversible by moving one file.
3. **Actions are full colour and are never tinted.** This is possible because
   `ui/delegates.py:61-66` already paints run state as a status dot with a
   running halo, plus a category stripe. No pipeline information was ever riding
   on the action icon, so nothing is lost by letting it carry its own palette.
4. **Guide modules are monochrome and are tinted at runtime**, by side
   (`theme.SIDE`) or category. One `arm.svg` renders blue for `L_arm`, red for
   `R_arm`, amber for `C_base`. The one exception is a module PNG, which is
   finished art and is left alone (§4).
5. **That difference is the tonal split**, and it lives in the geometry as well
   as the hue: actions are pictorial with a heavier stroke; modules are
   diagrammatic, thinner, and built from a shared bone-and-joint grammar.
   Because the split is structural it survives retinting, which a hue-only split
   would not.
6. **The four existing PNGs are converted, not replaced.** `kinematics` (bone),
   `import_asset` (crate and arrow), `script` (paper, lines, pen) and
   `reference_session` → `reference` (cube) keep their metaphors. The remaining
   19 old icons stay where they are and are converted when the matching actions
   exist.
7. **The rim is a pale tint of each icon's own hue, never black.** The old art
   was drawn with near-black outlines for a light UI; on the `#242424` ground
   that outline stops separating the shape and starts consuming it.
8. **The drawing rules are repo documentation, not spec prose.** They live in
   `AI/icon_rules.md` and oblige every new action or module folder to ship a
   first-pass SVG.

### Verified, not assumed

Every rendering assumption was measured in the live Maya session
(**Maya 2027, PySide6, Python 3.13.9**) rather than reasoned about:

| Claim | Evidence |
|---|---|
| Qt can load SVG | `QtSvg` imports; `QImageReader` lists `svg`, `svgz` |
| One file serves every size | a 288-byte file renders exactly at 16/18/22/24/26/64px |
| Colour art survives Qt's SVG Tiny 1.2 renderer | a 324-byte light-rim icon yields **58 distinct colours** at 64px — fills and rim intact, not flattened to a silhouette |
| Tinting is exact | `CompositionMode_SourceIn` returns `#5b8fd0`, `#d06a66`, `#d4b04a` verbatim |
| Assets reach Maya | `package/package.py:226` copies the whole `tik` tree with `shutil.copytree` |

`Qt5`/PySide2 (Maya 2024) was **not** verified. Qt5 ships the same SVG image
plugin, so the risk is low, and the generated fallback degrades gracefully if it
is ever wrong.

## 3. Where the code lives

Three modules, split along the existing layering rule — `tik/trigger/core` is
pure Python, no Maya and no Qt, enforced by `tests/unit/test_import_boundaries.py`.

| Module | Layer | Responsibility |
|---|---|---|
| `tik/trigger/core/icons.py` | pure | Given a registered class, locate its icon *file*. Returns a path and family, or `None`. |
| `tik/shared/ui/pick.py` | Qt, generic | Turn paths into `QIcon`/`QPixmap`; recolour; cache; expose the theme file. Knows nothing of actions or modules. |
| `tik/trigger/ui/iconography.py` | Qt, trigger | Family rules and fallbacks: `action_icon(cls)`, `module_icon(cls, side)`. |

Path resolution sits in `core` beside `discovery.py` because it is the same
"a plugin is `<folder>/<folder>.py`" knowledge. Resolving that twice is how the
two drift apart. It also makes resolution testable with no Qt at all.

`tik/shared/ui/icons.py` is unchanged. It stops being the only tier and becomes
the fallback tier.

### `pick.py`

Modelled on `creature_kit/shared/pick.py`, generalised because tikworks icons are
not in one folder:

```python
def icon(path) -> QtGui.QIcon
def pixmap(path, size=None) -> QtGui.QPixmap
def tinted_icon(path, colour, size) -> QtGui.QIcon   # SourceIn recolour, cached
def style_file(name="theme.qss") -> QtCore.QFile     # registers css:/rc: search paths
```

`tik/shared/ui/theme/__init__.py` remains the owner of the colour tokens and
`stylesheet()`; `pick` delegates to it rather than duplicating it. Being plain
about the value split: the icon half of `pick` is what this design needs, and
the theme half is a convenience door onto a room that already has one.

## 4. Resolution and tinting

```
<plugin folder>/<icon name>.png     artist's finished art — wins
<plugin folder>/<icon name>.svg     authored placeholder
generated fallback                  nothing on disk
```

The icon name is `cls.icon` if set, else the registered type, so
`actions/kinematics/kinematics.svg` sits beside `kinematics.py`. Adding an icon
is dropping in a file; no registration and no code change.

Tinting is decided by family and format. There is no per-file flag to forget to
set:

| Family | Source | Tinted |
|---|---|---|
| action | any | never — it carries its own colour |
| module | `.svg` or generated | yes — see below |
| module | `.png` | never — a PNG is someone's finished art |

A tinted module takes its colour from `theme.SIDE` when it is drawn for a placed
instance that has a side — a tree row or a properties header in the Guide
Designer. Shelf and palette entries are module *types* with no instance and so
no side; those take `theme.CATEGORY` from the class. The caller decides by
which of `module_icon(cls, side=...)` it has a side to pass.

## 5. Fallbacks

- **Action with no file** — today's coloured-initials chip from
  `shared/ui/icons.py`, tinted by `theme.CATEGORY`. Unchanged behaviour.
- **Module with no file** — a topology sketch derived from the module's declared
  `GuideLayout`: its real joint count and arrangement rather than two letters.
  `spine` becomes four stacked joints, `finger` four in a chain.

The module fallback is deliberately limited: `arm` and `leg` would look alike,
so it improves the gap before someone draws the real icon and never substitutes
for authored art.

## 6. The asset set

Nine files, all 24×24 viewBox.

**Actions** — full colour, light rim, in `tik/trigger/actions/<name>/<name>.svg`:

| File | Metaphor (from the old PNG) | Palette |
|---|---|---|
| `kinematics.svg` | bone, four lobes and a shaft | bone `#e3cf9f`, rim `#f2ead6` |
| `import_asset.svg` | blue arrow descending into a green crate | crate `#a3c169`/`#82a04c`/`#6d8940`, arrow `#4d9fd6`, rim `#e8f0dc` |
| `script.svg` | paper with text lines, blue pen | paper `#f0e1b4`, fold `#d3c08a`, pen `#4d9fd6`, rim `#f7efd8` |
| `reference.svg` | cube, inner edges dashed | `#a6e2ef`/`#7cc9dd`/`#5cadc6`, rim `#dff4fa` |

`import_asset` merges the original's two objects into one — the arrow enters the
crate rather than sitting in a separate badge — because the badge collapses to a
blob at the 16px the pipeline tree uses. Both of the original's colour elements
are kept. `reference`'s dashed inner edges echo the dashed stripe
`delegates.py:72` already paints for linked rows.

**Modules** — monochrome, in `tik/trigger/modules/<name>/<name>.svg`:

| File | Topology drawn |
|---|---|
| `base.svg` | root: ring, axis ticks, filled centre |
| `fkchain.svg` | four joints in an arc |
| `arm.svg` | three-joint bend (shoulder, elbow, wrist) |
| `twist.svg` | counter-rotating arrows about an axis |
| `ribbon.svg` | wavy band with a centre point |

## 7. Drawing rules — `AI/icon_rules.md`

A new topic file in `AI/`, alongside `coding_rules.md`, `testing_rules.md` and
`documentation_rules.md`. It is the authority for anyone — human or agent —
drawing a tikworks icon, and it carries:

- The two families and why they differ.
- **Actions:** 24×24; full colour; rim is a pale tint of that icon's own hue at
  ~1.15 stroke, never black; depth by tonal steps between faces; must hold at
  16px.
- **Modules:** 24×24; one flat colour; 1.35 stroke; the bone-and-joint grammar
  of thin bones and filled joint dots. **The glyph must depict the module's
  actual hierarchy** — the joint count and arrangement of its `GuideLayout`. A
  module icon that does not describe its topology is wrong.
- **The Qt SVG Tiny 1.2 subset**, with reasons attached so the rules are not
  "improved" away later: no `<filter>`, `<mask>`, `<text>`, `<foreignObject>`,
  `<use>`, `currentColor` or `@import`; self-contained files only. Tinting is
  done by pixmap composition, so `currentColor` — which Qt handles poorly — is
  never needed.
- Placement, naming and the PNG-wins rule; PNGs delivered at 64px minimum, since
  the settings header asks for 26 and there is no vector to fall back on.
- A copy-paste template per family, with the real palettes.
- **The obligation:** *a new action or module folder ships a first-pass
  `<name>.svg` beside its `.py`.* Not optional, not a follow-up.

Pointers are added so the file is reachable from where someone is already
working — a rule nobody navigates to is a rule that does not exist:
`AI/coding_rules.md` (subsection plus Related Files), `AI/developer_commands.md`
(both authoring checklists), `AGENTS.md` (Related Files), `CLAUDE.md` (the
tik.trigger section).

### Correcting the authoring checklists

`AI/developer_commands.md:129-143` is stale. The two checklists an agent would
follow to add an action or module tell it to inherit from `ActionCore`,
`GuidesCore` and `ModuleCore` and to write `data.json` and `ui_definition.json`.
None of those exist; the current names are `Action`, `Module` and
`defaults.json`. Adding an icon step to a checklist that is already wrong would
leave an agent following it still producing something broken, so both checklists
are corrected here. This is pre-existing drift, in scope only because it is the
exact document this feature depends on.

## 8. Registry and call-site changes

`@register_module` gains the parameters `@register_action` already has:

```python
def register_module(name: str, category: str = "generic", icon: str = "") -> ...:
    cls.module_type = name
    cls.category = category
    cls.icon = icon or name
```

The hardcoded `MODULE_CATEGORY` dict in `ui/designer/widgets.py:18-19` is
deleted; `module_entries()` reads `cls.category` instead. Modules declare their
own category the way actions do.

`import_asset.py:11` declares `icon="import_model"` and no such asset has ever
existed. The argument is dropped so the name defaults to `import_asset`.

Six call sites swap `glyph_icon(initials(...), colour)` for an `iconography`
call: `ui/palette.py:105`, `ui/shelf.py:20`, `shared/ui/tile_grid.py:32`,
`ui/delegates.py:87`, `ui/settings_panel.py:106`, and
`ui/designer/window.py:418,553,669`.

`shelf.py` and `tile_grid.py` are near-duplicate tile builders. That is noted
and deliberately left alone; folding them together is not this change.

## 9. Tests

**Unit, no Qt** (`tests/unit/test_icons_trigger.py`):

- resolution order, including PNG winning over a sibling SVG
- missing file returns `None`
- the `cls.icon` name overriding the registered type

**UI, offscreen** (`tests/ui/test_iconography.py`, `TIK_TESTS_NO_MAYA=1`,
`QT_QPA_PLATFORM=offscreen`):

- every registered action and module resolves to a real file
- each renders a non-empty pixmap at 16px
- a module tint returns the requested colour exactly
- a PNG is never tinted

**Asset lint:** authored SVGs contain none of `<filter>`, `<mask>`,
`<foreignObject>`, `<text>` or `@import`. A cheap guard against someone pasting
an Illustrator export that renders blank in Maya while looking fine in a browser.

## 10. Packaging

`pyproject.toml` declares no `package-data`, so `pip install .` would silently
drop every `.svg` and `.png`. Two lines fix it:

```toml
[tool.setuptools.package-data]
"*" = ["*.svg", "*.png", "*.qss", "*.json"]
```

The Maya deploy path needs nothing: `package/package.py:226` copies the whole
tree.

## 11. What this design does not do

- It does not convert the other 19 old PNGs. They are converted when the
  matching actions exist.
- It does not give actions a per-action colour override in the registry. Colour
  lives in the artwork.
- It does not merge `shelf.py` and `tile_grid.py`.
- It does not add a light theme. Actions carry fixed colour, so a future light
  theme would need its own decision about them; modules, being tinted, would
  follow automatically.
