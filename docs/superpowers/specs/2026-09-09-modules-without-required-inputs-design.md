# Modules Build Without Inputs: attachment is a connection, not a precondition

**Date:** 2026-09-09
**Status:** designed
**Amends:** `2026-08-29-trigger-ui-v3-and-io-graph-design.md` — the `Input` declaration and the
required/optional distinction. `2026-09-07-test-rig-sandbox-design.md` — the upstream half of
scope expansion, which existed only to work around the rule this document removes. Everything
else in both stands.

---

## 1. Why

Every module this repo ships except `base` declares at least one input, and every one of those
inputs is required. Build an arm with nothing wired into `root` and the builder refuses:

```
AttachError: L_arm.root: required input has no source.
```

That refusal has no mechanism behind it. A socket is created in `socket_grp` for **every
declared input whether or not it is wired** (`maya/rig.py:281`) — declaring the input is what
makes it — and modules build against the socket, never against the source. Unwired, the socket
sits at its matched guide, unconstrained, and the module is complete: the arm's collar hangs
off a static frame, a twist between two static sockets reads zero, a ribbon builds straight.
`_bind_parent_for` already returns `None` for an unconnected module and its bind joints hang
from its own `bind_grp` (`maya/build.py:377`).

So the arm that cannot be built would have built correctly. The only thing stopping it is a
policy at `maya/build.py:405`, and a second rule grew on top of it: scope expansion pulls
unbuilt *producers* into a scoped test build, and its docstring says why — "so a first build
of an arm on its own still works instead of failing on a required input"
(`core/build_scope.py:58`).

The policy is also wrong about rigs. A base is a convention, not a requirement. A rig may want
several bases for different purposes, or none at all, and the rigger who assembles one is not
making a mistake.

## 2. Decision

**Anything buildable in the Guide Designer is a valid build.**

That is the governing rule, and it is what the rest of this document serves. The Designer and
the pipeline must agree on what is legal — a module the rigger can lay down, draw guides for
and press Build on cannot be a module the pipeline refuses.

Concretely: **attachment is a connection, not a precondition.** An input describes a socket
another module *may* drive. Leaving it undriven is a legal, silent, ordinary state.

`Input.optional: bool = False` becomes `Input.required: bool = False`:

```python
@dataclass(frozen=True)
class Input:
    name: str
    kind: str = "transform"
    primary: bool = False
    required: bool = False   # was: optional: bool = False
    help: str = ""
```

The flag is inverted rather than deleted because a module may one day be unable to build
unwired — a module whose whole job is to read a frame it does not own. Nothing in this repo
declares `required=True`, and the ground rules test in section 8 holds that true. The day a
module needs it, it says so in one word instead of costing a contract change.

`primary` is untouched and keeps both its jobs: which input the tree view draws as parenting,
and which producer supplies the bind parent.

## 3. What an unwired module builds

Nothing here is new work. It is what the machinery already does once the refusal is gone, and
it is written down so the behaviour is a decision rather than an accident.

| | Wired | Unwired |
|---|---|---|
| Socket | created, constrained to the source | created, free-standing at its matched guide |
| Bind joints | hang from the producer's output | hang from the module's own `bind_grp` |
| Controls, outputs, attributes | as declared | as declared, unchanged |
| Module behaviour | follows its producer | works in place |

A module built alone is a rig root of its own. That is the point: an arm on a table, testable,
riggable and animatable, with no body under it.

## 4. What is still an error

A source that is **named but wrong** still fails the build, and both existing checks stay
exactly as they are (`maya/build.py:496-522`):

- `body.nope` — the producer was built, but has no such output. `AttachError`.
- `some_jnt` — neither a built module output nor an existing scene node. `AttachError`.

Silence is for "the producer is not here". A typo is not silence, and treating it as one would
hide the failure the rigger most wants to see.

**Two things go quiet, not one.** An absent source is the obvious one. The second was found
while implementing section 6 and is the reason a scoped build works at all: a source naming a
module the **document has but this pass did not build**. Select `L_arm` alone and its `root`
is still wired to `body.root` — the rigger meant that, and the body is simply not in this
pass. That is neither an unwired input nor a typo, so `_out_of_scope` (`maya/build.py`) reads
it as a third state and the socket stands free exactly as if nothing were wired. It attaches
on the pass that does build the body.

