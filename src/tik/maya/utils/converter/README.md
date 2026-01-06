# tik.maya Bidirectional Code Converter

A rule-based code conversion tool that translates between **tik.maya** and **maya.cmds** through semantic expansion/lifting.

## Overview

The converter supports **two directions**:

### tik.maya → maya.cmds (Semantic Expansion)
- Recognizes tik.maya surface-level expressions as written
- Expands those expressions into explicit, imperative `maya.cmds` equivalents
- Converts *intent*, not implementation

### maya.cmds → tik.maya (Semantic Lifting)
- Recognizes maya.cmds patterns in source code
- Lifts those patterns into idiomatic `tik.maya` expressions
- Compresses explicit cmds calls into the equivalent tik.maya API

Both directions:
- Do NOT inspect internals or record runtime behavior
- Are deterministic and testable
- Report unsupported patterns honestly

## Architecture

```
converter/
├── __init__.py          # Public API exports (both directions)
├── engine.py            # tik.maya → cmds engine
├── engine_reverse.py    # cmds → tik.maya engine
├── rules.py             # tik.maya → cmds rules
├── rules_reverse.py     # cmds → tik.maya rules
├── codegen.py           # cmds code generation utilities
├── codegen_tik.py       # tik.maya code generation utilities
├── helpers.py           # Blessed helper expansion registry
├── parsing.py           # AST parsing utilities
└── report.py            # Shared reporting structures
```

## Usage

### tik.maya → maya.cmds

```python
from tik.maya.utils.converter import convert

tik_code = '''
from tik.maya import Transform

node = Transform.create(name='myNode')
node['translateX'].set(5.0)
'''

result = convert(tik_code)
print(result.converted_code)
print(result.summary())
```

### maya.cmds → tik.maya

```python
from tik.maya.utils.converter import convert_to_tik

cmds_code = '''
from maya import cmds

node = cmds.createNode('transform', name='myNode')
cmds.setAttr('myNode.translateX', 5.0)
'''

result = convert_to_tik(cmds_code)
print(result.converted_code)
print(result.summary())
```

### Using the Converter Classes Directly

```python
from tik.maya.utils.converter import Converter, ReverseConverter

# tik.maya → cmds
converter = Converter(
    add_imports=True,      # Add 'from maya import cmds'
    add_header=True,       # Add documentation header
    preserve_comments=True # Preserve original comments
)
result = converter.convert(source_code)

# cmds → tik.maya
reverse_converter = ReverseConverter(
    add_imports=True,      # Add tik.maya imports
    add_header=True,       # Add documentation header
    preserve_comments=True # Preserve original comments
)
result = reverse_converter.convert(source_code)
```

### Examining Results

```python
# Access converted code
print(result.converted_code)

# Check what was converted
for entry in result.rules_applied:
    print(f"Line {entry.line_number}: {entry.rule_name}")

# Check for unsupported operations  
for entry in result.unsupported_operations:
    print(f"Line {entry.line_number}: {entry.message}")

# Get summary
print(result.summary())
```

## Supported Patterns

### Node Resolution

| tik.maya | maya.cmds |
|----------|-----------|
| `resolve('nodeName')` | `'nodeName'` |
| `tm.resolve('nodeName')` | `'nodeName'` |
| `tik.maya.resolve('nodeName')` | `'nodeName'` |

The `resolve()` function wraps a Maya node name into a tik.maya object. In cmds code, you work directly with string node names, so `resolve()` calls are converted to just the node name string.

### Node Creation

| tik.maya | maya.cmds |
|----------|-----------|
| `Transform.create(name='x')` | `cmds.createNode('transform', name='x')` |
| `Joint.create(name='j')` | `cmds.joint(name='j')` |
| `Mesh.create('polySphere')` | `cmds.polySphere()[0]` |
| `Curve.create(point=pts)` | `cmds.curve(point=pts)` |
| `Locator.create()` | `cmds.spaceLocator()[0]` |

### Attribute Access

| tik.maya | maya.cmds |
|----------|-----------|
| `node['attr'].get()` | `cmds.getAttr(f'{node}.attr')` |
| `node['attr'].set(val)` | `cmds.setAttr(f'{node}.attr', val)` |
| `node['attr'].value` (read) | `cmds.getAttr(f'{node}.attr')` |
| `node['attr'].value = val` | `cmds.setAttr(f'{node}.attr', val)` |

### Connections

| tik.maya | maya.cmds |
|----------|-----------|
| `plug.connect(other)` | `cmds.connectAttr(src, dst, force=True)` |
| `src['a'] >> dst['b']` | `cmds.connectAttr(src.a, dst.b, force=True)` |

### Transform Properties

| tik.maya | maya.cmds |
|----------|-----------|
| `node.translate = (x,y,z)` | `cmds.setAttr(f'{node}.translate', *val)` |
| `node.translate_x = val` | `cmds.setAttr(f'{node}.translateX', val)` |
| `node.rotate = (x,y,z)` | `cmds.setAttr(f'{node}.rotate', *val)` |
| `node.scale = (x,y,z)` | `cmds.setAttr(f'{node}.scale', *val)` |
| `node.visibility = val` | `cmds.setAttr(f'{node}.visibility', val)` |

### Node Methods

| tik.maya | maya.cmds |
|----------|-----------|
| `node.rename('name')` | `cmds.rename(node, 'name')` |
| `node.delete()` | `cmds.delete(node)` |
| `node.duplicate()` | `cmds.duplicate(node)[0]` |
| `node.add_attr('name', ...)` | `cmds.addAttr(node, longName='name', ...)` |
| `node.select()` | `cmds.select(node, replace=True)` |

### Attribute Methods

