# Icon Rules — TikWorks

## Overview
Every action and guide module in `tik.trigger` ships a hand-drawn SVG icon
beside its `.py` file. This file is the authority for drawing one — human or
agent — so a new plugin's first-pass icon looks like it belongs next to the
nine that already ship. The reasoning behind each rule lives in
`docs/superpowers/specs/2026-09-04-icon-system-design.md`; this file states
the rules themselves.

Resolution and tinting are implemented in
`src/python/tik/trigger/core/icons.py` (pure path lookup) and
`src/python/tik/trigger/ui/iconography.py` (family rules, fallbacks, tinting).
The Qt-subset lint that enforces the rules below lives in
`tests/unit/test_icon_assets.py`.

---

## The two families

An action is a **verb**: it does something to the scene, and it is drawn full
colour, pictorial, and is **never tinted** — `ui/delegates.py` already paints
run state as a separate status dot plus a category stripe, so nothing rides on
the action icon's own colour and it is free to keep it.

A guide module is a **noun**: it names a piece of the rig, and it is drawn
monochrome and diagrammatic, then **tinted at runtime** — by `theme.SIDE`
(`{"L": "#5b8fd0", "R": "#d06a66", "C": "#d4b04a"}`) when it is drawn for a
placed instance that has a side (`L_arm` renders blue, `R_arm` red, `C_base`
amber), or by `MODULE_COLORS` when it is drawn for a shelf or palette entry,
which is a module *type* with no instance and therefore no side. `MODULE_COLORS`
lives in `src/python/tik/shared/ui/theme/__init__.py` beside `SIDE` and
`CATEGORY`, keyed by the four real module categories — `body`, `limbs`,
`generic`, `face` — plus `scene`, the scene-nodes pseudo-module, which is not
a category a real module should register under. (`ui/designer/widgets.py`
re-exports `MODULE_COLORS` from `theme` for callers that already imported it
from there; `theme` is the source, import from it in new code.) A module
`.png` is the one exception: it is never tinted, because a PNG is an artist's
finished work and finished work is left alone.

(`theme.CATEGORY` is the *action* category palette — `structure`, `build`,
`deform`, `finish`, `utility` — used for an action's generated fallback chip
and its pipeline-tree category stripe. Do not confuse it with `MODULE_COLORS`:
a module's category is never one of `theme.CATEGORY`'s keys.)

This split is structural, not just a hue choice, so it survives retinting: a
heavier full-colour stroke for actions, a thin uniform stroke for modules.

---

## Canvas

Every icon — both families — uses `viewBox="0 0 24 24"` with matching
`width="24" height="24"`. One shared grid is what keeps an action's visual
weight comparable to a module's when they sit side by side in the palette or
the pipeline tree.

---

## Action rules

- **Full colour.** Depth comes from tonal steps between an object's faces
  (see `import_asset.svg`'s three crate faces at `#a3c169` / `#82a04c` /
  `#6d8940`), not from a single flat fill.
- **The rim is a pale tint of the icon's own hue, never black.** The original
  23-icon set used near-black outlines, drawn for a light UI; on the
  `#242424` dark ground a near-black rim stops separating the shape from the
  background and starts consuming it. Every shipped action icon's rim is a
  pale version of its own palette — `kinematics`'s bone rim is `#f2ead6`
  against a `#e3cf9f` fill, `reference`'s rim is `#dff4fa` against `#a6e2ef`.
- **Draw the rim as an underlay, not an outline on each shape.** One `<g>`
  with `fill` and `stroke` both set to the rim colour and
  `stroke-width="2.3"`, holding every shape in the icon; then a second `<g>`
  with `stroke="none"` repeating the same `<path>`/`<circle>` shapes filled
  with their real colours, on top. Because the rim group is a single
  underlay rather than a per-shape stroke, adjoining shapes get one clean
  outer silhouette with no visible seam where they overlap — see
  `kinematics.svg`'s four overlapping lobes, which read as one bone, not
  four separately outlined circles.
- **It must hold at 16px.** The pipeline tree renders at 16px; a shape that
  needs 24px of detail to read is wrong for this set.

## Module rules

- **One flat colour**, `stroke-width="1.35"`, no rim, no fill on the bones
  themselves.
- **The bone-and-joint grammar:** thin bones (`<path>` strokes) connecting
  **filled joint dots** (`<circle>` with `fill` set to the same colour and
  `stroke="none"`). Every shipped module icon follows this exactly — see
  `arm.svg` or `fkchain.svg` below.
- **The glyph must depict the module's actual hierarchy.** Draw the real
  joint count and arrangement declared in the module's `GuideLayout`, not a
  generic placeholder:
  - `fkchain.svg` is a **four-joint arc** — `fkchain.py` declares
    `GuideLayout("root", multi="segment", min=1, max=50)`, and the icon shows
    four dots strung diagonally to suggest an open-ended chain.
  - `arm.svg` is a **three-joint bend** (shoulder, elbow, hand) — `arm.py`
    declares five guides (`collar`, `shoulder`, `elbow`, `hand`, `neutral`),
    but the icon draws the three that read as "an arm" at a glance; `collar`
    and the `neutral` reference point are rigging plumbing, not the shape a
    rigger recognises.
  - `base.svg` is a ring with axis ticks and a filled centre — the root's
    "this is the world origin" shape, not a bone at all.
  - `twist.svg` is counter-rotating arrows about an axis; `ribbon.svg` is a
    wavy band with a centre point. Both describe *behaviour* along a chain
    rather than a joint count, because that is what best distinguishes them
    from `fkchain` at a glance.

  A module icon that does not describe its topology — two arbitrary dots and
  a line, standing in for any module — is wrong. If the module's shape does
  not compress to a legible glyph, draw the closest true diagram and say so
  in review; do not fall back to a generic mark.

