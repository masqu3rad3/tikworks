tik.trigger
===========

Modular rigging built on ``tik.maya``. **The session is the rig**: a ``.tr``
file is an ordered, nested list of actions; Build resets the scene and runs
them. Guides are an asset (``.trg``) authored in the Guide Designer and consumed
by the Kinematics action.

Concepts
--------

* **Session** (``.tr``, schema 4) — nested actions; every input is a file path
  or a value stored in the action. Old flat ``.tr`` files convert on load.
* **Action** — typed fields + ``run(ctx)`` (+ optional ``validate``,
  ``save_from_scene``); registered with a category for the shelf/palette.
* **Reference** — an action that runs another session inline; ticking or
  editing its rows stores *overrides* in the referencing session only.
* **Guides** — old-format ``.trg`` joint lists; ``Guides`` authors them in the
  live scene (add/mirror/reparent/test build/export/import).
* **Module** — manifest (``Guides(...)`` roles, ``inputs`` / ``outputs``, typed
  fields, ``legacy_types`` for old ``.trg`` names) + ``draw_guides(ctx)`` /
  ``build(ctx)``. Modules register built nodes with ``ctx.output(name, node)``
  and the node an input drives with ``ctx.attach(input, node)``.
* **Connections** — ``input <- source`` data in the ``.trg``
  (``{"input": "L_arm.root", "source": "body.root"}``); a source is another
  module's output or any scene node name (must exist at build time). Build
  everything first, then connect. The Guide Designer edits them in a tree
  (primary input = parenting) and a node graph side by side.

TD API
------

.. code-block:: python

   from tik import trigger

   rig = trigger.Session.open("hero_muscle.tr", backend=trigger.maya_backend())
   rig.add("import_asset", "import_model", file_path="geo/hero_muscle_v02.ma")
   base = rig.add("reference", "baseRig", file="rigs/baseRig.tr")
   base["scripts/head_rotation"].enabled = False          # override
   base["kinematics"].guides_file = "guides/hero_muscle.trg"
   rig.add("script", "fix", parent=rig["import_model"], code="...")
   rig.build()                    # reset scene, run everything
   rig.build(until="kinematics")
   rig.run("fix")                 # single step, no reset
   rig.save(increment=True)

   guides = trigger.Guides()      # the live scene
   body = guides.add("base", name="body")
   arm = guides.add("arm", side="L", parent=body, ribbon_joints=6)
   guides.mirror(arm)                              # -> R_arm, inputs mirrored
   guides.connect("L_arm.root", "body.root")       # explicit wiring
   guides.connect("tail.space", "some_jnt")        # any scene node
   guides.test_build(body, arm)
   guides.export("guides/hero_muscle.trg")

UI
--

.. code-block:: python

   import tik.trigger.ui
   tik.trigger.ui.show()

Dockable tool windows (File / Edit / Session / Tools / Help, status bar).
Tabs are open sessions. Add actions from the shelf pane (click = after
selection, drag = anywhere, drop on a row = nest) or press **Tab** for the
search palette (Enter: sibling, Shift+Enter: child). Referenced rows render
inline, dimmed, with checkboxes; edits become overrides. Versioned file fields
are Nuke-style: green = latest, amber = older, Alt+Up / Alt+Down while hovering
steps versions. The Guide Designer (Tools menu or the ✎ next to a guides file)
authors ``.trg`` files: tree and node graph over the same connections, Inputs
group in the properties, two-way scene binding, debounced scene sync.
Connections are data only — guide joints are never parented into each other
and the designer never touches the Maya selection (use *Select guides*).
Graph: Alt+MMB pans, Alt+RMB zooms around the press point, wheel zooms under
the pointer, F fits, View ▸ Grid / Snap to Grid, View ▸ Auto Layout (one
undo step). Drag output → input to connect, drag a plugged input away to
unplug, Delete disconnects selected wires, **Ctrl+drag slices** every wire
the line crosses, node menu → *Sever all connections*. Nodes collapse like
Maya's node editor: click the ≡ glyph or press 1 / 2 / 3 (header only /
connected plugs / everything). **Scene Nodes** (shelf / Tab) is a group of
arbitrary Maya nodes exposed as outputs — one group with ten outputs or ten
groups with one, your call; rows are picked from the Maya selection.
Right-click an input field for a menu of every other module → its outputs,
plus the scene nodes by group. Right-click a module (tree or graph): Select
root, Select all guides, Mirror, Build, Sever, Rename, Delete. Selecting
several modules of one type edits them together (the panel says so); mixed
types show nothing. Module names are unique per side (``arm``, ``arm1``…)
and renaming onto an existing name is refused. Modules may declare any
number of inputs and outputs (or none); the "primary" input only drives the
tree layout. *Build selected* / *Build all* test-build from the live scene;
the Kinematics action has an *Open Guide Designer* button.

Everything the designer authors — connections, scene-node groups, node
positions, collapse modes — is stored with the guides (``Guides.layout``,
on the guide holder in Maya, so it undoes) and written to the ``.trg`` under
``"designer"``; window size, pane ratios and selection are not.

``Guides`` caches one scene scan per edit; every write through the API
invalidates it. After moving or deleting guide joints by hand in Maya, call
``guides.invalidate()`` (the designer does this on every refresh).

Writing an action
-----------------

.. code-block:: python

   from tik.trigger.core import Action, BoolField, FileField, register_action

   @register_action("weights", category="deform")
   class Weights(Action):
       """Apply skin weights from a file."""
       file = FileField("", extensions=[".trw"])
       create_deformers = BoolField(True)

       def run(self, ctx):
           path = ctx.resolve(self.file)
           ...

       def save_from_scene(self, ctx):
           ...  # write the .trw next to the session
           return [str(path)]

Tests
-----

``tests/unit/test_{document,runner,handler,guides}_trigger.py``,
``tests/integration/trigger`` (rebuild story from files),
``tests/ui`` (``TIK_TESTS_NO_MAYA=1``: pipeline, palette, reference rows,
Guide Designer, binding).
