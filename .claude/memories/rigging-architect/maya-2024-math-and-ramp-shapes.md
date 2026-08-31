---
name: maya-2024-math-and-ramp-shapes
description: Maya 2024+ core math nodes (atan2/smoothStep/clampRange/normalize/acos), and the MEASURED shapes of remapValue's interpolation enum
type: repo-fact
---

**What is true** (measured in a live Maya 2027 session, 2026-08-31; the node set
shipped in Maya **2024**, which is the repo's floor, so all of this is usable):

Core, no plugin, no third party: `atan2 acos asin atan cos sin tan absolute
negate power max min sum subtract multiply divide average lerp clampRange
smoothStep normalize length dotProduct crossProduct determinant modulo floor
ceil round columnFromMatrix rowFromMatrix axisFromMatrix translationFromMatrix
rotationFromMatrix scaleFromMatrix multiplyPointByMatrix multiplyVectorByMatrix`.
Absent: `sign`, `slerp`, `dot`, `cross`, `normalizeVector`, `angleBetweenVectors`,
`floatMath`, `floatCorrect`. `pointMatrixMult` is gone in 2027 (use
`multiplyPointByMatrix`). `quatToEuler` / `quatProd` / `quatNormalize` /
`axisAngleToQuat` are still `quatNodes`; `inverseMatrix` is still `matrixNodes`;
`decomposeMatrix` is CORE in 2027.

`atan2`: `input1` = y, `input2` = x, `output` is a **doubleAngle** (getAttr
returns degrees). `atan2(1,1)=45`, `atan2(-1,-1)=-135`, `atan2(0,0)=0` (no NaN).
Wiring it into a plain `double` (e.g. `remapValue.inputValue`) auto-inserts a
`unitConversion` with factor 57.2958, and the trip back out to a `rotate`
channel inserts the inverse — the arithmetic stays in degrees end to end and is
correct. Two extra unitConversion nodes per strand; no trap.

`smoothStep` node = cubic Hermite `3t^2-2t^3` between `leftEdge` / `rightEdge`,
clamped outside. **`leftEdge > rightEdge` collapses the output to 0** — a
descending ramp needs a negated input, not swapped edges.

**`remapValue` interpolation enum, measured on a 2-point 0..1 ramp:**

| interp | shape | slope at x=0 | slope at x=1 |
|---|---|---|---|
| linear | t | 1 | 1 |
| smooth | **raised cosine** `(1-cos(pi t))/2` | **0** | **0** |
| spline | Catmull-Rom-ish | **~0.5** | **~0.5** |

Only `smooth` is C1 where the ramp meets its own clamp. `spline` visibly kinks
at saturation. `remapValue` **clamps** outside `[inputMin, inputMax]`, it never
extrapolates (verified out to 2x the range).

**How to apply next time:** for any "smooth, saturating, no hard hit at the
limits" driver, use ONE `remapValue` with a multi-point ramp and `interp=smooth`.
Because raised cosine has zero slope at *every* ramp point, a 3-point ramp
(lower to 0, neutral to the normalized zero position, upper to 1) is C1 at the
neutral crossing AND at both limits for **any** asymmetric pair of limits and
output magnitudes — no slope matching needed. The cost is a dead zone at the
neutral, which is anatomically the scapular "setting phase" and usually fine.
`tm.Remap` today writes only ramp indices 0 and 1 (`constructs/remap.py:120-124`)
— multi-point support is a tik.maya addition.
