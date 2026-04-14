# Trigger Connector Module
# Simple module with optional controller

import maya.cmds as cmds
from tik.trigger.session import GuideSession

session = GuideSession()

# Create connector with curve-as-shape setting
connector = session.create_module("connector", "conn_0")
connector.set_settings({"curveAsShape": False})
connector.create_guides()

print(f"Connector guides: {[g.name for g in connector.guides]}")

connector.build()
print(f"Plugs: {list(connector.plugs.keys())}")
print(f"Sockets: {list(connector.sockets.keys())}")

# Joints created
joints = cmds.ls("*_jnt", type="joint")
print(f"Scene joints: {joints}")
