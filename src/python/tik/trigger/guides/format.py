"""``.trg`` guide files — the old Trigger joint-list format, kept compatible.

A file is a JSON list of joint records::

    {"name", "position", "rotation", "joint_orient", "scale", "parent", "side",
     "type", "color", "radius", "user_attributes": [...]}

New files add optional keys (``module``, ``role``, ``index``, ``instance``,
``settings``) that old readers ignore. When they are missing, modules are
recovered from the legacy ``type`` names through the module registry.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from tik.trigger.core import registry
from tik.trigger.core.exceptions import GuideError

logger = logging.getLogger(__name__)

EXTENSION = ".trg"
ROOT_TYPE_ATTRS = ("moduleName", "upAxisX", "upAxisY", "upAxisZ", "mirrorAxisX",
                   "mirrorAxisY", "mirrorAxisZ", "lookAxisX", "lookAxisY", "lookAxisZ",
                   "useRefOri")


def legacy_type(module_cls, role: str) -> str:
    """Legacy ``type`` name for a module role (old files use capitalised names)."""
    mapping = getattr(module_cls, "legacy_types", {}) or {}
    return mapping.get(role) or role[:1].upper() + role[1:]


def legacy_table() -> dict[str, tuple[str, str, bool]]:
    """``legacy type -> (module_type, role, is_root)`` for every registered module."""
    table: dict[str, tuple[str, str, bool]] = {}
    for module_cls in registry.iter_modules():
        guides = module_cls.guides
        for role in guides.all_roles:
            key = legacy_type(module_cls, role)
            table.setdefault(key, (module_cls.module_type, role, role == guides.root))
    return table


@dataclass
class GuideInstance:
    """One module instance recovered from a guide file."""

    module_type: str
    instance_id: str
    name: str
    side: str
    root: dict
    joints: dict = field(default_factory=dict)  # (role, index) -> record
    settings: dict = field(default_factory=dict)
    parent_joint: Optional[str] = None  # joint name of another instance we hang under

    @property
    def joint_names(self) -> list[str]:
        return [record["name"] for record in self.joints.values()]


class GuideFile:
    """Load/save ``.trg`` files and group their joints into module instances."""

    def __init__(self, records: Optional[list[dict]] = None) -> None:
        self.records: list[dict] = list(records or [])
        self.unknown: list[str] = []  # legacy types no module claims

    # ------------------------------------------------------------- file io
    @classmethod
    def load(cls, file_path) -> "GuideFile":
        path = Path(file_path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise GuideError(f"Cannot read guides '{path}': {error}") from error
        if not isinstance(data, list):
            raise GuideError(f"'{path}' is not a Trigger guide file.")
        return cls(data)

    def save(self, file_path) -> Path:
        path = Path(file_path)
        if path.suffix != EXTENSION:
            path = path.with_suffix(EXTENSION)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.records, indent=2), encoding="utf-8")
        return path

    # ------------------------------------------------------------ queries
    def by_name(self) -> dict[str, dict]:
        return {record["name"]: record for record in self.records}

    def children_of(self, name: str) -> list[dict]:
        return [record for record in self.records if record.get("parent") == name]

    def classify(self, record: dict) -> Optional[tuple[str, str, bool]]:
        """``(module_type, role, is_root)`` for a record, or None when unknown."""
        if record.get("module") and record.get("role"):
            module_type, role = record["module"], record["role"]
            if not registry.is_module_registered(module_type):
                return None
            is_root = registry.get_module(module_type).guides.root == role
            return module_type, role, is_root
        return legacy_table().get(record.get("type", ""))

    def roots(self) -> list[dict]:
        found = []
        for record in self.records:
            info = self.classify(record)
            if info and info[2]:
                found.append(record)
        return found

    def root_names(self) -> list[str]:
        return [record["name"] for record in self.roots()]

    def instances(self) -> list[GuideInstance]:
        """Group records into module instances (explicit keys or legacy walk)."""
        self.unknown = sorted({
            record.get("type", "") for record in self.records if self.classify(record) is None
        })
        if any(record.get("instance") for record in self.records):
            return self._instances_explicit()
        return self._instances_legacy()

    def _instances_explicit(self) -> list[GuideInstance]:
        grouped: dict[str, GuideInstance] = {}
        by_name = self.by_name()
        for record in self.records:
            info = self.classify(record)
            instance_id = record.get("instance")
            if not info or not instance_id:
                continue
            module_type, role, is_root = info
            instance = grouped.get(instance_id)
            if instance is None:
                instance = GuideInstance(module_type, instance_id, record.get("name", ""), record.get("side", "C"), record)
                grouped[instance_id] = instance
            instance.joints[(role, int(record.get("index", 0)))] = record
            if is_root:
                instance.root = record
                instance.name = _module_name(record)
                instance.side = record.get("side", "C")
                instance.settings = dict(record.get("settings") or _settings_from_attrs(record))
                parent = by_name.get(record.get("parent") or "")
                instance.parent_joint = parent["name"] if parent and parent.get("instance") != instance_id else None
        return list(grouped.values())

    def _instances_legacy(self) -> list[GuideInstance]:
        instances: list[GuideInstance] = []
        for root in self.roots():
            module_type, root_role, _is_root = self.classify(root)
            instance = GuideInstance(
                module_type, uuid.uuid4().hex, _module_name(root), root.get("side", "C"), root,
                settings=_settings_from_attrs(root),
            )
            instance.joints[(root_role, 0)] = root
            parent = self.by_name().get(root.get("parent") or "")
            instance.parent_joint = parent["name"] if parent else None
            counters: dict[str, int] = {}
            self._walk_members(root, module_type, instance, counters)
            instances.append(instance)
        return instances

    def _walk_members(self, record: dict, module_type: str, instance: GuideInstance, counters: dict) -> None:
        for child in self.children_of(record["name"]):
            info = self.classify(child)
            if not info or info[2] or info[0] != module_type:
                continue  # another instance's root, or unknown
            role = info[1]
            index = counters.get(role, 0)
            counters[role] = index + 1
            instance.joints[(role, index)] = child
            self._walk_members(child, module_type, instance, counters)


def _module_name(record: dict) -> str:
    for attr in record.get("user_attributes", []) or []:
        if attr.get("attr_name") == "moduleName":
            return str(attr.get("default_value") or record["name"])
    return record.get("name", "")


def _settings_from_attrs(record: dict) -> dict:
    """Module properties = user attributes that are not the global joint attrs."""
    settings = {}
    for attr in record.get("user_attributes", []) or []:
        name = attr.get("attr_name")
        if name in ROOT_TYPE_ATTRS or not name:
            continue
        settings[name] = attr.get("default_value")
    return settings


def make_record(
    *,
    name: str,
    position,
    rotation,
    joint_orient,
    parent: Optional[str],
    side: str,
    legacy: str,
    module: str,
    role: str,
    index: int,
    instance: str,
    radius: float = 1.0,
    color: int = 17,
    settings: Optional[dict] = None,
    module_name: Optional[str] = None,
    axes: Optional[dict] = None,
    inherit_orientation: bool = True,
) -> dict:
    """Build a record in the legacy layout plus the new explicit keys."""
    record = {
        "name": name,
        "position": [float(value) for value in position],
        "rotation": [float(value) for value in rotation],
        "joint_orient": [float(value) for value in joint_orient],
        "scale": [1, 1, 1],
        "parent": parent,
        "side": side,
        "type": legacy,
        "color": int(color),
        "radius": float(radius),
        "user_attributes": [],
        "module": module,
        "role": role,
        "index": int(index),
        "instance": instance,
    }
    if settings is not None:  # root joint
        axes = axes or {"upAxis": (0, 1, 0), "mirrorAxis": (1, 0, 0), "lookAxis": (0, 0, 1)}
        attrs = [{"attr_name": "moduleName", "attr_type": "string", "nice_name": "Module Name",
                  "default_value": module_name or name}]
        for axis_name, vector in axes.items():
            for component, value in zip("XYZ", vector):
                attrs.append({"attr_name": f"{axis_name}{component}", "attr_type": "float",
                              "nice_name": f"{axis_name} {component}", "default_value": float(value)})
        attrs.append({"attr_name": "useRefOri", "attr_type": "bool", "nice_name": "Inherit Orientation",
                      "default_value": bool(inherit_orientation)})
        for key, value in settings.items():
            attrs.append({"attr_name": key, "attr_type": _attr_type(value), "nice_name": key.replace("_", " ").title(),
                          "default_value": value})
        record["user_attributes"] = attrs
        record["settings"] = dict(settings)
    return record


def _attr_type(value) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "long"
    if isinstance(value, float):
        return "double"
    return "string"
