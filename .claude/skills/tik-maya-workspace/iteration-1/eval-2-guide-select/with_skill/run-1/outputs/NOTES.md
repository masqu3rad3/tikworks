# eval-2-guide-select (with skill) — notes

## What I did

Wrote `select_guide_joints.py` using the tik.maya idioms from the skill — no raw
`maya.cmds` in the script:

- `tm.find_by_meta("kind", "guide", node_type="joint")` finds every joint whose
  typed metadata `kind` equals `"guide"` (the skill's documented API for exactly
  this query; meta lives as hidden `tikMeta_*` attributes, so it survives renames).
- `tm.select_nodes(guide_joints, replace=True)` selects them (wrappers
  auto-stringify — no manual `str()`); if none are found the selection is
  cleared instead.
- The function returns the wrapped Joint nodes, and the module is runnable
  directly (`__main__` prints a count).

One wrinkle: the isolated worktree I ran in holds an older branch whose
`tik.maya` snapshot (`src/tik/maya`, no `core/meta.py`) predates the meta
system. Per the skill's "verify the gap is real" step I checked
`references/api-map.md` and then the main repo — `find_by_meta` and
`node.meta` exist in `D:/dev/tikworks/src/python/tik/maya/core/meta.py` and are
exported as `tm.find_by_meta` / `tm.select_nodes`, so the script targets that
real API rather than re-implementing metadata scanning.

## How I verified it

Ran a standalone check under `mayapy` (Maya 2026) against the main repo's
`src/python`:

1. Built a scene with two meta-tagged guide joints, an untagged joint, a joint
   with `kind == "controller"`, and a locator with `kind == "guide"`.
2. Called `select_guide_joints()` — asserted exactly the two guide joints were
   returned and selected (`cmds.ls(selection=True)` in the test harness only).
3. Renamed one guide joint — still found and selected (meta is attribute-based).
4. Cleared the meta tags — function returned `[]` and cleared the selection.

Result: **ALL CHECKS PASSED** (verification script:
`verify_select_guide_joints.py` in the session scratchpad; the only console
noise was unrelated `userSetup` MEL errors from other tools on this machine).
