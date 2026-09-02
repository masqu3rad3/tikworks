TikWorks
========

TikWorks is a set of Python tools for Autodesk Maya, written by a rigger for
riggers. It has two halves that you can use independently:

- **tik.maya** wraps ``maya.cmds`` and OpenMaya in objects that survive renames,
  connect with ``>>`` and do arithmetic with ``+`` and ``*``. If you write Maya
  scripts, start here.
- **tik.trigger** is a modular rigging framework built on top of it. You place
  guides, connect modules, and press *Build*. If you build rigs, start here.

.. code-block:: python

   import tik.maya as tm

   driver = tm.Transform.create(name="driver")
   follower = tm.Transform.create(name="follower")

   driver["translate"] >> follower["translate"]          # a connection
   (driver["rx"] * 0.5 + 10) >> follower["ry"]           # a small node network

   driver.rename("hip_ctrl")
   driver.translate_y = 12                               # the wrapper still points at it

Everything on these pages is checked against the code in ``src/python/tik``. Where
a picture needs a live Maya viewport, you will see a labelled placeholder until a
real capture replaces it.

.. warning::

   TikWorks is under active development. ``tik.maya`` is stable enough to build
   on; ``tik.trigger`` is a working framework whose API can still change between
   commits.

Where to go
-----------

.. grid:: 1 1 2 2
   :gutter: 3

   .. grid-item-card:: Install and check the import
      :link: getting_started/installation
      :link-type: doc

      Maya 2024 or newer, Python 3.10 or newer, one path on ``sys.path``.

   .. grid-item-card:: Ten minutes with tik.maya
      :link: tik_maya/quickstart
      :link-type: doc

      Wrap a node, set a value, connect two attributes, build a math network.

   .. grid-item-card:: Build a rig with tik.trigger
      :link: tik_trigger/quickstart
      :link-type: doc

      A session, a few modules, a build. From the UI or from Python.

   .. grid-item-card:: How the packages fit together
      :link: architecture/overview
      :link-type: doc

      The layer rules, and the one question that decides where code goes.

The layers, in one picture
--------------------------

Each package depends only on the ones below it. The arrows never point up.

.. code-block:: text

   tik.tools      user-facing tools                 (polish: controller shapes)
      │
   tik.trigger    rigging framework                 (guides, modules, sessions, the UI)
      │
   tik.shared     Qt widgets, settings, JSON I/O    (used by tools and trigger)
      │
   tik.maya       the Maya wrapper                  (nodes, plugs, types, roles, constructs)
      │
   tik.core       pure Python                       (fields, Color, Side, B-spline maths)

The split between the two big packages follows one rule, quoted throughout this
documentation as the *animator-opinion rule*: if an animator could have an
opinion about it, it belongs to tik.trigger. tik.maya knows how to wire a matrix
constraint; tik.trigger knows that an arm has a collar.

.. toctree::
   :hidden:
   :caption: Getting started

   getting_started/installation

.. toctree::
   :hidden:
   :caption: tik.maya

   tik_maya/index
   tik_maya/why_tik_maya
   tik_maya/quickstart
   tik_maya/guides/nodes
   tik_maya/guides/plugs
   tik_maya/guides/transforms_and_joints
   tik_maya/guides/shapes
   tik_maya/guides/controllers
   tik_maya/guides/constructs
   tik_maya/guides/deformers
   tik_maya/guides/metadata_and_helpers
   tik_maya/guides/converter
   tik_maya/cheatsheet

.. toctree::
   :hidden:
   :caption: tik.trigger

   tik_trigger/index
   tik_trigger/concepts
   tik_trigger/quickstart
   tik_trigger/guides/trigger_window
   tik_trigger/guides/guide_designer
   tik_trigger/guides/sessions_and_actions
   tik_trigger/guides/guides_and_lockstep
   tik_trigger/guides/modules_reference
   tik_trigger/guides/actions_reference
   tik_trigger/guides/writing_modules
   tik_trigger/guides/writing_actions
   tik_trigger/guides/file_formats

.. toctree::
   :hidden:
   :caption: Architecture

   architecture/overview
   architecture/packages

.. toctree::
   :hidden:
   :caption: Contributing

   contributing/style_guide
   contributing/testing
   contributing/documentation

.. toctree::
   :hidden:
   :caption: Reference

   reference/index
   autoapi/index
