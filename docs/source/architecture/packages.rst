The packages
============

What each package contains today, as opposed to what it is for. The two big
ones have their own sections (:doc:`/tik_maya/index`,
:doc:`/tik_trigger/index`); this page covers the rest and the map.

tik.core
--------

Pure Python value objects and algorithms. No Maya, no Qt, no filesystem
assumptions beyond ``jsonio``.

.. list-table::
   :widths: 24 76

   * - ``fields``
     - Declarative, typed settings fields: ``Field`` and its subclasses
       (``IntField``, ``FloatField``, ``BoolField``, ``StringField``,
       ``ChoiceField``, ``VectorField``, ``Vector2Field``, ``Vector3Field``,
       ``ListField``, ``DictField``, ``FileField``, ``NodeRefField``,
       ``TableField`` with ``Column``), ``FieldGroup`` for folds, and the
       ``Schema`` mixin that gives a class ``fields()``, ``schema()``,
       ``values()``, ``apply()`` and ``reset()``. Every tik.trigger module and
       action is a ``Schema``.
   * - ``color``
     - ``Color``: RGB floats inside, names, hex and tuples in, HSV, randomisation.
   * - ``side``
     - ``Side``: ``L`` / ``R`` / ``C`` with ``mirror`` and ``multiplier``.
   * - ``bspline``
     - Clamped uniform B-spline basis functions; the maths behind ``MatrixSpline``.
   * - ``jsonio``
     - ``load``, ``save``, ``loads``, ``dumps`` with the project's error types.
   * - ``benchmark``
     - ``Benchmark`` with ``measure()`` contexts and ``compare()``.

tik.maya
--------

The Maya wrapper. :doc:`/tik_maya/index` is the entry point.

tik.shared
----------

Infrastructure and Qt widgets that more than one tool would otherwise
reimplement. May depend on Maya and on Qt; must not encode rig or pipeline
intent.

.. list-table::
   :widths: 24 76

   * - ``io``, ``user_settings``
     - ``IO`` (JSON files with extension checks), ``UserSettings`` and
       ``SettingsManager`` (dict-like settings with a file, defaults and change
       tracking).
   * - ``scene_data``
     - ``SceneDictionary``: a dict that stores itself in a node attribute.
   * - ``ui.Qt``
     - The one import point for Qt: re-exports the vendored ``Qt.py`` shim, so
       PySide2 and PySide6 look the same.
   * - ``ui.fields``
     - ``FormBuilder``: a Qt form generated from any ``Schema``, with folds,
       vector rows, tables, node pickers and file fields. The settings panels in
       Trigger are this widget.
   * - ``ui.maya_window``
     - ``MayaToolWindow``: a dockable, workspace-control-aware tool window base
       that degrades to a plain ``QMainWindow`` outside Maya.
   * - ``ui.scene_watcher``
     - ``SceneWatcher``: many ``scriptJob`` events collapsed into one debounced
       refresh, with optional OpenMaya callbacks for node removal.
   * - ``ui.binding``
     - Two-way binding between Maya attributes and Qt widgets.
   * - ``ui.theme``
     - The dark theme and its colour tokens, applied with ``theme.apply()``.
   * - ``ui.collapsible``, ``ui.filter_bar``, ``ui.tile_grid``,
       ``ui.versioned_field``, ``ui.status``, ``ui.feedback``, ``ui.icons``
     - The smaller widgets: fold groups, the keyword filter bar, the reflowing
       tile shelf, the Nuke-style versioned file field, status-bar fields,
       message boxes, generated glyph icons.

tik.trigger
-----------

The rigging framework. :doc:`/tik_trigger/index` is the entry point.

tik.tools
---------

User-facing tools. One so far:

.. list-table::
   :widths: 24 76

   * - ``polish``
     - Controller-shape tooling on top of ``tik.maya.utils.control_shapes``: a
       ``PolishCore`` that knows the library and extra search paths from its
       settings, and a Qt shape browser (``ui/mcv/controller_shapes_mcv.py``)
       with a category tree, a flat search mode and hover thumbnails.

.. figure:: /_static/screenshots/maya_polish_shape_library.png
   :class: screenshot
   :alt: The Polish shape library browser

   The Polish shape browser.

tik.vendor
----------

Third-party code shipped with the repository so there is nothing to install:
``Qt.py`` (the PySide2/PySide6 shim) and ``apiundo`` (the bridge that makes
OpenMaya edits undoable). Neither is TikWorks API and neither appears in the
:doc:`API reference </autoapi/index>`.

Repository map
--------------

.. code-block:: text

   tikworks/
   ├── src/python/tik/          the importable package (put src/python on sys.path)
   │   ├── core/  maya/  shared/  trigger/  tools/  vendor/
   ├── tests/
   │   ├── unit/                one file per module, run under mayapy
   │   ├── integration/trigger/ end-to-end builds against a real scene
   │   ├── ui/                  Qt tests without Maya (TIK_TESTS_NO_MAYA=1)
   │   └── helpers/             toy modules for the trigger tests
   ├── snippets/                cmds-vs-tik.maya comparisons, converter examples
   ├── docs/                    this documentation (Sphinx)
   │   ├── source/              pages, conf.py, screenshots
   │   ├── screenshots/         the script that renders the UI screenshots
   │   └── superpowers/         design specs and implementation plans
   ├── AI/                      coding, testing and documentation rules
   ├── package/                 build and deploy scripts
   └── Makefile                 docs, tests, coverage, packaging targets
