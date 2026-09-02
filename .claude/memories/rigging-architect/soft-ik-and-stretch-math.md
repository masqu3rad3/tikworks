---
name: soft-ik-and-stretch-math
description: Verified soft-IK exponential formula + additive stretch distribution as built in the legacy trigger repo (tools.make_stretchy_ik), with C0/C1 proof and node mapping
type: methodology
---

**What is true (read D:\dev\trigger\python\trigger\library\tools.py:515-757, 2026-08-30):**

Soft IK. L = sum of per-segment `initialDistance` plugs; ds = softIK + 0.001; da = L - ds;
d = |end - start| / globalScaleX.

    f(d) = d                                for d <= da
    f(d) = L - ds * e^(-(d - da)/ds)        for d >  da

C0: f(da) = L - ds = da. C1: f'(d>da) = e^(-(d-da)/ds) -> 1 at d = da, matching the identity
branch. lim d->inf f = L (asymptotic, never fully straight -> no pop).
Cannot be made branchless: min() picks wrong below da, max() picks wrong above. Keep one
`condition` node. The +0.001 epsilon is the softIK==0 guard (exponent underflows -> hard stop).
Node chain: tools.py:637 (sum) 640 (eps) 642 (da) 653-661 (d) 662-669 (formula)
671-686 (two conditions) 688 (-> end_loc.tx, a child of a root locator aimed at the goal).

The soft goal is a SCALAR distance along the root->target aim axis. The IK handle is
constrained to a blend between the raw controller (weight = `stretch`) and that soft
position (weight = 1 - stretch), so soft IK and stretch compose: the gap the chain must
stretch is exactly d - f(d).

Stretch distribution (tools.py:709-746): gap_local = |end_loc - soft_blend| / globalScale;
each joint gets initial_i + gap_local * (initial_i / L) -> uniform strain across segments.
Stretch limit = clamp(max = initial_i + stretchLimit) — ABSOLUTE units, not a percentage
despite the 0..1000/default-100 attr range (legacy quirk; fix in any rewrite).
Squash branch uses ratio = ctrl_distance / L, NOT divided by global scale — breaks under
rig scale (legacy bug).

Per-segment scaling trick: drive each joint's `initialDistance` attr from
static_rest_length * scaleAttr. Because initialDistance feeds L, the shares, the squash and
the limit, one multiply cleanly rescales a bone through the whole soft-IK+stretch network.

**How to apply next time:** reuse the formula verbatim for any soft IK; use e =
2.718281828459045 (legacy hardcodes 2.71828), Maya's native `power` node, and keep
initialDistance as a live plug so segment scaling is free.
