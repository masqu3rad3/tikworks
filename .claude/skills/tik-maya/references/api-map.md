# tik.maya API map

A curated map of the API surface, organized by layer. The API is pre-1.0 and evolves
without deprecation cycles — treat this as a *map*, and verify exact signatures in the
source file each entry names. If something here no longer matches the source, the source
wins; consider updating this file in the same change.

Package root: `src/python/tik/maya/`. Everything listed in `__init__.py`'s `__all__` is
importable as `tm.<Name>`; unknown attributes fall through to `maya.cmds` via the proxy
(PEP 562 `__getattr__` → `proxy_wrapper`), with wrapper→string input cleaning and
string→wrapper output wrapping for factory commands (`NODE_FACTORIES` in `core/constants.py`).

## core/

### `core/node.py` — `Node`
Base wrapper for any dependency node. Identity is UUID-based: `m_obj` re-resolves from
UUID when the cached `MObject` goes stale, so wrappers survive rename/reparent.

- Properties: `long_name`, `name`, `partial_name` (shortest unique — safe for cmds),
  `uuid`, `type`, `meta` (→ `MetaStore`)
- Methods: `create(cmd, name=, parent=)` (classmethod), `duplicate(**kw)`, `delete()`,
  `delete_history()`, `rename(new)` (undoable, `@protected`), `exists()`,
  `add_attr(name, **kw) -> Plug`, `delete_attr(name)`, `has_attr(name)`
- `node["attr"]` → `Plug`; `str(node)` → short name

### `core/dagnode.py` — `DagNode(Node)`
DAG-capable wrapper, registered for `"dagNode"` (inheritance fallback makes it the
default for any DAG type without a wrapper).

- Properties: `parent` (get/set; setter preserves world placement unless
  `set_parent(relative=True)`), `children`, `dag_path`, `visibility` (alias `v`),
  `bounding_box` (alias `bb`), `color` (index int, RGB tuple, `tik.core.Color`, or None)
- Methods: `select()`, `is_deformable()`, `get_color(as_color=)`, `set_color(c)`

### `core/plug.py` — `Plug`
Attribute handle. Central to everything.

- Properties: `value` (get/set), `attr`, `path`, `node`, `mplug`, `type`, `children`,
  `visible`, `keyable`, `locked`
- Methods: `get(**kw)` / `set(value, **kw)` (kwargs forwarded to get/setAttr),
  `exists()`, `create(attr_type=None, **kw)`, `delete()`, `rename(new)`, `lock()` / `unlock()`,
  `connect(other, force=True)`, `disconnect(other=None)`,
  `get_input(plug=False)`, `list_inputs(plugs=False)`, `list_outputs(plugs=False)`,
  `find_proxy_plugs()`
- Operators: `>>` connect, `<<` reverse connect, `//` disconnect;
  `+ - * / ** %` (and reflected forms) build utility nodes and return the output plug —
  scalar and compound (vector) plugs both handled
- Compound access: `plug["childAttr"]`
- **`create()` is the ONLY attribute creator** — there is no `tm.attribute` module.
  Index a node with a name that does not exist yet, then create it; returns the plug.
  Types: `float` `int` `bool` `enum` `angle` `distance` `time` `string` `matrix`
  (the first seven default to `keyable=True`, unlike `cmds.addAttr`).
  Kwarg aliases: `default` `min` `max` `soft_min` `soft_max` `items` (enum labels);
  `proxy=<Plug or path>` makes a proxy and derives its own type; every other kwarg is
  forwarded to `cmds.addAttr` verbatim, so `create(attributeType="double3")` works.
  ```python
  stretch = ctrl["stretch"].create("float", default=0.0, min=0.0, max=1.0)
  ctrl["space"].create("enum", items=["world", "local"], default=1)
  ctrl["notes"].create("string", default="rev 2")   # default applied post-addAttr
  fk_ctrl["ikFk"].create(proxy=stretch)
  ```
- Lock/hide is plug state, not a helper: `plug.locked = True`, `plug.visible = False`.
  Loop over `tm.TRANSFORM_CHANNELS` / `tm.ALL_CHANNELS` for the channel-box set.

### `core/scene.py` — module-level scene functions
`list_scene_nodes(*a, **kw)` (alias `ls` — wraps every result),
`select_nodes` (alias `select`), `create_node(node_type, name=, parent=)` (alias
`createNode`), `ensure_plugin(name)`, `proxy_wrapper` (the cmds fallthrough).
All exported star into `tm.*`.

### `core/registry.py`
`@register("<mayaNodeType>")` class decorator; `resolve(name_or_wrapper, class_name=None)`
returns the most specific registered wrapper (walks `nodeType(inherited=True)`,
falls back to `Node`); `is_registered(node_type)`.

