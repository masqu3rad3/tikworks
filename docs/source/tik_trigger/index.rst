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
* **Module** — manifest (``Guides(...)`` roles, plugs/sockets, typed fields,
  ``legacy_types`` for old ``.trg`` names) + ``draw_guides(ctx)`` / ``build(ctx)``.

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
   guides.mirror(arm)
   guides.test_build(body, arm)
   guides.export("guides/hero_muscle.trg")

UI
--

.. code-block:: python

   import tik.trigger.ui
   tik.trigger.ui.show()

Tabs are open sessions. Add actions from the collapsible shelf (click = after
selection, drag = anywhere, drop on a row = nest) or press **Tab** for the
search palette (Enter: sibling, Shift+Enter: child). Referenced rows render
inline, dimmed, with checkboxes; edits become overrides. The Guide Designer
(toolbar or the ✎ next to a guides file) authors ``.trg`` files with two-way
scene binding and drag-parenting.

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
