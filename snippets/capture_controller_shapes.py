import sys
from importlib import reload

kill_list = []
for name, _module in sys.modules.items():
    if name.startswith("tikmaya"):
        kill_list.append(name)
for x in kill_list:
    sys.modules.pop(x)

tikmaya_path = "D:/dev/tikworks/src"
if tikmaya_path not in sys.path:
    sys.path.append(tikmaya_path)

import tik.maya as tm
from tik.maya.utils import control_shapes

categories = ["arrows", "basics", "panels", "letters", "numbers", "pins",
              "symbols", "anatomy"]

cs_handler = control_shapes.ControlShapeLibrary()

for category in categories:
    category_node = tm.resolve(category)
    shapes = category_node.collect_shape_transforms()
    for shape in shapes:
        control_shapes.capture_to_disk(shape, name=shape.name, category=category)
        
        
control_shapes.capture_to_disk("FootPrint", name="FootPrint", category="anatomy")
