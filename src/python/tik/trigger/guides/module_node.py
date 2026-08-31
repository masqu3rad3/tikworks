"""Module document nodes: one scene node per module instance.

This node is the module's durable identity. Scalar settings live on it as real
Maya attributes, so the channel box and the Designer's two-way bindings work
against it exactly as they used to work against the root guide joint; the rest
of the :class:`~tik.trigger.core.guide_document.ModuleEntry` is a meta dict.

Guide joints hold no structural data any more, which is the point: deleting
them -- including the root -- can no longer destroy a module.
"""

from __future__ import annotations

from typing import Optional

import tik.maya as tm
from maya import cmds
from tik.maya import attribute
from tik.trigger.core.guide_document import ModuleEntry
from tik.trigger.maya import tags

MODULE_NODES_GRP = "trigger_modules_grp"

#: Field kinds with no sensible single-attribute form; they live only in meta.
_NON_SCALAR = ("list", "dict", "vector", "table")


def holder() -> tm.Transform:
    """The group every module document node hangs under."""
    if cmds.objExists(MODULE_NODES_GRP):
        return tm.Transform(MODULE_NODES_GRP)
    node = tm.Transform.create(name=MODULE_NODES_GRP)
    node.meta[tags.KIND] = "module_holder"
    return node


def create(entry: ModuleEntry, module=None) -> tm.Transform:
    """Create the document node for ``entry`` and write it."""
    node = tm.Transform.create(name=f"{entry.key}_module", parent=holder().long_name)
    node.meta[tags.KIND] = tags.MODULE_NODE
    node.meta[tags.INSTANCE] = entry.instance_id
    write(node, entry, module)
    return node


def write(node, entry: ModuleEntry, module=None) -> None:
    """Store ``entry`` on ``node``: meta for everything, attributes for scalars."""
    node.meta[tags.MODULE] = entry.module_type
    node.meta[tags.INSTANCE] = entry.instance_id
    node.meta[tags.NAME] = entry.name
    node.meta[tags.SIDE] = entry.side
    node.meta[tags.ENTRY] = entry.to_dict()
    if module is not None:
        sync_setting_attrs(node, module)


def read(node) -> ModuleEntry:
    """Rebuild the ``ModuleEntry`` stored on ``node``."""
    from tik.trigger.core import registry

    entry = ModuleEntry.from_dict(dict(node.meta[tags.ENTRY]))
    if not registry.is_module_registered(entry.module_type):
        return entry
    fields = registry.get_module(entry.module_type).fields()
    # Attributes win over the meta copy: the channel box is an authoring
    # surface, so a value tweaked there has to read back.
    for name in list(entry.settings):
        field_obj = fields.get(name)
        if field_obj is None or not node.has_attr(name):
            continue
        value = node[name].value
        kind = field_obj.type_name
        if kind == "choice":
            # the enum attribute stores an index; the setting wants the label
            try:
                value = field_obj.choices[int(value)]
            except (IndexError, ValueError, TypeError):
                continue
        elif kind == "bool":
            value = bool(value)
        entry.settings[name] = value
    return entry


def find(instance_id: str):
    """The document node for ``instance_id``, or None."""
    for node in find_all():
        if node.meta.get(tags.INSTANCE) == instance_id:
            return node
    return None


def find_all() -> list:
    """Every module document node in the scene."""
    found = []
    # cmds rather than tik.maya: one attribute-qualified ls finds every tagged
    # node without walking the DAG.
    for name in cmds.ls(f"*.{tm.META_PREFIX}{tags.KIND}", long=True, objectsOnly=True) or []:
        node = tm.resolve(name)
        if node.meta.get(tags.KIND) == tags.MODULE_NODE:
            found.append(node)
    return found


def remove(instance_id: str) -> None:
    node = find(instance_id)
    if node is not None and node.exists():
        cmds.delete(node.long_name)


def settings_plug(instance_id: str, field_name: str):
    """Plug backing a module property, for the Designer's two-way binding."""
    node = find(instance_id)
    if node is None or not node.has_attr(field_name):
        return None
    return node[field_name]


def sync_setting_attrs(node, module) -> None:
    """Mirror the module's scalar fields as real attributes on ``node``."""
    for name, field_obj in module.fields().items():
        value = getattr(module, name)
        kind = field_obj.type_name
        if kind in _NON_SCALAR:
            continue
        if not node.has_attr(name):
            if kind == "bool":
                attribute.add_bool(node, name, default=bool(value))
            elif kind == "int":
                attribute.add_int(node, name, default=int(value), min=field_obj.min, max=field_obj.max)
            elif kind == "float":
                attribute.add_float(node, name, default=float(value), min=field_obj.min, max=field_obj.max)
            elif kind == "choice":
                attribute.add_enum(
                    node, name, [str(item) for item in field_obj.choices],
                    default=field_obj.choices.index(value),
                )
            else:
                attribute.add_string(node, name)
        if kind == "choice":
            node[name].value = field_obj.choices.index(value)
        elif kind in ("string", "file", "node"):
            node[name].value = str(value)
        else:
            node[name].value = value
