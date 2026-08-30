# Mirror joint chain — implementation notes

## What was done

Added a `mirror()` method to the `Joint` wrapper in tik.maya, so a joint chain can
be mirrored across a world plane (YZ by default, i.e. left-to-right across X) with
behavior mirroring on by default:

```python
import tik.maya as tm

root = tm.resolve("L_shoulder")
mirrored = root.mirror(plane="YZ", behavior=True, search="L_", replace="R_")
# -> [Joint('R_shoulder'), Joint('R_elbow'), Joint('R_wrist')]
```

Signature: `Joint.mirror(plane="YZ", behavior=True, search=None, replace=None) -> list[Joint]`

- `plane` — `"YZ"` / `"XY"` / `"XZ"`, case-insensitive; invalid values raise `ValueError`.
- `behavior` — behavior mirroring (opposed rotation axes) vs. orientation-only.
- `search` / `replace` — optional name substitution for the duplicates (e.g. `"L_"` -> `"R_"`);
  providing only one of the pair raises `ValueError`.
- Returns tik.maya `Joint` wrappers (UUID-tracked), root first.
- Decorated with `@protected` (raises on a dead node) and `@keepselection`
  (the underlying command changes the selection; the caller's selection is restored).

## Where it lives and why

- `src/tik/maya/types/joint.py` — the `Joint` type wrapper. Per the tik-maya skill,
  all Maya interaction belongs inside tik.maya, and this is a joint-node capability
  with no semantic/rig meaning, so it belongs on the **type** (not a role or a
  construct — it creates no persistent multi-node network, it is a one-shot action).
  Internally it wraps `cmds.mirrorJoint`, which is legal there (raw `cmds` is allowed
  inside tik.maya) and is a single undoable command, so undo works out of the box.
- `tests/unit/test_joint.py` — tests appended to the existing joint test module,
  following its conventions (real Maya standalone, raw `cmds` for assertions).

Note: this worktree snapshot uses the `src/tik/...` layout (not `src/python/tik/...`
as in the current main branch); the code was placed where the worktree's package
actually lives.

## Tests added

- `test_mirror_chain_yz_returns_joints` — 3 `Joint` wrappers returned, names
  substituted L_->R_, mirrored hierarchy intact, original chain untouched.
- `test_mirror_chain_yz_positions_are_reflected` — every mirrored joint sits at the
  X-negated world position.
- `test_mirror_behavior_produces_symmetric_motion` — the defining behavior-mirror
  property: applying identical local rotation values to matching joints on both
  sides leaves the end joints mirror-symmetric across YZ (chain built with
  non-trivial joint orients so this actually exercises the axis flipping).
- `test_mirror_without_behavior_keeps_reflected_positions` — orientation-only mode.
- `test_mirror_from_mid_chain_only_mirrors_descendants` — mirroring a mid-chain
  joint duplicates only that joint and below, parented under the original parent.
- `test_mirror_plane_is_case_insensitive`, `test_mirror_invalid_plane_raises`,
  `test_mirror_search_without_replace_raises`, `test_mirror_keeps_selection`.

Position assertions use `abs=1e-4` tolerance: `cmds.mirrorJoint` stores values at
32-bit float precision, so mirrored positions differ from the exact double-precision
reflection by ~4e-6.

## Verification

Ran under Maya 2026 standalone (`mayapy -m pytest`, `PYTHONPATH=src`):

- `tests/unit/test_joint.py` — 17 passed (8 pre-existing + 9 new).
- Full `tests/unit` suite — 546 passed, 0 failed (no regressions).

## Files changed (no new source files were created)

- `src/tik/maya/types/joint.py` (modified)
- `tests/unit/test_joint.py` (modified)

The `src/python/tools/prop_rig.py` entry visible in `git status` is a pre-existing
stale intent-to-add index entry in the worktree (the file does not exist on disk);
it is not part of this change.
