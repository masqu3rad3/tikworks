---
name: tik-maya-layering-rule
description: The "no raw cmds/OpenMaya" rule applies only OUTSIDE tik.maya; internals of tik.maya may and should use cmds/OpenMaya directly for speed
type: repo-fact
---

# tik.maya layering nuance (user-confirmed 2026-08-29)

- The repo rule "consume tik.maya wrappers, never raw cmds/OpenMaya/pymel" applies ONLY to
  code outside tik.maya: tik.trigger modules/actions, tools, tests-as-tools.
- Code INSIDE src/python/tik/maya/** (types, roles, constructs — ribbon.py included) is
  explicitly ALLOWED to call maya.cmds and maya.api.OpenMaya directly. Priority there is
  efficiency; other tik.maya modules do the same (plug.py, matrix_constraint.py, transform.py).
- Therefore: raw cmds inside constructs/ribbon.py is idiomatic, NOT a violation. Do not
  report it as one.
- Design implication for new constructs: internals may use cmds/OpenMaya (prefer API-level
  math where faster, e.g. MMatrix offset computation as in matrix_constraint.py:98-101);
  the PUBLIC API must stay idiomatic tik.maya (Types/Roles/Constructs, Plug operators,
  @undo decorators, resolve()-based node handling).
