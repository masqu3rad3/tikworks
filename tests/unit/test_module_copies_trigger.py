"""Module copies: the row list, slugs, and the per-copy view."""

import pytest

from tik.trigger.core.copies import (
    EMPTY_SLUG,
    CopyError,
    copy_name,
    duplicate_row,
    new_slug,
    normalise,
    row_for,
)

DEFAULTS = {"segments": 3, "spacing": 5.0}


def test_the_first_slug_is_empty():
    """Which is what makes an existing .tr already a one-copy module."""
    rows = normalise([], DEFAULTS, "fingers")
    assert [row["slug"] for row in rows] == [EMPTY_SLUG]


def test_normalise_fills_in_every_per_copy_value():
    rows = normalise([{"slug": "", "name": "index"}], DEFAULTS, "fingers")
    assert rows[0]["segments"] == 3
    assert rows[0]["spacing"] == 5.0


def test_normalise_keeps_values_that_are_already_there():
    rows = normalise([{"slug": "", "name": "i", "segments": 9}], DEFAULTS, "f")
    assert rows[0]["segments"] == 9


def test_normalise_drops_keys_that_are_no_longer_per_copy():
    """A field that stopped being per_copy must not leave a value behind."""
    rows = normalise([{"slug": "", "name": "i", "gone": 1}], DEFAULTS, "f")
    assert "gone" not in rows[0]


def test_new_slug_never_reuses_one():
    assert new_slug([""]) == "c1"
    assert new_slug(["", "c1"]) == "c2"
    assert new_slug(["", "c2"]) == "c1"


def test_row_for_finds_by_slug():
    rows = normalise(
        [{"slug": "", "name": "a"}, {"slug": "c1", "name": "b"}], DEFAULTS, "f"
    )
    assert row_for(rows, "c1")["name"] == "b"
    assert row_for(rows, "nope") is None


def test_duplicate_copies_the_values_not_the_defaults():
    """A fifth finger wants the fourth finger's settings, not the module's."""
    rows = normalise([{"slug": "", "name": "index", "segments": 9}], DEFAULTS, "f")
    made = duplicate_row(rows, "", DEFAULTS, taken_names={"index"})
    assert made["segments"] == 9
    assert made["slug"] == "c1"


def test_duplicate_gives_the_new_row_a_free_name():
    rows = normalise([{"slug": "", "name": "index"}], DEFAULTS, "f")
    made = duplicate_row(rows, "", DEFAULTS, taken_names={"index"})
    assert made["name"] != "index"
    assert made["name"]


def test_duplicating_an_unknown_slug_is_refused():
    rows = normalise([{"slug": "", "name": "index"}], DEFAULTS, "f")
    with pytest.raises(CopyError, match="no copy"):
        duplicate_row(rows, "nope", DEFAULTS, taken_names=set())


def test_a_blank_name_falls_back_to_the_module_name():
    """Which is what keeps an untouched single-copy module named as it is."""
    assert copy_name({"slug": "", "name": ""}, "arm") == "arm"
    assert copy_name({"slug": "", "name": "index"}, "fingers") == "index"


# ---------------------------------------------------------- on the module
def _toy():
    from tik.core.fields import FloatField, IntField
    from tik.trigger.core import GuideLayout, Module

    class Toy(Module):
        module_type = "toy"
        guides = GuideLayout("root", multi="segment", min=1)
        outputs = ("root", "end")
        controls = ("fk",)
        segments = IntField(2)
        size = FloatField(1.0, shared=True)

        def guide_count(self):
            return self.segments

        def draw_guides(self, guides):
            guides.joint("root", (0, 0, 0))
            for index in range(self.segments):
                guides.joint("segment", (index + 1, 0, 0), index=index)

        def build(self, rig):
            pass

    return Toy


def test_an_untouched_module_has_exactly_one_empty_slug():
    module = _toy()(name="arm")
    assert module.copy_slugs() == [EMPTY_SLUG]


def test_copy_rows_carry_the_per_copy_defaults():
    module = _toy()(name="arm")
    assert module.copy_rows()[0]["segments"] == 2


def test_a_shared_field_is_not_in_the_rows():
    module = _toy()(name="arm")
    assert "size" not in module.copy_rows()[0]


