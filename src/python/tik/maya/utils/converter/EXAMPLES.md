# Converter Examples: Before & After

This document shows conversion examples in both directions:
- **tik.maya → maya.cmds** (semantic expansion)
- **maya.cmds → tik.maya** (semantic lifting)

---

# Part 1: tik.maya → maya.cmds

## Example 0: Node Resolution with resolve()

The most common pattern: wrapping existing Maya nodes with tik.maya.

### Before (tik.maya)
```python
import tik.maya as tm

# Wrap an existing node
node = tm.resolve('myNode')

# Now use tik.maya API
node['translateX'].set(5.0)
node.scale_x = 2.0
node.visibility = True
```

### After (maya.cmds)
```python
from maya import cmds

# Work directly with node name string
node = 'myNode'

# Use cmds API
cmds.setAttr(f'{node}.translateX', 5.0)
cmds.setAttr(f'{node}.scaleX', 2.0)
cmds.setAttr(f'{node}.visibility', True)
```

---

## Example 1: Basic Node Creation

### Before (tik.maya)
```python
from tik.maya import Transform, Joint, Mesh

# Create a transform
root = Transform.create(name='root_grp')

# Create a joint
joint1 = Joint.create(name='joint1')

# Create a mesh
sphere = Mesh.create('polySphere', radius=2)
```

### After (maya.cmds)
```python
from maya import cmds

# Create a transform
root = cmds.createNode('transform', name='root_grp')

# Create a joint
joint1 = cmds.joint(name='joint1')

# Create a mesh
sphere = cmds.polySphere(radius=2)[0]
```

---

## Example 2: Attribute Operations

### Before (tik.maya)
```python
from tik.maya import Transform

node = Transform.create(name='myNode')

# Get attribute
tx_value = node['translateX'].get()

# Set attribute (method)
node['translateX'].set(5.0)

# Set attribute (value property)
node['translateY'].value = 10.0

# Set via property
node.translate = (1, 2, 3)
node.rotate_x = 45.0
```

### After (maya.cmds)
```python
from maya import cmds

node = cmds.createNode('transform', name='myNode')

# Get attribute
tx_value = cmds.getAttr(f'{node}.translateX')

# Set attribute (method)
cmds.setAttr(f'{node}.translateX', 5.0)

# Set attribute (value property)
cmds.setAttr(f'{node}.translateY', 10.0)

# Set via property
cmds.setAttr(f'{node}.translate', *[1, 2, 3])
cmds.setAttr(f'{node}.rotateX', 45.0)
```

---

## Example 3: Attribute Connections

### Before (tik.maya)
```python
from tik.maya import Transform

src = Transform.create(name='source')
dst = Transform.create(name='destination')

# Connect using method
src['translateX'].connect(dst['translateX'])

# Connect using >> operator
src['translateY'] >> dst['translateY']
src['translateZ'] >> dst['translateZ']
```

### After (maya.cmds)
```python
from maya import cmds

src = cmds.createNode('transform', name='source')
dst = cmds.createNode('transform', name='destination')

# Connect using method
cmds.connectAttr(f'{src}.translateX', f'{dst}.translateX', force=True)

# Connect using >> operator
cmds.connectAttr(f'{src}.translateY', f'{dst}.translateY', force=True)
cmds.connectAttr(f'{src}.translateZ', f'{dst}.translateZ', force=True)
```

---

## Example 4: Node Operations

### Before (tik.maya)
```python
from tik.maya import Transform

node = Transform.create(name='originalName')

# Rename
node.rename('newName')

# Duplicate
dupe = node.duplicate()

# Delete
node.delete()

# Select
dupe.select()
```

### After (maya.cmds)
```python
from maya import cmds

node = cmds.createNode('transform', name='originalName')

# Rename
cmds.rename(node, 'newName')

# Duplicate
dupe = cmds.duplicate(node)[0]

# Delete
cmds.delete(node)

# Select
cmds.select(dupe, replace=True)
```

---

## Example 5: Attribute Locking

### Before (tik.maya)
```python
from tik.maya import Transform

node = Transform.create(name='ctrl')

# Lock attributes
node['translateX'].lock()
node['translateY'].lock()
node['translateZ'].lock()

# Unlock attribute
node['translateX'].unlock()
```

