---
name: twist-wrap-final-joint-hookup
description: Euler wrap only breaks interpolation, not the final pose; flat joints with live channels + unbounded twist = decompose swing, add twist float to rotateX (verified)
type: methodology
---

**What is true (verified live in Maya 2026-08-29):**
- `decomposeMatrix` wraps rotation to (−180, 180]: 270 → −90, 450 → 90, 720 → 0. A float channel is unbounded.
- BUT 270° and −90° about one axis are the *same orientation* — deformation is identical. Wrap only produces a visible error where a joint needs a *fraction* of the twist (mid joint must be 135°, quaternion/matrix blend gives −45°). Float interpolation of twist fixes that regardless of the final hookup.
- Flat joint (no parent, no offsetParentMatrix) with live channels and unbounded twist: `rotate = decompose(swing_only_matrix)`, then `rotateX += twist_float`, rotate order `xyz` (X innermost = rotation about the joint's own aim axis). Matches a parented swing+twist reference to ~1e-16 at 0/90/135/270/450°.
- Karoly's pure-math ribbon: joints flat, driven via offsetParentMatrix (parentMatrix→aimMatrix), twist float on rotateX. His translate channels are NOT live — flatness ≠ live values.

**Why:** The user requires flat deform joints with live TRS channel values AND 270°+ twist. The naive "decompose everything" hookup would wrap the rotateX readout; the swing/twist split preserves it.

**How to apply next time:** Keep the aim frame twist-free (up vector from a frame that carries no axial rotation), route ALL axial rotation (whole-segment roll + differential twist) as floats, and add twist after decomposition. Remember the swing Euler gimbal singularity (cosmetic channel jump only). See [[controllers-drive-twist]], [[pure-math-ribbon-research]].
