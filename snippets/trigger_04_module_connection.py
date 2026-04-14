# Trigger Module Connection
# Connect child module to parent module via socket/plug

import maya.cmds as cmds
from tik.trigger.session import GuideSession

session = GuideSession()

# Create base (parent)
base = session.create_module("base", "base_0")
base.create_guides()
base.build()

# Create connector (child) - will connect to base
connector = session.create_module("connector", "conn_0")
connector.create_guides()
connector.build()

# Connect connector's rootSocket to base's rootPlug
session.connect("base_0", "rootPlug", "conn_0", "rootSocket")
print(f"Connections: {session.connections}")

# Verify
print(f"Connector socket connected to: {connector.sockets['rootSocket'].connected_plug}")
