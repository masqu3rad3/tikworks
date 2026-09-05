"""The one scaffold every rig is built into, ensured before any build or action.

Spec: docs/superpowers/specs/2026-09-05-rig-scaffold-and-master-controls-design.md

A scene holds one rig and it has no name: the scaffold is addressed by fixed
names and confirmed by tags. ``ensure_rig`` is idempotent and heals -- a node
found by name but untagged is adopted, a missing node or attribute is created,
and the values of attributes already present are left alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from maya import cmds

import tik.maya as tm
from tik.maya.roles.controller import Controller

from . import tags

RIG_GRP = "rig_grp"
TRIGGER_GRP = "trigger_grp"
GEO_GRP = "geo_grp"
PREFERENCES_CTRL = "preferences_ctrl"
VISIBILITIES_CTRL = "visibilities_ctrl"

DISPLAY_MODES = ("normal", "template", "reference")  # == overrideDisplayType 0/1/2

#: (name, attr_type, default, kwargs) in channel-box order. A separator row
#: is inserted before "rig" so the three display pairs read as one block.
PREFERENCE_ATTRS = (
    ("cacheMode", "bool", False, {}),
    ("controls", "bool", True, {}),
    ("rig", "bool", False, {}),
    ("rigDisplay", "enum", 0, {"items": list(DISPLAY_MODES)}),
    ("joints", "bool", True, {}),
    ("jointsDisplay", "enum", 0, {"items": list(DISPLAY_MODES)}),
    ("geo", "bool", True, {}),
    ("geoDisplay", "enum", 0, {"items": list(DISPLAY_MODES)}),
)
DISPLAY_SEPARATOR = "display_"


@dataclass
class RigScaffold:
    """The fixed nodes of the one rig in the scene."""

    root: Any  # rig_grp
    trigger: Any  # trigger_grp
    geo: Any  # geo_grp
    preferences: Controller
    visibilities: Controller


def _log(events, message: str, level: str = "warning") -> None:
    if events is not None:
        events.log(message, level=level)


def _lock_channels(node) -> None:
    for channel in tm.SCALE_CHANNELS:
        plug = node[channel]
        plug.locked = True
        plug.visible = False


def _ensure_group(name: str, parent, kind: str, events) -> tm.Transform:
    """The transform ``name`` under ``parent`` (None = world), tagged ``kind``."""
    path = f"{parent.long_name}|{name}" if parent is not None else f"|{name}"
    if cmds.objExists(path):
        node = tm.Transform(path)
        if node.meta.get(tags.KIND) != kind:
            _log(events, f"Adopted existing '{name}' as the rig's {kind}.")
            node.meta[tags.KIND] = kind
    else:
        node = tm.Transform.create(
            name=name, parent=parent.long_name if parent is not None else None
        )
        node.meta[tags.KIND] = kind
    _lock_channels(node)
    return node


def _ensure_control(name: str, parent, kind: str, shape: str, events, size=1.0) -> Controller:
    """The controller ``name`` under ``parent``, tagged ``kind``."""
    path = f"{parent.long_name}|{name}"
    if cmds.objExists(path):
        node = tm.Transform(path)
        if Controller.is_controller(node):
            control = Controller(node)
        else:
            _log(events, f"Adopted existing '{name}' as the rig's {kind} control.")
            control = Controller(node)
            control._tag_as_controller()
            control.set_shape(shape, size=1.0)
        if node.meta.get(tags.KIND) != kind:
            node.meta[tags.KIND] = kind
        return control
    control = Controller.create(
        name=name, shape=shape, size=1.0, parent=parent.long_name, color=(1,1,0)
    )
    control.transform.meta[tags.KIND] = kind
    control.transform["rotate"].set([90,0,0]) # set to upright
    control.transform["scale"].set((size,size,size))
    control.transform.freeze()
    _lock_channels(control.transform)
    return control


def _ensure_preference_attrs(control: Controller) -> None:
    """Add any preference attribute that is missing; leave present ones alone."""
    node = control.transform
    for name, attr_type, default, kwargs in PREFERENCE_ATTRS:
        if name == "rig" and not node[DISPLAY_SEPARATOR].exists():
            row = node[DISPLAY_SEPARATOR].create(
                "enum", items=["----------"], keyable=False
            )
            row.visible = True
            row.locked = True
        plug = node[name]
        if plug.exists():
            continue
        plug.create(attr_type, default=default, keyable=False, **kwargs)
        plug.visible = True


def _wire_geo(control: Controller, geo) -> None:
    """geo -> geo_grp.visibility, geoDisplay -> its override type."""
    prefs = control.transform
    if geo["visibility"].get_input() is None:
        prefs["geo"] >> geo["visibility"]
    geo["overrideEnabled"].value = True
    if geo["overrideDisplayType"].get_input() is None:
        prefs["geoDisplay"] >> geo["overrideDisplayType"]


def ensure_rig(events: Optional[Any] = None) -> RigScaffold:
    """The scaffold, created or healed. Safe to call before every step."""
    root = _ensure_group(RIG_GRP, None, tags.RIG_ROOT, events)
    trigger = _ensure_group(TRIGGER_GRP, root, tags.RIG_TRIGGER, events)
    geo = _ensure_group(GEO_GRP, root, tags.RIG_GEO, events)
    preferences = _ensure_control(
        PREFERENCES_CTRL, trigger, tags.PREFERENCES, "P", events, size=1.0
    )
    visibilities = _ensure_control(
        VISIBILITIES_CTRL, trigger, tags.VISIBILITIES, "Cog", events, size=0.5
    )
    # move the preferences a bit higher
    visibilities.transform["translateX"].set(1)
    _ensure_preference_attrs(preferences)
    _wire_geo(preferences, geo)
    return RigScaffold(
        root=root,
        trigger=trigger,
        geo=geo,
        preferences=preferences,
        visibilities=visibilities,
    )


def find_rig() -> Optional[RigScaffold]:
    """The scaffold if the scene has one, without creating anything."""
    if not cmds.objExists(f"|{RIG_GRP}|{TRIGGER_GRP}|{PREFERENCES_CTRL}"):
        return None
    return ensure_rig()
