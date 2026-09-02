Plugs: attributes, connections and maths
========================================

A :class:`~tik.maya.core.plug.Plug` is one attribute on one node. You get one
with square brackets and never construct it yourself. It reads and writes the
value, controls the channel-box state, makes and breaks connections, and turns
Python operators into utility-node networks.

.. code-block:: python

   tx = cube["translateX"]
   tx.value, tx.locked, tx.keyable, tx.visible     # state
   tx.path                                         # 'pCube1.translateX'
   tx.node                                         # the owning wrapper
   tx.attr                                         # 'translateX'
   tx.type                                         # 'kDoubleLinearAttribute'
   tx.mplug                                        # the OpenMaya MPlug, when you need it

Why brackets and not properties
-------------------------------

``cube.translate`` exists for the nine transform channels and visibility, and
you should use it there. Everything else goes through ``cube["attr"]``, for a
plain reason: Maya attributes are an open set. Custom attributes, plugin
attributes, indexed and compound children all have names that could never be
Python properties, and the bracket form is the same for all of them.

Values
------

.. code-block:: python

   cube["translateX"].value = 5.0
   cube["translate"].value = (1, 2, 3)          # compound: a tuple
   cube["translate"].value                      # [(1.0, 2.0, 3.0)], as cmds.getAttr returns it
   cube["notes"].value = "rigger: AK"           # strings are typed automatically

   matrix = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
   cube["offsetParentMatrix"].value = matrix    # 16 numbers are recognised as a matrix

``value`` is ``get()`` and ``set()`` underneath. Use those directly when you need
to pass ``cmds`` flags:

.. code-block:: python

   cube["translateX"].get(time=24)
   cube["label"].set("hero", type="string")   # the type flag applies to string and list values

Compound and indexed attributes
-------------------------------

Children are reached by name from the parent, or straight from the node. Arrays
take the usual Maya index syntax in the attribute string:

.. code-block:: python

   cube["translate"]["translateX"]         # the same plug as cube["translateX"]
   cube["worldMatrix[0]"]                  # first element of an array attribute
   blend["target[2].targetMatrix"]         # a child of an array element
   cube["translate"].children              # [Plug tx, Plug ty, Plug tz]

Channel-box state
-----------------

.. code-block:: python

   plug.locked = True          # or plug.lock() / plug.unlock()
   plug.keyable = False        # non-keyable but still shown in the channel box
   plug.visible = False        # keyable off and channelBox off: hidden
   plug.visible = True         # shown again, keyable state restored

``visible`` is the one most people want. Setting it to ``False`` is what
"lock and hide" scripts do by hand.

Connections
-----------

Three operators, three methods.

.. code-block:: python

   source >> target            # connect (force=True), returns target so it chains
   target << source            # the same connection, written from the other side
   source // target            # disconnect that connection

   source.connect(target, force=True)
   source.disconnect(target)
   target.disconnect()         # break whatever feeds target

Query what is connected:

.. code-block:: python

   target.get_input()            # the source *node*, or None
   target.get_input(plug=True)   # the source *plug*
   target.list_inputs(plugs=True)
   source.list_outputs(plugs=True)
   source.find_proxy_plugs()     # proxy attributes mirroring this plug, as 'node.attr' strings

Arithmetic
----------

The Python operators create the standard Maya utility nodes, wire the operands
in, and return the output plug. Nothing is evaluated in Python; you are building
the dependency graph, and it stays live.

.. list-table::
   :header-rows: 1
   :widths: 14 43 43

   * - Operator
     - Scalar plug (float, int, angle, distance, bool, enum)
     - Compound plug (double3, float3, double2...)
   * - ``a + b``
     - ``addDoubleLinear``
     - ``plusMinusAverage`` (sum)
   * - ``a - b``
     - ``subtract`` (2025+), else ``floatMath``
     - ``plusMinusAverage`` (subtract)
   * - ``a * b``
     - ``multDoubleLinear``
     - ``multiplyDivide`` (multiply)
   * - ``a / b``
     - ``divide`` (2025+), else ``floatMath``
     - ``multiplyDivide`` (divide)
   * - ``a ** b``
     - ``power`` (2025+), else ``multiplyDivide``
     - ``multiplyDivide`` (power)
   * - ``a % b``
     - ``modulo``
     - not supported

The right-hand side can be another plug or a number. For compound plugs a number
is broadcast to all components, and a 3-tuple is applied component-wise.
Reversed forms (``5 - a``, ``2 ** a``, ``1.0 / a``) work the same way.

.. code-block:: python

   a, b = driver["tx"], driver["ty"]

   (a + b) >> target["tz"]                    # sum of two plugs
   (a * 2.5 - 1) >> target["sx"]              # precedence is Python's: * before -
   (10 / a) >> target["sy"]                   # reversed: 10 divided by the plug

   (driver["translate"] + (0, 5, 0)) >> target["translate"]    # vector + tuple
   (driver["scale"] ** 2) >> target["scale"]                    # component-wise power

Each operation is one node, so ``(a + b) * c`` is two nodes with the first
feeding the second. Chains of any length work, and intermediate plugs can be kept
in variables and reused.

Comparisons and blends
----------------------

Python does not let ``<`` or ``if`` return a plug, so these are methods. They
build ``condition`` nodes, which exist on every Maya version.

.. code-block:: python

   a.minimum(b)                 # min(a, b)
   a.maximum(0.0)               # max(a, 0)
   a.clamped(0.0, 1.0)          # min(max(a, 0), 1)
   a.lerp(b, weight)            # a + (b - a) * weight
   a.gt(0.5, 1.0, 0.0)          # 1.0 if a > 0.5 else 0.0

``weight``, ``b`` and the two results of ``gt`` may each be a plug or a number.

A worked example: stretch with a hard limit
-------------------------------------------

The stretch factor of a limb is the live root-to-control distance over the rest
length, never less than one, and here capped at 150 percent:

.. code-block:: python

   measure = tm.Measure.create(shoulder_jnt, ik_ctrl)     # a distanceBetween node
   ratio = measure.ratio_plug()                           # distance / rest distance
   stretch = ratio.clamped(1.0, 1.5)

   for joint in (elbow_jnt, wrist_jnt):
       (stretch * joint["tx"].value) >> joint["tx"]

Four lines describe the whole network: one ``distanceBetween``, one ``divide``,
two ``condition`` nodes, two ``multDoubleLinear``. Read the same thing in
``snippets/comparisons/06_stretchy_ik`` written with ``cmds`` to see what those
four lines replace.

Things to know
--------------

- **Every operation creates nodes.** They are as permanent as any other node;
  delete them when you tear a temporary network down. Node names carry the
  operation (``multDL3``, ``plusMinusAverage_add1``, ``condition2``) so they are
  easy to find.
- **Type matters.** Arithmetic checks whether the plug is a scalar numeric type
  or a 2- or 3-component numeric compound and raises ``TypeError`` for anything
  else (strings, matrices, messages).
- **Old Maya, older nodes.** On Maya 2024 the ``subtract``, ``divide`` and
  ``power`` nodes do not exist; tik.maya uses ``floatMath`` from the
  ``lookdevKit`` plugin (loaded for you) and ``multiplyDivide`` instead. The
  graph you get differs slightly by version; the values do not.
- **Plugs outlive names.** A plug holds its node's wrapper plus the attribute
  name, so ``plug.path`` is recomputed from the node's current name every time.
