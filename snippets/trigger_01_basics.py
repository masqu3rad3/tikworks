# Trigger Basics - Single Module
# Create guides, build, check plugs/sockets

import maya.cmds as cmds
from tik.trigger.session import GuideSession

session = GuideSession()

# Create a base module
base = session.create_module("base", "base_0")
print(f"Module: {base.name}, type: {base.module_name}")

# Create guides (makes Maya joints)
base.create_guides()
print(f"Guides: {[g.name for g in base.guides]}")

# Build the rig
base.build()
print(f"Built: {base.is_built}")
print(f"Plugs: {list(base.plugs.keys())}")
print(f"Sockets: {list(base.sockets.keys())}")

# Check scene joints
joints = cmds.ls("*_jnt", type="joint")
print(f"Scene joints: {joints}")

# Check groups
groups = cmds.ls("*_limbGrp", "*_scaleGrp", "*_controllerGrp", type="transform")
print(f"Scene groups: {groups}")
