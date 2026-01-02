tik.maya
========

Purpose
-------
A disciplined, boring wrapper around Autodesk Maya.

What lives here
---------------

- Node wrappers
- DAG traversal
- Attribute access
- Scene interaction
- OpenMaya integration
- Maya-specific abstractions

Rules
-----

- May depend on ``tik.core``
- Must not depend on Qt
- Must not depend on tools or UI
- Must mirror Maya behavior rather than reinterpret it
- Should remain predictable and mechanical

Mental model
------------

``How things exist *inside Maya*.`` If it does not make sense without Maya, it belongs here.

Three Pillars inside tik.maya
-----------------------------

.. code-block:: text

   ┌─────────────────────────────────────────────────────────────┐
   │                       Constructs                            │
   │          Orchestrate multiple nodes and roles               │
   │                (e.g., IK System, Space Switch)              │
   ├─────────────────────────────────────────────────────────────┤
   │                         Roles                               │
   │           What a node *means* semantically                  │
   │             (e.g., Controller, Driver)                      │
   ├─────────────────────────────────────────────────────────────┤
   │                         Types                               │
   │              What a node *is* in Maya                       │
   │          (e.g., Transform, Mesh, Joint)                     │
   └─────────────────────────────────────────────────────────────┘

Types
-----

**Types describe what a node *is*.** Location: ``tik/maya/types/``

A Type is a thin wrapper around a Maya node type. It maps 1:1 to Maya's node classification.

**Examples**

- :class:`~tik.maya.Transform` wraps ``transform`` nodes
- :class:`~tik.maya.Mesh` wraps ``mesh`` shape nodes
- :class:`~tik.maya.Joint` wraps ``joint`` nodes
- :class:`~tik.maya.Curve` wraps ``nurbsCurve`` shape nodes

**Rules for Types**

- Each Type maps to exactly one Maya node type
- Types are registered in the type registry via ``@register``
- Types expose low-level, structural behavior (transforms, attributes, geometry data)
- Types **never** encode semantic meaning

**A Type should answer**

- What attributes does this node have?
- How do I create this node?
- How do I query or manipulate its data?

**A Type should NOT answer**

- What is this node *used for*?
- What role does it play in a rig?
- Is this a controller or a driver?

.. code-block:: python

   from tik.maya import Transform, Joint, Mesh

   # Types tell you WHAT something is
   cube = Transform.create(name="cube")
   jnt = Joint.create(name="arm_jnt")

   # Types provide node-specific operations
   cube.freeze()           # Transform method
   cube.snap_to(target)    # Transform method
   mesh.vertices()         # Mesh method
   jnt.orient((0, 90, 0))  # Joint method

Roles
-----

**Roles describe what a node *means*.** Location: ``tik/maya/roles/``

A Role is a semantic overlay on top of an existing Type. It adds meaning and behavior without creating new Maya node types.

**Examples**

- ``Controller`` — A transform that an animator interacts with
- ``DeformerDriver`` — A joint that drives deformations
- ``SpaceSwitcher`` — A transform with space-switching capabilities

**Rules for Roles**

- Roles are **not** Maya node types
- Roles hold an existing Type instance internally (composition, not inheritance)
- Roles validate that they hold a compatible base Type
- Roles encode their identity in the scene (via attributes, metadata)
- Roles **never** create new Maya node kinds

**A Role should answer**

- What is this node's purpose in the rig?
- What high-level operations should this node support?

.. code-block:: python

   from tik.maya.roles.controller import Controller

   # A Controller is a Role that wraps a Transform
   ctrl = Controller.create(name="arm_ctrl", shape="circle")

   # The Role adds semantic behavior
   ctrl.set_shape("square", size=2.0)
   ctrl.set_color((1, 0, 0))  # Red

   # But you can still access the underlying Type
   ctrl.transform.translate = (0, 5, 0)

Identity recovery
^^^^^^^^^^^^^^^^^

Roles must be recoverable from the scene. If you save and reload, you should be able to identify which transforms are Controllers by checking for role markers.

.. code-block:: python

   # Check if a node is a Controller
   if Controller.is_controller(some_node):
       ctrl = Controller.from_node(some_node)

Constructs
----------

**Constructs orchestrate multiple nodes and roles.** Location: ``tik/maya/constructs/``

A Construct coordinates several nodes and roles to represent a pattern or setup. It's the "assembly" layer.

**Examples**

- IK Chain — Multiple joints + IK handle + pole vector
- Space Switch System — Transform + parent constraints + blend attributes
- Ribbon Setup — Surface + follicles + joints

**Rules for Constructs**

- Constructs manage collections of nodes and roles
- Constructs define relationships and connections
- Constructs may create and destroy nodes
- Constructs provide high-level operations on the whole system

.. note::
   The Constructs system is under development. As TikMaya matures, this will
   become the primary way to build complex rig systems.

Registry system
---------------

TikMaya uses a registry to map Maya node types to Python classes:

.. code-block:: python

   from tik.maya.core.registry import register, resolve

   @register("myCustomNode")
   class MyCustomNode(Node):
       pass

   # Now resolve() returns MyCustomNode for "myCustomNode" type nodes
   node = resolve("myCustomNode1")  # Returns MyCustomNode instance

The registry also handles inheritance. If no exact match exists, it walks the
Maya inheritance hierarchy to find the closest registered wrapper.
``resolve`` is re-exported in ``tik.maya.__init__`` so ``tik.maya.resolve``
and ``tm.resolve()`` (after ``import tik.maya as tm``) are equivalent.

Base classes
------------

**Node**
   Base wrapper for all Maya dependency nodes. Provides:

   - UUID-based identity tracking
   - Name caching and resolution
   - Attribute access via ``[]``
   - Lifecycle methods (``rename``, ``delete``, ``exists``)

**DagNode** (extends Node)
   For DAG-capable nodes. Adds:

   - ``parent`` / ``children`` hierarchy
   - ``visibility`` property
   - MDagPath integration

**ShapeNode** (extends DagNode)
   For shape nodes that live under transforms. Adds:

   - ``transform`` property (parent transform)
   - Smart initialization (accepts transform or shape name)

**Transform** (extends DagNode)
   For transform nodes. Adds:

   - ``translate``, ``rotate``, ``scale`` properties
   - ``shapes`` property
   - ``freeze()``, ``snap_to()`` methods
   - Matrix properties

**Type-specific classes** (Mesh, Curve, Joint, etc.)
   Extend the appropriate base with type-specific methods.

Design principles
-----------------

**Scene as Source of Truth**
   TikMaya never caches state that could become stale. It queries Maya when needed
   and uses UUIDs to maintain stable references.

**Explicit Over Implicit**
   Methods that modify scene state are clearly named as actions. Properties return
   current state without side effects.

**Consistency Across Types**
   All Types follow the same patterns:

   - ``create()`` class method for creation
   - ``[]`` for attribute access
   - Standard lifecycle methods

   This means learning one Type teaches you all of them.