---

## The Qt SVG Tiny 1.2 subset

Maya's Qt renders SVG through the Tiny 1.2 profile. These are **silently
ignored** — not an error, not a warning, just absent — so a file using them
looks correct in a browser and renders wrong or blank in Maya:

- `<filter>`
- `<mask>`
- `<text>`
- `<foreignObject>`
- `<use>`
- `currentColor`
- `@import`

Files must be self-contained: no external references, no `<use>` reuse of a
`<defs>` block, no `currentColor` — because tinting is never done by CSS
colour inheritance in the SVG itself, it is done afterward by recolouring the
*rendered pixmap* (`QPainter.CompositionMode_SourceIn` in
`tik/shared/ui/pick.py`). A module SVG is drawn once in its base colour;
`pick.tinted_icon()` swaps that colour per side or category. `currentColor`
is therefore never needed and must not be reached for out of habit.

`tests/unit/test_icon_assets.py` enforces the forbidden-element list (and the
`viewBox="0 0 24 24"` grid) against every shipped action and module icon as
part of the plain unit suite — no Qt required to run it. Do not relax or
"clean up" this list; it exists because the failure mode it catches is
invisible until someone opens Maya.

---

## Placement and precedence

An icon lives beside the `.py` it belongs to, named after the icon:
`<plugin folder>/<name>.svg` — e.g. `src/python/tik/trigger/actions/kinematics/kinematics.svg`,
`src/python/tik/trigger/modules/arm/arm.svg`. The name is `cls.icon` if the
`@register_action`/`@register_module` decorator set one, otherwise the
registered type name; dropping in a correctly-named file is the entire
integration — no registration and no code change.

**A `.png` of the same name wins over the `.svg`.** Resolution tries
`<name>.png` first, then `<name>.svg`, then a generated fallback
(`core/icons.py:SUFFIXES`). A PNG is an artist's finished work superseding
the authored-placeholder SVG that sits next to it; the SVG stays in the repo
as the source of record, so restoring it is moving one file.

Deliver PNGs at **64px minimum**. The settings header renders an icon at 26px
and, unlike the SVG path, there is no vector to fall back on if the raster is
too small — it will visibly upscale.

---

## Two copy-paste templates

Lifted verbatim from the repo. Copy one of these, keep the two-group
(rim-underlay / fill-on-top) or bone-and-joint structure, and change the
`path`/`circle` geometry and colours for the new icon.

### Action template — `src/python/tik/trigger/actions/reference/reference.svg`

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24"><g fill="#dff4fa" stroke="#dff4fa" stroke-width="2.3" stroke-linejoin="round" stroke-linecap="round"><path d="M12 2.7 L20.5 7.3 L12 11.9 L3.5 7.3 Z"/><path d="M3.5 7.3 L12 11.9 V21.2 L3.5 16.6 Z"/><path d="M20.5 7.3 V16.6 L12 21.2 V11.9 Z"/></g><g stroke="none"><path d="M12 2.7 L20.5 7.3 L12 11.9 L3.5 7.3 Z" fill="#a6e2ef"/><path d="M3.5 7.3 L12 11.9 V21.2 L3.5 16.6 Z" fill="#7cc9dd"/><path d="M20.5 7.3 V16.6 L12 21.2 V11.9 Z" fill="#5cadc6"/></g><g stroke="#2f7f96" stroke-width="1.1" fill="none" stroke-dasharray="2.4 2.1" stroke-linecap="round"><path d="M3.5 7.3 L12 11.9 L20.5 7.3"/><path d="M12 11.9 V21.2"/></g></svg>
```

Notice the three `<g>` groups in order: the rim underlay (`stroke-width="2.3"`,
rim colour `#dff4fa` for both fill and stroke), the real fills on top
(`stroke="none"`, one colour per cube face), and — specific to this icon, not
a required part of every action — a third group of dashed inner edges that
echoes the dashed stripe `ui/delegates.py` paints for linked rows.

### Module template — `src/python/tik/trigger/modules/arm/arm.svg`

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24"><g fill="none" stroke="#93a8c4" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round"><path d="M5.6 5.4 L15.6 11.6 L7.6 19"/><g fill="#93a8c4" stroke="none"><circle cx="5.6" cy="5.4" r="1.9"/><circle cx="15.6" cy="11.6" r="1.9"/><circle cx="7.6" cy="19" r="1.9"/></g></g></svg>
```

One flat colour (`#93a8c4` — the module's own base colour is irrelevant,
since `module_icon()` recolours it at render time), a single `<path>` for the
bones, and a nested `<g>` of filled `<circle>` joints. The colour used in the
authored file does not matter for a tinted module; use anything legible while
drawing, since it will be swapped.

---

## The obligation

**A new action or module folder ships a first-pass `<name>.svg` beside its
`.py`.** This is not optional and not a follow-up task: `test_icon_assets.py`
fails the whole suite for any registered action or module with no icon file,
so a plugin without one does not merge. A rough first pass that follows the
family's grammar (rim-underlay for an action, bone-and-joint for a module) is
enough to ship; refining it later is fine, shipping with no icon is not.

---

## Related Files
- `docs/superpowers/specs/2026-09-04-icon-system-design.md` — the design this
  file implements, with the reasoning behind each rule
- `AI/coding_rules.md` — the tik.trigger authoring rules this file extends
- `AI/developer_commands.md` — the New Action / New Module checklists that
  point here
- `src/python/tik/trigger/core/icons.py` — resolution order (`IconFile`,
  `find()`, `SUFFIXES`)
- `src/python/tik/trigger/ui/iconography.py` — family rules, tinting,
  `topology_icon()` fallback
- `tests/unit/test_icon_assets.py` — the Qt-subset and grid lint
