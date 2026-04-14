# Tik Trigger Test Harness
# Paste into Maya Script Editor and run

from tik.trigger.session import GuideSession
import maya.cmds as cmds

# Create a fresh session
session = GuideSession()
cmds.file(new=True, force=True)

print("Session ready. Examples:")


# --- 1. Create a base module and its guides ---
base = session.create_module("base", "myBase")
base.create_guides()
print(f"Created base module with {len(base.guides)} guides")
# Result: Creates a single root joint at origin


# --- 2. Create a connector module and its guides ---
connector = session.create_module("connector", "myConnector")
connector.create_guides()
print(f"Created connector module with {len(connector.guides)} guides")


# --- 3. Connect base to connector ---
session.connect("myBase", "rootPlug", "myConnector", "rootSocket")
print("Connected myBase:rootPlug -> myConnector:rootSocket")


# --- 4. Build all modules ---
for module_id, module in session.modules.items():
    module.build()
    print(f"Built {module_id}, plugs={list(module.plugs.keys())}, sockets={list(module.sockets.keys())}")


# --- 5. Save guides to file ---
session.save("C:/temp/test_guides.trg")
print("Saved guides to C:/temp/test_guides.trg")


# --- 6. Load guides from file ---
import maya.cmds as cmds
cmds.file(new=True, force=True)

new_session = GuideSession()
new_session.load("C:/temp/test_guides.trg")
print(f"Loaded session with {len(new_session.modules)} modules")
