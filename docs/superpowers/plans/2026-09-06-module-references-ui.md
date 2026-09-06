# Module References UI — Implementation Plan (Phase 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A rigger can link another session's modules, see which modules are borrowed and which they have overridden, revert an override, and choose what a `kinematics` action builds — all without touching Python.

**Architecture:** Four independent surfaces, each fed from data Phase 2 already produces (`entry.origin`, `entry.source`, `entry.enabled`, `overrides_for`). The tree gets two new item roles and paints them in the existing delegate; the properties panel gains a provenance strip; the Designer gains link/unlink gestures through `Feedback`; and `ListField` learns to render as a picker when it declares `choices_from`, which is what makes `kinematics.modules` editable at all.

**Tech Stack:** Python 3.10+, Qt (PySide via `tik.shared.ui.Qt`), pytest. UI tests run headless with `TIK_TESTS_NO_MAYA=1` and `QT_QPA_PLATFORM=offscreen`.

**Spec:** `docs/superpowers/specs/2026-09-06-module-referencing-design.md` §7.1, §7.3, §7.4. **Out of scope, deferred to Phase 4:** §7.2, the collapsible graph frame per reference — it needs a new `QGraphicsItem`, collapse behaviour and edge rerouting, and is the one piece with no existing scaffolding to extend.

**Depends on:** Phase 2 (`2026-09-06-module-references-engine.md`), complete.

## Global Constraints

- **One dialog surface.** Every message box, file browser and text prompt goes through `tik.shared.ui.feedback.Feedback`. A raw `QMessageBox` / `QFileDialog` / `QInputDialog` outside `shared/ui/feedback.py` fails `tests/unit/test_dialog_boundaries.py`.
- **Only `tik/trigger/ui` may read preferences.** This plan reads none.
- **`tik/trigger/core` stays pure** — no Qt. The picker's *widget* lives in `tik/shared/ui/fields.py`; only the `choices_from` **declaration** goes on the field in `tik/core/fields.py`, which is data, not Qt.
- **No third-party deps.** Line length 88, black + isort + flake8 clean.
- The tree and the graph are fed from **one** `GuideDiff` (`window.py` computes it once and hands it to both). Do not add a second scan; the override count is computed from the document alongside it, never folded into `GuideDiff` — overridden compares resolved-to-source and has nothing to do with the scene.

## Running tests

```bash
MAYAPY="/c/Program Files/Autodesk/Maya2026/bin/mayapy"
# UI (no Maya standalone: it cannot host a QApplication)
TIK_TESTS_NO_MAYA=1 QT_QPA_PLATFORM=offscreen PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "$MAYAPY" -m pytest tests/ui -q
# everything else
PYTHONPATH="D:/dev/tikworks/src/python;$PYTHONPATH" "$MAYAPY" -m pytest tests/unit tests/integration -q
```

