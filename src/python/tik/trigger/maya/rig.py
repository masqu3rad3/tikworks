"""What a module draws guides with, and what it builds through.

``GuideDraft`` and ``ModuleRig`` own naming, tagging, group placement and
registration. tik.maya owns the mechanism: a helper lives here only when it
removes naming, tagging, placement or registration boilerplate, so
``tm.MatrixConstraint.create(...)`` and friends stay visible in module code.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Optional, Sequence

import tik.maya as tm
from tik.core.control_shapes import rotate_data
from tik.core.side import Side
from tik.maya import naming
from tik.maya.roles.controller import Controller
from tik.trigger.core import shapes as shape_library
from tik.trigger.core.exceptions import GuideError
from tik.trigger.core.manifest import TIERS, GuideKind, instance_key
from tik.trigger.core.module import Module
from tik.trigger.core.schemas import ModuleInstance
from tik.trigger.guides.nodes import (
    MARKER_FAN_FALLBACK,
    MARKER_FAN_FRACTION,
    SIDE_COLORS,
    create_guide_node,
)

from . import tags

TWEAK_SCALE = 0.875
"""How much of its master's size a tweak is drawn at.

A tweak is a finer grip on the *same* control, not a different one, so it
takes the master's shape and reads as that shape one size down.
"""


def mirror_orient(orient):
    """The right side's version of a shape rotation authored for the left.

    The right side is mirrored *by behaviour*: its joints carry a 180 degree
    roll about X, so a shape authored for the left arrives rolled. Undoing
    that is conjugating the rotation by that roll -- ``Rx(180) . R . Rx(180)``
    -- which works out to negating Y and Z and leaving X alone. Measured: an
    FK bone runs along local +X on the left and local -X on the right, and
    ``Rz(-90)`` / ``Rz(+90)`` are what put a shape's normal on each.

    Negating Z alone would happen to be right for the bone-alignment case and
    wrong the moment a module declares a turn about X or Y.
    """
    if not orient:
        return orient
    x, y, z = orient
    return (x, -y, -z)


def _curve_for(shape, orient=None):
    """Curve data for a shape name, resolved through the *pinned* library.

    The data, not the name: ``Controller.create`` and ``Controller.set_shape``
    both resolve a name through ``ControlShapeLibrary.get_instance()``, the
    unpinned singleton that searches the artist's own folder -- the exact hole
    the pinned library exists to close. Falls back to the name when the
    library cannot resolve it, so the caller still gets tik.maya's warning
    rather than a controller with no shape at all.

    ``orient`` is baked into the returned CVs, so the controller's transform
    is never touched and stays aligned to its joint.
    """
    data = shape
    if isinstance(shape, str):
        data = shape_library.library().load(shape)
        if not data:
            return shape
    return rotate_data(data, orient) if orient else data


def node_of(value):
    """The Transform behind a role (a Controller), or ``value`` unchanged.

    Roles proxy attribute reads to their transform but are not Transform
    instances, so tik.maya APIs that type-check or assign reject them. The rig
    normalises its own arguments so module code can pass either.
    """
    return getattr(value, "transform", value)


@dataclass
class RigGroups:
    """The four groups created for every module instance, under ``limb``.

    ``socket`` holds input attach transforms driven by parent module outputs.
    ``control`` holds controllers and their offset/space groups, nothing else.
    ``rig`` holds the puppet: IK/FK chains, handles, math, helpers.
    ``bind`` holds deform/export joints only, and is empty when the module is
    connected to a parent (its joints are created in the parent's hierarchy).
    """

    limb: Any = None  # top group of the module
    socket: Any = None
    control: Any = None
    rig: Any = None
    bind: Any = None


class GuideDraft:
    """Creates tagged guide joints for ``Module.draw_guides``."""

    def __init__(self, module, holder, parent_node=None, parents=None) -> None:
        self.module = module
        self.side = module.side
        self.side_mult = module.side.multiplier
        self.holder = holder
        self.parent_node = parent_node
        #: ``{slug: joint}`` -- where each copy's root hangs. Each copy has
        #: its own primary input, so each has its own producer.
        self._parents = dict(parents or {})
        self._default_parent = parent_node
        self.created: dict[tuple[str, int], tm.Joint] = {}
        self.root: Optional[tm.Joint] = None
        #: Slug of the copy currently drawing, and the view drawing it.
        self._slug = ""
        self._drawing = module

    @contextmanager
    def for_copy(self, slug: str, view):
        """Draw one copy: qualify its roles, and give it its own root.

        ``view`` is the per-copy module, so the joints are named after the
        copy and ``attrs_for_role`` is asked about bare roles. ``root`` resets
        because each copy is its own chain -- without that, copy two's first
        joint would parent under copy one's root.
        """
        was = (self._slug, self._drawing, self.root, self.parent_node)
        self._slug, self._drawing, self.root = slug, view, None
        self.parent_node = self._parents.get(slug, self._default_parent)
        try:
            yield self
        finally:
            self._slug, self._drawing, self.root, self.parent_node = was

    def made(self, role: str, index: int = 0):
        """A joint this draft already created, in the *current copy's* scope.

        ``created`` is keyed by the qualified role, so looking one up by its
        bare name finds the first copy's joint whichever copy is drawing --
        which is how every copy's pivot guides ended up piled under copy
        one's anchor.
        """
        return self.created.get((Module.qualify(self._slug, role), index))

    def joint(
        self,
        role: str,
        position: Sequence[float],
        *,
        index: int = 0,
        parent: Any = None,
    ) -> tm.Transform:
        """Create one tagged guide; the first one becomes the copy's root.

        There is no ``radius`` and no ``marker``. What a guide looks like is a
        consequence of what it *is*, and what it is comes from the module's
        ``GuideLayout`` -- so no call site anywhere picks a number.
        """
        layout = type(self._drawing).guides
        kind = layout.kind_for(role, is_root=self.root is None)
        return self._create(role, position, kind, index=index, parent=parent)

    def reference(
        self,
        role: str,
        position: Sequence[float],
        *,
        index: int = 0,
        parent: Any = None,
    ) -> tm.Transform:
        """Create a reference guide for a role no layout declares.

        Pivot preset guides are made by the framework from a settings table
        rather than declared in a ``GuideLayout``, so they name their kind here
        instead of being looked up. Module authors never call this.
        """
        return self._create(
            role, position, GuideKind.REFERENCE, index=index, parent=parent
        )

    def _create(self, role, position, kind, *, index=0, parent=None) -> tm.Transform:
        key = (Module.qualify(self._slug, role), index)
        if key in self.created:
            raise GuideError(f"Guide '{key[0]}' [{index}] created twice.")
        is_root = self.root is None
        if parent is None:
            parent = self.parent_node if is_root else self.root
            if parent is None:
                parent = self.holder
        node = create_guide_node(
            self._drawing,
            role,
            position,
            kind=kind,
            index=index,
            parent=parent,
            tag_role=key[0],
        )
        for declared in self._drawing.attrs_for_role(role):
            node[declared.name].create(
                "float", default=declared.default, keyable=declared.keyable
            )
        self.created[key] = node
        if is_root:
            self.root = node
        return node

    def chain_step(self, anchor) -> tuple[tuple[float, float, float], float]:
        """Unit direction and step length for fanning markers off ``anchor``.

        The direction is the anchor's own incoming bone (parent -> anchor), so
        a fan off a hand runs along the hand's forward axis -- the direction a
        roll actually travels. A root has no incoming bone, so it falls back to
        the module's aim axis.
        """
        parent = anchor.parent
        if parent is not None:
            # world_position is an MVector, so this is the same idiom the
            # twist and limb systems use rather than a third spelling of it.
            vector = anchor.world_position - parent.world_position
            length = vector.length()
            if length > 1e-6:
                vector.normalize()
                return tuple(vector), MARKER_FAN_FRACTION * length
        return (float(self.side_mult), 0.0, 0.0), MARKER_FAN_FALLBACK


class ModuleRig:
    """Everything a module needs while building in Maya."""

    def __init__(
        self,
        module,
        instance: ModuleInstance,
        scaffold,
        guide_nodes: dict,
        bind_parent=None,
        shared=None,
        group_name: str = "",
    ) -> None:
        self.module = module
        self.instance = instance
        self.side = module.side
        self.side_mult = module.side.multiplier
        self.scaffold = scaffold
        # trigger_grp: the world-space anchor every module hangs under
        self.rig_root = scaffold.trigger
        self._guides = guide_nodes  # (role, index) -> Joint
        self.outputs: dict[str, Any] = {}
        self.attachments: dict[str, Any] = {}
        self.controllers: list[Controller] = []
        #: ``{control role: pivot node}``, movable or not. The not-movable
        #: ones are groups and never reach ``controllers``, so this is the
        #: only record that answers "does this control already have a pivot".
        self._pivots: dict = {}
        self.deform_joints: list[tm.Joint] = []
        #: The name the four groups are built under. A module's copies share
        #: one set of groups, so this is the *module's* name while
        #: ``instance.name`` is the copy's -- which is what keeps the groups
        #: ``L_fkchain_grp`` while the controls stay ``L_index_fk0``.
        self.group_name = group_name or instance.name
        # The four groups belong to the *module*, so a later copy builds into
        # the ones already standing rather than a second set beside them.
        # Its sockets do not: a socket is a copy's attach frame, and
        # ``rig.socket(match=...)`` aligns it to that copy's own guide -- one
        # shared socket would be dragged to wherever the last copy's guide
        # is, taking every rig already parented under it along.
        self.groups = self._create_groups() if shared is None else shared
        self._create_sockets()
        # Resolved by the builder from the connected input's producer, so bind
        # joints are created in their final hierarchy position.
        self.bind_parent = bind_parent if bind_parent is not None else self.groups.bind

    def _create_sockets(self) -> None:
        """One transform per declared input, in ``socket_grp``.

        Declaring an input is what creates its socket, so a module cannot
        forget to. Space inputs are skipped: they feed a ``SpaceSwitch`` on a
        controller, not a matrix attach, so they have nothing to receive.

        A socket is a transform, not a joint: its whole job is receiving a
        matrix from the producer's output. Joints in ``socket_grp`` would be a
        third joint set beside the puppet and the deform skeleton, and would
        turn up in every skin-bind dialog and joint scan for no gain.
        """
        for declared in self.module.inputs:
            if declared.kind == "space":
                continue
            self.attachments[declared.name] = tm.Transform.create(
                name=self.name(declared.name, suffix="socket"),
                parent=self.groups.socket.long_name,
            )

    # ------------------------------------------------------------- groups
    @property
    def group_key(self) -> str:
        """The *module's* display key, as the visibilities enum names it."""
        return instance_key(self.group_name, self.side.value)

    def group_label(self, *tokens, suffix=None) -> str:
        """A name in the *module's* namespace rather than the copy's.

        The four groups and the sockets belong to the module and are shared
        by its copies, so they cannot be named after whichever copy happened
        to build first.
        """
        return naming.format_name(
            *tokens, side=self.side.value, prefix=self.group_name, suffix=suffix
        )

    def _create_groups(self) -> RigGroups:
        limb = tm.Transform.create(
            name=self.group_label(suffix="grp"), parent=self.rig_root.long_name
        )
        socket = tm.Transform.create(
            name=self.group_label("socket", suffix="grp"), parent=limb.long_name
        )
        control = tm.Transform.create(
            name=self.group_label("control", suffix="grp"), parent=limb.long_name
        )
        rig = tm.Transform.create(
            name=self.group_label("rig", suffix="grp"), parent=limb.long_name
        )
        bind = tm.Transform.create(
            name=self.group_label("bind", suffix="grp"), parent=limb.long_name
        )

        self.separator(limb, "visibility_")
        limb["controlVisibility"].create("bool", default=True) >> control["visibility"]
        limb["rigVisibility"].create("bool", default=False) >> rig["visibility"]
        limb["bindVisibility"].create("bool", default=True) >> bind["visibility"]
        for group in (limb, socket, control, rig, bind):
            for channel in tm.TRANSFORM_CHANNELS:
                plug = group[channel]
                plug.locked = True
                plug.visible = False
        tags.tag(
            limb,
            **{
                tags.KIND: tags.RIG,
                tags.MODULE: self.module.module_type,
                tags.INSTANCE: self.instance.instance_id,
                tags.NAME: self.group_name,
                tags.SIDE: self.side.value,
            },
        )
        return RigGroups(limb=limb, socket=socket, control=control, rig=rig, bind=bind)

    # ------------------------------------------------------------- guides
    def guide(self, role: str, index: int = 0) -> tm.Joint:
        """The guide joint for ``role``/``index``; raises when the module has none."""
        try:
            return self._guides[(role, index)]
        except KeyError:
            raise GuideError(
                f"'{self.instance.name}' has no guide '{role}' [{index}]."
            ) from None

    def guides(self, *roles: str) -> list[tm.Joint]:
        """One guide node per named role, in the order given."""
        return [self.guide(role) for role in roles]

    def chain(self, role: str) -> list[tm.Joint]:
        """Every guide of a multi role, ordered by index."""
        pairs = sorted(key for key in self._guides if key[0] == role)
        return [self._guides[key] for key in pairs]

    # ------------------------------------------------------------- naming
    def name(self, *tokens, suffix: Optional[str] = None) -> str:
        """``<name>_<tokens>_<side>_<suffix>``, this module's naming convention."""
        return naming.format_name(
            *tokens, side=self.side.value, prefix=self.instance.name, suffix=suffix
        )

    def group(self, *tokens, under="rig") -> tm.Transform:
        """A named group placed under one of the module's groups (or a node)."""
        parent = (
            getattr(self.groups, under) if isinstance(under, str) else node_of(under)
        )
        return tm.Transform.create(
            name=self.name(*tokens, suffix="grp"),
            parent=parent.long_name if hasattr(parent, "long_name") else parent,
        )

    def socket(self, input_name: str, *, match=None) -> tm.Transform:
        """The socket for a declared input, optionally aligned to ``match``."""
        try:
            node = self.attachments[input_name]
        except KeyError:
            raise GuideError(
                f"'{self.module.module_type}' does not declare input '{input_name}'."
            ) from None
        if match is not None:
            node.align_to(node_of(match))
        return node

    # ------------------------------------------------------------ outputs
    def separator(self, node, name: str) -> tm.Plug:
        """A locked ``----------`` row in the channel box, above a group of attrs.

        Purely a channel-box layout convention, which is why it lives here and
        not in tik.maya: the rig decides how an animator's attributes are laid
        out. Accepts a controller or any node.

        Args:
            node: The node (or role) carrying the attribute.
            name: Attribute name for the row, e.g. ``"stretch_"``.

        Returns:
            tm.Plug: The separator plug.
        """
        plug = node_of(node)[name].create("enum", items=["----------"], keyable=False)
        plug.visible = True
        plug.locked = True
        return plug

    def controller(
        self,
        name: str,
        *,
        size: float = 1.0,
        parent: Any = None,
        color: Any = None,
        match: Any = None,
        mirror: str = "world",
        offset: bool = True,
        tier: Optional[str] = "primary",
    ) -> Controller:
        """A tagged controller with its offset group.

        The shape is *not* an argument: it comes from the module's manifest,
        which the rigger overrides per instance. Passing one here would keep a
        second place a default could hide, and the ground rules already require
        the manifest to equal what ``build()`` creates.

        ``match`` snaps it to a node; ``mirror`` is ``"behaviour"`` (FK-like,
        follows its joint) or ``"world"`` (IK/world-aligned), recorded for a
        pose-mirror tool. ``offset=False`` skips the offset group, for a
        controller that hangs under another one (a tweak). ``tier`` places the
        control in the rig's visibilities enum (one of ``TIERS``); ``None``
        leaves it untiered, which is what a tweak wants.
        """
        if tier is not None and tier not in TIERS:
            raise GuideError(
                f"'{name}': tier must be one of {TIERS} or None, got {tier!r}."
            )
        parent = parent if parent is not None else self.groups.control
        shape, size_multiplier = self.module.resolve_control_shape(name)
        effective_size = size * size_multiplier
        orient = self.module.control_orient_defaults(self.module.values()).get(name)
        if orient and self.side is Side.RIGHT:
            orient = mirror_orient(orient)
        controller = Controller.create(
            name=self.name(name, suffix="ctrl"),
            shape=_curve_for(shape, orient),
            size=effective_size,
            color=color if color is not None else SIDE_COLORS[self.side.value],
            parent=(
                node_of(parent).long_name
                if hasattr(node_of(parent), "long_name")
                else parent
            ),
        )
        if match is not None:
            controller.transform.align_to(node_of(match))
        tags.tag(
            controller.transform,
            **{
                tags.KIND: tags.CONTROLLER,
                tags.INSTANCE: self.instance.instance_id,
                tags.ROLE: name,
                tags.MIRROR: mirror,
            },
        )
        if tier is not None:
            controller.transform.meta[tags.TIER] = tier
        controller.offset = (
            controller.create_offset_group(name=self.name(name, suffix="offset"))
            if offset
            else None
        )
        # What this control ended up looking like, so a tweak can take the
        # same shape at a smaller size without re-deriving any of it.
        controller.shape_name = shape
        controller.shape_size = effective_size
        controller.shape_orient = orient
        self.controllers.append(controller)
        return controller

    def tweak_control(
        self,
        main: Controller,
        *,
        size: Optional[float] = None,
        shape: Optional[str] = None,
        scale: float = TWEAK_SCALE,
    ) -> Controller:
        """Create a secondary tweak controller under ``main``.

        The tweak is a child of the main, so it rides along when the animator
        moves the main control instead of being left behind. Downstream rig
        connections read the tweak, not the main.

        It takes the main's *resolved* shape -- the rigger's override
        included -- at ``scale`` of its size, because a tweak is a finer grip
        on the same control rather than a different one. ``shape`` and ``size``
        override that for a caller that wants something else.
        """
        role = main.transform.meta.get(tags.ROLE, main.transform.name)
        # A tweak is not in the control manifest -- rig.tweak_control parents
        # it under its main -- so it has no role of its own to resolve, and
        # reads what the main resolved to instead.
        shape = shape if shape is not None else getattr(main, "shape_name", "Circle")
        if size is None:
            size = getattr(main, "shape_size", 1.0) * scale
        # The master's turn too: a bone-aligned control wants a bone-aligned
        # tweak, and the master has already had its side mirrored in.
        orient = getattr(main, "shape_orient", None)
        tweak = self.controller(
            f"{role}_tweak",
            size=size,
            parent=main,
            match=main,
            mirror=main.meta.get(tags.MIRROR, tags.WORLD),
            offset=False,
            tier=None,
        )
        tweak.set_shape(_curve_for(shape, orient), size=size)
        tweak.shape_name = shape
        tweak.shape_size = size
        tweak.shape_orient = orient
        visible = main.transform["tweakVis"].create(
            "bool", default=False, keyable=False
        )
        visible.visible = True
        visible >> tweak.transform["visibility"]
        # The tweak inherits whatever the main has locked: an animator should
        # not reach a channel through the tweak that the main denies them.
        for channel in tm.ALL_CHANNELS:
            if not main.transform[channel].locked:
                continue
            plug = tweak.transform[channel]
            plug.locked = True
            plug.visible = False
        return tweak

    def pivot_control(
        self,
        main: Controller,
        *,
        movable: bool = True,
        size: Optional[float] = None,
        shape: str = "Sphere",
    ) -> Any:
        """Give ``main`` a pivot at the point its presets name, for its role.

        The pivot node is a plain child of ``main``, which is exactly where it
        belongs: a child at the local position of ``rotatePivot`` is the
        rotation's fixed point, so it sits on the pivot and follows the control
        with no space maths.

        ``movable`` is what the *animator* gets, and it is a separate question
        from which presets exist. With it the node is a controller: a marker to
        grab, a ``showPivot`` bool on ``main`` to reveal it, and a manual
        translate that adds on top of the preset, so an adjustment survives a
        preset change. Without it the node is a plain group -- nothing to
        select, nothing to key, and no ``showPivot``, because there is nothing
        to show. Named positions to switch between and a pivot to drag are two
        features, and a rigger who offers the first has not thereby agreed to
        the second.

        Index 0 of the enum is ``default`` -- the control's own origin, the way
        ``world`` is always index 0 of a space switch. With no rows there is no
        enum at all, only a pivot the animator moves by hand.

        Args:
            main: The controller whose pivot this is.
            movable: Build an animator-facing pivot controller rather than a
                plain group. Defaults to True, which is what a module calling
                this itself is asking for; the builder seam passes the rigger's
                answer instead.
            size: Shape scale (defaults to 1.0). Unused when not movable.
            shape: Control shape name. A pivot is a point, and a sphere is the
                one shape that reads the same from every angle. Unused when not
                movable.

        Returns:
            Controller | tm.Transform: The pivot controller, or the group that
            stands in for it when ``movable`` is False.

        Raises:
            GuideError: If ``main``'s role is not in the module's
                ``pivot_controls`` -- a module-author error, and a silent one
                would leave the rigger's preset rows pointing at nothing.
        """
        role = main.transform.meta.get(tags.ROLE, main.transform.name)
        if role not in self.module.pivot_controls_for_copy(self.module.values()):
            raise GuideError(
                f"'{self.module.module_type}' does not declare a movable pivot "
                f"for control '{role}'."
            )
        labels = self._pivot_labels(role)
        if not movable:
            # A fresh child of main starts at local zero, which *is* main's
            # pivot -- nothing to match. No offset group either: with no
            # manual translate riding on top, the preset drives this node
            # itself and the two nodes collapse into one.
            pivot = tm.Transform.create(
                name=self.name(f"{role}_pivot", suffix="grp"),
                parent=main.transform.long_name,
            )
            if labels:
                self._wire_pivot_presets(main, role, labels, holder=pivot, target=pivot)
            main.drive_pivot(pivot["translate"], scale=True)
            self._pivots[role] = pivot
            return pivot
        pivot = self.controller(
            f"{role}_pivot",
            size=size if size is not None else 1.0,
            parent=main,
            match=main,
            mirror=main.meta.get(tags.MIRROR, tags.WORLD),
            tier=None,
        )
        # A pivot controller is the same species as a tweak: not in the
        # control manifest, so it has no role to key an override on.
        pivot.set_shape(_curve_for(shape), size=size if size is not None else 1.0)
        pivot.shape_name = shape
        pivot.shape_size = size if size is not None else 1.0
        pivot.shape_orient = None
        show = main.transform["showPivot"].create("bool", default=False, keyable=False)
        show.visible = True
        show >> pivot.offset["visibility"]

        if labels:
            self._wire_pivot_presets(
                main, role, labels, holder=pivot.transform, target=pivot.offset
            )
        main.drive_pivot(
            pivot.offset["translate"] + pivot.transform["translate"], scale=True
        )
        self._pivots[role] = pivot
        return pivot

    def pivot_node(self, role: str) -> Any:
        """The pivot this build made for ``role``, movable or not, else None.

        Not ``controller_by_role(f"{role}_pivot")``: a pivot that is not
        movable is a group and never reaches ``self.controllers``, so asking
        for a controller would report "no pivot" and build a second one.
        """
        return self._pivots.get(role)

    def _pivot_labels(self, role: str) -> list[str]:
        """Preset labels declared for ``role``, in row order."""
        return self.module.pivot_labels(role)

    def _wire_pivot_presets(
        self,
        main: Controller,
        role: str,
        labels: list[str],
        *,
        holder,
        target,
    ) -> None:
        """Store each preset on ``holder`` and switch ``target`` with a choice.

        A ``choice`` node takes its input type from its *first connection*, not
        from a value written into it -- so the positions live as locked hidden
        ``double3`` attributes and are connected in. That costs no extra node
        and leaves the preset data readable on the control that uses it.

        ``holder`` and ``target`` are the same node for a pivot that is not
        movable. A movable one splits them: the preset drives the offset group
        while the controller translates on top, which is what lets a manual
        adjustment survive a preset change.
        """
        entries = ["default", *labels]
        positions = {"default": (0.0, 0.0, 0.0)}
        for label in labels:
            guide = self.guide(f"pivot_{role}_{label}")
            # snap-and-read: the target is a child of main, so its own
            # translate *is* the guide's position in main's local space.
            target.snap_to(guide, rotation=False)
            positions[label] = tuple(target.translate)
        target.translate = (0.0, 0.0, 0.0)

        choice = tm.create_node("choice", name=self.name(role, "pivotPreset"))
        for index, label in enumerate(entries):
            name = f"preset_{label}"
            plug = holder[name].create(attributeType="double3", hidden=True)
            for axis in "XYZ":
                holder[f"{name}{axis}"].create(attributeType="double", parent=name)
            plug.value = positions[label]
            plug.locked = True
            plug >> choice[f"input[{index}]"]
        choice["output"] >> target["translate"]

        preset = main.transform["pivotPreset"].create(
            "enum", items=entries, keyable=False
        )
        preset.visible = True
        preset >> choice["selector"]

    def controller_by_role(self, role: str) -> Optional[Controller]:
        """Return the controller registered under ``role``, if any."""
        for controller in self.controllers:
            if controller.transform.meta.get(tags.ROLE) == role:
                return controller
        return None

    def bind_joint(
        self,
        name: str,
        *,
        parent: Any = None,
        match: Any = None,
        radius: float = 1.0,
    ) -> tm.Joint:
        """Create a bind/deform joint in the single rig-wide hierarchy.

        Defaults to ``bind_parent``, which the builder resolves to the connected
        input's bind joint before ``build()`` runs. Bind joints are created in
        their final position and never reparented: ``MatrixConstraint`` wires a
        live connection to the driven's parent inverse at build time, so a joint
        moved afterwards keeps compensating for its old parent.
        """
        parent = parent if parent is not None else self.bind_parent
        joint = tm.Joint.create(
            name=self.name(name, suffix="jnt"),
            parent=parent.long_name if hasattr(parent, "long_name") else parent,
            radius=radius,
        )
        if match is not None:
            joint.align_to(node_of(match))
        return self.deform_joint(joint)

    def deform_joint(self, node) -> tm.Joint:
        """Tag ``node`` as one of this module's deform joints and register it."""
        tags.tag(
            node, **{tags.KIND: tags.DEFORM, tags.INSTANCE: self.instance.instance_id}
        )
        self.deform_joints.append(node)
        return node

    def output(self, name: str, node) -> None:
        """Publish ``node`` as the declared output ``name``."""
        if name not in self.module.output_names(self.module.values()):
            raise GuideError(
                f"'{self.module.module_type}' does not declare output '{name}'."
            )
        self.outputs[name] = node

    def attach(self, input_name: str, node) -> None:
        """Re-point an input at a node you built yourself, instead of its socket."""
        if self.module.get_input(input_name) is None:
            raise GuideError(
                f"'{self.module.module_type}' does not declare input '{input_name}'."
            )
        self.attachments[input_name] = node
