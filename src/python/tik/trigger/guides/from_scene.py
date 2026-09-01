"""Read the scene's guide joints back into a document (spec 5).

The Maya half of recovery, and deliberately thin: it gathers records and hands
them to :mod:`tik.trigger.core.scene_recovery`, which does the thinking without
importing Maya.

This is the ONLY module that reads ``trg_entry``. Capture, reconcile, build and
the Designer never do -- the document is the authority everywhere except here,
where there is no document yet to be authoritative (spec 4.1).
"""

from __future__ import annotations

from tik.trigger.core import registry
from tik.trigger.core.scene_recovery import SceneModule, document_from_scene
from tik.trigger.maya import tags

from . import nodes
from .snapshot import snapshot


def scene_modules(rendered: list) -> list:
    """One :class:`SceneModule` per instance in ``rendered``.

    The type and side come off any of the instance's joints; the breadcrumb only
    off its root, which is where regenerate stamps it. ``nodes.root_guide``
    resolves the root by asking the registry for the module's declared root
    role, and raises for an unregistered type -- so it is only ever called once
    the type is known-registered; an unknown type simply comes back with
    ``entry=None`` (``document_from_scene`` reports it and skips it).
    """
    seen: dict = {}
    for guide in rendered:
        if guide.instance_id in seen:
            continue
        joints = nodes.guide_nodes(guide.instance_id)
        any_joint = next(iter(joints.values()), None)
        if any_joint is None:
            continue
        meta = any_joint.meta.as_dict()
        module_type = meta.get(tags.MODULE, "")
        root = None
        if module_type and registry.is_module_registered(module_type):
            root = nodes.root_guide(joints, module_type)
        seen[guide.instance_id] = SceneModule(
            instance_id=guide.instance_id,
            module_type=module_type,
            side=meta.get(tags.SIDE, "C"),
            entry=root.meta.get(tags.ENTRY) if root is not None else None,
        )
    return list(seen.values())


def read() -> tuple:
    """``(GuideDocument, RecoveryReport)`` for whatever the scene holds."""
    rendered = snapshot()
    return document_from_scene(scene_modules(rendered), rendered)
