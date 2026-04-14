# Trigger Arm Module
# IK/FK arm with shoulder, elbow, hand

import maya.cmds as cmds
from tik.trigger.session import GuideSession

session = GuideSession()

# Create arm module (L side)
arm = session.create_module("arm", "arm_L")
arm.create_guides()

print(f"Arm guides: {len(arm.guides)} joints")
for g in arm.guides:
    print(f"  {g.name}: pos={g.position}")

arm.build()
print(f"Arm built: {arm.is_built}")
print(f"Plugs: {list(arm.plugs.keys())}")
print(f"Sockets: {list(arm.sockets.keys())}")

# Scene check
joints = cmds.ls("*_jnt", type="joint")
print(f"All joints: {joints}")
