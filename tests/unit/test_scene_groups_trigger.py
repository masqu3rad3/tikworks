"""Scene-node groups: the ``SceneGroupsMixin`` on ``GuideScene``.

The graph lets a rigger bundle loose Maya nodes into a named group and connect
module inputs to them. Until this file the mixin had no direct tests at all --
``tests/ui/stub.py`` carries a *reimplementation* of it, so the designer tests
passed against a copy while the real code went unexercised.
"""

import pytest

from tik.trigger.core.exceptions import GuideError


@pytest.fixture
def rig(guides):
    """Guides with a ``base`` module, so key collisions can be tested."""
    guides.add("base", name="body")
    return guides


class TestAdding:
    """``add_scene_group`` names, defaults and collisions."""

    def test_an_unnamed_group_gets_the_first_free_number(self, rig):
        assert rig.add_scene_group() == "sceneNodes1"
        assert rig.add_scene_group() == "sceneNodes2"

    def test_numbering_steps_over_a_name_already_taken(self, rig):
        rig.add_scene_group("sceneNodes1")
        rig.add_scene_group("sceneNodes2")

        assert rig.add_scene_group() == "sceneNodes3"

    def test_a_named_group_keeps_its_nodes(self, rig):
        rig.add_scene_group("chest", ["chest_jnt", "spine_jnt"])

        assert rig.scene_groups() == {"chest": ["chest_jnt", "spine_jnt"]}

    def test_a_group_defaults_to_empty(self, rig):
        name = rig.add_scene_group("chest")

        assert rig.scene_groups()[name] == []

    def test_a_duplicate_group_name_is_rejected(self, rig):
        rig.add_scene_group("chest")

        with pytest.raises(GuideError, match="already used"):
            rig.add_scene_group("chest")

    def test_a_module_key_cannot_be_reused_as_a_group_name(self, rig):
        """``body`` is a module; the graph could not tell the two nodes apart."""
        with pytest.raises(GuideError, match="already used"):
            rig.add_scene_group("body")

    def test_the_returned_mapping_is_a_copy(self, rig):
        rig.add_scene_group("chest", ["chest_jnt"])

        rig.scene_groups()["chest"].append("bogus_jnt")

        assert rig.scene_groups() == {"chest": ["chest_jnt"]}


class TestSetting:
    """``set_scene_group`` replaces members and prunes what they fed."""

    def test_an_unknown_group_is_rejected(self, rig):
        with pytest.raises(GuideError, match="No scene-nodes group"):
            rig.set_scene_group("nope", ["chest_jnt"])

    def test_the_nodes_are_replaced_wholesale(self, rig):
        rig.add_scene_group("chest", ["old_jnt"])

        rig.set_scene_group("chest", ["new_jnt", "other_jnt"])

        assert rig.scene_groups() == {"chest": ["new_jnt", "other_jnt"]}

    def test_blank_entries_are_dropped(self, rig):
        """The properties panel hands back a row per line, blanks included."""
        rig.add_scene_group("chest")

        rig.set_scene_group("chest", ["chest_jnt", "", "spine_jnt"])

        assert rig.scene_groups() == {"chest": ["chest_jnt", "spine_jnt"]}

    def test_dropping_a_node_disconnects_what_it_fed(self, rig):
        arm = rig.add("arm", side="L", name="arm")
        rig.add_scene_group("chest", ["chest_jnt"])
        rig.connect("L_arm.root", "chest_jnt")

        rig.set_scene_group("chest", ["spine_jnt"])

        assert arm.inputs == {}

    def test_keeping_a_node_keeps_its_connection(self, rig):
        arm = rig.add("arm", side="L", name="arm")
        rig.add_scene_group("chest", ["chest_jnt", "spine_jnt"])
        rig.connect("L_arm.root", "chest_jnt")

        rig.set_scene_group("chest", ["chest_jnt"])

        assert arm.inputs == {"root": "chest_jnt"}

    def test_a_node_another_group_still_lists_stays_connected(self, rig):
        """Membership, not this one group, is what keeps the connection alive."""
        arm = rig.add("arm", side="L", name="arm")
        rig.add_scene_group("chest", ["shared_jnt"])
        rig.add_scene_group("spine", ["shared_jnt"])
        rig.connect("L_arm.root", "shared_jnt")

        rig.set_scene_group("chest", [])

        assert arm.inputs == {"root": "shared_jnt"}


