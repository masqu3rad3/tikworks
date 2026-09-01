The code converter
==================

``tik.maya.utils.converter`` translates source code in both directions between
tik.maya and ``maya.cmds``. It works on the text of a script, by rewriting the
Python syntax tree with a set of rules, and it tells you what it could and could
not translate.

Two reasons you might want it:

- **Sharing a script with someone who does not have tik.maya.** Convert to
  ``cmds`` and send the result.
- **Moving an old ``cmds`` script towards tik.maya.** Convert to tik.maya, read
  the report, and clean up by hand what the rules did not cover.

tik.maya to cmds
----------------

.. code-block:: python

   from tik.maya.utils.converter import convert

   source = '''
   from tik.maya import Transform, Joint

   root = Transform.create(name="root_grp")
   jnt = Joint.create(name="hip")
   root.translate = (0, 5, 0)
   root["translateX"] >> jnt["translateX"]
   jnt["rotateX"].lock()
   '''

   report = convert(source)
   print(report.converted_code)
   print(report.summary())

The result carries the rewritten code plus one entry per rewrite:

.. code-block:: python

   report.rules_applied            # entries where a rule matched
   report.helpers_expanded         # method calls expanded into cmds sequences
   report.unsupported_operations   # what was left alone, and why
   report.warnings
   report.success_count, report.failure_count

Rules cover node creation (``Transform.create``, ``Joint.create``,
``Mesh.create``, ``Curve.create``, ``Locator.create``), plug access
(``.value``, ``.get()``, ``.set()``), connections (``.connect()`` and ``>>``),
transform properties, ``rename``/``delete``/``duplicate``/``select``,
``lock``/``unlock``, ``freeze`` and ``add_attr``. A registry of *blessed helper
expansions* turns tik.maya-only methods such as ``Mesh.unlock_normals`` into
their multi-line ``cmds`` or OpenMaya equivalents; methods with no honest
``cmds`` equivalent are reported as unsupported rather than guessed at.

The ``Converter`` class exposes the switches:

.. code-block:: python

   from tik.maya.utils.converter import Converter

   converter = Converter(add_imports=True, add_header=True, preserve_comments=True)
   report = converter.convert(source)

cmds to tik.maya
----------------

.. code-block:: python

   from tik.maya.utils.converter import convert_to_tik

   report = convert_to_tik('''
   import maya.cmds as cmds
   grp = cmds.createNode("transform", name="root_grp")
   cmds.setAttr(f"{grp}.translateX", 5)
   cmds.connectAttr(f"{grp}.translateX", "hip.translateX")
   ''')

Reverse rules lift ``createNode("transform")``, ``joint``, the polygon
primitives, ``curve`` and ``spaceLocator`` into ``create()`` calls;
``setAttr``/``getAttr``/``connectAttr`` into plug calls; and ``rename``,
``delete``, ``duplicate``, ``select``, ``addAttr`` and ``makeIdentity`` into
methods. Query commands whose meaning depends on context (``ls``,
``listRelatives`` and friends) are left in place and listed in the report with
the reason.

Limits
------

The converter is syntactic. It tracks which variables hold which tik.maya types
within a file, but it does not execute anything, so dynamic attribute names,
values computed at runtime and code paths it cannot see are passed through
untouched. Treat the output as a strong first draft and read the report.

``snippets/converter_examples.py`` in the repository walks through both
directions with printed results.
