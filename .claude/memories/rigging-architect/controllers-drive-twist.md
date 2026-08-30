---
name: controllers-drive-twist
description: Twist (and behavior generally) must be driven by controller rotations, not dedicated attrs — user rejected attr-first recommendation
type: mistake
---

**What happened:** In the ribbon redesign (2026-08-29), the recommendation framed a dedicated `twist` float attr as the primary twist interface, with controller rotations "wired in". The user rejected this: "Animators will ALWAYS ask for less controls with MORE features" — twist must come from rotating the controllers themselves (the Karoly method); attrs are acceptable only as offsets/multipliers on top.

**Why:** The controller transform is the animation interface. The source methodology (karolyart pure-math ribbon) made this exact choice deliberately; deviating from a proven source's interface design needs a concrete reason, not convenience.

**How to apply next time:** Default rig interfaces to transform-driven behavior. Extra channel-box attrs = secondary offsets only. When adapting a published technique, preserve its animator-facing choices unless the user asks otherwise. Also: float-purity matters — IK/FK twist blending must lerp float channels (never pass through a matrix) to keep unbounded twist. See [[pure-math-ribbon-research]].
