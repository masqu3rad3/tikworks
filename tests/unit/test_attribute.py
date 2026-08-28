"""Tests for tik.maya.core.attribute helpers."""

from maya import cmds

import tik.maya as tm
from tik.maya.core import attribute as attr


def test_add_separator_is_locked_and_visible():
    node = tm.Transform.create(name="node")
    plug = attr.add_separator(node, "settings")
    assert plug.exists()
    assert cmds.getAttr(plug.path, lock=True)
    assert cmds.getAttr(plug.path, channelBox=True)
    assert not cmds.getAttr(plug.path, keyable=True)


def test_add_float_with_limits():
    node = tm.Transform.create(name="node")
    plug = attr.add_float(node, "stretch", default=1.0, min=0.0, max=2.0)
    assert plug.value == 1.0
    assert cmds.attributeQuery("stretch", node=node.name, minimum=True) == [0.0]
    assert cmds.attributeQuery("stretch", node=node.name, maximum=True) == [2.0]
    assert cmds.getAttr(plug.path, keyable=True)


def test_add_bool_int_enum_string():
    node = tm.Transform.create(name="node")
    assert attr.add_bool(node, "flag", default=True).value is True
    assert attr.add_int(node, "count", default=4).value == 4
    enum_plug = attr.add_enum(node, "space", ["world", "local"], default=1)
    assert enum_plug.value == 1
    assert cmds.attributeQuery("space", node=node.name, listEnum=True) == [
        "world:local"
    ]
    assert attr.add_string(node, "label", default="hi").value == "hi"


def test_lock_and_hide_defaults_and_unlock():
    node = tm.Transform.create(name="node")
    attr.lock_and_hide(node)
    assert cmds.getAttr(f"{node.name}.tx", lock=True)
    assert not cmds.getAttr(f"{node.name}.tx", keyable=True)
    assert cmds.getAttr(f"{node.name}.v", lock=True)
    attr.unlock(node, ["tx"])
    assert not cmds.getAttr(f"{node.name}.tx", lock=True)
    assert cmds.getAttr(f"{node.name}.tx", keyable=True)


def test_lock_and_hide_subset_without_hide():
    node = tm.Transform.create(name="node")
    attr.lock_and_hide(node, ["sx", "sy", "sz"], hide=False)
    assert cmds.getAttr(f"{node.name}.sx", lock=True)
    assert cmds.getAttr(f"{node.name}.sx", keyable=True)
    assert not cmds.getAttr(f"{node.name}.tx", lock=True)


def test_lock_and_hide_accepts_node_name():
    node = tm.Transform.create(name="node")
    attr.lock_and_hide("node", ["ty"])
    assert cmds.getAttr(f"{node.name}.ty", lock=True)


def test_drive_connects_one_to_many():
    source = tm.Transform.create(name="source")
    first = tm.Transform.create(name="first")
    second = tm.Transform.create(name="second")
    attr.drive(source["tx"], [first["ty"], second["tz"]])
    source["tx"].value = 3.0
    assert first["ty"].value == 3.0 and second["tz"].value == 3.0


def test_add_proxy():
    source = tm.Transform.create(name="source")
    holder = tm.Transform.create(name="holder")
    src_plug = attr.add_float(source, "stretch", default=0.25)
    proxy = attr.add_proxy(holder, src_plug)
    assert proxy.attr == "stretch"
    assert proxy.value == 0.25
    proxy.value = 0.75
    assert src_plug.value == 0.75
