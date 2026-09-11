"""Which modules a scoped test build tears down and rebuilds."""

import pytest
from toy_modules import ToyChain, ToyRoot

from tik.trigger.core import clear_registries, register_module
from tik.trigger.core.build_scope import expand_build_scope
from tik.trigger.core.guide_document import ModuleEntry


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_module("toy_root")(ToyRoot)
    register_module("toy_chain")(ToyChain)
    yield
    clear_registries()


def _entry(instance_id, name, inputs=None, module_type="toy_chain", settings=None):
    return ModuleEntry(
        instance_id=instance_id,
        module_type=module_type,
        name=name,
        side="C",
        settings=dict(settings or {}),
        inputs=dict(inputs or {}),
    )


def _chain():
    """body -> arm -> hand, each consuming the one before it."""
    body = _entry("id_body", "body", module_type="toy_root")
    arm = _entry("id_arm", "arm", inputs={"root": "id_body.root"})
    hand = _entry("id_hand", "hand", inputs={"root": "id_arm.end"})
    return [body, arm, hand]


def test_an_unconnected_module_is_its_own_scope():
    entries = [_entry("id_solo", "solo", module_type="toy_root")]
    assert expand_build_scope(entries, ["id_solo"]) == ["id_solo"]


def test_an_unbuilt_producer_is_left_alone():
    """Building the arm alone builds the arm alone: its socket stands free."""
    assert expand_build_scope(_chain(), ["id_arm"]) == ["id_arm"]


def test_an_already_built_producer_is_left_alone():
    """The common loop: body built, tweak the arm, rebuild the arm only."""
    scope = expand_build_scope(_chain(), ["id_arm"], already_built={"id_body"})
    assert scope == ["id_arm"]


def test_a_built_consumer_is_rebuilt_with_its_producer():
    """Its attach would otherwise point at deleted nodes."""
    scope = expand_build_scope(
        _chain(), ["id_arm"], already_built={"id_body", "id_arm", "id_hand"}
    )
    assert scope == ["id_arm", "id_hand"]


def test_an_unbuilt_consumer_is_left_alone():
    """Nothing dangles, so nothing is built behind the rigger's back."""
    scope = expand_build_scope(
        _chain(), ["id_arm"], already_built={"id_body", "id_arm"}
    )
    assert scope == ["id_arm"]


def test_downstream_repair_is_transitive():
    scope = expand_build_scope(
        _chain(), ["id_body"], already_built={"id_body", "id_arm", "id_hand"}
    )
    assert scope == ["id_body", "id_arm", "id_hand"]


def test_the_scope_is_returned_in_document_order():
    entries = _chain()
    scope = expand_build_scope(
        entries, ["id_hand"], already_built={"id_body", "id_arm", "id_hand"}
    )
    assert scope == ["id_hand"]
    scope = expand_build_scope(
        entries,
        ["id_hand", "id_body"],
        already_built={"id_body", "id_arm", "id_hand"},
    )
    assert scope == ["id_body", "id_arm", "id_hand"]


def test_space_inputs_do_not_pull_a_module_into_scope():
    """Spaces are mutually referential; only structural inputs are the graph."""
    body = _entry("id_body", "body", module_type="toy_root")
    arm = _entry(
        "id_arm",
        "arm",
        inputs={"ik_world": "id_body.root"},
        settings={
            "anim_spaces": [{"control": "ik", "label": "world", "mode": "parent"}]
        },
    )
    assert expand_build_scope([body, arm], ["id_arm"]) == ["id_arm"]


def test_a_later_copys_space_input_does_not_pull_a_module_into_scope():
    """``space_inputs`` names are bare; ``entry.inputs`` keys are qualified.

    So only the first copy's space port was ever skipped, and a second copy's
    registered the arm as a structural consumer of the body -- rebuilding the
    body then tore the arm down and rebuilt it for a space connection, which
    is the thing this module exists to prevent.
    """
    body = _entry("id_body", "body", module_type="toy_root")
    arm = _entry(
        "id_arm",
        "arm",
        inputs={"c1_fk0_world": "id_body.root"},
        settings={
            "copies": [
                {"slug": "", "name": "a", "segments": 2},
                {"slug": "c1", "name": "b", "segments": 2},
            ],
            "anim_spaces": [{"control": "fk0", "label": "world", "mode": "parent"}],
        },
    )
    scope = expand_build_scope(
        [body, arm], ["id_body"], already_built={"id_body", "id_arm"}
    )
    assert scope == ["id_body"]


def test_an_unknown_module_type_treats_every_input_as_structural():
    """A module the registry has never heard of must not crash the scope."""
    body = _entry("id_body", "body", module_type="toy_root")
    arm = _entry("id_arm", "arm", inputs={"root": "id_body.root"}, module_type="ghost")
    scope = expand_build_scope(
        [body, arm], ["id_body"], already_built={"id_body", "id_arm"}
    )
    assert scope == ["id_body", "id_arm"]


def test_a_bare_scene_node_source_has_no_producer():
    arm = _entry("id_arm", "arm", inputs={"root": "some_locator"})
    assert expand_build_scope([arm], ["id_arm"]) == ["id_arm"]


def test_a_cycle_terminates():
    one = _entry("id_one", "one", inputs={"root": "id_two.end"})
    two = _entry("id_two", "two", inputs={"root": "id_one.end"})
    scope = expand_build_scope(
        [one, two], ["id_one"], already_built={"id_one", "id_two"}
    )
    assert scope == ["id_one", "id_two"]


def test_ids_not_in_the_document_are_ignored():
    assert expand_build_scope(_chain(), ["id_ghost"]) == []
