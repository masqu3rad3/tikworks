---
name: arm-collar-cycle-upstream-plugs
description: Which limb.py results are upstream vs downstream of the auto-collar in arm.py, and why the FK control's local `matrix` is the safe driver
type: repo-fact
---

**What is true:** in `modules/arm/arm.py` the collar drives `limb_from`
(`arm.py:132-135`), which is `build_ikfk_limb`'s `parent`. Everything the limb
hangs off that parent is **downstream** of the auto-collar and cycles if a reach
driver reads it.

Downstream of the collar (do NOT read from a reach driver):

- `puppet_group` (`limb.py:153-156`) and therefore both joint chains and the
  bind blend
- `pole_base` (`limb.py:185-189`) and therefore `soft_ik` (`limb.py:274-280`),
  the stretch/squash `Measure`s (`limb.py:320-325`, `333-337`), the pole space
  `AimFrame`, and so `pole_control` / `pole_tweak` **world** matrices
  (`limb.py:349-372`), plus `ik_lengths`' stretch factor
- `fk_controls[0].offset` (`limb.py:228-229`) and therefore every FK control's
  **world** matrix; `ik_handle`

Genuinely upstream (safe to read):

- `ik_control` / `ik_tweak` transforms (`limb.py:195-206`) — created under
  `rig.groups.control` with no constraint to `parent`. This is what `reach.py`
  reads today via `arm.py:157`.
- `switch_plug` (`ikFk`, `limb.py:209-211`) and every other attribute on
  `ik_control` (segment scales `limb.py:113-116`, stretch / squash / pole plugs)
- **`fk_controls[i]["matrix"]`** — a control's own local matrix depends only on
  its own TRS channels, not on its offset group. Its `worldMatrix` is
  downstream; its `matrix` is not. This is the FK-side humerus direction,
  gimbal-free and rotate-order-free.
- `pole_control`'s local `translate` channels (its world matrix is downstream)
- `hang_from` in `arm.py:102-105`, including with `limb_lock` driving it:
  `build_limb_lock` constrains `lock_root` to the **socket**, not the collar
  (`systems/limb_lock.py:130`), and reads `chain_root` only at build time for
  `align_to` (`limb_lock.py:129`).

**How to apply next time:** an auto-clavicle driver must be built from animator
*inputs* (the IK control's world matrix, the FK controls' local matrices, the
ikFk switch), never from the solved skeleton. That is also what production
SDK-based auto-clavicles do. Reading the solved upper arm requires either a
duplicated solve rooted upstream or an analytic re-solve, and both then owe
feature parity with stretch / softIk / polePin.
