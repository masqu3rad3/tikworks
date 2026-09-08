"""What a module draws guides with, and what it builds through.

``GuideDraft`` and ``ModuleRig`` own naming, tagging, group placement and
registration. tik.maya owns the mechanism: a helper lives here only when it
removes naming, tagging, placement or registration boilerplate, so
``tm.MatrixConstraint.create(...)`` and friends stay visible in module code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

import tik.maya as tm
from tik.maya import naming
from tik.maya.roles.controller import Controller
from tik.trigger.core.exceptions import GuideError
from tik.trigger.core.manifest import TIERS
from tik.trigger.core.schemas import ModuleInstance
from tik.trigger.core import shapes as shape_library
from tik.trigger.guides.nodes import SIDE_COLORS, create_guide_joint

from . import tags


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

    def __init__(self, module, holder, parent_node=None) -> None:
        self.module = module
        self.side = module.side
        self.side_mult = module.side.multiplier
        self.holder = holder
        self.parent_node = parent_node
        self.created: dict[tuple[str, int], tm.Joint] = {}
        self.root: Optional[tm.Joint] = None

    def joint(
        self,
        role: str,
        position: Sequence[float],
        *,
        index: int = 0,
        parent: Any = None,
        radius: float = 1.0,
        marker: bool = False,
    ) -> tm.Joint:
        """Create one tagged guide joint; the first one becomes the module root.

        ``marker`` draws it as a locator cross rather than a bone -- what a
        pivot-preset guide wants.
        """
        if (role, index) in self.created:
            raise GuideError(f"Guide '{role}' [{index}] created twice.")
        is_root = not self.created
        if parent is None:
            parent = self.parent_node if is_root else self.root
            if parent is None:
                parent = self.holder
        joint = create_guide_joint(
            self.module,
            role,
            position,
            index=index,
            parent=parent,
            radius=radius,
            marker=marker,
        )
        for declared in self.module.attrs_for_role(role):
            joint[declared.name].create(
                "float", default=declared.default, keyable=declared.keyable
            )
        self.created[(role, index)] = joint
        if is_root:
            self.root = joint
        return joint


class ModuleRig:
    """Everything a module needs while building in Maya."""

    def __init__(
        self,
        module,
        instance: ModuleInstance,
        scaffold,
        guide_nodes: dict,
        bind_parent=None,
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
        self.deform_joints: list[tm.Joint] = []
        self.groups = self._create_groups()
        # Resolved by the builder from the connected input's producer, so bind
        # joints are created in their final hierarchy position.
        self.bind_parent = bind_parent if bind_parent is not None else self.groups.bind
        self._create_sockets()

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
    def _create_groups(self) -> RigGroups:
        limb = tm.Transform.create(
            name=self.name(suffix="grp"), parent=self.rig_root.long_name
        )
        socket = tm.Transform.create(
            name=self.name("socket", suffix="grp"), parent=limb.long_name
        )
        control = tm.Transform.create(
            name=self.name("control", suffix="grp"), parent=limb.long_name
        )
        rig = tm.Transform.create(
            name=self.name("rig", suffix="grp"), parent=limb.long_name
        )
        bind = tm.Transform.create(
            name=self.name("bind", suffix="grp"), parent=limb.long_name
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
                tags.NAME: self.instance.name,
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
        # The *data*, not the name: Controller.create resolves a name through
        # the unpinned singleton, which searches the artist's own folder.
        curve_data = shape_library.library().load(shape)
        controller = Controller.create(
            name=self.name(name, suffix="ctrl"),
            shape=curve_data if curve_data else shape,
            size=size * size_multiplier,
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
        self.controllers.append(controller)
        return controller

    def tweak_control(
        self, main: Controller, *, size: Optional[float] = None, shape: str = "Circle"
    ) -> Controller:
        """Create a secondary tweak controller under ``main``.

        The tweak is a child of the main, so it rides along when the animator
        moves the main control instead of being left behind. Downstream rig
        connections read the tweak, not the main.
        """
        role = main.transform.meta.get(tags.ROLE, main.transform.name)
        tweak = self.controller(
            f"{role}_tweak",
            size=size if size is not None else 1.0,
            parent=main,
            match=main,
            mirror=main.meta.get(tags.MIRROR, tags.WORLD),
            offset=False,
            tier=None,
        )
        # A tweak is not in the control manifest -- rig.tweak_control parents
        # it under its main -- so it has no role to key an override on, and
        # its shape is set here rather than resolved.
        tweak.set_shape(shape, size=size if size is not None else 1.0)
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
        size: Optional[float] = None,
        shape: str = "Sphere",
    ) -> Controller:
        """Give ``main`` a movable pivot, with this module's presets for its role.

        The pivot controller is a plain child of ``main``, which is exactly
        where it belongs: a child at the local position of ``rotatePivot`` is
        the rotation's fixed point, so the marker sits on the pivot and follows
        the control with no space maths.

        A preset drives the pivot controller's *offset* group and the
        controller translates on top, so a manual adjustment survives a preset
        change. Index 0 of the enum is ``default`` -- the control's own origin,
        the way ``world`` is always index 0 of a space switch. With no rows
        there is no enum at all, only a pivot the animator moves by hand.

        Args:
            main: The controller whose pivot becomes movable.
            size: Shape scale (defaults to 1.0).
            shape: Control shape name. A pivot is a point, and a sphere is the
                one shape that reads the same from every angle.

        Returns:
            Controller: The pivot controller.

        Raises:
            GuideError: If ``main``'s role is not in the module's
                ``pivot_controls`` -- a module-author error, and a silent one
                would leave the rigger's preset rows pointing at nothing.
        """
        role = main.transform.meta.get(tags.ROLE, main.transform.name)
        if role not in self.module.pivot_controls:
            raise GuideError(
                f"'{self.module.module_type}' does not declare a movable pivot "
                f"for control '{role}'."
            )
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
        pivot.set_shape(shape, size=size if size is not None else 1.0)
        show = main.transform["showPivot"].create("bool", default=False, keyable=False)
        show.visible = True
        show >> pivot.offset["visibility"]

        labels = self._pivot_labels(role)
        if labels:
            self._wire_pivot_presets(main, pivot, role, labels)
        main.drive_pivot(
            pivot.offset["translate"] + pivot.transform["translate"], scale=True
        )
        return pivot

    def _pivot_labels(self, role: str) -> list[str]:
        """Preset labels declared for ``role``, in row order."""
        return [
            row["label"]
            for row in self.module.pivot_rows(self.module.values())
            if row.get("control") == role and row.get("label")
        ]

    def _wire_pivot_presets(
        self, main: Controller, pivot: Controller, role: str, labels: list[str]
    ) -> None:
        """Store each preset on ``pivot`` and switch between them with a choice.

        A ``choice`` node takes its input type from its *first connection*, not
        from a value written into it -- so the positions live as locked hidden
        ``double3`` attributes on the pivot controller and are connected in.
        That costs no extra node and leaves the preset data readable on the
        control that uses it.
        """
        entries = ["default", *labels]
        positions = {"default": (0.0, 0.0, 0.0)}
        for label in labels:
            guide = self.guide(f"pivot_{role}_{label}")
            # snap-and-read: the offset group is a child of main, so its own
            # translate *is* the guide's position in main's local space.
            pivot.offset.snap_to(guide, rotation=False)
            positions[label] = tuple(pivot.offset.translate)
        pivot.offset.translate = (0.0, 0.0, 0.0)

        choice = tm.create_node("choice", name=self.name(role, "pivotPreset"))
        for index, label in enumerate(entries):
            name = f"preset_{label}"
            plug = pivot.transform[name].create(attributeType="double3", hidden=True)
            for axis in "XYZ":
                pivot.transform[f"{name}{axis}"].create(
                    attributeType="double", parent=name
                )
            plug.value = positions[label]
            plug.locked = True
            plug >> choice[f"input[{index}]"]
        choice["output"] >> pivot.offset["translate"]

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