| tik.maya | maya.cmds |
|----------|-----------|
| `plug.lock()` | `cmds.setAttr(path, lock=True)` |
| `plug.unlock()` | `cmds.setAttr(path, lock=False)` |

### Transform Methods

| tik.maya | maya.cmds |
|----------|-----------|
| `transform.freeze()` | `cmds.makeIdentity(apply=True, ...)` |

## Unsupported Operations

### tik.maya → cmds (Unsupported tik.maya Operations)

The following tik.maya operations are explicitly **not supported** for automatic conversion because they:
- Use OpenMaya extensively
- Have complex or context-dependent behavior
- Return OpenMaya types (MVector, MMatrix, etc.)

| Method | Reason |
|--------|--------|
| `unlock_normals()` | Uses OpenMaya MFnMesh |
| `get_vertex_colors()` | Returns OpenMaya MColorArray |
| `set_vertex_colors()` | Uses OpenMaya MFnMesh |
| `vertices()` | Returns OpenMaya MPointArray |
| `cvs()` | Returns OpenMaya MPointArray |
| `scale_points()` | Uses OpenMaya MFnNurbsCurve |
| `snap_to()` | Uses OpenMaya MFnTransform |
| `world_translation` | Returns OpenMaya MVector |
| `world_matrix` | Returns OpenMaya MMatrix |
| `collect_hierarchy()` | Recursive traversal |

### cmds → tik.maya (Unsupported cmds Operations)

The following cmds functions are explicitly **not supported** for automatic conversion because they:
- Are query/selection-based operations
- Depend on scene state
- Have no direct tik.maya equivalent

| Command | Reason |
|---------|--------|
| `cmds.ls()` | Selection/query operation - context dependent |
| `cmds.listRelatives()` | Query operation - requires scene state |
| `cmds.listConnections()` | Query operation - requires scene state |
| `cmds.listAttr()` | Query operation - requires scene state |
| `cmds.listHistory()` | Query operation - requires scene state |
| `cmds.xform()` | Complex query/set operation - partially supported |
| `cmds.parent()` | Hierarchy operation - requires careful handling |
| `cmds.setParent()` | Hierarchy operation - requires careful handling |
| `cmds.polyEvaluate()` | Query operation - requires scene state |
| `cmds.pointPosition()` | Query operation - requires scene state |

When unsupported operations are encountered, the converter:
1. Does NOT attempt conversion
2. Emits a clear warning in the report
3. Preserves the original code with a comment

## Blessed Helper Registry

Some tik.maya methods have stable, well-understood semantics that can be safely expanded. These are explicitly registered in the **blessed helper registry**.

### Adding New Helpers

```python
from tik.maya.utils.converter.helpers import get_default_registry

registry = get_default_registry()

registry.register(
    method_name="my_helper",
    type_name="MyType",
    description="What this helper does",
    cmds_template="cmds.someCommand({node}, ...)",
    requires_openmaya=False,
)
```

### Current Blessed Helpers

- `Joint.orient()` → `cmds.joint(edit=True, orientation=...)`
- `Transform.freeze()` → `cmds.makeIdentity(apply=True, ...)`
- `DagNode.select()` → `cmds.select(replace=True)`
- `Node.exists()` → `cmds.objExists()`
- `Node.has_attr()` → `cmds.attributeQuery(exists=True)`

## Conversion Report

Every conversion produces a `ConversionReport` with:

```python
@dataclass
class ConversionReport:
    source_code: str           # Original input
    converted_code: str        # Converted output
    entries: List[ConversionEntry]  # Detailed entries
    
    # Convenience properties:
    rules_applied: List[ConversionEntry]
    helpers_expanded: List[ConversionEntry]
    unsupported_operations: List[ConversionEntry]
    warnings: List[ConversionEntry]
    success_count: int
    failure_count: int
```

## Design for Extensibility

### Adding the Reverse Direction (cmds → tik.maya)

The architecture supports adding a reverse conversion pass:

1. Create a new `rules_reverse.py` with cmds → tik rules
2. Create `engine_reverse.py` or extend `Converter` with a direction parameter
3. The existing parsing, codegen, and report infrastructure can be reused

### Adding New Rules

1. Subclass `ConversionRule` in `rules.py`
2. Implement `matches()` to define the AST pattern
3. Implement `convert()` to produce the cmds code
4. Add to `get_default_rules()` list

```python
class MyNewRule(ConversionRule):
    name = "my_rule"
    category = "my_category"
    description = "What this rule does"
    
    def matches(self, node: ast.AST, context: RuleContext) -> bool:
        # Pattern matching logic
        pass
    
    def convert(self, node: ast.AST, context: RuleContext) -> RuleMatch:
        # Conversion logic
        return RuleMatch(
            rule_name=self.name,
            original_node=node,
            converted_code="cmds.something(...)",
        )
```

## Limitations

### Current Limitations

1. **No CLI**: Must be used programmatically
2. **No batch processing**: Single source string at a time
3. **Variable tracking**: Heuristic-based, may miss some cases
4. **Complex expressions**: Nested operations may not convert fully
5. **Query operations**: cmds.ls(), cmds.listRelatives(), etc. are not supported

### Known Edge Cases

- Multi-line statements may not preserve formatting perfectly
- Some dynamic patterns (e.g., `getattr(node, attr)`) are not recognized
- String node names in variables require manual tracking
- f-strings with complex expressions may not parse correctly

## Next Steps

Logical expansion priorities:

1. **More node types**: Camera, Light, etc.
2. **More helpers**: Common utility methods
3. **Better variable tracking**: Type inference improvements
4. **CLI tool**: For batch processing
5. **Format preservation**: Better comment/whitespace handling
6. **xform support**: Partial support for cmds.xform()


