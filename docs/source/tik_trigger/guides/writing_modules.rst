Writing a module
================

A module is **declarative**. It states what it needs, and it implements two
methods that touch the scene through objects the framework hands it. The four
groups, the naming, the tagging, the side handling, parenting under the rig
root, a socket per declared input and the connection to its producer: all of
that is done for you.

The shape of one
----------------

.. code-block:: python

   import tik.maya as tm
   from tik.trigger.core import (
       BoolField, FloatField, GuideLayout, Input, Module, register_module,
   )


   @register_module("clavicle")
   class Clavicle(Module):
       """A single-joint clavicle driven by one FK controller."""

       label = "Clavicle"
       guides = GuideLayout("root", "tip")
       inputs = (Input("root", primary=True, help="Where the clavicle hangs"),)
       outputs = ("root", "tip")

       controller_size = FloatField(2.0, min=0.01, label="Controller Size")
       lock_scale = BoolField(True, help="Lock the controller's scale channels")

       def draw_guides(self, guides) -> None:
           root = guides.joint("root", (0, 0, 0), radius=1.5)
           guides.joint("tip", (5 * guides.side_mult, 0, 0), parent=root)

       def build(self, rig) -> None:
           root_guide, tip_guide = rig.guides("root", "tip")
           socket = rig.socket("root", match=root_guide)

           joint = rig.bind_joint("root", match=root_guide)
           tip = rig.bind_joint("tip", parent=joint, match=tip_guide)

           controller = rig.controller(
               "clavicle", size=self.controller_size, match=root_guide, mirror="behaviour",
           )
           tm.MatrixConstraint.create(socket, controller.offset, maintain_offset=True)
           tm.MatrixConstraint.create(controller, joint, maintain_offset=True)
           if self.lock_scale:
               for channel in ("sx", "sy", "sz"):
                   controller[channel].locked = True
                   controller[channel].visible = False

           rig.output("root", joint)
           rig.output("tip", tip)

Save it as ``tik/trigger/modules/clavicle/clavicle.py`` and ``load_plugins()``
finds it: the folder name and the file name must match, and the class must carry
the decorator. The UI builds its settings form from the two fields, its shelf
tile from ``label``, and its graph node from ``inputs`` and ``outputs``.

The manifest
------------

``GuideLayout``
~~~~~~~~~~~~~~~

The ordered guide roles the module needs. The first role is the root, the one a
child module's guides hang under.

.. code-block:: python

   GuideLayout("collar", "shoulder", "elbow", "hand")
   GuideLayout("root", multi="segment", min=1, max=50)    # root + N "segment" guides

For a repeating role, override ``guide_count()`` so a setting drives the count.
Changing that setting in the UI adds or removes guides while keeping every
surviving pose:

.. code-block:: python

   segments = IntField(3, min=1, max=50)

   def guide_count(self) -> int:
       return self.segments

``Input``
~~~~~~~~~

An attachment point another module, or a scene node, can drive.

.. code-block:: python

   inputs = (
       Input("start", primary=True, help="What the ribbon start pins to"),
       Input("end", help="What the ribbon end pins to"),
       Input("reference", optional=True, help="Frame the twist is read against"),
   )

- ``primary``: one per module. The tree shows it as parenting, and drawing a
  module under another pre-fills it.
- ``optional``: the build succeeds with nothing connected.
- ``kind``: ``transform`` (default), ``joint`` or ``attribute``; ``space`` is
  reserved for the inputs the anim-spaces table generates.

.. important::

   **Declaring an input is what creates its socket.** Before ``build()`` runs,
   ``ModuleRig`` materialises one transform per declared input in
   ``socket_grp``, so a module cannot forget to make one. ``rig.socket(name)``
   fetches it.

``outputs``
~~~~~~~~~~~

The names other modules may connect to. Every output must be registered with
``rig.output(name, joint)`` during ``build``, and every output must be a bind
joint, because that is what a child module's bind joints are created under.
Override ``output_names()`` when a setting adds outputs:

.. code-block:: python

   outputs = ("root", "end")

   @classmethod
   def output_names(cls, settings=None):
       count = int((settings or {}).get("segments", cls.segments.default))
       return ("root", *(f"segment{i + 1}" for i in range(count)), "end")

``guide_attrs``
~~~~~~~~~~~~~~~

