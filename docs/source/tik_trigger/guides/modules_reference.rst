Built-in modules
================

Five modules ship with tik.trigger. Each entry below lists what the module
draws, what it exposes and every setting it takes, straight from the class
declarations in ``src/python/tik/trigger/modules``.

Two rules apply to all of them:

- **A socket per input.** Every declared input gets a transform in the module's
  ``socket_grp`` that the producer's output drives at build time. Optional inputs
  may stay unconnected.
- **Every output is a bind joint.** That is what the next module's bind joints
  are created under, so the whole rig has one deform hierarchy.

Every module also carries an *Anim Spaces* table (in the *Spaces* fold). Each
row names one of the module's ``space_controls``, a mode (``parent``, ``point``,
``orient``) and a label, and adds one optional input called
``<control>_<label>`` that the builder turns into a
:class:`~tik.maya.constructs.space_switch.SpaceSwitch` on that controller.

base
----

The root of a rig. Not sided; everything else attaches to its ``root`` output.

.. list-table::
   :widths: 20 80

   * - Guides
     - ``root``
   * - Inputs
     - none
   * - Outputs
     - ``root``
   * - Builds
     - One ``root`` controller (a Circle, world-mirrored) and one ``root`` bind
       joint constrained to it.

.. list-table::
   :header-rows: 1
   :widths: 24 16 12 48

   * - Setting
     - Type
     - Default
     - Meaning
   * - ``controller_size``
     - float ≥ 0.01
     - ``10.0``
     - Size of the root controller.

fkchain
-------

N joints driven by nested FK controllers: tails, fingers, antennas.

.. list-table::
   :widths: 20 80

   * - Guides
     - ``root`` plus ``segment`` × *segments* (1 to 50)
   * - Inputs
     - ``root`` (primary)
   * - Outputs
     - ``root``, ``segment1`` … ``segment<N>``, ``end``
   * - Builds
     - One bind joint per guide, in a chain. One FK controller per joint except
       the last, each parented under the previous (behaviour-mirrored). The
       first controller's offset group follows the ``root`` socket.

.. list-table::
   :header-rows: 1
   :widths: 24 16 12 48

   * - Setting
     - Type
     - Default
     - Meaning
   * - ``segments``
     - int 1–50
     - ``3``
     - Joints after the root. Changing it adds or removes guides and outputs.
   * - ``spacing``
     - float ≥ 0.01
     - ``5.0``
     - Default distance between freshly drawn guides.
   * - ``controller_size``
     - float ≥ 0.01
     - ``2.0``
     - Size of the FK controllers.

arm
---

A biped arm: collar plus a single-IK-chain IK/FK limb, with limb lock and an
auto-collar.

.. figure:: /_static/screenshots/maya_built_arm.png
   :class: screenshot
   :alt: A built arm module

.. list-table::
   :widths: 20 80

   * - Guides
     - ``collar``, ``shoulder``, ``elbow``, ``hand``, ``neutral``
   * - Inputs
     - ``root`` (primary): where the collar hangs, usually the chest or body
   * - Outputs
     - ``collar``, ``upperarm``, ``lowerarm``, ``hand``
   * - Space controls
     - ``ik``, ``pole``
   * - Builds
     - A ``collar`` controller (CurvedCircle, behaviour-mirrored) driving the
       collar bind joint. Through the ``limb`` system: ``ik_*`` and ``fk_*``
       puppet joints in ``rig_grp``, one ``ikRPsolver`` handle with soft IK, FK
       controllers, an IK controller with a tweak, a pole controller with a
       twist-aware auto space, and bind joints that *are* the IK/FK blend (no
       separate blend chain). The ``ikFk`` attribute lives on the IK control.
       Optionally the ``reach`` system (auto-collar) and the ``limb_lock``
       system with its ``limbLock``, ``currentLength`` and ``lockLength``
       attributes.