# -------------------------------------------------------- the per-copy view
def test_the_view_resolves_the_copys_per_copy_values():
    """Inside build(), self.segments is a plain int -- the module author
    never learns that copies exist."""
    module = _toy()(name="fingers")
    module.copies = [
        {"slug": "", "name": "index", "segments": 4},
        {"slug": "c1", "name": "thumb", "segments": 3},
    ]
    assert module.for_copy("").segments == 4
    assert module.for_copy("c1").segments == 3


def test_the_view_takes_the_copys_name():
    module = _toy()(name="fingers")
    module.copies = [{"slug": "", "name": "index", "segments": 4}]
    assert module.for_copy("").name == "index"


def test_a_blank_copy_name_leaves_the_module_name():
    module = _toy()(name="arm")
    assert module.for_copy("").name == "arm"


def test_the_view_keeps_the_shared_fields():
    module = _toy()(name="fingers", settings={"size": 7.0})
    assert module.for_copy("").size == 7.0


def test_the_view_is_itself_a_one_copy_module():
    """So every manifest call on it returns bare, unqualified names."""
    module = _toy()(name="fingers")
    module.copies = [
        {"slug": "", "name": "index", "segments": 4},
        {"slug": "c1", "name": "thumb", "segments": 3},
    ]
    assert module.for_copy("c1").copy_slugs() == [EMPTY_SLUG]


def test_the_view_keeps_the_modules_side_and_id():
    from tik.core.side import Side

    module = _toy()(name="fingers", side=Side.LEFT)
    view = module.for_copy("")
    assert view.side is Side.LEFT
    assert view.instance_id == module.instance_id


def test_an_unknown_slug_is_refused():
    module = _toy()(name="fingers")
    with pytest.raises(CopyError, match="no copy"):
        module.for_copy("nope")


def test_editing_the_view_does_not_touch_the_module():
    """The view is a projection, not a handle on the original."""
    module = _toy()(name="fingers")
    view = module.for_copy("")
    view.segments = 11
    assert module.copy_rows()[0]["segments"] == 2


# ------------------------------------------------- expansion and the manifest
def test_qualify_leaves_the_first_copy_bare():
    module = _toy()(name="arm")
    assert module.qualify("", "root") == "root"
    assert module.qualify("c1", "root") == "c1_root"


def test_one_copy_expands_to_todays_roles_exactly():
    """The zero-change guarantee, at the guide layer."""
    module = _toy()(name="arm")
    assert module.expected_guides() == [("root", 0), ("segment", 0), ("segment", 1)]


def test_a_second_copy_adds_prefixed_roles_and_disturbs_nothing():
    module = _toy()(name="fingers")
    module.copies = [
        {"slug": "", "name": "index", "segments": 2},
        {"slug": "c1", "name": "thumb", "segments": 1},
    ]
    assert module.expected_guides() == [
        ("root", 0),
        ("segment", 0),
        ("segment", 1),
        ("c1_root", 0),
        ("c1_segment", 0),
    ]


def test_outputs_are_qualified_per_copy():
    Toy = _toy()
    settings = {
        "copies": [{"slug": "", "name": "index"}, {"slug": "c1", "name": "thumb"}]
    }
    assert Toy.output_names(settings) == ("root", "end", "c1_root", "c1_end")


def test_one_copy_leaves_the_outputs_bare():
    assert _toy().output_names({}) == ("root", "end")


def test_controls_are_qualified_per_copy():
    Toy = _toy()
    settings = {
        "copies": [{"slug": "", "name": "index"}, {"slug": "c1", "name": "thumb"}]
    }
    assert Toy.control_names(settings) == ("fk", "c1_fk")


def test_a_settings_driven_manifest_still_works_per_copy():
    """fkchain returns one output per segment; each copy gets its own count."""
    import tik.trigger as trigger

    trigger.load_plugins()
    from tik.trigger.core import registry

    FkChain = registry.get_module("fkchain")
    settings = {
        "copies": [
            {"slug": "", "name": "index", "segments": 2},
            {"slug": "c1", "name": "thumb", "segments": 1},
        ]
    }
    names = FkChain.output_names(settings)
    assert names[:4] == ("root", "segment1", "segment2", "end")
    assert names[4:] == ("c1_root", "c1_segment1", "c1_end")


