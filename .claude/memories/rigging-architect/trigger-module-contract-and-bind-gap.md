---
name: trigger-module-contract-and-bind-gap
description: What ctx offers a tik.trigger module today, where module groups are created, and the fact that nothing builds a single bind-joint hierarchy
type: repo-fact
---

**Verified 2026-08-30 (D:\dev\tikworks):**

Build ctx = `MayaBuildContext` (src/python/tik/trigger/backends/maya/context.py:75-183).
Surface: `.module .instance .side .side_mult .rig_root .groups .outputs .attachments
.controllers .deform_joints`; methods `guide(role, index=0)` `guides(role)`
`name(*tokens, suffix=)` `controller(name, shape=, size=, parent=, color=, match=)`
`deform_joint(node)` `output(name, node)` `attach(input_name, node)`.
Groups are created in `_create_groups` (context.py:92-117), NOT by the module:
`<side>_<name>_grp` > `_scale_grp` > `_controllers_grp`, plus `_nonScale_grp`
(inheritsTransform False), `_joints_grp`, `_rig_grp`. Vis bools live on the limb group
(:101-104); all six groups locked (:105-106). Dataclass = `RigGroups`
(core/context.py:13-22) with fields limb/scale/nonscale/controllers/joints/rig.

**The gap that matters:** `ctx.deform_joint()` (context.py:170-173) only writes a
`trg_kind=deform` tag and appends to a list. NOTHING consumes `ctx.deform_joints` — no
skeleton assembly, no reparenting. Module-to-module connection is
`Builder._connect_all` (core/builder.py:96-127) -> `MayaBackend.connect`
(backends/maya/backend.py:485-489), which only does
`MatrixConstraint.create(source_output, ctx.attachments[input])`. So a single
bind/deform joint hierarchy across connected modules does not exist and must be designed
(post-build reparent pass keyed on producer output -> consumer bind root, or a
`ctx.bind_joint(parent_input=...)` declaration).

**How to apply next time:** don't assume a bind skeleton exists; modules currently parent
bind joints under their own `_joints_grp` (base.py:30-32, fkchain.py:40-42, arm.py:54-66).
