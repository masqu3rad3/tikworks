"""Module base class.

A module declares what it needs (guides, inputs/outputs, settings) and
implements two methods that touch the scene through the objects the builder
hands them::

    @register_module("arm")
    class Arm(Module):
        label = "Arm"
        guides = GuideLayout("collar", "shoulder", "elbow", "hand")
        inputs = (Input("root", primary=True),)
        outputs = ("collar", "upperarm", "lowerarm", "hand")
        stretch = BoolField(True)

        def draw_guides(self, guides): ...
        def build(self, rig): ...

Everything else — the four groups, naming, tagging, side handling, parenting
under the rig root, materializing a socket per declared input and connecting
it to the producer — is done by ``ModuleRig`` and the builder.
"""

from __future__ import annotations

import uuid
from typing import Optional

from tik.core.fields import Column, FieldGroup, Schema, TableField
from tik.core.side import Side

from .manifest import GuideAttr, GuideLayout, Input, instance_key
from .schemas import GuidePose, ModuleInstance, ParentRef

SPACES = FieldGroup("Spaces", collapsed=True)
"""Every module's animation spaces fold away; declared here, not per module."""


class Module(Schema):
    """Base class for rig modules."""

    label: str = ""
    sided: bool = True
    guides: GuideLayout = GuideLayout("root")
    inputs: tuple[Input, ...] = (Input("root", primary=True),)
    #: Per-guide authored attributes, keyed by guide role. Roles absent from
    #: the mapping carry none, so existing modules are unaffected.
    guide_attrs: dict[str, tuple[GuideAttr, ...]] = {}
    space_controls: tuple[str, ...] = ()  # controller roles that accept spaces
    outputs: tuple[str, ...] = ("root",)
    module_type: str = ""  # stamped by @register_module
    anim_spaces = TableField(
        [],
        label="Anim Spaces",
        group=SPACES,
        help="Each row adds one animation space and one input port.",
        last=True,
        columns=(
            Column("control", "choice", choices_from="space_controls"),
            Column("mode", "choice", choices=("parent", "point", "orient")),
            Column("label", "string"),
        ),
    )

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
    def space_rows(cls, settings=None) -> list[dict]:
        """The anim-space rows from ``settings`` (or the field default)."""
        if settings is None:
            return [dict(row) for row in cls.anim_spaces.default]
        return [dict(row) for row in (settings.get("anim_spaces") or [])]

    @classmethod
    def space_inputs(cls, settings=None) -> list[Input]:
        """One optional, space-kind Input per row: ``<control>_<label>``."""
        found = []
        for row in cls.space_rows(settings):
            control, label = row.get("control", ""), row.get("label", "")
            if not control or not label:
                continue
            found.append(Input(f"{control}_{label}", kind="space", optional=True))
        return found

    @classmethod
    def input_names(cls, settings=None) -> list[str]:
        return [item.name for item in cls.inputs] + [
            item.name for item in cls.space_inputs(settings)
        ]

    @classmethod
    def primary_input(cls) -> Optional[Input]:
        for item in cls.inputs:
            if item.primary:
                return item
        return cls.inputs[0] if cls.inputs else None

    @classmethod
    def get_input(cls, name: str, settings=None) -> Optional[Input]:
        """Find a declared input, or one derived from an anim-space row."""
        found = next((item for item in cls.inputs if item.name == name), None)
        if found is not None:
            return found
        return next(
            (item for item in cls.space_inputs(settings) if item.name == name), None
        )

    @classmethod
    def output_names(cls, settings: Optional[dict] = None) -> tuple[str, ...]:
        """Outputs an instance exposes; override when a setting adds outputs (e.g. chain segments)."""
        return tuple(cls.outputs)

    @classmethod
    def attrs_for_role(cls, role: str) -> tuple[GuideAttr, ...]:
        """Declared per-guide attributes for ``role`` (empty when none)."""
        return tuple(cls.guide_attrs.get(role, ()))

    @classmethod
    def output_at_role(cls, role: str) -> Optional[str]:
        """Output a child's primary input is pre-filled with when drawn under ``role``.

        The output whose name matches the parent's guide role if there is one,
        else the parent's first output.
        """
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
        problems = list(self.guides.validate(pairs))
        problems.extend(self._validate_spaces())
        return problems

    def _validate_spaces(self) -> list[str]:
        """Anim-space rows must derive unique, well-formed port names."""
        problems, seen = [], set()
        for index, row in enumerate(self.anim_spaces):
            control, label = row.get("control", ""), row.get("label", "")
            if not label:
                problems.append(f"anim space row {index + 1}: label is required")
                continue
            if control not in self.space_controls:
                problems.append(
                    f"anim space row {index + 1}: '{control}' is not one of "
                    f"{list(self.space_controls)}"
                )
                continue
            name = f"{control}_{label}"
            if name in seen:
                problems.append(
                    f"anim space row {index + 1}: '{name}' is already defined"
                )
            seen.add(name)
        return problems

    def draw_guides(self, ctx) -> None:
        """Create the default guide layout through ``ctx``."""
        raise NotImplementedError

    def wire_guides(self, guides) -> None:
        """Connect a guide rig over already-created guides.

        Called after ``draw_guides`` *and* after guides are re-imported from a
        ``.trg``, so a module that constrains or drives its own guides gets
        the same rig on both paths. ``guides`` maps ``(role, index)`` to the
        guide node. Must be safe to run on freshly created guides only.
        """

    def build(self, ctx) -> None:
        """Build the rig from guides through ``ctx``."""
        raise NotImplementedError

    # ------------------------------------------------------------ transfer
    def to_instance(
        self,
        guides: Optional[list[GuidePose]] = None,
        parent: Optional[ParentRef] = None,
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
