"""Tests for the Node.meta metadata store."""

import pytest
from maya import cmds

import tik.maya as tm
from tik.maya.core.meta import META_PREFIX, find_by_meta


def test_set_get_roundtrip_types():
    node = tm.Transform.create(name="meta_node")
    node.meta["kind"] = "guide"
    node.meta["index"] = 3
    node.meta["ratio"] = 0.5
    node.meta["flag"] = True
    node.meta["items"] = ["a", 1]
    node.meta["settings"] = {"segments": 3, "local": False}
    assert node.meta["kind"] == "guide"
    assert node.meta["index"] == 3 and isinstance(node.meta["index"], int)
    assert node.meta["ratio"] == 0.5
    assert node.meta["flag"] is True
    assert node.meta["items"] == ["a", 1]
    assert node.meta["settings"] == {"segments": 3, "local": False}


def test_attr_name_uses_prefix_and_is_hidden_string():
    node = tm.Transform.create(name="meta_node")
    node.meta["kind"] = "guide"
    assert cmds.attributeQuery(f"{META_PREFIX}kind", node=node.name, exists=True)
    assert cmds.getAttr(f"{node.name}.{META_PREFIX}kind", type=True) == "string"
    assert not cmds.getAttr(f"{node.name}.{META_PREFIX}kind", keyable=True)


def test_contains_get_del_keys():
    node = tm.Transform.create(name="meta_node")
    assert "kind" not in node.meta
    assert node.meta.get("kind", "none") == "none"
    node.meta["kind"] = "guide"
    node.meta["role"] = "root"
    assert "kind" in node.meta
    assert sorted(node.meta.keys()) == ["kind", "role"]
    del node.meta["kind"]
    assert "kind" not in node.meta
    with pytest.raises(KeyError):
        node.meta["kind"]


def test_overwrite_and_none():
    node = tm.Transform.create(name="meta_node")
    node.meta["kind"] = "guide"
    node.meta["kind"] = "rig"
    assert node.meta["kind"] == "rig"
    node.meta["empty"] = None
    assert node.meta["empty"] is None


def test_invalid_key_rejected():
    node = tm.Transform.create(name="meta_node")
    with pytest.raises(ValueError):
        node.meta["bad key"] = 1


def test_update_clear_items_len():
    node = tm.Transform.create(name="meta_node")
    node.meta.update({"a": 1, "b": 2})
    assert node.meta["b"] == 2
    assert dict(node.meta.items()) == {"a": 1, "b": 2}
    assert len(node.meta) == 2
    node.meta.clear()
    assert node.meta.keys() == []


def test_survives_rename():
    node = tm.Transform.create(name="meta_node")
    node.meta["kind"] = "guide"
    node.rename("renamed_node")
    assert node.meta["kind"] == "guide"


def test_find_by_meta():
    first = tm.Transform.create(name="first")
    second = tm.Joint.create(name="second")
    third = tm.Transform.create(name="third")
    first.meta["kind"] = "guide"
    second.meta["kind"] = "guide"
    third.meta["kind"] = "rig"
    names = sorted(node.name for node in find_by_meta("kind", "guide"))
    assert names == ["first", "second"]
    joints = find_by_meta("kind", "guide", node_type="joint")
    assert [node.name for node in joints] == ["second"]
    assert len(find_by_meta("kind")) == 3
    assert find_by_meta("missing") == []


def test_find_by_meta_is_exported():
    assert tm.find_by_meta is find_by_meta


def test_undoable():
    node = tm.Transform.create(name="meta_node")
    cmds.undoInfo(openChunk=True)
    node.meta["kind"] = "guide"
    cmds.undoInfo(closeChunk=True)
    cmds.undo()
    assert "kind" not in node.meta
