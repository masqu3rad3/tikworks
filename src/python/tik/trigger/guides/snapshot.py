"""Scan the scene's guide joints into pure ``RenderedGuide`` records.

The Maya half of reconcile's input. Everything Maya-shaped stops here; what
comes out is plain data :mod:`tik.trigger.core.reconcile` can compare without
importing Maya.
"""

from __future__ import annotations

from typing import Optional

from maya import cmds

import tik.maya as tm
from tik.trigger.core.manifest import instance_key
from tik.trigger.core.reconcile import RenderedGuide
from tik.trigger.maya import tags


def _guide_triple(node) -> tuple:
    """``(instance_id, role, index)`` for a guide joint."""
    return (
        node.meta[tags.INSTANCE],
        node.meta.get(tags.ROLE, ""),
        int(node.meta.get(tags.INDEX, 0)),
    )


def _guide_attrs(node) -> dict:
    """User-defined numeric attributes on a guide, minus the meta bookkeeping."""
    found = {}
    for name in cmds.listAttr(node.long_name, userDefined=True) or []:
        if name.startswith(tm.META_PREFIX):
            continue
        try:
            found[name] = float(cmds.getAttr(f"{node.long_name}.{name}"))
        except (ValueError, RuntimeError, TypeError):
            continue  # compound or non-numeric: not a guide attr
    return found


def snapshot() -> list:
    """Every tagged guide joint in the scene, as pure records."""
    found = []
    # cmds rather than tik.maya: one attribute-qualified ls finds every tagged
    # joint without walking the DAG. This runs on every refresh.
    for name in (
        cmds.ls(
            f"*.{tm.META_PREFIX}{tags.KIND}", long=True, objectsOnly=True, type="joint"
        )
        or []
    ):
        node = tm.resolve(name)
        data = node.meta.as_dict()
        if data.get(tags.KIND) != tags.GUIDE or tags.INSTANCE not in data:
            continue
        parent = node.parent
        parent_triple: Optional[tuple] = None
        if parent is not None and parent.meta.get(tags.KIND) == tags.GUIDE:
            parent_triple = _guide_triple(parent)
        found.append(
            RenderedGuide(
                instance_id=data[tags.INSTANCE],
                role=data.get(tags.ROLE, ""),
                index=int(data.get(tags.INDEX, 0)),
                node=node.long_name,
                position=tuple(
                    cmds.xform(
                        node.long_name, query=True, worldSpace=True, translation=True
                    )
                ),
                rotation=tuple(
                    cmds.xform(
                        node.long_name, query=True, worldSpace=True, rotation=True
                    )
                ),
                rotate_order=int(cmds.getAttr(f"{node.long_name}.rotateOrder")),
                attrs=_guide_attrs(node),
                parent=parent_triple,
                key=(
                    instance_key(data[tags.NAME], data.get(tags.SIDE, "C"))
                    if data.get(tags.NAME)
                    else ""
                ),
            )
        )
    return found
