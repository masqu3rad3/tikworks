# The Test Rig: Guide Designer builds in their own container

**Date:** 2026-09-07
**Status:** approved, not yet implemented
**Amends:** `2026-09-05-rig-scaffold-and-master-controls-design.md` (decision 1 and section 3)
and `2026-09-05-draw-and-sync-separation-design.md` (section 7, for the Designer's build only
— a pipeline build is unchanged). Where this document and those disagree, this one wins;
everything it does not mention is unchanged.

---

## 1. Why

The Guide Designer's **Build** and **Build All** exist so a rigger can mock something up:
change a setting, change a connection, look at the result, change it again. Today
`GuideScene.test_build` calls `Builder().build(...)`, which calls `ensure_rig()`, which is
hard-coded to the one real scaffold at `|rig_grp`. Two consequences follow.

**It crosses paths with the real rig.** A mock-up hangs its limb groups in the real
`trigger_grp` and lands its per-module tier enums on the real `visibilities_ctrl`. There is
no way to look at a scene and say which parts are the rig and which parts are somebody
trying an idea.

**It is not repeatable.** Nothing tears down what a previous test build made, so pressing
Build twice on the same module stacks a second copy of it on top of the first. The rigger's
loop — the whole point of the feature — is the one thing it does badly.

The fix is a second, throwaway rig that the Designer builds into, and a build command that
removes what it is about to rebuild.

## 2. Decisions

1. **A test build goes into its own rig**, addressed by its own fixed names, never into
   `rig_grp`. The real build path is unchanged.
2. **Each module in the test rig gets a Maya `dagContainer`**, and teardown is deleting it.
   A container captures every node created while it is current — DAG *and* DG — so the
   utility nodes that a hierarchy delete would strand go with it.
3. **No namespace.** See section 8; it costs a real problem in the build path and, given
   containers, buys nothing back.
4. **Teardown follows build scope.** `Build All` deletes the whole test rig; a scoped build
   deletes only the modules it is about to rebuild.
5. **A scoped build expands downstream, and upstream only to fill gaps.** Consumers of a
   rebuilt module are torn down and rebuilt, so the test rig never holds a dangling attach.
   Producers are pulled in only when they are not already built.
6. **A pipeline run does not inherit a test rig.** `Runner.run` resets the scene before its
   first step, so `Build` and `Build & Publish` always start clean and no extra code is
   needed. The one gap is `Runner.run(only=...)` — running a single action deliberately skips
   the reset (`maya/runner.py:164`), and a leftover test rig would sit in the scene beside
   the real one. It cannot corrupt the real rig (separate root, and section 7 scopes the
   output lookups), so the remedy is **Clear Test Rig**, not implicit deletion: a build
   command that silently removes something the rigger built is worse than one that leaves it.

## 3. What the probe established

These decisions rest on measured behaviour, not on documentation. Maya 2026, `mayapy`
standalone and an interactive session:

| Question | Result |
|---|---|
| Does `container -current` capture nodes made by `MDagModifier` / `MDGModifier`? | **Yes** — `cmds`, DAG-modifier and DG-modifier nodes all became members. This is the hinge: tik.maya creates everything through `create_node_with_dag_modifier` / `..._dg_modifier` (`tik/maya/core/apicommon.py:77`, `:103`). |
| Does deleting a container delete its members? | **Yes**, DG nodes included. |
| A node created under a *non-member* parent — the bind-joint case? | Member of its own container. Deleting takes the joint and leaves the host group standing. |
| Is a container a group? | `container -type dagContainer` **is a transform**: it parents DAG children and holds DG nodes. There is no extra nesting level to invent. |
| Does deleting the root container cascade into nested module containers? | **Yes** — 17 nodes, one call, nothing left. |
| Nesting, tagging, discovery, undo | Nested containers delete independently; a container takes a `trg_instance` meta tag; `ls(containers=True)` finds them; one `cmds.undo()` reverts a whole build. |
| `blackBox` default | `False`. Contents stay open and editable. |
| Leftovers after teardown | None. `ikSystem` and the IK solvers are scene-global, are not captured, and are untouched. |
| Does tik.maya need to learn about containers? | **No.** `dagContainer` inherits `transform`, so `resolve_node_class`'s inheritance fallback (`tik/maya/core/registry.py:73`) already returns a `Transform`. Plugs, `meta` and `long_name` all work on it unchanged. |

