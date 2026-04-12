"""Connector module for tik.trigger.

A simple connector module that creates a single root joint with an optional
controller shape. Used to extend a rig hierarchy.

Guide Phase:
    Creates a single root guide joint.

Build Phase:
    Creates a root joint (limbPlug) with optional curve-as-shape controller.
    The root joint can connect to parent modules via rootSocket.

Connectors:
    Plug: rootPlug - main deformation joint output
    Socket: rootSocket - receives from parent modules
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import maya.cmds as cmds

from tik.trigger.core import register_module, RigModule
from tik.trigger.core.socket_data import JointType, Plug, Socket

if TYPE_CHECKING:
    from tik.trigger.core.schemas import GuideData

logger = logging.getLogger(__name__)


@register_module("connector")
class Connector(RigModule):
    """Connector module - creates a simple root joint.

    A simple module that creates a single root joint. Can optionally use
    a curve as the joint shape for visualization. Used to extend
    the rig hierarchy when connected to a parent module.

    Connectors:
        Plug: rootPlug - root_jnt (deformation output)
        Socket: rootSocket - root_jnt (for parent connections)
    """

    _module_name = "connector"

    def _create_guides_impl(self) -> None:
        """Create the connector guide joint."""
        cmds.select(clear=True)
        root_jnt = cmds.joint(
            name=f"{self._name}_root_jInit",
            position=(0.0, 0.0, 0.0),
        )
        logger.debug("Created connector guide: %s", root_jnt)

    def _update_guide_impl(self, index: int, guide_data: "GuideData") -> None:
        """Update a guide at the given index.

        Args:
            index: The index of the guide to update.
            guide_data: The new guide data.
        """
        if index != 0:
            return

        joints = cmds.ls(f"{self._name}_*_jInit", type="joint")
        if not joints:
            return

        joint_name = joints[0]
        cmds.xform(joint_name, worldSpace=True, translation=guide_data.position)
        cmds.xform(joint_name, worldSpace=True, rotation=guide_data.rotation)

    def _delete_guides_impl(self) -> None:
        """Delete all guide nodes from the Maya scene."""
        joints = cmds.ls(f"{self._name}_*_jInit", type="joint")
        if joints:
            cmds.delete(joints)
        logger.debug("Deleted connector guides for: %s", self._name)

    def _get_guide_data_impl(self) -> list["GuideData"]:
        """Query current guide positions from the Maya scene.

        Returns:
            List of current guide data.
        """
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
        # Get guide joint for alignment
        guide_joints = cmds.ls(f"{self._name}_*_jInit", type="joint")
        self._root_init = guide_joints[0] if guide_joints else None

        # Module properties
        self._use_ref_orientation = self.get_setting("useRefOrientation", True)
        self._curve_as_shape = self.get_setting("curveAsShape", False)

        # Get side from guide name
        if self._root_init and "_L_" in self._root_init:
            self._side = "L"
        elif self._root_init and "_R_" in self._root_init:
            self._side = "R"
        else:
            self._side = "C"

        logger.debug("Pre-build ready for connector: %s", self._name)

    def _create_groups_impl(self) -> None:
        """Create essential rig groups.

        Creates: limbGrp, scaleGrp, nonScaleGrp, controllerGrp
        """
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

        logger.debug("Created rig groups for connector: %s", self._name)

    def _create_joints_impl(self) -> None:
        """Create the root deformation joint."""
        # Create the root joint
        self._root_jnt = cmds.joint(
            name=f"{self._name}_root_jnt",
        )

        # Align to the guide position/rotation
        if self._root_init:
            cmds.delete(cmds.parentConstraint(self._root_init, self._root_jnt, maintainOffset=False))
            cmds.delete(cmds.scaleConstraint(self._root_init, self._root_jnt, maintainOffset=False))

        # Parent under limbGrp
        cmds.parent(self._root_jnt, self._limb_grp)

        # Connect visibility
        cmds.connectAttr(f"{self._scale_grp}.rigVis", f"{self._root_jnt}.v")
        cmds.connectAttr(f"{self._scale_grp}.jointVis", f"{self._limb_grp}.v")

        self._limb_plug = self._root_jnt
        logger.debug("Created root joint: %s", self._root_jnt)

    def _create_controllers_impl(self) -> None:
        """Create optional curve-as-shape controller."""
        import tik.maya as tm

        if self._curve_as_shape:
            # Create a cube controller shape
            cont_name = f"{self._name}_cont"
            cont_trans = tm.Transform.create(name=cont_name)

            # Align to root joint
            cont_trans.snap_to(self._root_jnt, position=True, rotation=self._use_ref_orientation)
            cont_trans.scale = (1, 1, 1)

            # Parent shape under root joint
            shapes = cont_trans.shapes
            if shapes:
                cmds.parent(shapes[0].name, self._root_jnt, relative=True, shape=True)
                cmds.delete(cont_trans.name)
                # Set joint to use curve shape
                cmds.setAttr(f"{self._root_jnt}.drawStyle", 2)  # Bone style with curve
            else:
                # No shape found, just delete the transform
                cmds.delete(cont_trans.name)

            self._controller = cont_name
        else:
            self._controller = None

        logger.debug("Created controllers for connector: %s", self._name)

    def _create_setup_impl(self) -> None:
        """Create IK/FK/setup connections - not applicable for connector."""
        pass

    def _finalize_impl(self) -> None:
        """Finalize the rig build."""
        pass

    def _delete_impl(self) -> None:
        """Delete the built rig from the Maya scene."""
        # Delete groups
        for grp in [self._limb_grp]:
            if cmds.objExists(grp):
                cmds.delete(grp)

        self._built = False
        logger.info("Deleted connector rig: %s", self._name)

    def _mirror_impl(self, source_guide_names: list[str]) -> None:
        """Mirror is not applicable for connector module.

        Args:
            source_guide_names: Not used.
        """
        pass

    def _define_connectors(self) -> None:
        """Define plugs and sockets after joint creation."""
        # Define the root plug
        self._connectors.plugs["rootPlug"] = Plug(
            name="rootPlug",
            joint_name=self._root_jnt,
            joint_type=JointType.DEFINITIVE,
        )

        # Define the root socket
        self._connectors.sockets["rootSocket"] = Socket(
            name="rootSocket",
            joint_name=self._root_jnt,
            joint_type=JointType.DEFINITIVE,
            accepts_plugs=["rootPlug"],
        )

        logger.debug("Defined connectors for connector: %s", self._name)