Cheat sheet
===========

You know the ``cmds`` spelling; here is the tik.maya one. ``tm`` is
``import tik.maya as tm`` throughout, and ``node`` is any wrapper.

Nodes
-----

.. list-table::
   :class: compare
   :header-rows: 1
   :widths: 50 50

   * - ``maya.cmds``
     - ``tik.maya``
   * - ``cmds.createNode("transform", name="grp")``
     - ``tm.Transform.create(name="grp")``
   * - ``cmds.joint(name="jnt")``
     - ``tm.Joint.create(name="jnt", parent=grp)``
   * - ``cmds.spaceLocator(name="loc")[0]``
     - ``tm.Locator.create(name="loc").transform``
   * - ``cmds.polySphere(name="ball")[0]``
     - ``tm.Mesh.create("polySphere", name="ball").transform``
   * - ``cmds.createNode("multiplyDivide")``
     - ``tm.create_node("multiplyDivide")``
   * - ``cmds.objExists("grp")``
     - ``node.exists()``
   * - ``cmds.rename("grp", "new")``
     - ``node.rename("new")``
   * - ``cmds.delete("grp")``
     - ``node.delete()``
   * - ``cmds.duplicate("grp")[0]``
     - ``node.duplicate()``
   * - ``cmds.nodeType("grp")``
     - ``node.type``
   * - ``cmds.ls("grp", uuid=True)[0]``
     - ``node.uuid``
   * - ``cmds.ls(type="joint")``
     - ``tm.ls(type="joint")``
   * - ``cmds.select("a", "b")``
     - ``tm.select(a, b)`` or ``a.select()``

Attributes
----------

.. list-table::
   :class: compare
   :header-rows: 1
   :widths: 50 50

   * - ``maya.cmds``
     - ``tik.maya``
   * - ``cmds.getAttr("n.translateX")``
     - ``node["translateX"].value``
   * - ``cmds.setAttr("n.translateX", 5)``
     - ``node["translateX"].value = 5``
   * - ``cmds.getAttr("n.translate")[0]``
     - ``node.translate`` (an ``MVector``)
   * - ``cmds.setAttr("n.translate", 1, 2, 3)``
     - ``node.translate = (1, 2, 3)``
   * - ``cmds.setAttr("n.tx", lock=True)``
     - ``node["tx"].locked = True``
   * - ``cmds.setAttr("n.tx", keyable=False, channelBox=False)``
     - ``node["tx"].visible = False``
   * - lock and hide scale
     - ``tm.attribute.lock_and_hide(node, ["sx", "sy", "sz"])``
   * - ``cmds.addAttr("n", ln="stretch", at="double", dv=1, k=True)``
     - ``tm.attribute.add_float(node, "stretch", default=1.0)``
   * - ``cmds.addAttr("n", ln="space", at="enum", en="a:b")``
     - ``tm.attribute.add_enum(node, "space", ["a", "b"])``
   * - ``cmds.attributeQuery("x", node="n", exists=True)``
     - ``node.has_attr("x")``
   * - ``cmds.deleteAttr("n.x")``
     - ``node.delete_attr("x")``

Connections
-----------

.. list-table::
   :class: compare
   :header-rows: 1
   :widths: 50 50

   * - ``maya.cmds``
     - ``tik.maya``
   * - ``cmds.connectAttr("a.tx", "b.tx", force=True)``
     - ``a["tx"] >> b["tx"]``
   * - ``cmds.disconnectAttr("a.tx", "b.tx")``
     - ``a["tx"] // b["tx"]``
   * - ``cmds.listConnections("b.tx", s=True, d=False, p=True)[0]``
     - ``b["tx"].get_input(plug=True)``
   * - ``cmds.listConnections("a.tx", s=False, d=True, p=True)``
     - ``a["tx"].list_outputs(plugs=True)``
   * - a ``multDoubleLinear`` and an ``addDoubleLinear``, wired
     - ``(a["tx"] * 2 + 5) >> b["ty"]``
   * - a ``condition`` node set to greater-than
     - ``a["tx"].gt(0, 1, 0)``
   * - two ``condition`` nodes for a clamp
     - ``a["tx"].clamped(0, 1)``

