# Plan C — Arm Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the module contract on a real limb: an arm with collar, IK/FK blend, pole vector, FK/IK visibility switching and ribbon segments, attached to `base`.

**Architecture:** `modules/arm/arm.py` composes `tm.IkFkChain`, `tm.Ribbon`, `tm.MatrixConstraint` and `ctx.controller` — no raw `cmds`. Everything the framework owns (groups, naming, tagging, attachment) stays in the backend.

**Spec:** `docs/superpowers/specs/2026-08-28-trigger-rebuild-design.md` §7, §10 (C)

## Tasks

- [x] **Task 1:** `Arm(Module)` manifest: `Guides("collar","shoulder","elbow","hand")`, plugs `("collar","hand")`, sockets `("root",)`, fields `ribbon_joints`, `ribbon_controllers`, `controller_size`, `ik_solver`, `stretchy`; `draw_guides` chained defaults mirrored by `ctx.side_mult`.
- [x] **Task 2:** `build(ctx)`: collar joint + rig chain, hand deform joint, socket + collar controller, switch controller carrying `ikFk`, `IkFkChain` (group constrained to collar), FK controllers (visibility ← `fk_visibility`), IK hand + pole controllers (visibility ← `ik_visibility`), two ribbons pinned to the rig joints, deform joints registered, plugs `collar`/`hand`.
- [x] **Task 3:** `tests/integration/trigger/test_arm_trigger.py`: node inventory, attachment to base, IK/FK switch behaviour, right-side mirror, ribbon stretch + undo.
- [x] **Task 4:** Full suite green, commit `feat(tik.trigger): arm module`.
