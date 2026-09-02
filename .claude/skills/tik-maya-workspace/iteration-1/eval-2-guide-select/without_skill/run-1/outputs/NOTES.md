# eval-2-guide-select (without skill) — NOTES

## What I did

Wrote `select_guide_joints.py` (worktree root, copied here): selects every joint
in the scene whose meta `kind` attribute equals `"guide"`.

- Uses only the `tik.maya` wrapper (`tm.ls`, `joint.has_attr`, `joint["kind"].value`,
  `tm.select`) — no direct `maya.cmds`/`OpenMaya` in the script, per project rules.
- This branch of tik.maya has no dedicated meta accessor (`node.meta` from the
  trigger design does not exist here), so "meta" is read as a plain string
  attribute named `kind` on the joint.
- Selects by `long_name` to stay unambiguous with duplicate short names; clears
  the selection when no guide joints exist. Exposes `find_guide_joints()` and
  `select_guide_joints()`; runnable as `__main__`.

## Verification

Ran a real smoke test under Maya standalone
(`C:/Program Files/Autodesk/Maya2026/bin/mayapy.exe`, scratchpad script
`test_select_guides.py`), scene containing:

- 2 joints tagged `kind="guide"` → selected
- 1 joint tagged `kind="deform"` → ignored
- 1 untagged joint → ignored
- 1 transform tagged `kind="guide"` → ignored (not a joint)
- 2 joints both short-named `clash` under different groups, both tagged guide
  → both selected

Result: `ALL ASSERTIONS PASSED` (selection == the 4 expected guide joints;
empty-scene case clears selection and returns `[]`).

## Finding along the way

tik.maya's `Plug` resolves attributes via the node's **short** name
(`Plug.path` → `self._node.name`, used by `_find_plug`), so `joint["kind"].value`
raises `RuntimeError` on nodes with ambiguous short names. The script works
around it by falling back to `tm.getAttr(f"{joint.long_name}.kind")` (the cmds
proxy). Worth fixing in `src/tik/maya/core/plug.py` eventually (use
`long_name`/MPlug from the stored MObject instead of the short path).
