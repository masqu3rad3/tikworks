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

from typing import Iterable, Optional

from maya import cmds

from tik.trigger.core import registry
from tik.trigger.core.exceptions import NotFoundError
from tik.trigger.core.guide_document import GuideDocument, ModuleEntry
from tik.trigger.core.ordering import dependency_order
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


def _producer_guide(
    entry: ModuleEntry, document: Optional[GuideDocument], slug: str = ""
):
    """The guide joint one copy's root should hang under, or None.

    The DAG is a rendering of the primary input connection, rebuilt every time,
    so the joint hierarchy and the connection graph cannot diverge (spec 4.4).

    ``slug`` says *which copy* is asking: each carries its own primary input,
    so each hangs under its own producer. And the output it names is itself
    qualified -- ``c1_hand`` is the second copy's hand -- so the slug has to
    come off before the role is recognised and go back on before the joint is
    looked up. Without that, ``c1_hand`` matched no layout role, fell back to
    the producer's root, and every consumer of every copy piled onto the
    first copy's root joint.
    """
    if document is None:
        return None
    module_cls = registry.get_module(entry.module_type)
    primary = module_cls.primary_input()
    if primary is None:
        return None
    port = primary.name if primary.shared else module_cls.qualify(slug, primary.name)
    source = entry.inputs.get(port)
    if not source or "." not in source:
        return None
    producer_id, _dot, output = source.rpartition(".")
    producer = document.module(producer_id)
    if producer is None:
        return None
    producer_cls = registry.get_module(producer.module_type)
    out_slug = producer_cls.slug_of(output)
    bare = output[len(out_slug) + 1 :] if out_slug else output
    role = bare if bare in producer_cls.guides.all_roles else producer_cls.guides.root
    found = nodes.guide_nodes(producer_id)
    return found.get((producer_cls.qualify(out_slug, role), 0)) or found.get(
        (producer_cls.qualify(out_slug, producer_cls.guides.root), 0)
    )


def _primary_producer_id(entry: ModuleEntry) -> Optional[str]:
    """The instance id ``entry``'s root should hang under, or None."""
    try:
        module_cls = registry.get_module(entry.module_type)
    except NotFoundError:
        return None  # unregistered: it renders nothing, so it parents nowhere
    primary = module_cls.primary_input()
    if primary is None:
        return None
    source = entry.inputs.get(primary.name)
    if not source or "." not in source:
        return None
    return source.rpartition(".")[0] or None


def reparent_consumers(document: GuideDocument, drawn_ids: Iterable[str]) -> None:
    """Hang already-drawn consumers of ``drawn_ids`` back under their producer.

    The other half of "the DAG is a rendering of the primary input connection"
    (spec 4.4): ``regenerate`` renders that connection for the module it is
    drawing, but a module is free to be drawn before its producer exists, and
    ``regenerate`` evicts foreign children to the holder before it rebuilds. So
    without this, drawing the base either strands an arm that was hanging
    correctly or leaves one that was drawn first parked at the holder for good
    -- reported out of date by a marker no Draw of that arm could clear.

    A re-parent, deliberately, not a redraw: the consumer's joints keep their
    identity and (``set_parent`` compensating) their world poses, so drawing
    one module never rebuilds another behind the rigger's back. Only modules
    that are *already drawn* are touched; an undrawn one has nothing to strand.
    """
    drawn = set(drawn_ids)
    for entry in document.modules:
        if entry.instance_id in drawn:
            continue  # just regenerated: it parented itself
        if _primary_producer_id(entry) not in drawn:
            continue
        module_cls = registry.get_module(entry.module_type)
        root = nodes.guide_nodes(entry.instance_id).get((module_cls.guides.root, 0))
        if root is None:
            continue  # not drawn
        target = _producer_guide(entry, document)
        if target is None:
            continue
        # By uuid: two wrappers of one node are not equal, and re-parenting a
        # joint that is already there would recompute its transform for nothing.
        current = root.parent
        if current is None or current.uuid != target.uuid:
            root.parent = target


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

        # One parent per copy: each copy carries its own primary input, so
        # each hangs under its own producer rather than all of them under
        # whatever the first copy happens to be wired to.
        parents = {
            slug: _producer_guide(entry, document, slug) for slug in module.copy_slugs()
        }
        draft = GuideDraft(module, holder, parents.get(""), parents=parents)
        module.draw_all_guides(draft)
        created = draft.created
        for record in entry.guides:
            joint = created.get(record.pair)
            if joint is None:
                continue
            # radius, colour and orient are not a pose (spec 4.3 step 5), so
            # an authored one applies even to an unposed guide -- before the
            # posed guard below. But each is Optional exactly like position:
            # None means "never authored", so draw_guides' own choice (e.g.
            # the module's per-side colour from create_guide_joint) must be
            # left alone rather than stamped over with a stale default.
            if record.radius is not None:
                joint.radius = record.radius
            if record.color is not None:
                joint.color = record.color
            if record.joint_orient is not None:
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
    """Entries with producers before consumers, so root parenting resolves.

    A cyclic connection is broken rather than reported: regenerate has to draw
    every module even when the document is inconsistent.
    """
    by_id = {entry.instance_id: entry for entry in document.modules}

    def producers(entry: ModuleEntry) -> list[ModuleEntry]:
        found = []
        for source in entry.inputs.values():
            if source and "." in source:
                producer = by_id.get(source.rpartition(".")[0])
                if producer is not None and producer is not entry:
                    found.append(producer)
        return found

    return dependency_order(
        document.modules, producers, lambda entry: entry.instance_id
    )