The ``neutral`` guide is the auto-collar's zero: the direction from the collar
in which the arm rests. The default guides form a T-pose, so the default neutral
is the T-pose. Only its direction matters, which is why it sits past the hand.

.. list-table::
   :header-rows: 1
   :widths: 26 18 14 42

   * - Setting
     - Type
     - Default
     - Meaning
   * - ``stretch``
     - bool
     - ``True``
     - Build the stretch network (limb grows past its rest length).
   * - ``squash``
     - bool
     - ``True``
     - Build the compress-side network.
   * - ``pole_pin``
     - bool
     - ``False``
     - Let the elbow lock to the pole control.
   * - ``limb_lock`` *(Limb Lock)*
     - bool
     - ``True``
     - Hold the shoulder-to-hand distance while the hand anchors. Inert until the
       animator raises ``limbLock``.
   * - ``lock_from`` *(Limb Lock)*
     - ``shoulder`` / ``collar``
     - ``shoulder``
     - ``shoulder`` displaces the arm chain and leaves the collar on the chest;
       ``collar`` carries the clavicle along.
   * - ``auto_collar`` *(Auto Collar)*
     - bool
     - ``True``
     - Build the auto-collar network.
   * - ``auto_collar_lift_angles``
     - two floats, ±89
     - ``(-60, 75)``
     - Arm elevation below and above the neutral at full falloff.
   * - ``auto_collar_lift_degrees``
     - two floats, ±90
     - ``(-6, 15)``
     - Collar rotation at each of those angles.
   * - ``auto_collar_swing_angles``
     - two floats, ±89
     - ``(-45, 60)``
     - Arm azimuth behind and in front of the neutral at full falloff.
   * - ``auto_collar_swing_degrees``
     - two floats, ±90
     - ``(-6, 10)``
     - Collar rotation at each of those angles.
   * - ``auto_collar_interpolation``
     - ``linear`` / ``smooth`` / ``spline``
     - ``smooth``
     - Ramp shape. Only ``smooth`` has no slope discontinuity.

.. note::

   The auto-collar's measured angles saturate at ±90° off-plane, which is why
   the angle limits are capped at ±89. Matrix-derived twist, used by the pole
   space and the twist module, is bounded to ±180° about the rest pose. Both are
   properties of the representation, not of the wiring.

twist
-----

N joints rolling about one axis between two inputs. Generic, not an arm
accessory: ``twist_source`` says which end drives the roll, ``extraction`` says
how the angle is read.

.. list-table::
   :widths: 20 80

   * - Guides
     - ``base``, ``end``, plus ``twist`` × *count* (1 to 20)
   * - Inputs
     - ``base`` (primary): the segment start. ``end``: the segment end.
       ``reference`` (optional): what a start-sourced twist is measured against;
       defaults to the base socket's parent.
   * - Outputs
     - ``twist0`` … ``twist<N-1>``
   * - Guide attributes
     - Each ``twist`` guide carries ``position`` (0 to 1 along the segment) and
       ``twistWeight`` (its share of the roll; unclamped, negative reverses).
   * - Builds
     - One bind joint per twist guide, riding an aim frame from the base socket
       to the end socket so they stay on the segment in every pose. Each joint's
       roll is the extracted twist times its weight.

The guides constrain the shape they describe: the base guide is free and its X
axis *is* the segment; the end guide can only move in ``translateX``; the twist
guides' channels are locked and driven by their ``position`` attribute. Aiming
is done by orienting the base, a single visible decision.

