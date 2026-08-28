"""Serializable session data structures (schema version 3)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

SCHEMA_VERSION = 3


@dataclass
class GuidePose:
    """World-space pose of one guide."""

    role: str
    index: int = 0
    position: tuple = (0.0, 0.0, 0.0)
    rotation: tuple = (0.0, 0.0, 0.0)

    @classmethod
    def from_dict(cls, data: dict) -> "GuidePose":
        return cls(
            role=data["role"],
            index=int(data.get("index", 0)),
            position=tuple(data.get("position", (0.0, 0.0, 0.0))),
            rotation=tuple(data.get("rotation", (0.0, 0.0, 0.0))),
        )


@dataclass
class ParentRef:
    """Which guide of another instance a root guide hangs under."""

    instance_id: str
    role: str = ""
    index: int = 0

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> Optional["ParentRef"]:
        if not data:
            return None
        return cls(
            instance_id=data["instance_id"],
            role=data.get("role", ""),
            index=int(data.get("index", 0)),
        )


@dataclass
class ModuleInstance:
    """A module placed in a rig (guides + settings + parenting)."""

    module_type: str
    instance_id: str
    name: str
    side: str = "C"
    settings: dict = field(default_factory=dict)
    guides: list[GuidePose] = field(default_factory=list)
    parent: Optional[ParentRef] = None
    attach: Optional[str] = None  # plug name override on the parent

    @property
    def guide_pairs(self) -> list[tuple[str, int]]:
        return [(pose.role, pose.index) for pose in self.guides]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["parent"] = asdict(self.parent) if self.parent else None
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ModuleInstance":
        return cls(
            module_type=data["module_type"],
            instance_id=data["instance_id"],
            name=data.get("name", data["module_type"]),
            side=data.get("side", "C"),
            settings=dict(data.get("settings", {})),
            guides=[GuidePose.from_dict(item) for item in data.get("guides", [])],
            parent=ParentRef.from_dict(data.get("parent")),
            attach=data.get("attach"),
        )


@dataclass
class ActionInstance:
    """One entry of the action pipeline."""

    action_type: str
    name: str
    enabled: bool = True
    settings: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ActionInstance":
        return cls(
            action_type=data["action_type"],
            name=data["name"],
            enabled=bool(data.get("enabled", True)),
            settings=dict(data.get("settings", {})),
        )


@dataclass
class RigDocument:
    """Root of a ``.trg`` file: guide snapshot + action pipeline + metadata."""

    schema: int = SCHEMA_VERSION
    meta: dict = field(default_factory=dict)
    guides: list[ModuleInstance] = field(default_factory=list)
    actions: list[ActionInstance] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "meta": dict(self.meta),
            "guides": [item.to_dict() for item in self.guides],
            "actions": [item.to_dict() for item in self.actions],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RigDocument":
        schema = int(data.get("schema", SCHEMA_VERSION))
        if schema > SCHEMA_VERSION:
            raise ValueError(
                f"Session schema {schema} is newer than supported {SCHEMA_VERSION}."
            )
        return cls(
            schema=SCHEMA_VERSION,
            meta=dict(data.get("meta", {})),
            guides=[ModuleInstance.from_dict(item) for item in data.get("guides", [])],
            actions=[ActionInstance.from_dict(item) for item in data.get("actions", [])],
        )


def order_instances(instances: list[ModuleInstance]) -> list[ModuleInstance]:
    """Return instances parents-first, keeping the input order otherwise."""
    by_id = {instance.instance_id: instance for instance in instances}
    ordered: list[ModuleInstance] = []
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(instance: ModuleInstance) -> None:
        if instance.instance_id in done:
            return
        if instance.instance_id in visiting:
            raise ValueError(f"Cyclic parenting at '{instance.name}'.")
        visiting.add(instance.instance_id)
        parent = by_id.get(instance.parent.instance_id) if instance.parent else None
        if parent is not None:
            visit(parent)
        visiting.discard(instance.instance_id)
        done.add(instance.instance_id)
        ordered.append(instance)

    for instance in instances:
        visit(instance)
    return ordered


__all__: list[Any] = [
    "SCHEMA_VERSION",
    "GuidePose",
    "ParentRef",
    "ModuleInstance",
    "ActionInstance",
    "RigDocument",
    "order_instances",
]
