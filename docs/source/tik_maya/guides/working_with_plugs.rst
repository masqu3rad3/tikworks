Working with Plugs and Attributes
===================================

In tik.maya, **Plugs** are the gateway to working with node attributes. This guide covers everything from basic attribute access to advanced mathematical operations.

What is a Plug?
---------------

A **Plug** is tik.maya's wrapper around a Maya attribute. It provides a clean, Pythonic interface for reading values, setting values, managing connections, and building dependency graph networks.

.. code-block:: python

   import tik.maya as tm

   # Resolve a node
   cube = tm.resolve("pCube1")

   # Get a Plug for an attribute
   tx_plug = cube["translateX"]

   # The plug gives you access to the attribute's value and properties
   print(tx_plug.value)        # Read the value
   print(tx_plug.locked)       # Check if locked
   print(tx_plug.keyable)      # Check if keyable
   print(tx_plug.type)         # Get the attribute type

Every Plug instance represents a specific attribute on a specific node, tracked by the node's UUID. The Plug object remains valid even if the node is renamed.

Why Dictionary-Style Access?
-----------------------------

tik.maya uses **dictionary-style bracket notation** (``node["attr"]``) for accessing attributes instead of properties (``node.attr``). This design choice is intentional and provides significant advantages.

**Dictionary-Style Access is Superior Because:**

1. **Pythonic and Explicit**
   Using ``[]`` clearly signals attribute access, making code more readable and
   intentional. It follows Python's mapping protocol convention.

2. **Supports ALL Attributes**
   Maya allows user-created attributes with any valid name. Properties can't support
   every possible attribute name (e.g., attributes with special characters, reserved
   Python keywords, or dynamic runtime attributes).

3. **Consistency**
   Using the same syntax for both built-in and custom attributes ensures consistent
   code patterns. You don't need to remember which attributes have properties and
   which don't.

4. **Dynamic Access**
   You can use variables and computed strings to access attributes:

   .. code-block:: python

      # Access attributes dynamically
      for axis in ["X", "Y", "Z"]:
          node[f"translate{axis}"].value = 0.0

5. **No Naming Conflicts**
   Properties can conflict with Python methods or other class functionality.
   Dictionary-style access is isolated from the class interface.

.. tip::
   While tik.maya **does** provide convenience properties for common transform
   attributes (e.g., ``transform.translate_x``), the bracket notation is the
   **recommended approach** for all attribute access to maintain consistency
   and flexibility.

Accessing Attributes
--------------------

Basic Access
~~~~~~~~~~~~

Use bracket notation to get a Plug for any attribute:

.. code-block:: python

   import tik.maya as tm

   cube = tm.resolve("pCube1")

   # Single-value attributes
   tx = cube["translateX"]
   ry = cube["rotateY"]
   sx = cube["scaleZ"]

   # Compound attributes (vectors)
   translate = cube["translate"]
   rotate = cube["rotate"]
   scale = cube["scale"]

   # Custom attributes
   my_attr = cube["customAttribute"]

Child Attributes
~~~~~~~~~~~~~~~~

For compound attributes, you can access child components in two ways:

.. code-block:: python

   # Method 1: Direct child access
   tx = cube["translateX"]
   ty = cube["translateY"]
   tz = cube["translateZ"]

   # Method 2: Parent then child
   translate = cube["translate"]
   tx = translate["translateX"]
   # Or use the shorter child name
   tx = translate["X"]

Nested compound attributes work the same way:

.. code-block:: python

   # Access nested attributes
   world_matrix = cube["worldMatrix"]
   first_element = world_matrix[0]  # For array attributes

Reading and Writing Values
---------------------------

The ``value`` Property
~~~~~~~~~~~~~~~~~~~~~~

The simplest way to read and write attribute values is the ``value`` property:

.. code-block:: python

   import tik.maya as tm

   cube = tm.resolve("pCube1")

   # Read a value
   current_x = cube["translateX"].value
   print(current_x)  # 0.0

   # Write a value
   cube["translateX"].value = 10.0

   # Works with compound attributes
   cube["translate"].value = (5.0, 10.0, 15.0)

   # Read compound values
   pos = cube["translate"].value
   print(pos)  # [(5.0, 10.0, 15.0)]

Explicit Methods
~~~~~~~~~~~~~~~~

