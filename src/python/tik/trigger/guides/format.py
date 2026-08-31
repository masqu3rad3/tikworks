"""``.trg`` guide files.

A file is a JSON object with a ``joints`` list, a ``connections`` list and
optional ``meta`` / ``designer`` dicts. Each joint record is::

    {"name", "position", "rotation", "joint_orient", "scale", "parent",
     "side", "color", "radius", "module", "role", "index", "instance"}

Root records carry ``settings`` and ``module_name``. A record without a
``module``/``role`` pair belongs to no registered module and is reported in
``GuideFile.unknown``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from tik.trigger.core import registry
from tik.trigger.core.exceptions import GuideError

logger = logging.getLogger(__name__)

EXTENSION = ".trg"


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
    inputs: dict = field(default_factory=dict)  # input name -> source

    @property
    def key(self) -> str:
        return self.name if self.side in ("C", "") else f"{self.side}_{self.name}"

    @property
    def joint_names(self) -> list[str]:
        return [record["name"] for record in self.joints.values()]


class GuideFile:
    """Load/save ``.trg`` files and group their joints into module instances."""

    def __init__(self, records: Optional[list[dict]] = None, connections: Optional[list[dict]] = None, meta: Optional[dict] = None,
                 designer: Optional[dict] = None) -> None:
        self.records: list[dict] = list(records or [])
        self.connections: list[dict] = list(connections or [])  # {"input": "L_arm.root", "source": "body.root"}
        self.meta: dict = dict(meta or {})
        # Guide Designer state that belongs to the asset, not the window:
        # {"scene_nodes": {group: [scene node, ...]}, "positions": {key: [x, y]}, "collapse": {key: 0|1|2}}
        self.designer: dict = dict(designer or {})
        self.unknown: list[str] = []  # module types no registered module claims

    # ------------------------------------------------------------- file io
    @classmethod
    def load(cls, file_path) -> "GuideFile":
        path = Path(file_path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise GuideError(f"Cannot read guides '{path}': {error}") from error
        if isinstance(data, dict) and isinstance(data.get("joints"), list):
            return cls(data["joints"], data.get("connections", []), data.get("meta", {}), data.get("designer", {}))
        raise GuideError(f"'{path}' is not a Trigger guide file.")

    def save(self, file_path) -> Path:
        path = Path(file_path)
        if path.suffix != EXTENSION:
            path = path.with_suffix(EXTENSION)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"joints": self.records, "connections": self.connections, "meta": self.meta}
        if self.designer:
            payload["designer"] = self.designer
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def inputs_for(self, key: str) -> dict:
        """``{input name: source}`` for the instance ``key`` from the connections list."""
        found = {}
        for item in self.connections:
            target = str(item.get("input", ""))
            if target.startswith(key + "."):
                found[target[len(key) + 1:]] = item.get("source", "")
        return found

    # ------------------------------------------------------------ queries
    def by_name(self) -> dict[str, dict]:
        return {record["name"]: record for record in self.records}

    def children_of(self, name: str) -> list[dict]:
        return [record for record in self.records if record.get("parent") == name]

    def classify(self, record: dict) -> Optional[tuple[str, str, bool]]:
        """``(module_type, role, is_root)`` for a record, or None when unknown."""
        module_type, role = record.get("module"), record.get("role")
        if not module_type or not role or not registry.is_module_registered(module_type):
            return None
        return module_type, role, registry.get_module(module_type).guides.root == role

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
        """Group records into module instances."""
        self.unknown = sorted({
            record.get("module", "") for record in self.records if self.classify(record) is None
        })
        instances = self._instances_explicit()
        self._resolve_inputs(instances)
        return instances

    def _resolve_inputs(self, instances: list[GuideInstance]) -> None:
        """Explicit connections win; otherwise derive the primary input from the parent joint."""
        by_joint: dict[str, tuple[GuideInstance, str]] = {}
        for instance in instances:
            for (role, _index), record in instance.joints.items():
                by_joint[record["name"]] = (instance, role)
        for instance in instances:
            explicit = self.inputs_for(instance.key)
            if explicit:
                instance.inputs = explicit
                continue
            if not instance.parent_joint or instance.parent_joint not in by_joint:
                continue
            parent, role = by_joint[instance.parent_joint]
            module_cls = registry.get_module(instance.module_type)
            parent_cls = registry.get_module(parent.module_type)
            primary = module_cls.primary_input()
            output = parent_cls.output_at_role(role)
            if primary is not None and output is not None:
                instance.inputs = {primary.name: f"{parent.key}.{output}"}

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
                instance.name = record.get("module_name") or record.get("name", "")
                instance.side = record.get("side", "C")
                instance.settings = dict(record.get("settings") or {})
                parent = by_name.get(record.get("parent") or "")
                instance.parent_joint = parent["name"] if parent and parent.get("instance") != instance_id else None
        return list(grouped.values())


def make_record(
    *,
    name: str,
    position,
    rotation,
    joint_orient,
    parent: Optional[str],
    side: str,
    module: str,
    role: str,
    index: int,
    instance: str,
    radius: float = 1.0,
    color: int = 17,
    attrs: Optional[dict] = None,
    settings: Optional[dict] = None,
    module_name: Optional[str] = None,
) -> dict:
    """One joint record in the ``.trg`` layout."""
    record = {
        "name": name,
        "position": [float(value) for value in position],
        "rotation": [float(value) for value in rotation],
        "joint_orient": [float(value) for value in joint_orient],
        "scale": [1, 1, 1],
        "parent": parent,
        "side": side,
        "color": int(color),
        "radius": float(radius),
        "module": module,
        "role": role,
        "index": int(index),
        "instance": instance,
    }
    if attrs:
        record["attrs"] = {key: float(value) for key, value in attrs.items()}
    if settings is not None:  # root joint
        record["settings"] = dict(settings)
        record["module_name"] = module_name or name
    return record
