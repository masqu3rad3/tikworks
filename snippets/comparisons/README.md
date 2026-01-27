# tik.maya Comparison Examples

This folder contains side-by-side comparisons between `maya.cmds` and `tik.maya` approaches to common rigging tasks.

## Organization

Each subfolder contains paired examples:
- `*_cmds.py` - Traditional maya.cmds approach
- `*_tikmaya.py` - tik.maya approach

## Examples

### 0. `00_quick_comparison/`
**Side-by-side comparison in one file**
- Quick overview of all the key differences
- Run this first for a fast introduction!

### 1. `01_joint_chain/`
**Creating and manipulating joint chains**
- Demonstrates: Code readability, property-based API

### 2. `02_attribute_connections/`
**Connecting attributes and building node networks**
- Demonstrates: Operator overloading (`>>`, `+`, `*`), reduced boilerplate

### 3. `03_fk_chain/`
**Building a complete FK chain with controllers**
- Demonstrates: Code reduction, cleaner workflow

### 4. `04_attribute_math/`
**Creating math node networks for driven setups**
- Demonstrates: Mathematical operators, dramatic code reduction

### 5. `05_batch_operations/`
**Batch processing nodes and attributes**
- Demonstrates: Performance gains, pythonic iteration

### 6. `06_stretchy_ik/`
**Real-world stretchy IK limb setup**
- Demonstrates: Complex math networks as readable expressions
- ~60% code reduction for the stretch network!

### 7. `07_twist_joints/`
**Twist joint distribution setup**
- Demonstrates: Blend math with operators, compound attribute math
- Per-axis AND compound (vector) math examples

### 8. `08_cylinder_rig/`
**Spline IK simple Cylinder rig**
- Demonstrates: Direct cmds replacement without changing anything else
- Easy to swap tik.maya into existing codebases

## How to Run

1. Copy the script contents into Maya's Script Editor
2. Run both versions (cmds and tikmaya) to compare
3. Check the timing output at the end

## Requirements

- Maya 2024+
- tik.maya in PYTHONPATH: `sys.path.insert(0, "path/to/tikworks/src")`

## Key Takeaways

| Feature | maya.cmds | tik.maya |
|---------|-----------|----------|
| Attribute access | `cmds.getAttr("node.attr")` | `node["attr"].value` or `node.translate` |
| Attribute set | `cmds.setAttr("node.attr", val)` | `node["attr"].value = val` |
| Connections | `cmds.connectAttr("a.out", "b.in")` | `a["out"] >> b["in"]` |
| Math networks | 10+ lines per operation | `(a + b) * c >> output` |
| Parent query | `cmds.listRelatives(n, p=True)[0]` | `node.parent` |
| Lock attribute | `cmds.setAttr("n.a", lock=True)` | `node["attr"].locked = True` |

