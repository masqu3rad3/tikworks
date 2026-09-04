"""Serializable session data structures (schema version 3)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from tik.trigger.core.ordering import dependency_order

SCHEMA_VERSION = 3

# What a build does with the guides once it is done.
AFTERLIFE_MODES = ("keep", "hide", "delete")


@dataclass
class GuidePose:
    """World-space pose of one guide."""

    role: str
    index: int = 0
    position: tuple = (0.0, 0.0, 0.0)
    rotation: tuple = (0.0, 0.0, 0.0)
    # Euler triples are order-relative, so the order travels with them: reading
    # a rotation in one order and applying it in another silently reinterprets
    # it. Maya's default (xyz) is 0.
    rotate_order: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "GuidePose":
        """Rebuild a pose from its JSON form."""
        return cls(
            role=data["role"],
            index=int(data.get("index", 0)),
            position=tuple(data.get("position", (0.0, 0.0, 0.0))),
            rotation=tuple(data.get("rotation", (0.0, 0.0, 0.0))),
            rotate_order=int(data.get("rotate_order", 0)),
        )


@dataclass
class ParentRef:
    """Which guide of another instance a root guide hangs under."""

    instance_id: str
    role: str = ""
    index: int = 0

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> Optional["ParentRef"]:
        """Rebuild a parent reference from its JSON form; None stays None."""
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
    inputs: dict = field(
        default_factory=dict
    )  # input name -> "<key>.<output>" | scene node

    @property
    def key(self) -> str:
        """Display key: ``name`` for center modules, ``<side>_<name>`` otherwise."""
        return self.name if self.side in ("C", "") else f"{self.side}_{self.name}"

    @property
    def guide_pairs(self) -> list[tuple[str, int]]:
        """``(role, index)`` of every guide pose."""
        return [(pose.role, pose.index) for pose in self.guides]

    def to_dict(self) -> dict:
        """The JSON form used by ``.trg`` files."""
        data = asdict(self)
        data["parent"] = asdict(self.parent) if self.parent else None
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ModuleInstance":
        """Rebuild an instance from its JSON form."""
        return cls(
            module_type=data["module_type"],
            instance_id=data["instance_id"],
            name=data.get("name", data["module_type"]),
            side=data.get("side", "C"),
            settings=dict(data.get("settings", {})),
            guides=[GuidePose.from_dict(item) for item in data.get("guides", [])],
            parent=ParentRef.from_dict(data.get("parent")),
            inputs=dict(data.get("inputs", {}) or {}),
        )


@dataclass
class ActionInstance:
    """One entry of the action pipeline."""

    action_type: str
    name: str
    enabled: bool = True
    settings: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """The JSON form used by ``.trg`` files."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ActionInstance":
        """Rebuild an action instance from its JSON form."""
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
        """The JSON form of the whole rig document."""
        return {
            "schema": self.schema,
            "meta": dict(self.meta),
            "guides": [item.to_dict() for item in self.guides],
            "actions": [item.to_dict() for item in self.actions],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RigDocument":
        """Rebuild a rig document from its JSON form."""
        schema = int(data.get("schema", SCHEMA_VERSION))
        if schema > SCHEMA_VERSION:
            raise ValueError(
                f"Session schema {schema} is newer than supported {SCHEMA_VERSION}."
            )
        return cls(
            schema=SCHEMA_VERSION,
            meta=dict(data.get("meta", {})),
            guides=[ModuleInstance.from_dict(item) for item in data.get("guides", [])],
            actions=[
                ActionInstance.from_dict(item) for item in data.get("actions", [])
            ],
        )


def split_source(source: str) -> tuple[Optional[str], str]:
    """``"L_arm.hand"`` -> ("L_arm", "hand"); ``"some_jnt"`` -> (None, "some_jnt")."""
    if "." in source:
        key, _dot, output = source.rpartition(".")
        return key, output
    return None, source


def order_instances(instances: list[ModuleInstance]) -> list[ModuleInstance]:
    """Return instances parents-first, keeping the input order otherwise."""
    by_id = {instance.instance_id: instance for instance in instances}

    def parents(instance: ModuleInstance) -> list[ModuleInstance]:
        parent = by_id.get(instance.parent.instance_id) if instance.parent else None
        return [parent] if parent is not None else []

    return dependency_order(
        instances,
        parents,
        lambda instance: instance.instance_id,
        cycle_error=lambda instance: f"Cyclic parenting at '{instance.name}'.",
    )


def order_by_connections(
    instances: list[ModuleInstance], inputs_for
) -> list[ModuleInstance]:
    """Return instances with producers before consumers.

    Bind joints must be created in their final hierarchy position, so a
    module's producer has to be built before the module itself.

    Args:
        instances: The instances to order.
        inputs_for: Callable returning ``{input_name: source}`` for an instance.
            A source is ``"<module key>.<output>"`` or a bare scene node name;
            bare names have no producer and are ignored.

    Returns:
        The instances, producers first, input order preserved otherwise.

    Raises:
        ValueError: On a cyclic connection, naming the instance.
    """
    by_key = {instance.key: instance for instance in instances}

    def producers(instance: ModuleInstance) -> list[ModuleInstance]:
        found = []
        for source in (inputs_for(instance) or {}).values():
            if not source or "." not in source:
                continue
            key, _dot, _output = source.rpartition(".")
            producer = by_key.get(key)
            if producer is not None and producer is not instance:
                found.append(producer)
        return found

    return dependency_order(
        instances,
        producers,
        lambda instance: instance.instance_id,
        cycle_error=lambda instance: f"Cyclic module connection at '{instance.name}'.",
    )


__all__: list[Any] = [
    "SCHEMA_VERSION",
    "AFTERLIFE_MODES",
    "GuidePose",
    "ParentRef",
    "ModuleInstance",
    "ActionInstance",
    "RigDocument",
    "order_instances",
    "order_by_connections",
    "split_source",
]
