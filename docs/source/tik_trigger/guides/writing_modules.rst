Writing a Module
================

A module is **declarative**: it states what it needs, and implements two methods
that touch the scene through objects the framework hands it. Everything else —
the four groups, naming, tagging, side handling, parenting under the rig root,
creating a socket per declared input and connecting it to its producer — is done
for you.

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
           rig.socket("root", match=root_guide)

           joint = rig.bind_joint("root", match=root_guide)
           tip = rig.bind_joint("tip", parent=joint, match=tip_guide)

           controller = rig.controller(
               "clavicle", size=self.controller_size, match=root_guide,
               mirror="behaviour",
           )
           tm.MatrixConstraint.create(controller, joint, maintain_offset=True)

           rig.output("root", joint)
           rig.output("tip", tip)

Registering it under ``tik/trigger/modules/clavicle/clavicle.py`` is enough for
``load_plugins()`` to find it, and for the UI to build its settings form.

The manifest
------------

``GuideLayout``
~~~~~~~~~~~~~~~

The ordered guide roles the module needs. The first role is the root.

.. code-block:: python

   GuideLayout("collar", "shoulder", "elbow", "hand")
   GuideLayout("root", multi="segment", min=1, max=50)   # root + N segments

For a repeating role, override ``guide_count()`` to drive the count from a
setting:

.. code-block:: python

   segments = IntField(3, min=1, max=50)

   def guide_count(self) -> int:
       return self.segments

``Input``
~~~~~~~~~

An attachment point another module (or a scene node) can drive.

.. code-block:: python

   inputs = (
       Input("start", primary=True, help="What the ribbon start pins to"),
       Input("end", help="What the ribbon end pins to"),
       Input("reference", optional=True, help="Frame the twist is read against"),
   )

- ``primary`` — one per module; the tree view shows it as parenting.
- ``optional`` — the build succeeds with no source connected.
- ``kind`` — ``transform`` | ``joint`` | ``attribute``, used by graph validation.

.. important::
   **Declaring an input is what creates its socket.** ``ModuleRig`` materializes
   one transform per declared input in ``socket_grp`` before ``build()`` runs, so
   a module cannot forget to make one.

``outputs``
~~~~~~~~~~~

The names other modules may connect to. Override ``output_names()`` when a
setting adds outputs:

.. code-block:: python

   outputs = ("root", "end")

   @classmethod
   def output_names(cls, settings=None):
       count = int((settings or {}).get("segments", cls.segments.default))
       return ("root", *(f"segment{i + 1}" for i in range(count)), "end")

``guide_attrs``
~~~~~~~~~~~~~~~

Guides normally round-trip by world position alone. A module that needs per-guide
*data* — a twist weight, a falloff — declares it, and the guide layer creates,
exports and restores the attribute:

.. code-block:: python

   from tik.trigger.core import GuideAttr

   guide_attrs = {
       "twist": (GuideAttr("twistWeight", default=1.0, help="Roll share"),),
   }

Anim spaces
~~~~~~~~~~~

Every module inherits an ``anim_spaces`` table field. List the controller roles
that accept spaces, and each row becomes one optional input named
``<control>_<label>``:

.. code-block:: python

   space_controls = ("ik", "pole")   # a row {"control": "ik", "label": "chest"}
                                     # adds the input "ik_chest"

Fields
------

Settings are :mod:`tik.core.fields` descriptors — the Python class *is* the
schema, and the UI form is generated from it. An optional ``defaults.json``
beside the module overrides defaults only; it can never add or rename a field.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Field
     - Use
   * - ``IntField`` / ``FloatField``
     - Numbers, with ``min`` / ``max``.
   * - ``BoolField``
     - Checkboxes.
   * - ``StringField``
     - Free text.
   * - ``ChoiceField``
     - A fixed set of ``choices``.
   * - ``Vector2Field`` / ``Vector3Field``
     - A pair or triple on one row.
   * - ``ListField`` / ``DictField``
     - Collections; ``DictField`` is usually ``hidden=True``.
   * - ``FileField``
     - A path, with ``extensions`` and Nuke-style version stepping in the UI.
   * - ``NodeRefField``
     - A Maya node name picked from the selection.
   * - ``TableField`` + ``Column``
     - Rows of typed columns (this is what ``anim_spaces`` is).

Related fields fold together with a ``FieldGroup``:

.. code-block:: python

   from tik.trigger.core import FieldGroup

   LIMB_LOCK = FieldGroup("Limb Lock")
   AUTO_COLLAR = FieldGroup("Auto Collar", collapsed=True)

   limb_lock = BoolField(True, label="Limb Lock", group=LIMB_LOCK)

Drawing guides
--------------

``draw_guides(guides)`` receives a
:class:`~tik.trigger.maya.rig.GuideDraft`, which creates tagged, named,
side-coloured guide joints and adds any declared ``guide_attrs``:

.. code-block:: python

   def draw_guides(self, guides) -> None:
       root = guides.joint("root", (0, 0, 0), radius=2.0)
       for index in range(self.segments):
           guides.joint(
               "segment", (self.spacing * (index + 1) * guides.side_mult, 0, 0),
               index=index, parent=root,
           )

``guides.side_mult`` is ``-1`` on the right, so one set of numbers serves both
sides. Creating the same ``(role, index)`` twice raises ``GuideError``.

