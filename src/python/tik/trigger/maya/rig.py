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
from maya import cmds
from tik.core.side import Side
from tik.maya import attribute, naming
from tik.maya.roles.controller import Controller
from tik.trigger.core.exceptions import GuideError
from tik.trigger.core.schemas import ModuleInstance

from . import tags

SIDE_COLORS = {Side.LEFT: 6, Side.RIGHT: 13, Side.CENTER: 17}


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
    ) -> tm.Joint:
        if (role, index) in self.created:
            raise GuideError(f"Guide '{role}' [{index}] created twice.")
        is_root = not self.created
        if parent is None:
            parent = self.parent_node if is_root else self.root
            if parent is None:
                parent = self.holder
        joint = tm.Joint.create(
            name=naming.format_name(
                self.module.name, role, index if index else None,
                side=self.side.value, suffix="guide",
            ),
            parent=parent.long_name if hasattr(parent, "long_name") else parent,
            radius=radius,
        )
        joint.world_position = position
        tags.tag(
            joint,
            **{
                tags.KIND: tags.GUIDE,
                tags.MODULE: self.module.module_type,
                tags.INSTANCE: self.module.instance_id,
                tags.ROLE: role,
                tags.INDEX: index,
                tags.SIDE: self.side.value,
            },
        )
        joint.color = SIDE_COLORS[self.side]
        for declared in self.module.attrs_for_role(role):
            attribute.add_float(
                joint, declared.name, default=declared.default, keyable=declared.keyable
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
        rig_root,
        guide_nodes: dict,
        bind_parent=None,
    ) -> None:
        self.module = module
        self.instance = instance
        self.side = module.side
        self.side_mult = module.side.multiplier
        self.rig_root = rig_root
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
        limb = tm.Transform.create(name=self.name(suffix="grp"), parent=self.rig_root.long_name)
        socket = tm.Transform.create(name=self.name("socket", suffix="grp"), parent=limb.long_name)
        control = tm.Transform.create(name=self.name("control", suffix="grp"), parent=limb.long_name)
        rig = tm.Transform.create(name=self.name("rig", suffix="grp"), parent=limb.long_name)
        bind = tm.Transform.create(name=self.name("bind", suffix="grp"), parent=limb.long_name)

        attribute.add_separator(limb, "visibility_")
        attribute.add_bool(limb, "controlVisibility", default=True) >> control["visibility"]
        attribute.add_bool(limb, "rigVisibility", default=False) >> rig["visibility"]
        attribute.add_bool(limb, "bindVisibility", default=True) >> bind["visibility"]
        for group in (limb, socket, control, rig, bind):
            attribute.lock_and_hide(group, attribute.TRANSFORM_ATTRS)
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
        return naming.format_name(
            *tokens, side=self.side.value, prefix=self.instance.name, suffix=suffix
        )

    def group(self, *tokens, under="rig") -> tm.Transform:
        """A named group placed under one of the module's groups (or a node)."""
        parent = getattr(self.groups, under) if isinstance(under, str) else node_of(under)
        return tm.Transform.create(
            name=self.name(*tokens, suffix="grp"),
            parent=parent.long_name if hasattr(parent, "long_name") else parent,
        )

    def socket(self, input_name: str, *, match=None) -> tm.Transform:
        """This module's socket for a declared input, optionally aligned to ``match``."""
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
    def controller(
        self,
        name: str,
        *,
        shape: str = "Circle",
        size: float = 1.0,
        parent: Any = None,
        color: Any = None,
        match: Any = None,
        mirror: str = "world",
        offset: bool = True,
    ) -> Controller:
        """A tagged controller with its offset group.

        ``match`` snaps it to a node; ``mirror`` is ``"behaviour"`` (FK-like,
        follows its joint) or ``"world"`` (IK/world-aligned), recorded for a
        pose-mirror tool. ``offset=False`` skips the offset group, for a
        controller that hangs under another one (a tweak).
        """
        parent = parent if parent is not None else self.groups.control
        controller = Controller.create(
            name=self.name(name, suffix="ctrl"),
            shape=shape,
            size=size,
            color=color if color is not None else SIDE_COLORS[self.side],
            parent=node_of(parent).long_name if hasattr(node_of(parent), "long_name") else parent,
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
            shape=shape,
            size=size if size is not None else 1.0,
            parent=main,
            match=main,
            mirror=main.meta.get(tags.MIRROR, tags.WORLD),
            offset=False,
        )
        visible = attribute.add_bool(
            main.transform, "tweakVis", default=False, keyable=False
        )
        cmds.setAttr(visible.path, channelBox=True)
        visible >> tweak.transform["visibility"]
        locked = [
            attr
            for attr in attribute.ALL_CHANNELS
            if cmds.getAttr(f"{main.transform.long_name}.{attr}", lock=True)
        ]
        if locked:
            attribute.lock_and_hide(tweak.transform, locked)
        return tweak

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
        tags.tag(node, **{tags.KIND: tags.DEFORM, tags.INSTANCE: self.instance.instance_id})
        self.deform_joints.append(node)
        return node

    def output(self, name: str, node) -> None:
        if name not in self.module.output_names(self.module.values()):
            raise GuideError(f"'{self.module.module_type}' does not declare output '{name}'.")
        self.outputs[name] = node

    def attach(self, input_name: str, node) -> None:
        """Re-point an input at a node you built yourself, instead of its socket."""
        if self.module.get_input(input_name) is None:
            raise GuideError(f"'{self.module.module_type}' does not declare input '{input_name}'.")
        self.attachments[input_name] = node
