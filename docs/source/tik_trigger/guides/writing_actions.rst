Writing an action
=================

An action is one step of a session's pipeline: typed fields plus ``run(ctx)``.
Everything else, the row in the pipeline, the settings form, the shelf tile,
validation before a build, is derived from the class.

.. code-block:: python

   import tik.maya as tm
   from tik.trigger.core import Action, BoolField, FileField, register_action
   from tik.trigger.core.exceptions import ActionExecutionError


   @register_action("weights", category="deform", icon="weights")
   class Weights(Action):
       """Apply skin weights from a file."""

       label = "Skin Weights"

       file = FileField("", extensions=[".json"], label="Weight file")
       create_deformers = BoolField(True, help="Create missing skinClusters")

       def run(self, ctx) -> None:
           path = ctx.resolve(self.file)
           if not path.exists():
               raise ActionExecutionError(f"weights file not found: {path}")
           tm.SkinCluster.create_from_file(str(path))
           ctx.log(f"Applied weights from {path.name}")

       def validate(self, ctx) -> list[str]:
           problems = super().validate(ctx)      # keeps the file-exists check
           if not self.file:
               problems.append("no weight file set")
           return problems

       def save_from_scene(self, ctx) -> list[str]:
           path = ctx.resolve(self.file)
           tm.resolve("body_skin").save_weights(str(path))
           return [str(path)]

Put it in ``tik/trigger/actions/weights/weights.py`` and ``load_plugins()`` finds
it. The ``category`` (``structure``, ``build``, ``deform``, ``finish`` or
``utility``) decides which shelf group and palette section it appears in and
which colour its tile takes.

The lifecycle
-------------

.. list-table::
   :header-rows: 1
   :widths: 26 74

   * - Method
     - When it runs
   * - ``run(ctx)``
     - Required. Once per build, in document order, when the action is enabled.
       Raise :class:`~tik.trigger.core.exceptions.ActionExecutionError` for a
       failure that should stop the build with a readable message.
   * - ``validate(ctx)``
     - Optional. Pre-flight only, from ``Session.validate()``, never during a
       build and never touching the scene. The base implementation reports a
       missing file for every ``FileField`` opened for reading, so call
       ``super()`` rather than replacing it.
   * - ``save_from_scene(ctx)``
     - Optional. Writes side files (weights, shapes) from the current scene and
       returns the paths it wrote. The properties panel offers it as a button
       when an action implements it.
   * - ``summary()``
     - Optional. The short text shown next to the action's name in the pipeline.
       Defaults to the basename of the first file field that has a value.

``ActionContext``
-----------------

.. code-block:: python

   ctx.session      # the running Session (its document, its guides)
   ctx.events       # the EventBus; ctx.log() writes to it
   ctx.base_dir     # the folder relative paths resolve against
   ctx.path         # this action's path in the running document
   ctx.depth        # nesting depth, for indenting logs
   ctx.paths        # extra named paths from the runner: {"directory": base_dir}

   ctx.resolve("geo/hero.ma")     # -> absolute Path, relative to base_dir
   ctx.log("Imported 3 files", level="info")

.. note::

   For an action that came in through a ``reference``, ``base_dir`` is the
   *referenced* session's own folder, so its relative paths keep resolving
   against the place they were authored in.

Reading fields
--------------

Fields are plain attributes on ``self``. Values were validated when they were
set, whether from the UI, from ``handle.setting = value`` or from the ``.tr``,
so ``run()`` does not re-check types.

Fields and the UI
-----------------

The Python class is the schema; the settings form is generated from it by
``tik.shared.ui.fields.FormBuilder``, so there is no second place to keep in
step. Group related fields into folds with a ``FieldGroup``, and mark fields
``hidden=True`` when they should round-trip through the document without
appearing in the form. That is how the ``reference`` action stores its overrides.

.. code-block:: python

   from tik.trigger.core import ChoiceField, FieldGroup

   BUILD_OPTIONS = FieldGroup("Build Options", collapsed=True)

   after_build = ChoiceField("delete", choices=["keep", "hide", "delete"], group=BUILD_OPTIONS)

Fields marked ``mode="open"`` on a ``FileField`` (the default) are the ones the
base ``validate`` checks for existence; use ``mode="save"`` for paths the action
writes.

Testing an action
-----------------

Actions that touch the scene are tested under ``mayapy`` like everything else.
The pure parts, field validation and ``summary()``, need no Maya at all:

.. code-block:: python

   def test_weights_summary():
       action = Weights(settings={"file": "weights/body.json"})
       assert action.summary() == "body.json"

.. seealso::

   :doc:`sessions_and_actions` for how actions are added, addressed and
   overridden, and :doc:`actions_reference` for the four built-in ones.
