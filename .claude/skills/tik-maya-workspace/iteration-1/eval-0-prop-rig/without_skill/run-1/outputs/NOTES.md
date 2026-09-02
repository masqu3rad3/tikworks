# eval-0-prop-rig (without skill) — notes

## What was built

`src/python/tools/prop_rig.py` — `build_prop_rig(name=None, controller_size=None, controller_color=17)`:

- Finds the selected mesh: accepts either a selected mesh shape or a selected
  transform carrying a mesh shape (first match wins). Raises `RuntimeError`
  when nothing suitable is selected.
- Builds `<name>_root_GRP` snapped (position + rotation) to the mesh pivot,
  `<name>_offset_GRP` zeroed under it, and `<name>_CTRL` (circle controller)
  zeroed under the offset.
- The controller drives the mesh transform via `parentConstraint` +
  `scaleConstraint` (maintainOffset), leaving the geometry hierarchy untouched.
- Controller size defaults to a radius fitted from the mesh bounding box
  (max of width/depth * 0.5 * 1.2); color defaults to index yellow (17).
- Returns a dict of the created nodes and selects the controller.

Per the repo rule ("consume tik.maya, don't call cmds directly"), the tool is
written entirely against `tik.maya`: `Transform.create`, `snap_to`,
`Controller.create` (roles/controller with the built-in "Circle" library
shape), the `tm.ls` / `tm.parentConstraint` proxy layer, and the `@undo`
decorator so the whole build is one undo chunk.

Note on location: the task asked for `src/python/tools/prop_rig.py` (matching
the layout described in CLAUDE.md), but this worktree's actual layout is
`src/tik/...` with tools under `src/tik/tools/`. I followed the task path
literally; if it should live with the other tools, it belongs at
`src/tik/tools/prop_rig.py` (contents unchanged — only the import in the
usage docstring would become `from tik.tools.prop_rig import build_prop_rig`).

## Verification

Ran a smoke script under `mayapy` (Maya 2026, `maya.standalone`), covering:

- no selection raises `RuntimeError` — passed
- build on a translated/rotated `polyCube`:
  - hierarchy root -> offset -> ctrl and expected names — passed
  - controller has nurbsCurve shapes and the `isController` tag — passed
  - root world translation matches the mesh pivot (2, 1, -3) — passed
  - moving the controller moves the mesh (parentConstraint) — passed
  - scaling the controller scales the mesh (scaleConstraint) — passed
  - parentConstraint and scaleConstraint nodes exist under the mesh — passed
- selecting the mesh *shape* (not the transform) also builds correctly,
  with explicit `controller_size`/`controller_color` overrides — passed

Output ended with `ALL SMOKE CHECKS PASSED`. (Maya 2024 is installed but has
no `mayapy.exe` on this machine, so 2026 was used.) The existing pytest suite
was not run since no existing repo files were touched.

## Files changed

- Added: `src/python/tools/prop_rig.py` (new file; no existing files modified)
