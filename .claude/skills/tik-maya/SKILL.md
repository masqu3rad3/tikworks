---
name: tik-maya
description: TikWorks Maya coding via the tik.maya wrapper. Use this skill EVERY time code that interacts with Maya is written, edited, or reviewed in this repo — rig builds, trigger modules and actions, scene utilities, deformer tools, tests that touch the scene, or one-off snippets sent to a running Maya session. Trigger it whenever the task mentions Maya, cmds, OpenMaya, joints, controllers, rigging, skinning, deformers, guides, or scene nodes, even if tik.maya is not named. It teaches the tik.maya idioms, forbids raw maya.cmds/OpenMaya/pymel in tool code, and covers when and how to extend tik.maya itself.
---

# Writing Maya code in TikWorks

TikWorks has its own Maya API wrapper: **tik.maya** (`src/python/tik/maya/`).
All Maya interaction in tools, tests, and scripts goes through it.

## The rules

1. **Never call `maya.cmds` or `maya.api.OpenMaya` directly** in anything outside
   `src/python/tik/maya/` itself (module/action bodies in trigger included).
   Raw calls are permitted only *inside* tik.maya, where they implement the wrapper.
2. **Never use third-party wrappers** — no pymel, no cmdx, no other API layers.
3. **When tik.maya lacks a capability, extend tik.maya** — don't work around it
   (see "When tik.maya falls short" below).

Why this matters: tik.maya wrappers track nodes by **UUID**, so they survive renames
and reparenting where name strings silently go stale; scene-modifying operations are
wired for **undo** (`undocommit` / undo chunks); and every Maya quirk fixed inside the
wrapper is fixed for every tool at once. A raw `cmds` call in a tool forfeits all three.

## Core idioms

Import convention (used everywhere in the repo):

```python
import tik.maya as tm
```

**Wrap an existing node** — `resolve` returns the most specific registered wrapper
(Joint, Mesh, Transform, …) and accepts names or existing wrappers:

```python
node = tm.resolve("L_arm01_jnt")     # -> Joint instance
```

**Create nodes** — classmethods on the type, or `tm.create_node` for raw node types:

```python
grp = tm.Transform.create(name="rig_grp", parent=other)   # parent: wrapper, str, or None
joints = tm.Joint.chain(positions, name_pattern="spine_{index}", parent=grp)
```

**Attributes are Plugs** — index the node with the attribute name:

```python
node["translateX"].value          # read (also .get() for kwargs like time=)
node["translateX"].value = 5.0    # write (also .set(v) for kwargs)
node.translate_x = 5.0            # Transform exposes snake_case TRS properties
node["v"].locked = True           # plugs carry .locked / .keyable / .visible
node["v"].visible = False         # hide from the channel box
```

**New attributes come from the same handle** — `create()` is the only creator; there
are no free `add_*` helpers. It returns the plug and defaults to `keyable=True`:

```python
stretch = ctrl["stretch"].create("float", default=0.0, min=0.0, max=1.0)
ctrl["space"].create("enum", items=["world", "local"], default=1)
ctrl["notes"].create("string", default="rev 2")
fk_ctrl["ikFk"].create(proxy=stretch)          # a proxy of another plug
ctrl["custom"].create(attributeType="double3")  # raw addAttr flags pass through
```

Types: `float` `int` `bool` `enum` `angle` `distance` `time` `string` `matrix`.
Aliases: `default` `min` `max` `soft_min` `soft_max` `items`.

**Connections are operators**:

```python
a["worldMatrix"] >> b["offsetParentMatrix"]   # connect a -> b
b["input"] << a["output"]                     # connect (reversed reading)
a["tx"] // b["tx"]                            # disconnect
```

**Plug arithmetic builds the node graph** — `+ - * / ** %` on plugs create the
utility nodes for you and return the output plug:

```python
(driver["tx"] * 0.5 + offset["tx"]) >> driven["ty"]
```

**Typed metadata** lives on nodes as hidden attributes (`tikMeta_*`), JSON-encoded:

```python
node.meta["kind"] = "guide"                 # any JSON-serializable value
node.meta.as_dict()                         # bulk read (cheap); meta[k] in a loop is not
tm.find_by_meta("kind", "guide", node_type="joint")
```

**Constructs** orchestrate multi-node setups — reach for them before hand-wiring:
`tm.MatrixConstraint.create(driver, driven, maintain_offset=True)`,
`tm.SpaceSwitch.create(...)`, `tm.IkFkChain`, `tm.Ribbon`, `tm.MatrixSwitch`, `tm.Measure`.

**Helpers**: `tm.naming` (`format_name`, `unique_name` — mechanics only; conventions
belong to the caller), `tm.TRANSFORM_CHANNELS` / `tm.ALL_CHANNELS`,
decorators `@undo` / `@keepselection` from `tik.maya.core.decorators`.

**The cmds proxy escape hatch** — `tm.<anything>` that isn't a wrapper falls through to
`maya.cmds` with wrappers auto-converted to names in, and factory results wrapped out:

```python
tm.polySphere(radius=2)       # legal, returns wrapped nodes
```

Use it for commands with no wrapper yet. If you reach for the same proxy call more than
once or twice, that's the signal to promote it into a real wrapper method instead.

## Identity gotchas

- Hold **wrapper objects**, not name strings. A stored `long_name` breaks on rename;
  the wrapper doesn't.
- Wrappers auto-stringify when passed to tik.maya functions and the cmds proxy — no
  manual `str()` needed.
- A wrapped node can die (deleted, new scene). `node.exists()` checks; most mutating
  methods raise `RuntimeError` on a dead node via `@protected`.

## When tik.maya falls short

The wrapper is **editable and currently has no backward-compatibility guarantees**
(this will be announced when it changes). Improving it is part of the job, not a detour.

1. **First, verify the gap is real.** Read `references/api-map.md`, then grep the source —
   the capability often exists under a different name
   (`grep -rn "def " src/python/tik/maya/ | grep -i <keyword>`).
2. **One-off, obscure command?** Use the cmds proxy (`tm.<command>`) inline.
3. **Anything reusable → implement it in tik.maya.** Signature improvements to existing
   methods are welcome too — update all callers and tests in the same change.

Where new code goes (never conflate these layers):

- **Type** (`types/`) — what a node *is*; maps 1:1 to a Maya node type; registered with
  `@register("<mayaNodeType>")`; never encodes semantic meaning.
- **Role** (`roles/`) — what a node *means* (Controller…); wraps an existing type
  instance; never creates new node kinds.
- **Construct** (`constructs/`) — orchestrates several nodes/roles into a pattern;
  a `create()` classmethod that returns a wrapper holding the created network.
- **Core** (`core/`) — Node/DagNode/Plug plumbing, registry, meta, naming, decorators.

House style inside tik.maya (full detail: `references/api-map.md` and `AI/coding_rules.md`):
properties for state (noun), methods for actions (verb), **no `get_`/`set_` prefixes**;
every scene-modifying operation must be undoable (`apicommon.undocommit` for API-level
edits, `cmds.undoInfo` chunks for cmds sequences); no single-letter names; type hints
and PEP 257 docstrings on public APIs; new behavior needs a pytest under `tests/unit/`.

## Verifying your code

Tests run under Maya standalone via mayapy — plain `python` cannot import `maya`:

```powershell
$env:PYTHONPATH="src/python"; mayapy -m pytest tests/unit/test_<module>.py -q
```

(`make tests-unit` / `make tests-integration` wrap the same thing.) Prefer exercising
real Maya behavior over mocks. For interactive checks, a running Maya session may be
reachable through the `adsk` MCP tools (`maya_execute_python_code`) — remember
`src/python` must be on `sys.path` there too.

## References

- `references/api-map.md` — curated map of the whole API surface, per module. Read it
  before concluding something doesn't exist.
- `src/python/tik/maya/utils/converter/EXAMPLES.md` — side-by-side cmds ↔ tik.maya
  translations; the fastest way to "lift" cmds-style thinking into tik.maya.
- `AI/coding_rules.md` — repo-wide coding standards this skill summarizes.