You can also use the ``get()`` and ``set()`` methods for more control:

.. code-block:: python

   # Get with additional arguments
   value = cube["translateX"].get()

   # Set with type specification
   cube["myStringAttr"].set("Hello", type="string")

   # Set matrix values
   identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
   cube["offsetParentMatrix"].set(identity, type="matrix")

Attribute Properties
--------------------

Plugs provide several properties for managing attribute behavior in the Maya UI:

Locked State
~~~~~~~~~~~~

.. code-block:: python

   # Check if locked
   is_locked = cube["translateX"].locked

   # Lock an attribute
   cube["translateX"].locked = True
   # Or use the method
   cube["translateX"].lock()

   # Unlock an attribute
   cube["translateX"].locked = False
   # Or use the method
   cube["translateX"].unlock()

Keyable State
~~~~~~~~~~~~~

.. code-block:: python

   # Check if keyable
   is_keyable = cube["translateX"].keyable

   # Make keyable
   cube["translateX"].keyable = True

   # Make non-keyable (but visible in channel box)
   cube["translateX"].keyable = False

Visibility
~~~~~~~~~~

.. code-block:: python

   # Check visibility in channel box
   is_visible = cube["translateX"].visible

   # Hide from channel box
   cube["translateX"].visible = False

   # Show in channel box
   cube["translateX"].visible = True

Attribute Type
~~~~~~~~~~~~~~

.. code-block:: python

   # Get the attribute type
   attr_type = cube["translateX"].type
   print(attr_type)  # 'kDoubleLinearAttribute'

Attribute Path
~~~~~~~~~~~~~~

.. code-block:: python

   # Get the full Maya path
   path = cube["translateX"].path
   print(path)  # 'pCube1.translateX'

   # Get just the attribute name
   name = cube["translateX"].attr
   print(name)  # 'translateX'

   # Get the node
   node = cube["translateX"].node
   print(node.name)  # 'pCube1'

Connecting Attributes
---------------------

tik.maya provides three operators for managing attribute connections.

The Connect Operator (>>)
~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``>>`` operator creates a connection from one attribute to another:

.. code-block:: python

   import tik.maya as tm

   locator = tm.Locator.create(name="driver")
   cube = tm.Transform.create(name="driven")

   # Connect locator position to cube position
   locator.transform["translate"] >> cube["translate"]

   # Connect individual components
   locator.transform["translateX"] >> cube["translateX"]

The ``>>`` operator returns the right-hand side, enabling chaining:

.. code-block:: python

   # Chain multiple connections
   a["output"] >> b["input"] >> c["input"]

   # This is equivalent to:
   a["output"] >> b["input"]
   b["input"] >> c["input"]

The Reverse Connect Operator (<<)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``<<`` operator works in reverse—it connects the right side to the left:

.. code-block:: python

   # These are equivalent:
   cube["tx"] << locator.transform["tx"]
   locator.transform["tx"] >> cube["tx"]

