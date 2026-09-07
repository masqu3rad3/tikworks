"""The Switches shell, offscreen, against a fabricated context.

The window never touches Maya; every scene read is behind ``HAS_MAYA`` or in
``times_provider``. These tests are what that buys.
"""

import pytest

from tik.trigger.anim import registry as switch_registry
from tik.trigger.anim.context import Control, SwitchContext
from tik.trigger.anim.registry import clear_switches, register_switch
from tik.trigger.anim.switch import Switch
from tik.trigger.anim.window import SwitchesWindow


@pytest.fixture(autouse=True)
def _switches():
    kept = switch_registry.registered()
    clear_switches()

    @register_switch("toy")
    class Toy(Switch):
        label = "Toy"
        help = "A toy switch."
        order = 10

        def states(self, context):
            return ["a", "b", "c"] if context.controls else []

        def current(self, context):
            return {1: "a", 2: None}.get(len(context.controls))

        def apply(self, context, state, *, key, times):
            Toy.applied = (state, key, tuple(times))
            return f"Switched to {state}"

    @register_switch("later")
    class Later(Switch):
        label = "Later"
        help = "Will do something one day."
        order = 20
        available = False

    yield Toy
    switch_registry.restore(kept)


def _window():
    window = SwitchesWindow()
    window.times_provider = lambda: (1.0,)
    return window


def _one():
    return SwitchContext(
        nodes=("|rig|L_arm_ik_ctrl",),
        controls=(
            Control(node="|rig|L_arm_ik_ctrl", role="ik", side="L", module="arm"),
        ),
    )


def _two():
    return SwitchContext(
        nodes=("|rig|L_arm_ik_ctrl", "|rig|R_arm_ik_ctrl"),
        controls=(
            Control(node="|rig|L_arm_ik_ctrl", role="ik", side="L", module="arm"),
            Control(node="|rig|R_arm_ik_ctrl", role="ik", side="R", module="arm"),
        ),
    )


# --------------------------------------------------------------------- tabs
def test_a_tab_per_switch_in_order(qapp):
    window = _window()
    assert [window.tabs.tabText(index) for index in range(window.tabs.count())] == [
        "Toy",
        "Later",
    ]


def test_an_unavailable_tab_is_still_selectable(qapp):
    """A tab that vanishes changes the tool's shape under the animator."""
    window = _window()
    window.set_context(_one())
    window.tabs.setCurrentIndex(1)
    assert window.tabs.currentIndex() == 1


# ---------------------------------------------------------------- selection
def test_empty_selection_disables_apply_and_says_so(qapp):
    window = _window()
    window.set_context(SwitchContext())
    assert window.can_apply is False
    assert window.states == []
    assert "Select a rig control" in window.body_note.text()
    assert window.context_label.text() == "Nothing selected"


def test_one_control_shows_its_name_and_current_state(qapp):
    window = _window()
    window.set_context(_one())
    assert window.context_label.text() == "L_arm_ik_ctrl"
    assert window.module_label.text() == "L_arm"
    assert window.states == ["a", "b", "c"]
    assert window.current == "a"
    assert window.pending is None
    assert window.can_apply is False


def test_several_controls_are_counted_and_their_modules_listed(qapp):
    window = _window()
    window.set_context(_two())
    assert window.context_label.text() == "2 controls"
    assert window.module_label.text() == "L_arm, R_arm"


# ------------------------------------------------------------------- choice
def test_choosing_a_state_arms_apply(qapp):
    window = _window()
    window.set_context(_one())
    window.choose("b")
    assert window.pending == "b"
    assert window.can_apply is True
    assert window.apply_button.isEnabled() is True


def test_choosing_the_current_state_does_not_arm_apply(qapp):
    window = _window()
    window.set_context(_one())
    window.choose("a")
    assert window.pending is None
    assert window.can_apply is False


def test_a_mixed_selection_arms_apply_for_any_state(qapp):
    window = _window()
    window.set_context(_two())
    assert window.current is None
    window.choose("a")
    assert window.can_apply is True


def test_a_new_selection_drops_the_pending_choice(qapp):
    window = _window()
    window.set_context(_one())
    window.choose("c")
    window.set_context(_two())
    assert window.pending is None


# -------------------------------------------------------------------- apply
def test_apply_runs_the_switch_and_reports(qapp, _switches):
    window = _window()
    window.set_context(_one())
    window.choose("c")
    window.apply()
    assert _switches.applied == ("c", True, (1.0,))
    assert window.status_label.text() == "Switched to c"
    assert window.pending is None
    assert window.can_apply is False


def test_apply_passes_the_key_choice_through(qapp, _switches):
    window = _window()
    window.set_context(_one())
    window.key_box.setChecked(False)
    window.choose("b")
    window.apply()
    assert _switches.applied == ("b", False, (1.0,))


def test_apply_does_nothing_when_not_armed(qapp, _switches):
    window = _window()
    window.set_context(_one())
    _switches.applied = None
    window.apply()
    assert _switches.applied is None


# -------------------------------------------------------------- placeholder
def test_a_placeholder_tab_shows_its_help_and_never_applies(qapp):
    window = _window()
    window.set_context(_one())
    window.tabs.setCurrentIndex(1)
    assert window.states == []
    assert window.can_apply is False
    note = window.body_note.text()
    assert "Not built yet" in note
    assert "Will do something one day" in note
    assert "Not built yet" not in window.status_label.text()


# --------------------------------------------------------------------- bars
def test_the_range_button_names_the_range(qapp):
    window = _window()
    window.set_playback_range(1.0, 120.0)
    assert window.range_button.text() == "Range 1–120"


def test_frame_is_the_default_scope(qapp):
    window = _window()
    assert window.frame_button.isChecked() is True
    assert window.range_button.isChecked() is False


# ------------------------------------------------------------ scene seeding
def test_a_new_window_shows_the_live_selection(qapp, monkeypatch):
    """Construction seeds from the scene. It once cleared straight afterwards,
    so the tool opened empty over a live selection."""
    from tik.trigger.anim import window as window_module

    monkeypatch.setattr(window_module, "HAS_MAYA", True)
    monkeypatch.setattr(
        window_module.SwitchContext, "from_scene", classmethod(lambda cls: _one())
    )
    window = SwitchesWindow()
    window.times_provider = lambda: (1.0,)
    assert window.context_label.text() == "L_arm_ik_ctrl"
    assert window.states == ["a", "b", "c"]


def test_refresh_from_scene_is_inert_without_maya(qapp):
    window = _window()
    window.set_context(_one())
    window.refresh_from_scene()
    assert window.context_label.text() == "L_arm_ik_ctrl"


def test_own_to_maya_is_inert_without_maya(qapp):
    """The floating-window owner step must never fire outside Maya."""
    window = _window()
    before = window.parent()
    window.own_to_maya()
    assert window.parent() is before


def test_own_to_maya_leaves_a_docked_window_alone(qapp, monkeypatch):
    """Claiming a widget Maya has put in a workspace control would steal it
    out of the control, leaving a floating tool beside an empty panel."""
    from tik.shared.ui import maya_window

    monkeypatch.setattr(
        SwitchesWindow, "_workspace_control", lambda self: "SomeWorkspaceControl"
    )
    monkeypatch.setattr(maya_window, "get_main_window", lambda: qapp.activeWindow())
    window = _window()
    before = window.parent()
    window.own_to_maya()
    assert window.parent() is before
