"""A section with no candidate controls does not render.

Spec: docs/superpowers/specs/2026-09-11-control-capability-declarations-design.md

A fold the rigger cannot use is worse than a missing one: it claims the module
offers something it does not.
"""

from __future__ import annotations

import pytest

from tik.core.fields import Column, FieldGroup, ListField, Schema, TableField
from tik.shared.ui.fields import FormBuilder

GROUP = FieldGroup("Rows", collapsed=True)


class Toy(Schema):
    """A table whose only option column is resolved from the target."""

    options: tuple = ()
    table = TableField(
        [],
        label="Table",
        group=GROUP,
        columns=(
            Column("control", "choice", choices_from="options"),
            Column("mode", "choice", choices=("parent", "point")),
        ),
    )


def _form(target, qapp):
    return FormBuilder(target)


# ------------------------------------------------------------- the rule
def test_a_table_with_no_options_renders_no_widget(qapp):
    form = _form(Toy(), qapp)
    with pytest.raises(KeyError):
        form.widget("table")


def test_its_fold_hides_with_it(qapp):
    form = _form(Toy(), qapp)
    fold = form._groups.get("Rows")
    # isHidden, not isVisible: nothing here is shown, so isVisible is False
    # for every fold and the assertion would pass without hiding anything.
    assert fold is None or fold.isHidden()


def test_the_fold_stays_hidden_through_set_visible_fields(qapp):
    """The designer calls it after every set_target, so it is the real path.

    It decided a fold's visibility from every *declared* field rather than
    the ones that got a widget, so it put back every fold set_target had
    just closed.
    """
    form = _form(Toy(), qapp)
    form.set_visible_fields(["table"])
    fold = form._groups.get("Rows")
    assert fold is None or fold.isHidden()


def test_a_live_fold_survives_set_visible_fields(qapp):
    """The other direction: a fold with something in it must stay open."""
    target = Toy()
    target.options = ("a", "b")
    form = _form(target, qapp)
    form.set_visible_fields(["table"])
    assert not form._groups["Rows"].isHidden()


def test_a_table_with_options_renders(qapp):
    target = Toy()
    target.options = ("a", "b")
    assert _form(target, qapp).widget("table") is not None


def test_a_table_holding_rows_renders_even_with_no_options(qapp):
    """The stale-row escape: the rigger must be able to delete what is there.

    A setting that narrows the candidates must never strand a row somewhere
    the rigger cannot reach it.
    """
    target = Toy()
    target.table = [{"control": "gone", "mode": "parent"}]
    assert _form(target, qapp).widget("table") is not None


def test_a_static_column_alone_does_not_keep_a_dead_table(qapp):
    """The test is per column: one empty resolved column is enough.

    ``mode`` has fixed choices and can never empty, so a table kept alive by
    it would still offer rows nobody can fill in.
    """
    form = _form(Toy(), qapp)
    assert "table" not in form._widgets


# ------------------------------------------------- the three real sections
SECTIONS = ("anim_spaces", "pivot_presets", "control_shape_overrides")


def _module_form(module_type, qapp, settings=None):
    import tik.trigger as trigger
    from tik.trigger.core import get_module

    trigger.load_plugins()
    module = get_module(module_type)(name=module_type)
    if settings:
        module.apply(settings, strict=False)
    return FormBuilder(module)


def test_twist_renders_none_of_the_three_sections(qapp):
    """It builds no controllers at all, so all three tables are unfillable."""
    form = _module_form("twist", qapp)
    for name in SECTIONS:
        assert name not in form._widgets


def test_twist_hides_all_three_folds_the_way_the_designer_builds_them(qapp):
    """The whole sequence the properties panel runs, not just set_target.

    An empty fold is the visible half of the complaint: three boxes that open
    onto nothing.
    """
    from tik.trigger.core import get_module

    module = get_module("twist")(name="twist")
    form = FormBuilder(module)
    form.set_visible_fields(list(type(module).per_copy_fields()))
    for label in ("Spaces", "Pivots", "Shapes"):
        fold = form._groups.get(label)
        assert fold is None or fold.isHidden(), f"{label} fold is still shown"


