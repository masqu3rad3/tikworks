"""Guide kinds: what a guide *is*, and what the framework may derive from it.

Pure -- no Maya. The appearance these kinds resolve to lives in
``tik/trigger/guides/nodes.py`` and is covered by the integration tests.
"""

import pytest

from tik.trigger.core import GuideKind, GuideLayout


def test_first_role_is_root_and_the_rest_are_joints():
    layout = GuideLayout("collar", "shoulder", "elbow", "hand")
    assert layout.kind_for("collar", is_root=True) is GuideKind.ROOT
    assert layout.kind_for("shoulder") is GuideKind.JOINT
    assert layout.kind_for("hand") is GuideKind.JOINT


def test_declared_reference_wins_over_derivation():
    layout = GuideLayout("collar", "shoulder", "neutral", reference=("neutral",))
    assert layout.kind_for("neutral") is GuideKind.REFERENCE
    assert layout.reference == ("neutral",)


def test_declared_driven_wins_over_derivation():
    layout = GuideLayout("base", "end", multi="twist", driven=("twist",))
    assert layout.kind_for("twist") is GuideKind.DRIVEN
    assert layout.driven == ("twist",)


def test_a_multi_role_may_be_declared():
    # the multi role is not in `roles`, so validation must consult all_roles
    GuideLayout("base", multi="twist", driven=("twist",))


def test_unknown_role_is_a_plain_joint():
    # pivot preset roles are created by the framework and are not in any layout
    layout = GuideLayout("hand")
    assert layout.kind_for("pivot_ik_wrist") is GuideKind.JOINT


def test_reference_naming_an_absent_role_raises():
    with pytest.raises(ValueError, match="not one of its roles"):
        GuideLayout("collar", "shoulder", reference=("nope",))


def test_driven_naming_an_absent_role_raises():
    with pytest.raises(ValueError, match="not one of its roles"):
        GuideLayout("collar", "shoulder", driven=("nope",))


def test_a_role_in_both_raises():
    with pytest.raises(ValueError, match="both reference and driven"):
        GuideLayout("collar", "neutral", reference=("neutral",), driven=("neutral",))


def test_the_root_role_may_not_be_declared():
    # root_guide() and parent_ref() walk joints; a module's root must be one
    with pytest.raises(ValueError, match="root role"):
        GuideLayout("collar", "shoulder", reference=("collar",))
    with pytest.raises(ValueError, match="root role"):
        GuideLayout("collar", "shoulder", driven=("collar",))


def test_defaults_are_empty_so_existing_layouts_are_unchanged():
    layout = GuideLayout("root", multi="segment", min=2)
    assert layout.reference == ()
    assert layout.driven == ()
    assert layout.kind_for("segment") is GuideKind.JOINT