### After (maya.cmds)
```python
from maya import cmds

node = cmds.createNode('transform', name='ctrl')

# Lock attributes
cmds.setAttr(f'{node}.translateX', lock=True)
cmds.setAttr(f'{node}.translateY', lock=True)
cmds.setAttr(f'{node}.translateZ', lock=True)

# Unlock attribute
cmds.setAttr(f'{node}.translateX', lock=False)
```

---

## Example 6: Transform Operations

### Before (tik.maya)
```python
from tik.maya import Transform

node = Transform.create(name='myTransform')

# Set transforms
node.translate = (10, 20, 30)
node.rotate = (0, 45, 0)
node.scale = (1, 2, 1)

# Freeze transforms
node.freeze()
```

### After (maya.cmds)
```python
from maya import cmds

node = cmds.createNode('transform', name='myTransform')

# Set transforms
cmds.setAttr(f'{node}.translate', *[10, 20, 30])
cmds.setAttr(f'{node}.rotate', *[0, 45, 0])
cmds.setAttr(f'{node}.scale', *[1, 2, 1])

# Freeze transforms
cmds.makeIdentity(node, apply=True, translate=True, rotate=True, scale=True)
```

---

## Example 7: Adding Custom Attributes

### Before (tik.maya)
```python
from tik.maya import Transform

node = Transform.create(name='ctrl')

# Add custom attributes
node.add_attr('customFloat', attributeType='float', defaultValue=0.0)
node.add_attr('customBool', attributeType='bool', defaultValue=True)
```

### After (maya.cmds)
```python
from maya import cmds

node = cmds.createNode('transform', name='ctrl')

# Add custom attributes
cmds.addAttr(node, longName='customFloat', attributeType='float', defaultValue=0.0)
cmds.addAttr(node, longName='customBool', attributeType='bool', defaultValue=True)
```

---

## Unsupported Operations (Preserved as Comments)

Some operations cannot be automatically converted because they use OpenMaya
or have complex behavior. These are flagged in the conversion report.

### Before (tik.maya)
```python
from tik.maya import Mesh

mesh = Mesh.create('polySphere')

# These use OpenMaya internally
verts = mesh.vertices()           # Returns MPointArray
mesh.unlock_normals(soften=True)  # Uses MFnMesh
colors = mesh.get_vertex_colors() # Returns MColorArray
```

### After (maya.cmds)
```python
from maya import cmds

mesh = cmds.polySphere()[0]

# UNSUPPORTED: vertices() - Returns OpenMaya MPointArray; no direct cmds equivalent
# verts = mesh.vertices()

# UNSUPPORTED: unlock_normals() - Uses OpenMaya MFnMesh; no direct cmds equivalent
# mesh.unlock_normals(soften=True)

# UNSUPPORTED: get_vertex_colors() - Returns OpenMaya MColorArray; no direct cmds equivalent
# colors = mesh.get_vertex_colors()
```

---

## Conversion Report Example

When converting code, you receive a detailed report:

```
============================================================
CONVERSION REPORT
============================================================
Rules applied:        8
Helpers expanded:     0
Unsupported:          2
Warnings:             0
------------------------------------------------------------

RULES APPLIED:
  Line 5: transform_create
  Line 6: joint_create
  Line 9: plug_set
  Line 10: transform_property_set
  Line 13: plug_connect
  Line 14: plug_rshift_connect
  Line 17: node_rename
  Line 18: dagnode_select

UNSUPPORTED OPERATIONS:
  Line 21: unlock_normals: Uses OpenMaya MFnMesh; no direct cmds equivalent
    Original: mesh.unlock_normals()
  Line 22: vertices: Returns OpenMaya MPointArray; no direct cmds equivalent
    Original: verts = mesh.vertices()
============================================================
```

---

# Part 2: maya.cmds → tik.maya

## Example R1: Basic Node Creation

### Before (maya.cmds)
```python
from maya import cmds

# Create nodes
root = cmds.createNode('transform', name='root_grp')
joint1 = cmds.joint(name='joint1')
sphere = cmds.polySphere(radius=2)[0]
```

### After (tik.maya)
```python
from tik.maya import Transform, Joint, Mesh

# Create nodes
root = Transform.create(name='root_grp')
joint1 = Joint.create(name='joint1')
sphere = Mesh.create('polySphere', radius=2)
```

