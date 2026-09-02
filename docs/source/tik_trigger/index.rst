tik.trigger
===========

``tik.trigger`` is the rigging framework of TikWorks. Where tik.maya knows how
to wire a matrix constraint, tik.trigger knows what an arm is: that it has a
collar, that the IK control mirrors in world space, that ``stretch`` is a
checkbox an animator may argue about. You describe a rig as a set of connected
modules, place their guides, and build.

.. figure:: /_static/screenshots/trigger_window_designer.png
   :class: screenshot
   :alt: The Trigger window on the Guide Designer sub-tab

   The Trigger window. A session tab, its Guide Designer sub-tab, a body with two
   arms, a tail, a twist and a ribbon connected in the graph.

The one-paragraph version
-------------------------

A rig is a **session**, saved as a ``.tr`` file. The session holds two things:
an ordered, nestable list of **actions** (import the model, build the rig, run a
script) and the rig's **guides**: which modules exist, how they connect, where
their guide joints sit. Pressing *Build* resets the Maya scene and runs the
actions in order; the ``kinematics`` action turns the guides into modules and
connects them. The session is the truth. The Maya scene is a working copy of
one session at a time, and the guide joints in it are a rendering the session
owns and can redraw.

.. warning::

   tik.trigger is under active development. These pages match the code in
   ``src/python/tik/trigger`` as of this build; both can still change.

Where to start
--------------

.. grid:: 1 1 2 2
   :gutter: 3

   .. grid-item-card:: Concepts
      :link: concepts
      :link-type: doc

      Five ideas carry the framework. Read this once and the rest is detail.

   .. grid-item-card:: Quickstart
      :link: quickstart
      :link-type: doc

      A body, two arms and a build, from the UI and from Python.

   .. grid-item-card:: The Trigger window
      :link: guides/trigger_window
      :link-type: doc

      Sessions, the pipeline, references, menus and shortcuts.

   .. grid-item-card:: The Guide Designer
      :link: guides/guide_designer
      :link-type: doc

      Modules, the tree, the node graph, sync and snapshot.

   .. grid-item-card:: Built-in modules and actions
      :link: guides/modules_reference
      :link-type: doc

      What ``base``, ``fkchain``, ``arm``, ``twist`` and ``ribbon`` build, and
      every setting they take.

   .. grid-item-card:: Write your own
      :link: guides/writing_modules
      :link-type: doc

      A module is a declaration plus two methods. An action is fields plus
      ``run()``.

What is in the package
----------------------

.. list-table::
   :header-rows: 1
   :widths: 24 76

   * - Sub-package
     - Contents
   * - ``tik.trigger.core``
     - Pure Python, no Maya, no Qt. The session document, the guide document,
       the ``Module`` and ``Action`` base classes, the manifest pieces
       (``GuideLayout``, ``Input``, ``GuideAttr``), the registry, reconcile,
       discovery and file versioning. The import boundary is enforced by a
       test.
   * - ``tik.trigger.guides``
     - The guides in the Maya scene: ``GuideScene`` and ``GuideHandle``, the
       joint primitives, capture, regenerate, snapshot, the checkout stamp and
       the ``.trg`` exchange format.
   * - ``tik.trigger.maya``
     - Building: ``ModuleRig`` and ``GuideDraft`` (what modules build and draw
       through), the ``Builder``, the action ``Runner``, scene tags and the
       scene observer.
   * - ``tik.trigger.systems``
     - Shared rig sub-assemblies that create controllers and name animator
       attributes: ``limb`` (IK/FK), ``limb_lock``, ``reach`` (auto-collar),
       ``twist`` (twist extraction).
   * - ``tik.trigger.modules``
     - ``base``, ``fkchain``, ``arm``, ``twist``, ``ribbon``.
   * - ``tik.trigger.actions``
     - ``import_asset``, ``kinematics``, ``reference``, ``script``.
   * - ``tik.trigger.session``
     - ``Session`` and ``ActionHandle``, the API a TD scripts against.
   * - ``tik.trigger.ui``
     - The Qt tool: the Trigger window, the pipeline view, the Guide Designer
       and its node graph.

Importing is cheap
------------------

``import tik.trigger`` does not import Maya. The Maya-touching names are resolved
on first use, so the pure parts can be imported and tested anywhere:

.. code-block:: python

   import tik.trigger as trigger

   trigger.Module            # available at once (pure core)
   trigger.load_plugins()    # imports the built-in modules and actions so they register
   trigger.list_modules()    # ['arm', 'base', 'fkchain', 'ribbon', 'twist']
   trigger.list_actions()    # ['import_asset', 'kinematics', 'reference', 'script']

   trigger.Session           # imports tik.trigger.session on first access
   trigger.GuideScene        # imports tik.trigger.guides on first access

Modules and actions are found by folder: ``modules/<name>/<name>.py`` with a
``@register_module`` or ``@register_action`` decorator inside. Dropping a folder
in is how a third-party pack is installed.