Guides normally round-trip by pose alone. A module that needs per-guide *data*
declares it, and the guide layer creates the attribute on the joint, captures it
into the document, exports it and restores it:

.. code-block:: python

   from tik.trigger.core import GuideAttr

   guide_attrs = {
       "twist": (GuideAttr("twistWeight", default=1.0, help="Roll share"),),
   }

Anim spaces
~~~~~~~~~~~

Every module inherits an ``anim_spaces`` table. List the controller roles that
accept spaces, and each row the rigger adds becomes one optional input named
``<control>_<label>`` and, at build time, a space switch on that controller:

.. code-block:: python

   space_controls = ("ik", "pole")     # a row {"control": "ik", "label": "chest"}
                                       # adds the input "ik_chest"

Fields
------

Settings are :mod:`tik.core.fields` descriptors. The Python class *is* the
schema: the UI form, the ``.tr`` serialisation and ``handle.setting = value``
validation all read the same declarations. An optional ``defaults.json`` beside
the module overrides default values only; it can never add or rename a field.

.. list-table::
   :header-rows: 1
   :widths: 32 68

   * - Field
     - Use
   * - ``IntField`` / ``FloatField``
     - Numbers, with ``min`` and ``max``.
   * - ``BoolField``
     - A checkbox.
   * - ``StringField``
     - Free text.
   * - ``ChoiceField(default, choices)``
     - A fixed set of values, shown as a combo box.
   * - ``Vector2Field`` / ``Vector3Field``
     - A pair or a triple on one row, with optional per-component ``labels``.
   * - ``ListField`` / ``DictField``
     - Collections. ``DictField`` is usually ``hidden=True``.
   * - ``FileField(default, extensions, mode)``
     - A path, with version stepping in the UI.
   * - ``NodeRefField``
     - A Maya node name, picked from the selection.
   * - ``TableField`` + ``Column``
     - Rows of typed columns; this is what ``anim_spaces`` is.

Every field takes ``label``, ``help`` (the tooltip), ``hidden`` and ``group``.
Related fields fold together with a ``FieldGroup``:

.. code-block:: python

   from tik.trigger.core import FieldGroup

   LIMB_LOCK = FieldGroup("Limb Lock")
   AUTO_COLLAR = FieldGroup("Auto Collar", collapsed=True)

   limb_lock = BoolField(True, label="Limb Lock", group=LIMB_LOCK)

.. figure:: /_static/screenshots/form_builder_arm.png
   :class: screenshot
   :alt: The arm module's generated form

   The arm's fields as the UI renders them: three plain checkboxes, then the
   *Limb Lock*, *Auto Collar* and *Spaces* folds.

Drawing guides
--------------

``draw_guides(guides)`` receives a :class:`~tik.trigger.maya.rig.GuideDraft`.
Its one method creates a tagged, named, side-coloured guide joint and adds any
declared guide attributes:

.. code-block:: python

   def draw_guides(self, guides) -> None:
       root = guides.joint("root", (0, 0, 0), radius=2.0)
       for index in range(self.segments):
           guides.joint(
               "segment", (self.spacing * (index + 1) * guides.side_mult, 0, 0),
               index=index, parent=root,
           )

Positions are world space. ``guides.side_mult`` is ``-1`` on the right, so one
set of numbers serves both sides. The first joint drawn is the root and the
default parent of the rest; creating the same ``(role, index)`` twice raises
``GuideError``.

``wire_guides(guides)`` is optional. It runs after ``draw_guides`` *and* after
guides are re-imported from a ``.trg``, so a module that constrains or drives its
own guides (the twist module locks its end guide to ``translateX``) gets the same
guide rig on both paths.

Building
--------

