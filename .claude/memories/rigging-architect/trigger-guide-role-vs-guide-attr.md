---
name: trigger-guide-role-vs-guide-attr
description: Adding a role to Module.guides hard-breaks existing .trg imports; guide_attrs degrade gracefully. Guides round-trip full world rotation.
type: repo-fact
---

**What is true:**

- `.trg` import does **not** run `draw_guides`. `GuideScene.import_guide_instances`
  (`guides/scene.py:266-300`) creates one joint per `(role, index)` **present in
  the file**. A role added to `Module.guides` after a file was written is simply
  absent, and `rig.guide(role)` then raises `GuideError`
  (`trigger/maya/rig.py:188-194`) — a hard build failure on every old asset.
  The authoring path is tolerant (`create_guides` -> `draw_guides` ->
  `apply_poses`, `scene.py:73-95`); only the import path is not.
- `guide_attrs` **do** degrade gracefully: the import loop reads
  `module_cls.attrs_for_role(role)` and defaults anything missing from the
  record to `item.default` (`scene.py:282-287`); the draw path creates them in
  `GuideDraft.joint` (`trigger/maya/rig.py:104-107`). They are float-only
  (`core/manifest.py:29-47`).
- Guides round-trip **position + world rotation + rotateOrder**
  (`core/schemas.py:15-25`, `guides/nodes.py:169-176` and `233-243`), and the
  `.trg` record additionally carries `joint_orient` (`guides/format.py:196-207`).
  So a guide can legitimately encode a *direction or a frame*, not just a point.
- `GuideDraft.joint(role, position, ...)` takes **no orientation argument**
  (`trigger/maya/rig.py:67-75`) — `draw_guides` can only place, not orient.

**How to apply next time:** prefer a new guide when the authored thing is
genuinely a *direction or a place* the rigger wants to see and drag; prefer a
`guide_attrs` float when it is a number. If a new role is unavoidable, either
teach `import_guide_instances` to fill declared-but-missing roles from
`draw_guides`, or make the consumer tolerate the absence with a documented
fallback — otherwise every existing `.trg` stops building.
