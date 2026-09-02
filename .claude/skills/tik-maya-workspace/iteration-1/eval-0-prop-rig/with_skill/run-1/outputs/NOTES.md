# eval-0 prop-rig — with_skill — notes

## What was built

`src/python/tools/prop_rig.py` — `build_prop_rig(mesh=None, name=None, control_shape="Circle", control_size=None, control_color=17)`.

For the selected mesh (or an explicit mesh/transform argument) it creates:

- `<name>_root_grp` — `tm.Transform.create`, snapped to the mesh transform's position/rotation (`snap_to`)
- `<name>_offset_grp` — under the root (zeroed local, inherits the root placement)
- `<name>_ctrl` — a `Controller.create(shape="Circle", ...)` under the offset group, circle radius auto-fitted to the mesh bounding box, colored yellow
- the controller drives the mesh transform via `parentConstraint` + `scaleConstraint` (`maintainOffset=True`) through the tm cmds proxy — so the mesh keeps its current pose and follows the control for T/R/S

Returns a dict of wrappers (`mesh`, `root`, `offset`, `control`, `constraints`), selects the controller, and the whole build is one undo chunk (`@undo` from `tik.maya.core.decorators`).

## tik.maya adherence

No raw `maya.cmds` / `OpenMaya` imports in the tool. Everything goes through `tik.maya` (`tm.resolve`, `tm.ls`, `Transform.create`, `snap_to`, `bounding_box`, the `Controller` role, `@undo`). The two constraints use the documented cmds-proxy escape hatch (`tm.parentConstraint` / `tm.scaleConstraint`) — both are in `NODE_FACTORIES`, so they return wrapped nodes. This branch of the worktree has no `MatrixConstraint` construct (the `constructs/` folder only contains `panel.py`), so the proxy was the right tool per the skill's guidance.

## Layout caveat

The task asked for `src/python/tools/prop_rig.py` and the file was placed exactly there. Note the worktree branch (`worktree-agent-a04cdafcc5a489521`) actually uses a `src/tik/...` layout (`src/tik/tools/` is where the existing `polish` tool lives), so on this branch the natural home would be `src/tik/tools/prop_rig.py`; the module is import-path-agnostic either way (it only needs `tik` importable).

## Verification (really ran)

Ran a standalone check script under real Maya via
`C:\Program Files\Autodesk\Maya2026\bin\mayapy.exe` (script: scratchpad `verify_prop_rig.py`), covering:

- no selection -> `RuntimeError`; non-mesh argument -> `ValueError`
- build from a selected, moved+rotated `polySphere`: node names, hierarchy (root -> offset -> ctrl), root at world level, root snapped to mesh pivot, controller has nurbsCurve shapes and is tagged, mesh pose unchanged by the build
- driving: moving/scaling/rotating the controller moves/scales/rotates the mesh (offset maintained, e.g. ctrl ry 30 on a 45-rotated mesh -> mesh ry 75)
- explicit `mesh=` + custom `name=`; selecting the mesh *shape* resolves to its transform
- one `cmds.undo()` removes the entire rig

Result: **ALL 20 CHECKS PASSED** (the only console errors were from the user's own userSetup scripts referencing `$gMainWindow`, unrelated to this tool).

Nothing was committed; the file is untracked in the worktree (`changes.diff` shows the new-file diff captured via `git add -N`, then the index was reset).
