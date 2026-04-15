"""FK Chain module for tik.trigger.

TODO: RE-WRITE THIS PROPERLY
- This is a placeholder/test module with ugly code mixing tik.maya and maya.cmds
- No proper controller curves (just transforms)
- Needs clean implementation with proper Controller class

A simple FK (Forward Kinematics) chain module with plug/socket connectors.
This module is used to test the core kinematics workflow.

Guide Phase:
    Creates 3 guide joints: root, mid, end

Build Phase:
    Creates 3 deformation joints with FK controllers in a parented hierarchy.
    The controllers follow the joint chain.

Connectors:
    Plug: rootPlug - root joint (for parent connection)
    Socket: endSocket - end joint (for child connections)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import maya.cmds as cmds
import maya.api.OpenMaya as om

from tik.trigger.core import register_module, RigModule
from tik.trigger.core.socket_data import JointType, Plug, Socket
from tik.trigger.core.module_registry import MODULE_INSTANCE_ATTR
from tik.trigger.core.module_registry import get_module

if TYPE_CHECKING:
    from tik.trigger.core.schemas import GuideData

logger = logging.getLogger(__name__)


@register_module("fkchain")
class FKChain(RigModule):
    """FK Chain module - simple forward kinematics chain.

    A simple FK chain with three joints and controllers.
    Used for testing plug/socket connections and the kinematics workflow.

    Connectors:
        Plug: rootPlug - root_jnt (connect to parent's plug)
        Socket: endSocket - end_jnt (for children to connect)
    """

    _module_name = "fkchain"

    def _create_guides_impl(self) -> None:
        """Create the FK chain guide joints: root, mid, end."""
        # Get joint roles from registry
        registry = get_module("fkchain")
        if not registry:
            logger.error("FKChain module not registered in module_registry")
            return
        joint_roles = [role.name for role in registry.joint_roles]  # ["root", "mid", "end"]

        # Default positions - chain along Y axis
        positions = [
            (0, 0, 0),      # root
            (0, 5, 0),      # mid
            (0, 10, 0),     # end
        ]

        previous_joint = None

        for idx, (role_name, position) in enumerate(zip(joint_roles, positions)):
            cmds.select(clear=True)
            joint_name = f"{self._name}_{role_name}_jInit"
            jnt = cmds.joint(
                name=joint_name,
                position=position,
            )
            cmds.setAttr(f"{jnt}.radius", 1.5)

            # Set identification attributes for kinematics
            self._set_guide_attributes(jnt, role_name)

            # Parent under previous joint if not first
            if previous_joint:
                cmds.parent(jnt, previous_joint)

            previous_joint = jnt
            logger.debug("Created FK chain guide: %s", jnt)

    def _update_guide_impl(self, index: int, guide_data: "GuideData") -> None:
        """Update a guide at the given index.

        Args:
            index: The index of the guide to update.
            guide_data: The new guide data.
        """
        registry = get_module("fkchain")
        if not registry:
            return
        joint_roles = [role.name for role in registry.joint_roles]

        if index >= len(joint_roles):
            return

        role_name = joint_roles[index]
        joint_name = f"{self._name}_{role_name}_jInit"

        if cmds.objExists(joint_name):
            cmds.xform(joint_name, worldSpace=True, translation=guide_data.position)
            cmds.xform(joint_name, worldSpace=True, rotation=guide_data.rotation)

    def _delete_guides_impl(self) -> None:
        """Delete all guide joints from the Maya scene."""
        joints = cmds.ls(f"{self._name}_*_jInit", type="joint")
        if joints:
            cmds.delete(joints)
        logger.debug("Deleted FK chain guides for: %s", self._name)

    def _get_guide_data_impl(self) -> list["GuideData"]:
        """Query current guide positions from the Maya scene.

        Returns:
            List of current guide data with parent/children populated from DAG.
        """
        from tik.trigger.core.schemas import GuideData

        registry = get_module("fkchain")
        if not registry:
            return []
        joint_roles = [role.name for role in registry.joint_roles]
        guides = []
        guide_by_name = {}

        # First pass: create GuideData for each joint
        for role_name in joint_roles:
            joint_name = f"{self._name}_{role_name}_jInit"
            if not cmds.objExists(joint_name):
                continue

            pos = cmds.xform(joint_name, query=True, worldSpace=True, translation=True)
            rot = cmds.xform(joint_name, query=True, worldSpace=True, rotation=True)

            side = "L" if "_L_" in joint_name else ("R" if "_R_" in joint_name else "C")

            gd = GuideData(
                name=joint_name,
                position=tuple(pos),
                rotation=tuple(rot),
                side=side,
            )
            guides.append(gd)
            guide_by_name[joint_name] = gd

        # Second pass: populate parent/children from Maya DAG
        for gd in guides:
            # Get parent from Maya - capture ALL parents (even inter-module)
            parent = cmds.listRelatives(gd.name, parent=True, type="joint")
            if parent:
                parent_name = parent[0]
                # Set parent if it has moduleInstance attribute (even if different module)
                if cmds.objExists(f"{parent_name}.{MODULE_INSTANCE_ATTR}"):
                    gd.parent = parent_name

            # Get children from Maya - capture all children
            children = cmds.listRelatives(gd.name, children=True, type="joint") or []
            for child_name in children:
                if cmds.objExists(f"{child_name}.{MODULE_INSTANCE_ATTR}"):
                    gd.children.append(child_name)

        return guides

    def _pre_build(self) -> None:
        """Prepare data from guides before building."""
        import maya.cmds as cmds

        registry = get_module("fkchain")
        if not registry:
            return
        self._joint_roles = [role.name for role in registry.joint_roles]

        # Get guide joint references
        self._guide_refs = {}
        for role_name in self._joint_roles:
            self._guide_refs[role_name] = f"{self._name}_{role_name}_jInit"

        # Calculate joint positions and distances
        self._joint_positions = {}
        self._joint_distances = {}

        prev_pos = None
        for role_name in self._joint_roles:
            if cmds.objExists(self._guide_refs[role_name]):
                pos = cmds.xform(self._guide_refs[role_name], query=True, worldSpace=True, translation=True)
                self._joint_positions[role_name] = pos
                if prev_pos:
                    dist = ((pos[0]-prev_pos[0])**2 + (pos[1]-prev_pos[1])**2 + (pos[2]-prev_pos[2])**2) ** 0.5
                    self._joint_distances[f"{prev_pos}_{role_name}"] = dist
                prev_pos = pos

        logger.debug("Pre-build ready for FK chain: %s", self._name)

    def _create_groups_impl(self) -> None:
        """Create essential rig groups.

        Creates: limbGrp, scaleGrp, controllerGrp
        """
        import maya.cmds as cmds

        self._limb_grp = cmds.group(empty=True, name=f"{self._name}_limbGrp")
        self._scale_grp = cmds.group(empty=True, name=f"{self._name}_scaleGrp")
        self._controller_grp = cmds.group(empty=True, name=f"{self._name}_controllerGrp")

        # Add visibility attributes to scaleGrp
        cmds.addAttr(self._scale_grp, attributeType="bool", longName="contVis", shortName="contVis", defaultValue=True)
        cmds.addAttr(self._scale_grp, attributeType="bool", longName="jointVis", shortName="jointVis", defaultValue=True)
        cmds.addAttr(self._scale_grp, attributeType="bool", longName="rigVis", shortName="rigVis", defaultValue=False)
        cmds.setAttr(f"{self._scale_grp}.contVis", channelBox=True)
        cmds.setAttr(f"{self._scale_grp}.jointVis", channelBox=True)
        cmds.setAttr(f"{self._scale_grp}.rigVis", channelBox=True)

        cmds.parent(self._scale_grp, self._limb_grp)
        cmds.parent(self._controller_grp, self._scale_grp)

        logger.debug("Created rig groups for FK chain: %s", self._name)

    def _create_joints_impl(self) -> None:
        """Create the FK chain deformation joints."""
        import maya.cmds as cmds

        registry = get_module("fkchain")
        if not registry:
            return
        self._joint_roles = [role.name for role in registry.joint_roles]

        self._deformation_joints = {}
        previous_jnt = None

        for role_name in self._joint_roles:
            guide_ref = self._guide_refs.get(role_name)
            if not guide_ref or not cmds.objExists(guide_ref):
                continue

            cmds.select(clear=True)
            jnt_name = f"{self._name}_{role_name}_jDef"
            jnt = cmds.joint(name=jnt_name)

            # Align to guide
            cmds.delete(cmds.parentConstraint(guide_ref, jnt, maintainOffset=False))
            cmds.delete(cmds.scaleConstraint(guide_ref, jnt, maintainOffset=False))
            cmds.makeIdentity(jnt, apply=True)

            cmds.setAttr(f"{jnt}.radius", 1.0)

            # Parent under previous joint or under controller group
            if previous_jnt:
                cmds.parent(jnt, previous_jnt)
            else:
                cmds.parent(jnt, self._limb_grp)

            self._deformation_joints[role_name] = jnt
            previous_jnt = jnt

        # Define limb plug (root joint)
        self._root_jnt = self._deformation_joints.get("root")
        self._end_jnt = self._deformation_joints.get("end")

        # Connect visibility
        if self._root_jnt:
            cmds.connectAttr(f"{self._scale_grp}.jointVis", f"{self._root_jnt}.v")

        logger.debug("Created FK chain joints")

    def _create_controllers_impl(self) -> None:
        """Create the FK controllers.

        Creates one controller per joint, parented in a hierarchy.
        """
        import tik.maya as tm

        registry = get_module("fkchain")
        if not registry:
            return
        self._joint_roles = [role.name for role in registry.joint_roles]

        self._controllers = {}
        self._controller_offsets = {}
        previous_cont = None
        previous_offset = None

        for role_name in self._joint_roles:
            def_jnt = self._deformation_joints.get(role_name)
            if not def_jnt or not cmds.objExists(def_jnt):
                continue

            # Calculate controller scale based on joint distance
            cont_scale = 2.0
            if previous_offset:
                # Use distance to previous joint as guide for scale
                try:
                    pos = cmds.xform(def_jnt, query=True, worldSpace=True, translation=True)
                    prev_pos = cmds.xform(previous_offset, query=True, worldSpace=True, translation=True)
                    dist = ((pos[0]-prev_pos[0])**2 + (pos[1]-prev_pos[1])**2 + (pos[2]-prev_pos[2])**2) ** 0.5
                    cont_scale = max(dist / 4, 1.0)
                except:
                    cont_scale = 2.0

            # Create controller transform
            cont_name = f"{self._name}_{role_name}_cont"
            cont = tm.Transform.create(name=cont_name)
            cont.scale = (cont_scale, cont_scale, cont_scale)

            # Snap to deformation joint
            cont.snap_to(def_jnt, position=True, rotation=True)

            # Create offset group
            offset_grp = cmds.group(empty=True, name=f"{cont_name}_off")
            cmds.delete(cmds.parentConstraint(def_jnt, offset_grp, maintainOffset=False))
            cmds.parent(cont.name, offset_grp)

            # Parent offset group under previous controller or controller group
            if previous_offset:
                cmds.parent(offset_grp, previous_offset)
            else:
                cmds.parent(offset_grp, self._controller_grp)

            # Parent constraint controller to joint
            cmds.parentConstraint(cont.name, def_jnt, maintainOffset=False)

            self._controllers[role_name] = cont
            self._controller_offsets[role_name] = offset_grp
            previous_cont = cont
            previous_offset = offset_grp

        # Store reference to root controller
        self._root_cont = self._controllers.get("root")
        self._root_offset = self._controller_offsets.get("root")

        logger.debug("Created FK chain controllers")

    def _create_setup_impl(self) -> None:
        """Create FK setup - the hierarchy is already set up via parenting."""
        # FK chain is already set up through parent-child relationships
        # No additional IK handles or constraints needed
        pass

    def _finalize_impl(self) -> None:
        """Finalize the rig build."""
        import maya.cmds as cmds

        # Hide rig visibility
        cmds.setAttr(f"{self._scale_grp}.rigVis", 0)

        # Connect visibility to all controllers
        for offset_name in self._controller_offsets.values():
            if cmds.objExists(offset_name):
                cmds.connectAttr(f"{self._scale_grp}.contVis", f"{offset_name}.v")

        logger.debug("Finalized FK chain rig: %s", self._name)

    def _delete_impl(self) -> None:
        """Delete the built rig from the Maya scene."""
        import maya.cmds as cmds

        for grp in [self._limb_grp, self._controller_grp]:
            if grp and cmds.objExists(grp):
                cmds.delete(grp)

        self._built = False
        logger.info("Deleted FK chain rig: %s", self._name)

    def _mirror_impl(self, source_guide_names: list[str]) -> None:
        """Mirror is not implemented for FK chain.

        Args:
            source_guide_names: Names of source guides to mirror from.
        """
        logger.debug("Mirror not implemented for FK chain: %s", self._name)

    def _define_connectors(self) -> None:
        """Define plugs and sockets after joint creation."""
        import maya.cmds as cmds

        if not self._root_jnt or not cmds.objExists(self._root_jnt):
            logger.warning("Cannot define connectors - root joint not found")
            return

        if not self._end_jnt or not cmds.objExists(self._end_jnt):
            logger.warning("Cannot define connectors - end joint not found")
            return

        # Define root plug (output - for connecting to parent's plug)
        self._connectors.plugs["rootPlug"] = Plug(
            name="rootPlug",
            joint_name=self._root_jnt,
            joint_type=JointType.DEFINITIVE,
        )

        # Define sockets for ALL joints - any joint can be a socket for children
        for role_name, jnt in self._deformation_joints.items():
            socket_name = f"{role_name}Socket"
            self._connectors.sockets[socket_name] = Socket(
                name=socket_name,
                joint_name=jnt,
                joint_type=JointType.DEFINITIVE,
                accepts_plugs=["rootPlug"],
            )

        logger.debug("Defined connectors for FK chain: %s", self._name)
