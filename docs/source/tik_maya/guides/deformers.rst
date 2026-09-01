Deformers and weights
=====================

:class:`~tik.maya.types.skincluster.SkinCluster` and
:class:`~tik.maya.types.blendshape.BlendShape` wrap the two deformers rigs
depend on most. Both inherit :class:`~tik.maya.core.deformer.Deformer`, which
adds weight import and export, and both hand weights back as a
:class:`~tik.maya.core.deformer.DeformerWeights` container you can do arithmetic
on.

SkinCluster
-----------

.. code-block:: python

   skin = tm.SkinCluster.create(geometry="body_geo", influences=joints, name="body_skin")
   skin = tm.resolve("skinCluster1")         # or wrap an existing one

   skin.influences                           # ['hip_jnt', 'spine_jnt', ...]
   skin.influence_count, skin.vertex_count
   skin.geometry, skin.original_geometry     # deformed shape and the orig shape
   skin.skinning_method = 1                  # 0 classic linear, 1 dual quaternion, 2 blended
   skin.max_influences = 4
   skin.normalize_weights = 1

   skin.add_influence("clavicle_jnt", weight=0.0, lock_weights=True)
   skin.remove_influence("clavicle_jnt")
   skin.lock_influence("hip_jnt", lock=True)
   skin.is_influence_locked("hip_jnt")
   skin.influence_index("spine_jnt")

   "hip_jnt" in skin, len(skin), list(skin)  # influences behave like a collection

``create`` with neither geometry nor influences makes an unconnected
``skinCluster`` node; with both it runs ``cmds.skinCluster`` with sensible
defaults (no ``toSelectedBones``, classic linear, normalised, four influences)
that any keyword overrides.

Weights
~~~~~~~

.. code-block:: python

   weights = skin.get_weights()                          # every influence, every vertex
   hip = skin.get_influence_weights("hip_jnt")           # one influence
   some = skin.get_vertex_weights([0, 1, 2])             # a few vertices

   skin.set_influence_weights("hip_jnt", hip * 0.5, normalize=True)
   skin.set_weights(weights)
   skin.set_vertex_weights([0, 1, 2], some)

   skin.get_blend_weights(), skin.set_blend_weights(values)   # dual-quaternion blend
   skin.prune_weights(threshold=0.001)
   skin.copy_weights(other_skin, surface_association="closestPoint",
                     influence_association="closestJoint")
   skin.mirror_weights(mirror_mode="YZ", mirror_inverse=False)
   skin.reset_weights(to_bind_pose=True)

   skin.go_to_bind_pose(), skin.bind_pose()
   skin.unbind(delete_history=True), skin.rebind()

Files
~~~~~

.. code-block:: python

   skin.save_weights("weights/body_skin.json")
   skin.load_weights("weights/body_skin.json", method="index")   # cmds.deformerWeights methods
   other = tm.SkinCluster.create_from_file("weights/body_skin.json")

``save_weights`` and ``load_weights`` go through ``cmds.deformerWeights``.
``create_from_file`` reads the JSON, creates a skinCluster on the shape named in
the file with the influences it lists, and applies the weights.

BlendShape
----------

.. code-block:: python

   bs = tm.BlendShape.create(geometry="face_geo", targets=["smile_geo", "frown_geo"], name="face_bs")

   bs.influences                    # target names
   bs.weight_count, bs.next_target
   bs.index_by_name("smile"), bs.name_by_index(0)

   bs.add_target("blink_geo", name="blink", weight=1.0)
   bs.add_inbetween("smile", "smile_half_geo", weight=0.5)

   bs.get_influence_weights("smile")            # per-vertex paint weights of one target
   bs.set_influence_weights("smile", weights)
   bs.get_base_weights(), bs.set_base_weights(weights)
   bs.save_weights(path), bs.load_weights(path)

DeformerWeights
---------------

A flat ``array.array('d')`` with a channel count and an element count, plus the
operators that make weight maths read like maths:

.. code-block:: python

   a = skin.get_influence_weights("hip_jnt")
   b = skin.get_influence_weights("spine_jnt")

   blended = (a + b) * 0.5
   inverted = 1.0 - a
   clamped = (a * 1.2).clamp(0.0, 1.0)
   normalised = skin.get_weights().normalize()

   a[10], len(a), list(a)                  # element access and iteration
   a.get_element_weights(10)               # every channel for one vertex
   a.get_channel_weights(0)                # every vertex for one channel
   a.to_list(), a.to_m_double_array()

Arithmetic works between two containers of matching shape, or between a
container and a number. Every operation returns a new container; ``copy()`` is
there when you want to be explicit.

WeightsIO
---------

The file model behind deformer JSON: shapes, sparse weight layers per influence,
a header. Useful when you want to read a weights file without a scene, or build
one.

.. code-block:: python

   from tik.maya.core.deformer import WeightsIO

   io = WeightsIO.load_json("weights/body_skin.json")
   io.influence_names
   io.shape("body_geoShape")
   io.dense_influence_weights("body_geoShape", "hip_jnt")   # array.array, one value per vertex
   io.to_deformer_weights()                                 # the whole thing as DeformerWeights
   io.save_json("weights/body_skin_v002.json")

``SkinCluster.create_from_weights_object(io)`` closes the loop from a
``WeightsIO`` back to a bound skin.
