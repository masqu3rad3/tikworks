"""DCC-free tests for tik.trigger.core: manifest, module, registry, schemas, builder."""

import json

import pytest

from trigger_fakes import FakeBackend, ToyChain, ToyRoot
from tik.trigger.core import (
    AttachError,
    BuildError,
    Builder,
    DuplicateRegistrationError,
    EventBus,
    Guides,
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
    fixed = Guides("collar", "shoulder")
    assert fixed.root == "collar"
    assert fixed.expand() == [("collar", 0), ("shoulder", 0)]
    assert fixed.validate([("collar", 0)]) == ["missing guide 'shoulder'"]

    chain = Guides("root", multi="segment", min=2, max=4)
    assert chain.expand(3) == [("root", 0), ("segment", 0), ("segment", 1), ("segment", 2)]
    assert chain.validate([("root", 0), ("segment", 0)]) == ["needs at least 2 'segment' guides"]
    assert "allows at most 4" in chain.validate([("root", 0)] + [("segment", i) for i in range(5)])[0]
    assert chain.validate([("root", 0), ("segment", 0), ("segment", 1), ("nope", 0)]) == [
        "unknown guide role 'nope'"
    ]


def test_guides_rejects_bad_declarations():
    with pytest.raises(ValueError):
        Guides()
    with pytest.raises(ValueError):
        Guides("a", "a")
    with pytest.raises(ValueError):
        Guides("a", multi="a")


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
        attach="end",
    )
    data = json.loads(json.dumps(instance.to_dict()))
    restored = ModuleInstance.from_dict(data)
    # anim_spaces lives on the base Module, so every module carries the key.
    assert restored.settings == {"segments": 3, "anim_spaces": []}
    assert restored.side == "R"
    assert restored.parent == ParentRef("abc", "root")
    assert restored.attach == "end"
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
def _scene():
    backend = FakeBackend()
    root = backend.create_guides(ToyRoot(name="body"))
    chain = backend.create_guides(
        ToyChain(name="tail", side="L", settings={"segments": 3}),
        parent=ParentRef(root.instance_id, "root"),
    )
    return backend, root, chain


def test_builder_builds_in_order_and_connects():
    backend, root, chain = _scene()
    events = EventBus()
    seen = []
    events.subscribe("progress", lambda **kw: seen.append(kw["label"]))
    report = Builder(backend, events).build(rig_name="rig", afterlife="hide")
    assert report.built == [root.instance_id, chain.instance_id]
    assert seen == ["Building body", "Building tail"]
    assert backend.connections == [("L_tail", "root", "C_body_root_jnt")]
    assert report.connections == [("L_tail.root", "body.root")]
    assert backend.afterlife_mode == "hide"
    assert ("rig_root", "rig") in backend.calls
    assert backend.calls.index(("undo_open", "Trigger build: rig")) < backend.calls.index(
        ("rig_root", "rig")
    )
    ctx = report.contexts[chain.instance_id]
    assert ctx.outputs["end"] == "tail_segment_2"
    assert len(ctx.deform_joints) == 3
    assert ctx.name("upper", suffix="jnt") == "L_tail_upper_jnt"


def test_builder_inputs_scene_node_missing_and_optional():
    backend, root, chain = _scene()
    # explicit inputs win over the DAG-derived one; scene node sources must exist
    chain.inputs = {"root": "body.root", "space": "some_jnt"}
    with pytest.raises(AttachError) as info:
        Builder(backend).build()
    assert "some_jnt" in str(info.value) and "L_tail.space" in str(info.value)
    backend.scene_nodes.add("some_jnt")
    report = Builder(backend).build()
    assert ("L_tail", "space", "some_jnt") in backend.connections
    assert ("L_tail.space", "some_jnt") in report.connections
    chain.inputs = {"root": "body.nope"}
    with pytest.raises(AttachError) as info:
        Builder(backend).build()
    assert "not built" in str(info.value)
    chain.inputs = {}
    chain.parent = None  # nothing to derive from -> required input missing
    with pytest.raises(AttachError) as info:
        Builder(backend).build()
    assert "required input" in str(info.value)


