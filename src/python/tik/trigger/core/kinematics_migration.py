"""Translate a pre-schema-7 ``kinematics`` scope into explicit instance ids.

The old action took *root names* and pulled each root's whole subtree; the new
one takes exactly the instance ids it builds. Both approximations this module
makes are deliberate, and both are reported rather than hidden:

* a root name matched either a module's name -- side-less, so ``"arm"``
  selected both ``L_arm`` and ``R_arm`` -- **or** a root guide *joint* name
  such as ``L_arm_root_guide``. Only the first is resolvable without a scene.
* the old subtree walk followed the scene DAG. The document has no DAG, so the
  walk here follows module inputs, which ``regenerate`` derives the DAG from.
  The two agree unless somebody reparented guides without reconnecting them.

Anything that does not resolve is preserved in ``legacy_roots`` for
``Session.validate`` to report. It is never silently dropped: a root that
quietly resolved to nothing would turn a session that builds a rig today into
one that builds an empty scene.
"""

from __future__ import annotations

from typing import Iterable

from .schemas import split_source

KINEMATICS = "kinematics"


def _children_of(instance_id: str, entries: list) -> list:
    """Entries with an input naming ``instance_id``."""
    found = []
    for entry in entries:
        for source in entry.inputs.values():
            key, _output = split_source(source)
            if key == instance_id:
                found.append(entry)
                break
    return found


def _subtree(roots: Iterable, entries: list) -> list:
    """Ids of ``roots`` plus everything reachable from them through inputs."""
    wanted = {entry.instance_id for entry in roots}
    changed = True
    while changed:
        changed = False
        for instance_id in list(wanted):
            for child in _children_of(instance_id, entries):
                if child.instance_id not in wanted:
                    wanted.add(child.instance_id)
                    changed = True
    return [entry.instance_id for entry in entries if entry.instance_id in wanted]


def resolve_roots(roots: list, entries: list) -> tuple:
    """Return ``(instance ids, unresolved root names)``.

    An empty ``roots`` is the old "build everything", so every module comes
    back.
    """
    if not roots:
        return [entry.instance_id for entry in entries], []
    resolved, unresolved = [], []
    for name in roots:
        matched = [
            entry for entry in entries if entry.name == name or entry.key == name
        ]
        if matched:
            resolved.extend(matched)
        else:
            unresolved.append(name)
    return _subtree(resolved, entries), unresolved


def migrate_kinematics(actions: list, guides) -> None:
    """Rewrite every ``kinematics`` node's scope in place, depth first."""
    entries = list(getattr(guides, "modules", []))
    for node in actions:
        if node.type == KINEMATICS and "guide_roots" in node.settings:
            roots = list(node.settings.pop("guide_roots") or [])
            modules, unresolved = resolve_roots(roots, entries)
            node.settings["modules"] = modules
            if unresolved:
                node.settings["legacy_roots"] = unresolved
        migrate_kinematics(node.children, guides)