``build(rig)`` receives a :class:`~tik.trigger.maya.rig.ModuleRig`. The rule
for what lives on ``rig``: it owns naming, tagging, group placement and
registration, and nothing else. tik.maya owns the mechanism, which is why module
code still says ``tm.MatrixConstraint.create(...)`` outright rather than through
a wrapper that would only hide it.

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Call
     - What it gives you
   * - ``rig.guide(role, index=0)``
     - One guide joint. ``rig.guides("a", "b")`` for several, ``rig.chain(role)``
       for every guide of a multi role in index order.
   * - ``rig.socket(name, match=)``
     - The socket for a declared input, optionally aligned to a node.
   * - ``rig.controller(name, shape=, size=, parent=, color=, match=, mirror=, offset=)``
     - A tagged ``Controller`` in ``control_grp`` with its offset group at
       ``ctrl.offset``. ``mirror`` is ``"behaviour"`` (FK-like, follows its
       joint) or ``"world"`` (IK-like, world-aligned); a pose-mirror tool reads
       it, the rig does not.
   * - ``rig.tweak_control(main, size=)``
     - A secondary controller parented under ``main`` with a ``tweakVis`` switch.
   * - ``rig.controller_by_role(role)``
     - A controller this module already made, by its role name.
   * - ``rig.bind_joint(name, parent=, match=, radius=)``
     - A deform joint in the single rig-wide bind hierarchy. Defaults to
       ``rig.bind_parent``, the connected producer's bind joint.
   * - ``rig.deform_joint(node)``
     - Tag a joint you made yourself as deform.
   * - ``rig.output(name, node)``
     - Register a declared output. An undeclared name raises.
   * - ``rig.attach(input, node)``
     - Point an input at a node you built instead of its socket.
   * - ``rig.name(*tokens, suffix=)`` / ``rig.group(*tokens, under=)``
     - Module-correct names (``L_arm_<tokens>_<suffix>``), and groups under
       ``socket``, ``control``, ``rig`` or ``bind``.
   * - ``rig.groups``, ``rig.side``, ``rig.side_mult``, ``rig.instance``
     - The four groups, the side and the ``ModuleInstance`` being built.

Module ground rules
-------------------

.. list-table::
   :header-rows: 1
   :widths: 24 76

   * - Rule
     - Detail
   * - Four groups
     - ``socket_grp`` (input attach transforms), ``control_grp`` (controllers
       and their offset and space groups, *nothing else*), ``rig_grp`` (the
       puppet: IK/FK chains, handles, maths), ``bind_grp`` (deform joints only).
       The module never creates them.
   * - Two skeletons
     - The puppet lives in ``rig_grp`` and may use mirrored-behaviour orients.
       The engine-neutral deform skeleton lives in ``bind_grp`` with identical
       orients on both sides and **live translate, rotate and scale**, so it
       bakes and exports. A bind joint's transform is never parked in
       ``offsetParentMatrix``.
   * - One bind hierarchy
     - Per rig. Bind joints are created in final position via
       ``rig.bind_parent`` and never reparented: ``MatrixConstraint`` wires a
       live connection to the driven's parent inverse at build time, so a joint
       moved afterwards would keep compensating for its old parent.
   * - A socket per input
     - Created for you. Declaring the input is what makes it.
   * - Controllers
     - Come with their offset group. Drive them from sockets with constraints;
       never parent a controller under a socket.

.. note::

   ``Controller`` proxies attribute and plug *reads* to its transform, so
   ``ctrl["tx"]`` and ``ctrl.long_name`` work. It does not proxy writes:
   assignments (``ctrl.transform.world_position = ...``) and type-checked
   tik.maya calls (``snap_to``, ``set_parent``) take ``ctrl.transform``.

Systems, not base modules
-------------------------

.. important::

   **Modules never inherit from other modules.** A module's ``guides``,
   ``inputs``, ``outputs`` and fields are class attributes the registry and the
   form builder read, and a base module would drag its declarations along.
   Shared behaviour goes in ``tik/trigger/systems/`` as a function that takes
   ``rig`` first.

The arm is the example: it draws five guides and registers four outputs itself,
and calls ``build_ikfk_limb(rig, ...)``, ``build_reach(rig, ...)`` and
``build_limb_lock(rig, ...)`` for the parts a leg will share. Each returns a
small dataclass of the nodes and plugs it made so the module can wire them
together. :doc:`modules_reference` describes what each system builds.

Validation
----------

Override ``validate()`` to report problems that prevent building; call
``super()`` to keep the guide-layout and anim-space checks:

.. code-block:: python

   def validate(self) -> list[str]:
       problems = super().validate()
       if self.min_angle >= self.max_angle:
           problems.append("min_angle must be below max_angle")
       return problems

Testing
-------

Module tests run against a real Maya scene under ``mayapy``; there are no fake
backends. ``tests/helpers/toy_modules.py`` shows the smallest modules that
exercise the pipeline, and ``tests/integration/trigger/test_arm_trigger.py``
builds the arm end to end. :doc:`/contributing/testing` has the commands.
