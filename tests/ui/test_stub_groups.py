"""The stub's group surface matches GuideScene's.

A double that has drifted from the real surface tests nothing, so the shapes
are compared directly rather than trusted.
"""

import inspect

import pytest
from stub import StubScene
from toy_modules import ToyChain, ToyRoot

from tik.trigger.core import clear_registries, register_module
from tik.trigger.guides.scene import GuideScene

GROUP_API = (
    "groups",
    "group_of",
    "group_members",
    "group",
    "ungroup",
    "add_copy",
    "remove_from_group",
    "mirror_group",
)


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_module("toy_root")(ToyRoot)
    register_module("toy_chain")(ToyChain)
    yield
    clear_registries()


def _pair(scene, side="L"):
    return [scene.add("toy_chain", name=name, side=side) for name in ("a", "b")]


def test_the_stub_offers_every_group_method_the_scene_does():
    missing = [name for name in GROUP_API if not hasattr(StubScene, name)]
    assert missing == []


def test_the_signatures_match():
    """A stub that drifts from the real surface tests nothing."""
    for name in GROUP_API:
        real = inspect.signature(getattr(GuideScene, name))
        stub = inspect.signature(getattr(StubScene, name))
        assert list(real.parameters) == list(stub.parameters), name


def test_add_copy_groups_a_lone_module():
    scene = StubScene()
    handle = scene.add("toy_chain", name="index", side="L")
    copy = scene.add_copy(handle)
    group = scene.group_of(handle.instance_id)
    assert group.members == [handle.instance_id, copy.instance_id]


def test_the_stubs_group_state_survives_a_cache_invalidation():
    """The document is rebuilt on demand; the groups must not be rebuilt away."""
    scene = StubScene()
    handles = _pair(scene)
    group = scene.group(handles, label="fingers")
    scene.add("toy_chain", name="c", side="L")  # invalidates the document cache
    assert scene.document.module_group(group.group_id) is not None
    assert scene.groups()[0].members == [h.instance_id for h in handles]


def test_removing_a_member_down_to_one_dissolves_the_group_in_the_stub():
    scene = StubScene()
    handles = _pair(scene)
    scene.group(handles, label="fingers")
    scene.remove(handles[1])
    assert scene.groups() == []
