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
        segments = IntField(2, per_copy=True)
        size = FloatField(1.0)

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
