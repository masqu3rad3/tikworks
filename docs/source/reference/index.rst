API map
=======

The :doc:`generated reference </autoapi/index>` documents every module under
``src/python/tik`` from its docstrings. This page is the short way in: the
classes and functions the guides talk about, with a link to each.

tik.maya
--------

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Name
     - Page
   * - ``Node``, ``resolve()``
     - :mod:`tik.maya.core.node`, :mod:`tik.maya.core.registry`
   * - ``DagNode``, ``ShapeNode``
     - :mod:`tik.maya.core.dagnode`, :mod:`tik.maya.core.shapenode`
   * - ``Plug``
     - :mod:`tik.maya.core.plug`
   * - the ``cmds`` passthrough, ``create_node``, ``ls``, ``select``
     - :mod:`tik.maya.core.scene`, :mod:`tik.maya.core.constants`
   * - ``Transform``, ``Joint``, ``IkHandle``
     - :mod:`tik.maya.types.transform`, :mod:`tik.maya.types.joint`,
       :mod:`tik.maya.types.ikhandle`
   * - ``Mesh``, ``Curve``, ``Nurbs``, ``Locator``, ``Camera``, ``Light``
     - :mod:`tik.maya.types.mesh`, :mod:`tik.maya.types.curve`,
       :mod:`tik.maya.types.nurbs`, :mod:`tik.maya.types.locator`,
       :mod:`tik.maya.types.camera`, :mod:`tik.maya.types.light`
   * - ``SkinCluster``, ``BlendShape``, ``DeformerWeights``, ``WeightsIO``
     - :mod:`tik.maya.types.skincluster`, :mod:`tik.maya.types.blendshape`,
       :mod:`tik.maya.core.deformer`
   * - ``Controller``
     - :mod:`tik.maya.roles.controller`
   * - the constructs
     - :mod:`tik.maya.constructs.matrix_constraint`,
       :mod:`tik.maya.constructs.matrix_switch`,
       :mod:`tik.maya.constructs.space_switch`,
       :mod:`tik.maya.constructs.matrix_blend`,
       :mod:`tik.maya.constructs.measure`,
       :mod:`tik.maya.constructs.soft_ik`,
       :mod:`tik.maya.constructs.chain_lengths`,
       :mod:`tik.maya.constructs.aim_frame`,
       :mod:`tik.maya.constructs.angle_between`,
       :mod:`tik.maya.constructs.remap`,
       :mod:`tik.maya.constructs.matrix_spline`,
       :mod:`tik.maya.constructs.ribbon`,
       :mod:`tik.maya.constructs.panel`
   * - ``node.meta``, ``find_by_meta``
     - :mod:`tik.maya.core.meta`
   * - ``attribute`` and ``naming`` helpers, decorators
     - :mod:`tik.maya.core.attribute`, :mod:`tik.maya.core.naming`,
       :mod:`tik.maya.core.decorators`
   * - the shape library
     - :mod:`tik.maya.utils.control_shapes`
   * - the code converter
     - :mod:`tik.maya.utils.converter`

tik.trigger
-----------

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Name
     - Page
   * - ``Session``, ``ActionHandle``
     - :mod:`tik.trigger.session`
   * - ``Document``, ``ActionNode``
     - :mod:`tik.trigger.core.document`
   * - ``GuideDocument``, ``ModuleEntry``, ``GuideRecord``
     - :mod:`tik.trigger.core.guide_document`
   * - ``Module``, ``GuideLayout``, ``Input``, ``GuideAttr``
     - :mod:`tik.trigger.core.module`, :mod:`tik.trigger.core.manifest`
   * - ``Action``, ``ActionContext``
     - :mod:`tik.trigger.core.action`
   * - the registry and discovery
     - :mod:`tik.trigger.core.registry`, :mod:`tik.trigger.core.discovery`
   * - ``reconcile()``, ``GuideDiff``
     - :mod:`tik.trigger.core.reconcile`
   * - ``EventBus``, the exceptions
     - :mod:`tik.trigger.core.events`, :mod:`tik.trigger.core.exceptions`
   * - file versioning
     - :mod:`tik.trigger.core.versioning`
   * - ``GuideScene``, ``GuideHandle``
     - :mod:`tik.trigger.guides.scene`, :mod:`tik.trigger.guides.handle`
   * - ``.trg`` files
     - :mod:`tik.trigger.guides.format`
   * - ``ModuleRig``, ``GuideDraft``, ``Builder``, ``Runner``
     - :mod:`tik.trigger.maya.rig`, :mod:`tik.trigger.maya.build`,
       :mod:`tik.trigger.maya.runner`
   * - scene tags
     - :mod:`tik.trigger.maya.tags`
   * - the systems
     - :mod:`tik.trigger.systems.limb`, :mod:`tik.trigger.systems.limb_lock`,
       :mod:`tik.trigger.systems.reach`, :mod:`tik.trigger.systems.twist`
   * - the window
     - :mod:`tik.trigger.ui.main`, :mod:`tik.trigger.ui.designer.window`

Built-in modules and actions
----------------------------

Each built-in module and action lives in its own folder and has its own page:

.. toctree::
   :maxdepth: 1

   /autoapi/tik/trigger/modules/base/base/index
   /autoapi/tik/trigger/modules/fkchain/fkchain/index
   /autoapi/tik/trigger/modules/arm/arm/index
   /autoapi/tik/trigger/modules/twist/twist/index
   /autoapi/tik/trigger/modules/ribbon/ribbon/index
   /autoapi/tik/trigger/actions/import_asset/import_asset/index
   /autoapi/tik/trigger/actions/kinematics/kinematics/index
   /autoapi/tik/trigger/actions/reference/reference/index
   /autoapi/tik/trigger/actions/script/script/index

tik.core and tik.shared
-----------------------

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Name
     - Page
   * - the fields
     - :mod:`tik.core.fields`
   * - ``Color``, ``Side``
     - :mod:`tik.core.color`, :mod:`tik.core.side`
   * - ``FormBuilder``
     - :mod:`tik.shared.ui.fields`
   * - ``MayaToolWindow``, ``SceneWatcher``
     - :mod:`tik.shared.ui.maya_window`, :mod:`tik.shared.ui.scene_watcher`
   * - settings and JSON I/O
     - :mod:`tik.shared.user_settings`, :mod:`tik.shared.io`
