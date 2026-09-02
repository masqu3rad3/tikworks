Metadata, attributes, naming and decorators
===========================================

The small things that keep coming up in rig code, collected in one place. All of
them live in ``tik.maya.core`` and most are re-exported from ``tik.maya``.

Metadata on nodes: ``node.meta``
--------------------------------

Every wrapper has a ``meta`` mapping. Each key becomes a hidden string attribute
``tikMeta_<key>`` holding JSON, so you can hang typed data on any node without
inventing node types, and it survives renames because it is attribute based.

.. code-block:: python

   jnt.meta["kind"] = "guide"
   jnt.meta["settings"] = {"segments": 3, "stretch": True}
   jnt.meta["kind"]                  # 'guide'
   jnt.meta.get("missing", None)
   "kind" in jnt.meta                # True
   jnt.meta.keys(), jnt.meta.items(), jnt.meta.as_dict()
   jnt.meta.update({"side": "L", "index": 2})
   del jnt.meta["index"]
   jnt.meta.clear()

Values round-trip through JSON: strings, numbers, booleans, lists and dicts of
those. Keys must be valid identifiers.

Find nodes by their metadata with :func:`~tik.maya.core.meta.find_by_meta`:

.. code-block:: python

   tm.find_by_meta("kind", "guide")                     # every node with kind == "guide"
   tm.find_by_meta("kind", "guide", node_type="joint")  # joints only
   tm.find_by_meta("kind")                              # anything that has the key at all

tik.trigger's scene tags (``trg_kind``, ``trg_instance``, ``trg_role`` ...) are
exactly this mechanism. ``as_dict()`` reads every key with one ``listAttr`` and
one ``getAttr`` per key, so prefer it when you need several values.

Creating attributes: ``plug.create()``
--------------------------------------

An attribute *is* a :class:`~tik.maya.core.plug.Plug`, so indexing a node with a
name that does not exist yet gives you the handle to create it. ``create()``
takes a friendly type name, returns the plug, and gets the ``addAttr`` flags
right -- including ``keyable=True``, which ``cmds.addAttr`` leaves off.

.. code-block:: python

   stretch = ctrl["stretch"].create("float", default=1.0, min=0.0, max=2.0)
   ctrl["soft"].create("float", default=0.0, min=0.0, soft_max=10.0)
   ctrl["segments"].create("int", default=3, min=1)
   ctrl["showPole"].create("bool", default=True)
   ctrl["space"].create("enum", items=["world", "chest", "root"], default=0)
   ctrl["notes"].create("string", default="rev 2")

   other_ctrl["stretch"].create(proxy=stretch)   # a proxy of 'stretch' elsewhere

The type names are ``float``, ``int``, ``bool``, ``enum``, ``angle``,
``distance``, ``time``, ``string`` and ``matrix``. Alongside ``default``,
``min``, ``max``, ``soft_min``, ``soft_max`` and ``items``, any raw
``cmds.addAttr`` flag is forwarded untouched, so nothing is out of reach::

   node["custom"].create(attributeType="double3")

``soft_min`` and ``soft_max`` set the slider range without capping the value;
an animator can still type past them, up to ``min`` and ``max``.

Locking and hiding
------------------

State lives on the plug, so there is no separate helper. ``TRANSFORM_CHANNELS``
(the nine transform channels) and ``ALL_CHANNELS`` (those plus ``v``) are
exported from ``tik.maya``.

.. code-block:: python

   for channel in ("sx", "sy", "sz", "v"):
       plug = ctrl[channel]
       plug.locked = True
       plug.visible = False

   for channel in tm.ALL_CHANNELS:      # everything an animator could grab
       ctrl[channel].locked = True

   stretch >> upper["sx"]               # one source into many targets
   stretch >> lower["sx"]

Naming: ``tm.naming``
---------------------

Only the mechanics: uniqueness and token joining. Conventions (what a side token
looks like, which suffix a joint takes) belong to whoever calls these.

.. code-block:: python

   from tik.maya import naming

   naming.unique_name("arm")            # 'arm', or 'arm1' if 'arm' exists, 'arm2'...
   naming.unique_name("arm01")          # respects padding: 'arm02'
   naming.format_name("upArm", 0, suffix="jnt", side="L")   # 'L_upArm_0_jnt'
   naming.format_name("root", prefix="body", suffix="grp")  # 'body_root_grp'

Empty tokens and ``None`` are skipped, integers are accepted.

Decorators
----------

.. code-block:: python

   from tik.maya.core.decorators import undo, keepselection

   @undo
   def build_arm():
       ...        # every cmds call inside is one undo step

   @keepselection
   def make_shapes():
       ...        # the user's selection is restored afterwards

``undo`` opens and closes an undo chunk around the call. ``keepselection``
records the selection before and restores it after, for functions that have to
select things to do their work. Both are what the constructs use internally.

.. note::

   API-level edits in tik.maya (node creation through ``MDagModifier``,
   reparenting, renaming) are undoable too. They register with the vendored
   ``apiundo`` bridge, so a mix of API and ``cmds`` calls still undoes as you
   would expect.

Colours: ``tik.core.color.Color``
---------------------------------

A pure-Python colour value that every ``color`` property in tik.maya accepts.

.. code-block:: python

   from tik.core.color import Color

   red = Color("red")                 # by name (22 CSS-style names)
   teal = Color("#008080")            # hex
   custom = Color((0.2, 0.6, 1.0))    # RGB floats
   custom.rgb, custom.rgb255, custom.hex, custom.hsv
   custom.set_hsv(v=0.5)              # darken
   Color.random(mode=Color.RANDOM_PASTEL, seed=7)
   ctrl.color = red

Sides: ``tik.core.side.Side``
-----------------------------

.. code-block:: python

   from tik.core.side import Side

   Side.from_value("left")            # Side.LEFT  (also 'L', 'l', 'Left')
   Side.LEFT.mirror                   # Side.RIGHT; CENTER mirrors to itself
   Side.RIGHT.multiplier              # -1, else 1
   str(Side.LEFT)                     # 'L'

``Side`` is a ``str`` enum, so it compares equal to its letter and serialises
cleanly. tik.trigger uses it for every module's side.

Benchmarks
----------

.. code-block:: python

   from tik.maya.core.benchmark import MayaBenchmark

   bench = MayaBenchmark()
   bench.measure("build", iterations=20, new_scene=True).run(build_function)
   bench.compare()

``MayaBenchmark`` disables undo and the viewport while it runs, and can start
each iteration from a new scene. The comparison snippets under
``snippets/comparisons`` use it to time ``cmds`` against tik.maya.
