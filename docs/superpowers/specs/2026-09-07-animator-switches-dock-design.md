# The Animator Switches Dock

**Date:** 2026-09-07
**Status:** Approved design, ready for planning
**Builds on:** `2026-09-07-movable-pivots-and-pivot-presets-design.md` (the pivot
presets this tool drives, and Part 6's switch tool, which this replaces)
**Design canvas:** the tool, its selection states, the shell anatomy and the
docked/floating context — https://claude.ai/code/artifact/55db7554-0541-4297-816b-38a7778a582e

## Purpose

`Tools > Switch Pivot (Preserve)…` works, and it is the wrong shape. It is a
modal dialog: it takes the viewport away to ask one question, answers it, and
closes. An animator switching a hand's pivot does it dozens of times in a
blocking pass, between selections, while scrubbing.

This design replaces it with a **dockable, non-modal mini tool** that follows
the selection, and makes it the shell for the switches that come after it —
FK/IK, the pole-pin freeze, and whatever else fits the rule below.

## The organising rule

> **A switch changes what a control *does*, and the pose survives it.**

Which point it turns about, which chain drives it, whether the elbow is held.
Every one is a match-and-switch: something is measured, something changes,
and something the animator authored is put back.

That rule is what makes one tool out of three rather than three tools sharing a
window, and it is the test a fourth tab has to pass. A tab that cannot name what
it promises not to disturb is not a switch and does not belong here.

## Scope

In scope: the `tik/trigger/anim` package and its import boundary, the switch
registry and tab contract, the dock shell, the pivot switch including switching
across a frame range, declared placeholders for FK/IK and the pole pin, the
launcher, and removing the modal menu item.

Out of scope: what the FK/IK and pole-pin switches actually do — they register,
declare themselves unavailable and say so. Animation layers, a picker, and
anything that moves a rig rather than switching it.

---

## Part 1 — Where it lives

```
tik/trigger/anim/
  __init__.py              show(dockable=True)
  registry.py              @register_switch, get_switch, iter_switches
  context.py               SwitchContext — the selection, as plain data
  switch.py                Switch — the tab contract
  window.py                SwitchesWindow — the shell
  switches/
    __init__.py            imports the three, so registration happens
    pivot/pivot.py         + pivot.svg
    ikfk/ikfk.py           + ikfk.svg        (declared placeholder)
    polepin/polepin.py     + polepin.svg     (declared placeholder)
```

### 1.1 An animator tool reads the rig, never the session

`tik/trigger/ui` is the rigger's application: it owns a `Session`, a
`GuideDocument`, guides and a pipeline. None of that exists at animation time —
the animator has a built rig in a scene and nothing else. So:

`trigger/anim` may import `tik.maya`, `tik.shared`, `tik.trigger.maya.tags` and
`tik.trigger.maya.pivot`. It may **not** import `trigger.session`,
`trigger.core.document`, `trigger.core.guide_document`, `trigger.guides` or
`trigger.ui`.

`tests/unit/test_import_boundaries.py` enforces it, beside the rule that keeps
preferences out of the build path.

This costs nothing, because everything a switch needs is already on the built
nodes — the `pivotPreset` enum, the `trg_*` tags — and it buys a guarantee worth
having: the rigger's app and the animator's tools cannot entangle, whatever
either grows into.

### 1.2 Operations stay in `trigger/maya`

`tik/trigger/maya/pivot.py` keeps the pivot operation: headless, no Qt, run
under `mayapy` in tests, callable from a shelf button without opening a window.
The tab is a thin UI over it. Every switch that follows does the same — the
scene work is a plain function, the tab is how an animator reaches it.

---

## Part 2 — The tab contract

```python
class Switch:
    """One tab: a named set of states you pick between, with the pose held."""

    label: str = ""            #: tab text
    help: str = ""             #: one line under the picker
    order: int = 100           #: tab order, low first
    available: bool = True     #: False -> a declared placeholder

    switch_type: str = ""      #: stamped by @register_switch
    icon: str = ""             #: stamped by @register_switch

    def states(self, context: SwitchContext) -> list[str]:
        """The states offered for this selection. Empty: nothing to offer."""

    def current(self, context: SwitchContext) -> Optional[str]:
        """The state the selection is in; None when the selection disagrees."""

    def apply(self, context, state, *, key: bool, times) -> str:
        """Do it; return one line for the status bar."""
```

`@register_switch("pivot")` stamps `switch_type` and finds the icon, exactly as
`@register_action` and `@register_module` do. Folder per switch, a same-named
`.svg` beside the `.py`, per `AI/icon_rules.md`.

### 2.1 `states()` is what lights a tab

A tab whose `states()` is empty for the current selection shows an unlit dot and
a body explaining what it wants instead — "no control with a movable pivot is
selected". It stays clickable: a tab that vanishes makes the tool's shape change
under the animator's hands, and a dark tab can say why it has nothing.

### 2.2 A placeholder is a declared absence, not an empty picker

`available = False` is how `ikfk` and `polepin` ship. The shell renders their
`help` under a "not built yet" line rather than an empty state picker, so
nothing about them reads as broken or as pretending to work. They exist to prove
the registry and the shell, and to reserve the tab order.

### 2.3 The shell never touches Maya

Only `states`, `current` and `apply` do. `SwitchContext` is plain data, built
once per selection change:

```python
@dataclass(frozen=True)
class SwitchContext:
    nodes: tuple[str, ...] = ()      #: long names, selection order
    controls: tuple[Control, ...] = ()   #: the trigger controllers among them
```

with `Control` carrying `node`, `role`, `side`, `module` and `instance` read from
the `trg_*` tags. So `tests/ui/` can drive the whole window offscreen with a
fabricated context and a fake switch, the way `tests/ui/stub.py` already fakes
`GuideScene` — no Maya, no rig, no build.

---

## Part 3 — The shell

Four zones, fixed. A new tab supplies labels for zone 3 and nothing else.

1. **Tab strip** — one tab per switch, in `order`. Each carries an availability
   dot: accent when `states()` is non-empty, `#4f4f4f` when it is not. The dot
   is a generated pixmap set as the tab's icon.
2. **Selection context** — side colour bars (`theme.SIDE`), the control name, the
   module. `2 controls` and the module keys when several are selected. Empty
   selection reads "Select a rig control", not a blank.
3. **State picker** — the states as chips. The control's **current** state is
   filled (the `FilterPill` vocabulary: `#3a2e1f` on a `#FE7E00` border); a
   **pending** choice is outlined in accent without the fill. Mixed across a
   selection is a dashed border and no fill.
4. **Action bar** — `Key`, the `Frame` / `Range` segmented pair, `Apply`, and a
   status line with a state dot (`theme.STATUS`).

### 3.1 Apply commits

Clicking a chip marks it pending and changes nothing in the scene. `Apply` is
enabled only when there is a pending state that differs from the current one.
This is deliberate: `Key` and the frame scope are part of the operation being
composed, and a model where the scene changes before they are set makes them
retroactive corrections rather than choices.

Apply runs, writes one line to the status, and the pending state becomes the
current one.

### 3.2 What `Range` means

`Frame` is the current frame. `Range` is the playback range, and the button says
so — `Range 1–120` — so it is never a mystery.

`times` handed to `apply()` is:

- `Frame`: `(current_time,)`
- `Range`: every keyframe time on any keyable channel of the affected controls
  that falls inside the playback range; when there are none, the current frame,
  and the status says the control has no keys in the range.

The union across *all* channels matters and is not an implementation detail:
once a pivot moves, every later pose depends on it, so a control keyed only on
rotation still needs its translation corrected at those times.

### 3.3 Selection following

A `SceneWatcher` on `SelectionChanged`, `Undo` and `Redo` rebuilds the context
and refreshes the tabs. `Undo` and `Redo` are in the list because undoing a
switch changes a control's current state, and the tool would otherwise show a
stale chip. The watcher is debounced and re-entrancy-guarded already; the
launcher calls `SceneWatcher.uninstall_all()` so a relaunch after a module
reload does not leave the old instance firing into stale code.

---

## Part 4 — The pivot switch

```python
@register_switch("pivot")
class PivotSwitch(Switch):
    label = "Pivot"
    help = "Which point the control turns about."
    order = 10
```

- `states()` — the `pivotPreset` labels shared by every selected control (the
  intersection). A selection with no movable pivot yields `[]`.
- `current()` — the shared label, or `None` when they disagree.
- `apply()` — `pivot.switch_pivot_preset` per control, per time.

### 4.1 `switch_pivot_preset` grows a `times` argument

```python
def switch_pivot_preset(control, preset, key=False, times=None) -> str
```

`times=None` keeps today's behaviour: switch at the current frame. With `times`,
for each time in order: evaluate there, read the control's parent-space origin,
set the preset, read it again, correct `translate` by the difference, and key
`translate` when `key` is set. The `pivotPreset` enum is keyed once, at the first
time, with a **stepped** tangent — a pivot is a discrete state and interpolating
between two enum values is meaningless.

The compensation itself is unchanged and already proven: a `rotatePivot` change
displaces the control by a constant translation in its parent's space, which is
why correcting `translate` by the parent-space delta is exact.

---

## Part 5 — Launch, and what goes away

`tik.trigger.anim.show(dockable=True)` mirrors `tik.trigger.ui.main.show()`:
uninstall stale watchers, tear down the workspace control, construct, show. An
animator's shelf button is one line; the rigger reaches it from the Trigger
window's `Tools > Switches`.

`Tools > Switch Pivot (Preserve)…`, `TriggerWindow.switch_pivot_preset` and
`TriggerWindow._selected_pivot_controls` are **removed**. They are the modal
version of this tool, and two ways to do one thing where one of them takes the
viewport away is the thing this design exists to end.

`Feedback.ask_choice` stays. Its caller goes, but it is a small, tested
primitive on the one dialog surface every tikworks dialog must use, and the next
list question should not have to re-add it.

---

## Part 6 — Tests

| File | What it covers |
|------|----------------|
| `tests/unit/test_import_boundaries.py` | anim may not import session, document, guide_document, guides or ui |
| `tests/unit/test_switch_registry.py` | registration, stamping, ordering, duplicate refusal, the placeholder flag |
| `tests/unit/test_pivot_trigger.py` | `times=` switching, the stepped enum key, the all-channel key-time union, the no-keys fallback |
| `tests/ui/test_switches_window.py` | the shell offscreen with a fake switch and a fabricated context: tab order, availability dots, pending vs current, mixed, Apply enablement, the status line, the empty selection |
| `tests/integration/trigger/test_arm_trigger.py` | the pivot switch's `states`/`current` against a real built arm |

`tests/ui` runs with `TIK_TESTS_NO_MAYA=1`, so the shell and the context
dataclass must import without Maya. That is a constraint on the design, not an
accident of the tests: it is what "the shell never touches Maya" means in
practice.

---

## Summary of Changes

| File | Change |
|------|--------|
| `tik/trigger/anim/` | new package: registry, context, switch, window, launcher |
| `tik/trigger/anim/switches/pivot/` | the pivot switch |
| `tik/trigger/anim/switches/ikfk/`, `polepin/` | declared placeholders |
| `tik/trigger/maya/pivot.py` | `times=`, the stepped enum key, key-time collection |
| `tik/trigger/ui/main.py` | `Tools > Switches`; the modal item and its two handlers removed |
| `tests/unit/test_import_boundaries.py` | the anim rule |
| `AI/coding_rules.md`, `CLAUDE.md` | the switch contract and the anim boundary |
