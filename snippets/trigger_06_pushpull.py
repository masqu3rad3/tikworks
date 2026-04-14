# Trigger PushPull Module
# Converts rotation to translation (eyelids, lips)

import maya.cmds as cmds
from tik.trigger.session import GuideSession

session = GuideSession()

# Create pushpull module
pp = session.create_module("pushpull", "pp_0")
pp.set_settings({
    "extractAxis": "X",
    "translateAxis": "Y",
    "extractMultiplier": 0.5,
    "driverRange": [-45.0, 45.0],
    "drivenRange": [0.0, 2.0]
})
pp.create_guides()

print(f"PushPull guides: {len(pp.guides)} joints")
for g in pp.guides:
    print(f"  {g.name}: {g.position}")

pp.build()
print(f"PushPull built: {pp.is_built}")
print(f"Plugs: {list(pp.plugs.keys())}")
print(f"Sockets: {list(pp.sockets.keys())}")

# Check scene
joints = cmds.ls("*_jDef", type="joint")
print(f"Deformation joints: {joints}")
