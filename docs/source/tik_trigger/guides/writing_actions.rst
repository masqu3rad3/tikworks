Writing an Action
=================

An action is one step of a session's pipeline: typed fields plus ``run(ctx)``.

.. code-block:: python

   from tik.trigger.core import Action, BoolField, FileField, register_action


   @register_action("weights", category="deform", icon="weights")
   class Weights(Action):
       """Apply skin weights from a file."""

       label = "Skin Weights"

       file = FileField("", extensions=[".trw"], label="Weight file")
       create_deformers = BoolField(True, help="Create missing skinClusters")

       def run(self, ctx) -> None:
           path = ctx.resolve(self.file)
           ...

       def validate(self, ctx) -> list[str]:
           problems = super().validate(ctx)     # keeps the file-exists check
           if not self.file:
               problems.append("no weight file set")
           return problems

       def save_from_scene(self, ctx) -> list[str]:
           ...   # write the .trw next to the session
           return [str(path)]

Put it in ``tik/trigger/actions/weights/weights.py`` and ``load_plugins()`` finds
it. The ``category`` (``structure``, ``build``, ``deform``, ``finish``,
``utility``) decides which shelf group and palette section it appears in.

The lifecycle
-------------

.. list-table::
   :header-rows: 1
   :widths: 26 74

   * - Method
     - When it runs
   * - ``run(ctx)``
     - Required. Once per build, in document order, if the action is enabled.
   * - ``validate(ctx)``
     - Optional. Pre-flight only, from ``Session.validate()``. Never touches the
       scene. The base implementation already reports missing files for every
       ``FileField`` opened for reading — call ``super()`` rather than replacing
       it.
   * - ``save_from_scene(ctx)``
     - Optional. Writes side files (weights, shapes) from the current scene and
       returns the paths it wrote.
   * - ``summary()``
     - Optional. The short text shown next to the action's name in the pipeline.
       Defaults to the first file field's basename.

``ActionContext``
-----------------

.. code-block:: python

   ctx.session      # the running Session
   ctx.events       # the EventBus (ctx.log() writes to it)
   ctx.base_dir     # the folder relative paths resolve against
   ctx.path         # this action's path in the running document
   ctx.depth        # nesting depth, for logs
   ctx.paths        # extra named paths from the runner

   ctx.resolve("geo/hero.ma")     # -> absolute Path, relative to base_dir
   ctx.log("Imported 3 files")

.. note::
   For an action that came from a ``reference``, ``base_dir`` is the
   *referenced* session's own directory, so its relative paths keep resolving
   against the folder they were authored in.

Reading fields
--------------

Fields are read as plain attributes on ``self``; values were validated when they
were set, so ``run()`` does not re-check types:

.. code-block:: python

   def run(self, ctx) -> None:
       if self.reference:
           cmds.file(str(self.resolve_path(ctx)), reference=True, force=True)

Raise :class:`~tik.trigger.core.exceptions.ActionExecutionError` for a failure
that should stop the build with a readable message.

Fields and the UI
-----------------

The Python class is the schema — the settings form is generated from it by
``tik.shared.ui.fields.FormBuilder``, so there is no second place to keep in
step. Group related fields into folds:

.. code-block:: python

   from tik.trigger.core import FieldGroup

   BUILD_OPTIONS = FieldGroup("Build Options", collapsed=True)

   after_build = ChoiceField("delete", choices=["keep", "hide", "delete"],
                             group=BUILD_OPTIONS)

Hidden fields (``hidden=True``) still round-trip through the document but do not
appear in the form — that is how the ``reference`` action stores its overrides.

.. seealso::
   :doc:`sessions_and_actions` for how actions are added, addressed and
   overridden.
