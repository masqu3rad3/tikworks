"""DCC-free tests for tik.trigger.core: manifest, module, registry, schemas, builder."""

import json

import pytest

from toy_modules import ToyChain, ToyRoot
from tik.trigger.core import (
    DuplicateRegistrationError,
    EventBus,
    GuideLayout,
    ModuleInstance,
    NotFoundError,
    ParentRef,
    RigDocument,
    Side,
    clear_registries,
    get_module,
    register_action,
    register_module,
    unregister_module,
)
from tik.trigger.core.schemas import GuidePose, order_instances


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_module("toy_root")(ToyRoot)
    register_module("toy_chain")(ToyChain)
    yield
    clear_registries()


# ---------------------------------------------------------------- manifest
def test_guides_fixed_and_multi():
    fixed = GuideLayout("collar", "shoulder")
    assert fixed.root == "collar"
    assert fixed.expand() == [("collar", 0), ("shoulder", 0)]
    assert fixed.validate([("collar", 0)]) == ["missing guide 'shoulder'"]

    chain = GuideLayout("root", multi="segment", min=2, max=4)
    assert chain.expand(3) == [("root", 0), ("segment", 0), ("segment", 1), ("segment", 2)]
    assert chain.validate([("root", 0), ("segment", 0)]) == ["needs at least 2 'segment' guides"]
    assert "allows at most 4" in chain.validate([("root", 0)] + [("segment", i) for i in range(5)])[0]
    assert chain.validate([("root", 0), ("segment", 0), ("segment", 1), ("nope", 0)]) == [
        "unknown guide role 'nope'"
    ]


def test_guides_rejects_bad_declarations():
    with pytest.raises(ValueError):
        GuideLayout()
    with pytest.raises(ValueError):
        GuideLayout("a", "a")
    with pytest.raises(ValueError):
        GuideLayout("a", multi="a")


# ------------------------------------------------------------------ module
def test_module_defaults_and_registry_stamp():
    module = ToyChain(name="tail", side="left")
    assert module.module_type == "toy_chain"
    assert module.side is Side.LEFT
    assert module.segments == 2
    assert module.expected_guides() == [("root", 0), ("segment", 0), ("segment", 1)]
    assert ToyChain.display_label() == "Toy Chain"


def test_unsided_module_forces_center():
    module = ToyRoot(side="left")
    assert module.side is Side.CENTER


def test_module_instance_roundtrip():
    module = ToyChain(name="tail", side="R", settings={"segments": 3})
    instance = module.to_instance(
        guides=[GuidePose("root"), GuidePose("segment", 0, (1, 0, 0))],
        parent=ParentRef("abc", "root"),
        inputs={"root": "body.root"},
    )
    data = json.loads(json.dumps(instance.to_dict()))
    restored = ModuleInstance.from_dict(data)
    # anim_spaces lives on the base Module, so every module carries the key.
    assert restored.settings == {"segments": 3, "anim_spaces": []}
    assert restored.side == "R"
    assert restored.parent == ParentRef("abc", "root")
    assert restored.inputs == {"root": "body.root"}
    module2 = ToyChain.from_instance(restored)
    assert module2.segments == 3 and module2.instance_id == module.instance_id
    assert module2.guide_pairs == [("root", 0), ("segment", 0)]


def test_validate_uses_scene_guide_pairs():
    module = ToyChain(settings={"segments": 2})
    module.guide_pairs = [("root", 0)]
    assert module.validate() == ["needs at least 1 'segment' guides"]


# ---------------------------------------------------------------- registry
def test_registry_duplicate_and_missing():
    with pytest.raises(DuplicateRegistrationError):
        register_module("toy_root")(ToyChain)
    register_module("toy_root")(ToyRoot)  # same class again is fine
    with pytest.raises(NotFoundError):
        get_module("nothing")
    unregister_module("toy_root")
    with pytest.raises(NotFoundError):
        get_module("toy_root")


def test_register_action_stamps_type():
    from tik.trigger.core import Action, list_actions

    @register_action("noop")
    class Noop(Action):
        def run(self, ctx):
            pass

    assert Noop.action_type == "noop"
    assert list_actions() == ["noop"]


# ----------------------------------------------------------------- schemas
def test_document_roundtrip_and_schema_guard():
    document = RigDocument(meta={"author": "me"})
    document.guides.append(ToyRoot().to_instance())
    data = json.loads(json.dumps(document.to_dict()))
    restored = RigDocument.from_dict(data)
    assert restored.meta["author"] == "me"
    assert restored.guides[0].module_type == "toy_root"
    with pytest.raises(ValueError):
        RigDocument.from_dict({"schema": 99})