class TestRenaming:
    """``rename_scene_group`` moves the name and everything keyed by it."""

    def test_an_unknown_group_is_rejected(self, rig):
        with pytest.raises(GuideError, match="No scene-nodes group"):
            rig.rename_scene_group("nope", "chest")

    @pytest.mark.parametrize("new", ["", "   ", "chest"])
    def test_a_blank_or_unchanged_name_is_a_no_op(self, rig, new):
        rig.add_scene_group("chest", ["chest_jnt"])

        rig.rename_scene_group("chest", new)

        assert rig.scene_groups() == {"chest": ["chest_jnt"]}

    def test_the_new_name_is_stripped(self, rig):
        rig.add_scene_group("chest", ["chest_jnt"])

        rig.rename_scene_group("chest", "  torso  ")

        assert rig.scene_groups() == {"torso": ["chest_jnt"]}

    def test_colliding_with_another_group_is_rejected(self, rig):
        rig.add_scene_group("chest")
        rig.add_scene_group("spine")

        with pytest.raises(GuideError, match="already used"):
            rig.rename_scene_group("chest", "spine")

    def test_colliding_with_a_module_key_is_rejected(self, rig):
        rig.add_scene_group("chest")

        with pytest.raises(GuideError, match="already used"):
            rig.rename_scene_group("chest", "body")

    def test_the_nodes_come_along(self, rig):
        rig.add_scene_group("chest", ["chest_jnt", "spine_jnt"])

        rig.rename_scene_group("chest", "torso")

        assert rig.scene_groups() == {"torso": ["chest_jnt", "spine_jnt"]}

    def test_the_graph_position_and_collapse_come_along(self, rig):
        """A rename must not cost the node its place in the graph."""
        rig.add_scene_group("chest", ["chest_jnt"])
        rig.update_layout(positions={"chest": [10.0, 20.0]}, collapse={"chest": 2})

        rig.rename_scene_group("chest", "torso")

        layout = rig.layout
        assert layout["positions"] == {"torso": [10.0, 20.0]}
        assert layout["collapse"] == {"torso": 2}

    def test_another_nodes_layout_is_left_alone(self, rig):
        rig.add_scene_group("chest", ["chest_jnt"])
        rig.add_scene_group("spine", ["spine_jnt"])
        rig.update_layout(positions={"chest": [1.0, 2.0], "spine": [3.0, 4.0]})

        rig.rename_scene_group("chest", "torso")

        assert rig.layout["positions"] == {"torso": [1.0, 2.0], "spine": [3.0, 4.0]}

    def test_a_connection_to_a_member_survives(self, rig):
        """Connections name the *node*, not the group, so a rename cannot break one."""
        arm = rig.add("arm", side="L", name="arm")
        rig.add_scene_group("chest", ["chest_jnt"])
        rig.connect("L_arm.root", "chest_jnt")

        rig.rename_scene_group("chest", "torso")

        assert arm.inputs == {"root": "chest_jnt"}


class TestRemoving:
    """``remove_scene_group`` takes the group, its layout and its connections."""

    def test_the_group_is_gone(self, rig):
        rig.add_scene_group("chest", ["chest_jnt"])

        rig.remove_scene_group("chest")

        assert rig.scene_groups() == {}

    def test_removing_an_unknown_group_is_quiet(self, rig):
        rig.add_scene_group("chest", ["chest_jnt"])

        rig.remove_scene_group("nope")

        assert rig.scene_groups() == {"chest": ["chest_jnt"]}

    def test_what_its_nodes_fed_is_disconnected(self, rig):
        arm = rig.add("arm", side="L", name="arm")
        rig.add_scene_group("chest", ["chest_jnt"])
        rig.connect("L_arm.root", "chest_jnt")

        rig.remove_scene_group("chest")

        assert arm.inputs == {}

    def test_a_node_another_group_still_lists_stays_connected(self, rig):
        arm = rig.add("arm", side="L", name="arm")
        rig.add_scene_group("chest", ["shared_jnt"])
        rig.add_scene_group("spine", ["shared_jnt"])
        rig.connect("L_arm.root", "shared_jnt")

        rig.remove_scene_group("chest")

        assert arm.inputs == {"root": "shared_jnt"}

    def test_its_graph_layout_goes_too(self, rig):
        rig.add_scene_group("chest", ["chest_jnt"])
        rig.update_layout(positions={"chest": [10.0, 20.0]}, collapse={"chest": 1})

        rig.remove_scene_group("chest")

        assert "chest" not in rig.document.positions
        assert "chest" not in rig.document.collapse


class TestLookup:
    """``scene_node_group`` answers 'which group lists this node?'."""

    def test_a_member_reports_its_group(self, rig):
        rig.add_scene_group("chest", ["chest_jnt"])

        assert rig.scene_node_group("chest_jnt") == "chest"

    def test_a_stranger_reports_nothing(self, rig):
        rig.add_scene_group("chest", ["chest_jnt"])

        assert rig.scene_node_group("elsewhere_jnt") is None

    def test_nothing_is_reported_when_there_are_no_groups(self, rig):
        assert rig.scene_node_group("chest_jnt") is None


def test_groups_round_trip_through_a_trg(rig, tmp_path):
    """The document owns the groups; they are not derived from the scene."""
    from tik.trigger.guides import GuideScene

    rig.add_scene_group("chest", ["chest_jnt", "spine_jnt"])
    rig.update_layout(positions={"chest": [5.0, 6.0]})
    path = rig.export(tmp_path / "hero")

    reopened = GuideScene()
    reopened.import_(path)

    assert reopened.scene_groups() == {"chest": ["chest_jnt", "spine_jnt"]}
    assert reopened.layout["positions"]["chest"] == [5.0, 6.0]


def test_clear_takes_the_modules_and_leaves_the_groups(rig):
    """``clear`` is documented as module-only; a scene group is not a module."""
    rig.add_scene_group("chest", ["chest_jnt"])

    rig.clear()

    assert rig.document.modules == []
    assert rig.scene_groups() == {"chest": ["chest_jnt"]}
