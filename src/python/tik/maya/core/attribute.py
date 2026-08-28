"""Attribute helpers shared by rig constructs and tools.

Every helper accepts a wrapped node or a node name and returns a
:class:`~tik.maya.core.plug.Plug` where that makes sense.
"""

from __future__ import annotations

from typing import Iterable, Optional

from maya import cmds

from .plug import Plug
from .registry import resolve

TRANSFORM_ATTRS = ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz")
ALL_CHANNELS = TRANSFORM_ATTRS + ("v",)


def _node(node):
    return node if hasattr(node, "long_name") else resolve(node)


def add_separator(node, name: str = "____") -> Plug:
    """Add a locked, channel-box-visible enum used as a visual separator."""
    node = _node(node)
    cmds.addAttr(
        node.long_name,
        longName=name,
        attributeType="enum",
        enumName="----------",
        keyable=False,
    )
    path = f"{node.long_name}.{name}"
    cmds.setAttr(path, channelBox=True)
    cmds.setAttr(path, lock=True)
    return Plug(node, name)


def _add_numeric(
    node, name, attribute_type, default, min_value, max_value, keyable
) -> Plug:
    node = _node(node)
    kwargs = {
        "longName": name,
        "attributeType": attribute_type,
        "defaultValue": default,
        "keyable": keyable,
    }
    if min_value is not None:
        kwargs["minValue"] = min_value
    if max_value is not None:
        kwargs["maxValue"] = max_value
    cmds.addAttr(node.long_name, **kwargs)
    return Plug(node, name)


def add_float(
    node, name, default=0.0, min=None, max=None, keyable=True  # noqa: A002
) -> Plug:
    """Add a double attribute."""
    return _add_numeric(node, name, "double", float(default), min, max, keyable)


def add_int(
    node, name, default=0, min=None, max=None, keyable=True  # noqa: A002
) -> Plug:
    """Add a long (integer) attribute."""
    return _add_numeric(node, name, "long", int(default), min, max, keyable)


def add_bool(node, name, default=False, keyable=True) -> Plug:
    """Add a boolean attribute."""
    node = _node(node)
    cmds.addAttr(
        node.long_name,
        longName=name,
        attributeType="bool",
        defaultValue=bool(default),
        keyable=keyable,
    )
    return Plug(node, name)


def add_enum(node, name, items: Iterable[str], default=0, keyable=True) -> Plug:
    """Add an enum attribute with the given item labels."""
    node = _node(node)
    cmds.addAttr(
        node.long_name,
        longName=name,
        attributeType="enum",
        enumName=":".join(items),
        defaultValue=default,
        keyable=keyable,
    )
    return Plug(node, name)


def add_string(node, name, default="") -> Plug:
    """Add a string attribute."""
    node = _node(node)
    cmds.addAttr(node.long_name, longName=name, dataType="string")
    plug = Plug(node, name)
    if default:
        plug.value = default
    return plug


def lock_and_hide(
    node, attrs: Optional[Iterable[str]] = None, hide: bool = True
) -> None:
    """Lock (and optionally hide from the channel box) the given attributes.

    Defaults to translate/rotate/scale/visibility.
    """
    node = _node(node)
    for attr_name in attrs or ALL_CHANNELS:
        path = f"{node.long_name}.{attr_name}"
        cmds.setAttr(path, lock=True)
        if hide:
            cmds.setAttr(path, keyable=False, channelBox=False)


def unlock(node, attrs: Optional[Iterable[str]] = None, show: bool = True) -> None:
    """Unlock (and optionally re-expose) the given attributes."""
    node = _node(node)
    for attr_name in attrs or ALL_CHANNELS:
        path = f"{node.long_name}.{attr_name}"
        cmds.setAttr(path, lock=False)
        if show:
            cmds.setAttr(path, keyable=True)


def drive(source: Plug, targets: Iterable[Plug], force: bool = True) -> None:
    """Connect ``source`` into every plug in ``targets``."""
    for target in targets:
        source.connect(target, force=force)


def add_proxy(node, source: Plug, name: Optional[str] = None) -> Plug:
    """Add a proxy attribute on ``node`` mirroring ``source``."""
    node = _node(node)
    name = name or source.attr
    cmds.addAttr(node.long_name, longName=name, proxy=source.path)
    return Plug(node, name)
