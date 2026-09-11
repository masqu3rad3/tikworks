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
    #: Controller roles this module builds. What each rigger-facing section
    #: offers is named separately below; tweak controllers are excluded from
    #: all of them by construction, since ``rig.tweak_control`` parents them
    #: under their main.
    controls: tuple[str, ...] = ()
    #: Controller roles that may host an animation space. Empty means *every*
    #: control -- the one manifest entry whose default is "all", because
    #: hosting a space is something any controller can do, so a module narrows
    #: rather than opts in. A pivot and a shape are offers a module makes.
    space_controls: tuple[str, ...] = ()
    #: Controller roles that get a movable pivot, mapped to the guide their
    #: preset guides hang under. Declaring an entry is what makes the control
    #: movable, the way declaring an input is what makes its socket. The anchor
    #: is the module author's business, never the rigger's, so it is a class
    #: attribute rather than a table column.
    #:
    #: A value is a guide *reference*: ``"hand"`` means that role at index 0,
    #: and ``("segment", 2)`` addresses the third guide of a multi -- which is
    #: what lets a module whose controls depend on a setting declare a pivot
    #: for each of them.
    pivot_controls: dict[str, object] = {}
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
        #: The only shared field on ``Module``. Everything else -- settings,
        #: inputs, spaces, pivots and shapes -- belongs to a copy, so a copy
        #: is a whole module's worth of authoring and the list itself is the
        #: one thing that cannot be.
        shared=True,
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
            Column("control", "choice", choices_from="space_control_names"),
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
        rows_from="shape_control_names",
        columns=(
            Column("control", "choice", choices_from="shape_control_names"),
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
        """The anim-space rows from ``settings`` (or the field default).

        Deliberately unfiltered. A row naming a control the module no longer
        offers keeps its port, because **the port is what carries the wire**:
        lowering ``segments`` and raising it again has to restore the setup
        intact. ``warnings()`` tells the rigger, and the builder skips the row
        with a warning when no controller turns up for it -- neither of which
        costs the connection.
        """
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
    def inputs_for_copy(cls, settings=None) -> list[str]:
        """One copy's inputs: the declared ones, then its anim-space ports."""
        return [item.name for item in cls.inputs] + [
            item.name for item in cls.space_inputs(settings)
        ]

    @classmethod
    def input_names(cls, settings=None) -> list[str]:
        """Inputs an instance exposes, qualified per copy.

        A copy attaches where it likes -- five fingers may hang off five
        different things -- so each copy has its own port rather than sharing
        the module's. Qualified the same way outputs and controls are, which
        keeps ``entry.inputs`` an ordinary flat dict that every existing
        reader walks unchanged.
        """
        shared = {item.name for item in cls.inputs if item.shared}
        found: list[str] = []
        for slug, one in cls._copy_settings(settings):
            for name in cls.inputs_for_copy(one):
                # A shared input is the module's: one port, wired once.
                port = name if name in shared else cls.qualify(slug, name)
                if port not in found:
                    found.append(port)
        return found

    @classmethod
    def primary_input(cls) -> Optional[Input]:
        """The input marked primary, else the first declared one, else None."""
        for item in cls.inputs:
            if item.primary:
                return item
        return cls.inputs[0] if cls.inputs else None

    @classmethod
    def get_input(cls, name: str, settings=None) -> Optional[Input]:
        """Find a declared input, or one derived from an anim-space row.

        ``name`` may be qualified (``c1_root``); the copy prefix is stripped
        first, and an unknown copy resolves to nothing.
        """
        if any(item.name == name and item.shared for item in cls.inputs):
            return next(item for item in cls.inputs if item.name == name)
        slug = cls.slug_of(name)
        if slug:
            known = {item[0] for item in cls._copy_settings(settings)}
            if slug not in known:
                return None
            name = name[len(slug) + 1 :]
        found = next((item for item in cls.inputs if item.name == name), None)
        if found is not None:
            # A shared input has no qualified form: ``c1_world`` names no
            # port, and resolving it would let a wire land nowhere.
            return None if (slug and found.shared) else found
        return next(
            (item for item in cls.space_inputs(settings) if item.name == name), None
        )

    @classmethod
    def outputs_for_copy(cls, settings: Optional[dict] = None) -> tuple[str, ...]:
        """Outputs *one copy* exposes.

        Override when a setting adds outputs (chain segments, say). The public
        ``output_names`` repeats this across the module's copies and qualifies
        each name, so an author writes single-copy code and never sees a copy.
        """
        return tuple(cls.outputs)

    @classmethod
    def controls_for_copy(cls, settings: Optional[dict] = None) -> tuple[str, ...]:
        """Controller roles *one copy* builds.

        Override when a setting drives them -- ``fkchain`` builds one per
        segment. This is the shape of ``outputs_for_copy`` on purpose: one
        idiom for a manifest entry whose set depends on settings, not two.
        """
        return tuple(cls.controls)

    @classmethod
    def space_controls_for_copy(
        cls, settings: Optional[dict] = None
    ) -> tuple[str, ...]:
        """Controller roles of *one copy* that may host an animation space.

        Falls back to every control the copy builds, which is what makes an
        undeclared module behave exactly as it did before this hook existed.
        """
        if cls.space_controls:
            return tuple(cls.space_controls)
        return tuple(cls.controls_for_copy(settings))

    @classmethod
    def pivot_controls_for_copy(cls, settings: Optional[dict] = None) -> dict:
        """Controller roles of *one copy* with a movable pivot, and their anchors.

        Returns the whole mapping rather than its keys: an anchor a computed
        module works out from its settings has nowhere else to come from, and
        dropping it here is what stopped ``fkchain`` and ``ribbon`` declaring
        a pivot at all.
        """
        return dict(cls.pivot_controls)

    @classmethod
    def control_shape_defaults_for_copy(
        cls, settings: Optional[dict] = None
    ) -> dict[str, str]:
        """Default shape per control role, for *one copy*."""
        return dict(cls.control_shapes)

    @classmethod
    def control_orient_defaults_for_copy(cls, settings: Optional[dict] = None) -> dict:
        """Shape rotation per control role in degrees, for *one copy*."""
        return dict(cls.control_orients)

    # -- the public manifest: the hooks above, repeated across the copies ---
    @classmethod
    def _copy_settings(cls, settings: Optional[dict] = None) -> list:
        """``[(slug, one-copy settings)]`` for a module-level settings dict.

        Each entry is a settings dict a ``*_for_copy`` hook can be called
        with: the copy's per-copy values folded in, and ``copies`` holding
        only that row under the empty slug. Tables that address controls by
        name are sliced to this copy and de-qualified, so a hook never sees
        another copy's rows and never sees a prefix it would qualify twice.
        """
        settings = dict(settings or {})
        defaults = cls.per_copy_defaults(settings)
        rows = copy_list.normalise(settings.get("copies"), defaults, "")
        found = []
        for row in rows:
            one = dict(settings)
            one.update({name: row[name] for name in defaults if name in row})
            one["copies"] = [dict(row, slug=copy_list.EMPTY_SLUG)]
            found.append((row["slug"], one))
        return found

    @staticmethod
    def slug_of(control: str) -> str:
        """The copy slug a qualified control name carries, or ``""``.

        Recognised by shape (``c`` followed by digits) rather than by looking
        the copy up, because this has to answer for a settings dict alone --
        the same dict a classmethod is handed with no instance in sight.
        """
        head = control.split("_", 1)[0]
        return head if head[:1] == "c" and head[1:].isdigit() else ""

    @classmethod
    def output_names(cls, settings: Optional[dict] = None) -> tuple[str, ...]:
        """Outputs an instance exposes, qualified per copy."""
        return tuple(
            cls.qualify(slug, name)
            for slug, one in cls._copy_settings(settings)
            for name in cls.outputs_for_copy(one)
        )

    @classmethod
    def control_names(cls, settings: Optional[dict] = None) -> tuple[str, ...]:
        """Controller roles an instance builds, qualified per copy."""
        return tuple(
            cls.qualify(slug, name)
            for slug, one in cls._copy_settings(settings)
            for name in cls.controls_for_copy(one)
        )

    @classmethod
    def space_control_names(cls, settings: Optional[dict] = None) -> tuple[str, ...]:
        """Controller roles that may host an animation space, qualified per copy."""
        return tuple(
            cls.qualify(slug, name)
            for slug, one in cls._copy_settings(settings)
            for name in cls.space_controls_for_copy(one)
        )

    @classmethod
    def shape_control_names(cls, settings: Optional[dict] = None) -> tuple[str, ...]:
        """Controller roles with a definable shape, qualified per copy.

        The keys of ``control_shape_defaults`` rather than a list of its own:
        a control with a declared default is shape-editable, and a second list
        would repeat ``controls`` line for line and then drift from it.
        Ordered by the control manifest so the table's rows are stable.
        """
        defaults = cls.control_shape_defaults(settings)
        return tuple(name for name in cls.control_names(settings) if name in defaults)

    @classmethod
    def pivot_control_names(cls, settings: Optional[dict] = None) -> tuple[str, ...]:
        """Controller roles with a movable pivot, qualified per copy."""
        return tuple(
            cls.qualify(slug, name)
            for slug, one in cls._copy_settings(settings)
            for name in cls.pivot_controls_for_copy(one)
        )

    @classmethod
    def pivot_anchor(cls, control: str, settings: Optional[dict] = None):
        """The ``(guide role, index)`` a control's preset guides hang under.

        ``None`` if the control has no movable pivot. ``control`` may be
        qualified (``c1_ik``); the copy's own anchors are consulted, because
        two copies of a chain anchor to different guides.
        """
        slug = cls.slug_of(control)
        bare = control[len(slug) + 1 :] if slug else control
        for found, one in cls._copy_settings(settings):
            if found != slug:
                continue
            anchor = cls.pivot_controls_for_copy(one).get(bare)
            if anchor is None:
                return None
            return (anchor, 0) if isinstance(anchor, str) else tuple(anchor)
        return None

    @classmethod
    def control_shape_defaults(cls, settings: Optional[dict] = None) -> dict[str, str]:
        """Default shape per control role, keyed by the qualified names."""
        found: dict = {}
        for slug, one in cls._copy_settings(settings):
            for name, shape in cls.control_shape_defaults_for_copy(one).items():
                found[cls.qualify(slug, name)] = shape
        return found

    @classmethod
    def control_orient_defaults(cls, settings: Optional[dict] = None) -> dict:
        """Shape rotation per control role, keyed by the qualified names."""
        found: dict = {}
        for slug, one in cls._copy_settings(settings):
            for name, orient in cls.control_orient_defaults_for_copy(one).items():
                found[cls.qualify(slug, name)] = orient
        return found

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
    def per_copy_defaults(cls, settings: Optional[dict] = None) -> dict:
        """``{field name: value}`` to seed a copy row that lacks one.

        The *module's current value* where the settings carry one, and only
        then the field default. This is what makes an existing document
        already a valid one-copy module: a ``.tr`` written before copies
        existed holds ``segments`` at the top level and no ``copies`` at all,
        and its single implicit copy has to inherit that number rather than
        silently reverting to the class default.
        """
        settings = settings or {}
        return {
            name: settings.get(name, item.default)
            for name, item in cls.per_copy_fields().items()
        }

    def copy_rows(self) -> list[dict]:
        """Well-formed copy rows: at least one, each fully populated."""
        return copy_list.normalise(
            self.copies, type(self).per_copy_defaults(self.values()), self.name
        )

    @staticmethod
    def qualify(slug: str, name: str) -> str:
        """``("", "root")`` -> ``root``; ``("c1", "root")`` -> ``c1_root``.

        The first copy is bare, which is what makes an existing document
        already valid and what stops a second copy from disturbing it.
        """
        return name if not slug else f"{slug}_{name}"

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
        row = copy_list.row_for(self.copy_rows(), slug)
        if row is None:
            raise copy_list.CopyError(f"There is no copy '{slug}' on '{self.name}'.")
        # Through _copy_settings, so the view also gets its own slice of the
        # control-keyed tables rather than the module's whole set.
        settings = next(
            one
            for found, one in type(self)._copy_settings(self.values())
            if found == slug
        )
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

    def pivot_labels(self, role: str) -> list[str]:
        """Preset labels declared for ``role``, in row order.

        On ``Module`` rather than on ``ModuleRig`` because the builder asks
        the same question to decide whether to make a pivot at all, and that
        is a question about settings, not about a scene.
        """
        return [
            row["label"]
            for row in self.pivot_rows(self.values())
            if row.get("control") == role and row.get("label")
        ]

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

        Each copy's layout in turn, then that copy's pivot-preset guides, with
        every role qualified by the copy's slug. A preset guide is an ordinary
        guide in every respect -- it poses, syncs, reconciles and round-trips
        through a ``.trg`` -- so the only thing that marks it out is where its
        role name comes from.

        A one-copy module returns exactly what it always returned: the first
        slug is empty, so its roles carry no prefix.
        """
        pairs: list[tuple[str, int]] = []
        for slug in self.copy_slugs():
            view = self.for_copy(slug)
            for role, index in view.guides.expand(view.guide_count()):
                pairs.append((self.qualify(slug, role), index))
            for role in view.pivot_guide_roles(view.values()):
                pairs.append((self.qualify(slug, role), 0))
        return pairs

    # ------------------------------------------------------------ lifecycle
    def validate(self) -> list[str]:
        """Return problems that prevent building (empty list = ok).

        Each copy is checked through its own view against the bare layout,
        which is the only thing that knows what a well-formed copy looks like.
        """
        pairs = self.guide_pairs or self.expected_guides()
        problems: list[str] = []
        for slug in self.copy_slugs():
            view = self.for_copy(slug)
            prefix = f"{slug}_" if slug else ""
            pivot_roles = {
                self.qualify(slug, role)
                for role in view.pivot_guide_roles(view.values())
            }
            mine = [
                (role[len(prefix) :], index)
                for role, index in pairs
                if role not in pivot_roles
                and self.slug_of(role) == slug
                and role.startswith(prefix)
            ]
            for problem in view.guides.validate(mine):
                problems.append(problem if not slug else f"{view.name}: {problem}")
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
        # A copy name is what its controls are called, and the module name is
        # not in them, so two copies sharing a name build over each other.
        seen: set = set()
        for row in self.copy_rows():
            name = copy_list.copy_name(row, self.name)
            if name in seen:
                problems.append(
                    f"two copies are both called '{name}': their controls "
                    f"would collide"
                )
            seen.add(name)
        if len(self.copy_rows()) > 1:
            # Each copy carries its own tables naming its own controls, so
            # each is checked through its own view and told apart by name.
            for slug in self.copy_slugs():
                view = self.for_copy(slug)
                label = copy_list.copy_name(
                    copy_list.row_for(self.copy_rows(), slug), self.name
                )
                problems.extend(f"{label}: {item}" for item in view.warnings())
            return problems
        spaceable = type(self).space_control_names(self.values())
        for row in self.anim_spaces:
            control, label = row.get("control", ""), row.get("label", "")
            if not control or not label:
                continue
            if control not in spaceable:
                problems.append(
                    f"anim space '{control}_{label}': control '{control}' is "
                    f"not offered an animation space with the current settings"
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
        shapeable = type(self).shape_control_names(self.values())
        for row in self.control_shape_overrides:
            control, shape = row.get("control", ""), row.get("shape", "")
            if not control:
                continue
            if control not in shapeable:
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

        It is also where copies happen. Each one draws through its own view
        inside ``draft.for_copy``, which qualifies the roles and hands the
        copy its own root, so ``draw_guides`` sees an ordinary single-copy
        module and names its roles bare.
        """
        for slug in self.copy_slugs():
            view = self.for_copy(slug)
            with draft.for_copy(slug, view):
                view.draw_guides(draft)
                view._draw_pivot_guides(draft)

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
            anchor_ref = type(self).pivot_anchor(control, settings)
            # Through ``made``, which qualifies with the copy currently
            # drawing: a bare lookup finds the first copy's anchor whichever
            # copy is asking.
            anchor = draft.made(*anchor_ref) if anchor_ref else None
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