def test_order_instances_parents_first_and_cycle():
    root = ToyRoot(name="root").to_instance()
    child = ToyChain(name="child").to_instance(parent=ParentRef(root.instance_id))
    grandchild = ToyChain(name="grand").to_instance(parent=ParentRef(child.instance_id))
    ordered = order_instances([grandchild, child, root])
    assert [item.name for item in ordered] == ["root", "child", "grand"]
    cyc_a = ToyChain(name="a").to_instance()
    cyc_b = ToyChain(name="b").to_instance(parent=ParentRef(cyc_a.instance_id))
    cyc_a.parent = ParentRef(cyc_b.instance_id)
    with pytest.raises(ValueError):
        order_instances([cyc_a, cyc_b])


# ----------------------------------------------------------------- builder
def test_order_by_connections_puts_producers_first():
    from tik.trigger.core.schemas import order_by_connections

    a = ToyRoot(name="a").to_instance()
    b = ToyChain(name="b").to_instance()
    c = ToyChain(name="c").to_instance()
    inputs = {"a": {}, "b": {"root": f"{a.key}.root"}, "c": {"root": f"{b.key}.root"}}
    ordered = order_by_connections([c, b, a], lambda item: inputs[item.name])
    assert [item.name for item in ordered] == ["a", "b", "c"]


def test_order_by_connections_detects_a_cycle():
    from tik.trigger.core.schemas import order_by_connections

    a = ToyChain(name="a").to_instance()
    b = ToyChain(name="b").to_instance()
    inputs = {"a": {"root": f"{b.key}.root"}, "b": {"root": f"{a.key}.root"}}
    with pytest.raises(ValueError, match="Cyclic"):
        order_by_connections([a, b], lambda item: inputs[item.name])


def test_order_by_connections_keeps_unconnected_order():
    from tik.trigger.core.schemas import order_by_connections

    a = ToyRoot(name="a").to_instance()
    b = ToyChain(name="b").to_instance()
    ordered = order_by_connections([b, a], lambda item: {})
    assert [item.name for item in ordered] == ["b", "a"]


def test_order_by_connections_ignores_bare_scene_sources():
    from tik.trigger.core.schemas import order_by_connections

    a = ToyChain(name="a").to_instance()
    ordered = order_by_connections([a], lambda item: {"root": "some_jnt"})
    assert [item.name for item in ordered] == ["a"]


# ------------------------------------------------------------------- spaces

# ------------------------------------------------------------ anim spaces
def _spaced_module():
    from tik.trigger.core import Module

    class Spaced(Module):
        space_controls = ("ik", "pole")

    return Spaced


def test_space_rows_are_empty_by_default():
    assert _spaced_module().space_rows({}) == []


def test_space_inputs_derive_one_port_per_row():
    module_cls = _spaced_module()
    settings = {"anim_spaces": [
        {"control": "ik", "mode": "parent", "label": "chest"},
        {"control": "pole", "mode": "point", "label": "chest"},
    ]}
    derived = module_cls.space_inputs(settings)
    assert [item.name for item in derived] == ["ik_chest", "pole_chest"]
    assert all(item.kind == "space" for item in derived)
    assert all(item.optional for item in derived)


def test_input_names_include_spaces():
    module_cls = _spaced_module()
    settings = {"anim_spaces": [{"control": "ik", "mode": "parent", "label": "chest"}]}
    assert module_cls.input_names(settings) == ["root", "ik_chest"]
    assert module_cls.input_names({}) == ["root"]


def test_validate_rejects_an_empty_label():
    module = _spaced_module()(name="x")
    module.anim_spaces = [{"control": "ik", "mode": "parent", "label": ""}]
    assert any("label" in problem for problem in module.validate())


def test_validate_rejects_an_unknown_control():
    module = _spaced_module()(name="x")
    module.anim_spaces = [{"control": "ghost", "mode": "parent", "label": "chest"}]
    assert any("ghost" in problem for problem in module.validate())


def test_validate_rejects_duplicate_rows():
    """(control, label) is the derived port name; a clash would drop a wire."""
    module = _spaced_module()(name="x")
    module.anim_spaces = [
        {"control": "ik", "mode": "parent", "label": "chest"},
        {"control": "ik", "mode": "orient", "label": "chest"},
    ]
    assert any("ik_chest" in problem for problem in module.validate())


def _with_space_rows(instance, rows):
    instance.settings["anim_spaces"] = rows
    return instance