Hierarchy and transforms
------------------------

.. list-table::
   :class: compare
   :header-rows: 1
   :widths: 50 50

   * - ``maya.cmds``
     - ``tik.maya``
   * - ``cmds.listRelatives("n", parent=True)[0]``
     - ``node.parent``
   * - ``cmds.parent("child", "parent")``
     - ``child.parent = parent``
   * - ``cmds.parent("child", world=True)``
     - ``child.parent = None``
   * - ``cmds.listRelatives("n", children=True)``
     - ``node.children``
   * - ``cmds.listRelatives("n", shapes=True)``
     - ``node.shapes``
   * - ``cmds.listRelatives("n", allDescendents=True, type="joint")``
     - ``node.collect_hierarchy(node_types=["joint"])``
   * - ``cmds.xform("n", q=True, ws=True, rp=True)``
     - ``node.world_position``
   * - ``cmds.xform("n", ws=True, t=(1, 2, 3))``
     - ``node.world_position = (1, 2, 3)``
   * - ``cmds.getAttr("n.worldMatrix[0]")``
     - ``node.world_matrix`` (an ``MMatrix``)
   * - ``cmds.matchTransform("n", "target")``
     - ``node.snap_to(target)``
   * - ``cmds.delete(cmds.aimConstraint("t", "n", ...))``
     - ``node.aim_at(target)``
   * - ``cmds.makeIdentity("n", apply=True, t=1, r=1, s=1)``
     - ``node.freeze()``
   * - an offset group above a control
     - ``ctrl.create_offset_group()``
   * - ``cmds.setAttr("n.overrideEnabled", 1); ... overrideColor``
     - ``node.color = 17`` or ``node.color = (1, 0.5, 0)``

Joints
------

.. list-table::
   :class: compare
   :header-rows: 1
   :widths: 50 50

   * - ``maya.cmds``
     - ``tik.maya``
   * - a loop of ``cmds.joint(p=...)`` calls
     - ``tm.Joint.chain(positions, name_pattern="arm_{index}")``
   * - ``cmds.joint("j", e=True, oj="xyz", sao="yup", zso=True)``
     - ``tm.Joint.orient_chain(joints)``
   * - ``cmds.mirrorJoint("j", mirrorYZ=True, mirrorBehavior=True, sr=("L_", "R_"))``
     - ``joint.mirror("x", search="L_", replace="R_")``
   * - ``cmds.ikHandle(sj="a", ee="c", sol="ikRPsolver")[0]``
     - ``tm.IkHandle.create(a, c)``
   * - ``cmds.poleVectorConstraint("pole", "handle")``
     - ``handle.pole_vector(pole)``
   * - ``cmds.getAttr("j.jointOrient")[0]``
     - ``joint.joint_orient``

Rig networks
------------

.. list-table::
   :class: compare
   :header-rows: 1
   :widths: 50 50

   * - You used to build
     - Now
   * - ``multMatrix`` + ``decomposeMatrix`` into a node
     - ``tm.MatrixConstraint.create(driver, driven)``
   * - an enum, an offset group, a ``blendMatrix`` and conditions
     - ``tm.SpaceSwitch.create(ctrl, [a, b], labels=["a", "b"])``
   * - a ``distanceBetween`` and a divide for stretch
     - ``tm.Measure.create(a, b).ratio_plug()``
   * - an exponential soft-IK network
     - ``tm.SoftIk.create(root, goal, total_length)``
   * - a ribbon with follicles
     - ``tm.Ribbon.create(start, end, name="arm", joint_count=5)``
   * - a controller curve with a colour override
     - ``Controller.create("arm_ctrl", shape="Circle", color=17)``

Metadata
--------

.. list-table::
   :class: compare
   :header-rows: 1
   :widths: 50 50

   * - ``maya.cmds``
     - ``tik.maya``
   * - ``addAttr(dt="string")`` + ``setAttr(json.dumps(...))``
     - ``node.meta["settings"] = {...}``
   * - ``cmds.ls("*.myTag", o=True)``
     - ``tm.find_by_meta("myTag", value)``
