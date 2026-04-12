"""Base module for tik.trigger.

This is the simplest module - it creates a single root joint with controllers.
It serves as the root of a rig hierarchy.

Guide Phase:
    Creates a single root guide joint at the world origin.

Build Phase:
    Creates a root joint with placement and master controllers.
    The root joint serves as the main deformation output (limbPlug).
    Child modules can connect to the rootSocket.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import tik.maya as tm
from tik.trigger.core import register_module, RigModule
from tik.trigger.core.socket_data import JointType, Plug, Socket

if TYPE_CHECKING:
    from tik.trigger.core.schemas import GuideData

logger = logging.getLogger(__name__)


@register_module("base")
class Base(RigModule):
    """Base module - creates a root joint with controllers.

    The base module is typically the root of a rig hierarchy. It creates:
    - A root deformation joint (base_jnt)
    - Placement controller for positioning
    - Master controller as top-level control
    - rootSocket for child module connections

    Connectors:
        Plug: rootPlug - base_jnt (main deformation output)
        Socket: rootSocket - base_jnt (for child connections)
    """

    _module_name = "base"

    def _create_guides_impl(self) -> None:
        """Create the base guide joint."""
        import maya.cmds as cmds

        cmds.select(clear=True)
        root_jnt = cmds.joint(
            name=f"{self._name}_root_jInit",
            position=(0.0, 0.0, 0.0),
        )
        logger.debug("Created base guide: %s", root_jnt)

    def _update_guide_impl(self, index: int, guide_data: "GuideData") -> None:
        """Update a guide at the given index.

        Args:
            index: The index of the guide to update.
            guide_data: The new guide data.
        """
        import maya.cmds as cmds

        if index != 0:
            return

        # Get the joint name
        joints = cmds.ls(f"{self._name}_*_jInit", type="joint")
        if not joints:
            return

        joint_name = joints[0]
        cmds.xform(joint_name, worldSpace=True, translation=guide_data.position)
        cmds.xform(joint_name, worldSpace=True, rotation=guide_data.rotation)

    def _delete_guides_impl(self) -> None:
        """Delete all guide nodes from the Maya scene."""
        import maya.cmds as cmds

        joints = cmds.ls(f"{self._name}_*_jInit", type="joint")
        if joints:
            cmds.delete(joints)
        logger.debug("Deleted base guides for: %s", self._name)

    def _get_guide_data_impl(self) -> list["GuideData"]:
        """Query current guide positions from the Maya scene.

        Returns:
            List of current guide data.
        """
        import maya.cmds as cmds

        from tik.trigger.core.schemas import GuideData

        joints = cmds.ls(f"{self._name}_*_jInit", type="joint")
        guides = []

        for joint_name in joints:
            pos = cmds.xform(joint_name, query=True, worldSpace=True, translation=True)
            rot = cmds.xform(joint_name, query=True, worldSpace=True, rotation=True)

            # Determine side from joint name
            if "_L_" in joint_name:
                side = "L"
            elif "_R_" in joint_name:
                side = "R"
            else:
                side = "C"

            guides.append(GuideData(
                name=joint_name,
                position=tuple(pos),
                rotation=tuple(rot),
                side=side,
            ))

        return guides

    def _pre_build(self) -> None:
        """Prepare data from guides before building."""
        # Get the root joint name for later use
        import maya.cmds as cmds

        joints = cmds.ls(f"{self._name}_*_jInit", type="joint")
        self._root_jnt_name = joints[0] if joints else f"{self._name}_root_jnt"
        self._build_controls = self.get_setting("build_controls", True)
        logger.debug("Pre-build ready for: %s", self._name)

    def _create_groups_impl(self) -> None:
        """Create essential rig groups.

        Creates: limbGrp, scaleGrp, nonScaleGrp, controllerGrp
        """
        import maya.cmds as cmds

        # Create standard rig groups
        self._limb_grp = cmds.group(
            empty=True,
            name=f"{self._name}_limbGrp"
        )
        self._scale_grp = cmds.group(
            empty=True,
            name=f"{self._name}_scaleGrp"
        )
        self._controller_grp = cmds.group(
            empty=True,
            name=f"{self._name}_controllerGrp"
        )

        # Add visibility attributes to scaleGrp
        cmds.addAttr(self._scale_grp, attributeType="bool", longName="contVis", shortName="contVis", defaultValue=True)
        cmds.addAttr(self._scale_grp, attributeType="bool", longName="jointVis", shortName="jointVis", defaultValue=True)
        cmds.addAttr(self._scale_grp, attributeType="bool", longName="rigVis", shortName="rigVis", defaultValue=False)
        cmds.setAttr(f"{self._scale_grp}.contVis", channelBox=True)
        cmds.setAttr(f"{self._scale_grp}.jointVis", channelBox=True)
        cmds.setAttr(f"{self._scale_grp}.rigVis", channelBox=True)

        # Parent groups in order
        cmds.parent(self._scale_grp, self._limb_grp)
        cmds.parent(self._controller_grp, self._scale_grp)

        logger.debug("Created rig groups for: %s", self._name)

    def _create_joints_impl(self) -> None:
        """Create the root deformation joint."""
        import maya.cmds as cmds

        # Create the base joint
        self._base_jnt = cmds.joint(
            name=f"{self._name}_root_jnt",
        )

        # Align to the guide position
        guide_joints = cmds.ls(f"{self._name}_*_jInit", type="joint")
        if guide_joints:
            cmds.delete(cmds.parentConstraint(guide_joints[0], self._base_jnt, maintainOffset=False))
            cmds.delete(cmds.scaleConstraint(guide_joints[0], self._base_jnt, maintainOffset=False))

        # Parent under limbGrp
        cmds.parent(self._base_jnt, self._limb_grp)

        # Connect visibility and scale from scaleGrp
        cmds.connectAttr(f"{self._scale_grp}.rigVis", f"{self._base_jnt}.v")
        cmds.connectAttr(f"{self._scale_grp}.s", f"{self._base_jnt}.s")

        self._limb_plug = self._base_jnt
        logger.debug("Created base joint: %s", self._base_jnt)

    def _create_controllers_impl(self) -> None:
        """Create placement and master controllers."""
        import maya.cmds as cmds

        if not self._build_controls:
            return

        # Create placement controller
        placement_name = f"{self._name}_placement_cont"
        placement_trans = tm.Transform.create(name=placement_name)
        placement_trans.translate = (0, 0, 0)
        placement_trans.scale = (10, 10, 10)

        # Create master controller
        master_name = f"{self._name}_master_cont"
        master_trans = tm.Transform.create(name=master_name)
        master_trans.translate = (0, 0, 0)
        master_trans.scale = (15, 15, 15)

        # Create offset groups
        placement_off = cmds.group(empty=True, name=f"{placement_name}_off")
        master_off = cmds.group(empty=True, name=f"{master_name}_off")

        # Align offset groups to base joint
        cmds.delete(cmds.parentConstraint(self._base_jnt, placement_off, maintainOffset=False))
        cmds.delete(cmds.parentConstraint(self._base_jnt, master_off, maintainOffset=False))

        # Parent placement under master
        cmds.parent(placement_trans.name, master_trans.name)
        cmds.parent(placement_off, master_trans.name)
        cmds.parent(master_off, self._controller_grp)

        # Parent constraint base joint to placement
        cmds.parentConstraint(placement_trans.name, self._base_jnt, maintainOffset=False)

        # Matrix constraint master to scaleGrp
        cmds.connectAttr(f"{master_trans.name}.worldMatrix[0]", f"{self._scale_grp}.offsetParentMatrix")

        # Store controller names
        self._placement_cont = placement_trans.name
        self._master_cont = master_trans.name
        self._anchor_locations = [placement_trans.name, master_trans.name]

        # Connect visibility
        cmds.connectAttr(f"{self._scale_grp}.contVis", f"{placement_off}.v")
        cmds.connectAttr(f"{self._scale_grp}.contVis", f"{master_off}.v")

        # Lock scale on controllers
        for attr in ["sx", "sy", "sz", "v"]:
            cmds.setAttr(f"{placement_trans.name}.{attr}", lock=True, keyable=False)
            cmds.setAttr(f"{master_trans.name}.{attr}", lock=True, keyable=False)

        logger.debug("Created controllers for: %s", self._name)

    def _create_setup_impl(self) -> None:
        """Create IK/FK/setup connections - not applicable for base."""
        # Base module doesn't have IK/FK
        pass

    def _finalize_impl(self) -> None:
        """Finalize the rig build - visibility and constraints are already set."""
        pass

    def _delete_impl(self) -> None:
        """Delete the built rig from the Maya scene."""
        import maya.cmds as cmds

        # Delete groups
        for grp in [self._limb_grp, self._controller_grp]:
            if cmds.objExists(grp):
                cmds.delete(grp)

        self._built = False
        logger.info("Deleted base rig: %s", self._name)

    def _mirror_impl(self, source_guide_names: list[str]) -> None:
        """Mirror is not applicable for base module.

        Args:
            source_guide_names: Not used.
        """
        # Base module has no mirrorable content
        pass

    def _define_connectors(self) -> None:
        """Define plugs and sockets after joint creation."""
        # Define the root plug
        self._connectors.plugs["rootPlug"] = Plug(
            name="rootPlug",
            joint_name=self._base_jnt,
            joint_type=JointType.DEFINITIVE,
        )

        # Define the root socket
        self._connectors.sockets["rootSocket"] = Socket(
            name="rootSocket",
            joint_name=self._base_jnt,
            joint_type=JointType.DEFINITIVE,
            accepts_plugs=["rootPlug"],
        )

        logger.debug("Defined connectors for base: %s", self._name)