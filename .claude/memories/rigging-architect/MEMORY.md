# rigging-architect memory index

One line per memory file in this directory. Read the linked file before relying on a lesson.

- [Pure-math ribbon research](pure-math-ribbon-research.md) — karolyart technique verified 2026-08-29: matrix blend T/S + aimMatrix orient + float twist; B-spline weights; node coverage in repo
- [tik.maya layering rule](tik-maya-layering-rule.md) — raw cmds/OpenMaya idiomatic INSIDE tik.maya; wrapper rule binds only outside consumers
- [controllers drive twist](controllers-drive-twist.md) — MISTAKE: attr-first twist rejected; controller rotations are the interface, attrs = offsets only; keep IK/FK twist blend float-pure
- [aim up frame, twist-subtracted](aim-up-frame-twist-subtracted.md) — static up flips; up = Rx(-wired_twist) x pinned start; Karoly has no secondary; aim at next pick to avoid cycles
- [twist wrap & final joint hookup](twist-wrap-final-joint-hookup.md) — wrap breaks interpolation only, not pose; flat joint = decompose swing + add twist float to rotateX (verified); Karoly uses OPM, not live channels
- [Soft IK & stretch math](soft-ik-and-stretch-math.md) — legacy exponential soft-IK formula (C1-continuous), additive uniform-strain stretch, initialDistance-as-plug segment scaling
- [Trigger module contract & bind gap](trigger-module-contract-and-bind-gap.md) — what ctx offers, where groups are made, and that nothing assembles a single bind skeleton
- [Maya 2024+ math nodes & ramp shapes](maya-2024-math-and-ramp-shapes.md) — atan2/smoothStep core since 2024; remapValue "smooth" is raised cosine (C1 at both ends), "spline" is not; multi-point ramp is kink-free by construction
- [Auto-collar two zeros](reach-auto-collar-two-zeros.md) — MISTAKE: reach.py ramp zero and aim zero are unrelated, so the collar dips before it lifts; blend-toward-aim-frame can never saturate
- [Guide role vs guide_attr](trigger-guide-role-vs-guide-attr.md) — a new guide role hard-breaks old .trg imports; guide_attrs default in gracefully; guides carry full world rotation
- [Arm collar cycle map](arm-collar-cycle-upstream-plugs.md) — what in limb.py is upstream vs downstream of the auto-collar; FK control local `matrix` is safe, worldMatrix is not