``wire_guides(guides)`` is optional. It runs after ``draw_guides`` *and* after
guides are re-imported from a ``.trg``, so a module that constrains or drives
its own guides gets the same rig on both paths.

Building
--------

``build(rig)`` receives a :class:`~tik.trigger.maya.rig.ModuleRig`. The ``rig``
object owns naming, tagging, group placement and registration; ``tik.maya`` owns
the mechanism — which is why module code still says
``tm.MatrixConstraint.create(...)`` outright.

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Call
     - What it gives you
   * - ``rig.guide(role, index=0)``
     - One guide joint. ``rig.guides("a", "b")`` for several,
       ``rig.chain(role)`` for every guide of a multi role, in index order.
   * - ``rig.socket(name, match=)``
     - The socket for a declared input, optionally aligned to a node.
   * - ``rig.controller(name, shape=, size=, parent=, match=, mirror=, offset=)``
     - A tagged ``Controller`` with its offset group at ``ctrl.offset``.
       ``mirror`` is ``"behaviour"`` (FK-like) or ``"world"`` (IK-like).
   * - ``rig.tweak_control(main, size=)``
     - A secondary control parented under ``main``, with its ``tweakVis`` switch.
   * - ``rig.bind_joint(name, parent=, match=)``
     - A deform joint in the single rig-wide bind hierarchy. Defaults to
       ``rig.bind_parent``.
   * - ``rig.deform_joint(node)``
     - Tag a joint you made yourself as deform.
   * - ``rig.output(name, node)``
     - Register a declared output. An undeclared name raises.
   * - ``rig.attach(input, node)``
     - Point an input at a node you built, instead of its socket.
   * - ``rig.name(*tokens, suffix=)`` / ``rig.group(*tokens, under=)``
     - Module-correct names, and groups under ``socket`` / ``control`` / ``rig``
       / ``bind``.

Module ground rules
-------------------

.. list-table::
   :header-rows: 1
   :widths: 24 76

   * - Rule
     - Detail
   * - Four groups
     - ``socket_grp`` (input attach transforms), ``control_grp`` (controllers
       and their offset/space groups, *nothing else*), ``rig_grp`` (the puppet:
       IK/FK chains, handles, math), ``bind_grp`` (deform/export joints only).
   * - Two skeletons
     - The puppet lives in ``rig_grp``; the engine-neutral deform skeleton lives
       in ``bind_grp`` with **live TRS**, so it bakes and exports.
   * - One bind hierarchy
     - Per rig, built in final position via ``rig.bind_parent`` and never
       reparented. ``MatrixConstraint`` wires a live connection to the driven's
       parent inverse at build time, so a joint moved afterwards keeps
       compensating for its old parent.
   * - A socket per input
     - Created for you in ``socket_grp``. Declaring the input is what makes it.
   * - Controllers
     - Come with their offset group (``ctrl.offset``).

.. note::
   ``Controller`` proxies attribute and plug *reads* to its transform, but not
   writes. Assignments and type-checked ``tik.maya`` APIs take
   ``ctrl.transform``.

Systems, not base modules
-------------------------

.. important::
   **Modules never inherit from other modules.** Shared behaviour goes in
   ``tik/trigger/systems/``.

A *system* composes ``tik.maya`` constructs **and** creates controllers, naming
the animator-facing attributes. The built-in ones:

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - System
     - What it builds
   * - ``limb``
     - The IK/FK limb behind the arm and the leg. Three joint sets, not four:
       ``ik_*`` and ``fk_*`` in ``rig_grp``, and bind joints that *are* the
       blend result — so there is no redundant blend chain, and one
       ``ikRPsolver`` handle serves the whole limb.
   * - ``limb_lock``
     - Holds the root-to-effector distance while the effector anchors: lock an
       arm, pull the hand, and the shoulder is dragged after it. Three
       attributes — ``limbLock``, ``currentLength``, ``lockLength``.
   * - ``reach``
     - Auto-collar, named for the behaviour rather than the anatomy (the same
       system serves a hip). A neutral guide, an off-plane signed ``atan2``
       elevation and a three-point ``remapValue``.
   * - ``twist``
     - Twist extraction in degrees, from a swing-twist matrix decomposition or
       from a driver's own roll.

.. warning::
   Two measured bounds are properties of the representation, not of the wiring:
   matrix-derived twist is bounded to ±180° about the rest pose, and the
   ``reach`` elevation to ±90° off-plane.

Built-in modules
----------------

.. list-table::
   :header-rows: 1
   :widths: 16 84

   * - Type
     - Summary
   * - ``base``
     - The root controller and joint every rig starts from. Not sided;
       everything else attaches to its ``root`` output.
   * - ``fkchain``
     - N joints driven by nested FK controllers — tails, fingers, antennas.
       Exposes ``root``, one ``segment<N>`` per joint, and ``end``.
   * - ``arm``
     - Biped arm: collar, shoulder, elbow, hand, plus a neutral guide for the
       auto-collar. Single IK chain, limb lock, twist-aware pole space.
   * - ``twist``
     - N joints rolling about one axis between two inputs. Position and weight
       are *authored* per guide, not derived; the joints ride an aim frame, so
       they stay on the base-to-end line in every pose.
   * - ``ribbon``
     - A deforming strip pinned between two inputs, with optional stretch-driven
       scale and volume preservation.

.. seealso::
   ``AI/coding_rules.md`` holds the full text of the module ground rules, and
   the ``tik-maya`` skill covers writing the Maya code inside ``build()``.
