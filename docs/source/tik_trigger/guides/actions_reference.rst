Built-in actions
================

An action is one step of a session's pipeline. Four ship with tik.trigger. Their
``category`` decides which shelf group and palette section they appear in:
``build`` for the two that produce the rig, ``structure`` for the two that shape
the pipeline itself.

import_asset
------------

*Import Model*, category ``build``. Brings a file into the build scene.

.. list-table::
   :header-rows: 1
   :widths: 20 22 12 46

   * - Field
     - Type
     - Default
     - Meaning
   * - ``file_path``
     - file (``.ma`` ``.mb`` ``.fbx`` ``.obj`` ``.abc`` ``.usd``)
     - ``""``
     - The file to import. Relative paths resolve against the session's folder.
   * - ``namespace``
     - string
     - ``""``
     - Optional namespace for the imported nodes.
   * - ``reference``
     - bool
     - ``False``
     - Create a Maya file reference instead of importing.

``run`` fails with a readable error when the file does not exist; ``validate``
reports the same before any build starts.

kinematics
----------

*Kinematics*, category ``build``. Builds every module from guides, or only the
ones under the given roots.

.. list-table::
   :header-rows: 1
   :widths: 22 20 12 46

   * - Field
     - Type
     - Default
     - Meaning
   * - ``guides_file``
     - file (``.trg``)
     - ``""``
     - **Leave empty to build this session's own guides.** Set a path to build a
       shared guide library instead.
   * - ``rig_name``
     - string
     - ``"trigger"``
     - Name of the rig root group (``<rig_name>_rig``) every module hangs under.
   * - ``guide_roots`` *(Build Options)*
     - list of names
     - ``[]``
     - Root guide names to build; everything parented under them is included.
       Empty means all.
   * - ``after_build`` *(Build Options)*
     - ``keep`` / ``hide`` / ``delete``
     - ``delete``
     - What happens to the guides once the rig is built. Anything but ``keep``
       is recorded as deliberate, so the next sync does not redraw them.

With ``guides_file`` empty the action clears the scene's guide rendering, redraws
the session's own guide document, and builds from that: no separate file, no
version skew between the file and the session. It raises if the session holds no
guides and no file is set.

reference
---------

*Reference*, category ``structure``. Runs the actions of another ``.tr`` as part
of this session. Ticking, unticking or editing a referenced action stores an
override here; the referenced file is never modified.

.. list-table::
   :header-rows: 1
   :widths: 20 22 14 44

   * - Field
     - Type
     - Default
     - Meaning
   * - ``file``
     - file (``.tr``)
     - ``""``
     - The session to reference.
   * - ``version``
     - string
     - ``"latest"``
     - ``latest``, ``pinned`` or an explicit ``v###``. Decides which file on disk
       is expanded when the name is versioned.
   * - ``include`` *(Scope)*
     - list of paths
     - ``[]``
     - Action paths to include; empty means all.
   * - ``overrides``
     - dict, hidden
     - ``{}``
     - ``{action path: {enabled: bool, settings: {...}}}``. Written by the UI
       and by ``ActionHandle`` when you edit a linked row; you never type it.

The action itself does nothing when run. The runner expands it into the
referenced document's steps, each with the referenced session's folder as its
``base_dir`` so relative paths keep resolving where they were authored.
References can nest; a cycle is reported as a planning problem.

script
------

*Script*, category ``structure``. Runs Python from a file, inline text, or both,
with ``ctx`` (the :class:`~tik.trigger.core.action.ActionContext`) in scope.

.. list-table::
   :header-rows: 1
   :widths: 20 16 12 52

   * - Field
     - Type
     - Default
     - Meaning
   * - ``file_path``
     - string
     - ``""``
     - A ``.py`` file to execute first. A relative path resolves against the
       session's folder.
   * - ``code``
     - string
     - ``""``
     - Inline code, executed after the file.

.. code-block:: python

   rig.add("script", "report", code="ctx.log(f'running {ctx.path} from {ctx.base_dir}')")

Inside the script, ``ctx.session`` is the running :class:`~tik.trigger.session.Session`,
so a script can read other actions' settings or the guide document.

.. seealso::

   :doc:`writing_actions` for the ``Action`` base class, the lifecycle and the
   context object.
