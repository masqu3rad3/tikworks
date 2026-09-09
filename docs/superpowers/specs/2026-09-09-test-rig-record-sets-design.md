# The Test Rig, Without Containers: a uuid census and a record set

**Date:** 2026-09-09
**Status:** implemented
**Amends:** `2026-09-07-test-rig-sandbox-design.md` — decision 2, sections 3, 4 and 5, and the
`dagContainer` half of section 9. Everything else in that document stands: the second
scaffold, the namespace, teardown following build scope, and scope expansion are all
unchanged. Where the two disagree, this one wins.

---

## 1. Why

A test build made every node it created a member of a Maya `dagContainer`, one per module,
because deleting the container was a complete teardown. It works, and it makes the test rig
unusable.

**Maya's Channel Box shows the owning container in place of any node inside one.** Select a
test-built IK control and the Channel Box lists `translate`, `rotate`, `scale`, `visibility`
— the *container's* transform channels. `ikFk`, `stretch`, `softIk`, `poleFollow`, the whole
authored attribute layout, is absent from the display. The attributes are built: `listAttr`
on the same controller returns exactly what the kinematics action's build returns, node for
node and attribute for attribute. They are simply never shown, and there is nothing the
rigger can do about it.

Nothing switches this off. Measured on Maya 2026, with the controller selected:

| Escape route tried | Result |
|---|---|
| `containerAutoSelectContainer` = 0 | Channel Box still shows the container. |
| `containerCentricSelection` = 0 | Still the container. |
| `containerFlatViewCap` raised past the member count | Still the container. |
| `blackBox` = 0 (the default) | Still the container. |
| Any flag on `cmds.container` | There is none for this. |

The only thing that changes the answer is not being a member: `container -e -rn <node>` and
the Channel Box shows the controller. So a container may not survive the build.

The root made it worse. `|trigger_test:rig_grp` was itself a `dagContainer`, and **parenting a
DAG node under a `dagContainer` makes it a member** — so `preferences_ctrl` and
`visibilities_ctrl` were hijacked too, and would have stayed hijacked even if the per-module
containers were fixed.

## 2. Decision

**Keep the container out of the scene entirely. Record what a module made with a uuid census
and an `objectSet`.**

- `capturing(instance_id, key)` takes `cmds.ls(uuid=True)` before the block and after it. The
  difference is what the module created.
- The difference is added to that module's record — an `objectSet` in the test namespace,
  tagged with `trg_instance`, `trg_name` and `trg_kind` exactly as the container was.
- Teardown is: delete the set, then delete its former members.
- The test root is a plain `transform`. `clear()` already swept by removing the namespace and
  its contents, which is the completest sweep there is, so the root was never load-bearing.

Uuids rather than names because a build renames as it goes. An `objectSet` because it is a DG
node no part of the Maya UI treats specially: it has no DAG presence, no channels, and it
does not touch selection.

## 3. Why not dissolve the container at the end

The tempting middle road — keep the container for the *collecting*, then hand its membership
to a set and `container -e -removeContainer` — was implemented, measured and abandoned. Two
further container habits kill it:

| Measured | Consequence |
|---|---|
| A `dagContainer` **adopts an unparented DAG node** created while it is current. | The container is not a neutral observer; it changes the hierarchy the module builds. |
| `container -e -removeContainer` **deletes any member with no connections**. | A lone `multMatrix` a module has not wired up yet is destroyed on the way out. A build path cannot have that. |

The census has neither habit. It observes and changes nothing.

## 4. What the amended sections say now

**Section 3's probe table** stands as a record of what containers do; it is no longer a record
of what the test rig does. Three rows are now reasons *against*, not for: the Channel Box
substitution (new, above), the DAG-child adoption, and `-removeContainer`'s deletion of
unconnected members.

**Section 4's scaffold** loses the `dagContainer` root and the per-module `*_con` transforms:

