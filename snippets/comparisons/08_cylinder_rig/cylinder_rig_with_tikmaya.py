"""Even simply replacing the cmds namespace with tik.maya works out of the box."""
import tik.maya as tm
from tik.maya.core import benchmark


def create_test_rig():
    # ---------------------------------------------------------
    # Create Cylinder
    # ---------------------------------------------------------
    # Create cylinder with enough subdivisions to deform smoothly
    # height=10, radius=2
    main_geo = tm.polyCylinder(
        r=2, h=10,
        sx=20, sy=20, sz=1,
        ax=[0, 1, 0],
        name='main_geo'
    )[0]

    # Move cylinder up so the base is at the origin (approximate)
    tm.xform(main_geo, translation=[0, 5, 0])

    # Freeze transformations and delete history
    tm.makeIdentity(main_geo, apply=True, t=1, r=1, s=1, n=0)
    tm.delete(main_geo, constructionHistory=True)

    # ---------------------------------------------------------
    # Create Blendshape (Bulge)
    # ---------------------------------------------------------
    # Duplicate the cylinder
    target_geo = tm.duplicate(main_geo, name='bulge_target')[0]

    # Create a non-linear flare deformer to make it "bulgy"
    flare_node, flare_handle = tm.nonLinear(target_geo, type='flare')

    # Adjust flare attributes
    tm.setAttr(f"{flare_node}.startFlareX", 1.8)
    tm.setAttr(f"{flare_node}.startFlareZ", 1.8)
    tm.setAttr(f"{flare_node}.endFlareX", 1.8)
    tm.setAttr(f"{flare_node}.endFlareZ", 1.8)
    tm.setAttr(f"{flare_node}.curve",
               -0.8)  # Negative curve creates the bulge

    # Delete history on the target to bake the deformation
    tm.delete(target_geo, constructionHistory=True)

    # Create Blendshape: Target -> Main
    bs_node = tm.blendShape(target_geo, main_geo, name='cylinder_BS')[0]

    # Delete the target mesh as requested
    tm.delete(target_geo)

    # ---------------------------------------------------------
    # Create Joint Chain
    # ---------------------------------------------------------
    tm.select(clear=True)

    joint_count = 6
    total_height = 10.0
    bind_joints = []

    # Create joints from bottom (0) to top (10)
    for i in range(joint_count):
        y_pos = (total_height / (joint_count - 1)) * i
        jnt = tm.joint(p=(0, y_pos, 0), name=f"bind_{i}_JNT")
        bind_joints.append(jnt)

    # ---------------------------------------------------------
    # Skin Main Cylinder
    # ---------------------------------------------------------
    tm.skinCluster(bind_joints, main_geo, toSelectedBones=True,
                   name='geo_skinCluster')

    # ---------------------------------------------------------
    # Create Spline IK
    # ---------------------------------------------------------
    # Create Spline IK from first to last joint
    # autoCreateCurve=True, simplifyCurve=False
    ik_handle, effector, ik_curve = tm.ikHandle(
        name='cylinder_splineIK',
        solver='ikSplineSolver',
        startJoint=bind_joints[0],
        endEffector=bind_joints[-1],
        createCurve=True
    )

    # Rename the generated curve for clarity
    ik_curve = tm.rename(ik_curve, 'spline_curve')

    # Hide the IK handle and curve to keep viewport clean
    tm.setAttr(f"{ik_handle}.visibility", 0)
    tm.setAttr(f"{ik_curve}.visibility", 0)

    # ---------------------------------------------------------
    # Create Control Joints (to drive the Spline Curve)
    # ---------------------------------------------------------
    # We will create 3 control joints: Bottom, Middle, Top
    control_positions = [0, 5, 10]
    control_joints = []

    tm.select(clear=True)

    for i, pos in enumerate(control_positions):
        # Clear selection so joints are not parented to each other (better for spline drivers)
        tm.select(clear=True)
        jnt = tm.joint(p=(0, pos, 0), name=f"driver_{i}_JNT")

        # Visually make them larger or distinct (optional)
        tm.setAttr(f"{jnt}.radius", 1.5)
        control_joints.append(jnt)

    # Bind the Spline IK Curve to these control joints
    tm.skinCluster(control_joints, ik_curve, toSelectedBones=True,
                   name='curve_skinCluster')

    # ---------------------------------------------------------
    # Create Controllers
    # ---------------------------------------------------------
    controllers = []

    for i, target_jnt in enumerate(control_joints):
        # Create a circle curve
        ctrl = tm.circle(normal=(0, 1, 0), radius=2.5, name=f"ctrl_{i}_CRV")[
            0]

        # Match controller position to the joint
        tm.matchTransform(ctrl, target_jnt, pos=True, rot=True)

        # Freeze transformations on the controller (zero out)
        tm.makeIdentity(ctrl, apply=True, t=1, r=1, s=1, n=0)

        # Parent Constraint: Controller -> Joint
        tm.parentConstraint(ctrl, target_jnt, maintainOffset=True)

        controllers.append(ctrl)

    # ---------------------------------------------------------
    # Master Controller
    # ---------------------------------------------------------
    master_ctrl = tm.circle(normal=(0, 1, 0), radius=5, name="master_cont")[
        0]

    # Color the master controller yellow (override color 17) for visibility
    tm.setAttr(f"{master_ctrl}.overrideEnabled", 1)
    tm.setAttr(f"{master_ctrl}.overrideColor", 17)

    # Parent individual controllers under master_cont
    tm.parent(controllers, master_ctrl)

    # ---------------------------------------------------------
    # Custom Attribute Connection
    # ---------------------------------------------------------
    attr_name = "customShape"

    # Add float attribute (min 0, max 1)
    tm.addAttr(master_ctrl, longName=attr_name, attributeType='float', min=0,
               max=1, keyable=True)

    # Connect attribute to Blendshape weight
    # Note: When blending, the attribute on the blendshape node is usually the name of the target
    bs_target_attr = f"{bs_node}.bulge_target"

    if tm.objExists(bs_target_attr):
        tm.connectAttr(f"{master_ctrl}.{attr_name}", bs_target_attr)
    else:
        tm.error(
            f"Warning: Could not find blendshape target attribute {bs_target_attr}")

    # ---------------------------------------------------------
    # Final Cleanup / Organization
    # ---------------------------------------------------------
    # Create a group for geometry and rig parts to keep Outliner clean
    rig_grp = tm.group(empty=True, name="RIG_SYSTEM_GRP")
    geo_grp = tm.group(empty=True, name="GEOMETRY_GRP")

    tm.parent(main_geo, geo_grp)
    tm.parent(bind_joints[0], rig_grp)
    tm.parent(ik_handle, rig_grp)
    tm.parent(ik_curve, rig_grp)

    # Group the driver joints
    driver_grp = tm.group(control_joints, name="DRIVER_JOINTS_GRP")
    tm.parent(driver_grp, rig_grp)

    # print("Rig generation complete.")

def run_benchmark(iterations=100):
    """Run the benchmark and report timing."""
    bm = benchmark.MayaBenchmark()
    bm.measure("create_test_rig", iterations=iterations, new_scene=True).run(
        create_test_rig)

if __name__ == "__main__":
    run_benchmark()