Two side-effects worth recording:

- **`ls(type="container")` does not find a `dagContainer`.** Use `ls(type="dagContainer")` or
  `ls(containers=True)`.
- **Deleting a producer's container also took the consumer's attach `multMatrix`** (the
  socket transform survived) — Maya cascading through the orphaned utility chain. Harmless
  here, and consistent with decision 5.

## 4. The test scaffold

```
|test_rig_grp                    dagContainer, trg_kind = rig_root
├── test_trigger_grp             trg_kind = rig_trigger
│   ├── test_preferences_ctrl    controller, trg_kind = preferences
│   ├── test_visibilities_ctrl   controller, trg_kind = visibilities
│   ├── body_con                 dagContainer, trg_instance = <uuid>
│   │   └── body_grp …           the module's four groups, as today
│   └── L_arm_con                dagContainer, trg_instance = <uuid>
└── test_geo_grp                 trg_kind = rig_geo
```

`scaffold.py` keeps one private `_ensure(names, events)` and grows a second public entry:

```python
def ensure_rig(events=None) -> RigScaffold:        # unchanged behaviour
def ensure_test_rig(events=None) -> RigScaffold:   # new
def find_test_rig() -> Optional[RigScaffold]:      # new, creates nothing
```

The two differ in the name table and in the root being a `dagContainer`. `RigScaffold` gains
`is_test: bool = False`.

`wire_preferences` and `wire_tiers` (`maya/build.py`) read `rig.scaffold` and need no change:
a test build lands its per-module tier enums on `test_visibilities_ctrl` and its visibility
connections on `test_preferences_ctrl`, never on the real controls.

This amends decision 1 of the scaffold spec, which now reads: **one *real* rig per scene, and
it has no name; plus at most one test rig.** Both are addressed by fixed names and confirmed
by tags. The test rig is created lazily, by the first test build, and is not in the session
document.

## 5. Module containers

A new `tik/trigger/maya/sandbox.py` owns the container machinery. It is named `sandbox` rather
than `test_rig` so that no file under `src/` carries a `test_` prefix.

```python
TEST_ROOT = "test_rig_grp"

def module_container(instance_id: str, key: str, parent) -> tm.Transform
def find_module_container(instance_id: str)                 # by trg_instance tag
def current(container)                                      # context manager
def teardown(instance_ids, scaffold) -> list[str]           # containers + their enums
def clear() -> bool                                         # delete TEST_ROOT wholesale
```

`current()` sets the container current and clears it in a `finally`, so the flag cannot leak
out of a failed build.

`Builder` sets a module's container current around **both** `_build_one` and that module's
`_connect_one` and space wiring. Attach constraints therefore belong to the *consumer* and
die with it — which is what makes decision 5 sound. Module code and tik.maya are untouched.

Teardown of one module is `cmds.delete(container)` plus removing that module's enum from
`test_visibilities_ctrl` (`tier_attr_name(key)`), which is an attribute on the scaffold
control rather than a node in the container.

## 6. Scope

Scope expansion is pure Python over the guide document's connection graph and lives in
`tik/trigger/core/` — no Maya, so it is unit-testable.

```python
def expand_build_scope(entries, ids, already_built) -> list[str]
```

`already_built` is the set of instance ids that currently have a module container in the test
rig — `sandbox` derives it by scanning `trg_instance` tags on the containers under
`test_rig_grp`, so it is a fact about the scene, never a cached list.

- **Downstream, always.** Every transitive consumer of a module in `ids` joins the scope.
  They are torn down and rebuilt.
