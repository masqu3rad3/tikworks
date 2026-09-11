"""DCC-free tests for tik.trigger.core: manifest, module, registry, schemas, builder."""

import json

import pytest
from toy_modules import ToyChain, ToyRoot

import tik.trigger as trigger
from tik.trigger.core import (
    DuplicateRegistrationError,
    GuideLayout,
    Input,
    Module,
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
    assert chain.expand(3) == [
        ("root", 0),
        ("segment", 0),
        ("segment", 1),
        ("segment", 2),
    ]
    assert chain.validate([("root", 0), ("segment", 0)]) == [
        "needs at least 2 'segment' guides"
    ]
    assert (
        "allows at most 4"
        in chain.validate([("root", 0)] + [("segment", index) for index in range(5)])[0]
    )
    assert chain.validate(
        [("root", 0), ("segment", 0), ("segment", 1), ("nope", 0)]
    ) == ["unknown guide role 'nope'"]


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
    # anim_spaces, pivot_presets and control_shape_overrides live on the base
    # Module, so every module carries all three keys.
    assert restored.settings == {
        "segments": 3,
        "controller_size": 1.0,
        "anim_spaces": [],
        "pivot_presets": [],
        "control_shape_overrides": [],
        "copies": [],
    }
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

    first = ToyRoot(name="a").to_instance()
    second = ToyChain(name="b").to_instance()
    third = ToyChain(name="c").to_instance()
    inputs = {
        "a": {},
        "b": {"root": f"{first.key}.root"},
        "c": {"root": f"{second.key}.root"},
    }
    ordered = order_by_connections(
        [third, second, first], lambda item: inputs[item.name]
    )
    assert [item.name for item in ordered] == ["a", "b", "c"]


def test_order_by_connections_detects_a_cycle():
    from tik.trigger.core.schemas import order_by_connections

    first = ToyChain(name="a").to_instance()
    second = ToyChain(name="b").to_instance()
    inputs = {"a": {"root": f"{second.key}.root"}, "b": {"root": f"{first.key}.root"}}
    with pytest.raises(ValueError, match="Cyclic"):
        order_by_connections([first, second], lambda item: inputs[item.name])


def test_order_by_connections_keeps_unconnected_order():
    from tik.trigger.core.schemas import order_by_connections

    first = ToyRoot(name="a").to_instance()
    second = ToyChain(name="b").to_instance()
    ordered = order_by_connections([second, first], lambda item: {})
    assert [item.name for item in ordered] == ["b", "a"]


# ------------------------------------------------------------- categories
def test_register_module_stamps_category_and_icon():
    from tik.trigger.core import Module, register_module, registry

    @register_module("probe_limb", category="limbs")
    class ProbeLimb(Module):
        pass

    try:
        assert ProbeLimb.module_type == "probe_limb"
        assert ProbeLimb.category == "limbs"
        assert ProbeLimb.icon == "probe_limb"  # defaults to the registered name
    finally:
        registry.unregister_module("probe_limb")


def test_register_module_category_defaults_to_generic():
    from tik.trigger.core import Module, register_module, registry

    @register_module("probe_plain")
    class ProbePlain(Module):
        pass

    try:
        assert ProbePlain.category == "generic"
    finally:
        registry.unregister_module("probe_plain")


def test_shipped_modules_declare_a_category():
    from tik.trigger.core import registry

    trigger.load_plugins()
    expected = {
        "base": "body",
        "fkchain": "generic",
        "arm": "limbs",
        "twist": "generic",
        "ribbon": "generic",
    }
    for name, category in expected.items():
        assert registry.get_module(name).category == category


def test_import_asset_icon_defaults_to_its_own_name():
    from tik.trigger.core import registry

    trigger.load_plugins()
    assert registry.get_action("import_asset").icon == "import_asset"


def test_order_by_connections_ignores_bare_scene_sources():
    from tik.trigger.core.schemas import order_by_connections

    first = ToyChain(name="a").to_instance()
    ordered = order_by_connections([first], lambda item: {"root": "some_jnt"})
    assert [item.name for item in ordered] == ["a"]


# ------------------------------------------------------------------- spaces


# ------------------------------------------------------------ anim spaces
def _spaced_module():
    from tik.trigger.core import Module

    class Spaced(Module):
        controls = ("ik", "pole")

    return Spaced


def _dynamic_module():
    from tik.trigger.core import IntField, Module

    class Dynamic(Module):
        segments = IntField(3, min=1)

        @classmethod
        def control_names(cls, settings=None):
            count = int((settings or {}).get("segments", cls.segments.default))
            return tuple(f"fk{index}" for index in range(count))

    return Dynamic


def test_space_rows_are_empty_by_default():
    assert _spaced_module().space_rows({}) == []


def test_space_inputs_derive_one_port_per_row():
    module_cls = _spaced_module()
    settings = {
        "anim_spaces": [
            {"control": "ik", "mode": "parent", "label": "chest"},
            {"control": "pole", "mode": "point", "label": "chest"},
        ]
    }
    derived = module_cls.space_inputs(settings)
    assert [item.name for item in derived] == ["ik_chest", "pole_chest"]
    assert all(item.kind == "space" for item in derived)
    assert not any(item.required for item in derived)


def test_an_input_is_not_required_by_default():
    """Attachment is a connection, not a precondition.

    Spec: 2026-09-09-modules-without-required-inputs-design.md, section 2.
    """
    assert Input("root", primary=True).required is False
    assert Input("anchor", required=True).required is True


def test_input_names_include_spaces():
    module_cls = _spaced_module()
    settings = {"anim_spaces": [{"control": "ik", "mode": "parent", "label": "chest"}]}
    assert module_cls.input_names(settings) == ["root", "ik_chest"]
    assert module_cls.input_names({}) == ["root"]


def test_validate_rejects_an_empty_label():
    module = _spaced_module()(name="x")
    module.anim_spaces = [{"control": "ik", "mode": "parent", "label": ""}]
    assert any("label" in problem for problem in module.validate())


def test_validate_rejects_duplicate_rows():
    """(control, label) is the derived port name; a clash would drop a wire."""
    module = _spaced_module()(name="x")
    module.anim_spaces = [
        {"control": "ik", "mode": "parent", "label": "chest"},
        {"control": "ik", "mode": "orient", "label": "chest"},
    ]
    assert any("ik_chest" in problem for problem in module.validate())


def test_control_names_defaults_to_the_declared_controls():
    assert _spaced_module().control_names() == ("ik", "pole")
    assert _spaced_module().control_names({}) == ("ik", "pole")


def test_control_names_can_follow_a_setting():
    module_cls = _dynamic_module()
    assert module_cls.control_names({"segments": 2}) == ("fk0", "fk1")
    assert module_cls.control_names() == ("fk0", "fk1", "fk2")


def test_a_stale_control_warns_instead_of_failing_validation():
    """Lowering a count must not make an authored rig unbuildable."""
    module = _dynamic_module()(name="x")
    module.segments = 2
    module.anim_spaces = [{"control": "fk5", "mode": "parent", "label": "world"}]
    assert module.validate() == []
    assert any("fk5" in item for item in module.warnings())


def test_a_stale_control_keeps_its_row_and_its_port():
    """Ports come from rows, not from controls, so the wire survives."""
    module_cls = _dynamic_module()
    settings = {
        "segments": 2,
        "anim_spaces": [{"control": "fk5", "mode": "parent", "label": "world"}],
    }
    assert module_cls.input_names(settings) == ["root", "fk5_world"]


def test_warnings_are_empty_when_every_control_exists():
    module = _spaced_module()(name="x")
    module.anim_spaces = [{"control": "ik", "mode": "parent", "label": "chest"}]
    assert module.warnings() == []


def test_shipped_modules_declare_their_controls():
    """The bug this replaces: fkchain offered an empty control combo."""
    from tik.trigger.core import get_module

    trigger.load_plugins()
    assert get_module("base").control_names() == ("root",)
    assert get_module("twist").control_names() == ()
    assert get_module("fkchain").control_names({"segments": 4}) == (
        "fk0",
        "fk1",
        "fk2",
        "fk3",
    )


def _with_space_rows(instance, rows):
    instance.settings["anim_spaces"] = rows
    return instance


# ------------------------------------------------------------ action scope
def test_action_scope_defaults_to_build_and_is_stamped():
    from tik.trigger.core import Action
    from tik.trigger.core.document import BUILD, PUBLISH
    from tik.trigger.core.registry import BOTH, allows, iter_actions

    class Plain(Action):
        def run(self, ctx):
            pass

    class Exporter(Action):
        def run(self, ctx):
            pass

    class Either(Action):
        def run(self, ctx):
            pass

    register_action("plain")(Plain)
    register_action("exporter", scope=PUBLISH)(Exporter)
    register_action("either", scope=BOTH)(Either)

    assert Plain.scope == BUILD
    assert Exporter.scope == PUBLISH
    assert Either.scope == BOTH

    assert allows("plain", BUILD) and not allows("plain", PUBLISH)
    assert allows("exporter", PUBLISH) and not allows("exporter", BUILD)
    assert allows("either", BUILD) and allows("either", PUBLISH)
    assert not allows("ghost", BUILD)

    assert {cls.action_type for cls in iter_actions()} == {
        "plain",
        "exporter",
        "either",
    }
    assert {cls.action_type for cls in iter_actions(scope=BUILD)} == {"plain", "either"}
    assert {cls.action_type for cls in iter_actions(scope=PUBLISH)} == {
        "exporter",
        "either",
    }


def test_unknown_action_scope_is_rejected():
    from tik.trigger.core import Action
    from tik.trigger.core.exceptions import RegistryError

    class Nope(Action):
        def run(self, ctx):
            pass

    with pytest.raises(RegistryError):
        register_action("nope", scope="sideways")(Nope)


def test_base_action_declares_a_scope():
    from tik.trigger.core import Action
    from tik.trigger.core.document import BUILD

    assert Action.scope == BUILD


def test_shipped_actions_declare_their_scopes():
    from tik.trigger.actions.import_asset.import_asset import ImportAsset
    from tik.trigger.actions.kinematics.kinematics import Kinematics
    from tik.trigger.actions.reference.reference import Reference
    from tik.trigger.actions.script.script import Script
    from tik.trigger.core import registry
    from tik.trigger.core.document import BUILD, PUBLISH

    for cls in (ImportAsset, Kinematics, Reference, Script):
        registry.ensure_registered(cls)

    # a hook script is as useful before an export as during a build
    assert registry.allows("script", BUILD) and registry.allows("script", PUBLISH)
    # everything else stays build-only
    assert registry.allows("kinematics", BUILD) and not registry.allows(
        "kinematics", PUBLISH
    )
    assert registry.allows("import_asset", BUILD) and not registry.allows(
        "import_asset", PUBLISH
    )
    # a reference in the publish list would expand another session's *build*
    # actions into a publish run, which is nonsense
    assert not registry.allows("reference", PUBLISH)


# ------------------------------------------------------------ pivot presets
def _pivot_module():
    """A module with one movable control and three preset rows."""

    class Pivoted(Module):
        guides = GuideLayout("root", "hand")
        controls = ("ik",)
        pivot_controls = {"ik": "hand"}
        pivot_presets = Module.pivot_presets.with_default(
            [{"control": "ik", "label": label} for label in ("tip", "ball", "wrist")]
        )

    return Pivoted


def test_pivot_control_names_comes_from_the_declaration():
    module = _pivot_module()()
    assert module.pivot_control_names(module.values()) == ("ik",)
    assert Module.pivot_control_names({}) == ()


def test_pivot_rows_default_to_the_modules_own():
    module = _pivot_module()()
    assert [row["label"] for row in module.pivot_rows(module.values())] == [
        "tip",
        "ball",
        "wrist",
    ]


def test_pivot_guide_roles_are_named_for_control_and_label():
    module = _pivot_module()()
    assert module.pivot_guide_roles(module.values()) == (
        "pivot_ik_tip",
        "pivot_ik_ball",
        "pivot_ik_wrist",
    )


def test_pivot_guide_roles_skip_incomplete_rows():
    module = _pivot_module()()
    module.pivot_presets = [
        {"control": "ik", "label": "tip"},
        {"control": "", "label": "orphan"},
        {"control": "ik", "label": ""},
    ]
    assert module.pivot_guide_roles(module.values()) == ("pivot_ik_tip",)


def test_expected_guides_includes_the_preset_guides():
    module = _pivot_module()()
    assert module.expected_guides() == [
        ("root", 0),
        ("hand", 0),
        ("pivot_ik_tip", 0),
        ("pivot_ik_ball", 0),
        ("pivot_ik_wrist", 0),
    ]


def test_validate_accepts_preset_guides():
    """The layout does not know the pivot roles; validate must not hand them over."""
    module = _pivot_module()()
    assert module.validate() == []


def test_validate_rejects_an_empty_preset_label():
    module = _pivot_module()()
    module.pivot_presets = [{"control": "ik", "label": ""}]
    assert module.validate() == ["pivot preset row 1: label is required"]


def test_validate_rejects_duplicate_preset_rows():
    module = _pivot_module()()
    module.pivot_presets = [
        {"control": "ik", "label": "tip"},
        {"control": "ik", "label": "tip"},
    ]
    assert module.validate() == ["pivot preset row 2: 'ik.tip' is already defined"]


def test_a_preset_on_a_control_with_no_movable_pivot_warns():
    """A settings change must cost a warning, never the rig."""
    module = _pivot_module()()
    module.pivot_presets = [{"control": "fk", "label": "tip"}]
    assert module.validate() == []
    assert module.warnings() == [
        "pivot preset 'fk.tip': control 'fk' has no movable pivot with the "
        "current settings"
    ]


# ------------------------------------------------------------- action notes
def test_every_action_carries_a_note_that_renders_after_its_own_settings():
    from tik.trigger.core import Action, StringField

    class Annotated(Action):
        tag = StringField("")

        def run(self, ctx):
            pass

    names = list(Annotated.fields())
    assert names[-1] == "notes"
    assert names.index("tag") < names.index("notes")
    assert Annotated().notes == ""


def test_the_note_lives_in_its_own_fold_so_it_lands_at_the_end_of_the_form():
    """Ungrouped fields render before every fold: the note needs a group."""
    from tik.trigger.core import Action

    group = Action.fields()["notes"].group
    assert group is not None and group.label == "Notes"
    assert group.collapsed is True


def test_a_note_is_free_text_and_keeps_its_line_breaks():
    from tik.trigger.core import Action

    class Annotated(Action):
        def run(self, ctx):
            pass

    action = Annotated()
    action.notes = "first line\r\nsecond line"
    assert action.notes == "first line\nsecond line"


def test_a_stale_control_shape_row_warns_but_does_not_invalidate():
    """Lowering a count leaves a row naming a control that is no longer built.

    Kept, not dropped: raising the count restores the setup intact -- the same
    rule anim_spaces and pivot_presets already follow.
    """
    from tik.trigger.core.module import Module

    class Chain(Module):
        module_type = "shapechain"

        @classmethod
        def control_names(cls, settings=None):
            count = int((settings or {}).get("segments", 1))
            return tuple(f"fk{index}" for index in range(count))

    chain = Chain()
    chain.control_shape_overrides = [{"control": "fk7", "shape": "Cube"}]
    warnings = chain.warnings()
    assert any("fk7" in text and "not built" in text for text in warnings)
    assert chain.validate() == []
    # The row survives, so raising the count restores it.
    assert chain.control_shape_overrides[0]["control"] == "fk7"


def test_an_unresolvable_shape_name_warns_but_does_not_invalidate():
    from tik.trigger.core.module import Module

    class ShapeToy(Module):
        module_type = "shapetoy"
        controls = ("root",)

    toy = ShapeToy()
    toy.control_shape_overrides = [{"control": "root", "shape": "NotAShape"}]
    assert any("NotAShape" in text for text in toy.warnings())
    assert toy.validate() == []


# --------------------------------------------- candidate sets per section
def test_space_controls_defaults_to_every_control():
    """Hosting a space is something any controller can do; a module narrows."""

    class Everything(Module):
        controls = ("a", "b", "c")

    assert Everything.space_control_names({}) == ("a", "b", "c")


def test_space_controls_narrows_when_declared():
    class Narrow(Module):
        controls = ("a", "b", "c")
        space_controls = ("b",)

    assert Narrow.space_control_names({}) == ("b",)


def test_space_controls_follows_a_settings_driven_control_set():
    """The hook sees one copy's settings, like every other *_for_copy."""
    from tik.core.fields import IntField

    class Dynamic(Module):
        count = IntField(2)

        @classmethod
        def controls_for_copy(cls, settings=None):
            number = int((settings or {}).get("count", 2))
            return tuple(f"fk{index}" for index in range(number))

    assert Dynamic.space_control_names({"count": 3}) == ("fk0", "fk1", "fk2")
