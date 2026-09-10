"""A module group in the graph: the frame, the collapsed node, its ports."""

import pytest
from stub import StubScene
from toy_modules import ToyChain, ToyRoot

from tik.trigger.core import clear_registries, register_module
from tik.trigger.ui.graph.view import GraphView


@pytest.fixture(autouse=True)
def _registered():
    clear_registries()
    register_module("toy_root")(ToyRoot)
    register_module("toy_chain")(ToyChain)
    yield
    clear_registries()


@pytest.fixture
def grouped(qapp):
    """A scene with two grouped toy_chains, and a view over it."""
    scene = StubScene()
    handles = [scene.add("toy_chain", name=name, side="L") for name in ("a", "b")]
    group = scene.group(handles, label="fingers")
    view = GraphView(guides=scene)
    return view, scene, group, handles


def test_an_expanded_group_draws_a_frame_around_its_members(grouped):
    view, scene, group, handles = grouped
    scene.set_frame(group.group_id, collapsed=False)
    view.rebuild()
    assert group.group_id in view.graph.frames
    assert {"L_a", "L_b"} <= set(view.graph.nodes)


def test_a_collapsed_group_draws_one_node_and_hides_its_members(grouped):
    view, scene, group, handles = grouped
    scene.set_frame(group.group_id, collapsed=True)
    view.rebuild()
    keys = set(view.graph.nodes)
    assert f"@{group.group_id}" in keys
    assert "L_a" not in keys
    assert "L_b" not in keys


def test_a_collapsed_group_node_is_titled_by_its_key(grouped):
    view, scene, group, handles = grouped
    scene.set_frame(group.group_id, collapsed=True)
    view.rebuild()
    node = view.graph.nodes[f"@{group.group_id}"]
    assert node.title == "L_fingers"
    assert "2" in node.subtitle


def test_a_group_defaults_to_collapsed(grouped):
    """The whole point is fewer nodes; a group that opened expanded would make
    the rigger collapse it every time the graph redrew."""
    view, scene, group, handles = grouped
    view.rebuild()
    assert f"@{group.group_id}" in view.graph.nodes


def test_the_collapsed_node_carries_one_input_port_per_distinct_name(grouped):
    """Unlike a reference, whose ports are only what crosses its boundary: an
    unwired group could then not be wired at all, which is the main thing the
    collapsed node is for."""
    view, scene, group, handles = grouped
    scene.set_frame(group.group_id, collapsed=True)
    view.rebuild()
    node = view.graph.nodes[f"@{group.group_id}"]
    expected = list(handles[0].module_class.input_names(handles[0].settings))
    assert list(node.inputs) == expected


def test_the_collapsed_node_carries_an_output_port_per_member(grouped):
    """Outputs stay per member: 'which one drives that' has no default answer."""
    view, scene, group, handles = grouped
    scene.set_frame(group.group_id, collapsed=True)
    view.rebuild()
    node = view.graph.nodes[f"@{group.group_id}"]
    assert len(node.outputs) == sum(len(h.outputs) for h in handles)


def test_toggling_the_frame_expands_the_group(grouped):
    view, scene, group, handles = grouped
    view.rebuild()
    view.toggle_frame(group.group_id)
    assert scene.frames[group.group_id]["collapsed"] is False
    assert "L_a" in view.graph.nodes


def test_an_ungrouped_module_is_untouched(grouped):
    view, scene, group, handles = grouped
    loose = scene.add("toy_root", name="spine")
    view.rebuild()
    assert loose.key in view.graph.nodes


def test_dissolving_the_group_brings_its_members_back(grouped):
    view, scene, group, handles = grouped
    view.rebuild()
    assert f"@{group.group_id}" in view.graph.nodes
    scene.ungroup(group.group_id)
    view.rebuild()
    assert {"L_a", "L_b"} <= set(view.graph.nodes)
    assert f"@{group.group_id}" not in view.graph.nodes


# ------------------------------------------------ fan-in and the picker
def test_wiring_a_collapsed_groups_input_wires_every_member(grouped):
    """'All of these attach to the same place' is a meaningful thing to say."""
    view, scene, group, handles = grouped
    other = scene.add("toy_root", name="hand")
    output = list(other.outputs)[0]
    view.rebuild()
    view._connect_to_group(group, "root", f"{other.key}.{output}")
    for handle in handles:
        assert handle.instance.inputs["root"] == f"{other.key}.{output}"


def test_wiring_a_group_input_skips_a_member_without_that_input(grouped):
    view, scene, group, handles = grouped
    other = scene.add("toy_root", name="hand")
    output = list(other.outputs)[0]
    view.rebuild()
    view._connect_to_group(group, "not_an_input", f"{other.key}.{output}")
    for handle in handles:
        assert "not_an_input" not in handle.instance.inputs


def test_dragging_from_a_group_output_asks_which_member(grouped, monkeypatch):
    """'Which one of these drives that' has no default answer, so fanning an
    output out would silently create wires the rigger did not intend."""
    view, scene, group, handles = grouped
    asked = {}

    def fake_pick(options, title=""):
        asked["options"] = list(options)
        return handles[1].instance_id

    monkeypatch.setattr(view, "_pick_member", fake_pick)
    assert view._pick_group_output_member(group) == handles[1].instance_id
    assert len(asked["options"]) == 2


def test_cancelling_the_member_picker_makes_no_connection(grouped, monkeypatch):
    view, scene, group, handles = grouped
    monkeypatch.setattr(view, "_pick_member", lambda options, title="": None)
    assert view._pick_group_output_member(group) is None


def test_the_member_picker_goes_through_feedback(grouped, monkeypatch):
    """Every dialog in the repo goes through Feedback; a raw QInputDialog here
    would fail tests/unit/test_dialog_boundaries.py."""
    from tik.shared.ui import feedback

    view, scene, group, handles = grouped
    seen = {}

    def handler(kind, title, text, details, buttons):
        seen["kind"] = kind
        seen["options"] = list(buttons)
        return buttons[1]

    previous = feedback.set_handler(handler)
    try:
        picked = view._pick_group_output_member(group)
    finally:
        feedback.set_handler(previous)
    assert seen["kind"] == "choice"
    assert seen["options"] == ["L_a", "L_b"]
    assert picked == handles[1].instance_id
