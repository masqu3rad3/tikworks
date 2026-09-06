# Module Reference Graph Frame — Implementation Plan (Phase 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A reference draws as a frame around its modules in the graph, and collapses to a single node — so a hero rig referencing a forty-module base stays readable.

**Architecture:** Two states, and neither hides anything. **Expanded** builds the member nodes exactly as today plus a `FrameItem` drawn behind them, sized to their extents. **Collapsed** builds *one* `NodeItem` in their place, whose ports are only the connections that cross the boundary, with wires rewritten to it. Choosing between two builds rather than hiding-and-rerouting means no second wire path to keep correct, and a collapsed frame is an ordinary node to selection, dragging and hit-testing.

**Tech Stack:** Python 3.10+, Qt (`tik.shared.ui.Qt`), pytest. UI tests run headless with `TIK_TESTS_NO_MAYA=1` and `QT_QPA_PLATFORM=offscreen`.

**Spec:** `docs/superpowers/specs/2026-09-06-module-referencing-design.md` §7.2. This is the last unbuilt section of that spec.

**Depends on:** Phase 3, complete. `GuideDocument.frames` already exists (added in Phase 2, Task 1) and is deliberately *not* `positions`/`collapse` — those two are projected through `node_ids()` and replaced wholesale by `layout_from_keys`, so a frame stored there would be deleted by the first node drag.

## Global Constraints

- **No third-party deps.** Line length 88, black + isort + flake8 clean.
- **One dialog surface** — this plan adds no dialogs.
- The graph paints draw state from the **pushed** `draw_states` dict, never by scanning the scene itself. Do not add a second source.
- `collapse` holds a 0–2 node *mode*; a frame's collapsed flag is a **bool** in `frames`. Do not conflate them.

## Running tests

```bash
MAYAPY="/c/Program Files/Autodesk/Maya2026/bin/mayapy"
TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "$MAYAPY" -m pytest tests/ui -q
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "$MAYAPY" -m pytest tests/unit tests/integration -q
```

Baseline entering this phase: **1700 unit+integration, 526 UI, lint clean.**

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `src/python/tik/trigger/guides/scene.py` | `frames` / `set_frame` — the frame section of the layout, bypassing the display-key projection. | 1 |
| `src/python/tik/trigger/ui/graph/items.py` | `FrameItem`: the background rect, its title and its collapse glyph. | 2 |
| `src/python/tik/trigger/ui/graph/scene.py` | `add_frame`, and clearing frames with the rest of the graph. | 2 |
| `src/python/tik/trigger/ui/graph/view.py` | Group members by origin; build expanded-with-frame or collapsed-as-one-node; rewrite crossing wires. | 3 |
| `tests/ui/stub.py` | `frames` / `set_frame`, mirroring the scene. | 1 |
| `tests/ui/test_graph_frames.py` | **New.** Everything above. | 1–3 |

---

### Task 1: The frame section of the layout

**Files:**
- Modify: `src/python/tik/trigger/guides/scene.py`
- Modify: `tests/ui/stub.py`
- Test: `tests/ui/test_graph_frames.py` (create)

**Interfaces:**
- Produces: `GuideScene.frames -> dict` (`{ref_id: {"position": [x, y], "collapsed": bool}}`) and `GuideScene.set_frame(ref_id, position=None, collapsed=None)`, which touches the session so a collapse lands on the undo stack like any other document edit.

- [x] **Step 1: Write the failing test**

Assert: `frames` starts empty; `set_frame` stores a position and a collapsed flag; setting one leaves the other alone; the values survive a `GuideDocument` round trip; and — the reason this section exists at all — a `set_layout` call (what every node drag performs) **does not** clear them.

- [x] **Step 2: Run it to verify it fails**

- [x] **Step 3: Implement**

```python
    @property
    def frames(self) -> dict:
        """Graph frame placement per reference, ``{ref_id: {...}}``.

        Its own section, not part of ``layout``: that one is projected through
        display keys and replaced wholesale on every drag, which would delete
        a frame the first time anybody moved a node.
        """
        return {key: dict(value) for key, value in self.document.frames.items()}

    def set_frame(self, ref_id, position=None, collapsed=None) -> None:
        """Store a frame's position and/or collapsed state. Partial updates."""
        frame = self.document.frames.setdefault(ref_id, {})
        if position is not None:
            frame["position"] = [float(position[0]), float(position[1])]
        if collapsed is not None:
            frame["collapsed"] = bool(collapsed)
        self._touch()
```

Mirror both on `StubScene`.

