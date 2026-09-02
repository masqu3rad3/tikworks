---
name: reach-auto-collar-two-zeros
description: MISTAKE - systems/reach.py has two unrelated zeros, so the collar dips before it lifts; and blend-toward-an-aim-frame can never saturate
type: mistake
---

**What happened:** `systems/reach.py` drives the collar with
`MatrixBlend(rest, AimFrame(rest -> scaled aim point), Remap(AngleBetween(...)))`.
Riggers reported the collar bending *down* before lifting when the arm rises.

**Why (measured in a live Maya session by rebuilding reach.py's network on a
bare rig: A-pose guides 30 deg below the socket X, defaults vertical =
horizontal = 0.5, start 0, end 90, interp smooth):**

1. **Two different zeros.** The ramp's zero is the *arm's* bind direction
   (`reach.py:84`); the aim frame's zero is the *collar's* rest orientation.
   They are unrelated directions. Between them the weight grows while the aim
   delta is still negative, so the dip deepens as the arm rises. Measured collar
   delta: -0.93 deg at bind, worst -1.17 deg at armElev -20, back through zero
   only at armElev 0 (T-pose), then it lifts. With a realistic +12 deg elevated
   clavicle rest the dip reaches -3.09 deg and does not return to zero until
   armElev **+23**. The effective neutral is emergent, not authorable.
2. **Bind pose is not reproduced (a plain bug).** `rest_direction` is sampled
   from the RAW probe (`reach.py:84`) but the ramp's input is the SCALED vector
   (`reach.py:98`). Error at bind = `phi - atan(vertical * tan phi)`; for a
   30 deg A-pose at vertical 0.5 that is exactly **13.90 deg**, weight 0.058,
   collar already off its bind pose. Vanishes only at vertical = horizontal = 1.
3. **The unsigned `angleBetween` makes the ramp V-shaped** with its vertex at
   `atan(tan(phi_bind) / vertical)` — measured minimum at armElev -50, not at
   the bind pose -30 — so arm-down re-engages the automation on the wrong side
   with the same limits as arm-up. Up and down cannot have separate limits.
4. **The end angle saturates the WEIGHT, not the OUTPUT.** Past full weight the
   collar simply tracks the arm 1:1 forever — measured 139 deg of collar
   rotation at 120 deg of arm elevation. "Stop at the limit" is structurally
   impossible in a blend-toward-an-aim-frame model, whatever curve you put on
   the weight. Anatomy wants roughly 15 deg of clavicular elevation for 180 deg
   of humeral elevation, i.e. a gain near 0.1, not 1.0.

**How to apply next time:** any auto-follow driver needs ONE authored zero, a
SIGNED input, and an output that is authored degrees — not a fraction of a full
aim. Drive the helper group's rotate channels from a `remapValue`; do not blend
toward an aim frame. And whenever a "rest" value is captured in Python, capture
it from the *same plug the live network reads*.