def test_validate_accepts_the_expanded_roles():
    module = _toy()(name="fingers")
    module.copies = [
        {"slug": "", "name": "index", "segments": 2},
        {"slug": "c1", "name": "thumb", "segments": 1},
    ]
    module.guide_pairs = module.expected_guides()
    assert module.validate() == []


def test_validate_still_catches_a_missing_guide():
    module = _toy()(name="fingers")
    module.copies = [
        {"slug": "", "name": "index", "segments": 2},
        {"slug": "c1", "name": "thumb", "segments": 1},
    ]
    module.guide_pairs = [
        pair for pair in module.expected_guides() if pair[0] != "c1_root"
    ]
    assert any("root" in problem for problem in module.validate())


def test_a_control_table_belongs_to_its_copy():
    """Each copy carries its own table, naming its own controls by their
    bare role -- so a tab shows four shape rows, not twenty."""
    module = _toy()(name="fingers")
    module.copies = [
        {
            "slug": "",
            "name": "index",
            "segments": 1,
            "control_shape_overrides": [{"control": "fk", "shape": "Circle"}],
        },
        {
            "slug": "c1",
            "name": "thumb",
            "segments": 1,
            "control_shape_overrides": [{"control": "fk", "shape": "Cube"}],
        },
    ]
    assert module.for_copy("").control_shape_overrides[0]["shape"] == "Circle"
    assert module.for_copy("c1").control_shape_overrides[0]["shape"] == "Cube"
    assert module.for_copy("c1").control_shape_overrides[0]["control"] == "fk"


def test_the_implicit_first_copy_inherits_the_modules_own_value():
    """A .tr written before copies existed holds segments at the top level
    and no copies at all; its single implicit copy must inherit that number,
    not revert to the class default."""
    module = _toy()(name="arm", settings={"segments": 7})
    assert module.copy_rows()[0]["segments"] == 7
    assert module.for_copy("").segments == 7


def test_an_old_settings_dict_keeps_its_manifest():
    Toy = _toy()
    assert Toy.output_names({"segments": 7}) == ("root", "end")
    assert Toy.control_names({"segments": 7}) == ("fk",)


def test_a_pre_copies_fkchain_keeps_its_outputs():
    import tik.trigger as trigger

    trigger.load_plugins()
    from tik.trigger.core import registry

    FkChain = registry.get_module("fkchain")
    assert FkChain.output_names({"segments": 2}) == (
        "root",
        "segment1",
        "segment2",
        "end",
    )


# ------------------------------------------------------------- per-copy inputs
def test_every_setting_is_per_copy_by_default():
    """A copy is a whole module's worth of settings."""
    Toy = _toy()
    assert "segments" in Toy.per_copy_fields()
    assert "size" in Toy.shared_fields()  # the one exception this toy declares


def test_the_copy_list_is_the_only_shared_field_on_module():
    """A copy is a whole module's worth of authoring -- settings, inputs,
    spaces, pivots and shapes -- and the list itself is the one thing that
    cannot belong to a copy."""
    from tik.trigger.core import Module

    assert list(Module.shared_fields()) == ["copies"]
    Toy = _toy()
    for name in ("anim_spaces", "pivot_presets", "control_shape_overrides"):
        assert name in Toy.per_copy_fields(), name


def test_inputs_are_qualified_per_copy():
    """Each copy attaches where it likes, so each has its own port."""
    Toy = _toy()
    settings = {
        "copies": [{"slug": "", "name": "index"}, {"slug": "c1", "name": "thumb"}]
    }
    assert Toy.input_names(settings) == ["root", "c1_root"]


def test_one_copy_leaves_the_input_bare():
    assert _toy().input_names({}) == ["root"]


def test_get_input_resolves_a_qualified_name():
    Toy = _toy()
    settings = {
        "copies": [{"slug": "", "name": "index"}, {"slug": "c1", "name": "thumb"}]
    }
    assert Toy.get_input("c1_root", settings).name == "root"
    assert Toy.get_input("root", settings).name == "root"
    assert Toy.get_input("c9_root", settings) is None


