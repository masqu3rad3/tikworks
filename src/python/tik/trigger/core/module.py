"""Module base class.

A module declares what it needs (guides, plugs/sockets, settings) and
implements two methods that touch the scene through a context:

    @register_module("arm")
    class Arm(Module):
        label = "Arm"
        guides = Guides("collar", "shoulder", "elbow", "hand")
        plugs = ("collar", "hand")
        sockets = ("root",)
        local = BoolField(False)

        def draw_guides(self, ctx): ...
        def build(self, ctx): ...

Everything else (groups, naming, tagging, side handling, parenting under
the rig root, attaching to the parent module) is done by the backend/builder.
"""

from __future__ import annotations

import uuid
from typing import Optional

from tik.core.fields import Schema
from tik.core.side import Side

from .manifest import Guides, Input, instance_key
from .schemas import GuidePose, ModuleInstance, ParentRef


class Module(Schema):
    """Base class for rig modules."""

    label: str = ""
    sided: bool = True
    guides: Guides = Guides("root")
    inputs: tuple[Input, ...] = (Input("root", primary=True),)
    outputs: tuple[str, ...] = ("root",)
    module_type: str = ""  # stamped by @register_module
    legacy_types: dict = {}  # role -> old .trg "type" name (default: capitalised role)

    def __init__(
        self,
        instance_id: Optional[str] = None,
        name: Optional[str] = None,
        side=Side.CENTER,
        settings: Optional[dict] = None,
    ) -> None:
        self.instance_id = instance_id or uuid.uuid4().hex
        self.side = Side.from_value(side) if self.sided else Side.CENTER
        self.name = name or self.module_type or type(self).__name__.lower()
        self.guide_pairs: list[tuple[str, int]] = []
        if settings:
            self.apply(settings, strict=False)

    # ------------------------------------------------------------ manifest
    @classmethod
    def display_label(cls) -> str:
        return cls.label or cls.module_type or cls.__name__

    @classmethod
    def input_names(cls) -> list[str]:
        return [item.name for item in cls.inputs]

    @classmethod
    def primary_input(cls) -> Optional[Input]:
        for item in cls.inputs:
            if item.primary:
                return item
        return cls.inputs[0] if cls.inputs else None

    @classmethod
    def get_input(cls, name: str) -> Optional[Input]:
        return next((item for item in cls.inputs if item.name == name), None)

    @classmethod
    def output_for_role(cls, role: str) -> Optional[str]:
        """Output matching a guide role (legacy derivation), else the first output."""
        if role in cls.outputs:
            return role
        return cls.outputs[0] if cls.outputs else None

    @property
    def key(self) -> str:
        return instance_key(self.name, self.side.value)

    def guide_count(self) -> int:
        """Number of multi-role guides to draw; override when a setting drives it."""
        return self.guides.min_count

    def expected_guides(self) -> list[tuple[str, int]]:
        """``(role, index)`` pairs this module wants when drawing fresh guides."""
        return self.guides.expand(self.guide_count())

    # ------------------------------------------------------------ lifecycle
    def validate(self) -> list[str]:
        """Return problems that prevent building (empty list = ok)."""
        pairs = self.guide_pairs or self.expected_guides()
        return self.guides.validate(pairs)

    def draw_guides(self, ctx) -> None:
        """Create the default guide layout through ``ctx``."""
        raise NotImplementedError

    def build(self, ctx) -> None:
        """Build the rig from guides through ``ctx``."""
        raise NotImplementedError

    # ------------------------------------------------------------ transfer
    def to_instance(
        self,
        guides: Optional[list[GuidePose]] = None,
        parent: Optional[ParentRef] = None,
        attach: Optional[str] = None,
        inputs: Optional[dict] = None,
    ) -> ModuleInstance:
        """Serialize this module into a ``ModuleInstance``."""
        return ModuleInstance(
            module_type=self.module_type,
            instance_id=self.instance_id,
            name=self.name,
            side=self.side.value,
            settings=self.values(),
            guides=list(guides or []),
            parent=parent,
            attach=attach,
            inputs=dict(inputs or {}),
        )

    @classmethod
    def from_instance(cls, instance: ModuleInstance) -> "Module":
        """Instantiate from a ``ModuleInstance``."""
        module = cls(
            instance_id=instance.instance_id,
            name=instance.name,
            side=instance.side,
            settings=instance.settings,
        )
        module.guide_pairs = list(instance.guide_pairs)
        return module

    def __repr__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r}, side={self.side.value!r})"
