"""
FK Chain with Controllers - maya.cmds approach
==============================================
This example creates a complete FK chain with:
- Joint hierarchy
- NURBS curve controllers
- Controller-to-joint connections
- Proper naming and organization

This is a real-world rigging scenario that shows the verbosity
of traditional maya.cmds code.

Run this in Maya's Script Editor to see the results.
"""
from maya import cmds
from tik.maya.core import benchmark


def create_fk_chain_cmds(joint_count=5, base_name="arm"):
    """Create a complete FK chain with controllers using maya.cmds."""

    joints = []
    controllers = []
    controller_groups = []

    # ========================================
    # CREATE JOINTS
    # ========================================
    cmds.select(clear=True)
    for index in range(joint_count):
        joint = cmds.joint(
            position=(index * 3, 0, 0),
            name=f"{base_name}_{index:02d}_JNT"
        )
        joints.append(joint)

    # Orient joints
    cmds.joint(joints[0], edit=True, orientJoint="xyz",
               secondaryAxisOrient="yup", children=True)

    # ========================================
    # CREATE CONTROLLERS
    # ========================================
    for index, joint in enumerate(joints):
        # Create circle controller
        ctrl_name = f"{base_name}_{index:02d}_CTRL"
        ctrl = cmds.circle(
            name=ctrl_name,
            normal=(1, 0, 0),
            radius=1.5
        )[0]
        controllers.append(ctrl)

        # Create offset group
        grp_name = f"{base_name}_{index:02d}_GRP"
        grp = cmds.group(empty=True, name=grp_name)
        controller_groups.append(grp)

        # Parent controller under group
        cmds.parent(ctrl, grp)

        # Match group to joint position/rotation
        joint_pos = cmds.xform(joint, query=True,
                               worldSpace=True, translation=True)
        joint_rot = cmds.xform(joint, query=True,
                               worldSpace=True, rotation=True)
        cmds.xform(grp, worldSpace=True, translation=joint_pos)
        cmds.xform(grp, worldSpace=True, rotation=joint_rot)

        # Connect controller rotation to joint rotation
        cmds.connectAttr(f"{ctrl}.rotate", f"{joint}.rotate")

        # Set controller color (yellow = 17)
        shape = cmds.listRelatives(ctrl, shapes=True)[0]
        cmds.setAttr(f"{shape}.overrideEnabled", 1)
        cmds.setAttr(f"{shape}.overrideColor", 17)

    # ========================================
    # PARENT CONTROLLER HIERARCHY
    # ========================================
    for index in range(len(controller_groups) - 1, 0, -1):
        cmds.parent(controller_groups[index], controllers[index - 1])

    # ========================================
    # LOCK AND HIDE UNUSED ATTRIBUTES
    # ========================================
    for ctrl in controllers:
        for attr in ["scaleX", "scaleY", "scaleZ", "visibility"]:
            cmds.setAttr(f"{ctrl}.{attr}", lock=True, keyable=False,
                        channelBox=False)

    # ========================================
    # ORGANIZE
    # ========================================
    rig_grp = cmds.group(empty=True, name=f"{base_name}_RIG_GRP")
    jnt_grp = cmds.group(empty=True, name=f"{base_name}_JNT_GRP")
    ctrl_grp = cmds.group(empty=True, name=f"{base_name}_CTRL_GRP")

    cmds.parent(joints[0], jnt_grp)
    cmds.parent(controller_groups[0], ctrl_grp)
    cmds.parent(jnt_grp, rig_grp)
    cmds.parent(ctrl_grp, rig_grp)

    return joints, controllers


def run_benchmark(iterations=50):
    """Run the benchmark and report timing."""
    bm = benchmark.MayaBenchmark()
    bm.measure("create_fk_chain_cmds", iterations=iterations, new_scene=True).run(
        create_fk_chain_cmds)


if __name__ == "__main__":
    run_benchmark()