- **Upstream, only to fill gaps.** A transitive producer joins the scope only if it is not in
  `already_built`. The common loop — body built, tweak the arm, rebuild the arm — stays fast,
  and a first build of an arm on its own works instead of failing on a required input.
- Space connections are excluded from the graph, exactly as in `Builder.build`'s
  `structural_inputs`: they are legitimately mutually referential.

`Build All` does not expand: it clears the whole test rig and builds everything.

## 7. Scoping the output lookups

`find_output` (`guides/nodes.py:45`) scans every tagged node in the scene. Once a real rig and
a test rig are both built, the same `trg_instance` answers twice and a cross-pass connection
can resolve to the wrong rig.

It gains an `under: Optional[str] = None` parameter — a long-path prefix. Every output is a
bind joint, so the test is exact and cheap. `Builder` passes the root it is building into,
whichever that is, which closes the same ambiguity for the real build.

## 8. Why there is no namespace

A `trigger_test:` namespace was the obvious first answer and is the wrong one.

`cmds.ls` with a wildcard **does not cross namespace boundaries**:

```
ls("*.trg_kind")                 → ['root_tagged']                      ← namespaced node missed
ls("*.trg_kind", recursive=True) → ['nstest:ns_tagged', 'root_tagged']
```

`find_instances` and `find_output` both scan with exactly that pattern (`guides/nodes.py:56`,
`:259`). Put the test rig in a namespace and `find_output` stops seeing its outputs, so
`_earlier_pass_output` returns `None` and every cross-module connection inside the test rig
fails with an `AttachError`. The repair would be `recursive=True` in shared build-path code —
which then makes those scans see *everything everywhere*, reintroducing the ambiguity of
section 7 in the one place the real build depends on.

Against that, the namespace's remaining jobs are all covered:

| Job | Covered by |
|---|---|
| Wholesale teardown | Deleting the root container (measured: 17 nodes, one call) |
| Short-name collisions | DAG nodes under different parents may share a short name; DG nodes auto-uniquify harmlessly. The one genuine clash, the scaffold root, is solved by the `test_` names of section 4 |
| "This is throwaway" | The container node and its `trg_kind` tag say it more plainly than a prefix |

## 9. Entry points

`GuideScene.test_build` (`guides/scene.py:824`) keeps its signature and its Sync → Draw →
build order, and passes the test-rig flag to `Builder`. The Designer's **Build** (module
context menu), **Build All** (action bar) and the two Guides-menu items keep their labels and
behaviour.

One addition: **Guides > Clear Test Rig**, calling `sandbox.clear()`. It is a no-op with a
status message when no test rig exists.

## 10. Tests

**Unit, no Maya** — `tests/unit/test_build_scope_trigger.py`: downstream cascade, upstream
gap-filling, both together, a module with no connections, and that space connections do not
pull a module into scope.

**Integration, Maya** — `tests/integration/trigger/test_test_rig_trigger.py`:

- a test build creates `test_rig_grp` and leaves `rig_grp` absent;
- with a real rig already built, a test build does not add, remove or alter one node under
  `rig_grp`, and adds no enum to the real `visibilities_ctrl`;
- a module's `dagContainer` holds its DG utility nodes as well as its DAG hierarchy;
- building the same selection three times in a row succeeds and leaves exactly one copy;
- tearing down one module leaves its siblings' nodes untouched and strands nothing;
- `Build All` on an existing test rig wipes it first;
- a scoped build of a producer rebuilds its consumers, and their attach constraints resolve;
- a scoped build of a consumer whose producer is unbuilt pulls the producer in;
- guides survive a test build (`afterlife="keep"`, unchanged);
- `sandbox.current()` leaves no current container behind when the build raises.

## 11. What does not change

The real build path and `rig_grp`; module code; tik.maya; the pipeline runner and actions;
the `.tr` schema; the guide document; Draw and Sync; and the guides' afterlife on a test
build, which stays `keep`.
