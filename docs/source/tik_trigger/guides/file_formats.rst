File formats
============

Two file types, both JSON, both readable in a text editor.

``.tr``: the session
--------------------

Schema version 5. The whole rig: the action pipeline and the guide document.

.. code-block:: json

   {
     "schema": 5,
     "meta": {
       "author": "arda",
       "created_at": "2026-09-01T10:12:00",
       "modified_at": "2026-09-01T11:40:32",
       "session_id": "3f9a1c0e8b6d4e7fa2c5d1b0e9f8a7c6"
     },
     "actions": [
       {"name": "import_model", "type": "import_asset", "enabled": true,
        "settings": {"file_path": "geo/hero_v02.ma", "namespace": "", "reference": false},
        "children": []},
       {"name": "build_rig", "type": "kinematics", "enabled": true,
        "settings": {"guides_file": "", "rig_name": "hero", "after_build": "delete"},
        "children": []}
     ],
     "guides": {
       "schema": 1,
       "modules": [
         {"instance_id": "…", "module_type": "base", "name": "body", "side": "C",
          "settings": {"controller_size": 10.0},
          "inputs": {},
          "guides": [{"role": "root", "index": 0, "position": [0, 0, 0], "rotation": [0, 0, 0],
                      "rotate_order": 0, "joint_orient": null, "radius": null, "color": null,
                      "attrs": {}, "parent": null}]},
         {"instance_id": "…", "module_type": "arm", "name": "arm", "side": "L",
          "settings": {"stretch": true, "squash": true},
          "inputs": {"root": "<body's instance_id>.root"},
          "guides": ["…"]}
       ],
       "scene_groups": [{"group_id": "props", "name": "props", "nodes": ["prop_ctrl"]}],
       "positions": {"<instance_id>": [120.0, 40.0]},
       "collapse": {"<instance_id>": 2}
     }
   }

Points worth knowing when you read one:

- **Actions nest.** ``children`` is the same structure again. Paths in the API
  (``import_model/fix``) are these names joined with ``/``.
- **Missing settings take the class default.** Fields are written out when an
  action or module is added; a field the class gained later is simply absent
  from older files and filled from its default at load time, so adding a field
  never breaks an old file.
- **Connections are UUIDs.** ``inputs`` sources are ``"<instance_id>.<output>"``
  or a bare scene node name. Display keys (``L_arm``) never appear in the file.
- **`null` means never authored.** A guide's ``radius``, ``color``,
  ``joint_orient``, ``position`` or ``rotation`` set to ``null`` means the
  module's own ``draw_guides`` decides; see :doc:`guides_and_lockstep`.
- **Paths are relative to the file** wherever the author left them relative.
  Moving a session together with its ``geo`` folder keeps it working.
- **Versioning is by name.** ``hero_v002.tr`` is version 2 of ``hero``;
  ``Session.save(increment=True)`` writes ``hero_v003.tr``. The ``reference``
  action's ``version`` field (``latest``, ``pinned``, ``v###``) resolves against
  that convention.

Overrides on a reference live in the referencing session, inside the reference
action's own settings:

.. code-block:: json

   {"name": "baseRig", "type": "reference",
    "settings": {"file": "rigs/baseRig.tr", "version": "latest",
                 "overrides": {"scripts/head_rotation": {"enabled": false},
                               "kinematics": {"settings": {"rig_name": "hero"}}}}}

``.trg``: a guide library
-------------------------

An import/export format for guides, one joint record per guide joint. It is
what *File → Export Guides…* writes and what the ``kinematics`` action reads when
its ``guides_file`` is set.

.. code-block:: json

   {
     "joints": [
       {"name": "L_arm_collar_guide", "position": [2.0, 0.0, 0.0], "rotation": [0, 0, 0],
        "joint_orient": [0, 0, 0], "parent": "body_root_guide", "side": "L",
        "color": 6, "radius": 1.5,
        "module": "arm", "role": "collar", "index": 0, "instance": "<uuid>",
        "settings": {"stretch": true}, "module_name": "arm", "attrs": {}},
       {"name": "L_arm_shoulder_guide", "…": "…", "role": "shoulder", "parent": "L_arm_collar_guide"}
     ],
     "connections": [
       {"input": "L_arm.root", "source": "body.root"}
     ],
     "meta": {},
     "designer": {
       "scene_nodes": {"props": ["prop_ctrl"]},
       "positions": {"L_arm": [120.0, 40.0]},
       "collapse": {"L_arm": 2}
     }
   }

- Each record carries its transform plus ``module``, ``role``, ``index`` and
  ``instance``. The **root record** of an instance also carries the module's
  ``settings`` and its ``module_name``.
- Records without a ``module``/``role`` pair belong to no registered module.
  They are collected in ``GuideFile.unknown`` and reported, not silently dropped.
- **Connections use display keys** here, unlike the ``.tr``, because a library
  is meant to be read by people and merged into sessions that have their own
  UUIDs. Import mints fresh ids and rewires the connections in a second pass.
- ``designer`` is optional graph layout, keyed by display key, merged on import.

Working with the files from Python
----------------------------------

.. code-block:: python

   from tik.trigger.core import Document
   from tik.trigger.guides.format import GuideFile

   document = Document.load("rigs/hero.tr")
   document.paths()                       # ['import_model', 'build_rig', ...]
   document.guides.modules[0].key         # 'body'
   document.save("rigs/hero_copy.tr")

   library = GuideFile.load("guides/hero.trg")
   library.root_names()                   # ['body_root_guide', 'L_arm_collar_guide', ...]
   library.instances()                    # [GuideInstance, ...] grouped per module
   library.unknown                        # records no registered module claims

``Document`` is pure Python and needs no Maya; it is the class the
:class:`~tik.trigger.session.Session` wraps.
