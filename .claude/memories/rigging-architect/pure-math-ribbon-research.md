---
name: pure-math-ribbon-research
description: Verified findings from researching the karolyart pure-math ribbon technique (2026-08-29) for replacing tik.maya Ribbon
type: repo-fact
---

# Pure-math ribbon research (2026-08-29)

## Source pages (both fetched successfully, cached content summarized in session)
- https://www.karolyart.com/works/breakdowns/pure-math-ribbon-rig (primary)
- https://www.karolyart.com/works/breakdowns/hybrid-matrix-ribbon-rig (prior iteration, NURBS + uvPin + pointMatrixMult)

## Technique core (from the pages)
- Pipeline: Controller -> math nodes -> joint. No NURBS, no follicles, no skinCluster.
- Nodes: blendMatrix (pos/scale blend), aimMatrix (joint orientation), parentMatrix
  (weighted multi-influence sum, normalizing), pickMatrix (strip rotation), plusMinusAverage
  (float twist), pointMatrixMult.
- Twist = float-channel linear interpolation (plusMinusAverage), NOT quaternion — avoids
  the 180-degree shortest-path flip; matrix-derived rotations still flip past 180 (author's
  open limitation).
- Mid-joint weights quoted: primary 1.0, neighbors 0.3 each => normalized 0.625/0.1875/0.1875.
  Compare exact uniform cubic B-spline basis at a knot: 4/6, 1/6, 1/6 (0.667/0.167/0.167).
  His weights are an eyeballed approximation of the degree-3 basis.
- Perf numbers from page: legacy ~1400us, hybrid ~1200us, pure math ~500us per ribbon;
  at 100x: 6800us vs 2700us.

## Repo facts verified (file:line)
- Current ribbon: src/python/tik/maya/constructs/ribbon.py — NURBS plane (raw cmds.nurbsPlane:113,
  rebuildSurface:122), follicles (createNode follicle:199), skinCluster maxInfluences=2 (:263),
  aimConstraint plugs (:161-180), Measure ratio -> scaleX stretch with Plug operator math (:273-281).
- Only consumer: src/python/tik/trigger/modules/arm/arm.py (:125-142).
- blendMatrix already used: constructs/ikfk_chain.py:107, constructs/matrix_switch.py:77.
- wtAddMatrix used: constructs/matrix_constraint.py:83. multMatrix/decompose/compose/inverse there too.
- NOT used anywhere in repo: aimMatrix, pickMatrix, parentMatrix, uvPin, quatToEuler,
  offsetParentMatrix (grep over src/python returned zero hits).
- Plug operator overloads (core/plug.py:764+) build scalar/vector math node networks (+ - * / ** %);
  Maya-version-aware node names in core/constants.py (NodeNames, uses_native_math_nodes >= 2025).
- scene.create_node handles arbitrary node types; ensure_plugin("matrixNodes") pattern at
  matrix_constraint.py:126.
- parentMatrix is a real Maya 2024+ node (Autodesk node docs: blends targets while normalizing
  weights; attrs inputMatrix/target[i].targetMatrix/weight/offsetMatrix).
