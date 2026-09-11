"""A section with no candidate controls does not render.

Spec: docs/superpowers/specs/2026-09-11-control-capability-declarations-design.md

A fold the rigger cannot use is worse than a missing one: it claims the module
offers something it does not.
"""

from __future__ import annotations

import pytest

from tik.core.fields import Column, FieldGroup, Schema, TableField
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
    assert fold is None or not fold.isVisible()


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


def test_a_ribbon_with_controllers_renders_all_three(qapp):
    form = _module_form("ribbon", qapp, {"mid_count": 2})
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
