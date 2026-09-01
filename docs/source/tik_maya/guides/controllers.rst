Controllers and the shape library
=================================

A controller is a transform an animator grabs. In Maya terms that is nothing
special: a transform with NURBS curve shapes under it and a colour override. What
makes it a *controller* is intent, and intent is what a **role** captures.
:class:`~tik.maya.roles.controller.Controller` is the one role tik.maya ships.

.. figure:: /_static/screenshots/maya_controller_shapes.png
   :class: screenshot
   :alt: Several controllers with library shapes and colour overrides

   Controllers built from library shapes, each with a colour override.

Roles wrap types
----------------

A ``Controller`` *holds* a ``Transform``; it does not inherit from it. This is
deliberate: a controller is not a new kind of Maya node, and the scene must be
able to tell you afterwards which transforms were meant as controllers.

.. code-block:: python

   from tik.maya.roles.controller import Controller

   ctrl = Controller.create("arm_ctrl", shape="Circle", size=2.0, color=17)
   ctrl.transform                     # the Transform underneath
   ctrl.transform.translate = (0, 10, 0)

   Controller.is_controller("arm_ctrl")     # True: tagged with an isController attribute
   again = Controller.from_node("arm_ctrl") # wrap an existing, tagged controller
   Controller("some_transform")             # wrap without checking the tag

``create`` makes the transform (extra keywords go to ``Transform.create``, so
``parent=`` works), tags it, adds the shape, applies the colour and hides the
history attribute from the channel box.

Reads pass through, writes do not
---------------------------------

Anything you *read* from a controller that it does not define itself is read from
its transform, plugs included:

.. code-block:: python

   ctrl.long_name               # the transform's
   ctrl["tx"].value             # the transform's plug
   ctrl.world_position          # works: a read

Assignments and type-checked APIs need the transform explicitly:

.. code-block:: python

   ctrl.transform.world_position = (1, 2, 3)      # not ctrl.world_position = ...
   ctrl.transform.snap_to(joint)                  # snap_to checks isinstance(target, Transform)
   tm.MatrixConstraint.create(ctrl, joint)        # constructs accept a Controller as *driver*

Shapes
------

.. code-block:: python

   ctrl.set_shape("CubePin", size=1.5)        # replace all shapes with a library shape
   ctrl.replace_shape("Arrow", size=1.5)      # swap while keeping the current placement
   ctrl.add_shape(curve_data, size=1.0)       # append one curve from raw data
   ctrl.clear_shapes()
   ctrl.shapes                                # [<Curve ...>, ...]

``set_shape`` accepts a library name or a dict of curve data
(``{"curves": [{"point": [...], "degree": 3, "periodic": False, "knot": [...]}]}``).
``replace_shape`` builds a temporary controller with the new shape, snaps it onto
the old one and transfers the CV positions, so a controller that has already been
positioned in a rig can change shape in place.

Colour
------

.. code-block:: python

   ctrl.color = 6                      # index colour
   ctrl.color = (0.2, 0.6, 1.0)        # RGB
   ctrl.color = tm_color               # a tik.core.color.Color
   ctrl.color                          # what is set, or None
   ctrl.get_color(as_color=True)       # RGB overrides as a Color object

The shape library
-----------------

Shapes are JSON files, one per shape, with a PNG thumbnail beside each. The
library ships nine categories:

.. list-table::
   :widths: 18 82

   * - basics
     - Circle, CurvedCircle, Cube, CurvedRectangle, Cylinder, Diamond, HalfDome,
       Ngon, Pyramid, Sphere, Square, Triangle
   * - pins
     - CubePin, Lollipop, PickPin, PyramidPin, SpherePin
   * - arrows
     - Arrow, BracketArrow, CircularArrow, CurvedArrow, DirectionalCircle,
       DottedArrow, DualCurvedArrow, Enter, Rotator, TriCircle, TriangleArrow,
       TriangleDualArrow, Uturn
   * - panels
     - Cog, Compass, Looper, Settings
   * - symbols
     - Checked, Drop, Plus, Refresh, Star, Unavailable
   * - anatomy
     - Arachnid, CartoonyFace, ClawPrint, Eye, FootPrint, Lungs, PawPrint
   * - letters, numbers
     - A to Z, Zero to Nine

.. container:: shape-gallery

   .. figure:: /_static/shapes/Circle.png

      Circle

   .. figure:: /_static/shapes/Cube.png

      Cube

   .. figure:: /_static/shapes/Diamond.png

      Diamond

   .. figure:: /_static/shapes/Sphere.png

      Sphere

   .. figure:: /_static/shapes/CubePin.png

      CubePin

   .. figure:: /_static/shapes/Lollipop.png

      Lollipop

   .. figure:: /_static/shapes/Arrow.png

      Arrow

   .. figure:: /_static/shapes/Rotator.png

      Rotator

   .. figure:: /_static/shapes/Cog.png

      Cog

   .. figure:: /_static/shapes/Star.png

      Star

   .. figure:: /_static/shapes/Eye.png

      Eye

   .. figure:: /_static/shapes/A.png

      A

Names are looked up across several folders, later ones overriding earlier ones:

1. the shipped shapes in ``tik/maya/data/control_shapes``,
2. your own in ``~/TikWorks/user_control_shapes`` (created on first use),
3. any folders listed in the ``TIKMAYA_SHAPES_PATH`` environment variable,
4. folders added at runtime with ``add_path``.

.. code-block:: python

   from tik.maya.utils.control_shapes import ControlShapeLibrary, capture_to_disk

   library = ControlShapeLibrary.get_instance()
   library.list_shapes()                 # every name the library can resolve
   library.get_path("Cog")               # the JSON file it would load
   library.add_path("/studio/shapes")    # more shapes, highest priority
   library.refresh()

Adding your own shape is one call from a curve transform you drew:

.. code-block:: python

   capture_to_disk("myCurve", name="Claw", category="custom", normalize=True, thumbnail=True)

``normalize`` scales the CVs into a unit box so ``size=1.0`` means the same
thing for every shape; ``thumbnail`` renders the PNG from a temporary panel. The
``tik.tools.polish`` shape browser is a Qt front end for exactly this library.
