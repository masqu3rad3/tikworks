---
name: aim-up-frame-twist-subtracted
description: A static aim up-vector flips when the segment swings parallel to it; use Rx(-wired_twist) x pinned start matrix as the up frame. Karoly uses no secondary at all.
type: methodology
---

**What is true (verified live 2026-08-29, Maya 2027):**
- `aimMatrix` keeps the input's translate and scale; only rotation is replaced.
- `multMatrix[composeMatrix(rotateX=-t), plug.worldMatrix]` equals the plug's swing-only frame exactly at t = 90/270/450 (matrices are periodic, the float t is not).
- `parentMatrix` weighted targets = normalised weighted sum of translate and scale; `pickMatrix(useRotate=0)` strips rotation; `aimMatrix` secondaryMode Align(2) with a matrix target projects that frame's axis onto the aim plane.
- Karoly's pure-math ribbon has NO secondary/up input ("in my example I don't have that") — roll is whatever the minimal-rotation aim produces. Do not copy that for limbs.

**Why:** The first spec draft took the up vector from the static ribbon group; an arm hanging straight down makes aim ∥ up → every joint flips. Pins that carry rotation fix it, but then the pinned roll would double-count the float twist — subtracting the wired twist float via composeMatrix gives a swing-only frame that follows the limb.

**How to apply next time:** For any aim-based strip: up frame = pinned start matrix with the wired twist removed; keep twist as floats onto rotateX. Aim targets = next output's pre-aim (pickMatrix) matrix, last aims at the last driver → no evaluation cycles. See [[twist-wrap-final-joint-hookup]], [[pure-math-ribbon-research]].
