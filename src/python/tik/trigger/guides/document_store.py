"""Read and write the whole ``GuideDocument`` in the Maya scene.

Module entries live one per document node (:mod:`.module_node`); the scene-node
groups and the Designer's graph layout live on the guide holder, because they
belong to the document as a whole rather than to any one module.

Everything here is a plain scene write, so Maya's undo covers the document the
same way it covers a joint move -- which is the reason the working copy lives in
the scene at all rather than in Python memory.
"""

from __future__ import annotations

from typing import Optional

import tik.maya as tm
from maya import cmds
from tik.trigger.core.guide_document import GuideDocument, ModuleEntry, SceneGroup
from tik.trigger.maya import tags

from . import module_node, nodes


def read_document() -> GuideDocument:
    """Assemble the document from the scene."""
    document = GuideDocument(
        modules=[module_node.read(node) for node in module_node.find_all()]
    )
    document.modules.sort(key=lambda entry: entry.name)
    if cmds.objExists(tags.GUIDE_HOLDER):
        stored = dict(tm.Transform(tags.GUIDE_HOLDER).meta.get(tags.DOCUMENT, {}) or {})
        document.scene_groups = [
            SceneGroup.from_dict(item) for item in stored.get("scene_groups", [])
        ]
        document.positions = {
            key: list(value) for key, value in (stored.get("positions") or {}).items()
        }
        document.collapse = {
            key: int(value) for key, value in (stored.get("collapse") or {}).items()
        }
    return document


def write_document(document: GuideDocument, modules: Optional[dict] = None) -> None:
    """Store ``document``, removing module nodes it no longer contains.

    Args:
        document: The document to store.
        modules: ``{instance_id: Module}`` for entries whose scalar settings
            should be re-mirrored as attributes. Entries absent from it keep the
            attributes they already have.
    """
    modules = modules or {}
    with nodes.undo_chunk("Trigger write guide document"):
        wanted = {entry.instance_id for entry in document.modules}
        for node in module_node.find_all():
            if node.meta.get(tags.INSTANCE) not in wanted:
                cmds.delete(node.long_name)
        for entry in document.modules:
            write_entry(entry, modules.get(entry.instance_id))
        nodes.holder().meta[tags.DOCUMENT] = {
            "scene_groups": [group.to_dict() for group in document.scene_groups],
            "positions": {key: list(value) for key, value in document.positions.items()},
            "collapse": dict(document.collapse),
        }


def read_entry(instance_id: str) -> Optional[ModuleEntry]:
    node = module_node.find(instance_id)
    return module_node.read(node) if node is not None else None


def write_entry(entry: ModuleEntry, module=None) -> None:
    """Create or update one module's document node."""
    node = module_node.find(entry.instance_id)
    if node is None:
        module_node.create(entry, module)
    else:
        module_node.write(node, entry, module)


def remove_entry(instance_id: str) -> None:
    module_node.remove(instance_id)


def read_stamp() -> str:
    """The id of the session whose guides the scene holds, or ``""``."""
    if not cmds.objExists(tags.GUIDE_HOLDER):
        return ""
    return str(tm.Transform(tags.GUIDE_HOLDER).meta.get(tags.SESSION, "") or "")


def write_stamp(session_id: str) -> None:
    """Record which session owns the guides currently in the scene."""
    nodes.holder().meta[tags.SESSION] = str(session_id)
