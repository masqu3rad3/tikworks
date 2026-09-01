"""Regenerate: rebuild one module's guide joints from its document entry.

Scoped to a single module, never global -- if changing one field redrew the
whole character, lockstep would not be viable.

The step that matters is restoring stored poses (spec 4.3 step 4). A guide the
document has a pose for goes back exactly where the rigger put it; a guide it
has never seen posed lands wherever ``draw_guides`` puts it, never at the
origin. That is the difference between a tool that keeps up with you and one
that throws your work away.
"""

from __future__ import annotations

from typing import Optional

from maya import cmds
from tik.trigger.core import registry
from tik.trigger.core.guide_document import GuideDocument, ModuleEntry
from tik.trigger.maya import tags
from tik.trigger.maya.rig import GuideDraft

from . import nodes
from .capture import regenerating


def _module_for(entry: ModuleEntry):
    """Rebuild the ``Module`` object for ``entry``, keeping its identity."""
    module_cls = registry.get_module(entry.module_type)
    return module_cls(
        instance_id=entry.instance_id,
        name=entry.name,
        side=entry.side,
        settings=dict(entry.settings),
    )


def _producer_guide(entry: ModuleEntry, document: Optional[GuideDocument]):
    """The guide joint this module's root should hang under, or None.

    The DAG is a rendering of the primary input connection, rebuilt every time,
    so the joint hierarchy and the connection graph cannot diverge (spec 4.4).
    """
    if document is None:
        return None
    module_cls = registry.get_module(entry.module_type)
    primary = module_cls.primary_input()
    if primary is None:
        return None
    source = entry.inputs.get(primary.name)
    if not source or "." not in source:
        return None
    producer_id, _dot, output = source.rpartition(".")
    producer = document.module(producer_id)
    if producer is None:
        return None
    producer_cls = registry.get_module(producer.module_type)
    role = output if output in producer_cls.guides.all_roles else producer_cls.guides.root
    found = nodes.guide_nodes(producer_id)
    return found.get((role, 0)) or found.get((producer_cls.guides.root, 0))


def _stamp_breadcrumb(entry: ModuleEntry, created: dict) -> None:
    """Park the module's identity on its root guide, for Snapshot to find.

    WRITTEN here, READ only by Snapshot (spec 4.1). Capture, reconcile, build,
    the Designer and the Builder never consult it, so the document stays the
    sole authority and a stale or hand-edited tag can corrupt nothing.

    Poses are deliberately absent (spec 4.2): a guide moves when a rigger drags
    it, with no document write and so no regenerate to refresh this tag. What is
    kept here changes *only* through a document write, and every document write
    ends in a regenerate -- so the breadcrumb can never be staler than the joints
    it sits on.
    """
    root = nodes.root_guide(created, entry.module_type)
    if root is None:
        return
    data = entry.to_dict()
    data.pop("guides", None)
    root.meta[tags.ENTRY] = data


def regenerate(entry: ModuleEntry, document: Optional[GuideDocument] = None) -> dict:
    """Rebuild ``entry``'s guide joints. Returns ``{(role, index): joint}``."""
    module = _module_for(entry)
    holder = nodes.holder()
    with nodes.undo_chunk(f"Trigger regenerate: {entry.name}"), regenerating():
        existing = nodes.guide_nodes(entry.instance_id)
        for node in existing.values():
            # keep other instances' guides that hang under ours
            for child in node.children:
                if child.meta.get(tags.INSTANCE) not in (None, entry.instance_id):
                    child.parent = holder
        if existing:
            cmds.delete([node.long_name for node in existing.values() if node.exists()])

        draft = GuideDraft(module, holder, _producer_guide(entry, document))
        module.draw_guides(draft)
        created = draft.created
        for record in entry.guides:
            joint = created.get(record.pair)
            if joint is None:
                continue
            # radius, colour and orient are not a pose (spec 4.3 step 5) -- an
            # unposed guide still has them, so they land before the posed guard.
            joint.radius = record.radius
            joint.color = record.color
            joint.joint_orient = record.joint_orient
            for name, value in record.attrs.items():
                if joint.has_attr(name):
                    joint[name].value = value
            if not record.posed:
                continue  # unposed: leave it where draw_guides put it
            # The order must be set before the rotation: xform interprets the
            # euler triple in the node's current rotateOrder.
            cmds.setAttr(f"{joint.long_name}.rotateOrder", record.rotate_order)
            cmds.xform(joint.long_name, worldSpace=True, translation=record.position)
            if record.rotation is not None:
                cmds.xform(joint.long_name, worldSpace=True, rotation=record.rotation)
        # after the poses land, so a guide rig can take over the channels
        module.wire_guides(created)
        _stamp_breadcrumb(entry, created)
    return created


def regenerate_all(document: GuideDocument) -> None:
    """Rebuild every module, producers first so roots find their parent guide."""
    for entry in ordered(document):
        regenerate(entry, document)


def ordered(document: GuideDocument) -> list:
    """Entries with producers before consumers, so root parenting resolves."""
    by_id = {entry.instance_id: entry for entry in document.modules}
    result: list = []
    done: set = set()
    visiting: set = set()

    def visit(entry: ModuleEntry) -> None:
        if entry.instance_id in done or entry.instance_id in visiting:
            return  # a cycle: break it rather than recursing forever
        visiting.add(entry.instance_id)
        for source in entry.inputs.values():
            if source and "." in source:
                producer = by_id.get(source.rpartition(".")[0])
                if producer is not None and producer is not entry:
                    visit(producer)
        visiting.discard(entry.instance_id)
        done.add(entry.instance_id)
        result.append(entry)

    for entry in document.modules:
        visit(entry)
    return result