The check is `key not in by_key and key in self._keys_to_ids` — a *document* key this build
did not build — and it deliberately does not apply to a producer an **earlier pass** built,
which `_earlier_pass_output` finds in the scene and attaches normally. It is not gated on test
builds: a `kinematics` action naming a subset is the same situation by design, since a rig may
be split across several passes.

The anim-space warning at `maya/build.py:446` is also unchanged. A space row names a label the
rigger explicitly authored, so a missing source there is a mistake, not a default.

## 5. Nothing reports an unwired input

No log, no chip, no note in the build report.

The Designer already shows an empty connection field and the graph draws no edge — that is the
signal, it is precise, and it is visible *before* the build rather than after. A build-time
note would fire on every deliberately standalone module, which is now the normal case, and a
warning that fires on the normal case is trained away within a day.

## 6. Build scope loses its upstream half

`expand_build_scope` (`core/build_scope.py:45`) keeps its downstream half and drops its
upstream one.

**Downstream, unchanged:** a consumer that is *already built* is rebuilt, so the test rig never
holds an attach pointing at deleted nodes.

**Upstream, removed:** an unbuilt producer no longer joins the scope. Select `L_arm`, press
Build, and exactly `L_arm` is built — its collar socket free-standing at the collar guide. This
matches the `kinematics` rule that a pass builds only the modules it names, and it makes the
tweak-and-rebuild loop cheaper. Build the body afterwards and the downstream half rebuilds the
already-built arm, which attaches then.

## 7. The Designer and the manifest

- The connection field's placeholder inverts: `"module.output or scene node"` gains
  `"  (required)"` on the rare required input instead of `"  (optional)"` on the common
  unrequired one (`ui/designer/widgets.py:127`).
- `ribbon.reference` and `twist.reference` drop `optional=True`, which now says nothing.
- The inputs derived from anim-space rows (`core/module.py:145-151`) drop it for the same
  reason — one per `<control>_<label>` row, already unrequired, now unremarkably so.
  `tests/unit/test_core_trigger.py:304` asserts `all(item.optional for item in derived)`;
  with the default inverted there is nothing left to assert there, so the case keeps only
  its name/kind checks.
- `Base`'s docstring — "Root of a rig. Everything else attaches to its `root` plug" — becomes
  a statement of convention. Nothing in the codebase privileges `base`: it is an ordinary
  module with `inputs = ()`, there is no singleton check, and several bases or none already
  work structurally.

## 8. Enforcement

`tests/integration/trigger/test_module_ground_rules.py` wires every required input before
building (`_built_with`, lines 68-80). That wiring becomes conditional on `required`, and a
companion case is added:

> **Every module this repo ships builds standalone** — no parent, no inputs set — and produces
> its declared controls and outputs.

Parametrised over the same shipping-module list the existing ground rules use. This is what
turns "no module needs an input today" from a claim into something the suite holds, and it is
the executable form of the rule in section 2.

Tests that assert the old refusal lose those assertions:
`tests/integration/trigger/test_builder_trigger.py:198-224` (the `"required input"` branch) and
`tests/unit/test_connections_trigger.py:119`. The wrong-source branches in the same tests stay
— they cover section 4.

## 9. Compatibility

No schema bump. The `.tr` stores *connections*, never the declarations, and `optional` is not
serialised anywhere — it appears only in `core/manifest.py`, `core/module.py`, `maya/build.py`,
`ui/designer/widgets.py` and the two module manifests. Every existing session opens and builds
unchanged, and a session that built before builds identically now: this change only widens what
is accepted.

## 10. What this does not do

- It does not remove `primary`, or change how a guide parent pre-fills the primary input.
- It does not change the bind hierarchy rule. One bind hierarchy per rig, built in final
  position, never reparented — a standalone module simply roots its own.
- It does not add a way to mark a module "standalone" or "root". A module with no wired inputs
  is not a different kind of module.
- It does not introduce a required input anywhere. `required=True` is a capability this pass
  leaves unused on purpose.