### `core/meta.py` — `MetaStore`, `find_by_meta`
Typed metadata as hidden string attributes `tikMeta_<key>`, JSON payloads. Survives
rename (attribute-based). Mapping API: `node.meta[key]`, `get`, `keys`, `items`,
`update`, `clear`, `in`, plus `as_dict()` — one listAttr + one getAttr per key,
much cheaper than `meta[key]` in a loop.
`find_by_meta(key, value=<any>, node_type=None)` → wrapped nodes.

### `core/naming.py`
`format_name(*tokens, prefix=, suffix=, side=, sep="_")` — joins non-empty tokens as
`side_prefix_tokens_suffix`; `unique_name(base)` — next free numbered name, respects
existing padding. Mechanics only: conventions (side tokens, suffix vocabulary) belong
to the calling framework, not here.

### `core/decorators.py`
`@undo` (single undo chunk), `@keepselection`, `@protected` (raise if node dead),
`@register`-adjacent class helpers `add_aliases({...})`, `alias("name")`.
Maya-context decorators live HERE, not in tik.trigger.

### `core/apicommon.py`
API-2.0 plumbing: `undocommit(undo=, redo=)` (registers API edits with Maya's undo
queue — required for any MDGModifier/MDagModifier work), `create_node_with_dag_modifier`,
`create_node_with_dg_modifier`, `obj_exists`, `node_type`.

### `core/deformer.py`, `core/shapenode.py`, `core/constants.py`, `core/benchmark.py`
Deformer base plumbing (779 lines — read before touching skinCluster/blendShape);
`ShapeNode` shape-level wrapper; constants incl. `NODE_FACTORIES`; timing helpers.

## types/ — what a node IS (1:1 with Maya node types, no semantics)

- `transform.py` — `Transform(DagNode)`: `create(**kw)`, `shapes`,
  `world_matrix` / `matrix` / `parent_matrix`, `world_translation`, `world_position`
  (get/set), `translate` / `rotate` / `scale` + snake_case per-axis properties
  (`translate_x`, `rotate_y`, `scale_z`, …), `distance_to(other)`,
  `between(a, b, ratio=0.5)` (static), `align_to(target, position=, rotation=)`,
  `aim_at(...)`, `snap_to(...)`, `freeze(...)`, `create_offset_group(name=)`,
  `collect_hierarchy(...)`, `collect_shape_transforms(...)`
- `joint.py` — `Joint(Transform)`: `chain(positions, name_pattern="joint_{index}",
  parent=None, radius=1.0, orient=True)` (classmethod) plus joint-specific properties
- `mesh.py`, `curve.py`, `nurbs.py`, `locator.py`, `light.py`, `camera.py`,
  `ikhandle.py` — per-type wrappers
- `skincluster.py` — `SkinCluster`, `blendshape.py` — `BlendShape` (deformer-backed)

## roles/ — what a node MEANS (wraps a type instance; creates no node kinds)

- `controller.py` — `Controller`: semantic wrapper for controller transforms
  (shape replacement via `utils/control_shapes.py`, tagging, `controller.transform`
  exposes the underlying Transform)

## constructs/ — multi-node patterns (a `create()` classmethod returning a wrapper)

- `matrix_constraint.py` — `MatrixConstraint.create(driver, driven,
  maintain_offset=True, ...)`; handles joint-orient compensation; `.delete()` removes
  the network, leaving the driven node
- `space_switch.py` — `SpaceSwitch.create(node, spaces, ...)`: enum attr re-parenting
  a control between spaces; `add_space`, `remove` / teardown
- `matrix_switch.py`, `ikfk_chain.py`, `ribbon.py`, `measure.py`, `panel.py`
- Pattern for new constructs: dataclass-ish wrapper holding created nodes,
  `create()` builds, `delete()` tears down cleanly.

## utils/

- `control_shapes.py` — controller curve shape library
- `converter/` — bidirectional cmds ↔ tik.maya source converter;
  `EXAMPLES.md` there is the best idiom-by-idiom translation reference

## How tik.maya is consumed (live examples to imitate)

- `src/python/tik/trigger/modules/fkchain/fkchain.py` — a complete, small rig module:
  `tm.Joint.chain`, `Transform.create` + `align_to`, `create_offset_group`,
  `MatrixConstraint.create` in ~30 lines of build code
- `src/python/tik/trigger/modules/arm/arm.py` — the bigger, realistic one
- `src/python/tik/trigger/backends/maya/context.py` — how ctx helpers wrap tik.maya
- `tests/unit/` — `test_apicommon.py`, `test_attribute.py`, etc. show test idioms
  (real Maya standalone, no mocks)