.. list-table::
   :header-rows: 1
   :widths: 24 20 12 44

   * - Setting
     - Type
     - Default
     - Meaning
   * - ``count``
     - int 1–20
     - ``3``
     - Number of twist joints.
   * - ``axis``
     - ``auto`` / ``X`` / ``Y`` / ``Z``
     - ``auto``
     - The roll axis; ``auto`` picks the local axis of the driver that points at
       the other end.
   * - ``twist_source`` *(Extraction)*
     - ``start`` / ``end``
     - ``end``
     - ``end`` follows the child (a forearm); ``start`` counters the segment's
       own roll (an upper arm).
   * - ``extraction`` *(Extraction)*
     - ``auto`` / ``matrix`` / ``channel``
     - ``auto``
     - ``channel`` reads the driver's rotate channel: unbounded, but only right
       for an FK-style driver. ``matrix`` decomposes the rotation: works
       anywhere, wraps past ±180°.
   * - ``spacing`` *(Guides)*
     - float ≥ 0.01
     - ``10.0``
     - Default guide distance, base to end.

ribbon
------

A deforming strip pinned between two inputs, built on the
:class:`~tik.maya.constructs.ribbon.Ribbon` construct.

.. list-table::
   :widths: 20 80

   * - Guides
     - ``start``, ``end``
   * - Inputs
     - ``start`` (primary), ``end``, ``reference`` (optional: the frame the start
       twist is read against)
   * - Outputs
     - ``joint0`` … ``joint<N-1>``
   * - Builds
     - The ribbon construct in ``rig_grp`` (start and end plugs pinned to the
       sockets, mid controllers on the mid plugs), and one bind joint per ribbon
       joint under ``rig.bind_parent``, constrained from it.

.. list-table::
   :header-rows: 1
   :widths: 24 16 12 48

   * - Setting
     - Type
     - Default
     - Meaning
   * - ``joint_count``
     - int 1–40
     - ``5``
     - Number of deform joints along the strip.
   * - ``mid_count``
     - int 0–10
     - ``1``
     - Mid controllers between the ends.
   * - ``twist``
     - bool
     - ``True``
     - Drive the ribbon's twist from the pinned inputs.
   * - ``degree`` *(Deformation)*
     - int 1–3
     - ``3``
     - B-spline degree of the joint strip (clamped to the driver count).
   * - ``scaleable`` *(Deformation)*
     - bool
     - ``True``
     - Stretch-driven ``scaleX`` on the deform joints.
   * - ``preserve_volume`` *(Deformation)*
     - bool
     - ``False``
     - Counter-scale Y and Z by ``ratio ** -0.5``.
   * - ``controller_size`` *(Guides)*
     - float ≥ 0.01
     - ``2.0``
     - Size of the mid controllers.
   * - ``spacing`` *(Guides)*
     - float ≥ 0.01
     - ``10.0``
     - Default distance between the two guides.

The systems behind them
-----------------------

Modules never inherit from other modules; what they share lives in
``tik/trigger/systems``. A system composes tik.maya constructs *and* creates
controllers, naming the animator-facing attributes, which is exactly what a
construct is not allowed to do.

.. list-table::
   :header-rows: 1
   :widths: 16 84

   * - System
     - What it builds
   * - ``limb``
     - The IK/FK limb behind the arm. Three joint sets, not four: ``ik_*`` and
       ``fk_*`` in ``rig_grp``, and bind joints that are the blend result. One
       ``ikRPsolver`` handle serves the whole limb; soft IK, stretch and squash
       are independent factors on the chain lengths, so an option that is off
       really does leave a smaller graph.
   * - ``limb_lock``
     - Holds the root-to-effector distance while the effector anchors. Three
       attributes on the IK control: ``limbLock`` (0 to 1), ``currentLength``
       (a locked live readout) and ``lockLength`` (absolute units). The
       workflow: read ``currentLength``, paste it into ``lockLength``, raise
       ``limbLock``, and nothing moves at that instant.
   * - ``reach``
     - Auto-collar, named for the behaviour because the same system serves a
       hip. A frame whose X axis is the neutral direction, off-plane ``atan2``
       angles that never hit a branch cut, and one three-point ``smooth`` ramp
       per axis so the falloff is smooth through zero.
   * - ``twist``
     - Twist extraction in degrees, from a swing-twist matrix decomposition or
       from a driver's own roll channel.