def test_builder_wraps_failures():
    backend, root, chain = _scene()
    backend.fail_on = "tail"
    errors = []
    events = EventBus()
    events.subscribe("error", lambda **kw: errors.append(kw["context"]))
    with pytest.raises(BuildError) as info:
        Builder(backend, events).build()
    assert info.value.instance_id == chain.instance_id
    assert errors == ["building tail"]


def test_builder_validation_failure():
    backend, root, chain = _scene()
    chain.guides = [GuidePose("root")]  # scene lost its segments
    with pytest.raises(BuildError) as info:
        Builder(backend).build()
    assert "needs at least" in str(info.value)


def test_builder_empty_scene_and_bad_afterlife():
    backend = FakeBackend()
    assert Builder(backend).build().count == 0
    with pytest.raises(ValueError):
        Builder(backend).build(afterlife="burn")


# --------------------------------------------------- topological ordering
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


def test_builder_passes_bind_parent_from_the_producer():
    """A connected module builds its bind joints inside the producer's."""
    backend, root, chain = _scene()
    report = Builder(backend).build(rig_name="rig", afterlife="keep")
    producer_ctx = report.contexts[root.instance_id]
    consumer_ctx = report.contexts[chain.instance_id]
    assert consumer_ctx.bind_parent == producer_ctx.outputs["root"]


def test_builder_bind_parent_defaults_when_unconnected():
    backend = FakeBackend()
    solo = backend.create_guides(ToyRoot(name="solo"))
    report = Builder(backend).build(rig_name="rig", afterlife="keep")
    ctx = report.contexts[solo.instance_id]
    assert ctx.bind_parent == ctx.groups.bind


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


def test_space_inputs_do_not_feed_build_order():
    """An arm in head space while the head is in arm space is a normal rig."""
    backend = FakeBackend()
    first = backend.create_guides(ToyRoot(name="a"))
    second = backend.create_guides(ToyRoot(name="b"))
    _with_space_rows(first, [{"control": "root", "mode": "parent", "label": "b"}])
    _with_space_rows(second, [{"control": "root", "mode": "parent", "label": "a"}])
    first.inputs = {"root_b": "b.root"}
    second.inputs = {"root_a": "a.root"}
    report = Builder(backend).build(rig_name="rig", afterlife="keep")
    assert report.count == 2


def test_space_connections_are_grouped_by_control_and_mode():
    backend = FakeBackend()
    backend.create_guides(ToyRoot(name="body"))
    backend.create_guides(ToyRoot(name="head"))
    arm = backend.create_guides(ToyRoot(name="arm"))
    _with_space_rows(arm, [
        {"control": "root", "mode": "parent", "label": "body"},
        {"control": "root", "mode": "parent", "label": "head"},
    ])
    arm.inputs = {"root_body": "body.root", "root_head": "head.root"}
    Builder(backend).build(rig_name="rig", afterlife="keep")
    assert backend.space_connections == [("arm", "root", "parent", ["body", "head"])]


def test_row_order_is_enum_order():
    backend = FakeBackend()
    backend.create_guides(ToyRoot(name="body"))
    backend.create_guides(ToyRoot(name="head"))
    arm = backend.create_guides(ToyRoot(name="arm"))
    _with_space_rows(arm, [
        {"control": "root", "mode": "parent", "label": "head"},
        {"control": "root", "mode": "parent", "label": "body"},
    ])
    arm.inputs = {"root_body": "body.root", "root_head": "head.root"}
    Builder(backend).build(rig_name="rig", afterlife="keep")
    assert backend.space_connections[0][3] == ["head", "body"]


def test_an_unconnected_space_row_is_skipped():
    backend = FakeBackend()
    arm = backend.create_guides(ToyRoot(name="arm"))
    _with_space_rows(arm, [{"control": "root", "mode": "parent", "label": "ghost"}])
    report = Builder(backend).build(rig_name="rig", afterlife="keep")
    assert backend.space_connections == []
    assert report.spaces == []