---

## Example R2: Attribute Operations

### Before (maya.cmds)
```python
from maya import cmds

node = cmds.createNode('transform', name='myNode')

# Get attribute
tx_value = cmds.getAttr('myNode.translateX')

# Set attribute
cmds.setAttr('myNode.translateX', 5.0)
cmds.setAttr('myNode.visibility', True)

# Lock/unlock attributes
cmds.setAttr('myNode.translateY', lock=True)
cmds.setAttr('myNode.translateZ', lock=False)
```

### After (tik.maya)
```python
from tik.maya import Transform

node = Transform.create(name='myNode')

# Get attribute
tx_value = node['translateX'].get()

# Set attribute
node['translateX'].set(5.0)
node['visibility'].set(True)

# Lock/unlock attributes
node['translateY'].lock()
node['translateZ'].unlock()
```

---

## Example R3: Connections

### Before (maya.cmds)
```python
from maya import cmds

src = cmds.createNode('transform', name='source')
dst = cmds.createNode('transform', name='destination')

# Connect attributes
cmds.connectAttr('source.translateX', 'destination.translateX', force=True)
cmds.connectAttr('source.translateY', 'destination.translateY', force=True)
```

### After (tik.maya)
```python
from tik.maya import Transform

src = Transform.create(name='source')
dst = Transform.create(name='destination')

# Connect attributes
src['translateX'].connect(dst['translateX'], force=True)
src['translateY'].connect(dst['translateY'], force=True)
```

---

## Example R4: Node Operations

### Before (maya.cmds)
```python
from maya import cmds

node = cmds.createNode('transform', name='originalName')

# Rename
cmds.rename('originalName', 'newName')

# Select
cmds.select('newName', replace=True)

# Freeze transforms
cmds.makeIdentity('newName', apply=True, translate=True, rotate=True, scale=True)

# Delete
cmds.delete('newName')
```

### After (tik.maya)
```python
from tik.maya import Transform

node = Transform.create(name='originalName')

# Rename
node.rename('newName')

# Select
node.select()

# Freeze transforms
node.freeze(translate=True, rotate=True, scale=True)

# Delete
node.delete()
```

---

## Unsupported cmds Operations (Preserved)

Some cmds operations cannot be automatically lifted because they depend on scene state
or have no direct tik.maya equivalent.

### Before (maya.cmds)
```python
from maya import cmds

node = cmds.createNode('transform')

# These are unsupported - query/selection operations
selection = cmds.ls(selection=True)
children = cmds.listRelatives(node, children=True)
connections = cmds.listConnections(node)
history = cmds.listHistory(node)
```

### After (tik.maya)
```python
from tik.maya import Transform

node = Transform.create()

# UNSUPPORTED: cmds.ls() - Selection/query operation - context dependent
# selection = cmds.ls(selection=True)

# UNSUPPORTED: cmds.listRelatives() - Query operation - requires scene state
# children = cmds.listRelatives(node, children=True)

# UNSUPPORTED: cmds.listConnections() - Query operation - requires scene state
# connections = cmds.listConnections(node)

# UNSUPPORTED: cmds.listHistory() - Query operation - requires scene state
# history = cmds.listHistory(node)
```

---

## Reverse Conversion Report Example

When converting cmds code to tik.maya, you receive a similar detailed report:

```
============================================================
CONVERSION REPORT
============================================================
Rules applied:        10
Helpers expanded:     0
Unsupported:          2
Warnings:             0
------------------------------------------------------------

RULES APPLIED:
  Line 5: createnode_to_transform
  Line 6: joint_to_joint_create
  Line 7: polysphere_to_mesh_create
  Line 10: setattr_to_plug_set
  Line 11: setattr_to_plug_set
  Line 14: setattr_lock_to_plug_lock
  Line 17: connectattr_to_plug_connect
  Line 20: rename_to_node_rename
  Line 21: select_to_node_select
  Line 24: makeidentity_to_freeze

UNSUPPORTED OPERATIONS:
  Line 27: cmds.ls: Selection/query operation - context dependent
    Original: selection = cmds.ls(selection=True)
  Line 28: cmds.listRelatives: Query operation - requires scene state
    Original: children = cmds.listRelatives(node, children=True)
============================================================
```