The Disconnect Operator (//)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``//`` operator disconnects two attributes:

.. code-block:: python

   # Create a connection
   locator.transform["tx"] >> cube["tx"]

   # Break the connection
   locator.transform["tx"] // cube["tx"]

Explicit Connection Methods
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You can also use explicit methods:

.. code-block:: python

   # Connect
   locator.transform["translate"].connect(cube["translate"], force=True)

   # Disconnect from a specific plug
   locator.transform["translate"].disconnect(cube["translate"])

   # Disconnect from source (whatever is connected)
   cube["translate"].disconnect()

Querying Connections
~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Get the input connection (source)
   source = cube["translateX"].get_input(plug=True)
   if source:
       print(f"Connected from: {source.path}")

   # List all input connections
   inputs = cube["translate"].list_inputs(plugs=True)

   # List all output connections
   outputs = locator.transform["translate"].list_outputs(plugs=True)

Mathematical Operations
-----------------------

The **Plug** class provides powerful mathematical operators that create
dependency graph nodes to perform calculations on attribute values. This allows you to
build procedural networks using natural Python syntax instead of manually creating and
connecting utility nodes.

.. note::
   All arithmetic operations create **dependency graph nodes** (e.g., ``addDL``,
   ``multiplyDivide``, ``plusMinusAverage``). The connections are permanent until
   manually removed. These operations do not evaluate to Python values but return
   new Plug objects representing the output of the created node.

Basic Mathematical Operators
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The Plug class supports all standard Python mathematical operators. These operators
work with both **single-value attributes** (float, int, time, angle) and **compound
attributes** (double3, float3, such as translate, rotate, scale).

Addition (+)
^^^^^^^^^^^^

The addition operator creates dependency nodes to sum attribute values.

**Single-Value Addition:**

.. code-block:: python

   import tik.maya as tm

   # Create test nodes
   node_a = tm.Transform.create(name="nodeA")
   node_b = tm.Transform.create(name="nodeB")

   # Set values
   node_a["tx"].value = 10.0
   node_b["tx"].value = 5.0

   # Add two plugs - creates an addDL (addDoubleLinear) node
   result_plug = node_a["tx"] + node_b["tx"]
   print(result_plug.value)  # 15.0

   # Add a plug and a numeric value
   result_plug = node_a["tx"] + 8
   print(result_plug.value)  # 18.0

   # Reversed addition (numeric first)
   result_plug = 5 + node_a["tx"]
   print(result_plug.value)  # 15.0

**Compound (Vector) Addition:**

.. code-block:: python

   # Add two vector attributes - creates a plusMinusAverage node
   node_a["translate"].value = (1.0, 2.0, 3.0)
   node_b["translate"].value = (4.0, 5.0, 6.0)

   result_plug = node_a["translate"] + node_b["translate"]
   print(result_plug.value)  # [(5.0, 7.0, 9.0)]

   # Add a scalar to all components
   result_plug = node_a["translate"] + 10.0
   print(result_plug.value)  # [(11.0, 12.0, 13.0)]

   # Add a tuple to a vector
   result_plug = node_a["translate"] + (1.0, 2.0, 3.0)
   print(result_plug.value)  # [(2.0, 4.0, 6.0)]

Subtraction (-)
^^^^^^^^^^^^^^^

The subtraction operator creates nodes for subtracting attribute values.

**Single-Value Subtraction:**

.. code-block:: python

   node_a["tx"].value = 10.0
   node_b["tx"].value = 3.0

   # Subtract - creates a subtract node
   result_plug = node_a["tx"] - node_b["tx"]
   print(result_plug.value)  # 7.0

   # Subtract a numeric value
   result_plug = node_a["tx"] - 4
   print(result_plug.value)  # 6.0

   # Reversed subtraction
   result_plug = 20 - node_a["tx"]
   print(result_plug.value)  # 10.0

**Compound (Vector) Subtraction:**

.. code-block:: python

   node_a["translate"].value = (10.0, 20.0, 30.0)
   node_b["translate"].value = (1.0, 2.0, 3.0)

   # Subtract vectors - creates a plusMinusAverage node with subtract operation
   result_plug = node_a["translate"] - node_b["translate"]
   print(result_plug.value)  # [(9.0, 18.0, 27.0)]

Multiplication (*)
^^^^^^^^^^^^^^^^^^

The multiplication operator creates nodes for multiplying attribute values.

**Single-Value Multiplication:**

.. code-block:: python

   node_a["tx"].value = 4.0
   node_b["tx"].value = 3.0

   # Multiply - creates a multDL (multDoubleLinear) node
   result_plug = node_a["tx"] * node_b["tx"]
   print(result_plug.value)  # 12.0

   # Multiply by a scalar
   result_plug = node_a["tx"] * 2.5
   print(result_plug.value)  # 10.0

   # Reversed multiplication
   result_plug = 3 * node_a["tx"]
   print(result_plug.value)  # 12.0

**Compound (Vector) Multiplication:**

.. code-block:: python

   node_a["translate"].value = (2.0, 3.0, 4.0)
   node_b["translate"].value = (5.0, 6.0, 7.0)

   # Multiply vectors component-wise - creates a multiplyDivide node
   result_plug = node_a["translate"] * node_b["translate"]
   print(result_plug.value)  # [(10.0, 18.0, 28.0)]

   # Scale by a scalar
   result_plug = node_a["translate"] * 2.0
   print(result_plug.value)  # [(4.0, 6.0, 8.0)]

Division (/)
^^^^^^^^^^^^

The division operator creates nodes for dividing attribute values.

**Single-Value Division:**

.. code-block:: python

   node_a["tx"].value = 10.0
   node_b["tx"].value = 2.0

   # Divide - creates a divide node
   result_plug = node_a["tx"] / node_b["tx"]
   print(result_plug.value)  # 5.0

   # Divide by a scalar
   result_plug = node_a["tx"] / 4
   print(result_plug.value)  # 2.5

   # Reversed division
   result_plug = 20 / node_a["tx"]
   print(result_plug.value)  # 2.0

**Compound (Vector) Division:**

.. code-block:: python

   node_a["translate"].value = (10.0, 20.0, 30.0)
   node_b["translate"].value = (2.0, 4.0, 5.0)

   # Divide vectors component-wise - creates a multiplyDivide node
   result_plug = node_a["translate"] / node_b["translate"]
   print(result_plug.value)  # [(5.0, 5.0, 6.0)]

Power (**)
^^^^^^^^^^

The power operator raises attribute values to an exponent.

**Single-Value Power:**

.. code-block:: python

   node_a["tx"].value = 2.0
   node_b["tx"].value = 3.0

   # Power - creates a power node
   result_plug = node_a["tx"] ** node_b["tx"]
   print(result_plug.value)  # 8.0

   # Raise to a numeric power
   result_plug = node_a["tx"] ** 4
   print(result_plug.value)  # 16.0

   # Reversed power
   result_plug = 2 ** node_a["tx"]  # 2 raised to the plug value
   print(result_plug.value)  # 4.0

**Compound (Vector) Power:**

.. code-block:: python

   node_a["translate"].value = (2.0, 3.0, 4.0)

   # Power operation on each component - creates a multiplyDivide node
   result_plug = node_a["translate"] ** 2
   print(result_plug.value)  # [(4.0, 9.0, 16.0)]

Modulo (%)
^^^^^^^^^^

The modulo operator computes the remainder of division. **Only supports single values**.

.. code-block:: python

   node_a["tx"].value = 10.0
   node_b["tx"].value = 3.0

   # Modulo - creates a modulo node
   result_plug = node_a["tx"] % node_b["tx"]
   print(result_plug.value)  # 1.0

   # Modulo by a scalar
   node_a["tx"].value = 17.0
   result_plug = node_a["tx"] % 5
   print(result_plug.value)  # 2.0

   # Reversed modulo
   result_plug = 10 % node_a["tx"]
   print(result_plug.value)  # 2.0

Chained Operations
------------------

Python's operator precedence applies naturally, allowing complex expressions.
Each operation creates a node, and the result can be used in subsequent operations.

Simple Chaining
~~~~~~~~~~~~~~~

.. code-block:: python

   import tik.maya as tm

   node_a = tm.Transform.create(name="nodeA")
   node_b = tm.Transform.create(name="nodeB")
   node_c = tm.Transform.create(name="nodeC")

   node_a["tx"].value = 10.0
   node_b["tx"].value = 5.0
   node_c["tx"].value = 2.0

   # Operator precedence: multiplication before addition
   # Result: 10 + (5 * 2) = 20
   result_plug = node_a["tx"] + node_b["tx"] * 2.0
   print(result_plug.value)  # 20.0

   # Division before subtraction
   # Result: 20 - (10 / 2) = 15
   result_plug = node_a["tx"] - node_b["tx"] / 2.0
   print(result_plug.value)  # 15.0

Using Parentheses
~~~~~~~~~~~~~~~~~

Use parentheses to control evaluation order:

.. code-block:: python

   node_a["tx"].value = 4.0
   node_b["tx"].value = 2.0

   # Without parentheses: 4 + 2 * 3 = 4 + 6 = 10
   result_a = node_a["tx"] + node_b["tx"] * 3
   print(result_a.value)  # 10.0

   # With parentheses: (4 + 2) * 3 = 6 * 3 = 18
   result_b = (node_a["tx"] + node_b["tx"]) * 3
   print(result_b.value)  # 18.0

Complex Expressions
~~~~~~~~~~~~~~~~~~~

Build sophisticated dependency networks with multiple operations:

.. code-block:: python

   node_a["tx"].value = 4.0
   node_b["tx"].value = 2.0
   node_c["tx"].value = 3.0

   # Complex expression: (4 + 2) * 3 - 6 / 2 = 6 * 3 - 3 = 15
   result_plug = (node_a["tx"] + node_b["tx"]) * node_c["tx"] - 6 / node_b["tx"]
   print(result_plug.value)  # 15.0

Chaining with Connection Operator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Combine arithmetic operations with the connection operator (``>>``) to pipe results
directly to target attributes:

.. code-block:: python

   # Create nodes
   driver_a = tm.Transform.create(name="driverA")
   driver_b = tm.Transform.create(name="driverB")
   target = tm.Transform.create(name="target")

   driver_a["tx"].value = 10.0
   driver_b["tx"].value = 5.0

   # Chain arithmetic and connection: 10 + 5 * 2.5 = 22.5, then connect
   driver_a["tx"] + driver_b["tx"] * 2.5 >> target["tz"]

   print(target["tz"].value)  # 22.5

   # Update driver values to see the network update
   driver_a["tx"].value = 20.0
   print(target["tz"].value)  # 32.5

Vector Arithmetic
~~~~~~~~~~~~~~~~~

Chained operations work with compound attributes too:

.. code-block:: python

   node_a = tm.Transform.create(name="nodeA")
   node_b = tm.Transform.create(name="nodeB")
   target = tm.Transform.create(name="target")

   node_a["translate"].value = (1.0, 2.0, 3.0)
   node_b["translate"].value = (4.0, 5.0, 6.0)

   # Average two positions and scale by 2
   ((node_a["translate"] + node_b["translate"]) / 2.0) * 2.0 >> target["translate"]

   print(target["translate"].value)  # [(5.0, 7.0, 9.0)]

Advanced Examples
-----------------

Oscillation with Time
~~~~~~~~~~~~~~~~~~~~~

Combine arithmetic with time-based animation:

.. code-block:: python

   import tik.maya as tm

   # Create a time node to drive animation
   time_node = tm.create_node("time")

   # Create targets
   oscillator = tm.Transform.create(name="oscillator")

   # Scale time and add offset
   # translateX = (time * 0.1) + 5
   time_node["outTime"] * 0.1 + 5 >> oscillator["tx"]

Normalized Distance
~~~~~~~~~~~~~~~~~~~

Create a procedural rig element that responds to another object's position:

.. code-block:: python

   # Create locators
   driver = tm.Locator.create(name="driver")
   follower = tm.Locator.create(name="follower")
   indicator = tm.Locator.create(name="indicator")

   # Access transforms
   driver_xform = driver.transform
   follower_xform = follower.transform

   # Set positions
   driver_xform["translate"].value = (0, 0, 0)
   follower_xform["translate"].value = (10, 0, 0)

   # Scale follower X position by 0.5 and drive indicator
   follower_xform["tx"] * 0.5 >> indicator.transform["ty"]

Blend Between Transforms
~~~~~~~~~~~~~~~~~~~~~~~~~

Create a weighted blend between two transform positions:

.. code-block:: python

   # Create transforms
   source_a = tm.Transform.create(name="sourceA")
   source_b = tm.Transform.create(name="sourceB")
   blend_target = tm.Transform.create(name="blendTarget")
   weight_ctrl = tm.Transform.create(name="weightCtrl")

   # Set positions
   source_a["translate"].value = (0, 0, 0)
   source_b["translate"].value = (10, 10, 10)
   weight_ctrl["tx"].value = 0.5  # 50% blend

   # Create blend: A * (1 - weight) + B * weight
   # For TX = 0.5: (0 * 0.5) + (10 * 0.5) = 5
   (
       source_a["translate"] * (1.0 - weight_ctrl["tx"])
       + source_b["translate"] * weight_ctrl["tx"]
   ) >> blend_target["translate"]

   print(blend_target["translate"].value)  # [(5.0, 5.0, 5.0)]

   # Adjust weight
   weight_ctrl["tx"].value = 0.8
   print(blend_target["translate"].value)  # [(8.0, 8.0, 8.0)]

Scale Compensation
~~~~~~~~~~~~~~~~~~

Automatically compensate for parent scale in a rig:

.. code-block:: python

   # Create hierarchy
   parent = tm.Transform.create(name="parent")
   child = tm.Transform.create(name="child")
   compensated = tm.Transform.create(name="compensated")

   child.parent = parent
   compensated.parent = child

   # Set parent scale
   parent["scale"].value = (2.0, 2.0, 2.0)

   # Compensate by inverse scale
   # If parent scale is 2, child scale should be 0.5 to maintain world size
   1.0 / parent["scale"] >> compensated["scale"]

   print(compensated["scale"].value)  # [(0.5, 0.5, 0.5)]

Multi-Node Dependency Chain
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Build complex rigging logic with multiple interdependent nodes:

.. code-block:: python

   # Create control hierarchy
   main_ctrl = tm.Transform.create(name="main_ctrl")
   offset_ctrl = tm.Transform.create(name="offset_ctrl")
   detail_ctrl = tm.Transform.create(name="detail_ctrl")

   # Create driven joints
   joint_a = tm.Joint.create(name="joint_a")
   joint_b = tm.Joint.create(name="joint_b")
   joint_c = tm.Joint.create(name="joint_c")

   # Set initial values
   main_ctrl["tx"].value = 10.0
   offset_ctrl["ty"].value = 5.0
   detail_ctrl["tz"].value = 2.0

   # Complex dependency: combine multiple controls with different weights
   # Joint A gets main + half of offset
   main_ctrl["tx"] + offset_ctrl["ty"] * 0.5 >> joint_a["tx"]

   # Joint B gets accumulated value scaled
   (main_ctrl["tx"] + offset_ctrl["ty"] + detail_ctrl["tz"]) * 0.5 >> joint_b["ty"]

   # Joint C gets weighted difference
   (main_ctrl["tx"] - detail_ctrl["tz"] * 2.0) >> joint_c["tz"]

   print(joint_a["tx"].value)  # 12.5
   print(joint_b["ty"].value)  # 8.5
   print(joint_c["tz"].value)  # 6.0

Performance Considerations
--------------------------

**Node Creation**
   Each arithmetic operation creates a new Maya dependency graph node. For complex
   expressions with many operations, this can result in a significant number of nodes.
   This is normal and expected behavior.

**Evaluation Order**
   The dependency graph evaluates nodes in the correct order automatically. You don't
   need to worry about evaluation sequence - Maya handles it.

**Clean Scene**
   If you create temporary mathematical relationships for testing, remember to delete
   the generated nodes when no longer needed.

Common Patterns
---------------

Attribute Mirroring
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   left_ctrl = tm.Transform.create(name="L_arm_ctrl")
   right_ctrl = tm.Transform.create(name="R_arm_ctrl")

   # Mirror X translation (negate X)
   left_ctrl["tx"] * -1.0 >> right_ctrl["tx"]

Distance-Based Scaling
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Create distance node manually or use arithmetic to approximate
   driver = tm.Transform.create(name="driver")
   target = tm.Transform.create(name="target")

   driver["tx"].value = 5.0

   # Simple distance-to-scale relationship
   driver["tx"] / 10.0 >> target["sy"]

Offset Animation
~~~~~~~~~~~~~~~~

.. code-block:: python

   base_anim = tm.Transform.create(name="base")
   offset_anim = tm.Transform.create(name="offset")

   base_anim["rx"].value = 45.0

   # Add a constant offset to rotation
   base_anim["rx"] + 15.0 >> offset_anim["rx"]
   print(offset_anim["rx"].value)  # 60.0

Summary
-------

The Plug class provides a comprehensive interface for working with Maya attributes:

- **Pythonic Access**: Use dictionary-style notation (``node["attr"]``) for consistency
- **Read/Write**: Simple ``value`` property for getting and setting values
- **Properties**: Manage locked, keyable, visible, and type states
- **Connections**: Use ``>>``, ``<<``, and ``//`` operators for clean connection syntax
- **Child Access**: Navigate compound attributes naturally
- **Mathematical Operations**: Build dependency networks with standard Python operators
- **Chainable**: Combine multiple operations in a single expression
- **Type-Aware**: Works with both single values and compound (vector) attributes

For complete API details, see :class:`~tik.maya.core.plug.Plug`.

.. seealso::

   - :doc:`working_with_nodes` - Understanding node wrappers
   - :doc:`../quickstart` - Basic tik.maya usage
   - :doc:`../overview` - Core tik.maya concepts
