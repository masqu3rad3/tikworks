"""The Qt double must answer like the real GuideScene, or it tests nothing.

Both cases here are regressions found while building something else: each one
made a *passing* test assert about the wrong thing, which is the worst kind of
defect a test double can have.
"""

import pytest
from stub import StubScene
from toy_modules import ToyChain, ToyRoot

from tik.trigger.core import clear_registries, register_module


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_module("toy_root")(ToyRoot)
    register_module("toy_chain")(ToyChain)
    yield
    clear_registries()


def test_find_instances_honours_an_id_scope():
    scene = StubScene()
    first = scene.add("toy_chain", name="a", side="L")
    second = scene.add("toy_chain", name="b", side="L")
    found = scene.find_instances([second.instance_id])
    assert [item.instance_id for item in found] == [second.instance_id]
    assert first.instance_id not in [item.instance_id for item in found]


def test_find_instances_returns_everything_for_a_string_scope():
    scene = StubScene()
    scene.add("toy_chain", name="a", side="L")
    scene.add("toy_chain", name="b", side="L")
    assert len(scene.find_instances("scene")) == 2
    assert len(scene.find_instances()) == 2


def test_a_handle_resolves_to_its_own_instance():
    """GuideHandle.instance asks for one id and takes found[0]. With the scope
    ignored, every handle in a multi-module scene resolved to the first."""
    scene = StubScene()
    names = ("a", "b", "c")
    handles = [scene.add("toy_chain", name=name, side="L") for name in names]
    assert [handle.instance.name for handle in handles] == list(names)


def test_an_unknown_id_in_the_scope_is_skipped():
    scene = StubScene()
    handle = scene.add("toy_chain", name="a", side="L")
    found = scene.find_instances([handle.instance_id, "nope"])
    assert [item.instance_id for item in found] == [handle.instance_id]