Baseline entering this phase: **1700 unit+integration, 494 UI, lint clean.**

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `src/python/tik/core/fields.py` | `ListField` gains `choices_from` — a declaration only, no Qt. | 1 |
| `src/python/tik/shared/ui/fields.py` | A checkable list widget for a `ListField` that declares `choices_from`, resolved through an injected callable. | 1 |
| `src/python/tik/trigger/actions/kinematics/kinematics.py` | `modules` declares `choices_from="modules"`. | 1 |
| `src/python/tik/trigger/ui/settings_panel.py` | Passes a module-choices callable into `FormBuilder`. | 1 |
| `src/python/tik/trigger/ui/main.py` | Wires that callable to the current session's guide document. | 1 |
| `src/python/tik/trigger/ui/designer/delegates.py` | Paints the origin chip, the override diamond and the disabled row. | 2 |
| `src/python/tik/trigger/ui/designer/window.py` | Fills the new roles when populating the tree. | 2 |
| `src/python/tik/trigger/ui/designer/properties.py` | Provenance strip, *Revert to source*, the enabled toggle. | 3 |
| `src/python/tik/trigger/ui/designer/action_bar.py` (or the window's menu) | *Reference Modules…* and *Unlink*. | 4 |
| `tests/ui/test_kinematics_picker.py` | **New.** The picker widget and its wiring. | 1 |
| `tests/ui/test_designer_references.py` | **New.** Tree roles, properties strip, gestures. | 2–4 |
| `tests/ui/stub.py` | Grows whatever the new surfaces read. | 2–4 |

---

### Task 1: A picker for a list of ids

`kinematics.modules` is a `ListField` of uuids and currently renders as a comma-separated `QLineEdit` (`shared/ui/fields.py`, `kind == "list"`). Nobody can type a uuid. Until this exists, Phase 1 left the action uneditable in the UI — so this task comes first.

**Files:**
- Modify: `src/python/tik/core/fields.py` (`ListField.__init__`)
- Modify: `src/python/tik/shared/ui/fields.py` (`FormBuilder._make_widget`, `__init__`, `_set_widget_value`)
- Modify: `src/python/tik/trigger/actions/kinematics/kinematics.py`
- Modify: `src/python/tik/trigger/ui/settings_panel.py`, `src/python/tik/trigger/ui/main.py`
- Test: `tests/ui/test_kinematics_picker.py` (create)

**Interfaces:**
- Produces: `ListField(..., choices_from="modules")`; `FormBuilder(list_choices=callable)` where the callable takes the `choices_from` key and returns `[(label, value)]`; `_CheckListEditor` with `value()` / `set_value(list)` and a `valueChanged` signal, matching the other editors in that module.
- Consumes: `ActionSettingsPanel(module_choices=callable)`, wired in `main.py` to `[(entry.key, entry.instance_id) for entry in session.document.guides.modules if entry.enabled]`.

- [ ] **Step 1: Write the failing test**

`tests/ui/test_kinematics_picker.py`, following the conventions already in `tests/ui/`:

- a `ListField` with `choices_from` renders a checkable list, not a line edit;
- each row shows the **label** (`L_arm`) and carries the **value** (the uuid);
- ticking a row writes `[uuid]` into the field;
- a field already holding a uuid opens with that row ticked;
- a stored id that is no longer offered still shows, ticked, marked missing — so a stale entry is visible rather than silently dropped;
- a `ListField` **without** `choices_from` still renders the comma-separated line edit (no regression).

- [ ] **Step 2: Run it to verify it fails**

- [ ] **Step 3: Declare `choices_from` on the field**

In `tik/core/fields.py`:

```python
    def __init__(
        self,
        default=None,
        *,
        item_type: Optional[type] = None,
        choices_from: str = "",
        **kwargs,
    ) -> None:
        self.item_type = item_type
        #: Names the option source a UI resolves to render this as a picker.
        #: A declaration only -- ``tik.core`` never imports Qt, and a list
        #: without it stays a plain comma-separated field.
        self.choices_from = choices_from
        super().__init__(list(default) if default else [], **kwargs)
```

- [ ] **Step 4: Render the picker**

In `shared/ui/fields.py`, accept `list_choices` in `FormBuilder.__init__` (default `None`) and branch in `_make_widget`:

```python
        elif kind == "list":
            source = getattr(field, "choices_from", "")
            if source and self.list_choices is not None:
                widget = _CheckListEditor(lambda key=source: self.list_choices(key))
                widget.valueChanged.connect(
                    lambda value, field_name=name: self._on_change(field_name, value)
                )
            else:
                widget = QtWidgets.QLineEdit()
                ...unchanged...
```

`_CheckListEditor` is a `QListWidget` with checkable items. It refreshes its options every time `set_value` runs, because the module list changes while the panel is open. An id in the value that no option offers is appended as a ticked row labelled `"<id> (missing)"` and disabled for editing — never dropped, or saving would quietly shrink somebody's build scope.

- [ ] **Step 5: Wire it through**

`kinematics.modules` declares `choices_from="modules"`. `ActionSettingsPanel` takes `module_choices` and passes `list_choices=` to its `FormBuilder`. `main.py` supplies the current session's modules as `(key, instance_id)` pairs, skipping `enabled is False` ones — a module deliberately left out of the rig should not be offered for building (§6.2 already makes listing one an error).

- [ ] **Step 6: Run the UI suite, lint, commit**

---

### Task 2: The tree says what is borrowed and what is overridden

**Files:**
- Modify: `src/python/tik/trigger/ui/designer/delegates.py`
- Modify: `src/python/tik/trigger/ui/designer/window.py` (the population loop around `item.setData(0, DrawStateRole, state)`)
- Test: `tests/ui/test_designer_references.py` (create)

**Interfaces:**
- Produces: `OriginRole = QtCore.Qt.UserRole + 21`, `OverrideRole = QtCore.Qt.UserRole + 22`, `DisabledRole = QtCore.Qt.UserRole + 23` in `designer/delegates.py`.
- Consumes: `entry.origin`, `entry.enabled`, and `core.guide_reference.overrides_for(entry)` for the count.

- [ ] **Step 1: Write the failing test**

Assert, against the stub scene extended with referenced entries:

- a local module's row carries `OriginRole` `None` and `OverrideRole` `0`;
- a referenced module's row carries the reference's **file name** in `OriginRole`;
- an overridden referenced module's row carries the number of overridden things in `OverrideRole`;
- moving a guide back to source drops the count to 0 (the self-cleaning property, visible in the UI);
- a disabled referenced module's row carries `DisabledRole` True;
- the existing `DrawStateRole` is unaffected — a referenced module can be *not drawn* **and** overridden at once, and both must survive.

- [ ] **Step 2: Run it to verify it fails**

- [ ] **Step 3: Fill the roles**

In `window.py`, in the same loop that sets `DrawStateRole` (so there is still one pass, and no second diff):

```python
            from tik.trigger.core.guide_reference import overrides_for

            documents = {
                entry.instance_id: entry for entry in self.guides.document.modules
            }
            names = {
                item.ref_id: Path(item.file).name
                for item in self.guides.document.references
            }
            for instance_id, item in items.items():
                state = states.get(instance_id, DRAWN)
                item.setData(0, DrawStateRole, state)
                entry = documents.get(instance_id)
                origin = names.get(entry.origin) if entry is not None else None
                item.setData(0, OriginRole, origin)
                item.setData(0, OverrideRole, len(overrides_for(entry)) if entry else 0)
                item.setData(0, DisabledRole, entry is not None and not entry.enabled)
                item.setToolTip(0, _row_tooltip(state, origin, entry))
```

`_row_tooltip` composes the existing `TOOLTIPS[state]` with a provenance line and an override line, so the two facts stay legible together rather than one replacing the other.

- [ ] **Step 4: Paint them**

Extend `GuideStateDelegate.paint`. After the existing dot:

- **origin chip** — a small rounded rect, right-aligned in column 0, carrying the reference file's stem. Muted fill, not the accent: provenance is information, not a warning.
- **override diamond** — a filled ◆ before the chip with the count beside it when `OverrideRole > 0`. This one *does* earn a visible ink: an override is the thing that silently stops upstream fixes arriving.
- **disabled** — strike-through font and the dimmed text colour.

Reuse `draw_state.COLORS` and `DIMMED_TEXT` rather than inventing a palette; add only the two new inks the chip and diamond need, defined beside them.

- [ ] **Step 5: Run the UI suite, lint, commit**

---

### Task 3: Provenance and revert in the properties panel

**Files:**
- Modify: `src/python/tik/trigger/ui/designer/properties.py`
- Modify: `src/python/tik/trigger/ui/designer/window.py` (build the strip; show/hide on selection)
- Test: `tests/ui/test_designer_references.py` (extend)

**Interfaces:**
- Produces: `DesignerProperties._reference_strip()` returning the widget, `revert_module()` and `set_module_enabled(bool)` commands.
- Consumes: `Session.document.guides`, `core.guide_reference.overrides_for`, `Feedback.pop_question`.

- [ ] **Step 1: Write the failing test**

Assert: selecting a local module hides the strip; selecting a referenced one shows it naming the file; *Revert all* clears the overrides and the tree's `OverrideRole` returns to 0; the enable toggle writes `entry.enabled` and the row picks up `DisabledRole`; reverting asks for confirmation through the `Feedback` handler seam (`feedback.set_handler`) rather than a raw dialog.

- [ ] **Step 2: Run it to verify it fails**

- [ ] **Step 3: Build the strip**

A one-line header above the form: *from `baseRig.tr`* plus, when there are overrides, *n overridden* and a **Revert all** button, and a **Build in this rig** checkbox bound to `entry.enabled`.

Revert is a delete, not an unwind: copy the source's authored values back onto the entry (`name`, `side`, `settings`, `inputs`, and each guide record), then `touch()`. Because overrides are derived, the next `to_dict` simply finds no difference. Follow the revert with a **draw** of that module so the scene stops showing the reverted pose — and do it with the scene watcher muted and *before* any sync, or the sync re-derives the override from the joints that have not moved yet.

- [ ] **Step 4: Run the UI suite, lint, commit**

---

### Task 4: Link and unlink from the Designer

**Files:**
- Modify: `src/python/tik/trigger/ui/designer/window.py` (menu/bar entries and handlers)
- Test: `tests/ui/test_designer_references.py` (extend)

**Interfaces:**
- Consumes: `Session.link_modules(file, version)`, `Session.unlink_modules(ref_id, bake)`, `Feedback.browse_open`, `Feedback.pop_question`.

- [ ] **Step 1: Write the failing test**

Assert: *Reference Modules…* browses through the injected `file_browser` (never a raw `QFileDialog`) and calls `link_modules` with what it returns; a cancelled browse does nothing; linking an already-linked file surfaces the `SessionError` message rather than raising into Qt; *Unlink* asks the discard-or-bake question through `Feedback` and passes the answer to `unlink_modules`; the tree refreshes afterwards.

- [ ] **Step 2: Run it to verify it fails**

- [ ] **Step 3: Implement**

Both live where the Designer's other file gestures live, and both go through `self.file_browser` / `Feedback` so the boundary test stays green. Unlink's question is three-way — *Bake in*, *Discard*, *Cancel* — because discarding authored overrides is the one destructive act in this feature and must not be the default button.

- [ ] **Step 4: Run everything, lint, commit**

---

## Done when

- [ ] `tests/unit`, `tests/integration` and `tests/ui` are green.
- [ ] `make lint` is clean; `tests/unit/test_dialog_boundaries.py` still passes (no raw dialogs added).
- [ ] A rigger can, with no Python: link a `.tr`, see its modules badged in the tree, tick them into a `kinematics` action, move one of its guides, see the override count appear, revert it, and unlink.
- [ ] Phase 4 (the graph frame, spec §7.2) has its own plan and is not started here.
