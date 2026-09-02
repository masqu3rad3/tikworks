Shapes: meshes, curves, surfaces, locators, cameras, lights
============================================================

Shape wrappers are :class:`~tik.maya.core.shapenode.ShapeNode` subclasses. They
wrap the *shape* node, hand you the parent through ``.transform``, and accept a
transform name on construction if that is what you have.

.. code-block:: python

   mesh = tm.resolve("pCubeShape1")     # Mesh
   mesh.transform                       # <Transform 'pCube1'>
   tm.Mesh("pCube1")                    # also Mesh: given the transform, takes its first shape

   cube.shapes                          # from the transform side: [<Mesh 'pCubeShape1'>]

Creating shapes
---------------

Geometry classes take the Maya command that produces the geometry as their first
argument; the remaining keywords go to that command.

.. code-block:: python

   ball = tm.Mesh.create("polySphere", name="ball", radius=2, subdivisionsAxis=16)
   strip = tm.Nurbs.create("nurbsPlane", name="strip", lengthRatio=4, patchesV=4)
   line = tm.Curve.create(point=[(0, 0, 0), (0, 5, 0)], degree=1, name="line")
   loc = tm.Locator.create(name="aim")
   cam = tm.Camera.create(name="shotCam")
   key = tm.Light.create("spotLight", name="key")

``Mesh.create`` accepts the polygon primitives (``polyCube``, ``polySphere``,
``polyPlane``, ``polyCylinder``, ``polyCone``, ``polyTorus``) or ``"mesh"`` for
an empty shape node; ``Nurbs.create`` accepts ``nurbsPlane``, ``sphere``,
``cylinder``, ``cone``, ``torus`` or ``"nurbsSurface"``. Anything else raises
``ValueError`` listing the choices. Everything returns the shape wrapper, so
position the result through ``.transform``:

.. code-block:: python

   ball.transform.translate = (0, 5, 0)

Mesh
----

.. code-block:: python

   points = mesh.vertices(space="world")           # OpenMaya.MPointArray
   near = mesh.vertices_in_radius((0, 0, 0), radius=1.0)   # [vertex indices]

   mesh.unlock_normals(soften=True)                # unlock, then smooth every edge
   mesh.set_vertex_colors((1, 0, 0))               # every vertex red, displayColors on
   mesh.set_vertex_colors(tm_color, indices=near)  # a subset, or a tik.core Color
   mesh.get_vertex_colors()                        # MColorArray or None

``vertices`` and the colour methods go through ``MFnMesh``, so they are fast
enough for whole-mesh operations.

Curve and Nurbs
---------------

.. code-block:: python

   curve.cvs(space="object")          # MPointArray
   curve.line_width = 2.0             # display width
   curve.scale_points(1.5)            # scale CVs about the object origin ...
   curve.scale_points(1.5, pivot="center")           # ... or the bounding-box centre
   curve.scale_points(1.5, pivot="custom", pivot_point=(0, 1, 0))

   surface.cvs(space="world")

``scale_points`` edits CV positions in place, which is how controller shapes get
resized without touching the transform's scale.

Locator
-------

Nothing beyond ``ShapeNode``: ``loc.transform`` is where you move it.

Camera
------

.. code-block:: python

   cam.lens = 50.0                    # focalLength
   cam.fit("horizontal")              # filmFit: fill / horizontal / vertical / overscan
   cam.set_controls("cameraAndAim")   # camera / cameraAndAim / cameraAimAndUp
   cam.aim, cam.up                    # the aim and up locators of an aim camera, or None
   cam.delete()                       # also removes the lookAt parent of an aim camera

Light
-----

``Light.create(light_type, **kwargs)`` runs ``cmds.createNode`` for the given
light type (``pointLight``, ``directionalLight``, ``spotLight``, ``areaLight``,
``ambientLight``...). Any light node resolves to ``Light``: the registry walks
Maya's inheritance chain up to ``light``.

Display colour
--------------

Every DAG node, shapes included, has ``color``:

.. code-block:: python

   mesh.color = 13                    # index
   mesh.color = (0.9, 0.2, 0.2)       # RGB override
   mesh.color = None                  # override off
   mesh.get_color(as_color=True)      # a tik.core.color.Color for RGB overrides

The :doc:`Controller <controllers>` role exposes the same property as
``ctrl.color``; it sets the override on the controller's transform, which the
curve shapes under it inherit.