- [x] **Step 4: Run it, lint, commit**

---

### Task 2: `FrameItem`

**Files:**
- Modify: `src/python/tik/trigger/ui/graph/items.py`, `graph/scene.py`, `graph/constants.py`
- Test: `tests/ui/test_graph_frames.py` (extend)

**Interfaces:**
- Produces: `FrameSpec(ref_id, title, collapsed)` and `FrameItem(spec)` with `set_extent(QRectF)` and a `glyph_rect()` for the collapse toggle; `GraphScene.add_frame(spec, rect) -> FrameItem` and a `frame_toggle_requested = QtCore.Signal(str)`.

- [x] **Step 1: Write the failing test**

Assert: a frame's bounding rect encloses the rect it was given plus its padding; its title reads the reference's name; it sits **behind** the nodes (`zValue()` below every `NodeItem`); it is not selectable or movable when expanded (it is a backdrop, and dragging it would fight the nodes inside); clicking its glyph emits `frame_toggle_requested` with the `ref_id`.

- [x] **Step 2: Run it to verify it fails**

- [x] **Step 3: Implement**

`FrameItem` is a plain `QGraphicsItem` with `setZValue(-10)`, a rounded rect stroked in a muted ink (same `ORIGIN_INK` family the tree chip uses, so provenance reads the same in both panes), a title in the top-left, and a glyph rect in the top-right. `PADDING = 16` and `TITLE_HEIGHT = 20` go in `constants.py` beside the other geometry.

- [x] **Step 4: Run it, lint, commit**

---

### Task 3: Build expanded or collapsed

The task that makes it useful.

**Files:**
- Modify: `src/python/tik/trigger/ui/graph/view.py` (`rebuild`)
- Test: `tests/ui/test_graph_frames.py` (extend)

**Interfaces:**
- Consumes: `entry.origin` per handle (through `guides.document`), `GuideScene.frames`, `GraphScene.add_frame`.
- Produces: a collapsed frame node keyed `@<ref_id>`, whose port names are the member keys they belong to (`L_arm.hand`), so a wire to it still names its real producer.

- [x] **Step 1: Write the failing test**

Assert, with two referenced modules and one local module wired to one of them:

- **expanded** — all three module nodes exist, plus one `FrameItem`, and the frame's rect encloses both member nodes;
- **collapsed** — the two member nodes are **gone**, one node keyed `@r1` exists, the local node still exists, and the wire from the local module now lands on the collapsed node;
- a connection **between two referenced modules** does not appear as a port on the collapsed node — only crossings do, which is the entire point of collapsing;
- toggling back to expanded restores the member nodes and the original wire;
- a reference with no crossing connections still collapses to a node with no ports rather than vanishing.

- [x] **Step 2: Run it to verify it fails**

- [x] **Step 3: Implement**

In `rebuild`, before placing nodes, partition the handles:

```python
        entries = {item.instance_id: item for item in self.guides.document.modules}
        frames = self.guides.frames
        origin_of = {
            handle.key: entries[handle.instance_id].origin
            for handle in handles
            if handle.instance_id in entries
        }
        collapsed = {
            ref_id
            for ref_id, frame in frames.items()
            if frame.get("collapsed")
        }
```

A handle whose origin is in `collapsed` is not drawn. For each collapsed `ref_id`, walk every connection once and keep the crossings: a source inside and a target outside becomes an **output** on the frame node; a source outside and a target inside becomes an **input**. Port names keep the member's key (`L_arm.hand`), so the wire still names its real producer and expanding restores the same connection without a translation table.

Wire rewriting is one substitution at the point wires are added: if a key belongs to a collapsed reference, address `@<ref_id>` and the member-qualified port instead.

For each *expanded* reference, add a `FrameItem` after its members are placed, sized to their union rect.

- [x] **Step 4: Wire the toggle**

`frame_toggle_requested` reaches the Designer, which calls `guides.set_frame(ref_id, collapsed=not collapsed)` and refreshes. The collapsed node's position is stored through `set_frame` when it is dragged, in the same place `nodes_moved` already persists node positions.

- [x] **Step 5: Run everything, lint, commit**

---

## Done when

**Status: complete.** 1700 unit+integration and 547 UI tests pass, lint clean.

- [x] `tests/unit`, `tests/integration` and `tests/ui` are green; `make lint` clean.
- [x] A reference collapses to one node and expands back, with crossing wires preserved both ways.
- [x] A node drag does not delete a frame (the bug that `frames` exists to prevent).
- [x] The spec has no unbuilt sections left.
