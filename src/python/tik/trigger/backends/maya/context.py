"""Maya implementations of the guide and build contexts."""

from __future__ import annotations

from typing import Any, Optional, Sequence

import tik.maya as tm
from maya import cmds
from tik.core.side import Side
from tik.maya import attribute, naming
from tik.maya.roles.controller import Controller
from tik.trigger.core.context import RigGroups
from tik.trigger.core.exceptions import GuideError
from tik.trigger.core.schemas import ModuleInstance

from . import tags

SIDE_COLORS = {Side.LEFT: 6, Side.RIGHT: 13, Side.CENTER: 17}


class MayaGuideContext:
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
        self.created[(role, index)] = joint
        if is_root:
            self.root = joint
        return joint


class MayaBuildContext:
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

    def guides(self, role: str) -> list[tm.Joint]:
        pairs = sorted(key for key in self._guides if key[0] == role)
        return [self._guides[key] for key in pairs]

    # ------------------------------------------------------------- naming
    def name(self, *tokens, suffix: Optional[str] = None) -> str:
        return naming.format_name(
            *tokens, side=self.side.value, prefix=self.instance.name, suffix=suffix
        )

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
    ) -> Controller:
        parent = parent if parent is not None else self.groups.control
        controller = Controller.create(
            name=self.name(name, suffix="ctrl"),
            shape=shape,
            size=size,
            color=color if color is not None else SIDE_COLORS[self.side],
            parent=parent.long_name,
        )
        if match is not None:
            controller.transform.align_to(match)
        tags.tag(
            controller.transform,
            **{
                tags.KIND: tags.CONTROLLER,
                tags.INSTANCE: self.instance.instance_id,
                tags.ROLE: name,
                tags.MIRROR: mirror,
            },
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
            parent=main.transform,
            match=main.transform,
            mirror=main.transform.meta.get(tags.MIRROR, tags.WORLD),
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
            joint.align_to(match)
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
        if self.module.get_input(input_name) is None:
            raise GuideError(f"'{self.module.module_type}' does not declare input '{input_name}'.")
        self.attachments[input_name] = node
