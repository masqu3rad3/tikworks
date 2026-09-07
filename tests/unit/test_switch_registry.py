"""The animator switch registry and its contract (no Maya, no Qt)."""

import pytest

from tik.trigger.anim import registry as switch_registry
from tik.trigger.anim.context import Control, SwitchContext
from tik.trigger.anim.registry import (
    clear_switches,
    get_switch,
    iter_switches,
    register_switch,
)
from tik.trigger.anim.switch import Switch
from tik.trigger.core.exceptions import DuplicateRegistrationError, NotFoundError


@pytest.fixture
def empty_registry():
    """An empty registry, with the shipped switches put back afterwards."""
    kept = switch_registry.registered()
    clear_switches()
    yield
    switch_registry.restore(kept)


def _toy(name, order=100, available=True, states=("a", "b")):
    class Toy(Switch):
        label = name.title()

    Toy.order = order
    Toy.available = available
    Toy.states = lambda self, context: list(states)
    return register_switch(name)(Toy)


# ----------------------------------------------------------------- registry
def test_register_stamps_type_and_icon(empty_registry):
    toy = _toy("pivot")
    assert toy.switch_type == "pivot"
    assert toy.icon == "pivot"
    assert get_switch("pivot") is toy


def test_the_icon_name_can_differ_from_the_type(empty_registry):
    class Toy(Switch):
        label = "Toy"

    register_switch("toy", icon="other")(Toy)
    assert Toy.icon == "other"


def test_registering_a_name_twice_is_refused(empty_registry):
    _toy("pivot")
    with pytest.raises(DuplicateRegistrationError):

        @register_switch("pivot")
        class Other(Switch):
            label = "Other"


def test_registering_the_same_class_twice_is_fine(empty_registry):
    toy = _toy("pivot")
    register_switch("pivot")(toy)
    assert get_switch("pivot") is toy


def test_unknown_switch_raises(empty_registry):
    with pytest.raises(NotFoundError):
        get_switch("nope")


def test_switches_iterate_in_order_then_label(empty_registry):
    _toy("zed", order=10)
    _toy("alpha", order=10)
    _toy("last", order=90)
    assert [item.switch_type for item in iter_switches()] == ["alpha", "zed", "last"]


# ----------------------------------------------------------------- contract
def test_the_base_contract_offers_nothing():
    class Bare(Switch):
        label = "Bare"

    context = SwitchContext()
    assert Bare().states(context) == []
    assert Bare().current(context) is None
    assert Bare.display_label() == "Bare"
    with pytest.raises(NotImplementedError):
        Bare().apply(context, "a", key=False, times=())


def test_display_label_falls_back_to_the_type(empty_registry):
    class Nameless(Switch):
        pass

    register_switch("nameless")(Nameless)
    assert Nameless.display_label() == "nameless"


# ------------------------------------------------------------------ context
def test_context_reports_keys_and_sides_without_repeats():
    context = SwitchContext(
        nodes=("|a", "|b", "|c"),
        controls=(
            Control(node="|a", role="ik", side="L", module="arm", instance="1"),
            Control(node="|b", role="pole", side="L", module="arm", instance="1"),
            Control(node="|c", role="ik", side="R", module="arm", instance="2"),
        ),
    )
    assert context.is_empty is False
    assert context.keys == ("L_arm", "R_arm")
    assert context.sides == ("L", "R")


def test_a_centre_control_key_carries_no_side():
    assert Control(node="|a", side="C", module="spine").key == "spine"


def test_a_control_with_no_module_has_no_key():
    assert Control(node="|a", side="L").key == ""


def test_an_empty_context_is_empty():
    assert SwitchContext().is_empty is True
    assert SwitchContext().keys == ()
    assert SwitchContext().sides == ()


def test_a_selection_of_non_controls_is_still_empty():
    """Nodes are recorded, but a switch has nothing to act on."""
    assert SwitchContext(nodes=("|pCube1",)).is_empty is True
