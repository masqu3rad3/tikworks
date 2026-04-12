"""PushPull module for tik.trigger.

A module that extracts rotation from a parent joint and converts it to
translation on the end joint. Used for things like eyelids, lips, etc.

Guide Phase:
    Creates two guide joints: PushPullBase and PushPullEnd

Build Phase:
    Creates start and end joints. The rotation from the parent/rotation_parent
    is extracted and converted to translation on the end joint using a remap
    network.

Connectors:
    Plug: basePlug - start_jnt (deformation output)
    Socket: endSocket - end_jnt (for child connections)
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


@register_module("pushpull")
class PushPull(RigModule):
    """PushPull module - converts rotation to translation.

    Extracts rotation from a parent joint and converts it to translation
    on the end joint using a remap network. Useful for things like
    eyelids, lips, and other sliding joints.

    Connectors:
        Plug: basePlug - start_jnt (deformation output)
        Socket: endSocket - end_jnt (for child connections)
    """

    _module_name = "pushpull"

    def _create_guides_impl(self) -> None:
        """Create the pushpull guide joints."""
        cmds.select(clear=True)
        base_jnt = cmds.joint(
            name=f"{self._name}_base_jInit",
            position=(0.0, 0.0, 0.0),
        )

        cmds.select(clear=True)
        end_jnt = cmds.joint(
            name=f"{self._name}_end_jInit",
            position=(0.0, 5.0, 0.0),
        )

        logger.debug("Created pushpull guides: %s, %s", base_jnt, end_jnt)

    def _update_guide_impl(self, index: int, guide_data: "GuideData") -> None:
        """Update a guide at the given index.

        Args:
            index: The index of the guide to update.
            guide_data: The new guide data.
        """
        if index == 0:
            joint_name = f"{self._name}_base_jInit"
        elif index == 1:
            joint_name = f"{self._name}_end_jInit"
        else:
            return

        if cmds.objExists(joint_name):
            cmds.xform(joint_name, worldSpace=True, translation=guide_data.position)
            cmds.xform(joint_name, worldSpace=True, rotation=guide_data.rotation)

    def _delete_guides_impl(self) -> None:
        """Delete all guide nodes from the Maya scene."""
        joints = cmds.ls(f"{self._name}_*_jInit", type="joint")
        if joints:
            cmds.delete(joints)
        logger.debug("Deleted pushpull guides for: %s", self._name)

    def _get_guide_data_impl(self) -> list["GuideData"]:
        """Query current guide positions from the Maya scene.

        Returns:
            List of current guide data.
        """
        from tik.trigger.core.schemas import GuideData

        base_joint = f"{self._name}_base_jInit"
        end_joint = f"{self._name}_end_jInit"
        guides = []

        for joint_name in [base_joint, end_joint]:
            if not cmds.objExists(joint_name):
                continue

            pos = cmds.xform(joint_name, query=True, worldSpace=True, translation=True)
            rot = cmds.xform(joint_name, query=True, worldSpace=True, rotation=True)

            side = "L" if "_L_" in joint_name else ("R" if "_R_" in joint_name else "C")

            guides.append(GuideData(
                name=joint_name,
                position=tuple(pos),
                rotation=tuple(rot),
                side=side,
            ))

        return guides

    def _pre_build(self) -> None:
        """Prepare data from guides before building."""
        self._guide_base = f"{self._name}_base_jInit"
        self._guide_end = f"{self._name}_end_jInit"

        # Get settings
        self._extract_axis = self.get_setting("extractAxis", "X")
        self._translate_axis = self.get_setting("translateAxis", "X")
        self._extract_multiplier = self.get_setting("extractMultiplier", 0.5)
        self._reverse_flip = self.get_setting("reverseFlip", False)
        self._bidirectional = self.get_setting("bidirectional", False)
        self._driver_range = self.get_setting("driverRange", [-90.0, 90.0])
        self._driven_range = self.get_setting("drivenRange", [0.0, 2.0])
        self._interpolation = self.get_setting("interpolation", "linear")
        self._rotation_parent = self.get_setting("rotationParent", "")

        # Determine side multiplier
        if "_L_" in self._guide_base:
            self._side_mult = -1
            self._side = "L"
        elif "_R_" in self._guide_base:
            self._side_mult = 1
            self._side = "R"
        else:
            self._side_mult = 1
            self._side = "C"

        logger.debug("Pre-build ready for pushpull: %s", self._name)

    def _create_groups_impl(self) -> None:
        """Create essential rig groups."""
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

        cmds.parent(self._scale_grp, self._limb_grp)
        cmds.parent(self._controller_grp, self._scale_grp)

        logger.debug("Created rig groups for pushpull: %s", self._name)

    def _create_joints_impl(self) -> None:
        """Create the start and end deformation joints."""
        # Create start joint
        self._start_jnt = cmds.joint(
            name=f"{self._name}_base_jDef",
        )

        # Create end joint
        self._end_jnt = cmds.joint(
            name=f"{self._name}_end_jDef",
        )
        cmds.parent(self._end_jnt, self._start_jnt)

        # Align to guides
        if cmds.objExists(self._guide_base):
            cmds.delete(cmds.parentConstraint(self._guide_base, self._start_jnt, maintainOffset=False))
            cmds.delete(cmds.scaleConstraint(self._guide_base, self._start_jnt, maintainOffset=False))

        if cmds.objExists(self._guide_end):
            cmds.delete(cmds.parentConstraint(self._guide_end, self._end_jnt, maintainOffset=False))
            cmds.delete(cmds.scaleConstraint(self._guide_end, self._end_jnt, maintainOffset=False))

        # Parent under limbGrp
        cmds.parent(self._start_jnt, self._limb_grp)

        # Connect visibility
        cmds.connectAttr(f"{self._scale_grp}.jointVis", f"{self._start_jnt}.v")
        cmds.connectAttr(f"{self._scale_grp}.jointVis", f"{self._end_jnt}.v")

        self._limb_plug = self._start_jnt
        logger.debug("Created pushpull joints: %s, %s", self._start_jnt, self._end_jnt)

    def _create_controllers_impl(self) -> None:
        """Create controllers - not applicable for pushpull."""
        pass

    def _create_setup_impl(self) -> None:
        """Create the rotation-to-translation extraction network."""
        # Get rotation parent - either specified or find parent of start joint
        parents = cmds.listRelatives(self._start_jnt, parent=True)
        rotation_parent = self._rotation_parent or (parents[0] if parents else None)

        if not rotation_parent:
            logger.warning("No rotation parent found for pushpull: %s", self._name)
            return

        try:
            self._create_pushpull_network(rotation_parent)
        except Exception as e:
            logger.warning("Failed to create pushpull setup network for %s: %s", self._name, e)

    def _create_pushpull_network(self, rotation_parent: str) -> None:
        """Create the pushpull node network.

        Args:
            rotation_parent: The joint to extract rotation from.
        """
        # Create nodes for the compound
        compose_name = f"{self._name}_composeMatrix"
        decompose_name = f"{self._name}_decomposeMatrix"
        quat_to_euler_name = f"{self._name}_quatToEuler"
        direction_name = f"{self._name}_{self._extract_axis}_direction"
        remap_name = f"{self._name}_{self._translate_axis}_remapValue"
        compensate_name = f"{self._name}_{self._extract_axis}_compensate"

        # Create nodes
        self._compose_node = cmds.createNode("composeMatrix", name=compose_name)
        self._decompose_node = cmds.createNode("decomposeMatrix", name=decompose_name)
        self._quat_to_euler_node = cmds.createNode("quatToEuler", name=quat_to_euler_name)
        self._direction_node = cmds.createNode("multiplyDivide", name=direction_name)
        self._remap_node = cmds.createNode("remapValue", name=remap_name)
        self._compensate_node = cmds.createNode("addDoubleLinear", name=compensate_name)

        # Set direction value
        input2_value = -1 if self._reverse_flip else 1
        cmds.setAttr(f"{self._direction_node}.input2X", input2_value)

        # Connect rotation from rotation parent
        cmds.connectAttr(f"{rotation_parent}.rotateX", f"{self._compose_node}.inputRotateX")
        cmds.connectAttr(f"{rotation_parent}.rotateY", f"{self._compose_node}.inputRotateY")
        cmds.connectAttr(f"{rotation_parent}.rotateZ", f"{self._compose_node}.inputRotateZ")

        # Chain: compose -> decompose -> quat_to_euler -> direction -> quat_to_euler.w
        cmds.connectAttr(f"{self._compose_node}.outputMatrix", f"{self._decompose_node}.inputMatrix")
        cmds.connectAttr(f"{self._decompose_node}.outputQuat{self._extract_axis}", f"{self._quat_to_euler_node}.inputQuat{self._extract_axis}")
        cmds.connectAttr(f"{self._decompose_node}.outputQuatW", f"{self._direction_node}.input1")
        cmds.connectAttr(f"{self._direction_node}.output", f"{self._quat_to_euler_node}.inputQuatW")

        # Connect to compensate and remap
        cmds.connectAttr(f"{self._quat_to_euler_node}.outputRotate{self._extract_axis}", f"{self._remap_node}.inputValue")
        cmds.connectAttr(f"{self._quat_to_euler_node}.outputRotate{self._extract_axis}", f"{self._compensate_node}.input1")

        # Multiply for final output
        if self._extract_multiplier != 0.0:
            multiply_name = f"{self._name}_{self._extract_axis}_multDoubleLinear"
            self._multiply_node = cmds.createNode("multiplyDivide", name=multiply_name)
            cmds.setAttr(f"{self._multiply_node}.input2X", self._extract_multiplier)

            cmds.connectAttr(f"{self._compensate_node}.output", f"{self._multiply_node}.input1")
            cmds.connectAttr(f"{self._multiply_node}.output", f"{self._start_jnt}.rotate{self._extract_axis}")

            # Set compensate offset
            rotate_value = cmds.getAttr(f"{self._quat_to_euler_node}.outputRotate{self._extract_axis}")
            cmds.setAttr(f"{self._compensate_node}.input2", rotate_value * -1)
        else:
            cmds.connectAttr(f"{self._compensate_node}.output", f"{self._start_jnt}.rotate{self._extract_axis}")

        # Setup remap for driven joint translation
        driver_neutral = cmds.getAttr(f"{self._quat_to_euler_node}.outputRotate{self._extract_axis}")
        driven_neutral = cmds.getAttr(f"{self._end_jnt}.translate{self._translate_axis}")

        # Build value arrays
        driver_value_range = [driver_neutral] + list(self._driver_range)
        driven_value_range = [driven_neutral] + list(self._driven_range)

        # Override minimum values if not bidirectional
        if not self._bidirectional:
            driver_value_range[1] = driver_neutral
            driven_value_range[1] = driven_neutral

        interpolation_dict = {"none": 0, "linear": 1, "smooth": 2, "spline": 3}

        for index, (driver_value, driven_value) in enumerate(zip(driver_value_range, driven_value_range)):
            cmds.setAttr(f"{self._remap_node}.value[{index}].value_Position", driver_value)
            cmds.setAttr(f"{self._remap_node}.value[{index}].value_FloatValue", driven_value)
            cmds.setAttr(f"{self._remap_node}.value[{index}].value_Interp", interpolation_dict.get(self._interpolation, 1))

        # Connect remap output to end joint translation
        cmds.connectAttr(f"{self._remap_node}.outValue", f"{self._end_jnt}.translate{self._translate_axis}", force=True)

        logger.debug("Created pushpull setup for: %s", self._name)

    def _finalize_impl(self) -> None:
        """Finalize the rig build."""
        pass

    def _delete_impl(self) -> None:
        """Delete the built rig from the Maya scene."""
        # Delete groups
        if cmds.objExists(self._limb_grp):
            cmds.delete(self._limb_grp)

        self._built = False
        logger.info("Deleted pushpull rig: %s", self._name)

    def _mirror_impl(self, source_guide_names: list[str]) -> None:
        """Mirror is not applicable for pushpull module.

        Args:
            source_guide_names: Not used.
        """
        pass

    def _define_connectors(self) -> None:
        """Define plugs and sockets after joint creation."""
        # Define the base plug
        self._connectors.plugs["basePlug"] = Plug(
            name="basePlug",
            joint_name=self._start_jnt,
            joint_type=JointType.DEFINITIVE,
        )

        # Define the end socket
        self._connectors.sockets["endSocket"] = Socket(
            name="endSocket",
            joint_name=self._end_jnt,
            joint_type=JointType.DEFINITIVE,
            accepts_plugs=["basePlug"],
        )

        logger.debug("Defined connectors for pushpull: %s", self._name)