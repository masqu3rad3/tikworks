# Trigger Full Rig Build
# Base + Arm connected together

import maya.cmds as cmds
from tik.trigger.session import GuideSession

session = GuideSession()

# Create base (root of hierarchy)
base = session.create_module("base", "base_0")
base.create_guides()
base.build()
print(f"Base: plugs={list(base.plugs.keys())}, sockets={list(base.sockets.keys())}")

# Create arm (child) - connects to base
arm = session.create_module("arm", "arm_L")
arm.create_guides()
arm.build()
print(f"Arm: plugs={list(arm.plugs.keys())}, sockets={list(arm.sockets.keys())}")

# Connect arm's collarSocket to base's rootPlug
# (Check actual socket names first)
print(f"\nBase plugs: {base.plugs}")
print(f"Arm sockets: {arm.sockets}")

# Build all
session.build_all()
print(f"\nAll built: {all(m.is_built for m in session.modules.values())}")

# Scene summary
print(f"\nScene joints: {cmds.ls('*_jnt', type='joint')}")
print(f"Scene groups: {cmds.ls('*_Grp', type='transform')}")