def test_arm_keeps_all_three_folds_through_the_same_sequence(qapp):
    from tik.trigger.core import get_module

    module = get_module("arm")(name="arm")
    form = FormBuilder(module)
    form.set_visible_fields(list(type(module).per_copy_fields()))
    for label in ("Spaces", "Pivots", "Shapes"):
        assert not form._groups[label].isHidden(), f"{label} fold went missing"


def test_arm_renders_all_three(qapp):
    form = _module_form("arm", qapp)
    for name in SECTIONS:
        assert form.widget(name) is not None


def test_a_ribbon_with_no_controllers_renders_none(qapp):
    form = _module_form(
        "ribbon",
        qapp,
        {"mid_count": 0, "start_controller": False, "end_controller": False},
    )
    for name in SECTIONS:
        assert name not in form._widgets


def test_a_ribbon_of_mids_alone_offers_spaces_and_shapes_but_no_pivots(qapp):
    """A mid is exempt from pivots, so that one section has no candidates.

    The three sections answer separately, which is the whole point of naming
    them separately.
    """
    form = _module_form("ribbon", qapp, {"mid_count": 2})
    assert form.widget("anim_spaces") is not None
    assert form.widget("control_shape_overrides") is not None
    assert "pivot_presets" not in form._widgets
    assert form._groups["Pivots"].isHidden()


def test_a_ribbon_with_an_end_controller_renders_all_three(qapp):
    """The ends do take a pivot, so the fold comes back with one."""
    form = _module_form("ribbon", qapp, {"mid_count": 2, "end_controller": True})
    for name in SECTIONS:
        assert form.widget(name) is not None


# ----------------------------------------- the panel notices a set emptying
def test_topology_notices_a_candidate_set_emptying():
    """Without this the folds stay on screen until something else rebuilds."""
    import tik.trigger as trigger
    from tik.trigger.core import get_module
    from tik.trigger.ui.designer.properties import DesignerProperties

    trigger.load_plugins()
    module_cls = get_module("ribbon")

    class _Handle:
        def __init__(self, settings):
            self.module_class = module_cls
            self.settings = settings
            self.instance = type("I", (), {"guides": ()})()

    full = _Handle({"mid_count": 2, "start_controller": True})
    none = _Handle({"mid_count": 0, "start_controller": False, "end_controller": False})
    assert DesignerProperties._topology(full) != DesignerProperties._topology(none)


def test_topology_notices_a_narrowed_space_set():
    """A module may narrow one set without changing the controls it builds."""
    from tik.trigger.core import Module
    from tik.trigger.ui.designer.properties import DesignerProperties

    class Wide(Module):
        controls = ("a", "b")
        control_shapes = {"a": "Circle", "b": "Circle"}

    class Narrow(Wide):
        space_controls = ("a",)

    class _Handle:
        def __init__(self, module_class):
            self.module_class = module_class
            self.settings = {}
            self.instance = type("I", (), {"guides": ()})()

    assert DesignerProperties._topology(_Handle(Wide)) != DesignerProperties._topology(
        _Handle(Narrow)
    )


# ------------------------------------------------- the same rule, for a list
class ListToy(Schema):
    """A tick list whose options are resolved from the target."""

    options: tuple = ()
    picked = ListField([], item_type=str, group=GROUP, choices_from="options")


def test_a_list_nobody_can_tick_renders_no_widget(qapp):
    """Same rule as a table nobody can fill, same reason."""
    form = _form(ListToy(), qapp)
    with pytest.raises(KeyError):
        form.widget("picked")


def test_an_unfillable_lists_fold_hides_with_it(qapp):
    form = _form(ListToy(), qapp)
    fold = form._groups.get("Rows")
    assert fold is None or fold.isHidden()


def test_a_list_holding_a_value_always_renders(qapp):
    """A setting that narrowed the options must never strand a tick."""
    target = ListToy()
    target.picked = ["gone"]
    form = _form(target, qapp)
    assert form.widget("picked") is not None
