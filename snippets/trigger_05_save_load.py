# Trigger Save/Load
# Persist guides to file and reload

import maya.cmds as cmds
from tik.trigger.session import GuideSession

session = GuideSession()

# Create modules
base = session.create_module("base", "base_0")
base.create_guides()

arm = session.create_module("arm", "arm_L")
arm.create_guides()

print(f"Before save: {len(session.modules)} modules")

# Save
session.save("C:/temp/test_rig.trg")
print("Saved to C:/temp/test_rig.trg")

# Clear and reload
cmds.file(new=True, force=True)

new_session = GuideSession()
new_session.load("C:/temp/test_rig.trg")
print(f"After load: {len(new_session.modules)} modules")
print(f"Module names: {list(new_session.modules.keys())}")
