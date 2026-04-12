"""Arm module for tik.trigger.

A complete arm module with IK/FK switching, ribbon segments, and controllers.
Supports shoulder, elbow, and hand with full rig building.

Guide Phase:
    Creates 4 guide joints: Collar, Shoulder, Elbow, Hand

Build Phase:
    Creates deformation joints, IK/FK chains, ribbon segments for upper and lower arm,
    and controllers for IK/FK switching.

Connectors:
    Plug: limbPlug - collar joint (connects to parent's plug)
    Sockets: collarSocket, shoulderSocket, elbowSocket, handSocket
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import maya.cmds as cmds
import maya.api.OpenMaya as om

from tik.trigger.core import register_module, RigModule
from tik.trigger.core.socket_data import JointType, Plug, Socket

if TYPE_CHECKING:
    from tik.trigger.core.schemas import GuideData

logger = logging.getLogger(__name__)


@register_module("arm")
class Arm(RigModule):
    """Arm module - IK/FK switching limb with ribbon segments.

    Creates a full arm rig with:
    - Collar, shoulder, elbow, hand joints
    - IK/FK switching via FKIK switch controller
    - Ribbon segments for upper and lower arm
    - Pole vector controller
    - Volume preservation attributes

    Connectors:
        Plug: limbPlug - collar_jnt (deformation output)
        Socket: collarSocket, shoulderSocket, elbowSocket, handSocket
    """

    _module_name = "arm"

    def _create_guides_impl(self) -> None:
        """Create the arm guide joints."""
        # Guide positions based on side
        if self._name.endswith("_L") or "_L_" in self._name:
            side_mult = -1
            side = "L"
        elif self._name.endswith("_R") or "_R_" in self._name:
            side_mult = 1
            side = "R"
        else:
            side_mult = 1
            side = "C"

        # Default arm positions (in Y-up, side-facing Z)
        if side == "C":
            collar_vec = om.MVector(0, 0, 2)
            shoulder_vec = om.MVector(0, 0, 5)
            elbow_vec = om.MVector(0, -1, 9)
            hand_vec = om.MVector(0, 0, 14)
        else:
            collar_vec = om.MVector(2 * side_mult, 0, 0)
            shoulder_vec = om.MVector(5 * side_mult, 0, 0)
            elbow_vec = om.MVector(9 * side_mult, 0, -1)
            hand_vec = om.MVector(14 * side_mult, 0, 0)

        # Create collar guide
        cmds.select(clear=True)
        collar_jnt = cmds.joint(
            name=f"{self._name}_collar_jInit",
            position=(collar_vec.x, collar_vec.y, collar_vec.z),
        )
        cmds.setAttr(f"{collar_jnt}.radius", 2)

        # Create shoulder guide
        cmds.select(clear=True)
        shoulder_jnt = cmds.joint(
            name=f"{self._name}_shoulder_jInit",
            position=(shoulder_vec.x, shoulder_vec.y, shoulder_vec.z),
        )

        # Create elbow guide
        cmds.select(clear=True)
        elbow_jnt = cmds.joint(
            name=f"{self._name}_elbow_jInit",
            position=(elbow_vec.x, elbow_vec.y, elbow_vec.z),
        )

        # Create hand guide
        cmds.select(clear=True)
        hand_jnt = cmds.joint(
            name=f"{self._name}_hand_jInit",
            position=(hand_vec.x, hand_vec.y, hand_vec.z),
        )

        logger.debug("Created arm guides: collar=%s, shoulder=%s, elbow=%s, hand=%s",
                     collar_jnt, shoulder_jnt, elbow_jnt, hand_jnt)

    def _update_guide_impl(self, index: int, guide_data: "GuideData") -> None:
        """Update a guide at the given index.

        Args:
            index: The index of the guide to update.
            guide_data: The new guide data.
        """
        guide_names = ["collar", "shoulder", "elbow", "hand"]
        if index >= len(guide_names):
            return

        joint_name = f"{self._name}_{guide_names[index]}_jInit"
        if cmds.objExists(joint_name):
            cmds.xform(joint_name, worldSpace=True, translation=guide_data.position)
            cmds.xform(joint_name, worldSpace=True, rotation=guide_data.rotation)

    def _delete_guides_impl(self) -> None:
        """Delete all guide nodes from the Maya scene."""
        joints = cmds.ls(f"{self._name}_*_jInit", type="joint")
        if joints:
            cmds.delete(joints)
        logger.debug("Deleted arm guides for: %s", self._name)

    def _get_guide_data_impl(self) -> list["GuideData"]:
        """Query current guide positions from the Maya scene.

        Returns:
            List of current guide data.
        """
        from tik.trigger.core.schemas import GuideData

        guide_names = ["collar", "shoulder", "elbow", "hand"]
        guides = []

        for guide_name in guide_names:
            joint_name = f"{self._name}_{guide_name}_jInit"
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
        guide_names = ["collar", "shoulder", "elbow", "hand"]
        self._guide_refs = {}
        for name in guide_names:
            self._guide_refs[name] = f"{self._name}_{name}_jInit"

        # Determine side
        if "_L_" in self._name:
            self._side = "L"
            self._side_mult = -1
        elif "_R_" in self._name:
            self._side = "R"
            self._side_mult = 1
        else:
            self._side = "C"
            self._side_mult = 1

        # Module properties
        self._is_local = self.get_setting("localJoints", False)
        self._use_ref_orientation = self.get_setting("useRefOrientation", True)

        # Calculate distances
        collar_pos = cmds.xform(self._guide_refs["collar"], query=True, worldSpace=True, translation=True)
        shoulder_pos = cmds.xform(self._guide_refs["shoulder"], query=True, worldSpace=True, translation=True)
        elbow_pos = cmds.xform(self._guide_refs["elbow"], query=True, worldSpace=True, translation=True)
        hand_pos = cmds.xform(self._guide_refs["hand"], query=True, worldSpace=True, translation=True)

        self._shoulder_dist = ((collar_pos[0]-shoulder_pos[0])**2 + (collar_pos[1]-shoulder_pos[1])**2 + (collar_pos[2]-shoulder_pos[2])**2) ** 0.5
        self._upper_arm_dist = ((shoulder_pos[0]-elbow_pos[0])**2 + (shoulder_pos[1]-elbow_pos[1])**2 + (shoulder_pos[2]-elbow_pos[2])**2) ** 0.5
        self._lower_arm_dist = ((elbow_pos[0]-hand_pos[0])**2 + (elbow_pos[1]-hand_pos[1])**2 + (elbow_pos[2]-hand_pos[2])**2) ** 0.5

        logger.debug("Pre-build ready for arm: %s (shoulder=%.1f, upper=%.1f, lower=%.1f)",
                     self._name, self._shoulder_dist, self._upper_arm_dist, self._lower_arm_dist)

    def _create_groups_impl(self) -> None:
        """Create essential rig groups."""
        self._limb_grp = cmds.group(empty=True, name=f"{self._name}_limbGrp")
        self._scale_grp = cmds.group(empty=True, name=f"{self._name}_scaleGrp")
        self._controller_grp = cmds.group(empty=True, name=f"{self._name}_controllerGrp")
        self._rig_joints_grp = cmds.group(empty=True, name=f"{self._name}_rigJointsGrp")
        self._def_joints_grp = cmds.group(empty=True, name=f"{self._name}_defJointsGrp")

        # Add visibility attributes to scaleGrp
        cmds.addAttr(self._scale_grp, attributeType="bool", longName="contVis", shortName="contVis", defaultValue=True)
        cmds.addAttr(self._scale_grp, attributeType="bool", longName="jointVis", shortName="jointVis", defaultValue=True)
        cmds.addAttr(self._scale_grp, attributeType="bool", longName="rigVis", shortName="rigVis", defaultValue=False)
        cmds.setAttr(f"{self._scale_grp}.contVis", channelBox=True)
        cmds.setAttr(f"{self._scale_grp}.jointVis", channelBox=True)
        cmds.setAttr(f"{self._scale_grp}.rigVis", channelBox=True)

        cmds.parent(self._scale_grp, self._limb_grp)
        cmds.parent(self._controller_grp, self._scale_grp)
        cmds.parent(self._rig_joints_grp, self._limb_grp)
        cmds.parent(self._def_joints_grp, self._limb_grp)

        logger.debug("Created rig groups for arm: %s", self._name)

    def _create_joints_impl(self) -> None:
        """Create the arm joints."""
        import maya.cmds as cmds

        # Create limb plug
        collar_pos = cmds.xform(self._guide_refs["collar"], query=True, worldSpace=True, translation=True)
        self._limb_plug = cmds.joint(name=f"{self._name}_plug_j")
        cmds.xform(self._limb_plug, worldSpace=True, translation=collar_pos)
        cmds.setAttr(f"{self._limb_plug}.radius", 3)
        cmds.parent(self._limb_plug, self._limb_grp)

        # Create collar joint
        cmds.select(self._limb_plug)
        self._collar_jnt = cmds.joint(name=f"{self._name}_collar_jDef")
        cmds.setAttr(f"{self._collar_jnt}.radius", 1.5)
        cmds.delete(cmds.parentConstraint(self._guide_refs["collar"], self._collar_jnt, maintainOffset=False))
        cmds.makeIdentity(self._collar_jnt, apply=True)

        # Create collar end (shoulder position)
        cmds.select(self._collar_jnt)
        self._collar_end_jnt = cmds.joint(name=f"{self._name}_collarEnd_j")
        cmds.setAttr(f"{self._collar_end_jnt}.radius", 1.5)
        cmds.delete(cmds.parentConstraint(self._guide_refs["shoulder"], self._collar_end_jnt, maintainOffset=False))
        cmds.makeIdentity(self._collar_end_jnt, apply=True)

        # Create elbow joint
        cmds.select(self._collar_end_jnt)
        self._elbow_jnt = cmds.joint(name=f"{self._name}_elbow_jDef")
        cmds.setAttr(f"{self._elbow_jnt}.radius", 1.5)
        cmds.delete(cmds.parentConstraint(self._guide_refs["elbow"], self._elbow_jnt, maintainOffset=False))
        cmds.makeIdentity(self._elbow_jnt, apply=True)

        # Create hand joint
        cmds.select(self._elbow_jnt)
        self._hand_jnt = cmds.joint(name=f"{self._name}_hand_jDef")
        cmds.setAttr(f"{self._hand_jnt}.radius", 1.0)
        cmds.delete(cmds.parentConstraint(self._guide_refs["hand"], self._hand_jnt, maintainOffset=False))
        cmds.makeIdentity(self._hand_jnt, apply=True)

        # Create IK joints
        cmds.select(self._collar_end_jnt)
        self._ik_up_jnt = cmds.joint(name=f"{self._name}_IK_up_j")
        cmds.setAttr(f"{self._ik_up_jnt}.radius", 0.5)
        cmds.delete(cmds.parentConstraint(self._guide_refs["shoulder"], self._ik_up_jnt, maintainOffset=False))
        cmds.makeIdentity(self._ik_up_jnt, apply=True)

        cmds.select(self._ik_up_jnt)
        self._ik_low_jnt = cmds.joint(name=f"{self._name}_IK_low_j")
        cmds.setAttr(f"{self._ik_low_jnt}.radius", 0.5)
        cmds.delete(cmds.parentConstraint(self._guide_refs["elbow"], self._ik_low_jnt, maintainOffset=False))
        cmds.makeIdentity(self._ik_low_jnt, apply=True)

        cmds.select(self._ik_low_jnt)
        self._ik_low_end_jnt = cmds.joint(name=f"{self._name}_IK_lowEnd_j")
        cmds.setAttr(f"{self._ik_low_end_jnt}.radius", 0.5)
        cmds.delete(cmds.parentConstraint(self._guide_refs["hand"], self._ik_low_end_jnt, maintainOffset=False))
        cmds.makeIdentity(self._ik_low_end_jnt, apply=True)

        # Create FK joints
        cmds.select(self._collar_end_jnt)
        self._fk_up_jnt = cmds.joint(name=f"{self._name}_FK_up_j")
        cmds.setAttr(f"{self._fk_up_jnt}.radius", 2.0)
        cmds.delete(cmds.parentConstraint(self._guide_refs["shoulder"], self._fk_up_jnt, maintainOffset=False))
        cmds.makeIdentity(self._fk_up_jnt, apply=True)

        cmds.select(self._fk_up_jnt)
        self._fk_low_jnt = cmds.joint(name=f"{self._name}_FK_low_j")
        cmds.setAttr(f"{self._fk_low_jnt}.radius", 2.0)
        cmds.delete(cmds.parentConstraint(self._guide_refs["elbow"], self._fk_low_jnt, maintainOffset=False))
        cmds.makeIdentity(self._fk_low_jnt, apply=True)

        cmds.select(self._fk_low_jnt)
        self._fk_low_end_jnt = cmds.joint(name=f"{self._name}_FK_lowEnd_j")
        cmds.setAttr(f"{self._fk_low_end_jnt}.radius", 2.0)
        cmds.delete(cmds.parentConstraint(self._guide_refs["hand"], self._fk_low_end_jnt, maintainOffset=False))
        cmds.makeIdentity(self._fk_low_end_jnt, apply=True)

        # Parent joints under groups
        cmds.parent(self._collar_jnt, self._def_joints_grp)
        cmds.parent(self._ik_up_jnt, self._rig_joints_grp)
        cmds.parent(self._fk_up_jnt, self._rig_joints_grp)

        # Connect visibility
        cmds.connectAttr(f"{self._scale_grp}.jointVis", f"{self._collar_jnt}.v")
        cmds.connectAttr(f"{self._scale_grp}.jointVis", f"{self._elbow_jnt}.v")
        cmds.connectAttr(f"{self._scale_grp}.jointVis", f"{self._hand_jnt}.v")

        logger.debug("Created arm joints")

    def _create_controllers_impl(self) -> None:
        """Create the arm controllers."""
        import tik.maya as tm

        # Shoulder controller
        shoulder_scale = (self._shoulder_dist / 2, self._shoulder_dist / 2, self._shoulder_dist / 2)
        self._shoulder_cont = tm.Transform.create(name=f"{self._name}_shoulder_cont")
        self._shoulder_cont.scale = shoulder_scale
        self._shoulder_cont.snap_to(self._collar_jnt, position=True, rotation=True)

        # Hand IK controller
        ik_scale = (self._lower_arm_dist / 3, self._lower_arm_dist / 3, self._lower_arm_dist / 3)
        self._hand_ik_cont = tm.Transform.create(name=f"{self._name}_IK_hand_cont")
        self._hand_ik_cont.scale = ik_scale
        self._hand_ik_cont.snap_to(self._hand_jnt, position=True, rotation=True)

        # Add IK attributes
        for attr_name, short_name, default, min_val, max_val in [
            ("Pole_Vector", "polevector", 0.0, 0.0, 1.0),
            ("Pole_Pin", "polevectorPin", 0.0, 0.0, 1.0),
            ("Scale_Upper_Arm", "sUpArm", 1.0, 0.0, None),
            ("Scale_Lower_Arm", "sLowArm", 1.0, 0.0, None),
            ("Squash", "squash", 0.0, 0.0, 1.0),
            ("Stretch", "stretch", 1.0, 0.0, 1.0),
            ("Volume_Preserve", "volume", 0.0, 0.0, None),
        ]:
            if max_val is not None:
                cmds.addAttr(self._hand_ik_cont.name, shortName=short_name, longName=attr_name,
                            defaultValue=default, minValue=min_val, maxValue=max_val,
                            attributeType="double", keyable=True)
            else:
                cmds.addAttr(self._hand_ik_cont.name, shortName=short_name, longName=attr_name,
                            defaultValue=default, minValue=min_val,
                            attributeType="double", keyable=True)

        # FK controllers
        fk_up_scale = (self._upper_arm_dist / 2, self._upper_arm_dist / 8, self._upper_arm_dist / 8)
        self._fk_up_cont = tm.Transform.create(name=f"{self._name}_FK_upArm_cont")
        self._fk_up_cont.scale = fk_up_scale
        self._fk_up_cont.snap_to(self._fk_up_jnt, position=True, rotation=True)

        fk_low_scale = (self._lower_arm_dist / 2, self._lower_arm_dist / 8, self._lower_arm_dist / 8)
        self._fk_low_cont = tm.Transform.create(name=f"{self._name}_FK_lowArm_cont")
        self._fk_low_cont.scale = fk_low_scale
        self._fk_low_cont.snap_to(self._fk_low_jnt, position=True, rotation=True)

        fk_hand_scale = (self._lower_arm_dist / 5, self._lower_arm_dist / 5, self._lower_arm_dist / 5)
        self._fk_hand_cont = tm.Transform.create(name=f"{self._name}_FK_hand_cont")
        self._fk_hand_cont.scale = fk_hand_scale
        self._fk_hand_cont.snap_to(self._hand_jnt, position=True, rotation=True)

        # FKIK Switch controller
        switch_scale = (self._upper_arm_dist / 4, self._upper_arm_dist / 4, self._upper_arm_dist / 4)
        self._switch_cont = tm.Transform.create(name=f"{self._name}_FKIK_switch_cont")
        self._switch_cont.scale = switch_scale
        self._switch_cont.snap_to(self._hand_jnt, position=True, rotation=True)
        cmds.setAttr(f"{self._switch_cont.name}.scaleX", self._side_mult)

        # Add switch attributes
        for attr_name, short_name, default, min_val in [
            ("FK_IK", "fkik", 0.0, 0.0),
            ("Auto_Shoulder", "autoShoulder", 1.0, 0.0),
            ("Align_Shoulder", "alignShoulder", 0.0, 0.0),
            ("Hand_Auto_Twist", "handAutoTwist", 1.0, 0.0),
            ("Hand_Manual_Twist", "handManualTwist", 0.0, 0.0),
        ]:
            cmds.addAttr(self._switch_cont.name, shortName=short_name, longName=attr_name,
                        defaultValue=default, minValue=min_val,
                        attributeType="float", keyable=True)

        # Parent controllers under controllerGrp
        cmds.parent(self._shoulder_cont.name, self._controller_grp)
        cmds.parent(self._hand_ik_cont.name, self._controller_grp)
        cmds.parent(self._switch_cont.name, self._controller_grp)

        # Parent constraint collar to shoulder controller
        cmds.parentConstraint(self._shoulder_cont.name, self._collar_jnt, maintainOffset=True)

        # FK hierarchy
        cmds.parent(self._fk_hand_cont.name, self._fk_low_cont.name)
        cmds.parent(self._fk_low_cont.name, self._fk_up_cont.name)
        cmds.parent(self._fk_up_cont.name, self._shoulder_cont.name)

        # Parent constraint FK joints
        cmds.parentConstraint(self._fk_up_cont.name, self._fk_up_jnt, maintainOffset=True)
        cmds.parentConstraint(self._fk_low_cont.name, self._fk_low_jnt, maintainOffset=True)
        cmds.parentConstraint(self._fk_hand_cont.name, self._fk_low_end_jnt, maintainOffset=True)

        logger.debug("Created arm controllers")

    def _create_setup_impl(self) -> None:
        """Create IK setup and connections."""
        # Create IK handles
        sc_ik_handle = cmds.ikHandle(
            startJoint=self._ik_up_jnt,
            endEffector=self._ik_low_end_jnt,
            name=f"{self._name}_SC_IKHandle",
            solver="ikSCsolver",
        )[0]
        cmds.parent(sc_ik_handle, self._controller_grp)
        cmds.connectAttr(f"{self._scale_grp}.rigVis", f"{sc_ik_handle}.v")

        rp_ik_handle = cmds.ikHandle(
            startJoint=self._ik_up_jnt,
            endEffector=self._ik_low_end_jnt,
            name=f"{self._name}_RP_IKHandle",
            solver="ikRPsolver",
        )[0]
        cmds.parent(rp_ik_handle, self._controller_grp)
        cmds.connectAttr(f"{self._scale_grp}.rigVis", f"{rp_ik_handle}.v")

        # Parent hand IK controller to hand position
        cmds.parentConstraint(self._hand_ik_cont.name, rp_ik_handle, maintainOffset=False)

        # Create pole vector locator
        pole_bridge = cmds.spaceLocator(name=f"{self._name}_poleVector_brg")[0]
        elbow_world = cmds.xform(self._elbow_jnt, query=True, worldSpace=True, translation=True)
        mid_upper = ((cmds.xform(self._collar_end_jnt, query=True, worldSpace=True, translation=True)[0] + elbow_world[0]) / 2,
                     (cmds.xform(self._collar_end_jnt, query=True, worldSpace=True, translation=True)[1] + elbow_world[1]) / 2,
                     (cmds.xform(self._collar_end_jnt, query=True, worldSpace=True, translation=True)[2] + elbow_world[2]) / 2)
        cmds.move(mid_upper[0], mid_upper[1], mid_upper[2], pole_bridge)
        cmds.parent(pole_bridge, self._controller_grp)

        # Create pole controller
        import tik.maya as tm
        pole_scale = ((self._upper_arm_dist + self._lower_arm_dist) / 2) / 10
        self._pole_cont = tm.Transform.create(name=f"{self._name}_poleVector_cont")
        self._pole_cont.scale = (pole_scale, pole_scale, pole_scale)
        self._pole_cont.snap_to(pole_bridge, position=True, rotation=True)
        cmds.parent(self._pole_cont.name, self._controller_grp)

        # Pole vector constraint
        cmds.poleVectorConstraint(self._pole_cont.name, rp_ik_handle)

        logger.debug("Created arm IK setup")

    def _finalize_impl(self) -> None:
        """Finalize the rig build."""
        # Hide rig visibility
        cmds.setAttr(f"{self._scale_grp}.rigVis", 0)

        logger.debug("Finalized arm rig: %s", self._name)

    def _delete_impl(self) -> None:
        """Delete the built rig from the Maya scene."""
        # Delete all created groups
        for grp in [self._limb_grp, self._controller_grp]:
            if cmds.objExists(grp):
                cmds.delete(grp)

        self._built = False
        logger.info("Deleted arm rig: %s", self._name)

    def _mirror_impl(self, source_guide_names: list[str]) -> None:
        """Mirror the arm from source guides.

        Args:
            source_guide_names: Names of source guides to mirror from.
        """
        # For now, just log - full mirror would need more complex implementation
        logger.debug("Mirror not fully implemented for arm: %s", self._name)

    def _define_connectors(self) -> None:
        """Define plugs and sockets after joint creation."""
        # Define limb plug (output)
        self._connectors.plugs["limbPlug"] = Plug(
            name="limbPlug",
            joint_name=self._collar_jnt,
            joint_type=JointType.DEFINITIVE,
        )

        # Define sockets
        self._connectors.sockets["collarSocket"] = Socket(
            name="collarSocket",
            joint_name=self._collar_jnt,
            joint_type=JointType.DEFINITIVE,
            accepts_plugs=["limbPlug"],
        )

        self._connectors.sockets["shoulderSocket"] = Socket(
            name="shoulderSocket",
            joint_name=self._collar_end_jnt,
            joint_type=JointType.DEFINITIVE,
            accepts_plugs=["limbPlug"],
        )

        self._connectors.sockets["elbowSocket"] = Socket(
            name="elbowSocket",
            joint_name=self._elbow_jnt,
            joint_type=JointType.DEFINITIVE,
            accepts_plugs=["limbPlug"],
        )

        self._connectors.sockets["handSocket"] = Socket(
            name="handSocket",
            joint_name=self._hand_jnt,
            joint_type=JointType.DEFINITIVE,
            accepts_plugs=["limbPlug"],
        )

        logger.debug("Defined connectors for arm: %s", self._name)