def test_the_primary_input_is_still_the_first_copys():
    """One module, one tree row, one parent: the first copy's."""
    Toy = _toy()
    assert Toy.primary_input().name == "root"


# ---------------------------------------------------- a shared input
def _shared_input_toy():
    from tik.core.fields import IntField
    from tik.trigger.core import GuideLayout, Input, Module

    class Anchored(Module):
        module_type = "anchored"
        guides = GuideLayout("root")
        inputs = (
            Input("root", primary=True),
            Input("world", shared=True),
        )
        outputs = ("root",)
        segments = IntField(1)

        def draw_guides(self, guides):
            guides.joint("root", (0, 0, 0))

        def build(self, rig):
            pass

    return Anchored


def test_an_input_is_per_copy_unless_it_says_otherwise():
    from tik.trigger.core import Input

    assert Input("root").shared is False
    assert Input("world", shared=True).shared is True


def test_a_shared_input_keeps_one_unqualified_port():
    """One declaration, one port, however many copies: the whole hand hangs
    off the same thing and the rigger wires it once."""
    Anchored = _shared_input_toy()
    settings = {"copies": [{"slug": "", "name": "a"}, {"slug": "c1", "name": "b"}]}
    assert Anchored.input_names(settings) == ["root", "world", "c1_root"]


def test_a_shared_input_resolves_unqualified():
    Anchored = _shared_input_toy()
    settings = {"copies": [{"slug": ""}, {"slug": "c1"}]}
    assert Anchored.get_input("world", settings).name == "world"
    assert Anchored.get_input("c1_world", settings) is None


# ------------------------------------------------------- naming a new copy
def test_a_new_copy_is_the_module_name_plus_a_number():
    """arm / arm1 / arm2, the way Maya names a duplicate."""
    rows = normalise([{"slug": "", "name": ""}], DEFAULTS, "arm")
    made = duplicate_row(rows, "", DEFAULTS, taken_names={"arm"}, base="arm")
    assert made["name"] == "arm1"

    rows.append(made)
    again = duplicate_row(rows, "", DEFAULTS, taken_names={"arm", "arm1"}, base="arm")
    assert again["name"] == "arm2"


def test_the_base_wins_over_the_source_copys_name():
    """Duplicating `thumb` on an `arm` module still gives arm1, not thumb1:
    the numbering belongs to the module, as it does in Maya."""
    rows = normalise([{"slug": "", "name": "thumb"}], DEFAULTS, "arm")
    made = duplicate_row(rows, "", DEFAULTS, taken_names={"thumb"}, base="arm")
    assert made["name"] == "arm"


# ------------------------------------ the three candidate sets, per copy
def test_space_control_names_qualify_per_copy():
    from tik.trigger.core import get_module

    module = get_module("base")(name="base")
    module.copies = [{"slug": "", "name": "a"}, {"slug": "c1", "name": "b"}]
    assert type(module).space_control_names(module.values()) == ("root", "c1_root")


def test_shape_control_names_qualify_per_copy():
    from tik.trigger.core import get_module

    module = get_module("base")(name="base")
    module.copies = [{"slug": "", "name": "a"}, {"slug": "c1", "name": "b"}]
    assert type(module).shape_control_names(module.values()) == ("root", "c1_root")


def test_pivot_anchor_resolves_per_copy():
    """Two copies of a chain anchor to their own guides, not copy one's."""
    from tik.trigger.core import get_module

    module = get_module("fkchain")(name="chain")
    module.copies = [
        {"slug": "", "name": "a", "segments": 2},
        {"slug": "c1", "name": "b", "segments": 3},
    ]
    values = module.values()
    assert type(module).pivot_anchor("c1_fk2", values) == ("segment", 1)
    # Copy one has two segments, so it builds no fk2 and offers no anchor.
    assert type(module).pivot_anchor("fk2", values) is None


def test_a_copy_view_sees_only_its_own_candidates():
    from tik.trigger.core import get_module

    module = get_module("base")(name="base")
    module.copies = [{"slug": "", "name": "a"}, {"slug": "c1", "name": "b"}]
    view = module.for_copy("c1")
    assert type(view).space_control_names(view.values()) == ("root",)