```
|trigger_test:rig_grp                  transform, trg_kind = rig_root
├── trigger_test:trigger_grp           trg_kind = rig_trigger
│   ├── trigger_test:preferences_ctrl  controller, trg_kind = preferences
│   ├── trigger_test:visibilities_ctrl controller, trg_kind = visibilities
│   ├── trigger_test:body_grp …        the module's four groups, as today
│   └── trigger_test:L_arm_grp …
└── trigger_test:geo_grp               trg_kind = rig_geo

trigger_test:body_set                  objectSet, trg_instance = <uuid>
trigger_test:L_arm_set                 objectSet, trg_instance = <uuid>
```

The records are DG nodes, so they sit outside the hierarchy rather than inside it. That is the
point: nothing in the rig's own tree is holding the bookkeeping.

**Section 5's API** becomes:

```python
def module_record(instance_id: str, key: str)       # the objectSet, created if absent
def find_module_record(instance_id: str)            # by trg_instance tag
def members(record) -> list[str]                    # long paths, gone nodes dropped
def capturing(instance_id, key)                     # context manager
def teardown(instance_ids, scaffold) -> list[str]   # records + their enums
def clear() -> bool                                 # remove the namespace wholesale
```

`Builder._module_scope` wraps `capturing` around **both** `_build_one` and that module's
`_connect_one` and space wiring, exactly as it wrapped the container, so an attach constraint
still belongs to the consumer and dies with it. Capturing a module twice adds to the one
record. A build that raises still leaves its record populated, so the next Build can tear the
half-built module down.

The tier enum on `visibilities_ctrl` is removed by `teardown` as before, keyed off the
`trg_name` tag rather than the node's name.

## 5. What the census sees that a container did not

A container recorded what was *made inside it*. A census records what *appeared*, which is a
superset, and the difference has one member that matters: **Maya's IK solvers**.

`cmds.ikHandle` looks a solver up by name and makes one only if it is absent. So the first
module in the scene to build IK causes four solver nodes to appear, every `ikHandle` in the
scene then points at the same ones, and the census — correctly, literally — sees them appear
during that module's build. Recording them there means tearing that module down deletes the
solvers, and Maya takes every other module's `ikHandle` with them. Measured: two arms built,
rebuild the right one, and the left arm's `ikHandle` is gone.

The 2026-09-07 spec noted this class in passing on the other side of the ledger — "`ikSystem`
and the IK solvers are scene-global, are not captured, and are untouched" — as something the
container got right for free. The census has to be told:

```python
SHARED_TYPES = ("ikSolver",)   # matched by inheritance: RP, SC, spline, hik
```

`_module_owned` drops those from the difference before it reaches the record. `ikSystem` needs
no entry — it lives at the scene root, outside the test namespace, and never appears.

This is the one place the census is weaker than a container, and it is a named list rather
than a mechanism, so a future scene-wide singleton that a module wakes up will need adding to
it. The two tests in section 7 fail loudly if it is wrong.

## 6. Two Maya details the implementation rests on

- **Names must be rooted.** Capture runs *inside* the `trigger_test:` namespace, where Maya
  reads a bare `trigger_test:foo` as a child of the current namespace — it looks for
  `trigger_test:trigger_test:foo` and reports the node as missing. Every name `sandbox` hands
  to `cmds` is prefixed with `:` unless it already starts with `|` or `:`, and `cmds.ls`
  hands a DG node back bare, so the rooting is re-applied after every `ls`.
- **Maya deletes a set that its members' removal empties.** So `teardown` deletes the record
  *first* and its members second; the other order leaves nothing to delete and a `None` name.
  Members go one at a time behind an `objExists` check, because deleting a parent takes its
  children and handing Maya a path that went with them is an error.

## 7. Tests

`tests/integration/trigger/test_test_rig_trigger.py`:

- a test-built controller — module and scaffold alike — belongs to no container, and a test
  build leaves no container in the scene at all;
- the census records DAG and DG nodes, records an unconnected node, adds to one record when a
  module is captured twice, and records what a build made before it raised;
- teardown removes one module and nothing else, and drops its tier enum;
- no record holds an `ikSolver`, and rebuilding one arm leaves the other arm's IK
  standing — both fail without `SHARED_TYPES`;
- the root is a plain transform;
- and the behaviour the 2026-09-07 spec bought is unchanged: three scoped builds leave one
  copy, Build All wipes first, a scoped build pulls in an unbuilt producer, leaves a sibling
  alone, and rebuilds a built consumer.
