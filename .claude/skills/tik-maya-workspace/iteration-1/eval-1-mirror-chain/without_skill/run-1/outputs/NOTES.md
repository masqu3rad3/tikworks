# Mirror Joint Chain — Notes

## What was done

Added a behavior-mirroring capability for joint chains to tik.maya:

- **`Joint.mirror(plane="YZ", behavior=True, search=None, replace=None)`** in
  `src/tik/maya/types/joint.py`. Defaults match the requested workflow: mirror
  left-to-right across the YZ plane with behavior mirroring. Optional
  `search`/`replace` renames the mirrored chain (e.g. `L_` -> `R_`), and
  `plane` accepts `YZ`/`XY`/`XZ` case-insensitively.
- New test file `tests/unit/test_joint_mirror.py` (10 tests).

## Where it lives and why

The method lives on the `Joint` type wrapper (`tik/maya/types/joint.py`),
alongside `orient()` and the other joint-specific behavior. tik.maya types are
the sanctioned layer for calling `maya.cmds` (`Joint.orient` and
`Transform.freeze` already do), so the implementation wraps Maya's canonical
`cmds.mirrorJoint` (with `mirrorBehavior`) rather than re-deriving mirror math,
and returns the new chain as wrapped `Joint` instances via the registry's
`resolve()`. It is decorated with the existing `@keepselection` so the caller's
selection survives (`mirrorJoint` selects the new chain otherwise). Input
validation (invalid plane, `search` without `replace`) raises `ValueError`
before touching the scene.

One semantic discovered while testing: for a *parented* joint, Maya mirrors
across the plane in the parent's space (through the parent's origin), not the
world origin. The docstring documents this and a test pins it down.

## Verification

Ran under Maya 2026 standalone (`mayapy -m pytest`, pytest 8.4.2, Python 3.11):

- `tests/unit/test_joint_mirror.py` + `tests/unit/test_joint.py`: 18 passed.
- Full unit suite `tests/unit`: **547 passed**, no regressions.

Tests cover: return types, mirrored world positions across YZ (x negated,
y/z kept) and XY/XZ planes, preserved hierarchy and parenting, `L_`->`R_`
search/replace naming, mid-chain mirroring (parent-space plane), selection
preservation, error cases, and the defining behavior-mirror property —
applying identical local rotations to the source and mirrored roots keeps the
wrists exact YZ mirrors of each other.

## Files

- Modified: `src/tik/maya/types/joint.py`
- New: `tests/unit/test_joint_mirror.py`
- Deliverables here: `test_joint_mirror.py`, `changes.diff` (git diff +
  `git status --short`), this `NOTES.md`.
