"""
FK Chain with Controllers - tik.maya approach
=============================================
This example creates the same complete FK chain with:
- Joint hierarchy
- NURBS curve controllers
- Controller-to-joint connections
- Proper naming and organization

Notice:
- Significantly fewer lines of code
- More readable, pythonic syntax
- Property-based access
- Object method chaining

Run this in Maya's Script Editor to see the results.
"""
import tik.maya as tm
from tik.maya.core import benchmark


def create_fk_chain_tikmaya(joint_count=5, base_name="arm"):
    """Create a complete FK chain with controllers using tik.maya."""

    joints = []
    controllers = []
    controller_groups = []

    # ========================================
    # CREATE JOINTS
    # ========================================
    tm.select(clear=True)
    for index in range(joint_count):
        joint = tm.joint(
            position=(index * 3, 0, 0),
            name=f"{base_name}_{index:02d}_JNT"
        )
        joints.append(joint)

    # Orient joints
    tm.joint(joints[0], edit=True, orientJoint="xyz",
             secondaryAxisOrient="yup", children=True)

    # ========================================
    # CREATE CONTROLLERS
    # ========================================
    for index, joint in enumerate(joints):
        # Create circle controller
        ctrl = tm.circle(
            name=f"{base_name}_{index:02d}_CTRL",
            normal=(1, 0, 0),
            radius=1.5
        )[0]
        controllers.append(ctrl)

        # Create offset group
        grp = tm.group(empty=True, name=f"{base_name}_{index:02d}_GRP")
        controller_groups.append(grp)

        # Parent and snap - cleaner syntax!
        ctrl.parent = grp
        grp.snap_to(joint)

        # Connect with >> operator
        ctrl["rotate"] >> joint["rotate"]

        # Set controller color - property access on shapes
        for shape in ctrl.shapes:
            shape.color = 17  # Yellow

    # ========================================
    # PARENT CONTROLLER HIERARCHY
    # ========================================
    for index in range(len(controller_groups) - 1, 0, -1):
        controller_groups[index].parent = controllers[index - 1]

    # ========================================
    # LOCK AND HIDE UNUSED ATTRIBUTES
    # ========================================
    for ctrl in controllers:
        for attr in ["scaleX", "scaleY", "scaleZ", "visibility"]:
            ctrl[attr].locked = True
            ctrl[attr].keyable = False

    # ========================================
    # ORGANIZE
    # ========================================
    rig_grp = tm.group(empty=True, name=f"{base_name}_RIG_GRP")
    jnt_grp = tm.group(empty=True, name=f"{base_name}_JNT_GRP")
    ctrl_grp = tm.group(empty=True, name=f"{base_name}_CTRL_GRP")

    joints[0].parent = jnt_grp
    controller_groups[0].parent = ctrl_grp
    jnt_grp.parent = rig_grp
    ctrl_grp.parent = rig_grp

    return joints, controllers


def run_benchmark(iterations=50):
    """Run the benchmark and report timing."""

    bm = benchmark.MayaBenchmark()
    bm.measure("create_fk_chain_tikmaya", iterations=iterations, new_scene=True).run(
        create_fk_chain_tikmaya)


if __name__ == "__main__":
    run_benchmark()

