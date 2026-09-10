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

from tik.core.fields import Column, FieldGroup, ListField, Schema, TableField
from tik.core.side import Side

from . import copies as copy_list
from . import shapes as shape_library
from .manifest import GuideAttr, GuideLayout, Input, instance_key
from .schemas import GuidePose, ModuleInstance, ParentRef

SPACES = FieldGroup("Spaces", collapsed=True)
"""Every module's animation spaces fold away; declared here, not per module."""

PIVOTS = FieldGroup("Pivots", collapsed=True)
"""Every module's pivot presets fold away; declared here, not per module."""

SHAPES = FieldGroup("Shapes", collapsed=True)
"""Every module's control shapes fold away; declared here, not per module."""


class Module(Schema):
    """Base class for rig modules."""

    label: str = ""
    sided: bool = True
    guides: GuideLayout = GuideLayout("root")
    inputs: tuple[Input, ...] = (Input("root", primary=True),)
    #: Per-guide authored attributes, keyed by guide role. Roles absent from
    #: the mapping carry none, so existing modules are unaffected.
    guide_attrs: dict[str, tuple[GuideAttr, ...]] = {}
    #: Controller roles this module builds. Every one of them can host an
    #: animation space; tweak controllers are excluded by construction, since
    #: ``rig.tweak_control`` parents them under their main.
    controls: tuple[str, ...] = ()
    #: Controller roles that get a movable pivot, mapped to the guide their
    #: preset guides hang under. Declaring an entry is what makes the control
    #: movable, the way declaring an input is what makes its socket. The anchor
    #: is the module author's business, never the rigger's, so it is a class
    #: attribute rather than a table column.
    pivot_controls: dict[str, str] = {}
    #: Default shape per controller role, keyed by the names ``control_names``
    #: returns. The manifest is the only place a default lives -- which is why
    #: ``rig.controller`` has no ``shape`` argument to hide a second one in.
    control_shapes: dict[str, str] = {}
    #: Per-role shape rotation in degrees, baked into the CVs at build time.
    #: Shapes are authored flat in XZ with the normal on +Y; a control that
    #: wraps a bone wants that normal along the bone instead. Module-level
    #: only -- an orientation is the module author's business, not a knob the
    #: rigger needs, and a column for it would crowd the shape table.
    control_orients: dict[str, tuple[float, float, float]] = {}
    outputs: tuple[str, ...] = ("root",)
    module_type: str = ""  # stamped by @register_module
    category: str = "generic"  # stamped by @register_module
    icon: str = ""  # stamped by @register_module
    copies = ListField(
        [],
        item_type=dict,
        label="Copies",
        hidden=True,
        help="One row per copy of this module.",
    )
    """One row per copy: its slug, its name, and its per-copy values.

    Hidden because the tab bar is its editor, the same arrangement
    ``filterable`` uses for the ``<name>_only_selected`` field it injects.
    An empty list means one copy -- see ``copy_rows``.

    Not ``last=True`` like the three tables below it: ``last`` decides where a
    field *renders*, and a hidden field renders nowhere. Marking it would only
    have pushed the three visible tables out of the trailing group.
    """
    anim_spaces = TableField(
        [],
        label="Anim Spaces",
        group=SPACES,
        help="Each row adds one animation space and one input port.",
        last=True,
        columns=(
            Column("control", "choice", choices_from="control_names"),
            Column("mode", "choice", choices=("parent", "point", "orient")),
            Column("label", "string"),
        ),
    )
    pivot_presets = TableField(
        [],
        label="Pivot Presets",
        group=PIVOTS,
        help="Each row adds one named pivot position and one guide to place it with.",
        last=True,
        columns=(
            Column("control", "choice", choices_from="pivot_control_names"),
            Column("label", "string"),
        ),
    )
    control_shape_overrides = TableField(
        [],
        label="Control Shapes",
        group=SHAPES,
        help="Override the shape and relative size of one controller.",
        last=True,
        rows_from="control_names",
        columns=(
            Column("control", "choice", choices_from="control_names"),
            Column("shape", "shape"),
            Column("size", "float"),
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
        """The label shown in the UI (falls back to the type or class name)."""
        return cls.label or cls.module_type or cls.__name__

    @classmethod
    def space_rows(cls, settings=None) -> list[dict]:
        """The anim-space rows from ``settings`` (or the field default)."""
        if settings is None:
            return [dict(row) for row in cls.anim_spaces.default]
        return [dict(row) for row in (settings.get("anim_spaces") or [])]

    @classmethod
    def space_inputs(cls, settings=None) -> list[Input]:
        """One space-kind Input per row: ``<control>_<label>``."""
        found = []
        for row in cls.space_rows(settings):
            control, label = row.get("control", ""), row.get("label", "")
            if not control or not label:
                continue
            found.append(Input(f"{control}_{label}", kind="space"))
        return found

    @classmethod
    def input_names(cls, settings=None) -> list[str]:
        """Declared inputs followed by the space inputs ``settings`` add."""
        return [item.name for item in cls.inputs] + [
            item.name for item in cls.space_inputs(settings)
        ]

    @classmethod
    def primary_input(cls) -> Optional[Input]:
        """The input marked primary, else the first declared one, else None."""
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
        """Outputs an instance exposes.

        Override when a setting adds outputs (chain segments, say).
        """
        return tuple(cls.outputs)

    @classmethod
    def control_names(cls, settings: Optional[dict] = None) -> tuple[str, ...]:
        """Controller roles an instance builds.

        Override when a setting drives them -- ``fkchain`` builds one per
        segment. This is the shape of ``output_names`` on purpose: one idiom
        for a manifest entry whose set depends on settings, not two.
        """
        return tuple(cls.controls)

    @classmethod
    def pivot_control_names(cls, settings: Optional[dict] = None) -> tuple[str, ...]:
        """Controller roles with a movable pivot.

        Override when a setting drives them, exactly as ``control_names`` and
        ``output_names`` are overridden.
        """
        return tuple(cls.pivot_controls)

    @classmethod
    def control_shape_defaults(cls, settings: Optional[dict] = None) -> dict[str, str]:
        """Default shape per control role.

        Override when a setting drives them -- exactly as ``control_names``
        and ``output_names`` are overridden.
        """
        return dict(cls.control_shapes)

    @classmethod
    def control_orient_defaults(cls, settings: Optional[dict] = None) -> dict:
        """Shape rotation per control role, in degrees.

        Override when a setting drives them, exactly as
        ``control_shape_defaults`` is overridden.
        """
        return dict(cls.control_orients)

    def shape_rows(self) -> dict[str, dict]:
        """The override rows, keyed by control role. Later rows win."""
        found = {}
        for row in self.control_shape_overrides:
            control = row.get("control", "")
            if control:
                found[control] = row
        return found

    def resolve_control_shape(self, role: str) -> tuple[str, float]:
        """The effective ``(shape, size multiplier)`` for one control role.

        Resolution is *per field*, not per row: a row that sets only a size
        keeps the manifest shape, and a row that sets only a shape keeps a
        multiplier of 1.0. An override naming a shape the library cannot
        resolve is discarded in favour of the manifest default -- the rigger
        gets a warning, not a broken build.
        """
        default = self.control_shape_defaults(self.values()).get(
            role, shape_library.DEFAULT_SHAPE
        )
        row = self.shape_rows().get(role, {})
        shape = row.get("shape", "")
        if not shape or not shape_library.has_shape(shape):
            shape = default
        size = row.get("size", "")
        return shape, float(size) if size != "" else 1.0

    # ------------------------------------------------------------- copies
    @classmethod
    def per_copy_defaults(cls) -> dict:
        """``{field name: default}`` for every field declared ``per_copy``."""
        return {name: item.default for name, item in cls.per_copy_fields().items()}

    def copy_rows(self) -> list[dict]:
        """Well-formed copy rows: at least one, each fully populated."""
        return copy_list.normalise(
            self.copies, type(self).per_copy_defaults(), self.name
        )

    def copy_slugs(self) -> list[str]:
        """Every copy's slug, in tab order. ``[""]`` for an untouched module."""
        return [row["slug"] for row in self.copy_rows()]

    def for_copy(self, slug: str) -> "Module":
        """This module as one of its copies sees itself.

        Same class, the copy's per-copy values applied, named after the copy,
        and holding only that copy's row -- so the view is a well-formed
        one-copy module and every manifest call on it returns *bare* names.

        That is the whole trick of this feature: ``draw_guides`` and
        ``build`` receive an ordinary single-copy module, so no module author
        writes anything. The view is a projection, not a handle: editing it
        does not touch the module it came from.
        """
        rows = self.copy_rows()
        row = copy_list.row_for(rows, slug)
        if row is None:
            raise copy_list.CopyError(f"There is no copy '{slug}' on '{self.name}'.")
        settings = self.values()
        settings.update(
            {name: row[name] for name in type(self).per_copy_fields() if name in row}
        )
        settings["copies"] = [dict(row, slug=copy_list.EMPTY_SLUG)]
        return type(self)(
            instance_id=self.instance_id,
            name=copy_list.copy_name(row, self.name),
            side=self.side,
            settings=settings,
        )

    @classmethod
    def pivot_rows(cls, settings=None) -> list[dict]:
        """The pivot-preset rows from ``settings`` (or the field default)."""
        if settings is None:
            return [dict(row) for row in cls.pivot_presets.default]
        return [dict(row) for row in (settings.get("pivot_presets") or [])]

    @classmethod
    def pivot_guide_roles(cls, settings=None) -> tuple[str, ...]:
        """``pivot_<control>_<label>`` per well-formed row, in row order.

        The role carries the *label*, never the row index: a document stores
        poses by ``(role, index)``, and an index-keyed role would shuffle every
        preset's position between presets the moment a row is reordered or
        removed.
        """
        found = []
        for row in cls.pivot_rows(settings):
            control, label = row.get("control", ""), row.get("label", "")
            if control and label:
                found.append(f"pivot_{control}_{label}")
        return tuple(found)

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
        """Display key: ``name`` for center modules, ``<side>_<name>`` otherwise."""
        return instance_key(self.name, self.side.value)

    def guide_count(self) -> int:
        """Number of multi-role guides to draw; override when a setting drives it."""
        return self.guides.min_count

    def expected_guides(self) -> list[tuple[str, int]]:
        """``(role, index)`` pairs this module wants when drawing fresh guides.

        The layout's pairs first, then one guide per pivot-preset row. A preset
        guide is an ordinary guide in every respect -- it poses, syncs,
        reconciles and round-trips through a ``.trg`` -- so the only thing that
        marks it out is where its role name comes from.
        """
        pairs = self.guides.expand(self.guide_count())
        pairs.extend((role, 0) for role in self.pivot_guide_roles(self.values()))
        return pairs

    # ------------------------------------------------------------ lifecycle
    def validate(self) -> list[str]:
        """Return problems that prevent building (empty list = ok)."""
        pairs = self.guide_pairs or self.expected_guides()
        pivot_roles = set(self.pivot_guide_roles(self.values()))
        problems = list(
            self.guides.validate([p for p in pairs if p[0] not in pivot_roles])
        )
        problems.extend(self._validate_spaces())
        problems.extend(self._validate_pivots())
        return problems

    def warnings(self) -> list[str]:
        """Problems worth showing that must not stop a build.

        Separate from ``validate`` because the builder treats every validation
        problem as fatal. Lowering ``segments`` leaves a row naming a control
        that is no longer built; that must cost the rigger a warning, not the
        rig -- and the row is kept, so raising the count restores the setup
        with its wire intact.
        """
        problems = []
        known = type(self).control_names(self.values())
        for row in self.anim_spaces:
            control, label = row.get("control", ""), row.get("label", "")
            if not control or not label:
                continue
            if control not in known:
                problems.append(
                    f"anim space '{control}_{label}': control '{control}' is "
                    f"not built with the current settings"
                )
        movable = type(self).pivot_control_names(self.values())
        for row in self.pivot_presets:
            control, label = row.get("control", ""), row.get("label", "")
            if not control or not label:
                continue
            if control not in movable:
                problems.append(
                    f"pivot preset '{control}.{label}': control '{control}' has "
                    f"no movable pivot with the current settings"
                )
        for row in self.control_shape_overrides:
            control, shape = row.get("control", ""), row.get("shape", "")
            if not control:
                continue
            if control not in known:
                problems.append(
                    f"control shape '{control}': control is not built with the "
                    f"current settings"
                )
            elif shape and not shape_library.has_shape(shape):
                problems.append(
                    f"control shape '{control}': shape '{shape}' is not in the "
                    f"shape library"
                )
        return problems

    def _validate_spaces(self) -> list[str]:
        """Anim-space rows must derive unique, well-formed port names."""
        problems, seen = [], set()
        for index, row in enumerate(self.anim_spaces):
            control, label = row.get("control", ""), row.get("label", "")
            if not label:
                problems.append(f"anim space row {index + 1}: label is required")
                continue
            name = f"{control}_{label}"
            if name in seen:
                problems.append(
                    f"anim space row {index + 1}: '{name}' is already defined"
                )
            seen.add(name)
        return problems

    def _validate_pivots(self) -> list[str]:
        """Pivot-preset rows must derive unique, well-formed guide roles."""
        problems, seen = [], set()
        for index, row in enumerate(self.pivot_presets):
            control, label = row.get("control", ""), row.get("label", "")
            if not label:
                problems.append(f"pivot preset row {index + 1}: label is required")
                continue
            name = f"{control}.{label}"
            if name in seen:
                problems.append(
                    f"pivot preset row {index + 1}: '{name}' is already defined"
                )
            seen.add(name)
        return problems

    def draw_guides(self, ctx) -> None:
        """Create the default guide layout through ``ctx``."""
        raise NotImplementedError

    def draw_all_guides(self, draft) -> None:
        """Everything a fresh draw creates: the module's guides, then its presets.

        The draw path calls this, not ``draw_guides``: preset guides follow a
        settings table rather than the layout, so no module author should have
        to remember to draw them.
        """
        self.draw_guides(draft)
        self._draw_pivot_guides(draft)

    def _draw_pivot_guides(self, draft) -> None:
        """One marker guide per pivot-preset row, at its control's anchor guide.

        Stacked on the anchor is deliberate: an unplaced preset should look
        unplaced, and moving the anchor carries its presets along.
        """
        settings = self.values()
        for row in self.pivot_rows(settings):
            control, label = row.get("control", ""), row.get("label", "")
            if not control or not label:
                continue
            anchor_role = self.pivot_controls.get(control)
            anchor = draft.created.get((anchor_role, 0)) if anchor_role else None
            if anchor is None:
                continue  # a stale row; Module.warnings() reports it
            draft.joint(
                f"pivot_{control}_{label}",
                tuple(anchor.world_position),
                parent=anchor,
                marker=True,
            )

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
